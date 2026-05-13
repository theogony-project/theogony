"""Minimal Oneiros tick: decay, delta merge, saturation, audit."""

from __future__ import annotations

from datetime import UTC, datetime

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge


def test_minimal_tick_decay_saturation_audit(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    hub = "hub"
    for i in range(5):
        mesh_runtime.edges.append_edge(
            Edge(
                source_id=hub,
                target_id=f"t{i}",
                weight=1.0,
                born_at=now,
                last_fired_at=now,
                decay_tier=0,
            )
        )
    mesh_runtime.edges.delta.append_hebbian_delta(
        source_id=hub,
        target_id="t0",
        weight_delta=0.15,
    )
    res = mesh_runtime.run_minimal_tick(
        lam=0.01,
        dt=1.0,
        max_out_degree=3,
        w_max=1.0,
    )
    assert res.delta_drained == 1
    loaded = mesh_runtime.edges.load_edges()
    hub_edges = [e for e in loaded if e.source_id == hub]
    assert len(hub_edges) == 3
    # Decay strictly reduces positive weights for tier-0 edges (k=2).
    assert all(e.weight < 1.0 for e in hub_edges)
    audit_rows = mesh_runtime.audit._table.to_arrow().to_pylist()  # noqa: SLF001 — test introspection
    assert len(audit_rows) >= 1
    assert any(r["action"] == "mesh_oneiros_minimal_tick" for r in audit_rows)
    assert mesh_runtime.last_tick_at() is not None
