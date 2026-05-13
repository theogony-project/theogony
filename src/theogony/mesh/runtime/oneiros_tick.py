"""Minimal Oneiros tick: drain delta buffer -> decay -> Hebbian merges ->
saturation -> rebuild CSR -> commit Lance version.

Steps for consolidation, splits, pathology, therapy are stubbed and call out
as part of S5.
"""

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
    EdgeStore,
    decay_edges_inplace,
    enforce_saturation,
    merge_edge_deltas,
)
from theogony.mesh.storage.nodes import MeshNodeStore

# ---- S5 stubs -------------------------------------------------------


def stub_consolidation_phase() -> None:
    raise NotImplementedError("Consolidation phase – Step S5")


def stub_split_phase() -> None:
    raise NotImplementedError("Sub-node splits – Step S5")


def stub_pathology_phase() -> None:
    raise NotImplementedError("Pathology surveillance – Step S5")


def stub_therapy_phase() -> None:
    raise NotImplementedError("Staged therapy – Step S5")


# ---- Tick result ----------------------------------------------------


@dataclass
class MinimalTickResult:
    edges_before: int
    edges_after: int
    delta_drained: int
    audit_id: str
    new_lance_version: int


# ---- Runtime --------------------------------------------------------


class MeshRuntime:
    """Warm-tier mesh opened from a filesystem directory.

    Call :meth:`open` to create or resume a workspace.  ``__init__`` is
    internal.
    """

    def __init__(
        self,
        root: Path,
        *,
        semantic_dim: int,
        frame_dim: int,
    ) -> None:
        self.root = root
        self.semantic_dim = semantic_dim
        self.frame_dim = frame_dim

        root.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(root / "lance"))

        self.nodes = MeshNodeStore(self.db, semantic_dim=semantic_dim, frame_dim=frame_dim)
        self.edges = EdgeStore(self.db)
        self.audit = MeshAuditLog(self.db)

        self._state_path = root / "mesh_state.json"

    @classmethod
    def open(cls, root: Path) -> MeshRuntime:
        """Open an existing workspace or initialise a new one.

        When the workspace already contains ``chunk_nodes`` the vector
        dimensions are read from the Lance schema so callers never need to
        remember them.
        """
        root = root.resolve()
        db = lancedb.connect(str(root / "lance"))
        resp = db.list_tables()
        tables = resp.tables or []
        if "chunk_nodes" not in tables:
            return cls(root, semantic_dim=384, frame_dim=64)

        chunk = db.open_table("chunk_nodes")
        sem = int(chunk.schema.field("semantic_vector").type.list_size)
        frm = int(chunk.schema.field("frame_vector").type.list_size)
        return cls(root, semantic_dim=sem, frame_dim=frm)

    # ---- state persistence ------------------------------------------

    def _read_state(self) -> dict[str, Any]:
        if not self._state_path.is_file():
            return {}
        return cast("dict[str, Any]", json.loads(self._state_path.read_text(encoding="utf-8")))

    def _write_state(self, data: dict[str, Any]) -> None:
        self._state_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def last_tick_at(self) -> datetime | None:
        raw = self._read_state().get("last_tick_at")
        if raw is None:
            return None
        return datetime.fromisoformat(str(raw))

    def current_lance_version(self) -> int:
        """Return the latest version across all managed tables (for status)."""
        max_ver = 0
        table_names = self.db.list_tables().tables or []
        for name in table_names:
            if name not in (
                "chunk_nodes",
                "consolidated_nodes",
                "mesh_edges",
                "edge_metadata",
                "mesh_audit",
            ):
                continue
            tbl = self.db.open_table(name)
            vers = tbl.list_versions()
            if vers:
                max_ver = max(max_ver, max(v["version"] for v in vers))
        return max_ver

    # ---- CSR --------------------------------------------------------

    def rebuild_csr(self) -> EdgeCSR:
        return self.edges.csr_from_store()

    # ---- tick -------------------------------------------------------

    def run_minimal_tick(
        self,
        *,
        lam: float = 0.05,
        dt: float = 1.0,
        max_out_degree: int = 64,
        w_max: float = 1.0,
    ) -> MinimalTickResult:
        """Drain delta buffer -> merge -> decay -> saturation -> Lance rewrite -> audit."""
        before = self.edges.count_rows()
        drained = self.edges.delta.drain()
        base = self.edges.load_all_edges()
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

        new_version = self.current_lance_version()
        state = self._read_state()
        state["last_tick_at"] = now.isoformat()
        state["lance_uri"] = str(self.root / "lance")
        self._write_state(state)

        return MinimalTickResult(
            edges_before=before,
            edges_after=after,
            delta_drained=len(drained),
            audit_id=aid,
            new_lance_version=new_version,
        )
