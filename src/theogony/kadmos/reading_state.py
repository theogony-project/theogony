"""
Kadmos v2 — ReadingStateStore: LanceDB-backed session store.

This module owns the durable side of the reading session.  The in-memory
:class:`ReadingState` (in ``model.py``) is the fast mutable view; this
store is the append-only, query-ready substrate that backs it.

Architecture (TARGET_ARCHITECTURE.md):
  - Kadmos writes directly to LanceDB, NOT through the KnowledgeStore
    protocol (which is a Neo4j legacy interface).
  - The LanceDB database is in-process, temporary per session by default.
    It can optionally be persisted to disk for later export.

Two tables:
  ``concepts`` — one row per concept, including superseded revisions.
                 Revisions are new rows with ``supersedes_id`` set, not
                 in-place updates (append-only discipline).
  ``edges``    — one row per edge. Same supersedes pattern.

After the reading session completes, a post-read kNN pass adds implicit
edges (top-k similarity neighbours per concept) — this is what drives the
100–500:1 edge/node ratio target (kadmos_v2_brief.md §4.1).

The store does NOT manage embeddings — the KadmosReader calls the
EmbeddingProvider and passes vectors in directly.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import lancedb
import pyarrow as pa

from theogony.config.logging import get_logger
from theogony.kadmos.model import (
    ActiveConcept,
    ActiveEdge,
    HypothesisCandidate,
    RevisionRecord,
    SynthesisNode,
)

if TYPE_CHECKING:
    pass

log = get_logger("kadmos.reading_state")

# Embedding dimension — matches the default BGE-small-en-v1.5 model.
# The store stores the dimension as a schema parameter; the KadmosReader
# must use a consistent embedder throughout a session.
_DEFAULT_EMBEDDING_DIM = 384

# Q3: top-5 similarity + top-3 traversal per step
SIMILARITY_CANDIDATES_K = 5
TRAVERSAL_CANDIDATES_K = 3

# Q2: working memory capacity ceiling before compression is triggered
WM_CAPACITY = 50

# Activation decay factor per reading step: τ = 4 steps, e^(-1/4) ≈ 0.78
WM_DECAY_FACTOR = 0.779  # exp(-1/4)


def _concept_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.utf8()),
            pa.field("label", pa.utf8()),
            pa.field("description", pa.utf8()),
            pa.field("embedding", pa.list_(pa.float32(), dim)),
            pa.field("activation", pa.float32()),
            pa.field("step_created", pa.int32()),
            pa.field("invalidated", pa.bool_()),
            pa.field("supersedes_id", pa.utf8()),  # "" = original, else = revision
            pa.field("revision_type", pa.utf8()),  # "" = original
            pa.field("revision_reason", pa.utf8()),
        ]
    )


def _edge_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.utf8()),
            pa.field("source_id", pa.utf8()),
            pa.field("target_id", pa.utf8()),
            pa.field("relation_description", pa.utf8()),
            pa.field("edge_embedding", pa.list_(pa.float32(), dim)),
            pa.field("weight", pa.float32()),
            pa.field("step_created", pa.int32()),
            pa.field("invalidated", pa.bool_()),
            pa.field("supersedes_id", pa.utf8()),
            pa.field("is_implicit", pa.bool_()),  # True = added by kNN post-pass
        ]
    )


class ReadingStateStore:
    """LanceDB-backed store for one KadmosReader session.

    Parameters
    ----------
    session_id:
        Unique identifier for this reading session.
    embedding_dim:
        Dimension of embedding vectors (must match EmbeddingProvider.dim).
    db_path:
        Directory for the LanceDB database.  Defaults to a fresh tmp
        directory that is retained after the session for inspection.
        Pass ``None`` to use an in-memory (non-persistent) path.
    """

    def __init__(
        self,
        session_id: str,
        embedding_dim: int = _DEFAULT_EMBEDDING_DIM,
        db_path: str | Path | None = None,
    ) -> None:
        self._session_id = session_id
        self._dim = embedding_dim

        if db_path is None:
            import tempfile

            self._db_dir = Path(tempfile.mkdtemp(prefix="kadmos_"))
            self._owned_dir = True
        else:
            self._db_dir = Path(db_path)
            self._db_dir.mkdir(parents=True, exist_ok=True)
            self._owned_dir = False

        self._db = lancedb.connect(str(self._db_dir))
        self._concepts_tbl = self._db.create_table(
            "concepts", schema=_concept_schema(self._dim), mode="overwrite"
        )
        self._edges_tbl = self._db.create_table(
            "edges", schema=_edge_schema(self._dim), mode="overwrite"
        )
        log.debug(
            "kadmos session store opened session_id=%s db=%s",
            session_id,
            self._db_dir,
        )

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._db_dir

    @property
    def session_id(self) -> str:
        return self._session_id

    # -------------------------------------------------------------------------
    # Concept writes
    # -------------------------------------------------------------------------

    def add_concept(
        self,
        concept: ActiveConcept,
        embedding: list[float],
        *,
        step: int,
    ) -> None:
        """Write a new concept row.  Raises if embedding dim mismatches."""
        if len(embedding) != self._dim:
            raise ValueError(f"embedding dim mismatch: expected {self._dim}, got {len(embedding)}")
        row = pa.table(
            {
                "id": [concept.id],
                "label": [concept.label],
                "description": [concept.description or ""],
                "embedding": [embedding],
                "activation": [float(concept.activation)],
                "step_created": [step],
                "invalidated": [concept.invalidated],
                "supersedes_id": [""],
                "revision_type": [""],
                "revision_reason": [""],
            }
        )
        self._concepts_tbl.add(row)

    def revise_concept(
        self,
        concept: ActiveConcept,
        embedding: list[float],
        revision: RevisionRecord,
        *,
        step: int,
    ) -> None:
        """Append a revision row (original row is not modified — append-only)."""
        if len(embedding) != self._dim:
            raise ValueError(f"embedding dim mismatch: expected {self._dim}, got {len(embedding)}")
        row = pa.table(
            {
                "id": [concept.id + f"_rev{step}"],
                "label": [concept.label],
                "description": [concept.description or ""],
                "embedding": [embedding],
                "activation": [float(concept.activation)],
                "step_created": [step],
                "invalidated": [concept.invalidated],
                "supersedes_id": [concept.id],
                "revision_type": [revision.revision_type],
                "revision_reason": [revision.reason],
            }
        )
        self._concepts_tbl.add(row)

    # -------------------------------------------------------------------------
    # Edge writes
    # -------------------------------------------------------------------------

    def add_edge(
        self,
        edge: ActiveEdge,
        edge_embedding: list[float],
        *,
        step: int,
    ) -> None:
        if len(edge_embedding) != self._dim:
            raise ValueError(
                f"edge embedding dim mismatch: expected {self._dim}, got {len(edge_embedding)}"
            )
        row = pa.table(
            {
                "id": [edge.id],
                "source_id": [edge.source_id],
                "target_id": [edge.target_id],
                "relation_description": [edge.relation_description],
                "edge_embedding": [edge_embedding],
                "weight": [float(edge.weight)],
                "step_created": [step],
                "invalidated": [edge.invalidated],
                "supersedes_id": [""],
                "is_implicit": [False],
            }
        )
        self._edges_tbl.add(row)

    def add_synthesis_as_concept(
        self,
        synthesis: SynthesisNode,
        embedding: list[float],
        *,
        step: int,
    ) -> None:
        """Write a synthesis node as a concept row with 'synthesis' in description."""
        if len(embedding) != self._dim:
            raise ValueError(f"embedding dim mismatch: expected {self._dim}, got {len(embedding)}")
        row = pa.table(
            {
                "id": [synthesis.id],
                "label": [synthesis.label],
                "description": [f"[synthesis:{synthesis.synthesis_level}] {synthesis.description}"],
                "embedding": [embedding],
                "activation": [1.0],
                "step_created": [step],
                "invalidated": [False],
                "supersedes_id": [""],
                "revision_type": ["synthesis"],
                "revision_reason": [synthesis.synthesis_level],
            }
        )
        self._concepts_tbl.add(row)

    # -------------------------------------------------------------------------
    # kNN similarity search — Schritt A
    # -------------------------------------------------------------------------

    def similarity_candidates(
        self,
        query_embedding: list[float],
        k: int = SIMILARITY_CANDIDATES_K,
    ) -> list[HypothesisCandidate]:
        """Find top-k concept nodes by cosine similarity.

        Returns only non-invalidated, non-superseded (original) rows.
        """
        if self._concepts_tbl.count_rows() == 0:
            return []
        try:
            results = (
                self._concepts_tbl.search(query_embedding)
                .metric("cosine")
                .where("invalidated = false AND supersedes_id = ''", prefilter=True)
                .limit(k)
                .to_arrow()
            )
        except Exception as exc:
            log.warning("kadmos: similarity_candidates failed: %s", exc)
            return []

        candidates: list[HypothesisCandidate] = []
        ids = results.column("id").to_pylist()
        labels = results.column("label").to_pylist()
        distances = results.column("_distance").to_pylist()
        for cid, label, dist in zip(ids, labels, distances, strict=True):
            # LanceDB returns distance (lower=closer for cosine); convert to score
            score = max(0.0, 1.0 - float(dist))
            candidates.append(
                HypothesisCandidate(
                    concept_id=cid,
                    label=str(label),
                    score=score,
                    hypothesis_type="similarity",
                )
            )
        return candidates

    # -------------------------------------------------------------------------
    # Graph traversal — Schritt A
    # -------------------------------------------------------------------------

    def traversal_candidates(
        self,
        active_concept_ids: list[str],
        k: int = TRAVERSAL_CANDIDATES_K,
    ) -> list[HypothesisCandidate]:
        """Find concepts reachable from active concepts via edges.

        Returns at most ``k`` candidates not already in ``active_concept_ids``.
        """
        if not active_concept_ids or self._edges_tbl.count_rows() == 0:
            return []

        found: dict[str, float] = {}
        for cid in active_concept_ids:
            try:
                # Outgoing edges
                out = (
                    self._edges_tbl.search()
                    .where(
                        f"source_id = '{cid}' AND invalidated = false AND supersedes_id = ''",
                        prefilter=True,
                    )
                    .limit(10)
                    .to_arrow()
                )
                for tid, w in zip(
                    out.column("target_id").to_pylist(),
                    out.column("weight").to_pylist(),
                    strict=True,
                ):
                    if tid not in active_concept_ids:
                        found[str(tid)] = max(found.get(str(tid), 0.0), float(w))
            except Exception:
                pass

        # Sort by weight descending, take top-k
        sorted_found = sorted(found.items(), key=lambda kv: kv[1], reverse=True)[:k]

        # Resolve labels
        candidates: list[HypothesisCandidate] = []
        for tid, weight in sorted_found:
            label = self._get_concept_label(tid)
            candidates.append(
                HypothesisCandidate(
                    concept_id=tid,
                    label=label,
                    score=weight,
                    hypothesis_type="traversal",
                )
            )
        return candidates

    # -------------------------------------------------------------------------
    # Post-read kNN pass — implicit edges
    # -------------------------------------------------------------------------

    def add_implicit_edges(self, k: int = 20) -> int:
        """Add top-k similarity edges for every non-invalidated concept node.

        These are the implicit kNN edges that drive the high edge/node ratio
        (kadmos_v2_brief.md §4.1).  Called once after the reading loop finishes.

        Returns the number of implicit edges added.
        """
        if self._concepts_tbl.count_rows() == 0:
            return 0

        all_rows = (
            self._concepts_tbl.search()
            .where("invalidated = false AND supersedes_id = ''", prefilter=True)
            .limit(10_000)
            .to_arrow()
        )
        ids = all_rows.column("id").to_pylist()
        embeddings = all_rows.column("embedding").to_pylist()
        total_added = 0

        for src_id, src_emb in zip(ids, embeddings, strict=True):
            try:
                hits = (
                    self._concepts_tbl.search(src_emb)
                    .metric("cosine")
                    .where("invalidated = false AND supersedes_id = ''", prefilter=True)
                    .limit(k + 1)
                    .to_arrow()
                )
            except Exception:
                continue

            hit_ids = hits.column("id").to_pylist()
            hit_dists = hits.column("_distance").to_pylist()

            edges_rows: list[dict[str, Any]] = []
            for tid, dist in zip(hit_ids, hit_dists, strict=True):
                if str(tid) == str(src_id):
                    continue
                edge_id = f"impl_{src_id}_{tid}"
                similarity = max(0.0, 1.0 - float(dist))
                # Edge embedding = average of source and target embeddings (cheap)
                tgt_emb = embeddings[ids.index(tid)] if tid in ids else src_emb
                avg_emb = [(a + b) / 2.0 for a, b in zip(src_emb, tgt_emb, strict=True)]
                edges_rows.append(
                    {
                        "id": edge_id,
                        "source_id": str(src_id),
                        "target_id": str(tid),
                        "relation_description": "implicit_knn",
                        "edge_embedding": avg_emb,
                        "weight": similarity,
                        "step_created": -1,
                        "invalidated": False,
                        "supersedes_id": "",
                        "is_implicit": True,
                    }
                )

            if edges_rows:
                batch = pa.table({col: [r[col] for r in edges_rows] for col in edges_rows[0]})
                self._edges_tbl.add(batch)
                total_added += len(edges_rows)

        log.debug("kadmos: post-read kNN pass added %d implicit edges", total_added)
        return total_added

    # -------------------------------------------------------------------------
    # Counts / diagnostics
    # -------------------------------------------------------------------------

    def concept_count(self, *, include_revisions: bool = False) -> int:
        if int(self._concepts_tbl.count_rows()) == 0:
            return 0
        if include_revisions:
            return int(self._concepts_tbl.count_rows())
        try:
            return int(
                self._concepts_tbl.search()
                .where("supersedes_id = ''", prefilter=True)
                .limit(1_000_000)
                .to_arrow()
                .num_rows
            )
        except Exception:
            return int(self._concepts_tbl.count_rows())

    def edge_count(self, *, implicit: bool | None = None) -> int:
        if int(self._edges_tbl.count_rows()) == 0:
            return 0
        try:
            if implicit is None:
                clause = "supersedes_id = ''"
            elif implicit:
                clause = "is_implicit = true"
            else:
                clause = "is_implicit = false AND supersedes_id = ''"
            return int(
                self._edges_tbl.search()
                .where(clause, prefilter=True)
                .limit(1_000_000)
                .to_arrow()
                .num_rows
            )
        except Exception:
            return int(self._edges_tbl.count_rows())

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _get_concept_label(self, concept_id: str) -> str:
        try:
            result = (
                self._concepts_tbl.search()
                .where(f"id = '{concept_id}'", prefilter=True)
                .limit(1)
                .to_arrow()
            )
            if result.num_rows > 0:
                return str(result.column("label").to_pylist()[0])
        except Exception:
            pass
        return concept_id


def new_concept_id() -> str:
    """Mint a fresh concept ID."""
    return f"C-{uuid.uuid4().hex[:12]}"


def new_edge_id() -> str:
    """Mint a fresh edge ID."""
    return f"E-{uuid.uuid4().hex[:12]}"


def new_synthesis_id() -> str:
    """Mint a fresh synthesis node ID."""
    return f"S-{uuid.uuid4().hex[:12]}"
