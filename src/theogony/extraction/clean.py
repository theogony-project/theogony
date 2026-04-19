"""
TextCleaner — strip Project Gutenberg header/footer + normalise whitespace.

Plan §2.5 (S): the first stage of the extraction pipeline. Takes raw
text from an :class:`~theogony.acquisition.RawContent` and returns a
:class:`CleanedContent` ready for sentence segmentation.

Discipline (Plan §3.3 + §9.5):

- Char offsets in downstream Sentence/Mention DTOs always refer to
  the **cleaned** text. The original raw text is preserved in the
  CleanedContent's ``raw_offset_start`` so a forensic lookup can map
  back when needed.
- The cleaner is pure (no I/O, no async, no logging at INFO level).
  Errors are recorded in the returned ``warnings`` list rather than
  raised — a missing header marker should not abort an ingest run.
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Project Gutenberg marker patterns
# ---------------------------------------------------------------------------

# PG marker variants seen in the wild:
#   *** START OF THE PROJECT GUTENBERG EBOOK ... ***   (newer)
#   *** START OF THIS PROJECT GUTENBERG EBOOK ... ***  (older)
#   ***START OF THE PROJECT GUTENBERG EBOOK ... ***    (no spaces, very old)
# Same variants for END. We accept any of them, case-insensitive,
# tolerant of internal whitespace.
_START_MARKER_RE: Final = re.compile(
    r"\*\*\*\s*START\s+OF\s+(?:THE|THIS)\s+PROJECT\s+GUTENBERG\s+EBOOK[^\n]*\*\*\*",
    flags=re.IGNORECASE,
)
_END_MARKER_RE: Final = re.compile(
    r"\*\*\*\s*END\s+OF\s+(?:THE|THIS)\s+PROJECT\s+GUTENBERG\s+EBOOK[^\n]*\*\*\*",
    flags=re.IGNORECASE,
)


class CleanedContent(BaseModel):
    """Output of :class:`TextCleaner`.

    ``content`` is what every downstream stage works on. The remaining
    fields are forensics — ``raw_length`` and ``raw_offset_start``
    let a debugger map a cleaned-text offset back into the original
    raw bytes when triaging an extraction surprise.
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    raw_length: int = Field(
        ge=0,
        description="Length of the raw input text in characters (post-newline-normalisation).",
    )
    raw_offset_start: int = Field(
        ge=0,
        description=(
            "Char offset in the normalised raw text where the cleaned "
            "body begins. 0 when no PG header was found."
        ),
    )
    raw_offset_end: int = Field(
        ge=0,
        description=(
            "Char offset (exclusive) in the normalised raw text where "
            "the cleaned body ends. raw_length when no PG footer was found."
        ),
    )
    header_stripped: bool
    footer_stripped: bool
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Cleaner
# ---------------------------------------------------------------------------


class TextCleaner:
    """Strip Project Gutenberg boilerplate and normalise whitespace.

    Stateless. Safe to share across async tasks.
    """

    def __init__(
        self,
        *,
        strip_pg_markers: bool = True,
        normalise_newlines: bool = True,
        strip_bom: bool = True,
        collapse_blank_lines: bool = True,
        max_consecutive_blank_lines: int = 2,
    ) -> None:
        self._strip_pg_markers = strip_pg_markers
        self._normalise_newlines = normalise_newlines
        self._strip_bom = strip_bom
        self._collapse_blank_lines = collapse_blank_lines
        self._max_consecutive_blank_lines = max(0, max_consecutive_blank_lines)

    def clean(self, raw: str) -> CleanedContent:
        """Strip PG markers + normalise whitespace, returning forensics with the cleaned text."""
        warnings: list[str] = []
        text = raw

        if self._strip_bom and text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")

        if self._normalise_newlines:
            # CRLF (Windows) and CR (old Mac) → LF. PG files use CRLF.
            text = text.replace("\r\n", "\n").replace("\r", "\n")

        raw_length = len(text)

        body_start = 0
        body_end = raw_length
        header_stripped = False
        footer_stripped = False

        if self._strip_pg_markers:
            start_match = _START_MARKER_RE.search(text)
            if start_match is not None:
                body_start = start_match.end()
                # Skip a single trailing newline immediately after the marker
                # so the body doesn't start with a blank line artefact.
                if body_start < raw_length and text[body_start] == "\n":
                    body_start += 1
                header_stripped = True
            else:
                warnings.append("pg_start_marker_not_found")

            end_match = _END_MARKER_RE.search(text, pos=body_start)
            if end_match is not None:
                body_end = end_match.start()
                # Trim a single trailing newline immediately before the marker.
                if body_end > body_start and text[body_end - 1] == "\n":
                    body_end -= 1
                footer_stripped = True
            else:
                warnings.append("pg_end_marker_not_found")

        body = text[body_start:body_end].strip("\n")

        if self._collapse_blank_lines and self._max_consecutive_blank_lines >= 0:
            body = self._collapse(body, self._max_consecutive_blank_lines)

        return CleanedContent(
            content=body,
            raw_length=raw_length,
            raw_offset_start=body_start,
            raw_offset_end=body_end,
            header_stripped=header_stripped,
            footer_stripped=footer_stripped,
            warnings=warnings,
        )

    @staticmethod
    def _collapse(text: str, max_blank_lines: int) -> str:
        """Replace runs of blank lines longer than ``max_blank_lines`` with that many.

        Avoids the blunt "single blank line max" heuristic — paragraph
        breaks in books are meaningful, but seven blank lines between
        chapters are not.
        """
        if max_blank_lines == 0:
            # Drop all blank lines entirely.
            return "\n".join(line for line in text.split("\n") if line.strip())

        replacement = "\n" * (max_blank_lines + 1)
        # Match `(\n[ \t]*){N,}` where N = max_blank_lines + 2 (i.e. > the cap).
        pattern = re.compile(r"(?:\n[ \t]*){" + str(max_blank_lines + 2) + r",}")
        return pattern.sub(replacement, text)
