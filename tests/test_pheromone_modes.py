"""Pheromone traversal modes and Slow-Path gate (W2 / PHX-0057)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.memory.edge_pheromone import EdgePheromoneTracker
from theogony.memory.relevance import RelevanceTracker
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.strategies.pheromone import effective_weight
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores.memory import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="9", location=loc, language="en")


def _emb_node(nid: str, label: str, loc: str, emb: list[float]) -> KnowledgeNode:
    return KnowledgeNode(
        id=nid,
        label=label,
        node_type=NodeType.CONCEPT,
        source_ref=_src(loc),
        embedding=emb,
        embedding_dim=len(emb),
    )


def test_follow_uses_observed_weight() -> None:
    e = KnowledgeEdge(
        source_id="a",
        target_id="b",
        relation_type="R",
        evidence_span="x",
        weight=0.5,
        pheromone_delta=0.2,
    )
    assert effective_weight(e, "follow") == pytest.approx(0.7)


def test_ignore_uses_baseline_weight() -> None:
    e = KnowledgeEdge(
        source_id="a",
        target_id="b",
        relation_type="R",
        evidence_span="x",
        weight=0.5,
        pheromone_delta=0.2,
    )
    assert effective_weight(e, "ignore") == pytest.approx(0.5)


def test_invert_uses_baseline_minus_delta() -> None:
    e = KnowledgeEdge(
        source_id="a",
        target_id="b",
        relation_type="R",
        evidence_span="x",
        weight=0.5,
        pheromone_delta=0.6,
    )
    assert effective_weight(e, "invert") == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_invert_returns_different_constellation_after_100_bumps() -> None:
    """PHX-0057 acceptance: invert must surface a sibling path the follow path dominates."""
    store = InMemoryKnowledgeStore()
    emb = [1.0, 0.0, 0.0, 0.0]
    na = _emb_node("AKA-a", "A", "la", emb)
    nb = _emb_node("AKA-b", "B", "lb", [0.95, 0.05, 0.0, 0.0])
    # C is orthogonal to the query: relevance comes almost entirely from the A→B→C walk.
    nc = _emb_node("AKA-c", "C", "lc", [0.0, 1.0, 0.0, 0.0])
    # S has a small query-aligned component but wins once the boosted spine is inverted away.
    ns = _emb_node("AKA-s", "S", "ls", [0.25, 0.97, 0.0, 0.0])
    await store.upsert_node(na)
    await store.upsert_node(nb)
    await store.upsert_node(nc)
    await store.upsert_node(ns)
    e_ab = KnowledgeEdge(
        source_id=na.id,
        target_id=nb.id,
        relation_type="NEXT",
        evidence_span="ab",
        weight=0.9,
    )
    e_bc = KnowledgeEdge(
        source_id=nb.id,
        target_id=nc.id,
        relation_type="NEXT",
        evidence_span="bc",
        weight=0.9,
    )
    e_bs = KnowledgeEdge(
        source_id=nb.id,
        target_id=ns.id,
        relation_type="SIDE",
        evidence_span="bs",
        weight=0.9,
    )
    await store.upsert_edge(e_ab)
    await store.upsert_edge(e_bc)
    await store.upsert_edge(e_bs)

    tracker = EdgePheromoneTracker(store, delta=0.015)
    for _ in range(100):
        await tracker.bump_all([e_bc.id])

    retriever = MultiHopRetriever(store)
    follow_res = await retriever.retrieve(
        emb, k=10, hops=2, min_weight=0.3, pheromone_mode="follow"
    )
    invert_res = await retriever.retrieve(
        emb, k=10, hops=2, min_weight=0.3, pheromone_mode="invert"
    )

    def _scores(res: object) -> dict[str, float]:
        return {sn.node.id: sn.score for sn in res.scored_nodes}

    fd = _scores(follow_res)
    inv = _scores(invert_res)
    assert nc.id in fd and ns.id in fd
    assert nc.id in inv and ns.id in inv
    # Follow: pheromone-boosted spine ranks C above the off-axis sibling.
    assert fd[nc.id] > fd[ns.id]
    # Invert: penalised BC makes the sibling branch relatively stronger than C.
    assert inv[ns.id] > inv[nc.id]


@pytest.mark.asyncio
async def test_query_pipeline_skips_bumps_when_mode_is_not_follow() -> None:
    store = InMemoryKnowledgeStore()
    na = _emb_node("AKA-x", "X", "lx", [1.0, 0.0, 0.0, 0.0])
    nb = _emb_node("AKA-y", "Y", "ly", [0.9, 0.1, 0.0, 0.0])
    await store.upsert_node(na)
    await store.upsert_node(nb)
    await store.upsert_edge(
        KnowledgeEdge(
            source_id=na.id,
            target_id=nb.id,
            relation_type="R",
            evidence_span="xy",
            weight=0.9,
        )
    )
    rel = MagicMock(spec=RelevanceTracker)
    rel.bump_all = AsyncMock()
    eph = MagicMock(spec=EdgePheromoneTracker)
    eph.bump_all = AsyncMock()
    embedder = MagicMock()
    embedder.model_id = "m"
    embedder.dim = 4
    embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])
    pipeline = QueryPipeline(
        embedder=embedder,
        retriever=MultiHopRetriever(store),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(StubLLMProvider(default=f"Hi [{na.id}] [{nb.id}].")),
        relevance=rel,
        settings=Settings(),
        edge_pheromone=eph,
    )
    await pipeline.ask("q", pheromone_mode="invert")
    rel.bump_all.assert_not_called()
    eph.bump_all.assert_not_called()
