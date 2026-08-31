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
    in_strength,
    merge_edge_deltas,
)
from theogony.mesh.storage.nodes import (
    _DEFAULT_VERSION_RETENTION,
    DEFAULT_FIRED_RECENT_DECAY,
    MeshNodeStore,
    NodeFiringBuffer,
    merge_node_firings,
)
from theogony.mesh.stratification import WeightClasses, global_weight_classes
from theogony.mesh.typed_edges import build_typed_boosted_csr

# ---- S5 stubs -------------------------------------------------------


def stub_consolidation_phase() -> None:
    """The phase is built; it is deliberately not called from here (PHX-1097).

    `theogony.mesh.runtime.consolidation.run_consolidation` implements it. It is
    not wired into the minimal tick for two reasons, and both are about what the
    tick is: the tick is a synchronous, offline, deterministic maintenance pass
    over edges, and consolidation needs a language model, a network, and money.
    Folding it in would make every tick fail without an API key and would put a
    decision about *what the substrate is* on a schedule nobody chose.

    So it is invoked explicitly — `scripts/mesh_consolidate.py` — and writes its
    own audit record under a different action, so that `tick_count()` keeps
    meaning what every recall figure in this repo is quoted against.
    """
    raise NotImplementedError(
        "Consolidation is not a tick phase — call "
        "theogony.mesh.runtime.consolidation.run_consolidation (PHX-1097)"
    )


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
    firing_passes: int = 0
    nodes_fired: int = 0


# ---- Runtime --------------------------------------------------------


# Without a read-consistency interval, lancedb pins every table handle to the
# version it was opened at. A long-lived reader is then not merely stale — it
# breaks. Reproduced (PHX-1093):
#
#     reader opens                     sees 1 edge
#     writer appends two               writer sees 3, reader still sees 1
#     writer runs prune_history        reader raises
#         LanceError(IO): Not found — the data files it was pinned to are gone
#
# The tick calls `prune_history`, so any process holding a runtime across a tick
# — the Cockpit does — starts throwing rather than serving old answers. A zero
# interval means "check on every operation": measured at 0.10 ms against 0.08 ms
# for `count_rows`, which is not a trade worth thinking about.
_READ_CONSISTENCY = timedelta(0)


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
        self.db = lancedb.connect(str(root / "lance"), read_consistency_interval=_READ_CONSISTENCY)

        self.nodes = MeshNodeStore(self.db, semantic_dim=semantic_dim, frame_dim=frame_dim)
        # Durable sidecar for node firings, same discipline as the edge deltas and
        # for the same reason: a pass recorded by `mesh ask` in one process must
        # survive to be folded in by `mesh tick` in another (PHX-1101).
        self.firings = NodeFiringBuffer(root / "node_firings.jsonl")
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
        self._csr_cache_key: tuple[int, int, int] | None = None
        # Same cache discipline for edge descriptors (see :meth:`descriptor_index`).
        self._descriptor_cache: dict[tuple[str, str], str | None] | None = None
        self._descriptor_cache_key: tuple[int, int, int] | None = None
        # And for the typed-edge re-weighting, which walks every edge position
        # once (see :meth:`typed_boosted_csr`).
        self._typed_csr_cache: EdgeCSR | None = None
        self._typed_csr_cache_key: tuple[tuple[int, int, int], float] | None = None
        # Weight-class boundaries, same discipline again: a node's class is a
        # property of the substrate, so it must not be recomputed per query from
        # whichever candidates the ANN returned (PHX-1091).
        self._weight_classes: WeightClasses | None = None
        self._weight_classes_key: tuple[tuple[int, int, int], int] | None = None

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
        db = lancedb.connect(str(root / "lance"), read_consistency_interval=_READ_CONSISTENCY)
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

    def tick_count(self) -> int:
        """How many Oneiros ticks this mesh has seen.

        Every recall figure in this repo is only comparable at equal tick count.
        A tick costs weight — decay removes ~777 units against ~0.1 returned by
        reinforcement (PHX-1077) — so anything that ticks for an unrelated reason
        (index upkeep, version pruning, P-ID backfill) pays for it in recall. That
        was the mechanism behind an unexplained 68% -> 65%, and PHX-1074 asked for
        this number so the next person comparing two figures can see whether they
        are comparing the same mesh.

        Counted from the audit log rather than a stored counter, so it is right
        for meshes that predate this method. `prune_history` discards Lance
        version snapshots, not rows, so the count survives maintenance — but it is
        a count of *recorded* ticks, and a tick that died before writing its audit
        row is not in it (PHX-1082 made such a tick report itself as failed).
        """
        try:
            rows = (
                self.audit._table.search().where("action = 'mesh_oneiros_minimal_tick'").to_list()
            )
        except Exception:  # noqa: BLE001 - a mesh with no audit table has seen no ticks
            return 0
        return len(rows)

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

    def _csr_cache_fingerprint(self) -> tuple[int, int, int]:
        """What must be equal for a cached CSR to still be the graph.

        The edge table's Lance version is here because the other two are
        **process-local**: `mutation_generation` is an in-process counter that
        starts at zero on every fresh runtime, so a reader could not see a writer
        at all. Measured before this: a second process appended two edges and the
        reader's fingerprint stayed at (0, 0) while the table moved 2 -> 3
        (PHX-1093).

        `.version` is a single property at 0.095 ms, not `list_versions()`, which
        is O(version count) and is what the warning below is about.
        """
        return (
            int(self.edges.edge_table.version),
            self.edges.mutation_generation,
            self.edges.delta.pending(),
        )

    def invalidate_csr_cache(self) -> None:
        """Drop the resident CSR (call after out-of-band edge mutations)."""
        self._csr_cache = None
        self._csr_cache_key = None
        self._descriptor_cache = None
        self._descriptor_cache_key = None
        self._typed_csr_cache = None
        self._typed_csr_cache_key = None
        self._weight_classes = None
        self._weight_classes_key = None

    def rebuild_csr(self, *, force: bool = False) -> EdgeCSR:
        """Return the edge CSR, reusing a resident cache when the graph is unchanged.

        Cache key = ``(edge_table_version, edge_mutation_generation, delta_pending)``. Set
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

        Keyed on the same fingerprint as the CSR, so it survives across queries and
        is rebuilt only after a write. Retrieval reads it once per query instead of
        rebuilding it per query, which costs 290 ms on the founding mesh against
        ~0 ms from this cache (re-measured 2026-08-26; see
        :meth:`EdgeStore.descriptor_index`).

        It used to be keyed on `mutation_generation` alone, which is the
        process-local counter PHX-1093 took off the CSR key for exactly this
        reason — a writer in another process moved the table and a reader here
        never noticed. That mattered less while every write went through a tick in
        the reader's own process. Consolidation is a separate pass in a separate
        process, and the half-stale state it produced is worse than either whole
        one: the CSR refreshes on the Lance version while the descriptors stay
        keyed to the pre-merge node pairs, so the typed-edge boost silently stops
        applying to every rewired edge and the Constellation labels the rest
        wrongly.
        """
        key = self._csr_cache_fingerprint()
        if not force and self._descriptor_cache is not None and self._descriptor_cache_key == key:
            return self._descriptor_cache
        index = self.edges.descriptor_index()
        self._descriptor_cache = index
        self._descriptor_cache_key = key
        return index

    def typed_boosted_csr(self, boost: float, *, force: bool = False) -> EdgeCSR:
        """CSR with P-ID-carrying edges scaled by ``boost``, cached like the CSR.

        Building it walks every edge position to look the descriptor up, which is
        O(E) Python — 94k edges on the founding mesh. Keyed on the CSR fingerprint
        *and* the boost, so a query loop pays it once rather than once per query.
        ``boost=1.0`` short-circuits to the plain CSR: the lever is free while off.
        """
        csr = self.rebuild_csr()
        if boost == 1.0:
            return csr
        key = (self._csr_cache_fingerprint(), float(boost))
        if not force and self._typed_csr_cache is not None and self._typed_csr_cache_key == key:
            return self._typed_csr_cache
        boosted = build_typed_boosted_csr(csr, self.descriptor_index(), boost=boost)
        self._typed_csr_cache = boosted
        self._typed_csr_cache_key = key
        return boosted

    def weight_classes(self, *, force: bool = False) -> WeightClasses:
        """Global weight-class boundaries over the answerable population.

        Answerable means consolidated and not a source anchor. Quantiles over
        *every* CSR node put 1,560 nodes in the micro class of which only 354
        could be hydrated at all — 252 source anchors and 102 unconsolidated
        fragments — and seating those would undo PHX-1042, which removed anchors
        from the answer budget because they carry nothing to read.

        Cached on the CSR fingerprint plus the node count, so it survives across
        queries and is rebuilt after a write. It costs one pass over the
        consolidated table (3,783 of 6,208 nodes on the founding mesh).
        """
        csr = self.rebuild_csr()
        key = (self._csr_cache_fingerprint(), self.nodes.consolidated_count())
        if not force and self._weight_classes is not None and self._weight_classes_key == key:
            return self._weight_classes
        strength = in_strength(csr)
        potentials = [
            float(strength[index])
            for node in self.nodes.iter_consolidated()
            if not node.is_source_anchor
            and (index := csr.id_to_index.get(str(node.id))) is not None
        ]
        classes = global_weight_classes(potentials)
        self._weight_classes = classes
        self._weight_classes_key = key
        return classes

    # ---- tick -------------------------------------------------------

    def run_minimal_tick(
        self,
        *,
        lam: float = 0.05,
        dt: float = 1.0,
        max_out_degree: int = DEFAULT_MAX_OUT_DEGREE,
        w_max: float = 1.0,
        version_retention: timedelta = _DEFAULT_VERSION_RETENTION,
        fired_recent_decay: float = DEFAULT_FIRED_RECENT_DECAY,
    ) -> MinimalTickResult:
        """Drain delta buffer -> merge -> decay -> saturation -> Lance rewrite -> audit."""
        before = self.edges.count_rows()
        drained = self.edges.delta.drain()
        base = self.edges.load_all_edges()
        pids_backfilled = _backfill_relation_pids(base)
        merged = merge_edge_deltas(base, drained, w_max=w_max)
        decay_edges_inplace(merged, lam=lam, dt=dt)
        merged = enforce_saturation(merged, max_out_degree=max_out_degree, w_max=w_max)
        try:
            self.edges.replace_all_edges(merged)
        except Exception:
            # `drain()` already unlinked the durable sidecar, so a failure here
            # would destroy reinforcement that no snapshot holds — the edge tables
            # are versioned by Lance and recoverable, the delta buffer is not.
            # Put the deltas back before the exception leaves this frame
            # (PHX-1082).
            for row in drained:
                self.edges.delta.append_hebbian_delta(
                    source_id=str(row["source_id"]),
                    target_id=str(row["target_id"]),
                    weight_delta=float(row["weight_delta"]),
                    relation_descriptor=row.get("relation_descriptor"),
                )
            raise
        self.invalidate_csr_cache()

        # Fold in what fired since the last tick. This is the node-side dual of
        # the delta drain above, and it runs here for the same reason: reads may
        # not mutate the version they read from (`MESH_IMPLEMENTATION.md` §"What
        # is forbidden"), so the query path records and the tick applies.
        #
        # Before this the counters were 0 on every node of every mesh, and the
        # four mechanisms that read them — tier promotion, tier-modulated decay,
        # Oneiros' replay, RL eligibility — were reading a history nobody kept
        # (PHX-1100, PHX-1101).
        firing_rows = self.firings.drain()
        nodes_fired = 0
        if firing_rows:
            consolidated = list(self.nodes.iter_consolidated(page_size=1024))
            updated, nodes_fired, _ = merge_node_firings(
                consolidated, firing_rows, recent_decay=fired_recent_decay
            )
            try:
                self.nodes.replace_all_consolidated(updated)
            except Exception:
                # `drain()` unlinked the sidecar; put the passes back before the
                # exception leaves this frame, exactly as the edge path does. The
                # node tables are versioned by Lance and recoverable, the sidecar
                # is not (PHX-1082).
                for row in firing_rows:
                    self.firings.append_firing(row.get("node_ids") or [], at=None)
                raise

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
                "firing_passes": len(firing_rows),
                "nodes_fired": nodes_fired,
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
            firing_passes=len(firing_rows),
            nodes_fired=nodes_fired,
        )
