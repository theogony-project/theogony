"""
Failure-mode tests for NousReader (nous_implementation_brief §5, E3).

Covers:
- Stub LLM returning parse-invalid JSON for >50% of calls → verdict="failed"
- Fetch failure → verdict="failed", report still written (no exception propagated)
- NousRunReport always returned (never raises)
"""

from __future__ import annotations

import pytest

from theogony.agents.llm import LLMResult, StubLLMProvider
from theogony.nous.reader import NousReader
from theogony.nous.wikipedia_parser import WikiSection
from theogony.stores.memory import InMemoryKnowledgeStore

# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _StubEmbedder:
    @property
    def model_id(self) -> str:
        return "stub-embedder@v1"

    @property
    def dim(self) -> int:
        return 2

    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class _BadJsonLLMProvider:
    """LLM that returns malformed JSON for all calls."""

    @property
    def model_id(self) -> str:
        return "bad-json-stub"

    async def complete(self, prompt: str, **kwargs) -> LLMResult:
        return LLMResult(text="THIS IS NOT JSON { broken", latency_ms=0, cost_eur=0.0)

    async def complete_with_web_search_for_research_plan(self, **kwargs):
        raise NotImplementedError


_FIVE_PARAGRAPHS = [
    WikiSection(
        title="Section",
        level=2,
        paragraphs=[
            "Paragraph one about Tibet and exploration.",
            "Paragraph two about Hedin's travels.",
            "Paragraph three about the Himalayas.",
            "Paragraph four about rivers and geography.",
            "Paragraph five about the expedition results.",
        ],
    )
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_bad_json_gives_failed_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """100% parse failures → verdict='failed' and no exception raised."""

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIVE_PARAGRAPHS

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    store = InMemoryKnowledgeStore()
    reader = NousReader(store=store, llm=_BadJsonLLMProvider(), embedder=_StubEmbedder())
    annotated, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")

    assert report.verdict == "failed"
    assert report.status == "failed"


@pytest.mark.asyncio
async def test_all_bad_json_report_is_returned_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even on 100% failure, read() returns (annotated, report), does not raise."""

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIVE_PARAGRAPHS

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    store = InMemoryKnowledgeStore()
    reader = NousReader(store=store, llm=_BadJsonLLMProvider(), embedder=_StubEmbedder())
    # Must not raise
    result = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert isinstance(result, tuple)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_majority_bad_json_gives_failed_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """3/5 parse failures (60%) → verdict='failed' (> 50% threshold)."""
    call_count = 0
    valid_json = (
        '{"new_concepts": [{"label": "Tibet", "node_type": "place", "confidence": 0.9}],'
        '"new_edges": [], "chronicle_hits_used": [], "synthesis_event": null,'
        '"repair_events": [], "resolution_updates": []}'
    )

    class _MostlyBadLLM:
        @property
        def model_id(self) -> str:
            return "mostly-bad"

        async def complete(self, prompt: str, **kwargs) -> LLMResult:
            nonlocal call_count
            call_count += 1
            text = valid_json if call_count <= 2 else "BROKEN JSON {"
            return LLMResult(text=text, latency_ms=0, cost_eur=0.0)

        async def complete_with_web_search_for_research_plan(self, **kwargs):
            raise NotImplementedError

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIVE_PARAGRAPHS

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    store = InMemoryKnowledgeStore()
    reader = NousReader(store=store, llm=_MostlyBadLLM(), embedder=_StubEmbedder())
    _, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.verdict == "failed"


@pytest.mark.asyncio
async def test_minority_failures_give_partial_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """2/5 parse failures (40%) → verdict='partial' (> 20% but <= 50%)."""
    call_count = 0
    valid_json = (
        '{"new_concepts": [{"label": "Tibet", "node_type": "place", "confidence": 0.9}],'
        '"new_edges": [], "chronicle_hits_used": [], "synthesis_event": null,'
        '"repair_events": [], "resolution_updates": []}'
    )

    class _SomeBadLLM:
        @property
        def model_id(self) -> str:
            return "some-bad"

        async def complete(self, prompt: str, **kwargs) -> LLMResult:
            nonlocal call_count
            call_count += 1
            # Calls 4 and 5 return invalid JSON (2/5 = 40%)
            text = valid_json if call_count <= 3 else "BROKEN {"
            return LLMResult(text=text, latency_ms=0, cost_eur=0.0)

        async def complete_with_web_search_for_research_plan(self, **kwargs):
            raise NotImplementedError

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIVE_PARAGRAPHS

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    store = InMemoryKnowledgeStore()
    reader = NousReader(store=store, llm=_SomeBadLLM(), embedder=_StubEmbedder())
    _, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.verdict == "partial"


@pytest.mark.asyncio
async def test_fetch_failure_returns_failed_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """If fetch_article_structured raises, read() still returns a failed report."""

    async def _bad_fetch(url: str, *, client=None, timeout_s=30.0):
        raise RuntimeError("simulated network error")

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _bad_fetch)

    store = InMemoryKnowledgeStore()
    llm = StubLLMProvider(default="{}")
    reader = NousReader(store=store, llm=llm, embedder=_StubEmbedder())
    annotated, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")

    assert report.verdict == "failed"
    assert report.nodes_written == 0
    assert annotated.steps == []
