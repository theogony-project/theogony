"""
Neo4jKnowledgeStore — production persistence backend (Plan §3.1a, §3.1).

Implements every method of the :class:`~theogony.core.store.KnowledgeStore`
Protocol against the official Neo4j Python driver's async API
(``neo4j.AsyncGraphDatabase``). The schema is the verbatim Plan §3.1a
DDL set (constraints + ten range indexes + one HNSW vector index)
shipped from :mod:`theogony.stores._schema`. Everything is idempotent
on connect.

Lifecycle
---------
The store is an async context manager. ``__aenter__`` opens the
driver, verifies connectivity, and runs the schema bootstrap;
``__aexit__`` closes the driver. Typical use::

    async with Neo4jKnowledgeStore(settings.neo4j, embedding_dim=384) as store:
        await store.upsert_node(node)

The IngestionPipeline takes a ``KnowledgeStore`` directly, so the
caller manages the context::

    async with Neo4jKnowledgeStore(...) as store:
        pipeline = IngestionPipeline(..., store=store)
        result = await pipeline.ingest(raw_content)

Property mapping
----------------
Pydantic ``KnowledgeNode`` and ``KnowledgeEdge`` are serialised onto
flat Neo4j properties per Plan §3.1a's tables:

- Scalar fields land on ``n.<field>`` directly.
- ``source_ref``, ``properties``, and (for nodes) the rest of
  ``external_ids`` go into JSON-serialised string columns
  (``source_ref_json``, ``properties_json``, ``external_ids_json``).
  Pydantic-discriminated-union round-trip is the reason for JSON.
- ``external_ids["wikidata"]`` is *also* flattened to a top-level
  indexed ``wikidata_id`` for cheap Detective lookup.
- ``scores`` (NodeScores) is flattened to confidence/relevance/
  connectivity/freshness, plus a denormalised ``vitality`` for cheap
  Oneiros queries.
- Datetimes are passed straight through; the driver handles the
  Python ↔ Neo4j temporal conversion.

Embedding-dim cross-check: every ``upsert_node`` whose
``node.embedding_dim`` is set verifies it equals the constructor's
``embedding_dim`` and raises :class:`ValueError` on mismatch — Plan
§3.1a "never silently truncate" rule.

What this module deliberately does NOT do
-----------------------------------------
- No APOC, no Bloom, no causal-cluster (out of E7 scope).
- No clustering Cypher beyond what the existing
  :meth:`assign_cluster` writes — Phoenix-tier cluster geometry
  belongs to Gen 2 (PHX-0011).
- No Phoenix bulk import / export over Cypher batches — the
  generator-style :meth:`import_nodes` is sufficient for Gen 1
  volumes (~2 000 nodes per book).
"""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from theogony.config.logging import get_logger
from theogony.config.settings import Neo4jSettings
from theogony.core.model import (
    ClusterSummary,
    Constellation,
    ConstellationEdge,
    ConstellationNode,
    EdgeType,
    EpistemicStatus,
    KnowledgeEdge,
    KnowledgeForm,
    KnowledgeNode,
    Layer,
    NodeScores,
    NodeType,
    ScoreUpdate,
    SourceRef,
)
from theogony.core.store import Path, ScoredNode
from theogony.stores._schema import all_schema_statements

if TYPE_CHECKING:
    from neo4j import AsyncDriver

log = get_logger("stores.neo4j")


def _cypher_effective_weight(rel: str) -> str:
    """Cypher expression for pheromone-mode-aware traversal weight (W2)."""
    d = f"coalesce({rel}.pheromone_delta, 0.0)"
    w = f"{rel}.weight"
    return (
        f"CASE coalesce($pheromone_mode, 'follow') "
        f"WHEN 'ignore' THEN {w} "
        f"WHEN 'invert' THEN CASE WHEN {w} - {d} < 0.0 THEN 0.0 "
        f"WHEN {w} - {d} > 1.0 THEN 1.0 ELSE {w} - {d} END "
        f"ELSE CASE WHEN {w} + {d} < 0.0 THEN 0.0 WHEN {w} + {d} > 1.0 THEN 1.0 "
        f"ELSE {w} + {d} END END"
    )


# ---------------------------------------------------------------------------
# Property serialisation helpers
# ---------------------------------------------------------------------------


def _node_to_props(node: KnowledgeNode, embedding_dim: int) -> dict[str, Any]:
    """Serialise a KnowledgeNode into a flat Cypher-ready properties dict.

    Mirrors Plan §3.1a's :KnowledgeNode property table exactly: scalar
    fields land verbatim; JSON columns hold the round-trippable rest.
    Returns a dict suitable for ``SET n += $props`` after id is set
    by the MERGE.

    Embedding-dim cross-check happens here so an upsert never reaches
    the wire with a malformed vector.
    """
    if node.embedding_dim is not None and node.embedding_dim != embedding_dim:
        raise ValueError(
            f"node {node.id} declares embedding_dim={node.embedding_dim} "
            f"but the store's vector index is dim={embedding_dim} — refusing "
            "silent coercion (Plan §3.1a)"
        )
    if node.embedding and len(node.embedding) != embedding_dim:
        raise ValueError(
            f"node {node.id} carries an embedding of length {len(node.embedding)} "
            f"but the store's vector index is dim={embedding_dim}"
        )

    rest_external = {k: v for k, v in node.external_ids.items() if k != "wikidata"}
    return {
        "label": node.label,
        "description": node.description,
        "node_type": node.node_type.value,
        "knowledge_form": node.knowledge_form.value,
        "epistemic_status": node.epistemic_status.value,
        "layer": node.layer.value,
        "cluster_id": node.cluster_id,
        "cluster_label": node.cluster_label,
        "depth_band": node.depth_band,
        "source_identifier": node.source_ref.identifier or None,
        # ``embedding`` is the only list-of-float we set; Neo4j stores it
        # as a list and the HNSW index reads it directly.
        "embedding": list(node.embedding) if node.embedding else None,
        "embedding_model_id": node.embedding_model_id,
        "embedding_dim": node.embedding_dim,
        "wikidata_id": node.external_ids.get("wikidata"),
        "external_ids_json": json.dumps(rest_external, sort_keys=True),
        "source_ref_json": node.source_ref.model_dump_json(),
        "confidence": node.scores.confidence,
        "relevance": node.scores.relevance,
        "connectivity": node.scores.connectivity,
        "freshness": node.scores.freshness,
        "vitality": node.scores.vitality(),
        "properties_json": json.dumps(node.properties, sort_keys=True, default=str),
        "created_at": node.created_at,
        "last_accessed": node.last_accessed,
        "last_verified": node.last_verified,
        "resolution_tier": node.resolution_tier,
        "manual_resolution_needed": node.manual_resolution_needed,
    }


def _edge_to_props(edge: KnowledgeEdge) -> dict[str, Any]:
    """Serialise a KnowledgeEdge into a Cypher-ready properties dict (Plan §3.1a)."""
    source_ref_json = edge.source_ref.model_dump_json() if edge.source_ref is not None else None
    return {
        "relation_type": edge.relation_type,
        "weight": edge.weight,
        "pheromone_delta": edge.pheromone_delta,
        "last_traversed": edge.last_traversed,
        "confidence": edge.confidence,
        "bidirectional": edge.bidirectional,
        "epistemic_type": edge.epistemic_type.value,
        "evidence_span": edge.evidence_span,
        "source_ref_json": source_ref_json,
        "properties_json": json.dumps(edge.properties, sort_keys=True, default=str),
        "created_at": edge.created_at,
    }


def _node_from_record(props: Mapping[str, Any]) -> KnowledgeNode:
    """Inverse of :func:`_node_to_props`. Defensive on missing fields."""
    raw_external = props.get("external_ids_json") or "{}"
    external_ids: dict[str, str] = json.loads(raw_external) if raw_external else {}
    if props.get("wikidata_id"):
        external_ids["wikidata"] = props["wikidata_id"]
    raw_source = props.get("source_ref_json")
    source_ref = (
        SourceRef.model_validate_json(raw_source)
        if raw_source
        else SourceRef(source_type="unknown")
    )
    raw_props = props.get("properties_json") or "{}"
    properties: dict[str, Any] = json.loads(raw_props) if raw_props else {}
    scores = NodeScores(
        confidence=float(props.get("confidence", 0.5)),
        relevance=float(props.get("relevance", 0.5)),
        connectivity=float(props.get("connectivity", 0.0)),
        freshness=float(props.get("freshness", 1.0)),
    )
    embedding = list(props.get("embedding") or [])
    return KnowledgeNode(
        id=props["id"],
        embedding=embedding,
        embedding_model_id=props.get("embedding_model_id"),
        embedding_dim=props.get("embedding_dim"),
        node_type=NodeType(props.get("node_type", NodeType.OTHER.value)),
        knowledge_form=KnowledgeForm(
            props.get("knowledge_form", KnowledgeForm.CHRONOLOGICAL.value)
        ),
        epistemic_status=EpistemicStatus(
            props.get("epistemic_status", EpistemicStatus.OBSERVED.value)
        ),
        label=props["label"],
        description=props.get("description"),
        layer=Layer(props.get("layer", Layer.EPHEMERA.value)),
        cluster_id=props.get("cluster_id"),
        cluster_label=props.get("cluster_label"),
        depth_band=int(props.get("depth_band", 0)),
        external_ids=external_ids,
        source_ref=source_ref,
        scores=scores,
        properties=properties,
        manual_resolution_needed=bool(props.get("manual_resolution_needed", False)),
        resolution_tier=props.get("resolution_tier"),
        created_at=_to_datetime(props.get("created_at")),
        last_accessed=_to_datetime(props.get("last_accessed")),
        last_verified=_optional_datetime(props.get("last_verified")),
    )


def _edge_from_record(
    props: Mapping[str, Any],
    source_id: str,
    target_id: str,
) -> KnowledgeEdge:
    """Inverse of :func:`_edge_to_props`. ``source_id`` / ``target_id``
    come from the Cypher record (Neo4j's relationship object exposes
    them via the start/end node)."""
    raw_source = props.get("source_ref_json")
    source_ref = SourceRef.model_validate_json(raw_source) if raw_source else None
    raw_props = props.get("properties_json") or "{}"
    properties: dict[str, Any] = json.loads(raw_props) if raw_props else {}
    return KnowledgeEdge(
        id=props["id"],
        source_id=source_id,
        target_id=target_id,
        relation_type=props["relation_type"],
        weight=float(props.get("weight", 0.5)),
        pheromone_delta=float(props.get("pheromone_delta", 0.0)),
        last_traversed=_optional_datetime(props.get("last_traversed")),
        confidence=float(props.get("confidence", 0.5)),
        bidirectional=bool(props.get("bidirectional", False)),
        epistemic_type=EdgeType(props.get("epistemic_type", EdgeType.EXTRACTION.value)),
        source_ref=source_ref,
        evidence_span=props.get("evidence_span"),
        properties=properties,
        created_at=_to_datetime(props.get("created_at")),
    )


def _to_datetime(value: Any) -> datetime:
    """Coerce a Neo4j temporal (or already-Python datetime) to ``datetime``.

    The driver returns ``neo4j.time.DateTime`` for stored DATETIME values;
    that type has a ``to_native()`` method that returns ``datetime.datetime``.
    Tests sometimes pass through plain Python datetimes already.
    """
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        result = to_native()
        if isinstance(result, datetime):
            return result
    raise TypeError(f"cannot coerce {type(value).__name__} to datetime: {value!r}")


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return _to_datetime(value)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_int(name: str, value: int, *, minimum: int = 0) -> int:
    """Validate an integer arg used to template into Cypher.

    Path-length bounds (``*1..N``) and ``LIMIT N`` cannot be Cypher
    parameters in standard Neo4j 5.x; we f-string-interpolate them
    after a positive-int validation. This guards against the obvious
    misuse + makes the safety boundary explicit at every call site.
    """
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an int >= {minimum}; got {value!r}")
    return value


# ---------------------------------------------------------------------------
# Neo4jKnowledgeStore
# ---------------------------------------------------------------------------


class Neo4jKnowledgeStore:
    """Production :class:`~theogony.core.store.KnowledgeStore` against Neo4j 5.x."""

    def __init__(self, settings: Neo4jSettings, *, embedding_dim: int) -> None:
        if embedding_dim <= 0:
            raise ValueError(f"embedding_dim must be positive; got {embedding_dim}")
        self._settings = settings
        self._embedding_dim = embedding_dim
        self._driver: AsyncDriver | None = None

    # ----- lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> Neo4jKnowledgeStore:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open the driver, verify connectivity, run the schema bootstrap.

        Verifies connectivity on first use to fail fast on a wrong URI
        or password rather than at the first query.
        """
        from neo4j import AsyncGraphDatabase

        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            self._settings.uri,
            auth=(self._settings.user, self._settings.password.get_secret_value()),
        )
        await self._driver.verify_connectivity()
        await self._ensure_schema()
        log.info(
            "neo4j connected uri=%s database=%s embedding_dim=%d",
            self._settings.uri,
            self._settings.database,
            self._embedding_dim,
        )

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    # ----- schema ------------------------------------------------------------

    async def _ensure_schema(self) -> None:
        """Run every Plan §3.1a DDL statement on connect.

        All statements are idempotent (``IF NOT EXISTS``); reconnecting
        against an existing database produces no errors and no schema
        churn.
        """
        async with self._session() as session:
            for stmt in all_schema_statements(self._embedding_dim):
                await session.run(stmt)

    # ----- session helper ----------------------------------------------------

    def _session(self) -> Any:
        """Return an AsyncSession bound to the configured database.

        The store is a thin wrapper around the driver — every method
        opens its own session via ``async with self._session() as session``.
        Session lifetime is per-operation so connection-pool churn stays
        local to one Cypher round-trip.
        """
        if self._driver is None:
            raise RuntimeError(
                "Neo4jKnowledgeStore not connected. Use as async context "
                "manager or call .connect() first."
            )
        return self._driver.session(database=self._settings.database)

    # ----- vector search -----------------------------------------------------

    async def vector_search(
        self,
        embedding: list[float],
        k: int = 20,
        layer: Layer | None = None,
        node_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> list[ScoredNode]:
        """HNSW vector search via ``db.index.vector.queryNodes``.

        Filters (layer, node_types, min_confidence) are applied in
        Cypher's WHERE clause after the index returns its top-k. The
        Plan §3.1a range indexes on ``layer`` and ``node_type`` make
        this filter cheap.
        """
        _validate_int("k", k, minimum=1)
        if not embedding:
            return []
        # Over-fetch so post-index filters don't truncate too aggressively.
        # 4× headroom is plenty for the small filter cardinalities we see
        # (layer + node_type + confidence) without straining the index.
        fetch_k = k * 4
        cypher = """
        CALL db.index.vector.queryNodes(
          'knowledge_node_embedding', $fetch_k, $embedding
        ) YIELD node, score
        WHERE ($layer IS NULL OR node.layer = $layer)
          AND ($node_types IS NULL OR node.node_type IN $node_types)
          AND ($min_confidence IS NULL OR node.confidence >= $min_confidence)
        RETURN node{.*, id: node.id} AS node, score
        ORDER BY score DESC
        LIMIT $k
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                embedding=list(embedding),
                fetch_k=fetch_k,
                k=k,
                layer=layer.value if layer is not None else None,
                node_types=list(node_types) if node_types is not None else None,
                min_confidence=min_confidence,
            )
            records = await result.data()
        out: list[ScoredNode] = []
        for rec in records:
            # Neo4j vector index scores are cosine-like, but floating point
            # drift can produce tiny overshoots (e.g. 1.0000001) that violate
            # the ScoredNode schema bound [−1, 1].
            raw_score = float(rec["score"])
            clamped_score = max(-1.0, min(1.0, raw_score))
            out.append(ScoredNode(node=_node_from_record(rec["node"]), score=clamped_score))
        return out

    # ----- traverse ----------------------------------------------------------

    async def traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        min_weight: float = 0.3,
        relation_types: list[str] | None = None,
        *,
        pheromone_mode: str = "follow",
    ) -> list[Path]:
        """Variable-length BFS-equivalent path query (Plan §2.6 / §3.1)."""
        _validate_int("max_depth", max_depth, minimum=1)
        ew = _cypher_effective_weight("rel")
        # Path-length bounds cannot be Cypher parameters; safe f-string
        # because max_depth is a validated int.
        cypher = f"""
        MATCH (start:KnowledgeNode {{id: $start_id}})
        MATCH path = (start)-[r:RELATION*1..{max_depth}]->(end:KnowledgeNode)
        WHERE all(rel IN r WHERE ({ew}) >= $min_weight)
          AND ($relation_types IS NULL OR all(
                rel IN r WHERE rel.relation_type IN $relation_types
          ))
        RETURN [n IN nodes(path) | n{{.*, id: n.id}}] AS path_nodes,
               [rel IN r | {{
                  rel: rel{{.*, id: rel.id}},
                  source_id: startNode(rel).id,
                  target_id: endNode(rel).id
               }}] AS path_edges,
               reduce(w = 1.0, rel IN r | w * ({ew})) AS total_weight
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                start_id=start_id,
                min_weight=min_weight,
                relation_types=list(relation_types) if relation_types is not None else None,
                pheromone_mode=pheromone_mode,
            )
            records = await result.data()
        paths: list[Path] = []
        for rec in records:
            nodes = [_node_from_record(p) for p in rec["path_nodes"]]
            edges = [
                _edge_from_record(item["rel"], item["source_id"], item["target_id"])
                for item in rec["path_edges"]
            ]
            paths.append(Path(nodes=nodes, edges=edges, total_weight=float(rec["total_weight"])))
        return paths

    # ----- multi-hop search --------------------------------------------------

    async def multi_hop_search(
        self,
        embedding: list[float],
        k: int = 20,
        hops: int = 3,
        min_weight: float = 0.3,
        layer: Layer | None = None,
        *,
        pheromone_mode: str = "follow",
    ) -> list[ScoredNode]:
        """Vector seed + graph expansion, deduplicated (matches InMemory)."""
        _validate_int("k", k, minimum=1)
        _validate_int("hops", hops, minimum=1)
        seeds = await self.vector_search(embedding, k=k, layer=layer)
        scored: dict[str, tuple[float, KnowledgeNode]] = {
            sn.node.id: (sn.score, sn.node) for sn in seeds
        }
        for seed in seeds:
            paths = await self.traverse(
                seed.node.id,
                max_depth=hops,
                min_weight=min_weight,
                pheromone_mode=pheromone_mode,
            )
            for path in paths:
                if not path.nodes:
                    continue
                last = path.nodes[-1]
                if layer is not None and last.layer != layer:
                    continue
                discounted = seed.score * path.total_weight
                existing = scored.get(last.id)
                if existing is None or existing[0] < discounted:
                    scored[last.id] = (discounted, last)
        ranked = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)
        return [ScoredNode(node=item[1], score=item[0]) for _, item in ranked[:k]]

    # ----- node CRUD ---------------------------------------------------------

    async def upsert_node(self, node: KnowledgeNode) -> str:
        props = _node_to_props(node, self._embedding_dim)
        cypher = """
        MERGE (n:KnowledgeNode {id: $id})
        SET n += $props
        RETURN n.id AS id
        """
        async with self._session() as session:
            result = await session.run(cypher, id=node.id, props=props)
            record = await result.single()
        return str(record["id"]) if record is not None else node.id

    async def upsert_edge(self, edge: KnowledgeEdge) -> None:
        props = _edge_to_props(edge)
        cypher = """
        MATCH (s:KnowledgeNode {id: $source_id})
        MATCH (t:KnowledgeNode {id: $target_id})
        MERGE (s)-[r:RELATION {id: $id}]->(t)
        SET r += $props
        """
        async with self._session() as session:
            await session.run(
                cypher,
                source_id=edge.source_id,
                target_id=edge.target_id,
                id=edge.id,
                props=props,
            )

    async def batch_upsert_nodes(self, nodes: Sequence[KnowledgeNode]) -> list[str]:
        """One Bolt round-trip per batch via Cypher UNWIND + MERGE.

        PHX-0046: replaces N round-trips for an N-node batch with a
        single ``UNWIND $rows AS row MERGE … SET n += row.props``
        round-trip. The rows preserve input order; ``RETURN row.id``
        propagates that order back so the IngestionPipeline can
        cross-reference returned ids against its in-memory node list.

        Embedding-dim cross-check applied per row before the Cypher
        runs: any node whose embedding length disagrees with the
        store's configured dim raises ``ValueError`` immediately
        (Plan §3.1a "never silently truncate"). Same contract as
        single ``upsert_node``; the batch path inherits the discipline
        rather than degrading it.
        """
        if not nodes:
            return []
        rows = [{"id": n.id, "props": _node_to_props(n, self._embedding_dim)} for n in nodes]
        cypher = """
        UNWIND $rows AS row
        MERGE (n:KnowledgeNode {id: row.id})
        SET n += row.props
        RETURN row.id AS id
        """
        async with self._session() as session:
            result = await session.run(cypher, rows=rows)
            records = await result.data()
        return [str(rec["id"]) for rec in records]

    async def batch_upsert_edges(self, edges: Sequence[KnowledgeEdge]) -> None:
        """One Bolt round-trip per batch via Cypher UNWIND + MERGE.

        PHX-0046: same shape as ``batch_upsert_nodes``. Endpoint
        nodes must already exist (caller's responsibility, matching
        ``upsert_edge``); this method does NOT MERGE-create the
        endpoints, it only attaches the relation.
        """
        if not edges:
            return
        rows = [
            {
                "id": e.id,
                "source_id": e.source_id,
                "target_id": e.target_id,
                "props": _edge_to_props(e),
            }
            for e in edges
        ]
        cypher = """
        UNWIND $rows AS row
        MATCH (s:KnowledgeNode {id: row.source_id})
        MATCH (t:KnowledgeNode {id: row.target_id})
        MERGE (s)-[r:RELATION {id: row.id}]->(t)
        SET r += row.props
        """
        async with self._session() as session:
            await session.run(cypher, rows=rows)

    async def get_node(self, node_id: str) -> KnowledgeNode | None:
        cypher = """
        MATCH (n:KnowledgeNode {id: $node_id})
        RETURN n{.*, id: n.id} AS node
        LIMIT 1
        """
        async with self._session() as session:
            result = await session.run(cypher, node_id=node_id)
            record = await result.single()
        if record is None:
            return None
        return _node_from_record(record["node"])

    async def get_edges_among(
        self,
        node_ids: Sequence[str],
        min_weight: float = 0.0,
    ) -> list[KnowledgeEdge]:
        # PHX-0050: one Cypher round-trip replaces N depth-1
        # get_neighborhood probes from the assembler hot loop. Both
        # endpoint matches are served by the
        # ``knowledge_node_id_unique`` constraint-backed range index
        # (Plan §3.1a); the WHERE-IN-list expands per-row but the
        # range-index seek per id is constant-time. Source/target
        # ids are projected explicitly so the assembler's edge
        # reconstruction does not depend on driver-side
        # ``rel.start_node`` / ``rel.end_node`` quirks (those are
        # the same caveat get_neighborhood already documented).
        if not node_ids:
            return []
        cypher = """
        MATCH (a:KnowledgeNode)-[r:RELATION]->(b:KnowledgeNode)
        WHERE a.id IN $ids AND b.id IN $ids AND r.weight >= $min_weight
        RETURN r{.*, id: r.id} AS rel,
               a.id AS source_id,
               b.id AS target_id
        """
        async with self._session() as session:
            result = await session.run(cypher, ids=list(node_ids), min_weight=min_weight)
            records = await result.data()
        return [
            _edge_from_record(rec["rel"], rec["source_id"], rec["target_id"]) for rec in records
        ]

    async def get_neighborhood(
        self,
        node_id: str,
        depth: int = 2,
        min_weight: float = 0.3,
        *,
        pheromone_mode: str = "follow",
    ) -> Constellation:
        """Bidirectional BFS via undirected variable-length match.

        Returns a Constellation with slim DTOs (Plan §9.1) — embeddings
        stay out of the synthesizer's context. Empty when ``node_id``
        is unknown; otherwise always includes the start node.
        """
        _validate_int("depth", depth, minimum=1)
        # Empty-state fast path keeps Cypher simple.
        start = await self.get_node(node_id)
        if start is None:
            return Constellation(query=f"node:{node_id}")
        # Undirected variable-length match collects both incoming and
        # outgoing edges within `depth` hops. We project source/target
        # IDs via Cypher rather than relying on driver-side
        # ``rel.start_node`` (variable-length matches do not always
        # populate start/end nodes on the returned Relationship
        # objects in async neo4j-driver 6.x). Each per-path relationship
        # list yields a list of {rel, source_id, target_id} dicts; we
        # then flatten + dedupe in Python.
        ew = _cypher_effective_weight("rel")
        cypher = f"""
        MATCH (start:KnowledgeNode {{id: $node_id}})
        OPTIONAL MATCH (start)-[r:RELATION*1..{depth}]-(other:KnowledgeNode)
        WHERE r IS NULL OR all(rel IN r WHERE ({ew}) >= $min_weight)
        WITH start,
             collect(DISTINCT other) AS others,
             collect(
               [rel IN r | {{
                  rel: rel{{.*, id: rel.id}},
                  source_id: startNode(rel).id,
                  target_id: endNode(rel).id
               }}]
             ) AS rel_lists
        RETURN start{{.*, id: start.id}} AS start,
               [n IN others WHERE n IS NOT NULL | n{{.*, id: n.id}}] AS others,
               rel_lists
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                node_id=node_id,
                min_weight=min_weight,
                pheromone_mode=pheromone_mode,
            )
            record = await result.single()
        if record is None:
            return Constellation(
                query=f"node:{node_id}",
                nodes=[ConstellationNode.from_knowledge_node(start)],
                suggested_sources=[start.source_ref],
            )
        # Flatten the list-of-list-of-relationship-projections and dedupe by id.
        nodes_raw: list[Mapping[str, Any]] = [record["start"], *record["others"]]
        seen_node_ids: set[str] = set()
        constellation_nodes: list[ConstellationNode] = []
        suggested: list[SourceRef] = []
        for raw in nodes_raw:
            node = _node_from_record(raw)
            if node.id in seen_node_ids:
                continue
            seen_node_ids.add(node.id)
            constellation_nodes.append(ConstellationNode.from_knowledge_node(node))
            suggested.append(node.source_ref)
        seen_edge_ids: set[str] = set()
        constellation_edges: list[ConstellationEdge] = []
        for rel_list in record["rel_lists"] or ():
            if not rel_list:
                continue
            for projection in rel_list:
                if projection is None:
                    continue
                rel_props = projection["rel"]
                if rel_props["id"] in seen_edge_ids:
                    continue
                seen_edge_ids.add(rel_props["id"])
                edge = _edge_from_record(
                    rel_props,
                    projection["source_id"],
                    projection["target_id"],
                )
                constellation_edges.append(ConstellationEdge.from_knowledge_edge(edge))
        return Constellation(
            query=f"node:{node_id}",
            nodes=constellation_nodes,
            edges=constellation_edges,
            suggested_sources=suggested,
        )

    async def delete_node(self, node_id: str) -> None:
        cypher = """
        MATCH (n:KnowledgeNode {id: $node_id})
        DETACH DELETE n
        """
        async with self._session() as session:
            await session.run(cypher, node_id=node_id)

    # ----- lifecycle ---------------------------------------------------------

    async def promote(self, node_id: str) -> None:
        await self._set_layer(node_id, Layer.MNEME)

    async def degrade(self, node_id: str) -> None:
        await self._set_layer(node_id, Layer.EPHEMERA)

    async def _set_layer(self, node_id: str, layer: Layer) -> None:
        cypher = """
        MATCH (n:KnowledgeNode {id: $node_id})
        SET n.layer = $layer
        """
        async with self._session() as session:
            await session.run(cypher, node_id=node_id, layer=layer.value)

    async def update_scores(self, node_id: str, scores: dict[str, float]) -> None:
        # Keep the denormalised vitality in sync when the underlying
        # NodeScores fields change (Plan §3.1a denormalisation).
        # Read the existing scores first so we apply the partial update
        # over the current state.
        existing = await self.get_node(node_id)
        if existing is None:
            return
        merged = NodeScores(
            confidence=scores.get("confidence", existing.scores.confidence),
            relevance=scores.get("relevance", existing.scores.relevance),
            connectivity=scores.get("connectivity", existing.scores.connectivity),
            freshness=scores.get("freshness", existing.scores.freshness),
        )
        cypher = """
        MATCH (n:KnowledgeNode {id: $node_id})
        SET n.confidence  = $confidence,
            n.relevance   = $relevance,
            n.connectivity = $connectivity,
            n.freshness   = $freshness,
            n.vitality    = $vitality
        """
        async with self._session() as session:
            await session.run(
                cypher,
                node_id=node_id,
                confidence=merged.confidence,
                relevance=merged.relevance,
                connectivity=merged.connectivity,
                freshness=merged.freshness,
                vitality=merged.vitality(),
            )

    async def batch_update_scores(self, updates: Sequence[ScoreUpdate]) -> None:
        # PHX-0048 (reopened by E8.5): one Bolt round-trip via Cypher
        # ``UNWIND $rows AS r MATCH … SET … = COALESCE(...)``. Each
        # row writes only non-NULL fields; the COALESCE preserves the
        # existing value when the caller passed None. The Plan §3.1a
        # ``knowledge_node_id_unique`` constraint-backed range index
        # serves the per-row MATCH (one db-hit per row).
        #
        # Empty input → no round-trip (matches the
        # :meth:`batch_upsert_*` PHX-0046 contract).
        # Missing node ids → silent no-op (the MATCH returns nothing
        # for that row, the SET applies to nothing).
        if not updates:
            return
        rows = [
            {
                "node_id": upd.node_id,
                "confidence": upd.confidence,
                "relevance": upd.relevance,
                "connectivity": upd.connectivity,
                "freshness": upd.freshness,
                "vitality": upd.vitality,
            }
            for upd in updates
        ]
        cypher = """
        UNWIND $rows AS r
        MATCH (n:KnowledgeNode {id: r.node_id})
        SET n.confidence   = COALESCE(r.confidence,   n.confidence),
            n.relevance    = COALESCE(r.relevance,    n.relevance),
            n.connectivity = COALESCE(r.connectivity, n.connectivity),
            n.freshness    = COALESCE(r.freshness,    n.freshness),
            n.vitality     = COALESCE(r.vitality,     n.vitality)
        """
        async with self._session() as session:
            await session.run(cypher, rows=rows)

    async def mark_self_referential(self, node_ids: Sequence[str], run_id: str) -> None:
        if not node_ids:
            return
        ids = list(node_ids)
        read_cypher = """
        UNWIND $ids AS nid
        MATCH (n:KnowledgeNode {id: nid})
        RETURN n.id AS id, n.properties_json AS properties_json
        """
        async with self._session() as session:
            result = await session.run(read_cypher, ids=ids)
            rows = await result.data()
        updates: list[dict[str, str]] = []
        for rec in rows:
            nid = str(rec["id"])
            raw = rec.get("properties_json") or "{}"
            try:
                props: dict[str, object] = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                props = {}
            prev = list(props.get("self_referential_in_runs") or [])
            if run_id not in prev:
                prev.append(run_id)
            props["self_referential_in_runs"] = prev
            updates.append(
                {
                    "id": nid,
                    "properties_json": json.dumps(props, sort_keys=True, default=str),
                }
            )
        if not updates:
            return
        write_cypher = """
        UNWIND $rows AS row
        MATCH (n:KnowledgeNode {id: row.id})
        SET n.properties_json = row.properties_json
        """
        async with self._session() as session:
            await session.run(write_cypher, rows=updates)

    async def count_neighbors_in_layer(self, layer: Layer) -> dict[str, int]:
        # Plan §5 E8.5 step 2: bulk degree map for one layer in one
        # Bolt round-trip. ``OPTIONAL MATCH`` keeps isolated nodes
        # (degree 0) in the result; the undirected ``-[r:RELATION]-``
        # makes the count symmetric (in + out edges).
        # PROFILE on the 2000-node demo target (PHX-0042 audit
        # methodology) keeps db-hits ≤ 200 per the Plan §5 E8.5
        # Risks bullet on dense graphs.
        cypher = """
        MATCH (n:KnowledgeNode {layer: $layer})
        OPTIONAL MATCH (n)-[r:RELATION]-()
        RETURN n.id AS id, count(r) AS degree
        """
        async with self._session() as session:
            result = await session.run(cypher, layer=layer.value)
            records = await result.data()
        return {str(rec["id"]): int(rec["degree"]) for rec in records}

    async def list_low_connectivity_nodes(
        self,
        *,
        layer: Layer,
        max_edges: int,
        batch_size: int,
    ) -> list[KnowledgeNode]:
        _validate_int("max_edges", max_edges, minimum=0)
        _validate_int("batch_size", batch_size, minimum=1)
        cypher = """
        MATCH (n:KnowledgeNode {layer: $layer})
        OPTIONAL MATCH (n)-[r:RELATION]-()
        WITH n, count(r) AS deg
        WHERE deg < $max_edges
        RETURN n{.*, id: n.id} AS node
        ORDER BY n.created_at ASC
        LIMIT $batch_size
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                layer=layer.value,
                max_edges=max_edges,
                batch_size=batch_size,
            )
            records = await result.data()
        return [_node_from_record(rec["node"]) for rec in records]

    async def find_similar_nodes_in_band(
        self,
        embedding: list[float],
        *,
        band_low: float,
        band_high: float,
        exclude_ids: set[str],
        top_k: int,
        layer: Layer | None = None,
    ) -> list[ScoredNode]:
        _validate_int("top_k", top_k, minimum=1)
        if not embedding:
            return []
        fetch_k = max(top_k * 25, 200)
        cypher = """
        CALL db.index.vector.queryNodes(
          'knowledge_node_embedding', $fetch_k, $embedding
        ) YIELD node, score
        WHERE score >= $band_low AND score <= $band_high
          AND NOT node.id IN $exclude_list
          AND ($layer IS NULL OR node.layer = $layer)
        RETURN node{.*, id: node.id} AS node, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                embedding=list(embedding),
                fetch_k=fetch_k,
                band_low=band_low,
                band_high=band_high,
                exclude_list=list(exclude_ids),
                top_k=top_k,
                layer=layer.value if layer is not None else None,
            )
            records = await result.data()
        return [
            ScoredNode(node=_node_from_record(rec["node"]), score=float(rec["score"]))
            for rec in records
        ]

    async def update_depth_band(
        self,
        node_id: str,
        depth_band: int,
        *,
        layer: Layer | None = None,
    ) -> None:
        if layer is None:
            cypher = """
            MATCH (n:KnowledgeNode {id: $node_id})
            SET n.depth_band = $depth_band
            """
            params: dict[str, Any] = {"node_id": node_id, "depth_band": depth_band}
        else:
            cypher = """
            MATCH (n:KnowledgeNode {id: $node_id})
            SET n.depth_band = $depth_band,
                n.layer = $layer
            """
            params = {
                "node_id": node_id,
                "depth_band": depth_band,
                "layer": layer.value,
            }
        async with self._session() as session:
            await session.run(cypher, **params)

    async def list_nodes_by_source_identifier(
        self,
        *,
        identifier: str,
        exclude_id: str | None = None,
    ) -> list[KnowledgeNode]:
        if not identifier:
            return []
        cypher = """
        MATCH (n:KnowledgeNode)
        WHERE n.source_identifier = $identifier
          AND ($exclude_id IS NULL OR n.id <> $exclude_id)
        RETURN n{.*, id: n.id} AS node
        """
        async with self._session() as session:
            result = await session.run(cypher, identifier=identifier, exclude_id=exclude_id)
            records = await result.data()
        return [_node_from_record(rec["node"]) for rec in records]

    # ----- clusters ----------------------------------------------------------

    async def get_cluster_centroid(self, cluster_id: str) -> list[float]:
        """Mean of cluster member embeddings.

        Cypher's reducer cannot do per-dimension averaging on
        list properties; we collect the embeddings client-side and
        compute the mean in Python. Cluster cardinality at Gen 1
        scale is a few hundred at most.
        """
        cypher = """
        MATCH (n:KnowledgeNode {cluster_id: $cluster_id})
        WHERE n.embedding IS NOT NULL AND size(n.embedding) > 0
        RETURN n.embedding AS embedding
        """
        async with self._session() as session:
            result = await session.run(cypher, cluster_id=cluster_id)
            records = await result.data()
        embeddings = [list(rec["embedding"]) for rec in records]
        if not embeddings:
            return []
        dim = len(embeddings[0])
        if any(len(e) != dim for e in embeddings):
            return []
        n = len(embeddings)
        return [sum(e[i] for e in embeddings) / n for i in range(dim)]

    async def assign_cluster(
        self,
        node_id: str,
        cluster_id: str | None,
        *,
        cluster_label: str | None = None,
    ) -> None:
        cypher = """
        MATCH (n:KnowledgeNode {id: $node_id})
        SET n.cluster_id = $cluster_id,
            n.cluster_label = $cluster_label
        """
        async with self._session() as session:
            await session.run(
                cypher,
                node_id=node_id,
                cluster_id=cluster_id,
                cluster_label=cluster_label,
            )

    async def list_clusters(self) -> list[ClusterSummary]:
        cypher = """
        MATCH (n:KnowledgeNode)
        WHERE n.cluster_id IS NOT NULL
          AND n.embedding IS NOT NULL
          AND size(n.embedding) > 0
        WITH n.cluster_id AS cid,
             collect(DISTINCT n.cluster_label) AS labels,
             collect(n.embedding) AS embeddings,
             collect(n.node_type) AS node_types,
             collect(n.source_ref_json) AS source_jsons
        RETURN cid,
               labels,
               size(embeddings) AS member_count,
               embeddings,
               node_types,
               source_jsons
        """
        async with self._session() as session:
            result = await session.run(cypher)
            records = await result.data()
        summaries: list[ClusterSummary] = []
        for rec in records:
            cid = str(rec["cid"])
            embeddings_raw = [list(e) for e in (rec.get("embeddings") or []) if e]
            embeddings_raw = [e for e in embeddings_raw if e]
            centroid: list[float] = []
            if embeddings_raw:
                dim = len(embeddings_raw[0])
                if all(len(e) == dim for e in embeddings_raw):
                    nemb = len(embeddings_raw)
                    centroid = [sum(e[i] for e in embeddings_raw) / nemb for i in range(dim)]
                    norm = math.sqrt(sum(x * x for x in centroid))
                    if norm > 0.0:
                        centroid = [x / norm for x in centroid]
            types: list[NodeType] = []
            for nt in rec.get("node_types") or []:
                if nt:
                    types.append(NodeType(str(nt)))
            dom_type: NodeType | None = None
            if types:
                dom_type = max(set(types), key=lambda t: sum(1 for x in types if x == t))
            sources: list[str] = []
            for sj in rec.get("source_jsons") or []:
                if sj:
                    sr = SourceRef.model_validate_json(str(sj))
                    sources.append(sr.source_type)
            dom_src: str | None = None
            if sources:
                dom_src = max(set(sources), key=lambda s: sum(1 for x in sources if x == s))
            raw_labels = rec.get("labels") or []
            clabel = next((x for x in raw_labels if x is not None), None)
            if clabel is not None and not isinstance(clabel, str):
                clabel = str(clabel)
            summaries.append(
                ClusterSummary(
                    cluster_id=cid,
                    cluster_label=clabel,
                    member_count=int(rec["member_count"]),
                    centroid=centroid,
                    dominant_node_type=dom_type,
                    dominant_source_type=dom_src,
                    properties={},
                )
            )
        summaries.sort(key=lambda s: s.cluster_id)
        return summaries

    async def get_cluster_members(self, cluster_id: str) -> AsyncIterator[str]:
        cypher = """
        MATCH (n:KnowledgeNode {cluster_id: $cluster_id})
        RETURN n.id AS id
        """
        async with self._session() as session:
            result = await session.run(cypher, cluster_id=cluster_id)
            async for record in result:
                yield str(record["id"])

    async def batch_bump_edges(
        self,
        edge_ids: Sequence[str],
        *,
        delta: float,
        ts: datetime,
    ) -> None:
        if not edge_ids:
            return
        rows = [{"edge_id": eid} for eid in edge_ids]
        cypher = """
        UNWIND $rows AS row
        MATCH ()-[r:RELATION {id: row.edge_id}]->()
        SET r.pheromone_delta = CASE
                WHEN coalesce(r.pheromone_delta, 0.0) + $delta > 1.0 THEN 1.0
                WHEN coalesce(r.pheromone_delta, 0.0) + $delta < -1.0 THEN -1.0
                ELSE coalesce(r.pheromone_delta, 0.0) + $delta
            END,
            r.last_traversed = $ts
        """
        async with self._session() as session:
            await session.run(cypher, rows=rows, delta=delta, ts=ts)

    async def list_aged_pheromone_edges(
        self,
        *,
        horizon: datetime,
        epsilon: float,
    ) -> list[tuple[str, float]]:
        cypher = """
        MATCH ()-[r:RELATION]->()
        WHERE r.last_traversed IS NOT NULL
          AND r.last_traversed < $horizon
          AND abs(coalesce(r.pheromone_delta, 0.0)) > $epsilon
        RETURN r.id AS id, coalesce(r.pheromone_delta, 0.0) AS delta
        """
        out: list[tuple[str, float]] = []
        async with self._session() as session:
            result = await session.run(cypher, horizon=horizon, epsilon=epsilon)
            async for record in result:
                out.append((str(record["id"]), float(record["delta"])))
        return out

    async def batch_update_pheromone_deltas(
        self,
        updates: Sequence[tuple[str, float]],
    ) -> None:
        if not updates:
            return
        rows = [{"edge_id": eid, "new_delta": nd} for eid, nd in updates]
        cypher = """
        UNWIND $rows AS row
        MATCH ()-[r:RELATION {id: row.edge_id}]->()
        SET r.pheromone_delta = row.new_delta
        """
        async with self._session() as session:
            await session.run(cypher, rows=rows)

    async def refresh_cross_cluster_edge_flags(self) -> None:
        """Recompute ``properties.cross_cluster`` on every RELATION (PHX-0060)."""
        cypher = """
        MATCH (s:KnowledgeNode)-[r:RELATION]->(t:KnowledgeNode)
        RETURN r.id AS id, r.properties_json AS properties_json,
               s.cluster_id AS sc, t.cluster_id AS tc
        """
        rows: list[dict[str, Any]] = []
        async with self._session() as session:
            result = await session.run(cypher)
            async for record in result:
                raw = record.get("properties_json") or "{}"
                props: dict[str, Any] = json.loads(raw) if raw else {}
                sc = record.get("sc")
                tc = record.get("tc")
                props["cross_cluster"] = bool(sc and tc and sc != tc)
                rows.append(
                    {
                        "id": record["id"],
                        "properties_json": json.dumps(props, sort_keys=True, default=str),
                    }
                )
        if not rows:
            return
        upd = """
        UNWIND $rows AS row
        MATCH ()-[r:RELATION]->()
        WHERE r.id = row.id
        SET r.properties_json = row.properties_json
        """
        async with self._session() as session:
            await session.run(upd, rows=rows)

    # ----- bulk operations ---------------------------------------------------

    async def export_layer(self, layer: Layer) -> AsyncIterator[KnowledgeNode]:
        """Async generator over all nodes in a given layer."""
        cypher = """
        MATCH (n:KnowledgeNode {layer: $layer})
        RETURN n{.*, id: n.id} AS node
        """
        async with self._session() as session:
            result = await session.run(cypher, layer=layer.value)
            async for record in result:
                yield _node_from_record(record["node"])

    async def import_nodes(self, nodes: AsyncIterator[KnowledgeNode]) -> None:
        async for node in nodes:
            await self.upsert_node(node)

    # ----- resolution-honesty queries ---------------------------------------

    async def list_pending_resolution(
        self,
        layer: Layer | None = None,
        limit: int = 100,
    ) -> list[KnowledgeNode]:
        _validate_int("limit", limit, minimum=1)
        # LIMIT cannot be a Cypher parameter on every Neo4j 5.x build;
        # validated-int interpolation keeps it portable.
        cypher = f"""
        MATCH (n:KnowledgeNode {{manual_resolution_needed: true}})
        WHERE $layer IS NULL OR n.layer = $layer
        RETURN n{{.*, id: n.id}} AS node
        ORDER BY n.created_at DESC
        LIMIT {limit}
        """
        async with self._session() as session:
            result = await session.run(
                cypher,
                layer=layer.value if layer is not None else None,
            )
            records = await result.data()
        return [_node_from_record(rec["node"]) for rec in records]

    async def resolve_node(
        self,
        node_id: str,
        wikidata_id: str | None,
    ) -> bool:
        # Operator confirms a Wikidata Q-ID for a previously
        # tier-0 mention. We bump tier to 1 (operator-confirmed),
        # set the flat wikidata_id index column + the JSON column,
        # and clear manual_resolution_needed. When wikidata_id is
        # falsy, only the manual flag clears (operator said "none
        # of the candidates fit").
        existing = await self.get_node(node_id)
        if existing is None:
            return False
        if wikidata_id:
            updated_external = {**existing.external_ids, "wikidata": wikidata_id}
            rest_external = {k: v for k, v in updated_external.items() if k != "wikidata"}
            cypher = """
            MATCH (n:KnowledgeNode {id: $node_id})
            SET n.wikidata_id              = $wikidata_id,
                n.external_ids_json        = $external_ids_json,
                n.resolution_tier          = $resolution_tier,
                n.manual_resolution_needed = false
            """
            params = {
                "node_id": node_id,
                "wikidata_id": wikidata_id,
                "external_ids_json": json.dumps(rest_external, sort_keys=True),
                "resolution_tier": 1,
            }
        else:
            cypher = """
            MATCH (n:KnowledgeNode {id: $node_id})
            SET n.manual_resolution_needed = false
            """
            params = {"node_id": node_id}
        async with self._session() as session:
            await session.run(cypher, **params)
        return True

    # ----- diagnostics -------------------------------------------------------

    async def count_nodes(self, layer: Layer | None = None) -> int:
        if layer is None:
            cypher = "MATCH (n:KnowledgeNode) RETURN count(n) AS c"
            params: dict[str, Any] = {}
        else:
            cypher = "MATCH (n:KnowledgeNode {layer: $layer}) RETURN count(n) AS c"
            params = {"layer": layer.value}
        async with self._session() as session:
            result = await session.run(cypher, **params)
            record = await result.single()
        return int(record["c"]) if record is not None else 0

    async def health(self) -> dict[str, object]:
        cypher = """
        MATCH (n:KnowledgeNode)
        WITH count(n) AS nodes,
             sum(CASE WHEN n.layer = 'ephemera' THEN 1 ELSE 0 END) AS eph,
             sum(CASE WHEN n.layer = 'mneme' THEN 1 ELSE 0 END) AS mne,
             sum(CASE WHEN n.manual_resolution_needed THEN 1 ELSE 0 END) AS pending
        OPTIONAL MATCH ()-[r:RELATION]->()
        RETURN nodes, eph, mne, pending, count(r) AS edges
        """
        async with self._session() as session:
            result = await session.run(cypher)
            record = await result.single()
        if record is None:
            return {
                "backend": "neo4j",
                "uri": self._settings.uri,
                "database": self._settings.database,
                "embedding_dim": self._embedding_dim,
                "nodes": 0,
                "edges": 0,
                "ephemera_nodes": 0,
                "mneme_nodes": 0,
                "pending_resolution": 0,
            }
        return {
            "backend": "neo4j",
            "uri": self._settings.uri,
            "database": self._settings.database,
            "embedding_dim": self._embedding_dim,
            "nodes": int(record["nodes"]),
            "edges": int(record["edges"]),
            "ephemera_nodes": int(record["eph"]),
            "mneme_nodes": int(record["mne"]),
            "pending_resolution": int(record["pending"]),
        }


__all__ = ["Neo4jKnowledgeStore"]
