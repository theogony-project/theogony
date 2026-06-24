"""Unit tests for the edge-density scaling sweep (phase-transition harness)."""

from __future__ import annotations

import torch

from theogony.mesh.eval.link_prediction import RANKERS
from theogony.mesh.eval.scaling import density_sweep, run_sweep


def _ring_graph() -> tuple[list[str], list[tuple[str, str, float]], torch.Tensor]:
    node_ids = [str(i) for i in range(6)]
    edges = [(str(i), str((i + 1) % 6), 1.0) for i in range(6)]
    edges += [(str(i), str((i + 2) % 6), 1.0) for i in range(6)]  # 12 directed edges
    sem = torch.eye(6, dtype=torch.float32)
    return node_ids, edges, sem


def test_density_sweep_produces_one_level_per_density() -> None:
    node_ids, edges, sem = _ring_graph()
    levels, test_n = density_sweep(
        node_ids, edges, sem, densities=[0.5, 1.0], test_fraction=0.25, hops=2, seed=0
    )
    assert len(levels) == 2
    assert test_n >= 1
    for level in levels:
        assert {r.ranker for r in level.rankers} == set(RANKERS)


def test_density_sweep_train_edges_grow_with_density() -> None:
    node_ids, edges, sem = _ring_graph()
    levels, _ = density_sweep(
        node_ids, edges, sem, densities=[0.25, 0.5, 1.0], test_fraction=0.25, seed=0
    )
    train_counts = [lvl.train_edges for lvl in levels]
    assert train_counts == sorted(train_counts)
    assert levels[0].mean_out_degree == levels[0].train_edges / len(node_ids)


def test_knn_curve_is_density_independent() -> None:
    # knn ignores edges, and the test set + filter mask are fixed across levels,
    # so its MRR must be identical at every density — the flat reference line.
    node_ids, edges, sem = _ring_graph()
    levels, _ = density_sweep(
        node_ids, edges, sem, densities=[0.25, 1.0], test_fraction=0.25, seed=0
    )

    def knn_mrr(level) -> float:
        return next(r.mrr for r in level.rankers if r.ranker == "knn")

    assert knn_mrr(levels[0]) == knn_mrr(levels[1])


def test_run_sweep_packages_report() -> None:
    node_ids, edges, sem = _ring_graph()
    report = run_sweep(
        run_id="test-run",
        workspace="memory://ring",
        node_ids=node_ids,
        all_edge_rows=edges,
        sem_unit=sem,
        densities=[0.5, 1.0],
        test_fraction=0.25,
        seed=0,
    )
    assert report.run_id == "test-run"
    assert report.node_count == 6
    assert report.total_edges == 12
    assert len(report.levels) == 2
    assert report.timing_s >= 0.0
