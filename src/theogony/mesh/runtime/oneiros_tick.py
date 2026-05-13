"""Minimal Oneiros tick: delta drain, decay, Hebb merge, saturation, CSR rebuild."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import lancedb

from theogony.mesh.storage.audit import MeshAuditLog
from theogony.mesh.storage.edges import (
    EdgeCSR,
    MeshEdgeStore,
    decay_edges_inplace,
    enforce_saturation,
    merge_edge_deltas,
)
from theogony.mesh.storage.nodes import MeshNodeStore


def stub_consolidation_phase() -> None:
    """Reserved for Step S5 (full Oneiros)."""
    raise NotImplementedError("consolidation is Step S5 — not implemented in S1")


def stub_split_phase() -> None:
    """Reserved for Step S5 (full Oneiros)."""
    raise NotImplementedError("sub-node splits are Step S5 — not implemented in S1")


def stub_pathology_phase() -> None:
    """Reserved for Step S5 (Argus pathology)."""
    raise NotImplementedError("pathology surveillance is Step S5 — not implemented in S1")


def stub_therapy_phase() -> None:
    """Reserved for Step S5 (staged therapy)."""
    raise NotImplementedError("therapy is Step S5 — not implemented in S1")


@dataclass
class MinimalTickResult:
    """Summary returned to callers/tests after one tick."""

    edges_before: int
    edges_after: int
    delta_drained: int
    audit_id: str


class MeshRuntime:
    """Warm-tier mesh opened from a filesystem directory."""

    def __init__(
        self,
        root: Path,
        *,
        semantic_dim: int,
        frame_dim: int,
        structural_dim: int = 0,
        temporal_dim: int = 0,
        description_dim: int = 0,
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.root / "lance"))
        self.nodes = MeshNodeStore(
            self.db,
            semantic_dim=semantic_dim,
            frame_dim=frame_dim,
            structural_dim=structural_dim,
            temporal_dim=temporal_dim,
            description_dim=description_dim,
        )
        self.edges = MeshEdgeStore(self.db)
        self.audit = MeshAuditLog(self.db)
        self.state_path = self.root / "mesh_state.json"

    @classmethod
    def open(cls, root: Path) -> MeshRuntime:
        """Open or initialise a workspace, inferring vector widths from existing Lance schemas."""
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(root / "lance"))
        if "chunk_nodes" not in db.list_tables():
            return cls(
                root,
                semantic_dim=384,
                frame_dim=64,
                structural_dim=0,
                temporal_dim=0,
                description_dim=0,
            )
        chunk = db.open_table("chunk_nodes")
        sem = int(chunk.schema.field("semantic_vector").type.list_size)
        frm = int(chunk.schema.field("frame_vector").type.list_size)
        consolidated = db.open_table("consolidated_nodes")
        cs = consolidated.schema
        s_dim = int(cs.field("structural_vector").type.list_size)
        t_dim = int(cs.field("temporal_vector").type.list_size)
        d_dim = int(cs.field("description_vector").type.list_size)
        # Tables use placeholder width 1 when optional tier is disabled in storage layer.
        struct_active = 0 if s_dim <= 1 else s_dim
        temp_active = 0 if t_dim <= 1 else t_dim
        desc_active = 0 if d_dim <= 1 else d_dim
        return cls(
            root,
            semantic_dim=sem,
            frame_dim=frm,
            structural_dim=struct_active,
            temporal_dim=temp_active,
            description_dim=desc_active,
        )

    def read_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {}
        return cast(dict[str, Any], json.loads(self.state_path.read_text(encoding="utf-8")))

    def write_state(self, data: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def last_tick_at(self) -> datetime | None:
        raw = self.read_state().get("last_tick_at")
        if raw is None:
            return None
        return datetime.fromisoformat(str(raw))

    def rebuild_csr(self) -> EdgeCSR:
        """CSR view of the current committed edge table."""
        return self.edges.csr_from_store()

    def run_minimal_tick(
        self,
        *,
        lam: float = 0.05,
        dt: float = 1.0,
        max_out_degree: int = 64,
        w_max: float = 1.0,
    ) -> MinimalTickResult:
        """Drain delta → merge → decay → saturation → Lance rewrite → audit."""
        before = self.edges.count_rows()
        drained = self.edges.delta.drain()
        base = self.edges.load_edges()
        merged = merge_edge_deltas(base, drained, w_max=w_max)
        decay_edges_inplace(merged, lam=lam, dt=dt)
        merged = enforce_saturation(merged, max_out_degree=max_out_degree, w_max=w_max)
        self.edges.replace_all_edges(merged)
        after = self.edges.count_rows()
        now = datetime.now(UTC)
        aid = self.audit.append(
            action="mesh_oneiros_minimal_tick",
            detail={
                "edges_before": before,
                "edges_after": after,
                "delta_drained": len(drained),
                "lambda": lam,
                "dt": dt,
                "max_out_degree": max_out_degree,
            },
        )
        state = self.read_state()
        state["last_tick_at"] = now.isoformat()
        state["lance_uri"] = str(self.root / "lance")
        self.write_state(state)
        return MinimalTickResult(
            edges_before=before,
            edges_after=after,
            delta_drained=len(drained),
            audit_id=aid,
        )
