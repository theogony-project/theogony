"""Integration tests for Mnemosyne in QueryPipeline (PHX-0071 / W5)."""

from __future__ import annotations

import pytest

from theogony.config.settings import LLMSettings, MnemosyneSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer
from theogony.docs_ingest import read_dump
from theogony.reporting.models import MetaClassificationVerdict
from theogony.retrieval.pipeline import build_pipeline_from_settings
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


async def _all_nodes(store: InMemoryKnowledgeStore) -> list[KnowledgeNode]:
    out: list[KnowledgeNode] = []
    for layer in (Layer.EPHEMERA, Layer.MNEME):
        async for n in store.export_layer(layer):
            out.append(n)
    return out


@pytest.mark.asyncio
async def test_pipeline_attaches_meta_classification_and_marks_self_referential_nodes() -> None:
    settings = Settings(llm=LLMSettings(provider="stub"))
    store = InMemoryKnowledgeStore()
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])

    pipeline = await build_pipeline_from_settings(settings, store)
    q = "How does the OneirosWorker promote nodes between depth bands?"
    result = await pipeline.ask(q, k=6, hops=2, pheromone_mode="ignore")

    assert result.report.meta_classification is not None
    assert result.report.meta_classification.verdict == MetaClassificationVerdict.SELF_REFERENTIAL
    run_id = result.report.run_id
    for cid in result.answer.cited_node_ids:
        node = await store.get_node(cid)
        assert node is not None
        runs = list(node.properties.get("self_referential_in_runs") or [])
        assert run_id in runs


@pytest.mark.asyncio
async def test_pipeline_skips_marking_when_not_self_referential() -> None:
    # Disable Mnemosyne so the stub answer/constellation cannot pick up incidental
    # meta vocabulary from the seed corpus and flip the verdict.
    settings = Settings(
        llm=LLMSettings(provider="stub"),
        mnemosyne=MnemosyneSettings(enabled=False),
    )
    store = InMemoryKnowledgeStore()
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])

    pipeline = await build_pipeline_from_settings(settings, store)
    result = await pipeline.ask("What is the weather in Tibet?", k=6, hops=2, pheromone_mode="ignore")

    assert result.report.meta_classification is not None
    assert result.report.meta_classification.verdict == MetaClassificationVerdict.NOT_SELF_REFERENTIAL
    for cid in result.answer.cited_node_ids:
        node = await store.get_node(cid)
        assert node is not None
        assert not (node.properties.get("self_referential_in_runs") or [])
    for n in await _all_nodes(store):
        assert not (n.properties.get("self_referential_in_runs") or [])
