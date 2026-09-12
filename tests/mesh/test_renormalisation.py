"""Homeostatic renormalisation, MESH_SUBSTRATE §6, in three readings (PHX-1106).

What is pinned: the global factor restores the mass and skips inside epsilon;
the per-node modes restore each node's own total and leave nodes without a
target alone; tier softening corrects consolidated edges less; and the tick
records what it did and anchors its set point where it was first switched on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge
from theogony.mesh.storage.edges import (
    node_weight_sums,
    renormalise_edges_inplace,
)

NOW = datetime(2026, 9, 12, tzinfo=UTC)


def _edge(a: ULID, b: ULID, w: float, tier: int = 0) -> Edge:
    return Edge(source_id=a, target_id=b, weight=w, born_at=NOW, last_fired_at=NOW, decay_tier=tier)


def _node() -> ConsolidatedNode:
    return ConsolidatedNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * 8,
        frame_vector=[0.1] * 4,
        description="X — a thing",
    )


def test_global_renormalisation_restores_the_mass_and_keeps_every_ratio() -> None:
    a, b, c = ULID(), ULID(), ULID()
    edges = [_edge(a, b, 0.2), _edge(b, c, 0.6)]
    report = renormalise_edges_inplace(edges, mode="global", target_mass=1.6)
    assert report.factor == pytest.approx(2.0)
    assert [e.weight for e in edges] == pytest.approx([0.4, 1.2])
    assert report.mass_after == pytest.approx(1.6)
    assert report.edges_scaled == 2


def test_global_renormalisation_skips_a_drift_inside_epsilon() -> None:
    a, b = ULID(), ULID()
    edges = [_edge(a, b, 0.995)]
    report = renormalise_edges_inplace(edges, mode="global", target_mass=1.0, epsilon=0.01)
    assert report.factor == 1.0 and report.edges_scaled == 0
    assert edges[0].weight == 0.995


def test_tier_softening_corrects_consolidated_edges_less() -> None:
    a, b, c = ULID(), ULID(), ULID()
    edges = [_edge(a, b, 0.5, tier=0), _edge(b, c, 0.5, tier=2)]
    renormalise_edges_inplace(edges, mode="global", target_mass=2.0, tier_softening=0.5)
    # factor 2 on the tier-0 edge; 1 + (2 - 1) * 0.5^2 = 1.25 on the tier-2 edge
    assert edges[0].weight == pytest.approx(1.0)
    assert edges[1].weight == pytest.approx(0.625)


def test_out_renormalisation_holds_each_source_total_and_leaves_the_rest() -> None:
    a, b, c, d = ULID(), ULID(), ULID(), ULID()
    edges = [_edge(a, b, 0.5), _edge(a, c, 0.5), _edge(d, b, 0.3)]
    targets = {str(a): 2.0}  # d has no target: untouched
    report = renormalise_edges_inplace(edges, mode="out", targets=targets)
    assert node_weight_sums(edges, side="out")[str(a)] == pytest.approx(2.0)
    assert edges[2].weight == 0.3
    assert report.nodes_scaled == 1 and report.edges_scaled == 2


def test_in_renormalisation_is_synaptic_scaling_on_the_target() -> None:
    """A target whose inputs decayed is scaled back up; the source rows that
    point at it therefore hand it more share again."""
    a, b, t = ULID(), ULID(), ULID()
    edges = [_edge(a, t, 0.25), _edge(b, t, 0.25), _edge(a, b, 1.0)]
    renormalise_edges_inplace(edges, mode="in", targets={str(t): 1.0})
    assert [e.weight for e in edges] == pytest.approx([0.5, 0.5, 1.0])


def test_the_modes_refuse_what_they_cannot_do() -> None:
    a, b = ULID(), ULID()
    with pytest.raises(ValueError):
        renormalise_edges_inplace([_edge(a, b, 0.5)], mode="global")
    with pytest.raises(ValueError):
        renormalise_edges_inplace([_edge(a, b, 0.5)], mode="out")
    with pytest.raises(ValueError):
        renormalise_edges_inplace([_edge(a, b, 0.5)], mode="sideways", target_mass=1.0)
    with pytest.raises(ValueError):
        node_weight_sums([_edge(a, b, 0.5)], side="both")


def test_the_tick_anchors_its_set_point_where_it_was_first_switched_on(tmp_path: Path) -> None:
    rt = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=4)
    a, b, c = _node(), _node(), _node()
    for n in (a, b, c):
        rt.nodes.append_consolidated(n)
    for e in (_edge(a.id, b.id, 0.8), _edge(b.id, c.id, 0.8), _edge(c.id, a.id, 0.8)):
        rt.edges.append_edge(e)

    first = rt.run_minimal_tick(lam=0.05, renormalise="global")
    assert first.renormalisation is not None
    # entering mass 2.4 over 3 nodes: the set point is 0.8 weight per node
    assert rt._read_state()["homeostatic_ratio"] == pytest.approx(0.8)
    assert first.renormalisation["set_point"] == pytest.approx(2.4)
    # decay took 0.032 off each edge; the factor brought the mass back
    assert first.renormalisation["mass_after"] == pytest.approx(2.4)
    weights = sorted(e.weight for e in rt.edges.load_all_edges())
    assert weights == pytest.approx([0.8, 0.8, 0.8])

    second = rt.run_minimal_tick(lam=0.05, renormalise="global")
    assert second.renormalisation is not None
    assert second.renormalisation["set_point"] == pytest.approx(2.4)


def test_a_tick_without_renormalisation_records_none(tmp_path: Path) -> None:
    rt = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=4)
    result = rt.run_minimal_tick()
    assert result.renormalisation is None
    with pytest.raises(ValueError):
        rt.run_minimal_tick(renormalise="sideways")
