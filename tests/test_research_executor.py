"""W11 — ResearchExecutor."""

from __future__ import annotations

import logging

import pytest

from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.curiosity.research_executor import ResearchExecutor
from theogony.curiosity.trigger import ResearchStep, ResearchStepKind


class _MiniWikidata:
    @property
    def source_type(self) -> str:
        return "wikidata"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        del query, limit
        return [
            SourceCandidate(
                source_type="wikidata",
                identifier="Q154759",
                title="Sven Hedin",
                authors=[],
                languages=["en"],
                url="https://www.wikidata.org/wiki/Q154759",
                download_url="https://www.wikidata.org/wiki/Q154759",
                metadata={"wikidata_description": "explorer", "copyright": False},
            )
        ]

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        body = "stub wikidata\n"
        return RawContent(
            source_type="wikidata",
            identifier=candidate.identifier,
            title=candidate.title,
            language="en",
            content=body,
            content_format="text/plain; charset=utf-8",
            url=candidate.url,
            bytes_acquired=len(body.encode("utf-8")),
            metadata={"copyright": False},
        )

    async def aclose(self) -> None:
        return None


class _MiniGutenberg:
    @property
    def source_type(self) -> str:
        return "gutenberg"

    def supports(self, source_type: str) -> bool:
        return source_type == "gutenberg"

    async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
        del query, limit
        return [
            SourceCandidate(
                source_type="gutenberg",
                identifier="43497",
                title="Trans-Himalaya",
                authors=["Hedin, Sven"],
                languages=["en"],
                download_url="https://example.org/pg43497.txt",
                metadata={"copyright": False, "estimated_bytes": 1200},
            )
        ]

    async def acquire(self, candidate: SourceCandidate) -> object:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_executor_dispatches_wikidata_step_to_wikidata_adapter() -> None:
    step = ResearchStep(
        kind=ResearchStepKind.WIKIDATA_LOOKUP,
        target="Sven Hedin",
        rationale="x",
    )
    ex = ResearchExecutor(wikidata=_MiniWikidata(), gutenberg=_MiniGutenberg())
    rows = await ex.execute_step(step)
    assert len(rows) == 1
    assert "Q154759" in rows[0].candidate_label


@pytest.mark.asyncio
async def test_executor_dispatches_gutenberg_step() -> None:
    step = ResearchStep(
        kind=ResearchStepKind.GUTENBERG_SEARCH,
        target="Hedin Tibet",
        rationale="x",
    )
    ex = ResearchExecutor(wikidata=_MiniWikidata(), gutenberg=_MiniGutenberg())
    rows = await ex.execute_step(step)
    assert len(rows) == 1
    assert "43497" in rows[0].candidate_label


@pytest.mark.asyncio
async def test_executor_returns_empty_for_unwired_kinds_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    step = ResearchStep(
        kind=ResearchStepKind.WIKIPEDIA_FETCH,
        target="Sven Hedin",
        rationale="x",
    )
    ex = ResearchExecutor(wikidata=_MiniWikidata(), gutenberg=_MiniGutenberg())
    rows = await ex.execute_step(step)
    assert rows == []
    assert any("W12" in r.message for r in caplog.records)
