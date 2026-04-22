"""Tests for :class:`~theogony.memory.morpheus.MorpheusAssociator`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from theogony.config.settings import MorpheusSettings
from theogony.core.model import EdgeType, KnowledgeEdge, KnowledgeNode, Layer, NodeType, SourceRef
from theogony.memory.morpheus import MorpheusAssociator
from theogony.stores.memory import InMemoryKnowledgeStore


def _ref(loc: str, *, ident: str = "doc-A") -> SourceRef:
    return SourceRef(source_type="test", identifier=ident, location=loc)


def _node(
    label: str,
    loc: str,
    *,
    emb: list[float],
    cluster: str | None = "c1",
    ident: str = "doc-A",
) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=_ref(loc, ident=ident),
        embedding=emb,
        cluster_id=cluster,
    )


@pytest.mark.asyncio
async def test_propose_skips_when_no_low_connectivity_candidates() -> None:
    store = InMemoryKnowledgeStore()
    hub = _node("hub", "l0", emb=[1.0, 0.0, 0.0, 0.0])
    await store.upsert_node(hub)
    for i in range(6):
        s = _node(f"s{i}", f"l{i}", emb=[0.0, 1.0, 0.0, 0.0])
        await store.upsert_node(s)
        await store.upsert_edge(KnowledgeEdge(source_id=hub.id, target_id=s.id, relation_type="R"))
    # ``degree < max_edges`` with ``max_edges=0`` is impossible → empty batch.
    cfg = MorpheusSettings(candidate_isolation_max_edges=0, batch_size=10)
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    assert prop.candidates_considered == 0
    assert prop.edges == []


@pytest.mark.asyncio
async def test_propose_emits_embedding_band_proposals() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", "la", emb=[1.0, 0.0, 0.0, 0.0])
    b = _node("b", "lb", emb=[0.92, 0.38, 0.0, 0.0])
    a.created_at = datetime.now(UTC) - timedelta(days=1)
    b.created_at = datetime.now(UTC)
    await store.upsert_node(a)
    await store.upsert_node(b)
    cfg = MorpheusSettings(
        candidate_isolation_max_edges=5,
        batch_size=10,
        embedding_band_low=0.7,
        embedding_band_high=0.99,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    assert any(e.properties.get("signal") == "embedding" for e in prop.edges)


@pytest.mark.asyncio
async def test_propose_skips_top_n_above_band_high() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", "la", emb=[1.0, 0.0, 0.0, 0.0])
    b = _node("b", "lb", emb=[1.0, 0.0, 0.0, 0.0])
    await store.upsert_node(a)
    await store.upsert_node(b)
    cfg = MorpheusSettings(
        embedding_band_low=0.6,
        embedding_band_high=0.99,
        candidate_isolation_max_edges=5,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    assert all(
        float(e.properties["signal_value"]) <= 0.99 + 1e-6
        for e in prop.edges
        if e.properties.get("signal") == "embedding"
    )


@pytest.mark.asyncio
async def test_propose_emits_cooccurrence_proposals() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", "la", emb=[1.0, 0.0, 0.0, 0.0], ident="shared-doc")
    b = _node("b", "lb", emb=[0.0, 1.0, 0.0, 0.0], ident="shared-doc")
    await store.upsert_node(a)
    await store.upsert_node(b)
    cfg = MorpheusSettings(
        candidate_isolation_max_edges=5,
        embedding_band_low=0.99,
        embedding_band_high=0.995,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    assert any(e.properties.get("signal") == "cooccurrence" for e in prop.edges)


@pytest.mark.asyncio
async def test_propose_dedupes_same_pair_from_two_signals() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", "la", emb=[1.0, 0.0, 0.0, 0.0], ident="docZ")
    b = _node("b", "lb", emb=[0.92, 0.38, 0.0, 0.0], ident="docZ")
    a.created_at = datetime.now(UTC) - timedelta(days=1)
    b.created_at = datetime.now(UTC)
    await store.upsert_node(a)
    await store.upsert_node(b)
    for i in range(6):
        spoke = _node(f"s{i}", f"ls{i}", emb=[0.0, 0.0, 0.1 * i, 1.0], ident="other")
        await store.upsert_node(spoke)
        await store.upsert_edge(
            KnowledgeEdge(source_id=b.id, target_id=spoke.id, relation_type=f"R{i}")
        )
    cfg = MorpheusSettings(
        candidate_isolation_max_edges=5,
        embedding_band_low=0.7,
        embedding_band_high=0.99,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    pairs = [(e.source_id, e.target_id) for e in prop.edges]
    assert pairs.count((a.id, b.id)) + pairs.count((b.id, a.id)) <= 1


@pytest.mark.asyncio
async def test_propose_respects_proposals_per_node_cap() -> None:
    store = InMemoryKnowledgeStore()
    cand = _node("cand", "l0", emb=[1.0, 0.0, 0.0, 0.0])
    await store.upsert_node(cand)
    for i in range(10):
        n = _node(f"n{i}", f"x{i}", emb=[0.9 + i * 0.001, 0.4, 0.0, 0.0])
        await store.upsert_node(n)
    cfg = MorpheusSettings(
        candidate_isolation_max_edges=5,
        proposals_per_node_cap=2,
        embedding_band_low=0.5,
        embedding_band_high=0.99,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    from collections import Counter

    c = Counter((e.source_id, e.target_id) for e in prop.edges if e.source_id == cand.id)
    assert max(c.values(), default=0) <= 2


@pytest.mark.asyncio
async def test_propose_marks_cross_cluster_in_properties() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", "la", emb=[1.0, 0.0, 0.0, 0.0], cluster="c1")
    b = _node("b", "lb", emb=[0.92, 0.38, 0.0, 0.0], cluster="c2")
    await store.upsert_node(a)
    await store.upsert_node(b)
    cfg = MorpheusSettings(
        cluster_scope="within_and_cross",
        candidate_isolation_max_edges=5,
        embedding_band_low=0.7,
        embedding_band_high=0.99,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    cross = [e for e in prop.edges if e.properties.get("cross_cluster") is True]
    assert cross


@pytest.mark.asyncio
async def test_propose_within_only_filters_cross_cluster() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", "la", emb=[1.0, 0.0, 0.0, 0.0], cluster="c1")
    b = _node("b", "lb", emb=[0.92, 0.38, 0.0, 0.0], cluster="c2")
    await store.upsert_node(a)
    await store.upsert_node(b)
    cfg = MorpheusSettings(
        cluster_scope="within_only",
        candidate_isolation_max_edges=5,
        embedding_band_low=0.7,
        embedding_band_high=0.99,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="r1")
    assert not any(e.properties.get("cross_cluster") for e in prop.edges)


@pytest.mark.asyncio
async def test_proposed_edges_have_correct_metadata() -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", "la", emb=[1.0, 0.0, 0.0, 0.0])
    b = _node("b", "lb", emb=[0.92, 0.38, 0.0, 0.0])
    await store.upsert_node(a)
    await store.upsert_node(b)
    cfg = MorpheusSettings(
        candidate_isolation_max_edges=5,
        embedding_band_low=0.7,
        embedding_band_high=0.99,
    )
    prop = await MorpheusAssociator(store, cfg=cfg).propose_associations(run_id="tick-xyz")
    assert prop.edges
    e = prop.edges[0]
    assert e.epistemic_type == EdgeType.INFERENCE
    assert e.confidence == pytest.approx(0.4)
    assert e.properties.get("proposed_by") == "morpheus"
    assert e.properties.get("tick_run_id") == "tick-xyz"
    assert "signal" in e.properties
