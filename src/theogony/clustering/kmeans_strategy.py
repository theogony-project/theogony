"""K-means clustering fallback for large corpora (PHX-0060 Phase 1)."""

from __future__ import annotations

import time

import numpy as np
from sklearn.cluster import KMeans

from theogony.clustering.protocol import ClusteringResult


def _row_normalise(embeddings: list[list[float]]) -> np.ndarray:
    arr = np.asarray(embeddings, dtype=np.float64)
    if arr.size == 0:
        return arr
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return arr / norms


class KMeansStrategy:
    name = "kmeans"

    def __init__(self, *, n_clusters: int) -> None:
        self._n_clusters = n_clusters

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
        n_clusters = min(self._n_clusters, len(node_ids))
        n_clusters = max(n_clusters, 1)
        km = KMeans(n_clusters=n_clusters, n_init="auto", random_state=0)
        labels = km.fit_predict(x)
        assignments = {nid: int(lbl) for nid, lbl in zip(node_ids, labels.tolist(), strict=True)}
        centroids: dict[int, list[float]] = {}
        centers = np.asarray(km.cluster_centers_, dtype=np.float64)
        for local_idx in range(centers.shape[0]):
            v = centers[local_idx]
            nrm = float(np.linalg.norm(v))
            if nrm == 0.0:
                continue
            centroids[local_idx] = (v / nrm).tolist()
        runtime_ms = int((time.perf_counter() - started) * 1000)
        return ClusteringResult(
            assignments=assignments,
            centroids=centroids,
            algorithm=self.name,
            runtime_ms=runtime_ms,
        )
