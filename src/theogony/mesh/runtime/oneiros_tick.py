"""Minimal Oneiros tick: drain delta buffer -> decay -> Hebbian merges ->
saturation -> rebuild CSR -> commit Lance version.

Steps for consolidation, splits, pathology, therapy are stubbed and call out
as part of S5.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import lancedb

from theogony.mesh.relation_pids import pid_for
from theogony.mesh.schemas import Edge, PIDTag
from theogony.mesh.storage.audit import MeshAuditLog
from theogony.mesh.storage.edges import (
    DEFAULT_MAX_OUT_DEGREE,
    EdgeCSR,
    EdgeStore,
    decay_edges_inplace,
    enforce_saturation,
    merge_edge_deltas,
)
from theogony.mesh.storage.nodes import _DEFAULT_VERSION_RETENTION, MeshNodeStore

# ---- S5 stubs -------------------------------------------------------


def stub_consolidation_phase() -> None:
    raise NotImplementedError("Consolidation phase – Step S5")


def stub_split_phase() -> None:
    raise NotImplementedError("Sub-node splits – Step S5")


def stub_pathology_phase() -> None:
    raise NotImplementedError("Pathology surveillance – Step S5")


def stub_therapy_phase() -> None:
    raise NotImplementedError("Staged therapy – Step S5")


def _backfill_relation_pids(edges: list[Edge]) -> int:
    """Give existing relations their Wikidata property, in place.

    The tick already rewrites every edge — load, merge, decay, saturate,
    replace — so annotating them here costs nothing beyond the lookup, and it is
    idempotent: an edge that already carries its P-ID is skipped.

    This normalises rather than asserts. The descriptor is already on the edge;
    the table gives it its authoritative name. Nothing new is claimed about the
    relation, which is why a maintenance pass may do it at all (PHX-1072).

    It runs on every tick rather than once, so that edges written before a
    descriptor entered the table pick it up when the table grows.
    """
    now = datetime.now(UTC)
    filled = 0
    for edge in edges:
        if edge.pids:
            continue
        pid = pid_for(edge.relation_descriptor)
        if pid is None:
            continue
        edge.pids = [PIDTag(pid=pid, confidence=1.0, attached_at=now)]
        filled += 1
    return filled


# ---- Tick result ----------------------------------------------------


@dataclass
class MinimalTickResult:
    edges_before: int
    edges_after: int
    delta_drained: int
    audit_id: str
    new_lance_version: int
    index_status: dict[str, str] = field(default_factory=dict)
    versions_pruned: dict[str, int] = field(default_factory=dict)
    pids_backfilled: int = 0


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
        # Durable delta sidecar: reinforcement written by `mesh ask --hebbian` in one
        # process must survive to be drained by `mesh tick` in another.
        self.edges = EdgeStore(self.db, delta_path=root / "edge_deltas.jsonl")
        self.audit = MeshAuditLog(self.db)

        self._state_path = root / "mesh_state.json"
        # Query-path CSR cache (PHX-1041). Invalidated when EdgeStore mutation
        # generation or pending delta-buffer count changes — see :meth:`rebuild_csr`.
        # (Do not key on Lance list_versions — that is O(version_count) and can
        # take tens of seconds on busy 100k workspaces.)
        self._csr_cache: EdgeCSR | None = None
        self._csr_cache_key: tuple[int, int] | None = None
        # Same cache discipline for edge descriptors (see :meth:`descriptor_index`).
        self._descriptor_cache: dict[tuple[str, str], str | None] | None = None
        self._descriptor_cache_key: int | None = None

    @classmethod
    def open(
        cls,
        root: Path,
        *,
        semantic_dim: int | None = None,
        frame_dim: int | None = None,
    ) -> MeshRuntime:
        """Open an existing workspace or initialise a new one.

        When the workspace already contains ``chunk_nodes`` the vector
        dimensions are read from the Lance schema so callers never need to
        remember them.
        """
        root = root.resolve()
        db = lancedb.connect(str(root / "lance"))
        resp = db.list_tables()
        tables = resp.tables or []
        if "chunk_nodes" in tables:
            chunk = db.open_table("chunk_nodes")
            sem = int(chunk.schema.field("semantic_vector").type.list_size)
            frm = int(chunk.schema.field("frame_vector").type.list_size)
            return cls(root, semantic_dim=sem, frame_dim=frm)
        if "consolidated_nodes" in tables:
            consolidated = db.open_table("consolidated_nodes")
            sem = int(consolidated.schema.field("semantic_vector").type.list_size)
            frm = int(consolidated.schema.field("frame_vector").type.list_size)
            return cls(root, semantic_dim=sem, frame_dim=frm)
        return cls(
            root,
            semantic_dim=semantic_dim or 384,
            frame_dim=frame_dim or 64,
        )

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

    def _csr_cache_fingerprint(self) -> tuple[int, int]:
        return (self.edges.mutation_generation, self.edges.delta.pending())

    def invalidate_csr_cache(self) -> None:
        """Drop the resident CSR (call after out-of-band edge mutations)."""
        self._csr_cache = None
        self._csr_cache_key = None
        self._descriptor_cache = None
        self._descriptor_cache_key = None

    def rebuild_csr(self, *, force: bool = False) -> EdgeCSR:
        """Return the edge CSR, reusing a resident cache when the graph is unchanged.

        Cache key = ``(edge_mutation_generation, delta_pending)``. Set
        ``force=True`` to bypass the cache (tests / Oneiros tick bookkeeping).
        Building uses the columnar Lance path in :meth:`EdgeStore.csr_from_store`
        (PHX-1041). Do not key on Lance ``list_versions`` — that is O(version
        count) and can take tens of seconds on busy 100k workspaces.
        """
        key = self._csr_cache_fingerprint()
        if not force and self._csr_cache is not None and self._csr_cache_key == key:
            return self._csr_cache
        csr = self.edges.csr_from_store()
        self._csr_cache = csr
        self._csr_cache_key = key
        return csr

    def descriptor_index(self, *, force: bool = False) -> dict[tuple[str, str], str | None]:
        """Return relation descriptors for every edge, cached like the CSR.

        Keyed on the edge mutation generation, so it survives across queries and is
        rebuilt only after a write. Retrieval reads it once per query instead of
        issuing a filtered metadata query, which measured ~194 ms *per query* on the
        founding mesh against ~0 ms from this cache.
        """
        key = self.edges.mutation_generation
        if not force and self._descriptor_cache is not None and self._descriptor_cache_key == key:
            return self._descriptor_cache
        index = self.edges.descriptor_index()
        self._descriptor_cache = index
        self._descriptor_cache_key = key
        return index

    # ---- tick -------------------------------------------------------

    def run_minimal_tick(
        self,
        *,
        lam: float = 0.05,
        dt: float = 1.0,
        max_out_degree: int = DEFAULT_MAX_OUT_DEGREE,
        w_max: float = 1.0,
        version_retention: timedelta = _DEFAULT_VERSION_RETENTION,
    ) -> MinimalTickResult:
        """Drain delta buffer -> merge -> decay -> saturation -> Lance rewrite -> audit."""
        before = self.edges.count_rows()
        drained = self.edges.delta.drain()
        base = self.edges.load_all_edges()
        pids_backfilled = _backfill_relation_pids(base)
        merged = merge_edge_deltas(base, drained, w_max=w_max)
        decay_edges_inplace(merged, lam=lam, dt=dt)
        merged = enforce_saturation(merged, max_out_degree=max_out_degree, w_max=w_max)
        self.edges.replace_all_edges(merged)
        self.invalidate_csr_cache()

        # The tick is the substrate's maintenance pass, so index upkeep belongs
        # here rather than on the ingest hot path: a mesh that has grown past the
        # threshold since the last tick gets its indices built once, not per write.
        index_status = self.nodes.ensure_indices()

        # Same reasoning for version history: the substrate writes one node at a
        # time across three tables, so a batch leaves thousands of Lance
        # snapshots and every later append pays for them (83.3 ms vs 2.6 ms on a
        # 2,325-node mesh — PHX-1060). Pruning belongs to the pass that has just
        # committed a consistent state; what the mesh did is in `mesh_audit`.
        versions_pruned = self.nodes.prune_history(retention=version_retention)
        versions_pruned.update(self.edges.prune_history(retention=version_retention))
        # The audit log is the most-written table of them all and was the one
        # no maintenance pass touched: 5,915 versions at 21,219 rows, and
        # reading the ten newest cost 266.6 ms against 2.1 ms pruned (PHX-1062).
        versions_pruned["mesh_audit"] = self.audit.prune_history(retention=version_retention)
        self.invalidate_csr_cache()

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
                "indices": index_status,
                "versions_pruned": versions_pruned,
                "pids_backfilled": pids_backfilled,
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
            index_status=index_status,
            versions_pruned=versions_pruned,
            pids_backfilled=pids_backfilled,
        )
