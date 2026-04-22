"""Unit tests for :class:`~theogony.memory.edge_pheromone.EdgePheromoneTracker` (W2 / PHX-0057)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.memory.edge_pheromone import (
    DEFAULT_EDGE_PHEROMONE_DELTA,
    EdgePheromoneTracker,
)
from theogony.stores.memory import InMemoryKnowledgeStore


def _node(label: str, loc: str) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=NodeType.CONCEPT,
        source_ref=SourceRef(source_type="t", identifier="1", location=loc, language="en"),
        embedding=[1.0, 0.0, 0.0],
        embedding_dim=3,
    )


@pytest.mark.asyncio
async def test_bump_all_dedupes_within_call() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("A", "la")
    b = _node("B", "lb")
    await store.upsert_node(a)
    await store.upsert_node(b)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="REL",
        evidence_span="x",
    )
    await store.upsert_edge(e)
    tracker = EdgePheromoneTracker(store, delta=0.01)
    await tracker.bump_all([e.id, e.id, e.id])
    edge = await store.get_edges_among([a.id, b.id])
    assert len(edge) == 1
    assert edge[0].pheromone_delta == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_bump_all_clamps_to_one() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("A", "lc")
    b = _node("B", "ld")
    await store.upsert_node(a)
    await store.upsert_node(b)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="REL",
        evidence_span="y",
        pheromone_delta=0.5,
    )
    await store.upsert_edge(e)
    tracker = EdgePheromoneTracker(store, delta=0.6)
    await tracker.bump_all([e.id])
    refreshed = store._edges[e.id]  # noqa: SLF001 — test reads internal map
    assert refreshed.pheromone_delta == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_bump_all_silent_no_op_on_unknown_edge_id() -> None:
    store = InMemoryKnowledgeStore()
    tracker = EdgePheromoneTracker(store)
    await tracker.bump_all(["EDGE-no-such-id"])


@pytest.mark.asyncio
async def test_bump_all_stamps_last_traversed_to_now() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("A", "le")
    b = _node("B", "lf")
    await store.upsert_node(a)
    await store.upsert_node(b)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="REL",
        evidence_span="z",
    )
    await store.upsert_edge(e)
    fixed = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    with patch("theogony.memory.edge_pheromone.datetime") as dt_mod:
        dt_mod.now.return_value = fixed
        dt_mod.UTC = UTC
        tracker = EdgePheromoneTracker(store)
        await tracker.bump_all([e.id])
    again = store._edges[e.id]  # noqa: SLF001
    assert again.last_traversed == fixed


def test_default_delta_matches_settings() -> None:
    assert Settings().relevance.edge_pheromone_delta == DEFAULT_EDGE_PHEROMONE_DELTA
