"""Edge storage: Lance quantitative rows, metadata sidecar, COO delta, CSR builder."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import lancedb
import pyarrow as pa
import torch

from theogony.mesh.schemas import Edge, EdgeMetadata

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


@dataclass(frozen=True)
class EdgeCSR:
    """CSR adjacency for outgoing edges (row = source, col = target)."""

    crow_indices: torch.Tensor
    col_indices: torch.Tensor
    values: torch.Tensor
    node_ids: list[str]
    id_to_index: dict[str, int]
    size: tuple[int, int]


class EdgeDeltaBuffer:
    """In-memory append path merged at Oneiros tick boundaries."""

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
                    "weight_delta": float(weight_delta),
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


def _edge_key(e: Edge) -> tuple[str, str]:
    return (e.source_id, e.target_id)


def merge_edge_deltas(
    base: list[Edge], deltas: list[dict[str, Any]], *, w_max: float
) -> list[Edge]:
    by_key: dict[tuple[str, str], Edge] = {}
    for e in base:
        by_key[_edge_key(e)] = e.model_copy(deep=True)

    for d in deltas:
        s, t = d["source_id"], d["target_id"]
        dw = float(d["weight_delta"])
        if dw <= 0:
            continue
        k = (s, t)
        if k in by_key:
            cur = by_key[k]
            nw = min(w_max, cur.weight + dw)
            by_key[k] = cur.model_copy(update={"weight": nw})
        else:
            # Minimal synthetic edge for Hebbian-only delta (S1).
            now = datetime.now(UTC)
            by_key[k] = Edge(
                source_id=s,
                target_id=t,
                weight=min(w_max, dw),
                born_at=now,
                last_fired_at=now,
            )
    return list(by_key.values())


def decay_edges_inplace(edges: list[Edge], *, lam: float, dt: float) -> None:
    """Discrete super-linear decay ``dw/dt ≈ -λ w^k`` with tier-modulated *k*."""

    def k_for_tier(tier: int) -> float:
        if tier <= 0:
            return 2.0
        if tier == 1:
            return 1.5
        return 1.2

    for e in edges:
        k = k_for_tier(e.decay_tier)
        w = float(e.weight)
        delta = lam * dt * (w**k)
        e.weight = max(0.0, w - delta)


def enforce_saturation(edges: list[Edge], *, max_out_degree: int, w_max: float) -> list[Edge]:
    """Per-source-node cap on outgoing edge count; drop lowest-weight edges first."""
    by_source: dict[str, list[Edge]] = {}
    for e in edges:
        by_source.setdefault(e.source_id, []).append(e)

    survivors: list[Edge] = []
    for out_list in by_source.values():
        out_list_sorted = sorted(out_list, key=lambda x: x.weight, reverse=True)
        kept = out_list_sorted[:max_out_degree]
        survivors.extend(kept)
    # Renormalise weights that exceed w_max (defensive)
    for e in survivors:
        e.weight = min(float(e.weight), w_max)
    return survivors


def build_csr_from_edges(edges: list[Edge], node_ids: list[str] | None = None) -> EdgeCSR:
    """Build PyTorch sparse CSR from ``Edge`` rows (conductance = weight * frame_consistency)."""
    endpoints: set[str] = set()
    for e in edges:
        endpoints.add(e.source_id)
        endpoints.add(e.target_id)
    if node_ids is None:
        ordered = sorted(endpoints)
    else:
        extra = endpoints - set(node_ids)
        ordered = sorted(set(node_ids) | extra)
    id_to_index = {nid: i for i, nid in enumerate(ordered)}
    n = len(ordered)

    row_counts = [0] * n
    for e in edges:
        si = id_to_index[e.source_id]
        row_counts[si] += 1
    crow = [0]
    for c in row_counts:
        crow.append(crow[-1] + c)
    nnz = crow[-1]
    col = [0] * nnz
    val = [0.0] * nnz
    write = crow[:-1]

    for e in edges:
        si = id_to_index[e.source_id]
        ti = id_to_index[e.target_id]
        pos = write[si]
        conductance = float(e.weight) * float(e.frame_consistency)
        col[pos] = ti
        val[pos] = conductance
        write[si] += 1

    crow_t = torch.tensor(crow, dtype=torch.int64)
    col_t = torch.tensor(col, dtype=torch.int64)
    val_t = torch.tensor(val, dtype=torch.float32)
    return EdgeCSR(
        crow_indices=crow_t,
        col_indices=col_t,
        values=val_t,
        node_ids=ordered,
        id_to_index=id_to_index,
        size=(n, n),
    )


class MeshEdgeStore:
    """Lance ``mesh_edges`` + ``edge_metadata`` with delta buffer."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        self._db = db
        self.delta = EdgeDeltaBuffer()
        if "mesh_edges" not in db.list_tables():
            self.edge_table = db.create_table("mesh_edges", schema=_EDGE_SCHEMA)
        else:
            self.edge_table = db.open_table("mesh_edges")
        if "edge_metadata" not in db.list_tables():
            self.meta_table = db.create_table("edge_metadata", schema=_METADATA_SCHEMA)
        else:
            self.meta_table = db.open_table("edge_metadata")

    def append_edge(self, edge: Edge) -> None:
        row = {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "weight": float(edge.weight),
            "decay_tier": int(edge.decay_tier),
            "frame_consistency": float(edge.frame_consistency),
            "eligibility": float(edge.eligibility),
            "feedback_modulated_strength": float(edge.feedback_modulated_strength),
            "born_at": edge.born_at,
            "last_fired_at": edge.last_fired_at,
            "payload_json": edge.model_dump_json(),
        }
        self.edge_table.add([row])
        meta = EdgeMetadata(
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_descriptor=edge.relation_descriptor,
            relation_kind=edge.relation_kind,
            description=edge.description,
            pids=edge.pids,
            creation_context=edge.creation_context,
        )
        if any(
            [
                meta.relation_descriptor,
                meta.relation_kind,
                meta.description,
                meta.pids,
                meta.creation_context,
            ]
        ):
            self.meta_table.add(
                [
                    {
                        "source_id": meta.source_id,
                        "target_id": meta.target_id,
                        "payload_json": meta.model_dump_json(),
                    }
                ]
            )

    def load_edges(self) -> list[Edge]:
        arrow = self.edge_table.search().limit(10_000_000).to_arrow()
        out: list[Edge] = []
        for row in arrow.to_pylist():
            out.append(Edge.model_validate_json(row["payload_json"]))
        return out

    def replace_all_edges(self, edges: list[Edge]) -> None:
        """Rewrite the quantitative edge table (Oneiros commit)."""
        self.edge_table.delete("true")
        if not edges:
            return
        batch = []
        for edge in edges:
            batch.append(
                {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "weight": float(edge.weight),
                    "decay_tier": int(edge.decay_tier),
                    "frame_consistency": float(edge.frame_consistency),
                    "eligibility": float(edge.eligibility),
                    "feedback_modulated_strength": float(edge.feedback_modulated_strength),
                    "born_at": edge.born_at,
                    "last_fired_at": edge.last_fired_at,
                    "payload_json": edge.model_dump_json(),
                }
            )
        self.edge_table.add(batch)

    def count_rows(self) -> int:
        return int(self.edge_table.count_rows())

    def csr_from_store(self, node_ids: list[str] | None = None) -> EdgeCSR:
        return build_csr_from_edges(self.load_edges(), node_ids=node_ids)
