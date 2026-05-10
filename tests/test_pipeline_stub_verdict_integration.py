"""QueryPipeline + StubVerdict / RegionDescriptor wiring (W3 / PHX-0058)."""

from __future__ import annotations

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.memory.relevance import RelevanceTracker
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.pipeline import QueryPipeline, QueryResult
from theogony.retrieval.spreading_activation_retrieval import SpreadingActivationRetriever
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores import InMemoryKnowledgeStore


class _ConstEmbedder:
    @property
    def model_id(self) -> str:
        return "const@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="1", location=loc, language="en")


@pytest.mark.asyncio
async def test_query_pipeline_attaches_stub_verdict_to_report() -> None:
    store = InMemoryKnowledgeStore()
    n = KnowledgeNode(
        label="Only",
        node_type=NodeType.CONCEPT,
        source_ref=_src("a"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="const@v1",
        cluster_id="clus-9",
    )
    n.scores.confidence = 0.2
    await store.upsert_node(n)
    llm = StubLLMProvider(default=f"Answer [{n.id}].")
    emb = _ConstEmbedder()
    pipe = QueryPipeline(
        embedder=emb,
        retriever=SpreadingActivationRetriever(store, emb),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(llm),
        relevance=RelevanceTracker(store),
        settings=Settings(),
    )
    result = await pipe.ask("What is Only?", k=3, hops=1)
    assert isinstance(result, QueryResult)
    assert result.report.stub_verdict is not None
    assert result.report.stub_verdict.node_count >= 1


@pytest.mark.asyncio
async def test_query_pipeline_attaches_region_descriptor_with_dominant_cluster_id() -> None:
    store = InMemoryKnowledgeStore()
    a = KnowledgeNode(
        label="A",
        node_type=NodeType.CONCEPT,
        source_ref=_src("la"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="const@v1",
        cluster_id="region-x",
    )
    a.scores.confidence = 0.9
    b = KnowledgeNode(
        label="B",
        node_type=NodeType.CONCEPT,
        source_ref=_src("lb"),
        embedding=[0.95, 0.05, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="const@v1",
        cluster_id="region-x",
    )
    b.scores.confidence = 0.85
    c = KnowledgeNode(
        label="C",
        node_type=NodeType.PLACE,
        source_ref=_src("lc"),
        embedding=[0.9, 0.1, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="const@v1",
        cluster_id="other",
    )
    c.scores.confidence = 0.8
    await store.upsert_node(a)
    await store.upsert_node(b)
    await store.upsert_node(c)
    await store.upsert_edge(
        KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="R", evidence_span="e")
    )
    llm = StubLLMProvider(default=f"See [{a.id}] [{b.id}] [{c.id}].")
    emb = _ConstEmbedder()
    pipe = QueryPipeline(
        embedder=emb,
        retriever=SpreadingActivationRetriever(store, emb),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(llm),
        relevance=RelevanceTracker(store),
        settings=Settings(),
    )
    result = await pipe.ask("clustered?", k=5, hops=2)
    desc = result.report.region_descriptor
    assert desc is not None
    assert desc.dominant_cluster_id == "region-x"
