"""Pheromone-aware effective edge weight (PHX-0057 Phase 1 / W2).

Lives under ``core`` so :mod:`theogony.stores.memory` can use it without
importing the retrieval package (which would circularly import stores).
"""

from __future__ import annotations

from typing import Literal

from theogony.core.model import ConstellationEdge, KnowledgeEdge

PheromoneMode = Literal["follow", "ignore", "invert"]


def effective_weight(
    edge: KnowledgeEdge | ConstellationEdge,
    mode: str,
) -> float:
    """Return traversal weight for ``mode`` (baseline ± delta per W2 brief)."""
    delta = getattr(edge, "pheromone_delta", 0.0) or 0.0
    base = edge.weight
    if mode == "follow":
        return max(0.0, min(1.0, base + float(delta)))
    if mode == "ignore":
        return base
    if mode == "invert":
        return max(0.0, min(1.0, base - float(delta)))
    raise ValueError(f"unknown pheromone_mode: {mode!r}")


__all__ = ["PheromoneMode", "effective_weight"]
