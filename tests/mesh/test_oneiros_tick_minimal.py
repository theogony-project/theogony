"""Minimal Oneiros tick: delta drain, Hebb merge, decay, saturation cap, audit."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge


def test_tick_applies_decay_and_saturation(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    hub = str(ULID())
    for _i in range(5):
        mesh_runtime.edges.append_edge(
            Edge(
                source_id=hub,
                target_id=str(ULID()),
                weight=1.0,
                born_at=now,
                last_fired_at=now,
                decay_tier=0,
            )
        )
    delta_target = str(ULID())
    mesh_runtime.edges.delta.append_hebbian_delta(
        source_id=hub,
        target_id=delta_target,
        weight_delta=0.2,
    )

    res = mesh_runtime.run_minimal_tick(lam=0.01, dt=1.0, max_out_degree=3, w_max=1.0)
    assert res.delta_drained == 1

    loaded = mesh_runtime.edges.load_all_edges()
    hub_edges = [e for e in loaded if str(e.source_id) == hub]
    # Saturation: 5 outbound -> 3
    assert len(hub_edges) == 3
    # Decay (k=2) reduces all
    for e in hub_edges:
        assert e.weight < 1.0

    assert res.audit_id is not None
    assert res.new_lance_version > 0


def test_tick_writes_audit(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    for _ in range(3):
        mesh_runtime.edges.append_edge(
            Edge(
                source_id=str(ULID()),
                target_id=str(ULID()),
                weight=0.5,
                born_at=now,
                last_fired_at=now,
            )
        )
    res = mesh_runtime.run_minimal_tick()
    rows = mesh_runtime.audit.list_recent()
    assert any(r["id"] == res.audit_id for r in rows)
    assert mesh_runtime.last_tick_at() is not None


def test_empty_tick_does_not_error(mesh_runtime: MeshRuntime) -> None:
    res = mesh_runtime.run_minimal_tick()
    assert res.edges_before == 0
    assert res.edges_after == 0
