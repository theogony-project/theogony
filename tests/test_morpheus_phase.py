"""Tests for :class:`~theogony.memory.morpheus_phase.MorpheusPhase`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from theogony.config.settings import Settings
from theogony.core.model import KnowledgeNode, Layer, NodeType, SourceRef
from theogony.memory.morpheus_phase import MorpheusPhase
from theogony.memory.tick_phase import TickContext
from theogony.stores.memory import InMemoryKnowledgeStore


def _n(label: str, *, emb: list[float]) -> KnowledgeNode:
    ref = SourceRef(source_type="t", identifier="d", location=f"l:{label}")
    return KnowledgeNode(
        label=label,
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=ref,
        embedding=emb,
    )


@pytest.mark.asyncio
async def test_phase_persists_proposals() -> None:
    store = InMemoryKnowledgeStore()
    a = _n("a", emb=[1.0, 0.0, 0.0, 0.0])
    b = _n("b", emb=[0.92, 0.38, 0.0, 0.0])
    await store.upsert_node(a)
    await store.upsert_node(b)
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        run_id="phase-r1",
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await MorpheusPhase().run(ctx)
    edges = await store.get_edges_among([a.id, b.id], min_weight=0.0)
    assert edges


@pytest.mark.asyncio
async def test_phase_writes_extras_with_breakdown() -> None:
    store = InMemoryKnowledgeStore()
    a = _n("a", emb=[1.0, 0.0, 0.0, 0.0])
    b = _n("b", emb=[0.92, 0.38, 0.0, 0.0])
    await store.upsert_node(a)
    await store.upsert_node(b)
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        run_id="phase-r2",
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await MorpheusPhase().run(ctx)
    bag = ctx.extras.get("morpheus")
    assert isinstance(bag, dict)
    assert bag.get("edges_proposed", 0) >= 1


@pytest.mark.asyncio
async def test_phase_handles_empty_candidate_set_silently() -> None:
    store = InMemoryKnowledgeStore()
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        run_id="phase-r3",
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await MorpheusPhase().run(ctx)
    bag = ctx.extras.get("morpheus")
    assert isinstance(bag, dict)
    assert bag.get("edges_proposed", 0) == 0
