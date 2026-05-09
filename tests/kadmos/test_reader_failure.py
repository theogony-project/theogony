"""
Failure-mode tests for KadmosReader (E4).

Covers:
- All LLM calls return bad JSON → verdict="failed"
- Fetch failure → failed report, no exception
- > 50% failures → verdict="failed"
- 20–50% failures → verdict="partial"
"""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.agents.llm import LLMResult
from theogony.kadmos.reader import KadmosReader
from theogony.kadmos.wikipedia_parser import WikiSection


class _StubEmbedder:
    @property
    def model_id(self) -> str:
        return "stub@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class _BadJsonLLM:
    @property
    def model_id(self) -> str:
        return "bad-json"

    async def complete(self, prompt: str, **kwargs) -> LLMResult:
        return LLMResult(text="BROKEN JSON {{{", latency_ms=0, cost_eur=0.0)

    async def complete_with_web_search_for_research_plan(self, **kwargs):
        raise NotImplementedError


_EMPTY_RESPONSE = (
    '{"new_concepts":[],"new_connections":[],'
    '"confirmed_hypotheses":[],"rejected_hypotheses":[],'
    '"revisions":[],"synthesis":null,'
    '"open_tensions":[],"next_granularity":"paragraph"}'
)

_FIVE_PARAS = [
    WikiSection(
        title="S",
        level=2,
        paragraphs=[
            "Paragraph one.",
            "Paragraph two.",
            "Paragraph three.",
            "Paragraph four.",
            "Paragraph five.",
        ],
    )
]


def _reader_with_llm(llm, tmp_path: Path) -> KadmosReader:
    return KadmosReader(
        llm=llm,
        embedder=_StubEmbedder(),
        db_path=str(tmp_path / "lancedb"),
    )


@pytest.mark.asyncio
async def test_all_bad_json_verdict_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_fetch(url: str, **kw):
        return _FIVE_PARAS

    import theogony.kadmos.reader as rm

    monkeypatch.setattr(rm, "fetch_article_structured", _fake_fetch)

    reader = _reader_with_llm(_BadJsonLLM(), tmp_path)
    _, report = await reader.read("https://en.wikipedia.org/wiki/Tibet")
    assert report.verdict == "failed"
    assert report.status == "failed"


@pytest.mark.asyncio
async def test_all_bad_json_no_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_fetch(url: str, **kw):
        return _FIVE_PARAS

    import theogony.kadmos.reader as rm

    monkeypatch.setattr(rm, "fetch_article_structured", _fake_fetch)

    reader = _reader_with_llm(_BadJsonLLM(), tmp_path)
    result = await reader.read("https://en.wikipedia.org/wiki/Tibet")
    assert isinstance(result, tuple)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_fetch_failure_returns_failed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _bad_fetch(url: str, **kw):
        raise RuntimeError("network error")

    import theogony.kadmos.reader as rm

    monkeypatch.setattr(rm, "fetch_article_structured", _bad_fetch)

    from theogony.agents.llm import StubLLMProvider

    reader = _reader_with_llm(StubLLMProvider(default="{}"), tmp_path)
    _, report = await reader.read("https://en.wikipedia.org/wiki/Tibet")
    assert report.verdict == "failed"
    assert report.total_concepts == 0


@pytest.mark.asyncio
async def test_majority_failures_verdict_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3/5 bad JSON (60%) → verdict='failed'."""
    call_count = 0
    valid = _EMPTY_RESPONSE

    class _MostlyBadLLM:
        @property
        def model_id(self) -> str:
            return "mostly-bad"

        async def complete(self, prompt: str, **kwargs) -> LLMResult:
            nonlocal call_count
            call_count += 1
            text = valid if call_count <= 2 else "BROKEN {"
            return LLMResult(text=text, latency_ms=0, cost_eur=0.0)

        async def complete_with_web_search_for_research_plan(self, **kwargs):
            raise NotImplementedError

    async def _fake_fetch(url: str, **kw):
        return _FIVE_PARAS

    import theogony.kadmos.reader as rm

    monkeypatch.setattr(rm, "fetch_article_structured", _fake_fetch)

    reader = _reader_with_llm(_MostlyBadLLM(), tmp_path)
    _, report = await reader.read("https://en.wikipedia.org/wiki/Tibet")
    assert report.verdict == "failed"


@pytest.mark.asyncio
async def test_minority_failures_verdict_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2/5 bad JSON (40%) → verdict='partial'."""
    call_count = 0
    valid = _EMPTY_RESPONSE

    class _SomeBadLLM:
        @property
        def model_id(self) -> str:
            return "some-bad"

        async def complete(self, prompt: str, **kwargs) -> LLMResult:
            nonlocal call_count
            call_count += 1
            text = valid if call_count <= 3 else "BROKEN {"
            return LLMResult(text=text, latency_ms=0, cost_eur=0.0)

        async def complete_with_web_search_for_research_plan(self, **kwargs):
            raise NotImplementedError

    async def _fake_fetch(url: str, **kw):
        return _FIVE_PARAS

    import theogony.kadmos.reader as rm

    monkeypatch.setattr(rm, "fetch_article_structured", _fake_fetch)

    reader = _reader_with_llm(_SomeBadLLM(), tmp_path)
    _, report = await reader.read("https://en.wikipedia.org/wiki/Tibet")
    assert report.verdict == "partial"


@pytest.mark.asyncio
async def test_merge_revision_with_self_id_does_not_raise(tmp_path: Path) -> None:
    """LLM sometimes emits merge_with_id == target; double-del caused KeyError."""
    from theogony.kadmos.model import ActiveConcept, ReadingState, RevisionRequest
    from theogony.kadmos.reading_state import ReadingStateStore

    db = str(tmp_path / "lancedb_merge_self")
    store = ReadingStateStore(session_id="sess-merge", embedding_dim=4, db_path=db)
    state = ReadingState(session_id="sess-merge")
    cid = "C-selfmergebug"
    concept = ActiveConcept(id=cid, label="Alpha", step_created=0)
    state.active_concepts[cid] = concept
    store.add_concept(concept, [0.1, 0.2, 0.3, 0.4], step=0)

    reader = _reader_with_llm(_BadJsonLLM(), tmp_path)
    rev = RevisionRequest(
        target_concept_id=cid,
        revision_type="merge",
        merge_with_id=cid,
        reason="duplicate",
        triggering_passage="p",
    )
    await reader._apply_revision(rev, state, store, step=1)
    assert cid in state.active_concepts
