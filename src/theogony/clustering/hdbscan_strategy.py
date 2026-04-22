"""HDBSCAN-based clustering (PHX-0060 Phase 1)."""

from __future__ import annotations

import time
from typing import cast

import numpy as np
from sklearn.cluster import HDBSCAN

from theogony.clustering.protocol import ClusteringResult


def _row_normalise(embeddings: list[list[float]]) -> np.ndarray:
    """L2-normalise rows; zero-norm rows stay zero."""
    arr = np.asarray(embeddings, dtype=np.float64)
    if arr.size == 0:
        return arr
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return arr / norms


class HDBSCANStrategy:
    """HDBSCAN on unit-sphere embeddings (Euclidean == cosine)."""

    name = "hdbscan"

    def __init__(
        self,
        *,
        min_cluster_size: int = 5,
        min_samples: int | None = None,
        allow_single_cluster: bool = False,
    ) -> None:
        self._min_cluster_size = min_cluster_size
        self._min_samples = min_samples if min_samples is not None else min_cluster_size
        self._allow_single_cluster = allow_single_cluster

    def cluster(
        self,
        node_ids: list[str],
        embeddings: list[list[float]],
    ) -> ClusteringResult:
        started = time.perf_counter()
        if not node_ids or not embeddings:
            return ClusteringResult(
                assignments={},
                centroids={},
                algorithm=self.name,
                runtime_ms=int((time.perf_counter() - started) * 1000),
            )
        x = _row_normalise(embeddings)
        clusterer = HDBSCAN(
            min_cluster_size=self._min_cluster_size,
            min_samples=self._min_samples,
            metric="euclidean",
            allow_single_cluster=self._allow_single_cluster,
        )
        labels = cast(np.ndarray, clusterer.fit_predict(x))
        assignments = {nid: int(lbl) for nid, lbl in zip(node_ids, labels.tolist(), strict=True)}
        centroids: dict[int, list[float]] = {}
        for local_idx in sorted({lbl for lbl in labels if lbl != -1}):
            mask = labels == local_idx
            members = x[mask]
            if members.shape[0] == 0:
                continue
            mean_v = members.mean(axis=0)
            nrm = float(np.linalg.norm(mean_v))
            if nrm == 0.0:
                continue
            centroids[int(local_idx)] = (mean_v / nrm).tolist()
        runtime_ms = int((time.perf_counter() - started) * 1000)
        return ClusteringResult(
            assignments=assignments,
            centroids=centroids,
            algorithm=self.name,
            runtime_ms=runtime_ms,
        )
