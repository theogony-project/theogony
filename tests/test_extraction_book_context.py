"""Unit tests for :class:`BookContextExtractor` (Plan §3.4 Stage-4 prerequisite)."""

from __future__ import annotations

import json

import pytest

from theogony.acquisition.base import RawContent
from theogony.agents.llm import StubLLMProvider
from theogony.extraction.book_context import (
    DEFAULT_MAX_OPENING_CHARS,
    BookContext,
    BookContextExtractor,
)
from theogony.extraction.sentence import Sentence

# ---------------------------------------------------------------- fixtures


def _hedin_raw() -> RawContent:
    """Minimal :class:`RawContent` standing in for Trans-Himalaya Vol. I."""
    return RawContent(
        source_type="gutenberg",
        identifier="43497",
        title="Trans-Himalaya: Discoveries and Adventurers in Tibet, Vol. 1",
        authors=["Hedin, Sven Anders"],
        language="en",
        content="(opening text not used directly here — sentences are passed in)",
        content_format="text/plain; charset=utf-8",
        bytes_acquired=100,
    )


def _sentence(idx: int, text: str, start: int = 0) -> Sentence:
    return Sentence(index=idx, text=text, start_char=start, end_char=start + len(text))


def _hedin_opening() -> list[Sentence]:
    """A handful of plausible opening sentences for prompt-shape tests."""
    parts = [
        "I left Stockholm in October 1905 to begin my third great journey to Tibet. ",
        (
            "The aim was to chart the high plateau between the "
            "Himalayas and the Trans-Himalaya range. "
        ),
        (
            "My companions were drawn from many nations: a Buryat "
            "lama, two Cossacks, a Pathan caravan-bashi. "
        ),
        "Beyond the passes lay regions no European had ever surveyed. ",
        "We crossed into Indian territory in early 1906. ",
    ]
    out: list[Sentence] = []
    cursor = 0
    for i, text in enumerate(parts):
        out.append(_sentence(i, text, start=cursor))
        cursor += len(text)
    return out


def _scripted_response(
    *,
    time_period: str | None = "1905-1908",
    places: list[str] | None = None,
    people: list[str] | None = None,
    summary: str = "Sven Hedin's third Trans-Himalaya expedition.",
) -> str:
    return json.dumps(
        {
            "time_period": time_period,
            "places": places if places is not None else ["Tibet", "India"],
            "people_descriptors": people if people is not None else ["Swedish geographer"],
            "summary": summary,
        }
    )


# ---------------------------------------------------------------- model tests


class TestBookContextModel:
    def test_default_constructs_empty(self) -> None:
        ctx = BookContext()
        assert ctx.time_period is None
        assert ctx.places == []
        assert ctx.people_descriptors == []
        assert ctx.summary == ""
        assert ctx.derived_from_book is None
        assert ctx.derived_from_model_id == ""

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            BookContext(time_period="2020", bogus="x")  # type: ignore[call-arg]

    def test_max_lengths_enforced(self) -> None:
        # places and people_descriptors capped at 20.
        with pytest.raises(ValueError):
            BookContext(places=[f"P{i}" for i in range(21)])
        with pytest.raises(ValueError):
            BookContext(people_descriptors=[f"D{i}" for i in range(21)])
        with pytest.raises(ValueError):
            BookContext(summary="x" * 1001)


class TestPromptBlock:
    def test_full_block_renders_all_fields(self) -> None:
        ctx = BookContext(
            time_period="1905-1908",
            places=["Tibet", "India"],
            people_descriptors=["Swedish geographer", "Tibetan monks"],
            summary="An expedition narrative.",
        )
        block = ctx.to_prompt_block()
        assert "Book context:" in block
        assert "1905-1908" in block
        assert "Tibet, India" in block
        assert "Swedish geographer, Tibetan monks" in block
        assert "An expedition narrative." in block

    def test_empty_block_explicit(self) -> None:
        # Empty context produces an explicit "(none established)" line
        # rather than a confusing dangling header.
        block = BookContext().to_prompt_block()
        assert block == "Book context: (none established by the opening pages.)"

    def test_partial_block_omits_missing_fields(self) -> None:
        ctx = BookContext(places=["Tibet"])
        block = ctx.to_prompt_block()
        assert "Tibet" in block
        assert "Time period" not in block
        assert "Central people" not in block


# ---------------------------------------------------------------- extractor


class TestExtractor:
    async def test_returns_parsed_book_context(self) -> None:
        llm = StubLLMProvider(default=_scripted_response())
        extractor = BookContextExtractor(llm=llm)

        ctx = await extractor.extract(
            raw_content=_hedin_raw(),
            opening_sentences=_hedin_opening(),
        )

        assert ctx.time_period == "1905-1908"
        assert ctx.places == ["Tibet", "India"]
        assert ctx.people_descriptors == ["Swedish geographer"]
        assert ctx.summary == "Sven Hedin's third Trans-Himalaya expedition."
        assert ctx.derived_from_book == "gutenberg:43497"
        assert ctx.derived_from_model_id == "stub-llm"

    async def test_passes_metadata_into_prompt(self) -> None:
        llm = StubLLMProvider(default=_scripted_response())
        extractor = BookContextExtractor(llm=llm)
        await extractor.extract(
            raw_content=_hedin_raw(),
            opening_sentences=_hedin_opening(),
        )

        assert len(llm.calls) == 1
        prompt = llm.calls[0]["prompt"]
        assert "Trans-Himalaya" in prompt
        assert "Hedin, Sven Anders" in prompt
        assert "Language: en" in prompt
        # Opening text is concatenated into the prompt.
        assert "Stockholm" in prompt
        assert "Tibet" in prompt

    async def test_truncates_opening_to_max_chars(self) -> None:
        llm = StubLLMProvider(default=_scripted_response())
        extractor = BookContextExtractor(llm=llm, max_opening_chars=200)

        # Opening totals ~500 chars; should stop on a sentence boundary
        # without exceeding 200.
        sentences = _hedin_opening()
        await extractor.extract(raw_content=_hedin_raw(), opening_sentences=sentences)

        prompt = llm.calls[0]["prompt"]
        # The prompt body includes the opening between "---" markers.
        opening_block = prompt.split("---")[1].strip()
        assert len(opening_block) <= 200

    async def test_supplies_json_schema_to_provider(self) -> None:
        llm = StubLLMProvider(default=_scripted_response())
        extractor = BookContextExtractor(llm=llm)
        await extractor.extract(raw_content=_hedin_raw(), opening_sentences=_hedin_opening())

        # The resolver downstream depends on the LLM honouring the schema —
        # so the extractor must always pass it.
        schema = llm.calls[0]["json_schema"]
        assert schema is not None
        assert schema["type"] == "object"
        assert set(schema["required"]) == {
            "time_period",
            "places",
            "people_descriptors",
            "summary",
        }

    async def test_temperature_zero_for_determinism(self) -> None:
        llm = StubLLMProvider(default=_scripted_response())
        extractor = BookContextExtractor(llm=llm)
        await extractor.extract(raw_content=_hedin_raw(), opening_sentences=_hedin_opening())
        assert llm.calls[0]["temperature"] == 0.0

    async def test_handles_empty_opening_sentences(self) -> None:
        llm = StubLLMProvider(default=_scripted_response(time_period=None, places=[]))
        extractor = BookContextExtractor(llm=llm)
        ctx = await extractor.extract(raw_content=_hedin_raw(), opening_sentences=[])
        # No crash; LLM still called (it might infer from title alone).
        assert len(llm.calls) == 1
        assert ctx.derived_from_book == "gutenberg:43497"

    async def test_invalid_json_returns_empty_context(self) -> None:
        # Honest-failure principle: bad LLM output should not break ingest.
        llm = StubLLMProvider(default="this is not JSON")
        extractor = BookContextExtractor(llm=llm)

        ctx = await extractor.extract(
            raw_content=_hedin_raw(),
            opening_sentences=_hedin_opening(),
        )

        assert ctx.time_period is None
        assert ctx.places == []
        assert ctx.people_descriptors == []
        assert ctx.summary == ""
        # Audit fields still populated so downstream knows context was attempted.
        assert ctx.derived_from_book == "gutenberg:43497"
        assert ctx.derived_from_model_id == "stub-llm"

    async def test_partial_payload_uses_defaults_for_missing(self) -> None:
        # The LLM returned valid JSON but omitted some fields. We
        # accept it (graceful) and fill defaults — this is friendlier
        # than a hard validation failure that throws away good data.
        llm = StubLLMProvider(default=json.dumps({"summary": "Just a summary."}))
        extractor = BookContextExtractor(llm=llm)
        ctx = await extractor.extract(
            raw_content=_hedin_raw(),
            opening_sentences=_hedin_opening(),
        )
        assert ctx.summary == "Just a summary."
        assert ctx.places == []
        assert ctx.time_period is None

    def test_invalid_max_opening_chars(self) -> None:
        with pytest.raises(ValueError, match="max_opening_chars"):
            BookContextExtractor(llm=StubLLMProvider(), max_opening_chars=0)
        with pytest.raises(ValueError, match="max_opening_chars"):
            BookContextExtractor(llm=StubLLMProvider(), max_opening_chars=-1)


class TestDefaults:
    def test_default_max_opening_is_reasonable(self) -> None:
        # Catches accidental regression where someone sets the default
        # to 80 instead of 8 000.
        assert 1_000 <= DEFAULT_MAX_OPENING_CHARS <= 50_000
