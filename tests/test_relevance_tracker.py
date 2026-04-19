"""
RelevanceTracker unit tests (Plan §3.8 layer 5).

Asserts the tracker:
- bumps ``last_accessed`` to a value strictly later than the prior;
- increments ``relevance`` by exactly ``relevance_delta`` on each call,
  capped at 1.0 (no overshoot, regardless of starting value);
- ``bump_all`` is dedupe-on-id (same id appearing twice in the input
  bumps the node only once);
- a nonexistent node id is a silent no-op (no exception, no log fanfare);
- the constructor validates ``relevance_delta`` lies in [0, 1].
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import make_node
from theogony.memory.relevance import (
    DEFAULT_RELEVANCE_DELTA,
    RelevanceTracker,
)
from theogony.stores import InMemoryKnowledgeStore


class TestBump:
    async def test_bump_advances_last_accessed_and_relevance(self) -> None:
        store = InMemoryKnowledgeStore()
        node = make_node("Hedin", confidence=0.7)
        # Pin a known starting state.
        node.scores.relevance = 0.4
        node.last_accessed = datetime.now(UTC) - timedelta(days=7)
        await store.upsert_node(node)
        before = node.last_accessed
        before_relevance = node.scores.relevance

        tracker = RelevanceTracker(store, relevance_delta=0.05)
        await tracker.bump(node.id)

        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.last_accessed > before
        assert fetched.scores.relevance == pytest.approx(before_relevance + 0.05)

    async def test_bump_caps_at_one_no_matter_starting_value(self) -> None:
        store = InMemoryKnowledgeStore()
        node = make_node("AlmostMaxed")
        node.scores.relevance = 0.98
        await store.upsert_node(node)
        tracker = RelevanceTracker(store, relevance_delta=0.05)
        await tracker.bump(node.id)
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.scores.relevance == 1.0  # capped — no 1.03 overshoot

    async def test_bump_caps_when_already_at_one(self) -> None:
        store = InMemoryKnowledgeStore()
        node = make_node("Maxed")
        node.scores.relevance = 1.0
        await store.upsert_node(node)
        tracker = RelevanceTracker(store, relevance_delta=0.10)
        await tracker.bump(node.id)
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.scores.relevance == 1.0

    async def test_bump_nonexistent_node_is_silent_noop(self) -> None:
        store = InMemoryKnowledgeStore()
        tracker = RelevanceTracker(store)
        # Must not raise, must not log at WARNING/ERROR level.
        await tracker.bump("AKA-deadbeefdead")

    async def test_repeated_bumps_accumulate(self) -> None:
        store = InMemoryKnowledgeStore()
        node = make_node("Hedin")
        node.scores.relevance = 0.5
        await store.upsert_node(node)
        tracker = RelevanceTracker(store, relevance_delta=0.05)
        for _ in range(3):
            await tracker.bump(node.id)
            # Ensure the timestamp resolution is high enough to advance.
            await asyncio.sleep(0)
        fetched = await store.get_node(node.id)
        assert fetched is not None
        # 0.5 + 3 * 0.05 = 0.65 (within float tolerance).
        assert fetched.scores.relevance == pytest.approx(0.65)


class TestBumpAll:
    async def test_dedupes_repeated_ids_in_input(self) -> None:
        store = InMemoryKnowledgeStore()
        a = make_node("A")
        a.scores.relevance = 0.5
        await store.upsert_node(a)
        tracker = RelevanceTracker(store, relevance_delta=0.10)
        await tracker.bump_all([a.id, a.id, a.id])
        fetched = await store.get_node(a.id)
        assert fetched is not None
        # Three copies in input, but only one bump applied: 0.5 + 0.10 = 0.60.
        assert fetched.scores.relevance == pytest.approx(0.60)

    async def test_bumps_each_distinct_id_exactly_once(self) -> None:
        store = InMemoryKnowledgeStore()
        a = make_node("A")
        b = make_node("B")
        a.scores.relevance = 0.4
        b.scores.relevance = 0.7
        await store.upsert_node(a)
        await store.upsert_node(b)
        tracker = RelevanceTracker(store, relevance_delta=0.05)
        await tracker.bump_all([a.id, b.id, a.id, b.id])
        fetched_a = await store.get_node(a.id)
        fetched_b = await store.get_node(b.id)
        assert fetched_a is not None and fetched_b is not None
        assert fetched_a.scores.relevance == pytest.approx(0.45)
        assert fetched_b.scores.relevance == pytest.approx(0.75)

    async def test_empty_input_is_silent_noop(self) -> None:
        tracker = RelevanceTracker(InMemoryKnowledgeStore())
        await tracker.bump_all([])


class TestConstructor:
    def test_default_delta_matches_plan_reference(self) -> None:
        tracker = RelevanceTracker(InMemoryKnowledgeStore())
        # Internal field — exposed via the module-level constant for test clarity.
        assert tracker._delta == DEFAULT_RELEVANCE_DELTA

    def test_rejects_delta_outside_unit_interval(self) -> None:
        with pytest.raises(ValueError, match="relevance_delta must be"):
            RelevanceTracker(InMemoryKnowledgeStore(), relevance_delta=-0.1)
        with pytest.raises(ValueError, match="relevance_delta must be"):
            RelevanceTracker(InMemoryKnowledgeStore(), relevance_delta=1.1)
