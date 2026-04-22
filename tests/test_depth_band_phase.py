"""Tests for :class:`~theogony.memory.depth_band_phase.DepthBandPhase`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from theogony.config.settings import Settings
from theogony.core.model import KnowledgeNode, Layer, NodeType, SourceRef
from theogony.memory.depth_band import step_one_toward_target
from theogony.memory.depth_band_phase import DepthBandPhase
from theogony.memory.tick_phase import TickContext
from theogony.stores.memory import InMemoryKnowledgeStore


def _n(label: str, *, layer: Layer, band: int, conn: float) -> KnowledgeNode:
    ref = SourceRef(source_type="t", identifier="d", location=f"l:{label}")
    node = KnowledgeNode(label=label, node_type=NodeType.CONCEPT, layer=layer, source_ref=ref)
    node.depth_band = band
    node.scores.connectivity = conn
    return node


@pytest.mark.asyncio
async def test_phase_steps_one_band_at_a_time() -> None:
    store = InMemoryKnowledgeStore()
    n = _n("slow", layer=Layer.EPHEMERA, band=0, conn=0.35)
    await store.upsert_node(n)
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await DepthBandPhase().run(ctx)
    got = await store.get_node(n.id)
    assert got is not None
    assert got.depth_band == 1


@pytest.mark.asyncio
async def test_phase_promotes_when_band_crosses_to_three() -> None:
    store = InMemoryKnowledgeStore()
    n = _n("promo", layer=Layer.EPHEMERA, band=2, conn=1.0)
    n.scores.confidence = 0.95
    n.scores.relevance = 0.95
    n.scores.freshness = 1.0
    await store.upsert_node(n)
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await DepthBandPhase().run(ctx)
    got = await store.get_node(n.id)
    assert got is not None
    assert got.layer == Layer.MNEME
    assert got.depth_band == 3


@pytest.mark.asyncio
async def test_phase_degrades_when_band_crosses_to_two() -> None:
    store = InMemoryKnowledgeStore()
    n = _n("cold", layer=Layer.MNEME, band=3, conn=0.05)
    n.scores.confidence = 0.1
    n.scores.relevance = 0.1
    n.scores.freshness = 0.1
    n.last_accessed = datetime.now(UTC) - timedelta(days=90)
    await store.upsert_node(n)
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await DepthBandPhase().run(ctx)
    got = await store.get_node(n.id)
    assert got is not None
    assert got.layer == Layer.EPHEMERA
    assert got.depth_band == 2


@pytest.mark.asyncio
async def test_phase_writes_distribution_to_extras() -> None:
    store = InMemoryKnowledgeStore()
    await store.upsert_node(_n("a", layer=Layer.EPHEMERA, band=0, conn=0.0))
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await DepthBandPhase().run(ctx)
    bag = ctx.extras.get("depth_band")
    assert isinstance(bag, dict)
    assert "distribution" in bag
    assert isinstance(bag["distribution"], dict)


@pytest.mark.asyncio
async def test_phase_handles_pre_w4_nodes_without_depth_band() -> None:
    store = InMemoryKnowledgeStore()
    ref = SourceRef(source_type="t", identifier="d", location="legacy")
    n = KnowledgeNode(label="legacy", node_type=NodeType.CONCEPT, layer=Layer.EPHEMERA, source_ref=ref)
    n.depth_band = 0
    n.scores.connectivity = 0.0
    await store.upsert_node(n)
    settings = Settings()
    ctx = TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )
    await DepthBandPhase().run(ctx)
    got = await store.get_node(n.id)
    assert got is not None
    assert got.depth_band >= 0


def test_step_one_unit() -> None:
    assert step_one_toward_target(1, 4) == 2
