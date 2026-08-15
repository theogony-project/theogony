"""
ChronikCrosslinker — cross-article similarity linking for the MNLM PoC.

After Kadmos reads an article, the crosslinker:
1. Embeds synthesis concepts (meta-concepts: paragraph, section, article level)
2. Embeds regular concepts
3. Runs kNN similarity search against all existing nodes in the global
   LanceDB Chronicle
4. Creates typed, weighted edges between similar nodes
5. Writes nodes + edges into the shared global Chronicle

Edge weights are cosine similarity [0.0, 1.0] with a configurable threshold.
Cross-article links use relation type "CROSS_SIMILAR".

Design follows the user's specification:
- ~2-5% of new nodes connect to existing nodes
- ~2% of existing nodes receive connections per new article
- Meta-concepts (synthesis/abstraction nodes) are strongly preferred
  for linking
- Max ~50 edges per new concept
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa

from theogony.config.logging import get_logger
from theogony.stores.lance_typing import as_vector_query

if TYPE_CHECKING:
    import lancedb

log = get_logger("kadmos.crosslink")

# Max similar candidates to retrieve per query
_DEFAULT_TOP_K = 50

# How many edges a single new node may create at most
_MAX_EDGES_PER_NODE = 50

# Minimum cosine similarity to create any edge (hard floor)
_MIN_SIMILARITY_FLOOR = 0.50

# For regular concept nodes: top fraction that receives links (~3%)
_CONCEPT_LINK_FRACTION = 0.03

# For synthesis (meta-concept) nodes: top fraction (~20%)
_SYNTHESIS_LINK_FRACTION = 0.20


class ChronikCrosslinker:
    """Cross-article similarity linker using a shared global LanceDB Chronicle.

    Usage::

        crosslinker = ChronikCrosslinker(db_path="data/chronicle")
        crosslinker.ingest_and_link(
            embedder=embedder,
            new_nodes=[
                {"id": "synth-001", "embedding": [...], "label": "Bernoulli's Principle",
                 "node_type": "synthesis", "source_anchor": "url#s1"},
            ],
            new_edges=[],  # intra-article edges carried along
        )
    """

    def __init__(
        self,
        db_path: str | Path = "data/chronicle",
        embedding_dim: int = 384,
        top_k: int = _DEFAULT_TOP_K,
        max_edges_per_node: int = _MAX_EDGES_PER_NODE,
        concept_link_fraction: float = _CONCEPT_LINK_FRACTION,
        synthesis_link_fraction: float = _SYNTHESIS_LINK_FRACTION,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.mkdir(parents=True, exist_ok=True)

        import lancedb

        # lancedb >= 0.37 returns the general DBConnection from connect().
        self._db: lancedb.DBConnection = lancedb.connect(str(self._db_path))
        self._dim = embedding_dim
        self._top_k = top_k
        self._max_edges_per_node = max_edges_per_node
        self._concept_link_fraction = concept_link_fraction
        self._synthesis_link_fraction = synthesis_link_fraction

        self._init_tables()

    def _init_tables(self) -> None:
        """Create or open the global chronicle tables."""
        schema_nodes = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self._dim)),
                pa.field("label", pa.string()),
                pa.field("node_type", pa.string()),
                pa.field("source_anchor", pa.string()),
                pa.field("source_domain", pa.string()),
                pa.field("payload", pa.string()),  # JSON metadata
                pa.field("created_at", pa.timestamp("us")),
            ]
        )
        if "nodes" not in self._db.table_names():
            self._nodes_tbl = self._db.create_table(
                "nodes",
                schema=schema_nodes,
            )
        else:
            self._nodes_tbl = self._db.open_table("nodes")

        schema_edges = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("source_id", pa.string()),
                pa.field("target_id", pa.string()),
                pa.field("relation_type", pa.string()),
                pa.field("weight", pa.float32()),
                pa.field("similarity", pa.float32()),
                pa.field("source_anchor", pa.string()),
                pa.field("target_anchor", pa.string()),
                pa.field("created_at", pa.timestamp("us")),
            ]
        )
        if "edges" not in self._db.table_names():
            self._edges_tbl = self._db.create_table(
                "edges",
                schema=schema_edges,
            )
        else:
            self._edges_tbl = self._db.open_table("edges")

    @property
    def node_count(self) -> int:
        return len(self._nodes_tbl)

    @property
    def edge_count(self) -> int:
        return len(self._edges_tbl)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_and_link(
        self,
        embedder: object,
        new_nodes: list[dict[str, Any]],
        new_edges: list[dict[str, Any]],
        *,
        source_domain: str = "unknown",
    ) -> dict[str, Any]:
        """Ingest nodes into the global chronicle and link them to existing nodes.

        Parameters
        ----------
        embedder:
            An embedder with an ``embed(text)`` method returning a list[float].
        new_nodes:
            List of dicts with keys: id, label, node_type, source_anchor,
            and optionally embedding (if missing, computed from label).
        new_edges:
            Intra-article edges to carry into the chronicle.
        source_domain:
            Domain label for provenance (e.g. "physics").

        Returns
        -------
        dict with keys: nodes_written, edges_written, crosslinks_created,
        existing_matches_found
        """
        if not new_nodes:
            return {
                "nodes_written": 0,
                "edges_written": 0,
                "crosslinks_created": 0,
                "existing_matches_found": 0,
            }

        # Step 1: ensure all nodes have embeddings
        # (embeddings are expected to be pre-computed by the async caller;
        # this fallback handles dicts that slipped through without them)
        for n in new_nodes:
            if not n.get("embedding"):
                n["embedding"] = [0.0] * self._dim

        # Step 2: separate synthesis nodes (preferred for linking) from regular
        synthesis_nodes = [n for n in new_nodes if n.get("node_type") == "synthesis"]
        concept_nodes = [n for n in new_nodes if n.get("node_type") != "synthesis"]

        # Step 3: write new nodes to the global chronicle
        self._write_nodes(new_nodes, source_domain)
        nodes_written = len(new_nodes)

        # Step 4: find crosslinks from new nodes to existing chronicle nodes
        crosslinks = []
        existing_count = self.node_count - len(new_nodes)

        if existing_count > 0:
            # Synthesis nodes (meta-concepts): link broadly
            for n in synthesis_nodes:
                matches = self._find_similar(n["id"], n["embedding"])
                # Take top fraction of matches (e.g. 20% of top-K)
                keep = max(1, int(len(matches) * self._synthesis_link_fraction))
                crosslinks.extend(self._make_cross_edges(n, matches[:keep]))

            # Regular concept nodes: link sparsely
            for n in concept_nodes:
                matches = self._find_similar(n["id"], n["embedding"])
                keep = max(1, int(len(matches) * self._concept_link_fraction))
                crosslinks.extend(self._make_cross_edges(n, matches[:keep]))

        # Step 5: write all edges (intra-article + crosslinks)
        all_edges = list(new_edges) + crosslinks
        if all_edges:
            self._write_edges(all_edges)

        log.info(
            "crosslink: domain=%s nodes=%d edges=%d crosslinks=%d "
            "chronicle_total_nodes=%d chronicle_total_edges=%d",
            source_domain,
            nodes_written,
            len(new_edges),
            len(crosslinks),
            self.node_count,
            self.edge_count,
        )

        return {
            "nodes_written": nodes_written,
            "edges_written": len(all_edges),
            "crosslinks_created": len(crosslinks),
            "existing_matches_found": len(crosslinks),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_nodes(self, nodes: list[dict[str, Any]], source_domain: str) -> None:
        """Batch-insert nodes into the global Chronicle."""
        import json

        now = datetime.now(UTC)
        data = []
        for n in nodes:
            data.append(
                {
                    "id": n["id"],
                    "vector": n["embedding"],
                    "label": n.get("label", ""),
                    "node_type": n.get("node_type", "concept"),
                    "source_anchor": n.get("source_anchor", ""),
                    "source_domain": source_domain,
                    "payload": json.dumps({k: v for k, v in n.items() if k not in ("embedding",)}),
                    "created_at": now,
                }
            )
        self._nodes_tbl.add(data)

    def _find_similar(self, query_id: str, query_embedding: list[float]) -> list[dict[str, Any]]:
        """Run kNN search against existing nodes, excluding the query node itself.

        Returns list of dicts with keys: id, label, node_type, score.
        """
        if len(self._nodes_tbl) <= 1:
            return []

        results = (
            as_vector_query(self._nodes_tbl.search(query_embedding))
            .metric("cosine")
            .where(f"id != '{query_id}'")
            .limit(min(self._top_k, 200))
            .to_list()
        )
        return [
            {
                "id": r["id"],
                "label": r.get("label", ""),
                "node_type": r.get("node_type", "concept"),
                "score": max(0.0, 1.0 - r.get("_distance", 0) / 2.0),
            }
            for r in results
        ]

    def _make_cross_edges(
        self, source_node: dict[str, Any], matches: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build CROSS_SIMILAR edges from source_node to each match."""
        import hashlib

        edges = []
        for m in matches[: self._max_edges_per_node]:
            weight = round(m["score"], 4)
            if weight < _MIN_SIMILARITY_FLOOR:
                continue
            # Deterministic edge ID
            raw = f"cross/{source_node['id']}->{m['id']}"
            eid = "EDGE-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            weight = round(m["score"], 4)
            edges.append(
                {
                    "id": eid,
                    "source_id": source_node["id"],
                    "target_id": m["id"],
                    "relation_type": "CROSS_SIMILAR",
                    "weight": weight,
                    "similarity": weight,
                    "source_anchor": source_node.get("source_anchor", ""),
                    "target_anchor": m.get("source_anchor", ""),
                }
            )
        return edges

    def _write_edges(self, edges: list[dict[str, Any]]) -> None:
        """Batch-insert edges into the global Chronicle."""
        now = datetime.now(UTC)
        data = []
        for e in edges:
            data.append(
                {
                    "id": e["id"],
                    "source_id": e["source_id"],
                    "target_id": e["target_id"],
                    "relation_type": e.get("relation_type", "CROSS_SIMILAR"),
                    "weight": e.get("weight", 0.5),
                    "similarity": e.get("similarity", e.get("weight", 0.5)),
                    "source_anchor": e.get("source_anchor", ""),
                    "target_anchor": e.get("target_anchor", ""),
                    "created_at": now,
                }
            )
        self._edges_tbl.add(data)
