"""Clustering strategy protocol and result shape (PHX-0060 Phase 1 / W1).

Strategies are pure CPU work: no store access, no LLM. The
:class:`~theogony.clustering.recluster_phase.ReclusterPhase` owns
persistence and identity-stability mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ClusteringResult:
    """Output of one :meth:`ClusteringStrategy.cluster` call.

    ``assignments`` maps node_id → local cluster index (int). HDBSCAN
    noise is ``-1``. ``centroids`` maps local index → unit-normalised
    mean embedding (non-noise clusters only).
    """

    assignments: dict[str, int]
    centroids: dict[int, list[float]]
    algorithm: str
    runtime_ms: int


@runtime_checkable
class ClusteringStrategy(Protocol):
    """One concrete clustering strategy."""

    name: str

    def cluster(
        self,
        node_ids: list[str],
        embeddings: list[list[float]],
    ) -> ClusteringResult:
        """Partition ``node_ids`` (parallel to ``embeddings``) into clusters."""
        ...
