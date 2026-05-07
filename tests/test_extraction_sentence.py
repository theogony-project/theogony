"""Tests for Sentencizer + Sentence DTO (Plan §2.5, §3a PID-1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from theogony.extraction.clean import CleanedContent
from theogony.extraction.sentence import Sentence, Sentencizer

# ---------------------------------------------------------------------------
# Sentence DTO
# ---------------------------------------------------------------------------


class TestSentenceDTO:
    def test_basic_construction(self) -> None:
        s = Sentence(index=0, text="Hello world.", start_char=0, end_char=12)
        assert s.index == 0
        assert s.text == "Hello world."

    def test_negative_index_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Sentence(index=-1, text="x", start_char=0, end_char=1)

    def test_negative_offset_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Sentence(index=0, text="x", start_char=-1, end_char=1)

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Sentence(
                index=0,
                text="x",
                start_char=0,
                end_char=1,
                typo="oops",  # type: ignore[call-arg]
            )

    def test_round_trip_json(self) -> None:
        s = Sentence(index=3, text="Harrer reached Lhasa.", start_char=42, end_char=63)
        restored = Sentence.model_validate_json(s.model_dump_json())
        assert restored == s


# ---------------------------------------------------------------------------
# Sentencizer
# ---------------------------------------------------------------------------


class TestSentencize:
    async def test_empty_string_returns_empty_list(self) -> None:
        s = Sentencizer()
        assert await s.sentencize("") == []

    async def test_single_sentence(self) -> None:
        s = Sentencizer()
        result = await s.sentencize("Hello world.")
        assert len(result) == 1
        assert result[0].index == 0
        assert result[0].text == "Hello world."
        assert result[0].start_char == 0
        assert result[0].end_char == 12

    async def test_three_sentences(self) -> None:
        s = Sentencizer()
        text = "First sentence. Second sentence! Third sentence?"
        result = await s.sentencize(text)
        assert len(result) == 3
        assert [r.index for r in result] == [0, 1, 2]
        assert result[0].text.strip() == "First sentence."
        assert result[1].text.strip() == "Second sentence!"
        assert result[2].text.strip() == "Third sentence?"

    async def test_offsets_match_substring(self) -> None:
        s = Sentencizer()
        text = "Harrer reached Uttarkashi at midnight. Then he met the Marchese."
        result = await s.sentencize(text)
        # Every sentence's substring at [start_char:end_char] must equal its text.
        for sent in result:
            assert text[sent.start_char : sent.end_char] == sent.text

    async def test_accepts_cleaned_content_directly(self) -> None:
        s = Sentencizer()
        cc = CleanedContent(
            content="Sentence one. Sentence two.",
            raw_length=27,
            raw_offset_start=0,
            raw_offset_end=27,
            header_stripped=False,
            footer_stripped=False,
        )
        result = await s.sentencize(cc)
        assert len(result) == 2
        assert result[0].text.strip() == "Sentence one."

    async def test_min_chars_filters_short_sentences(self) -> None:
        s = Sentencizer(min_chars=8)
        # Use a paragraph break to force the boundary; "Yes." is 4 chars
        # stripped → below threshold; the second sentence survives.
        text = "Yes.\n\nThis sentence is plenty long."
        result = await s.sentencize(text)
        assert len(result) == 1
        assert result[0].text.strip() == "This sentence is plenty long."
        # And re-indexing is contiguous from 0 (not from the original spaCy index).
        assert result[0].index == 0

    async def test_paragraph_break_is_a_boundary(self) -> None:
        s = Sentencizer()
        text = "First sentence.\n\nSecond sentence."
        result = await s.sentencize(text)
        assert len(result) == 2

    async def test_multiple_calls_share_pipeline(self) -> None:
        """Verify the lazy pipeline is built once and reused."""
        s = Sentencizer()
        await s.sentencize("First.")
        first_pipeline = s._nlp
        assert first_pipeline is not None
        await s.sentencize("Second.")
        assert s._nlp is first_pipeline

    async def test_large_input_respects_custom_max_length(self) -> None:
        s = Sentencizer(max_length=1_200_000)
        huge = ("A short sentence. " * 60_000).strip()
        result = await s.sentencize(huge)
        assert len(result) > 1


class TestRealHedinExcerpt:
    """Smoke-test the sentencizer on a real Hedin paragraph (no model required).

    The text is taken from the live Hedin #43497 download captured
    during Etappe-D smoke testing — exact byte-for-byte. If
    sentencizer behaviour drifts on this kind of prose we catch it
    here, not in production.
    """

    HEDIN_PARAGRAPH = (
        "Macfarlane's drawings were executed this summer, and I was able to "
        "inspect his designs and approve of them before they were worked up.\n"
        "\n"
        "As to the text, I have endeavoured to depict the events of the journey "
        "as far as the limited space permitted, but I have also imprudently "
        "allowed myself to touch on subjects with which I am not at all familiar."
    )

    async def test_two_sentences_from_paragraph(self) -> None:
        s = Sentencizer()
        result = await s.sentencize(self.HEDIN_PARAGRAPH)
        # Two prose sentences separated by a paragraph break. spaCy's
        # rule-based sentencizer splits at the period+newline boundary
        # plus the period inside the second clause.
        assert len(result) >= 2
        assert all(
            "Macfarlane" in r.text or "text" in r.text or "subjects" in r.text for r in result
        )
        # The substring invariant survives unicode + apostrophes.
        for sent in result:
            assert self.HEDIN_PARAGRAPH[sent.start_char : sent.end_char] == sent.text
