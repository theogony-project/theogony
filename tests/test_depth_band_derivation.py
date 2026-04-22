"""Unit tests for :mod:`theogony.memory.depth_band` (PHX-0059 / W4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer, NodeType, SourceRef
from theogony.memory.depth_band import (
    derive_depth_band,
    effective_connectivity,
    step_one_toward_target,
)


def _node(
    *,
    layer: Layer,
    connectivity: float,
    confidence: float = 0.7,
    relevance: float = 0.5,
    freshness: float = 1.0,
    last_accessed: datetime | None = None,
) -> KnowledgeNode:
    ref = SourceRef(source_type="test", identifier="doc-1", location="p1")
    n = KnowledgeNode(
        label="n",
        node_type=NodeType.CONCEPT,
        layer=layer,
        source_ref=ref,
    )
    n.scores.connectivity = connectivity
    n.scores.confidence = confidence
    n.scores.relevance = relevance
    n.scores.freshness = freshness
    if last_accessed is not None:
        n.last_accessed = last_accessed
    return n


def test_derive_band_zero_for_isolated_ephemera() -> None:
    n = _node(layer=Layer.EPHEMERA, connectivity=0.0, confidence=0.5, relevance=0.5)
    assert derive_depth_band(n, edges_for_node=[], idle_days=0.0, pheromone_bonus_weight=0.5) == 0


def test_derive_band_two_for_promotable_ephemera() -> None:
    n = _node(layer=Layer.EPHEMERA, connectivity=0.5, confidence=0.55, relevance=0.55, freshness=1.0)
    assert derive_depth_band(n, edges_for_node=[], idle_days=0.0, pheromone_bonus_weight=0.5) == 2


def test_derive_band_three_for_freshly_promoted_mneme() -> None:
    n = _node(layer=Layer.MNEME, connectivity=0.2, confidence=0.7, relevance=0.5, freshness=1.0)
    assert derive_depth_band(n, edges_for_node=[], idle_days=0.0, pheromone_bonus_weight=0.5) == 3


def test_derive_band_five_for_canonical_mneme() -> None:
    n = _node(layer=Layer.MNEME, connectivity=1.0, confidence=0.95, relevance=0.95, freshness=1.0)
    assert derive_depth_band(n, edges_for_node=[], idle_days=0.0, pheromone_bonus_weight=0.5) == 5


def test_derive_band_drops_to_three_for_idle_low_vitality_mneme() -> None:
    old = datetime.now(UTC)
    n = _node(
        layer=Layer.MNEME,
        connectivity=0.55,
        confidence=0.55,
        relevance=0.55,
        freshness=0.55,
        last_accessed=old,
    )
    assert derive_depth_band(n, edges_for_node=[], idle_days=40.0, pheromone_bonus_weight=0.5) == 3


def test_effective_connectivity_includes_pheromone_bonus() -> None:
    n = _node(layer=Layer.EPHEMERA, connectivity=0.5)
    edges = [
        KnowledgeEdge(source_id="a", target_id="b", relation_type="R", pheromone_delta=0.4),
        KnowledgeEdge(source_id="a", target_id="c", relation_type="R", pheromone_delta=0.0),
    ]
    eff = effective_connectivity(n, edges_for_node=edges, pheromone_bonus_weight=0.5)
    assert eff > 0.5


def test_effective_connectivity_clamped_to_one() -> None:
    n = _node(layer=Layer.EPHEMERA, connectivity=0.95)
    edges = [
        KnowledgeEdge(source_id="a", target_id="b", relation_type="R", pheromone_delta=1.0),
    ]
    eff = effective_connectivity(n, edges_for_node=edges, pheromone_bonus_weight=1.0)
    assert eff == pytest.approx(1.0)


def test_step_one_toward_target() -> None:
    assert step_one_toward_target(2, 5) == 3
    assert step_one_toward_target(3, 0) == 2
    assert step_one_toward_target(2, 2) == 2
