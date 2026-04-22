"""Unit tests for clustering strategies (PHX-0060)."""

from __future__ import annotations

import math

import pytest

from theogony.clustering.hdbscan_strategy import HDBSCANStrategy
from theogony.clustering.kmeans_strategy import KMeansStrategy
from theogony.clustering.protocol import ClusteringStrategy


def test_clustering_strategy_protocol_runtime_checkable() -> None:
    assert isinstance(HDBSCANStrategy(), ClusteringStrategy)
    assert isinstance(KMeansStrategy(n_clusters=3), ClusteringStrategy)


def test_hdbscan_strategy_assigns_obvious_clusters() -> None:
    strat = HDBSCANStrategy(min_cluster_size=3)
    # Three tight blobs on unit sphere (4D for stability).
    emb = _blob([1.0, 0.0, 0.0, 0.0], n=8, noise=0.01)
    emb += _blob([0.0, 1.0, 0.0, 0.0], n=8, noise=0.01)
    emb += _blob([0.0, 0.0, 1.0, 0.0], n=8, noise=0.01)
    ids = [f"n{i}" for i in range(len(emb))]
    r = strat.cluster(ids, emb)
    non_noise = {lbl for lbl in r.assignments.values() if lbl != -1}
    assert len(non_noise) == 3


def test_hdbscan_strategy_marks_outliers_as_noise() -> None:
    strat = HDBSCANStrategy(min_cluster_size=3)
    emb = _blob([1.0, 0.0, 0.0, 0.0], n=5, noise=0.01)
    emb.append([0.0, 0.0, 0.0, 1.0])  # far
    ids = [f"n{i}" for i in range(len(emb))]
    r = strat.cluster(ids, emb)
    assert r.assignments[ids[-1]] == -1


def test_kmeans_strategy_respects_n_clusters() -> None:
    strat = KMeansStrategy(n_clusters=4)
    emb = [[float(i % 4 == j) for j in range(4)] for i in range(20)]
    ids = [f"n{i}" for i in range(20)]
    r = strat.cluster(ids, emb)
    assert len({r.assignments[i] for i in ids}) == 4


def test_clustering_result_centroids_are_unit_normalised() -> None:
    strat = HDBSCANStrategy(min_cluster_size=3)
    emb = _blob([1.0, 0.0, 0.0, 0.0], n=10, noise=0.02)
    ids = [f"n{i}" for i in range(len(emb))]
    r = strat.cluster(ids, emb)
    for _k, c in r.centroids.items():
        n = math.sqrt(sum(x * x for x in c))
        assert n == pytest.approx(1.0, abs=0.05)


def _blob(center: list[float], *, n: int, noise: float) -> list[list[float]]:
    out: list[list[float]] = []
    for _ in range(n):
        v = [c + (noise * (i % 3 - 1)) for i, c in enumerate(center)]
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out
