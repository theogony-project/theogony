"""Tests for :class:`~theogony.memory.pheromone_decay_phase.PheromoneDecayPhase` (W2 / PHX-0057)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from theogony.config.settings import EdgePheromoneSettings, OneirosSettings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.memory.pheromone_decay_phase import PheromoneDecayPhase
from theogony.memory.tick_phase import TickContext
from theogony.stores.memory import InMemoryKnowledgeStore


def _node(nid: str, loc: str) -> KnowledgeNode:
    return KnowledgeNode(
        id=nid,
        label=nid,
        node_type=NodeType.CONCEPT,
        source_ref=SourceRef(source_type="t", identifier="1", location=loc, language="en"),
        embedding=[1.0, 0.0],
        embedding_dim=2,
    )


def _ctx(
    store: InMemoryKnowledgeStore,
    *,
    started_at: datetime,
    edge_cfg: EdgePheromoneSettings | None = None,
) -> TickContext:
    cfg = OneirosSettings()
    if edge_cfg is not None:
        cfg.edge_pheromone = edge_cfg
    return TickContext(
        started_at=started_at,
        perf_started=0.0,
        cfg=cfg,
        store=store,
    )


@pytest.mark.asyncio
async def test_decay_phase_skips_edges_within_horizon() -> None:
    store = InMemoryKnowledgeStore()
    a, b = _node("a", "h1"), _node("b", "h2")
    await store.upsert_node(a)
    await store.upsert_node(b)
    now = datetime(2025, 1, 15, tzinfo=UTC)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="R",
        evidence_span="s",
        pheromone_delta=0.5,
        last_traversed=now - timedelta(days=1),
    )
    await store.upsert_edge(e)
    phase = PheromoneDecayPhase()
    ctx = _ctx(store, started_at=now)
    await phase.run(ctx)
    assert store._edges[e.id].pheromone_delta == pytest.approx(0.5)  # noqa: SLF001
    assert ctx.extras["pheromone_decay"]["edges_decayed"] == 0


@pytest.mark.asyncio
async def test_decay_phase_pulls_aged_delta_toward_zero() -> None:
    store = InMemoryKnowledgeStore()
    a, b = _node("c", "h3"), _node("d", "h4")
    await store.upsert_node(a)
    await store.upsert_node(b)
    now = datetime(2025, 6, 1, tzinfo=UTC)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="R",
        evidence_span="s2",
        pheromone_delta=0.2,
        last_traversed=now - timedelta(days=60),
    )
    await store.upsert_edge(e)
    ctx = _ctx(
        store,
        started_at=now,
        edge_cfg=EdgePheromoneSettings(
            decay_horizon_days=30.0,
            decay_rate=0.05,
            decay_epsilon=0.0001,
        ),
    )
    await PheromoneDecayPhase().run(ctx)
    assert store._edges[e.id].pheromone_delta == pytest.approx(0.19)  # noqa: SLF001


@pytest.mark.asyncio
async def test_decay_phase_snaps_to_zero_below_epsilon() -> None:
    store = InMemoryKnowledgeStore()
    a, b = _node("e", "h5"), _node("f", "h6")
    await store.upsert_node(a)
    await store.upsert_node(b)
    now = datetime(2025, 6, 1, tzinfo=UTC)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="R",
        evidence_span="s3",
        # Eligible for listing (> epsilon); one 50% decay step lands below epsilon.
        pheromone_delta=0.0019,
        last_traversed=now - timedelta(days=90),
    )
    await store.upsert_edge(e)
    ctx = _ctx(
        store,
        started_at=now,
        edge_cfg=EdgePheromoneSettings(
            decay_horizon_days=30.0,
            decay_rate=0.5,
            decay_epsilon=0.001,
        ),
    )
    await PheromoneDecayPhase().run(ctx)
    assert store._edges[e.id].pheromone_delta == pytest.approx(0.0)  # noqa: SLF001


@pytest.mark.asyncio
async def test_decay_phase_does_not_touch_zero_delta_edges() -> None:
    store = InMemoryKnowledgeStore()
    a, b = _node("g", "h7"), _node("h", "h8")
    await store.upsert_node(a)
    await store.upsert_node(b)
    now = datetime(2025, 6, 1, tzinfo=UTC)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="R",
        evidence_span="s4",
        pheromone_delta=0.0,
        last_traversed=now - timedelta(days=90),
    )
    await store.upsert_edge(e)
    ctx = _ctx(store, started_at=now)
    await PheromoneDecayPhase().run(ctx)
    assert store._edges[e.id].pheromone_delta == pytest.approx(0.0)  # noqa: SLF001


@pytest.mark.asyncio
async def test_decay_phase_respects_clamp_on_negative_deltas() -> None:
    store = InMemoryKnowledgeStore()
    a, b = _node("i", "h9"), _node("j", "h10")
    await store.upsert_node(a)
    await store.upsert_node(b)
    now = datetime(2025, 6, 1, tzinfo=UTC)
    e = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="R",
        evidence_span="s5",
        pheromone_delta=-0.5,
        last_traversed=now - timedelta(days=90),
    )
    await store.upsert_edge(e)
    ctx = _ctx(
        store,
        started_at=now,
        edge_cfg=EdgePheromoneSettings(
            decay_horizon_days=30.0, decay_rate=0.1, decay_epsilon=0.0001
        ),
    )
    await PheromoneDecayPhase().run(ctx)
    # Moves toward zero: -0.5 * 0.9 = -0.45
    assert store._edges[e.id].pheromone_delta == pytest.approx(-0.45)  # noqa: SLF001


@pytest.mark.asyncio
async def test_decay_phase_writes_observability_to_ctx_extras() -> None:
    store = InMemoryKnowledgeStore()
    ctx = _ctx(store, started_at=datetime.now(tz=UTC))
    await PheromoneDecayPhase().run(ctx)
    assert "pheromone_decay" in ctx.extras
    payload = ctx.extras["pheromone_decay"]
    assert isinstance(payload, dict)
    assert "edges_decayed" in payload
    assert "horizon_days" in payload
    assert "decay_rate" in payload
