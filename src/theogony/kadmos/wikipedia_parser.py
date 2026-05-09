"""
Structured Wikipedia fetch and segmentation for Kadmos v2.

The brief requires paragraph-level reading units.  The MediaWiki
``action=parse`` REST API returns HTML that is already naturally segmented
into H2/H3 sections and <p> paragraphs — we parse that structure rather
than stripping to flat plaintext.

Public entry point:
    ``fetch_article_structured(title_or_url, *, client) -> list[WikiSection]``

Each :class:`WikiSection` has:
    - ``title``      — section heading ("" for the lead section)
    - ``level``      — heading level (2 for H2, etc.; 0 for lead)
    - ``paragraphs`` — non-empty paragraphs in document order, plain text

We intentionally keep the implementation simple: HTML → BeautifulSoup →
walk top-level elements.  No recursive section nesting beyond H2/H3 is
required by v1 (nous_implementation_brief §8 deferred list).
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, ConfigDict

from theogony import __version__
from theogony.config.logging import get_logger

log = get_logger("nous.wikipedia_parser")

_USER_AGENT = (
    f"theogony-nous/{__version__} "
    "(+https://github.com/theogony-project/theogony; open knowledge infrastructure)"
)
_DEFAULT_TIMEOUT_S = 30.0
_MEDIAWIKI_PARSE_URL = "https://en.wikipedia.org/w/api.php"
_STRIP_PATTERNS = re.compile(r"\[edit\]|\[\d+\]")


class WikiSection(BaseModel):
    """One H2/H3 section (or the lead section) from a Wikipedia article."""

    model_config = ConfigDict(extra="forbid")

    title: str
    level: int = 0
    paragraphs: list[str] = []


def _clean(text: str) -> str:
    """Strip edit-section markers and citation brackets from paragraph text."""
    return _STRIP_PATTERNS.sub("", text).strip()


def _parse_html_to_sections(html: str) -> list[WikiSection]:
    """Parse MediaWiki HTML into :class:`WikiSection` objects.

    Strategy:
    1. Walk the top-level children of the ``<div class="mw-parser-output">``
       (or ``<body>`` as fallback).
    2. When a heading tag (H2/H3) is encountered, start a new section.
    3. When a ``<p>`` tag is encountered, append its text to the current section.
    4. Ignore tables, infoboxes, navboxes, and empty paragraphs.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", class_="mw-parser-output") or soup.find("body") or soup
    assert isinstance(container, Tag)

    sections: list[WikiSection] = []
    current = WikiSection(title="", level=0)

    for child in container.children:
        if not isinstance(child, Tag):
            continue

        tag = child.name
        if tag in ("h2", "h3", "h4"):
            level = int(tag[1])
            heading_text = child.get_text(" ", strip=True)
            heading_text = _clean(heading_text)
            if current.paragraphs:
                sections.append(current)
            current = WikiSection(title=heading_text, level=level)
            continue

        if tag == "p":
            text = _clean(child.get_text(" ", strip=True))
            if len(text) > 20:
                current.paragraphs.append(text)

    if current.paragraphs:
        sections.append(current)

    return sections


async def fetch_article_structured(
    title_or_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> list[WikiSection]:
    """Fetch a Wikipedia article and return it as structured sections.

    ``title_or_url`` may be:
    - A plain article title: ``"Sven Hedin"``
    - A Wikipedia URL: ``"https://en.wikipedia.org/wiki/Sven_Hedin"``

    Uses the MediaWiki ``action=parse`` API to get rendered HTML, then
    parses it into :class:`WikiSection` objects.

    Raises ``httpx.HTTPError`` or ``ValueError`` on fetch/parse failure —
    callers (NousReader) catch and convert to ``verdict="failed"``.
    """
    title = _extract_title(title_or_url)

    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "disablelimitreport": "1",
        "disableeditsection": "1",
    }

    headers = {"User-Agent": _USER_AGENT}

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_s, headers=headers)

    try:
        response = await client.get(_MEDIAWIKI_PARSE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise ValueError(f"MediaWiki API error: {data['error'].get('info', data['error'])}")

        html = data["parse"]["text"]["*"]
        sections = _parse_html_to_sections(html)
        log.debug(
            "parsed article title=%r sections=%d total_paragraphs=%d",
            title,
            len(sections),
            sum(len(s.paragraphs) for s in sections),
        )
        return sections
    finally:
        if own_client:
            await client.aclose()


def _extract_title(title_or_url: str) -> str:
    """Normalise a Wikipedia URL or article title to a MediaWiki page title."""
    title_or_url = title_or_url.strip()
    if title_or_url.startswith("http"):
        # e.g. https://en.wikipedia.org/wiki/Sven_Hedin
        parts = title_or_url.rstrip("/").split("/wiki/", 1)
        if len(parts) == 2:
            return parts[1].replace("_", " ")
        raise ValueError(f"Cannot extract title from URL: {title_or_url!r}")
    return title_or_url


def parse_html_to_sections(html: str) -> list[WikiSection]:
    """Public wrapper around ``_parse_html_to_sections`` for offline testing."""
    return _parse_html_to_sections(html)
