"""Depth-band derivation for PHX-0059 Phase 1 / W4."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from theogony.core.model import KnowledgeNode, Layer


@runtime_checkable
class PheromoneEdgeLike(Protocol):
    """Minimal edge shape for pheromone-aware connectivity."""

    pheromone_delta: float


def effective_connectivity(
    node: KnowledgeNode,
    *,
    edges_for_node: list[PheromoneEdgeLike],
    pheromone_bonus_weight: float,
) -> float:
    """Connectivity boosted by accumulated pheromone deltas on this node's edges."""
    base = node.scores.connectivity
    if not edges_for_node:
        return base
    pheromone_bonus = sum(max(0.0, e.pheromone_delta) for e in edges_for_node) / len(edges_for_node)
    return min(1.0, base + pheromone_bonus_weight * pheromone_bonus)


def derive_depth_band(
    node: KnowledgeNode,
    *,
    edges_for_node: list[PheromoneEdgeLike],
    idle_days: float,
    pheromone_bonus_weight: float,
) -> int:
    """Return depth_band ∈ [0, 5] from lifecycle signals (target ladder, not smoothed)."""
    conn = effective_connectivity(
        node,
        edges_for_node=edges_for_node,
        pheromone_bonus_weight=pheromone_bonus_weight,
    )
    vit = node.scores.vitality()
    embeddedness = 0.6 * conn + 0.4 * vit

    if node.layer is Layer.EPHEMERA:
        if embeddedness < 0.20:
            return 0
        if embeddedness < 0.45:
            return 1
        if embeddedness < 0.65:
            return 2
        # Saturated promotable EPHEMERA: next stratum is MNEME band 3 (W4 brief).
        return 3

    if idle_days >= 30 and vit < 0.35:
        # Severely cooled + weakly embedded: aim for the EPHEMERA-facing band
        # so DepthBandPhase can step to 2 and trigger ``degrade`` (W4 brief).
        if embeddedness < 0.40:
            return 2
        return 3
    if embeddedness < 0.65:
        return 3
    if embeddedness < 0.85:
        return 4
    return 5


def step_one_toward_target(current: int, target: int) -> int:
    """Move at most one band toward ``target`` per tick."""
    if target > current:
        return current + 1
    if target < current:
        return current - 1
    return current


def resolved_current_band(node: KnowledgeNode, *, layer: Layer) -> int:
    """Clamp stored bands to the legal range for each layer."""
    b = node.depth_band
    if layer is Layer.EPHEMERA:
        return min(max(b, 0), 2)
    return min(max(b, 3), 5)


__all__ = [
    "PheromoneEdgeLike",
    "derive_depth_band",
    "effective_connectivity",
    "resolved_current_band",
    "step_one_toward_target",
]
