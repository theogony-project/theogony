"""An arriving agent has no API key, and should not need one (PHX-1111).

Measured from a fresh clone, in a clean environment, with the documented
commands: `theogony ask` stopped before retrieval ran, `theogony mcp` died
before its handshake, and `pantheon_ask` apologised in a successful result —
so the one thing this system does differently, the Constellation, could not be
seen without an OpenAI account. Retrieval never needed a language model. These
tests hold the read side to that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from theogony.agents.factory import build_llm_or_offline
from theogony.agents.llm import StubLLMProvider
from theogony.agents.llm_openai import OpenAILLMProvider
from theogony.config.settings import LLMSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest import read_dump
from theogony.retrieval.synthesize import AnswerSynthesizer, OfflineAnswerSynthesizer
from theogony.retrieval.synthesizer_factory import build_synthesizer
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


def _settings(*, openai_key: str | None = None, **overrides: Any) -> Settings:
    """OpenAI configured — the shipped default — with or without its key."""
    from pydantic import SecretStr

    return Settings(  # type: ignore[call-arg]
        OPENAI_API_KEY=SecretStr(openai_key) if openai_key else None,  # type: ignore[arg-type]
        ANTHROPIC_API_KEY=None,
        GEMINI_API_KEY=None,
        GOOGLE_API_KEY=None,
        llm=LLMSettings(provider="openai", fallback_provider=None),
        **overrides,
    )


def test_without_a_key_the_caller_gets_a_stub_and_the_reason() -> None:
    llm, reason = build_llm_or_offline(_settings())
    assert isinstance(llm, StubLLMProvider)
    assert reason is not None and "OPENAI_API_KEY" in reason


def test_with_a_key_nothing_changes() -> None:
    llm, reason = build_llm_or_offline(_settings(openai_key="sk-test"))
    assert isinstance(llm, OpenAILLMProvider)
    assert reason is None


def test_the_synthesizer_follows_the_llm_it_was_given_not_the_setting() -> None:
    """The setting still says `openai`; what arrived is a stub. Deciding from
    the setting built an LLM synthesizer around a provider that returns ""."""
    settings = _settings()
    assert isinstance(build_synthesizer(settings, StubLLMProvider()), OfflineAnswerSynthesizer)
    real, _ = build_llm_or_offline(_settings(openai_key="sk-test"))
    assert isinstance(build_synthesizer(settings, real), AnswerSynthesizer)


async def _seeded_resources(tmp_path: Path) -> Any:
    from theogony.extraction.audit import ExtractionAuditLog
    from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
    from theogony.mcp.server import McpResources
    from theogony.reporting.writer import RunReportWriter

    settings = _settings()
    store = InMemoryKnowledgeStore()
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])
    llm, reason = build_llm_or_offline(settings)
    audit = ExtractionAuditLog(tmp_path / "audit.sqlite")
    audit.__enter__()
    return McpResources(
        settings=settings,
        audit=audit,
        wd_cache=None,
        embedder=LocalSentenceTransformerEmbedder(
            model_id=settings.embedding.model_id, dim=settings.embedding.dim
        ),
        llm=llm,
        store=store,
        report_writer=RunReportWriter(tmp_path / "reports"),
        llm_unavailable_reason=reason,
    )


@pytest.mark.asyncio
async def test_pantheon_ask_returns_the_whole_constellation_without_a_key(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_ask, tool_status

    res = await _seeded_resources(tmp_path)
    try:
        status = await tool_status(res)
        assert status["llm_available"] is False and status["answer_mode"] == "offline"

        offline = await tool_ask(res, q="What is the Pantheon?", k=6, hops=2)
        assert "error" not in offline
        assert offline["answer_mode"] == "offline"
        assert "nothing here is generated" in offline["answer"]
        assert "hosted instance" not in offline["answer"], "a local install is not a hosted one"
        assert offline["note"]
        assert offline["constellation"]["nodes"], "retrieval needs no language model"
        assert offline["cited_node_ids"]

        # The agent is the language model: it can ask for the structure alone.
        bare = await tool_ask(res, q="What is the Pantheon?", k=6, hops=2, synthesize=False)
        assert bare["answer"] is None and bare["answer_mode"] == "none"
        assert "note" not in bare
        assert [n["id"] for n in bare["constellation"]["nodes"]] == [
            n["id"] for n in offline["constellation"]["nodes"]
        ]
    finally:
        res.audit.__exit__(None, None, None)


def test_the_ask_tool_tells_a_caller_it_works_without_a_key() -> None:
    from theogony.mcp.server import _tool_descriptors

    ask = next(d for d in _tool_descriptors() if d["name"] == "pantheon_ask")
    assert "without any" in ask["description"] and "answer_mode" in ask["description"]
    assert ask["inputSchema"]["properties"]["synthesize"]["default"] is True
