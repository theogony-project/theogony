"""Tests for TextCleaner (Plan §2.5)."""

from __future__ import annotations

import pytest

from theogony.extraction.clean import (
    _END_MARKER_RE,
    _START_MARKER_RE,
    CleanedContent,
    TextCleaner,
)


def _wrap_in_pg(body: str) -> str:
    """Wrap body in canonical Project Gutenberg header/footer (CRLF, like real files)."""
    header = (
        "\ufeffThe Project Gutenberg eBook of Test Title\r\n"
        "\r\n"
        "Title: Test Title\r\n"
        "Author: A. N. Author\r\n"
        "Language: English\r\n"
        "\r\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK TEST TITLE ***\r\n"
    )
    footer = (
        "\r\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK TEST TITLE ***\r\n"
        "\r\n"
        "Updated editions will replace the previous one.\r\n"
    )
    return header + body.replace("\n", "\r\n") + footer


# ---------------------------------------------------------------------------
# Marker regexes (the heart of the cleaner)
# ---------------------------------------------------------------------------


class TestMarkerRegexes:
    @pytest.mark.parametrize(
        "marker",
        [
            "*** START OF THE PROJECT GUTENBERG EBOOK FOO ***",
            "*** START OF THIS PROJECT GUTENBERG EBOOK FOO ***",
            "***START OF THE PROJECT GUTENBERG EBOOK FOO***",
            "*** start of the project gutenberg ebook foo ***",
            "*** START OF THE PROJECT GUTENBERG EBOOK TRANS-HIMALAYA: VOL. 1 (OF 2) ***",
        ],
    )
    def test_start_marker_variants_all_match(self, marker: str) -> None:
        assert _START_MARKER_RE.search(marker) is not None

    @pytest.mark.parametrize(
        "non_marker",
        [
            "Project Gutenberg's Trans-Himalaya, by Sven Hedin",  # body text mention
            "*** START OF SOMETHING ELSE ***",
            "Just some text without any markers.",
        ],
    )
    def test_start_marker_does_not_match_random_text(self, non_marker: str) -> None:
        assert _START_MARKER_RE.search(non_marker) is None

    def test_end_marker_variants(self) -> None:
        assert _END_MARKER_RE.search("*** END OF THE PROJECT GUTENBERG EBOOK FOO ***") is not None
        assert _END_MARKER_RE.search("*** END OF THIS PROJECT GUTENBERG EBOOK FOO ***") is not None


# ---------------------------------------------------------------------------
# clean()
# ---------------------------------------------------------------------------


class TestClean:
    def test_strips_canonical_pg_header_and_footer(self) -> None:
        cleaner = TextCleaner()
        wrapped = _wrap_in_pg("Once upon a midnight dreary,\nwhile I pondered, weak and weary.")
        result = cleaner.clean(wrapped)
        assert isinstance(result, CleanedContent)
        assert "Project Gutenberg" not in result.content
        assert "*** START" not in result.content
        assert "*** END" not in result.content
        assert "Updated editions will replace" not in result.content
        assert "Once upon a midnight dreary," in result.content
        assert "while I pondered, weak and weary." in result.content
        assert result.header_stripped is True
        assert result.footer_stripped is True
        assert result.warnings == []

    def test_preserves_offsets_into_normalised_raw(self) -> None:
        cleaner = TextCleaner()
        body = "Hello world.\nA second sentence."
        wrapped = _wrap_in_pg(body)
        result = cleaner.clean(wrapped)
        # The raw_offset_start should land at the offset *after* the START marker
        # and the (single) trailing newline. raw_offset_end should land just
        # before the END marker (with its single leading newline trimmed).
        normalised = wrapped.replace("\r\n", "\n").lstrip("\ufeff")
        assert normalised[result.raw_offset_start :].startswith("Hello world.")
        assert (
            normalised[result.raw_offset_start : result.raw_offset_end]
            .rstrip("\n")
            .endswith("A second sentence.")
        )
        assert result.raw_length == len(normalised)

    def test_no_markers_emits_warnings_and_returns_original_body(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean("plain text, no PG markers anywhere")
        assert "pg_start_marker_not_found" in result.warnings
        assert "pg_end_marker_not_found" in result.warnings
        assert result.header_stripped is False
        assert result.footer_stripped is False
        assert "plain text, no PG markers anywhere" in result.content

    def test_only_start_marker_present(self) -> None:
        cleaner = TextCleaner()
        text = "garbage\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\nbody"
        result = cleaner.clean(text)
        assert result.header_stripped is True
        assert result.footer_stripped is False
        assert "garbage" not in result.content
        assert "body" in result.content
        assert "pg_end_marker_not_found" in result.warnings
        assert "pg_start_marker_not_found" not in result.warnings

    def test_strip_pg_markers_can_be_disabled(self) -> None:
        cleaner = TextCleaner(strip_pg_markers=False)
        wrapped = _wrap_in_pg("body")
        result = cleaner.clean(wrapped)
        assert "*** START" in result.content
        assert "*** END" in result.content
        assert result.header_stripped is False
        assert result.footer_stripped is False
        # Without marker stripping there are no warnings either.
        assert result.warnings == []


class TestNormalisation:
    def test_crlf_is_normalised(self) -> None:
        cleaner = TextCleaner(strip_pg_markers=False)
        result = cleaner.clean("a\r\nb\r\nc")
        assert "\r" not in result.content
        assert result.content.split("\n") == ["a", "b", "c"]

    def test_bare_cr_is_normalised(self) -> None:
        cleaner = TextCleaner(strip_pg_markers=False)
        result = cleaner.clean("a\rb\rc")
        assert "\r" not in result.content

    def test_bom_is_stripped(self) -> None:
        cleaner = TextCleaner(strip_pg_markers=False)
        result = cleaner.clean("\ufeffhello")
        assert result.content == "hello"


class TestCollapseBlankLines:
    def test_default_collapses_to_two_blank_lines(self) -> None:
        cleaner = TextCleaner(strip_pg_markers=False)
        text = "a\n\n\n\n\n\nb"  # 5 blank lines between a and b
        result = cleaner.clean(text)
        # max_consecutive_blank_lines=2 ⇒ between two text lines there are 2
        # blank lines, total 3 newlines.
        assert result.content == "a\n\n\nb"

    def test_zero_drops_all_blank_lines(self) -> None:
        cleaner = TextCleaner(strip_pg_markers=False, max_consecutive_blank_lines=0)
        result = cleaner.clean("a\n\n\nb\n\nc")
        assert result.content == "a\nb\nc"

    def test_disabled_preserves_blank_lines(self) -> None:
        cleaner = TextCleaner(strip_pg_markers=False, collapse_blank_lines=False)
        text = "a\n\n\n\n\nb"
        result = cleaner.clean(text)
        assert result.content == text


# ---------------------------------------------------------------------------
# Plausibility: the real Hedin header/footer pattern
# ---------------------------------------------------------------------------


class TestRealHedinHeaderPattern:
    """Use the exact header/footer marker the live Hedin #43497 file uses.

    Drawn from the inspection captured during Etappe-D smoke testing
    (commit 2a07c8c message). If PG ever shifts marker conventions
    this test catches it before production.
    """

    HEDIN_START = (
        "*** START OF THE PROJECT GUTENBERG EBOOK TRANS-HIMALAYA: "
        "DISCOVERIES AND ADVENTURERS IN TIBET. VOL. 1 (OF 2) ***"
    )
    HEDIN_END = (
        "*** END OF THE PROJECT GUTENBERG EBOOK TRANS-HIMALAYA: "
        "DISCOVERIES AND ADVENTURERS IN TIBET. VOL. 1 (OF 2) ***"
    )

    def test_hedin_start_marker_matches(self) -> None:
        assert _START_MARKER_RE.search(self.HEDIN_START) is not None

    def test_hedin_end_marker_matches(self) -> None:
        assert _END_MARKER_RE.search(self.HEDIN_END) is not None

    def test_full_round_trip_with_hedin_markers(self) -> None:
        cleaner = TextCleaner()
        body = "I had long been planning a fresh journey through Tibet."
        text = (
            "\ufeffPreamble blah blah\r\n"
            "Title: Trans-Himalaya\r\n"
            "\r\n"
            f"{self.HEDIN_START}\r\n"
            "\r\n"
            f"{body}\r\n"
            "\r\n"
            f"{self.HEDIN_END}\r\n"
            "Footer prose.\r\n"
        )
        result = cleaner.clean(text)
        assert result.header_stripped is True
        assert result.footer_stripped is True
        assert "Preamble blah blah" not in result.content
        assert "Footer prose" not in result.content
        assert body in result.content
