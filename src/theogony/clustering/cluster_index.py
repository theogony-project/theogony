"""Insert-time nearest-centroid cluster assignment (PHX-0060 Phase 1)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from theogony.core.model import ClusterSummary

if TYPE_CHECKING:
    from theogony.core.store import KnowledgeStore


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        return list(v)
    return [x / n for x in v]


def _cosine_best(unit_embedding: list[float], centroids: dict[str, list[float]]) -> str | None:
    """Return ``cluster_id`` with highest cosine similarity to unit ``unit_embedding``."""
    if not centroids:
        return None
    u = unit_embedding
    best_id: str | None = None
    best_score = -2.0
    if len(centroids) > 100:
        ids = list(centroids.keys())
        mat = np.asarray([centroids[i] for i in ids], dtype=np.float64)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms = np.where(norms == 0.0, 1.0, norms)
        mat = mat / norms
        u_arr = np.asarray(u, dtype=np.float64)
        scores = mat @ u_arr
        j = int(np.argmax(scores))
        return ids[j]
    for cid, cvec in centroids.items():
        cv = _unit(cvec)
        score = sum(a * b for a, b in zip(u, cv, strict=True))
        if score > best_score:
            best_score = score
            best_id = cid
    return best_id


class ClusterIndex:
    """Nearest-centroid lookup for rough insert-time ``cluster_id`` assignment."""

    def __init__(self) -> None:
        self._centroids: dict[str, list[float]] = {}
        self._labels: dict[str, str | None] = {}

    async def rebuild_from_store(self, store: KnowledgeStore) -> None:
        self._centroids.clear()
        self._labels.clear()
        for summary in await store.list_clusters():
            self._centroids[summary.cluster_id] = summary.centroid
            self._labels[summary.cluster_id] = summary.cluster_label

    def replace(self, summaries: list[ClusterSummary]) -> None:
        self._centroids = {s.cluster_id: s.centroid for s in summaries}
        self._labels = {s.cluster_id: s.cluster_label for s in summaries}

    def assign(self, embedding: list[float]) -> str | None:
        if not self._centroids:
            return None
        return _cosine_best(_unit(embedding), self._centroids)
