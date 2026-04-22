"""Integration tests for pheromone write-back on ``QueryPipeline`` (W2)."""

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
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores.memory import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="42", location=loc, language="en")


@pytest.mark.asyncio
async def test_ask_with_follow_mode_bumps_cited_edges() -> None:
    store = InMemoryKnowledgeStore()
    a = KnowledgeNode(
        label="A",
        node_type=NodeType.PERSON,
        source_ref=_src("l1"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
    )
    b = KnowledgeNode(
        label="B",
        node_type=NodeType.PLACE,
        source_ref=_src("l2"),
        embedding=[0.95, 0.05, 0.0, 0.0],
        embedding_dim=4,
    )
    await store.upsert_node(a)
    await store.upsert_node(b)
    edge = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="VISITED",
        evidence_span="ev",
        weight=0.8,
        pheromone_delta=0.0,
    )
    await store.upsert_edge(edge)
    settings = Settings()
    delta = settings.relevance.edge_pheromone_delta
    embedder = MagicMock()
    embedder.model_id = "m"
    embedder.dim = 4
    embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])
    pipeline = QueryPipeline(
        embedder=embedder,
        retriever=MultiHopRetriever(store),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(
            StubLLMProvider(default=f"Answer [{a.id}] and [{b.id}] here.")
        ),
        relevance=RelevanceTracker(store, relevance_delta=settings.relevance.relevance_delta),
        settings=settings,
        edge_pheromone=EdgePheromoneTracker(store, delta=delta),
    )
    await pipeline.ask("Who?", pheromone_mode="follow")
    e2 = store._edges[edge.id]  # noqa: SLF001
    assert e2.pheromone_delta == pytest.approx(delta)


@pytest.mark.asyncio
async def test_ask_with_ignore_mode_does_not_bump_anything() -> None:
    store = InMemoryKnowledgeStore()
    a = KnowledgeNode(
        label="A2",
        node_type=NodeType.PERSON,
        source_ref=_src("l3"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
    )
    b = KnowledgeNode(
        label="B2",
        node_type=NodeType.PLACE,
        source_ref=_src("l4"),
        embedding=[0.95, 0.05, 0.0, 0.0],
        embedding_dim=4,
    )
    await store.upsert_node(a)
    await store.upsert_node(b)
    edge = KnowledgeEdge(
        source_id=a.id,
        target_id=b.id,
        relation_type="VISITED",
        evidence_span="ev2",
        weight=0.8,
        pheromone_delta=0.1,
    )
    await store.upsert_edge(edge)
    settings = Settings()
    embedder = MagicMock()
    embedder.model_id = "m"
    embedder.dim = 4
    embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])
    pipeline = QueryPipeline(
        embedder=embedder,
        retriever=MultiHopRetriever(store),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(StubLLMProvider(default=f"Text [{a.id}] [{b.id}].")),
        relevance=RelevanceTracker(store, relevance_delta=settings.relevance.relevance_delta),
        settings=settings,
        edge_pheromone=EdgePheromoneTracker(store, delta=settings.relevance.edge_pheromone_delta),
    )
    rel0 = (await store.get_node(a.id)).scores.relevance
    edge0 = store._edges[edge.id].pheromone_delta  # noqa: SLF001
    await pipeline.ask("Q", pheromone_mode="ignore")
    assert store._edges[edge.id].pheromone_delta == pytest.approx(edge0)  # noqa: SLF001
    assert (await store.get_node(a.id)).scores.relevance == pytest.approx(rel0)
