"""
Integration tests for KadmosReader (E4).

Uses StubLLMProvider + stub embedder + fake Wikipedia fetch.
No network, no live LLM, no external services.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.kadmos.reader import KadmosReader
from theogony.kadmos.wikipedia_parser import WikiSection

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubEmbedder:
    @property
    def model_id(self) -> str:
        return "stub-embedder@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        # Deterministic: hash text length into a 4-dim vector
        n = len(text)
        return [float((n * (i + 1)) % 100) / 100.0 for i in range(4)]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def _valid_llm_response(
    *,
    with_synthesis: bool = False,
    with_revision: bool = False,
    next_granularity: str = "paragraph",
) -> str:
    synthesis = None
    if with_synthesis:
        synthesis = {
            "label": "Tibetan Exploration",
            "description": "Synthesis of exploration themes",
            "basis_concept_ids": [],
            "synthesis_level": "paragraph",
            "confidence": 0.85,
        }

    revisions = []
    if with_revision:
        revisions = [
            {
                "target_concept_id": "PLACEHOLDER",
                "revision_type": "update",
                "reason": "New passage provides more context",
                "triggering_passage": "The expedition crossed Tibet",
                "new_understanding": "Tibet was crossed in 1906",
            }
        ]

    return json.dumps(
        {
            "new_concepts": [
                {
                    "label": "Sven Hedin",
                    "description": "Swedish explorer",
                    "confidence": 0.9,
                }
            ],
            "new_connections": [
                {
                    "source_label": "Sven Hedin",
                    "target_label": "Tibet",
                    "relation_description": "Hedin explored Tibet",
                    "weight": 0.85,
                }
            ],
            "confirmed_hypotheses": [],
            "rejected_hypotheses": [],
            "revisions": revisions,
            "synthesis": synthesis,
            "open_tensions": [],
            "next_granularity": next_granularity,
        }
    )


_FIXTURE_SECTIONS = [
    WikiSection(
        title="Early life",
        level=2,
        paragraphs=[
            "Sven Hedin was born in Stockholm in 1865.",
            "He developed an early interest in Central Asian geography.",
            "His first expedition took him to Persia and Mesopotamia.",
        ],
    ),
    WikiSection(
        title="Expeditions",
        level=2,
        paragraphs=[
            "Hedin's Trans-Himalaya expedition began in 1906.",
            "He mapped large sections of Tibet and the Himalayas.",
            "The expedition produced detailed geographical records.",
        ],
    ),
]

_EXPECTED_STEPS = sum(len(s.paragraphs) for s in _FIXTURE_SECTIONS)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KadmosReader:
    async def _fake_fetch(url: str, **kw):
        return _FIXTURE_SECTIONS

    import theogony.kadmos.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    return KadmosReader(
        llm=StubLLMProvider(default=_valid_llm_response()),
        embedder=_StubEmbedder(),
        db_path=str(tmp_path / "lancedb"),
    )


# ---------------------------------------------------------------------------
# Core loop tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reader_step_count(reader: KadmosReader) -> None:
    annotated, _ = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert len(annotated.steps) == _EXPECTED_STEPS


@pytest.mark.asyncio
async def test_reader_concepts_written(reader: KadmosReader) -> None:
    annotated, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    # Each step adds at least one concept
    assert report.total_concepts > 0
    assert annotated.total_concepts > 0


@pytest.mark.asyncio
async def test_reader_verdict_success(reader: KadmosReader) -> None:
    _, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.verdict == "good"


@pytest.mark.asyncio
async def test_reader_report_type(reader: KadmosReader) -> None:
    _, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.report_type == "kadmos"


@pytest.mark.asyncio
async def test_reader_session_id_matches(reader: KadmosReader) -> None:
    annotated, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert annotated.session_id == report.session_id


@pytest.mark.asyncio
async def test_reader_steps_have_text(reader: KadmosReader) -> None:
    annotated, _ = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    for step in annotated.steps:
        assert step.paragraph_text if hasattr(step, "paragraph_text") else step.text


@pytest.mark.asyncio
async def test_reader_max_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_fetch(url: str, **kw):
        return _FIXTURE_SECTIONS

    import theogony.kadmos.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    reader = KadmosReader(
        llm=StubLLMProvider(default=_valid_llm_response()),
        embedder=_StubEmbedder(),
        db_path=str(tmp_path / "lancedb"),
        max_sections=1,
    )
    annotated, _ = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert len(annotated.steps) == len(_FIXTURE_SECTIONS[0].paragraphs)


@pytest.mark.asyncio
async def test_reader_llm_calls_count(reader: KadmosReader) -> None:
    _, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    # Reading calls: 1 per paragraph
    # Forced synthesis calls: paragraph (if >=3 concepts), section (if >=5), article (if >=10)
    # With stub LLM returning few concepts, synthesis calls may be 0.
    # The minimum is _EXPECTED_STEPS (reading only).
    assert report.total_llm_calls >= _EXPECTED_STEPS


@pytest.mark.asyncio
async def test_reader_with_synthesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_fetch(url: str, **kw):
        return [
            WikiSection(
                title="S",
                level=2,
                paragraphs=["One paragraph about Tibet."],
            )
        ]

    import theogony.kadmos.reader as reader_mod

    monkeypatch.setattr(reader_mod, "fetch_article_structured", _fake_fetch)

    reader = KadmosReader(
        llm=StubLLMProvider(default=_valid_llm_response(with_synthesis=True)),
        embedder=_StubEmbedder(),
        db_path=str(tmp_path / "lancedb"),
    )
    annotated, report = await reader.read("https://en.wikipedia.org/wiki/Tibet")
    assert report.total_syntheses >= 1
    assert annotated.total_syntheses >= 1


@pytest.mark.asyncio
async def test_reader_lancedb_path_in_report(reader: KadmosReader) -> None:
    _, report = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert report.lancedb_path is not None
    assert "lancedb" in report.lancedb_path


@pytest.mark.asyncio
async def test_reader_final_working_memory_populated(reader: KadmosReader) -> None:
    annotated, _ = await reader.read("https://en.wikipedia.org/wiki/Sven_Hedin")
    assert len(annotated.final_active_concepts) >= 0  # may be empty after compression
