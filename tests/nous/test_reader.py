"""
Integration test for NousReader (nous_implementation_brief §5, E3).

Uses InMemoryKnowledgeStore + StubLLMProvider + stub embedder on a minimal
fixture article (2 sections × 3 paragraphs).  No network, no live LLM.

Assertions:
- AnnotatedReading.steps count matches paragraph count
- NousRunReport.nodes_written > 0
- NousRunReport.verdict == "success" (well, "good" per RunReportBase vocabulary)
"""

from __future__ import annotations

import json

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.nous.reader import NousReader
from theogony.nous.wikipedia_parser import WikiSection
from theogony.stores.memory import InMemoryKnowledgeStore

# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _StubEmbedder:
    """Deterministic tiny embedder for tests."""

    @property
    def model_id(self) -> str:
        return "stub-embedder@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [float(i) / max(len(text), 1) for i in range(4)]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def _make_stub_llm_output(
    *,
    concepts: list[dict] | None = None,
    edges: list[dict] | None = None,
    with_synthesis: bool = False,
) -> str:
    """Build a valid JSON response matching READING_STEP_OUTPUT_SCHEMA."""
    synthesis_event = None
    if with_synthesis:
        synthesis_event = {
            "label": "Synthesis Concept",
            "description": "Synthesised from paragraph",
            "basis_node_ids": [],
            "diagonal_edges": [],
            "synthesis_level": "paragraph",
            "confidence": 0.8,
        }

    return json.dumps(
        {
            "new_concepts": concepts
            or [
                {
                    "label": "Sven Hedin",
                    "node_type": "person",
                    "description": "Swedish explorer",
                    "confidence": 0.9,
                }
            ],
            "new_edges": edges or [],
            "chronicle_hits_used": [],
            "synthesis_event": synthesis_event,
            "repair_events": [],
            "resolution_updates": [],
        }
    )


# ---------------------------------------------------------------------------
# Fixture article  (2 sections × 3 paragraphs each = 6 steps)
# ---------------------------------------------------------------------------

_FIXTURE_SECTIONS = [
    WikiSection(
        title="Early life",
        level=2,
        paragraphs=[
            "Sven Hedin was born in Stockholm, Sweden, in 1865.",
            "He showed an early interest in geography and exploration.",
            "As a young man, Hedin travelled extensively in Central Asia.",
        ],
    ),
    WikiSection(
        title="Expeditions",
        level=2,
        paragraphs=[
            "Hedin made four major expeditions to Central Asia between 1885 and 1935.",
            "The Trans-Himalaya expedition was his most famous achievement.",
            "He discovered the sources of several major rivers in Tibet.",
        ],
    ),
]

_EXPECTED_STEPS = sum(len(s.paragraphs) for s in _FIXTURE_SECTIONS)


# ---------------------------------------------------------------------------
# Monkeypatch fetch to avoid HTTP
# ---------------------------------------------------------------------------


@pytest.fixture()
def reader_with_fixture(monkeypatch: pytest.MonkeyPatch) -> NousReader:
    """NousReader wired to fixture sections; no HTTP, no live LLM."""

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIXTURE_SECTIONS

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    store = InMemoryKnowledgeStore()
    llm = StubLLMProvider(default=_make_stub_llm_output())
    embedder = _StubEmbedder()
    return NousReader(store=store, llm=llm, embedder=embedder)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reader_step_count(reader_with_fixture: NousReader) -> None:
    annotated, report = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert len(annotated.steps) == _EXPECTED_STEPS


@pytest.mark.asyncio
async def test_reader_nodes_written(reader_with_fixture: NousReader) -> None:
    _, report = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.nodes_written > 0


@pytest.mark.asyncio
async def test_reader_verdict_success(reader_with_fixture: NousReader) -> None:
    _, report = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.verdict == "good"


@pytest.mark.asyncio
async def test_reader_report_type(reader_with_fixture: NousReader) -> None:
    _, report = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.report_type == "nous"


@pytest.mark.asyncio
async def test_reader_session_id_matches(reader_with_fixture: NousReader) -> None:
    annotated, report = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert annotated.session_id == report.session_id


@pytest.mark.asyncio
async def test_reader_annotated_reading_has_steps(reader_with_fixture: NousReader) -> None:
    annotated, _ = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert len(annotated.steps) > 0
    for step in annotated.steps:
        assert step.paragraph_text


@pytest.mark.asyncio
async def test_reader_chronicle_seeded_false_on_empty_store(
    reader_with_fixture: NousReader,
) -> None:
    annotated, report = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert annotated.chronicle_seeded is False
    assert report.chronicle_seeded is False


@pytest.mark.asyncio
async def test_reader_with_synthesis_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the stub LLM returns a synthesis event, synthesis_events should be > 0."""

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return [
            WikiSection(
                title="Section",
                level=2,
                paragraphs=["First paragraph about Tibet and Central Asia exploration."],
            )
        ]

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    store = InMemoryKnowledgeStore()
    llm = StubLLMProvider(default=_make_stub_llm_output(with_synthesis=True))
    reader = NousReader(store=store, llm=llm, embedder=_StubEmbedder())
    _, report = await reader.read("https://en.wikipedia.org/wiki/Tibet")
    assert report.synthesis_events >= 1


@pytest.mark.asyncio
async def test_reader_max_sections_limits_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_sections=1 must process only the first section's paragraphs."""

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIXTURE_SECTIONS

    import theogony.nous.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    store = InMemoryKnowledgeStore()
    llm = StubLLMProvider(default=_make_stub_llm_output())
    reader = NousReader(store=store, llm=llm, embedder=_StubEmbedder(), max_sections=1)
    annotated, _ = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    # Only first section's 3 paragraphs processed
    assert len(annotated.steps) == len(_FIXTURE_SECTIONS[0].paragraphs)


@pytest.mark.asyncio
async def test_reader_llm_calls_count(reader_with_fixture: NousReader) -> None:
    _, report = await reader_with_fixture.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    # One LLM call per paragraph
    assert report.llm_calls == _EXPECTED_STEPS
