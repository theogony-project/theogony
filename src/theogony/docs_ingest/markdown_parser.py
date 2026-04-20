"""
Markdown structure parser for the docs-aware ingest path.

Wraps ``markdown-it-py`` with a small Pydantic shape so the rest of
``docs_ingest`` works against deterministic, typed data and never has
to know about token streams.

The parser produces:

- one :class:`ParsedDocument` per Markdown file
- one :class:`ParsedSection` per H1/H2 heading inside the document
  (deeper headings are kept inside their containing section's body
  rather than promoted to standalone nodes — keeps the v1 graph
  manageable; deeper hierarchy is a follow-up)
- per-section :class:`MarkdownLink` records, captured separately from
  the prose so the link-extractor can wire cross-document edges
  without re-parsing

What is intentionally **not** captured here (kept inside ``body_text``
verbatim): inline emphasis, inline code, lists, blockquotes, tables.
The body text is the raw Markdown between the heading and the next
heading at the same or higher level — embedding-ready and
faithful to source.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token
from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class _Heading:
    """Internal: a single H1/H2 heading discovered during token walk."""

    level: int
    text: str
    line: int


class MarkdownLink(BaseModel):
    """One ``[text](href)`` link extracted from a section's prose.

    ``href`` is preserved verbatim so the link-extractor can decide
    whether it is a relative cross-doc link, an anchor, or an absolute
    URL.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    href: str


class ParsedSection(BaseModel):
    """One section (H1 or H2) inside a parsed Markdown document.

    ``body_text`` is the raw Markdown between this heading and the next
    heading at the same or higher level, **excluding** the heading line
    itself. The text is what an embedder consumes; downstream code does
    not strip it further.
    """

    model_config = ConfigDict(extra="forbid")

    #: 1 for H1, 2 for H2.
    level: int = Field(ge=1, le=2)
    #: The heading text with leading/trailing whitespace stripped.
    heading: str
    #: ``#anchor`` slug derived from the heading (GitHub-flavoured).
    anchor: str
    #: 1-based line number of the heading in the source file.
    line_start: int
    #: 1-based exclusive line number where this section ends. ``None``
    #: when the section runs to end-of-file.
    line_end: int | None = None
    #: Raw Markdown body, excluding the heading line.
    body_text: str
    #: Links discovered in this section's body.
    links: list[MarkdownLink] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """One parsed Markdown file."""

    model_config = ConfigDict(extra="forbid")

    #: Path relative to the repo root.
    rel_path: str
    #: First H1 heading, or the filename if no H1 is present. The
    #: chronicle uses this as the document node's label.
    title: str
    sections: list[ParsedSection] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------


def parse_markdown(rel_path: str, raw_text: str) -> ParsedDocument:
    """Parse one Markdown file into a :class:`ParsedDocument`.

    Splitting is line-based on H1/H2 headings; deeper headings stay
    inside their containing section's ``body_text``. The ``body_text``
    of a section is the literal substring between its heading and the
    next H1/H2.
    """
    lines = raw_text.splitlines()
    md = MarkdownIt("commonmark", {"html": False})
    tokens = md.parse(raw_text)

    headings = _extract_headings(tokens, lines)

    if not headings:
        # No H1/H2 — single virtual section spanning the whole file.
        title = _filename_title(rel_path)
        return ParsedDocument(
            rel_path=rel_path,
            title=title,
            sections=[
                ParsedSection(
                    level=1,
                    heading=title,
                    anchor=_slugify(title),
                    line_start=1,
                    line_end=None,
                    body_text=raw_text,
                    links=_extract_links(raw_text),
                )
            ],
        )

    title = next((h.text for h in headings if h.level == 1), headings[0].text)

    sections: list[ParsedSection] = []
    for idx, head in enumerate(headings):
        line_start = head.line
        line_end: int | None = headings[idx + 1].line if idx + 1 < len(headings) else None

        body_lines = (
            lines[line_start : (line_end - 1) if line_end is not None else len(lines)]
            if line_start < len(lines)
            else []
        )
        body_text = "\n".join(body_lines).strip("\n")

        sections.append(
            ParsedSection(
                level=head.level,
                heading=head.text,
                anchor=_slugify(head.text),
                line_start=line_start,
                line_end=line_end,
                body_text=body_text,
                links=_extract_links(body_text),
            )
        )

    return ParsedDocument(rel_path=rel_path, title=title, sections=sections)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _extract_headings(tokens: Iterable[Token], lines: list[str]) -> list[_Heading]:
    """Return one :class:`_Heading` per H1/H2 in token order.

    ``markdown_it.token.Token.map`` is the ``[start_line, end_line)``
    pair (0-indexed); we convert to 1-based for ``line`` to match how
    editors display line numbers. ``lines`` is currently unused but
    kept in the signature so future heuristics (e.g. blank-line-aware
    body slicing) have it without an extra parameter churn.
    """
    del lines  # silence unused; reserved for future heuristics
    out: list[_Heading] = []
    pending_level: int | None = None
    pending_line: int | None = None

    for tok in tokens:
        if tok.type == "heading_open" and tok.tag in ("h1", "h2"):
            pending_level = int(tok.tag[1])
            pending_line = (tok.map[0] if tok.map else 0) + 1
        elif tok.type == "inline" and pending_level is not None:
            out.append(
                _Heading(
                    level=pending_level,
                    text=tok.content.strip(),
                    line=pending_line or 1,
                )
            )
            pending_level = None
            pending_line = None
        elif tok.type == "heading_close":
            pending_level = None
            pending_line = None

    return out


_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")
"""Regex for ``[text](href)`` links.

Negative-lookbehind on ``!`` excludes images. Restricting both groups
to the same line keeps the regex from spanning a paragraph break.
"""


def _extract_links(text: str) -> list[MarkdownLink]:
    """Return the inline ``[text](href)`` links in raw Markdown text.

    Uses a regex rather than the markdown-it AST because we want links
    inside lists, tables, blockquotes, and admonitions; the AST walk
    would force us to recurse into every container token type.
    """
    out: list[MarkdownLink] = []
    seen: set[tuple[str, str]] = set()
    for m in _LINK_RE.finditer(text):
        text_, href = m.group(1).strip(), m.group(2).strip()
        # Strip a trailing close-paren that the lazy regex sometimes
        # captures from nested ``[…](https://…)`` constructs.
        href = href.rstrip(")")
        key = (text_, href)
        if key in seen:
            continue
        seen.add(key)
        out.append(MarkdownLink(text=text_, href=href))
    return out


_NON_ALNUM = re.compile(r"[^\w\- ]+")
_WHITESPACE = re.compile(r"\s+")


def _slugify(text: str) -> str:
    """GitHub-flavoured anchor slug.

    Lower-case, strip non-alphanumerics, collapse whitespace to
    single hyphens. Good-enough match for ``[link](#anchor)``-style
    cross-references; not a security-critical surface.
    """
    s = _NON_ALNUM.sub("", text.lower())
    s = _WHITESPACE.sub("-", s).strip("-")
    return s


def _filename_title(rel_path: str) -> str:
    """Derive a fallback title from the file basename.

    ``docs/PANTHEON_VISION.md`` → ``PANTHEON_VISION``. Used only when a
    document has no H1/H2 headings at all.
    """
    name = rel_path.rsplit("/", 1)[-1]
    stem = name[:-3] if name.endswith(".md") else name
    return stem


__all__ = [
    "MarkdownLink",
    "ParsedDocument",
    "ParsedSection",
    "parse_markdown",
]
