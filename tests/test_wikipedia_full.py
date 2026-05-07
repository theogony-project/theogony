"""Unit tests for Wikipedia full-text / TFA helpers."""

from theogony.extraction.wikipedia_full import (
    chunk_text,
    extract_tfa_main_title_from_day_wikitext,
    strip_html_to_plaintext,
)


def test_extract_tfa_main_title() -> None:
    wt = "blah {{TFAFULL|Crusading movement}} tail"
    assert extract_tfa_main_title_from_day_wikitext(wt) == "Crusading movement"
    wt2 = "{{TFAFULL|Fuji-class battleship|Battleships of Japan}}"
    assert extract_tfa_main_title_from_day_wikitext(wt2) == "Fuji-class battleship"


def test_strip_html_basic() -> None:
    html = "<p>Hello <b>world</b> &amp; friends</p>"
    out = strip_html_to_plaintext(html)
    assert "Hello" in out
    assert "world" in out


def test_chunk_text_overlap() -> None:
    s = "a" * 25
    parts = chunk_text(s, max_chars=10, overlap=2)
    assert len(parts) >= 2
    assert all(len(p) <= 10 for p in parts)
