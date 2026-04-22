"""Integration: pantheon_self seed + one re-cluster pass + retrieval parity (PHX-0060)."""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.clustering.runner import run_one_recluster_pass
from theogony.config.settings import ClusteringSettings, RetrievalSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType
from theogony.docs_ingest import read_dump
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.strategies.budget import RetrievalBudget
from theogony.retrieval.strategies.cluster_narrowing import ClusterNarrowingRetrievalStrategy
from theogony.retrieval.strategies.fixed_depth import FixedDepthStrategy
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


async def _load_pantheon_seed(store: InMemoryKnowledgeStore) -> tuple[int, int]:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    node_objs = [n for n in nodes if isinstance(n, KnowledgeNode)]
    edge_objs = [e for e in edges if isinstance(e, KnowledgeEdge)]
    await store.batch_upsert_nodes(node_objs)
    await store.batch_upsert_edges(edge_objs)
    return len(node_objs), len(edge_objs)


@pytest.mark.asyncio
async def test_pantheon_self_recluster_and_retrieval_parity(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    node_count, _edge_count = await _load_pantheon_seed(store)

    settings = Settings(
        data_dir=tmp_path,
        clustering=ClusteringSettings(
            algorithm="hdbscan",
            min_cluster_size=4,
            min_corpus_size=20,
        ),
    )
    writer = RunReportWriter(settings.run_reports_dir)
    report = await run_one_recluster_pass(store, settings, writer, force=True)
    assert report is not None

    summaries = await store.list_clusters()
    assert len(summaries) >= 3, f"expected >=3 clusters, got {len(summaries)}"

    largest = max(summaries, key=lambda s: s.member_count)
    assert largest.dominant_node_type == NodeType.CONCEPT

    max_share = largest.member_count / max(node_count, 1)
    assert max_share <= 0.80, f"largest cluster holds {max_share:.0%} of nodes (>80%)"

    embedder = LocalSentenceTransformerEmbedder(
        model_id=settings.embedding.model_id,
        dim=settings.embedding.dim,
    )
    await embedder.embed("warmup")
    query = "What is Pantheon?"
    q_emb = await embedder.embed(query)

    budget = RetrievalBudget(max_nodes=15, hops=2)
    fixed = MultiHopRetriever(store, strategy=FixedDepthStrategy(store))
    narrow = MultiHopRetriever(
        store,
        strategy=ClusterNarrowingRetrievalStrategy(
            store,
            top_n_clusters=8,
            inner_strategy=FixedDepthStrategy(store),
        ),
    )
    rf = await fixed.retrieve(q_emb, k=budget.max_nodes, hops=budget.hops, layer=None)
    rn = await narrow.retrieve(q_emb, k=budget.max_nodes, hops=budget.hops, layer=None)
    top_k = 8
    fixed_ids = [s.node.id for s in rf.scored_nodes[:top_k]]
    narrow_ids = [s.node.id for s in rn.scored_nodes[:top_k]]
    assert fixed_ids == narrow_ids, (
        f"cluster_narrow changed top-{top_k} ordering vs fixed_depth: "
        f"{fixed_ids!r} vs {narrow_ids!r}"
    )

    llm = StubLLMProvider(
        default="Pantheon is the project's knowledge substrate "
        + " ".join(f"[{nid}]" for nid in fixed_ids[:5])
        + "."
    )
    synth = AnswerSynthesizer(llm)
    relevance = RelevanceTracker(store)
    pipe_fixed = QueryPipeline(
        embedder=embedder,
        retriever=fixed,
        assembler=ConstellationAssembler(store),
        synthesizer=synth,
        relevance=relevance,
        settings=settings,
        report_writer=None,
    )
    relevance_n = RelevanceTracker(store)
    pipe_narrow = QueryPipeline(
        embedder=embedder,
        retriever=narrow,
        assembler=ConstellationAssembler(store),
        synthesizer=synth,
        relevance=relevance_n,
        settings=settings,
        report_writer=None,
    )
    ask_k, ask_hops = 15, 2
    out_f = await pipe_fixed.ask(query, k=ask_k, hops=ask_hops)
    out_n = await pipe_narrow.ask(query, k=ask_k, hops=ask_hops)
    assert out_f.answer.cited_node_ids == out_n.answer.cited_node_ids

    # Also exercise the factory path used by API/CLI.
    strat = build_retrieval_strategy(
        store,
        settings.model_copy(
            update={
                "retrieval": RetrievalSettings(
                    strategy="cluster_narrow",
                    cluster_narrow_top_n_clusters=8,
                )
            }
        ),
    )
    via_factory = await MultiHopRetriever(store, strategy=strat).retrieve(
        q_emb, k=budget.max_nodes, hops=budget.hops, layer=None
    )
    assert [s.node.id for s in via_factory.scored_nodes[:top_k]] == fixed_ids
