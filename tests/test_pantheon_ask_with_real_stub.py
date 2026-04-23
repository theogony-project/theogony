"""Regression gate: stub LLM settings + real production synthesizer routing (PHX-0070)."""

from __future__ import annotations

import pytest

from theogony.config.settings import LLMSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest import read_dump
from theogony.retrieval.pipeline import build_pipeline_from_settings
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


async def _load_pantheon_self_seed(store: InMemoryKnowledgeStore) -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    node_objs = [n for n in nodes if isinstance(n, KnowledgeNode)]
    edge_objs = [e for e in edges if isinstance(e, KnowledgeEdge)]
    await store.batch_upsert_nodes(node_objs)
    await store.batch_upsert_edges(edge_objs)


@pytest.mark.asyncio
async def test_pantheon_ask_against_pantheon_self_seed_with_stub_provider() -> None:
    """End-to-end: stub LLM provider + bundled pantheon_self seed.

    Uses ``build_llm_from_settings`` → ``build_synthesizer`` →
    :class:`~theogony.retrieval.synthesize.OfflineAnswerSynthesizer`, not a
    hand-wired mock synthesizer.
    """
    settings = Settings(
        llm=LLMSettings(provider="stub"),
    )
    store = InMemoryKnowledgeStore()
    await _load_pantheon_self_seed(store)
    pipeline = await build_pipeline_from_settings(settings, store)

    result = await pipeline.ask("What is the Pantheon?", k=6, hops=2)

    assert result.report.verdict in {"good", "partial"}
    assert result.report.verdict_reasoning != "synthesis raised before completion"
    assert result.answer.text != ""
    assert result.answer.cited_node_ids, "must cite at least one source"
    assert result.answer.cited_node_ids[0] in {n.id for n in result.constellation.nodes}
