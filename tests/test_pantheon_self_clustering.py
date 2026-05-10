"""Integration: pantheon_self seed + one re-cluster pass + spreading retrieval (PHX-0060)."""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.clustering.runner import run_one_recluster_pass
from theogony.config.settings import ClusteringSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType
from theogony.docs_ingest import read_dump
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.spreading_activation_retrieval import SpreadingActivationRetriever
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
async def test_pantheon_self_recluster_and_spreading_query(tmp_path: Path) -> None:
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
    retriever = SpreadingActivationRetriever(store, embedder)
    mh = await retriever.retrieve(await embedder.embed(query), k=15, hops=2, min_weight=0.01)
    assert len(mh.scored_nodes) >= 1

    top_ids = [s.node.id for s in mh.scored_nodes[:8]]
    llm = StubLLMProvider(
        default="Pantheon is the project's knowledge substrate "
        + " ".join(f"[{nid}]" for nid in top_ids[:5])
        + "."
    )
    synth = AnswerSynthesizer(llm)
    relevance = RelevanceTracker(store)
    pipeline = QueryPipeline(
        embedder=embedder,
        retriever=retriever,
        assembler=ConstellationAssembler(store),
        synthesizer=synth,
        relevance=relevance,
        settings=settings,
        report_writer=None,
    )
    out = await pipeline.ask(query, k=15, hops=2)
    assert len(out.answer.cited_node_ids) >= 1
