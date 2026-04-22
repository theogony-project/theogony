"""Pheromone-aware effective edge weight (PHX-0057 Phase 1 / W2).

Implementation is in :mod:`theogony.core.pheromone` to avoid a circular import
(``stores.memory`` → retrieval → … → ``stores.memory``). This module re-exports
for strategy code and backwards compatibility.
"""

from __future__ import annotations

from theogony.core.pheromone import PheromoneMode, effective_weight

__all__ = ["PheromoneMode", "effective_weight"]
