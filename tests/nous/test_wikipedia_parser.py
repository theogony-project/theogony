"""
Unit tests for nous.wikipedia_parser (nous_implementation_brief §5, E1).

All tests use offline HTML fixtures — no network access required.
"""

from __future__ import annotations

import pytest

from theogony.nous.wikipedia_parser import (
    WikiSection,
    _extract_title,
    parse_html_to_sections,
)

# ---------------------------------------------------------------------------
# Minimal fixture HTML that mirrors Wikipedia's mw-parser-output structure
# ---------------------------------------------------------------------------

_SIMPLE_HTML = """
<div class="mw-parser-output">
  <p>Sven Anders Hedin was a Swedish explorer.</p>
  <p>He made several expeditions to Central Asia.</p>
  <h2>Early life</h2>
  <p>Hedin was born in Stockholm in 1865.</p>
  <p>He showed an early interest in geography.</p>
  <h2>Expeditions</h2>
  <h3>Trans-Himalaya</h3>
  <p>The Trans-Himalaya is a mountain range.</p>
  <p>Hedin crossed it multiple times.</p>
</div>
"""

_EMPTY_PARAGRAPHS_HTML = """
<div class="mw-parser-output">
  <p>   </p>
  <p>Short.</p>
  <p>This is a substantive paragraph about the topic at hand.</p>
  <h2>See also</h2>
  <p>x</p>
</div>
"""

_NO_CONTAINER_HTML = """
<html><body>
  <p>Fallback paragraph with sufficient length for inclusion.</p>
  <h2>Section One</h2>
  <p>Another paragraph with enough text to pass the length filter.</p>
</body></html>
"""


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


def test_lead_section_paragraphs() -> None:
    sections = parse_html_to_sections(_SIMPLE_HTML)
    assert sections[0].title == ""
    assert sections[0].level == 0
    assert len(sections[0].paragraphs) == 2
    assert "Swedish explorer" in sections[0].paragraphs[0]


def test_h2_section_created() -> None:
    sections = parse_html_to_sections(_SIMPLE_HTML)
    titles = [s.title for s in sections]
    assert "Early life" in titles


def test_h3_section_created() -> None:
    sections = parse_html_to_sections(_SIMPLE_HTML)
    titles = [s.title for s in sections]
    assert "Trans-Himalaya" in titles


def test_section_levels() -> None:
    sections = parse_html_to_sections(_SIMPLE_HTML)
    level_map = {s.title: s.level for s in sections}
    assert level_map["Early life"] == 2
    assert level_map["Trans-Himalaya"] == 3


def test_empty_h2_not_created() -> None:
    """An H2 heading with no direct paragraphs (only a sub-heading follows) is not added."""
    sections = parse_html_to_sections(_SIMPLE_HTML)
    titles = [s.title for s in sections]
    # "Expeditions" H2 has no <p> before the <h3> Trans-Himalaya, so it must be absent.
    assert "Expeditions" not in titles


def test_paragraphs_under_sections() -> None:
    sections = parse_html_to_sections(_SIMPLE_HTML)
    early = next(s for s in sections if s.title == "Early life")
    assert len(early.paragraphs) == 2
    assert "Stockholm" in early.paragraphs[0]


def test_short_paragraphs_filtered() -> None:
    """Paragraphs under 20 chars (e.g. "Short." and "x") must be excluded."""
    sections = parse_html_to_sections(_EMPTY_PARAGRAPHS_HTML)
    all_paras = [p for s in sections for p in s.paragraphs]
    assert all(len(p) > 20 for p in all_paras)


def test_whitespace_only_paragraphs_filtered() -> None:
    sections = parse_html_to_sections(_EMPTY_PARAGRAPHS_HTML)
    all_paras = [p for s in sections for p in s.paragraphs]
    assert all(p.strip() for p in all_paras)


def test_no_mw_container_falls_back_to_body() -> None:
    sections = parse_html_to_sections(_NO_CONTAINER_HTML)
    assert len(sections) >= 1
    all_paras = [p for s in sections for p in s.paragraphs]
    assert any("Fallback" in p for p in all_paras)


def test_sections_are_wiksection_instances() -> None:
    sections = parse_html_to_sections(_SIMPLE_HTML)
    assert all(isinstance(s, WikiSection) for s in sections)


def test_empty_section_not_appended() -> None:
    """Sections with no paragraphs (only a heading and then the next heading) must not appear."""
    html = """
    <div class="mw-parser-output">
      <h2>Empty section</h2>
      <h2>Non-empty section</h2>
      <p>This paragraph has sufficient length to be included here.</p>
    </div>
    """
    sections = parse_html_to_sections(html)
    titles = [s.title for s in sections]
    assert "Empty section" not in titles
    assert "Non-empty section" in titles


def test_wikidata_edit_markers_stripped() -> None:
    html = """
    <div class="mw-parser-output">
      <p>Hedin was born in Stockholm.[edit] He explored Tibet.[1][2]</p>
    </div>
    """
    sections = parse_html_to_sections(html)
    para = sections[0].paragraphs[0]
    assert "[edit]" not in para
    assert "[1]" not in para
    assert "[2]" not in para


# ---------------------------------------------------------------------------
# _extract_title helper
# ---------------------------------------------------------------------------


def test_extract_title_from_plain_string() -> None:
    assert _extract_title("Sven Hedin") == "Sven Hedin"


def test_extract_title_from_wikipedia_url() -> None:
    assert _extract_title("https://en.wikipedia.org/wiki/Sven_Hedin") == "Sven Hedin"


def test_extract_title_strips_trailing_slash() -> None:
    assert _extract_title("https://en.wikipedia.org/wiki/Trans-Himalaya/") == "Trans-Himalaya"


def test_extract_title_invalid_url_raises() -> None:
    with pytest.raises(ValueError, match="Cannot extract title"):
        _extract_title("https://example.com/not-wikipedia")
