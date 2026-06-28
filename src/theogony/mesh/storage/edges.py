"""Edge storage: Lance ``mesh_edges`` table, COO delta buffer, CSR builder.

Per MESH_IMPLEMENTATION.md §"Edges — PyTorch sparse + delta buffer + Lance
metadata table":

1. **Stable CSR sparse tensor** – built at Oneiros tick boundaries.
2. **COO delta buffer** – lock-free append path for Hebbian updates.
3. **Lance edge-metadata table** – off-hot-path rich descriptors (parallel).

Edge insertion at S1 writes to both the quantitative Lance table and (when
metadata is present) the metadata table. At Oneiros tick time the delta buffer
is drained, merged, decayed, saturating the CSR is rebuilt, the quantitative
table is atomically replaced, and the metadata table is resynced.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import lancedb
import pyarrow as pa
import torch

from theogony.mesh.schemas import Edge, EdgeMetadata


def _have_table(db: lancedb.DBConnection, name: str) -> bool:
    resp = db.list_tables()
    return name in (resp.tables or [])


# ---- Lance schemas ----

_EDGE_SCHEMA = pa.schema(
    [
        ("source_id", pa.string()),
        ("target_id", pa.string()),
        ("weight", pa.float32()),
        ("decay_tier", pa.int32()),
        ("frame_consistency", pa.float32()),
        ("eligibility", pa.float32()),
        ("feedback_modulated_strength", pa.float32()),
        ("born_at", pa.timestamp("us")),
        ("last_fired_at", pa.timestamp("us")),
        ("payload_json", pa.string()),
    ]
)

_METADATA_SCHEMA = pa.schema(
    [
        ("source_id", pa.string()),
        ("target_id", pa.string()),
        ("payload_json", pa.string()),
    ]
)

# Edge-identity index for O(1) deduplication without materialising Edge objects
# (PHX-1033). One short hashed key per directed (source, target, relation)
# edge — the lightweight analogue of MeshNodeStore's consolidated_qid_index.
_DEDUP_INDEX_SCHEMA = pa.schema([("dedup_key", pa.string())])


# ---- CSR container ----


@dataclass(frozen=True)
class EdgeCSR:
    """CSR adjacency for outgoing edges (row = source, col = target)."""

    crow_indices: torch.Tensor  # int64  (N+1,)
    col_indices: torch.Tensor  # int64  (E,)
    values: torch.Tensor  # float32  (E,)
    node_ids: list[str]
    id_to_index: dict[str, int]


# ---- Delta buffer ----


class EdgeDeltaBuffer:
    """Lock-free append path merged into the stable CSR at each Oneiros tick."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: list[dict[str, Any]] = []

    def append_hebbian_delta(
        self,
        *,
        source_id: str,
        target_id: str,
        weight_delta: float,
    ) -> None:
        with self._lock:
            self._rows.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "weight_delta": weight_delta,
                }
            )

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            out = self._rows
            self._rows = []
            return out

    def pending(self) -> int:
        with self._lock:
            return len(self._rows)


# ---- Merging helpers ----


def merge_edge_deltas(
    base: list[Edge], deltas: list[dict[str, Any]], *, w_max: float
) -> list[Edge]:
    """Apply weight deltas to existing edges; create synthetic edges for new pairs."""

    def _key(e: Edge) -> tuple[str, str]:
        return (str(e.source_id), str(e.target_id))

    by_key: dict[tuple[str, str], Edge] = {}
    for e in base:
        by_key[_key(e)] = e.model_copy(deep=True)

    for d in deltas:
        s = str(d["source_id"])
        t = str(d["target_id"])
        dw = float(d["weight_delta"])
        if dw <= 0:
            continue
        k = (s, t)
        if k in by_key:
            cur = by_key[k]
            nw = min(w_max, cur.weight + dw)
            by_key[k] = cur.model_copy(update={"weight": nw})
        else:
            now = datetime.now(UTC)
            by_key[k] = Edge(
                source_id=s,  # type: ignore[arg-type]
                target_id=t,  # type: ignore[arg-type]
                weight=min(w_max, dw),
                born_at=now,
                last_fired_at=now,
            )
    return list(by_key.values())


def decay_edges_inplace(edges: list[Edge], *, lam: float = 0.05, dt: float = 1.0) -> None:
    """Discrete super-linear decay ``Δw = -λ · dt · w^k``, tier-modulated *k*.
    Default: ``k = 2`` (tier 0), ``k = 1.5`` (tier 1), ``k = 1.2`` (tier 2+).
    """

    def _k(tier: int) -> float:
        if tier <= 0:
            return 2.0
        if tier == 1:
            return 1.5
        return 1.2

    for e in edges:
        k = _k(e.decay_tier)
        w = float(e.weight)
        delta = lam * dt * (w**k)
        e.weight = max(0.0, w - delta)


def enforce_saturation(
    edges: list[Edge], *, max_out_degree: int = 64, w_max: float = 1.0
) -> list[Edge]:
    """Per-source-node cap on outgoing count; drop lowest-weight edges first."""
    by_source: dict[str, list[Edge]] = {}
    for e in edges:
        key = str(e.source_id)
        by_source.setdefault(key, []).append(e)

    survivors: list[Edge] = []
    for out_list in by_source.values():
        sorted_out = sorted(out_list, key=lambda x: x.weight, reverse=True)
        kept = sorted_out[:max_out_degree]
        survivors.extend(kept)

    for e in survivors:
        e.weight = min(e.weight, w_max)
    return survivors


def build_csr_from_edges(edges: list[Edge]) -> EdgeCSR:
    """Build a PyTorch CSR tensor where conductance = weight × frame_consistency."""
    endpoints: set[str] = set()
    for e in edges:
        endpoints.add(str(e.source_id))
        endpoints.add(str(e.target_id))
    ordered = sorted(endpoints)
    id_to_index = {nid: i for i, nid in enumerate(ordered)}
    n = len(ordered)

    row_counts = [0] * n
    for e in edges:
        si = id_to_index[str(e.source_id)]
        row_counts[si] += 1
    crow = [0]
    for c in row_counts:
        crow.append(crow[-1] + c)
    nnz = crow[-1]
    col = [0] * nnz
    val = [0.0] * nnz
    write = crow[:-1].copy()

    for e in edges:
        si = id_to_index[str(e.source_id)]
        ti = id_to_index[str(e.target_id)]
        pos = write[si]
        col[pos] = ti
        val[pos] = float(e.weight) * float(e.frame_consistency)
        write[si] += 1

    return EdgeCSR(
        crow_indices=torch.tensor(crow, dtype=torch.int64),
        col_indices=torch.tensor(col, dtype=torch.int64),
        values=torch.tensor(val, dtype=torch.float32),
        node_ids=ordered,
        id_to_index=id_to_index,
    )


# ---- Lance-backed edge store ----


class EdgeStore:
    """Lance ``mesh_edges`` table + parallel ``edge_metadata`` table + delta buffer."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        self._db = db
        self.delta = EdgeDeltaBuffer()

        if _have_table(db, "mesh_edges"):
            self.edge_table = db.open_table("mesh_edges")
        else:
            self.edge_table = db.create_table("mesh_edges", schema=_EDGE_SCHEMA)

        if _have_table(db, "edge_metadata"):
            self.meta_table = db.open_table("edge_metadata")
        else:
            self.meta_table = db.create_table("edge_metadata", schema=_METADATA_SCHEMA)

        if _have_table(db, "edge_dedup_index"):
            self.dedup_index = db.open_table("edge_dedup_index")
        else:
            self.dedup_index = db.create_table("edge_dedup_index", schema=_DEDUP_INDEX_SCHEMA)
        self._ensure_dedup_index()

    @staticmethod
    def dedup_key(source_id: str, target_id: str, relation_descriptor: str | None) -> str:
        """Stable 128-bit hash identifying a directed (source, target, relation) edge.

        Hashing keeps the index key fixed-width, control-character-free, and
        safe to compare, regardless of what a free-form ``relation_descriptor``
        contains.  Collisions are astronomically unlikely; a collision would at
        worst skip one legitimate edge as a duplicate (a benign, audited loss).
        """
        raw = f"{source_id}\x1f{target_id}\x1f{relation_descriptor or ''}".encode()
        return hashlib.blake2b(raw, digest_size=16).hexdigest()

    def _dedup_rows(self, edges: list[Edge]) -> list[dict[str, str]]:
        return [
            {
                "dedup_key": self.dedup_key(
                    str(edge.source_id), str(edge.target_id), edge.relation_descriptor
                )
            }
            for edge in edges
        ]

    def _iter_existing_dedup_keys(self, *, page_size: int = 4096) -> Iterator[str]:
        """Yield dedup keys for already-stored edges without building Edge objects."""
        offset = 0
        while True:
            rows = self.edge_table.search().limit(page_size).offset(offset).to_list()
            if not rows:
                return
            for row in rows:
                relation_descriptor: str | None = None
                payload = row.get("payload_json")
                if payload:
                    try:
                        relation_descriptor = json.loads(payload).get("relation_descriptor")
                    except (ValueError, TypeError):
                        relation_descriptor = None
                yield self.dedup_key(
                    str(row["source_id"]), str(row["target_id"]), relation_descriptor
                )
            offset += len(rows)

    def _ensure_dedup_index(self) -> None:
        """Backfill the dedup index for a workspace whose edges predate it (once)."""
        if self.edge_table.count_rows() == 0:
            return
        if self.dedup_index.count_rows() > 0:
            return
        batch: list[dict[str, str]] = []
        for key in self._iter_existing_dedup_keys():
            batch.append({"dedup_key": key})
            if len(batch) >= 4096:
                self.dedup_index.add(batch)
                batch = []
        if batch:
            self.dedup_index.add(batch)

    def load_dedup_keys(self) -> set[str]:
        """Return all stored edge dedup keys — the cheap replacement for a
        ``load_all_edges()`` scan when only edge identity is needed."""
        arrow = self.dedup_index.search().to_arrow()
        if arrow.num_rows == 0:
            return set()
        return set(arrow.column("dedup_key").to_pylist())

    @staticmethod
    def _edge_row(edge: Edge) -> dict[str, Any]:
        return {
            "source_id": str(edge.source_id),
            "target_id": str(edge.target_id),
            "weight": float(edge.weight),
            "decay_tier": int(edge.decay_tier),
            "frame_consistency": float(edge.frame_consistency),
            "eligibility": float(edge.eligibility),
            "feedback_modulated_strength": float(edge.feedback_modulated_strength),
            "born_at": edge.born_at,
            "last_fired_at": edge.last_fired_at,
            "payload_json": edge.model_dump_json(),
        }

    @staticmethod
    def _metadata_row(edge: Edge) -> dict[str, Any] | None:
        meta = EdgeMetadata(
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_descriptor=edge.relation_descriptor,
            relation_kind=edge.relation_kind,
            description=edge.description,
            pids=edge.pids,
            creation_context=edge.creation_context,
        )
        if not any(
            [
                meta.relation_descriptor,
                meta.relation_kind,
                meta.description,
                meta.pids,
                meta.creation_context,
            ]
        ):
            return None
        return {
            "source_id": str(meta.source_id),
            "target_id": str(meta.target_id),
            "payload_json": meta.model_dump_json(),
        }

    def append_edge(self, edge: Edge) -> None:
        """Write one edge to the quantitative table + optionally metadata."""
        self.append_edges([edge])

    def append_edges(self, edges: list[Edge]) -> None:
        """Write many edges to the quantitative table + optional metadata."""
        if not edges:
            return
        self.edge_table.add([self._edge_row(edge) for edge in edges])
        meta_rows = [row for edge in edges if (row := self._metadata_row(edge)) is not None]
        if meta_rows:
            self.meta_table.add(meta_rows)
        self.dedup_index.add(self._dedup_rows(edges))

    def load_all_edges(self) -> list[Edge]:
        arrow = self.edge_table.search().to_arrow()
        out: list[Edge] = []
        for row in arrow.to_pylist():
            out.append(Edge.model_validate_json(row["payload_json"]))
        return out

    def load_metadata_for_sources(
        self, source_ids: Iterable[str]
    ) -> dict[tuple[str, str], EdgeMetadata]:
        """Load edge descriptors for a small set of source nodes (Constellation enrichment).

        Keyed by ``(source_id, target_id)``. Used by retrieval to attach
        ``relation_descriptor`` to the edges of an activated sub-graph without scanning
        the full metadata table. ULIDs are alphanumeric, so they inline safely in the
        Lance filter (same pattern as :meth:`neighbor_ids`).
        """
        ids = {str(s) for s in source_ids}
        if not ids:
            return {}
        quoted = ",".join(f'"{sid}"' for sid in ids)
        rows = self.meta_table.search().where(f"source_id IN ({quoted})").to_list()
        out: dict[tuple[str, str], EdgeMetadata] = {}
        for row in rows:
            meta = EdgeMetadata.model_validate_json(row["payload_json"])
            out[(str(meta.source_id), str(meta.target_id))] = meta
        return out

    def replace_all_edges(self, edges: list[Edge]) -> None:
        """Atomically replace the quantitative and metadata tables (Oneiros commit)."""
        self.edge_table.delete("true")
        self.meta_table.delete("true")
        self.dedup_index.delete("true")
        if not edges:
            return
        self.edge_table.add([self._edge_row(edge) for edge in edges])
        meta_rows = [row for edge in edges if (row := self._metadata_row(edge)) is not None]
        if meta_rows:
            self.meta_table.add(meta_rows)
        self.dedup_index.add(self._dedup_rows(edges))

    def count_rows(self) -> int:
        return int(self.edge_table.count_rows())

    def neighbor_ids(self, node_id: str) -> set[str]:
        outgoing = self.edge_table.search().where(f'source_id = "{node_id}"').to_list()
        incoming = self.edge_table.search().where(f'target_id = "{node_id}"').to_list()
        neighbours = {str(row["target_id"]) for row in outgoing}
        neighbours.update(str(row["source_id"]) for row in incoming)
        return neighbours

    def csr_from_store(self) -> EdgeCSR:
        return build_csr_from_edges(self.load_all_edges())
