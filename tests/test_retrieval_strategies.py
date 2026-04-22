"""
RetrievalStrategy protocol, budgets, and concrete strategies (F3 / PHX-0056 Phase 1).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from theogony.agents.llm import StubLLMProvider
from theogony.config.settings import RetrievalSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.memory.relevance import RelevanceTracker
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.strategies.budget import RetrievalBudget
from theogony.retrieval.strategies.edge_product import EdgeProductBreadthFirstStrategy
from theogony.retrieval.strategies.fixed_depth import FixedDepthStrategy
from theogony.retrieval.strategies.protocol import RetrievalStrategy
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores.memory import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", location=loc, language="en")


async def _populate_two_node_chronik(
    store: InMemoryKnowledgeStore,
) -> tuple[KnowledgeNode, KnowledgeNode]:
    hedin = KnowledgeNode(
        label="Sven Hedin",
        node_type=NodeType.PERSON,
        source_ref=_src("loc:hedin"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="constant-embedder@v1",
    )
    tibet = KnowledgeNode(
        label="Tibet",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:tibet"),
        embedding=[0.9, 0.1, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="constant-embedder@v1",
    )
    edge = KnowledgeEdge(
        source_id=hedin.id,
        target_id=tibet.id,
        relation_type="EXPLORED",
        evidence_span="Sven Hedin explored Tibet.",
        weight=0.5,
    )
    await store.upsert_node(hedin)
    await store.upsert_node(tibet)
    await store.upsert_edge(edge)
    return hedin, tibet


class _ConstEmbedder:
    @property
    def model_id(self) -> str:
        return "constant-embedder@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def test_retrieval_strategy_protocol_runtime_checkable() -> None:
    store = InMemoryKnowledgeStore()
    assert isinstance(FixedDepthStrategy(store), RetrievalStrategy)


def test_retrieval_budget_default_values() -> None:
    b = RetrievalBudget()
    assert b.max_nodes == 10
    assert b.min_edge_weight == 0.3
    assert b.hops == 2
    assert b.min_path_product is None
    assert b.top_n_paths is None
    assert b.pheromone_mode == "follow"
    assert b.token_cap is None
    assert b.wall_clock_ms_cap is None


def test_retrieval_budget_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        RetrievalBudget(max_nodes=5, typo_field=1)  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_fixed_depth_strategy_byte_identical_to_legacy_multi_hop_retriever() -> None:
    store = InMemoryKnowledgeStore()
    await _populate_two_node_chronik(store)
    emb = [1.0, 0.0, 0.0, 0.0]
    k, hops, mw = 10, 2, 0.3
    legacy = await MultiHopRetriever(store).retrieve(emb, k=k, hops=hops, min_weight=mw)
    budget = RetrievalBudget(max_nodes=k, hops=hops, min_edge_weight=mw)
    strat = await FixedDepthStrategy(store).retrieve(emb, budget=budget)
    assert legacy.model_dump() == strat.model_dump()


@pytest.mark.asyncio
async def test_edge_product_strategy_prunes_below_min_path_product() -> None:
    store = InMemoryKnowledgeStore()
    s = KnowledgeNode(
        label="S",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:s"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="m",
    )
    a = KnowledgeNode(
        label="A",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:a"),
        embedding=[],
        embedding_model_id="m",
    )
    b_weak = KnowledgeNode(
        label="Bw",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:bw"),
        embedding=[],
        embedding_model_id="m",
    )
    b_good = KnowledgeNode(
        label="Bg",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:bg"),
        embedding=[],
        embedding_model_id="m",
    )
    await store.upsert_node(s)
    await store.upsert_node(a)
    await store.upsert_node(b_weak)
    await store.upsert_node(b_good)
    await store.upsert_edge(
        KnowledgeEdge(
            source_id=s.id,
            target_id=a.id,
            relation_type="R1",
            evidence_span="s-a",
            weight=0.95,
        )
    )
    await store.upsert_edge(
        KnowledgeEdge(
            source_id=a.id,
            target_id=b_weak.id,
            relation_type="R2",
            evidence_span="a-bw",
            weight=0.1,
        )
    )
    await store.upsert_edge(
        KnowledgeEdge(
            source_id=a.id,
            target_id=b_good.id,
            relation_type="R2",
            evidence_span="a-bg",
            weight=0.9,
        )
    )
    strat = EdgeProductBreadthFirstStrategy(store)
    emb = [1.0, 0.0, 0.0, 0.0]
    budget = RetrievalBudget(
        max_nodes=20,
        hops=2,
        min_edge_weight=0.05,
        min_path_product=0.2,
    )
    result = await strat.retrieve(emb, budget=budget)
    ids = {sn.node.id for sn in result.scored_nodes}
    assert b_good.id in ids
    assert b_weak.id not in ids


@pytest.mark.asyncio
async def test_edge_product_strategy_returns_top_n_when_set() -> None:
    store = InMemoryKnowledgeStore()
    s = KnowledgeNode(
        label="S",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:s2"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="constant@v1",
    )
    await store.upsert_node(s)
    leaves: list[KnowledgeNode] = []
    for i in range(6):
        n = KnowledgeNode(
            label=f"L{i}",
            node_type=NodeType.PLACE,
            source_ref=_src(f"loc:l{i}"),
            embedding=[],
            embedding_model_id="constant@v1",
        )
        leaves.append(n)
        await store.upsert_node(n)
        await store.upsert_edge(
            KnowledgeEdge(
                source_id=s.id,
                target_id=n.id,
                relation_type="LINK",
                evidence_span=f"s-{i}",
                weight=0.99,
            )
        )
    strat = EdgeProductBreadthFirstStrategy(store)
    emb = [1.0, 0.0, 0.0, 0.0]
    budget = RetrievalBudget(
        max_nodes=20,
        hops=1,
        min_edge_weight=0.1,
        top_n_paths=2,
    )
    result = await strat.retrieve(emb, budget=budget)
    leaf_ids = {n.id for n in leaves}
    hit_leaves = leaf_ids & {sn.node.id for sn in result.scored_nodes}
    assert len(hit_leaves) <= 2


@pytest.mark.asyncio
async def test_edge_product_strategy_populates_nodes_per_hop() -> None:
    store = InMemoryKnowledgeStore()
    await _populate_two_node_chronik(store)
    strat = EdgeProductBreadthFirstStrategy(store)
    budget = RetrievalBudget(max_nodes=10, hops=2, min_edge_weight=0.1)
    result = await strat.retrieve([1.0, 0.0, 0.0, 0.0], budget=budget)
    assert result.nodes_per_hop is not None
    assert len(result.nodes_per_hop) == 1 + min(budget.hops, 4)


@pytest.mark.asyncio
async def test_query_pipeline_uses_injected_strategy() -> None:
    store = InMemoryKnowledgeStore()
    await _populate_two_node_chronik(store)
    llm_text = "Answer"
    pipeline = QueryPipeline(
        embedder=_ConstEmbedder(),
        retriever=MultiHopRetriever(store),
        strategy=EdgeProductBreadthFirstStrategy(store),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(StubLLMProvider(default=llm_text)),
        relevance=RelevanceTracker(store),
        settings=Settings(),
    )
    result = await pipeline.ask("Q", k=10, hops=2)
    assert result.report.multi_hop.nodes_per_hop is not None


@pytest.mark.asyncio
async def test_query_pipeline_falls_back_to_settings_strategy_when_no_injection() -> None:
    store = InMemoryKnowledgeStore()
    await _populate_two_node_chronik(store)
    settings = Settings(retrieval=RetrievalSettings(strategy="edge_product"))
    retriever = MultiHopRetriever(
        store, strategy=build_retrieval_strategy(store, settings)
    )
    pipeline = QueryPipeline(
        embedder=_ConstEmbedder(),
        retriever=retriever,
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(StubLLMProvider(default="A")),
        relevance=RelevanceTracker(store),
        settings=settings,
    )
    result = await pipeline.ask("Q", k=10, hops=2)
    assert result.report.multi_hop.nodes_per_hop is not None
