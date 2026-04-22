"""Tests for ``ClusterNarrowingRetrievalStrategy``."""

from __future__ import annotations

import pytest

from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.retrieval.strategies.budget import RetrievalBudget
from theogony.retrieval.strategies.cluster_narrowing import (
    ClusterNarrowingRetrievalStrategy,
    _rank_clusters_by_similarity,
)
from theogony.retrieval.strategies.fixed_depth import FixedDepthStrategy
from theogony.stores.memory import InMemoryKnowledgeStore


def _n(label: str, emb: list[float], cid: str | None) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        source_ref=SourceRef(source_type="t", identifier="1"),
        embedding=emb,
        embedding_dim=len(emb),
        node_type=NodeType.CONCEPT,
        cluster_id=cid,
    )


@pytest.mark.asyncio
async def test_cluster_narrowing_falls_back_when_no_clusters_exist() -> None:
    store = InMemoryKnowledgeStore()
    n = _n("a", [1.0, 0.0, 0.0, 0.0], None)
    await store.upsert_node(n)
    strat = ClusterNarrowingRetrievalStrategy(store, top_n_clusters=2)
    inner = FixedDepthStrategy(store)
    budget = RetrievalBudget(max_nodes=5, hops=1)
    a = await inner.retrieve([1.0, 0.0, 0.0, 0.0], budget=budget, layer=None)
    b = await strat.retrieve([1.0, 0.0, 0.0, 0.0], budget=budget, layer=None)
    assert [x.node.id for x in a.scored_nodes] == [x.node.id for x in b.scored_nodes]


@pytest.mark.asyncio
async def test_cluster_narrowing_falls_back_when_top_n_coverage_too_low() -> None:
    store = InMemoryKnowledgeStore()
    await store.upsert_node(_n("only", [1.0, 0.0, 0.0, 0.0], "c1"))
    strat = ClusterNarrowingRetrievalStrategy(store, top_n_clusters=3)
    inner = FixedDepthStrategy(store)
    emb = [1.0, 0.0, 0.0, 0.0]
    budget = RetrievalBudget(max_nodes=10, hops=1)
    a = await inner.retrieve(emb, budget=budget, layer=None)
    b = await strat.retrieve(emb, budget=budget, layer=None)
    assert [x.node.id for x in a.scored_nodes] == [x.node.id for x in b.scored_nodes]


@pytest.mark.asyncio
async def test_cluster_narrowing_filters_to_top_clusters() -> None:
    store = InMemoryKnowledgeStore()
    ca, cb, cc = "cA", "cB", "cC"
    na = _n("a", [1.0, 0.0, 0.0, 0.0], ca)
    nb = _n("b", [0.0, 1.0, 0.0, 0.0], cb)
    nc = _n("c", [0.0, 0.0, 1.0, 0.0], cc)
    await store.batch_upsert_nodes([na, nb, nc])
    for i in range(25):
        await store.upsert_node(_n(f"xa{i}", [1.0, 0.02, 0.0, 0.0], ca))
    for i in range(25):
        await store.upsert_node(_n(f"xb{i}", [0.0, 1.0, 0.02, 0.0], cb))
    for i in range(25):
        await store.upsert_node(_n(f"xc{i}", [0.0, 0.0, 1.0, 0.02], cc))
    strat = ClusterNarrowingRetrievalStrategy(store, top_n_clusters=1)
    q = [1.0, 0.0, 0.0, 0.0]
    r = await strat.retrieve(
        q,
        budget=RetrievalBudget(max_nodes=15, hops=1),
        layer=None,
    )
    summaries = await store.list_clusters()
    top = _rank_clusters_by_similarity(q, summaries)[:1]
    candidate_ids: set[str] = set()
    for s in top:
        async for nid in store.get_cluster_members(s.cluster_id):
            candidate_ids.add(nid)
    assert all(s.node.id in candidate_ids for s in r.scored_nodes)


@pytest.mark.asyncio
async def test_cluster_narrowing_preserves_multi_hop_result_shape() -> None:
    store = InMemoryKnowledgeStore()
    n = _n("solo", [1.0, 0.0, 0.0, 0.0], None)
    await store.upsert_node(n)
    strat = ClusterNarrowingRetrievalStrategy(store)
    r = await strat.retrieve(
        [1.0, 0.0, 0.0, 0.0],
        budget=RetrievalBudget(max_nodes=3, hops=2),
        layer=None,
    )
    assert r.nodes_per_hop is None
    assert r.duplicates_removed >= 0
    assert r.duration_ms >= 0
