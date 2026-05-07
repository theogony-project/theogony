"""
Wikipedia helpers for full-article plaintext and TFA (Today's Featured Article) titles.

Uses the MediaWiki Action API with a descriptive User-Agent (WMF policy).
"""

from __future__ import annotations

import asyncio
import html as html_lib
import re
from collections.abc import AsyncIterator

import httpx

WIKI_USER_AGENT = (
    "TheogonyBot/1.0 (https://github.com/theogony-project/theogony; contact=ops@example.invalid)"
)

_TFAFULL_RE = re.compile(r"\{\{TFAFULL\|([^|}]+)(?:\|[^}]*)?\}\}")


def extract_tfa_main_title_from_day_wikitext(wikitext: str) -> str | None:
    """Return the first TFAFULL main-article title from a daily TFA wikitext page."""
    m = _TFAFULL_RE.search(wikitext)
    if not m:
        return None
    return m.group(1).strip().replace("_", " ")


def strip_html_to_plaintext(html_text: str) -> str:
    """Crude but dependency-free HTML → plain text for parse API output."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html_text, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def fetch_article_plaintext(
    client: httpx.AsyncClient,
    title: str,
    *,
    timeout_s: float = 60.0,
) -> str:
    """Fetch full article body as plaintext via action=parse (HTML stripped)."""
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "format": "json",
        "formatversion": "2",
        "page": title,
        "prop": "text",
    }
    headers = {"User-Agent": WIKI_USER_AGENT}
    response = await client.get(url, params=params, headers=headers, timeout=timeout_s)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"Wikipedia parse error: {payload['error']}")
    html_text = payload["parse"]["text"]
    return strip_html_to_plaintext(html_text)


async def fetch_day_tfa_wikitext(
    client: httpx.AsyncClient,
    *,
    year: int,
    month: int,
    day: int,
    timeout_s: float = 30.0,
) -> str:
    """Wikitext of ``Wikipedia:Today's featured article/Month day, year``."""
    month_names = (
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    mname = month_names[month]
    title = f"Wikipedia:Today's featured article/{mname} {day}, {year}"
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
    }
    headers = {"User-Agent": WIKI_USER_AGENT}
    response = await client.get(url, params=params, headers=headers, timeout=timeout_s)
    response.raise_for_status()
    pages = response.json()["query"]["pages"]
    for pid, page in pages.items():
        if pid == "-1" or page.get("missing"):
            raise RuntimeError(f"TFA day page not found: {title!r}")
        revs = page.get("revisions")
        if not revs:
            raise RuntimeError(f"No revisions for TFA day page: {title!r}")
        return revs[0]["slots"]["main"]["*"]
    raise RuntimeError("Empty query.pages")


async def iter_tfa_titles_en_calendar_month(
    client: httpx.AsyncClient,
    *,
    year: int,
    month: int,
    first_day: int = 1,
    last_day: int = 10,
) -> AsyncIterator[str]:
    """Yield main article titles from English Wikipedia daily TFA pages (inclusive day range)."""
    for day in range(first_day, last_day + 1):
        wt = await fetch_day_tfa_wikitext(client, year=year, month=month, day=day)
        main = extract_tfa_main_title_from_day_wikitext(wt)
        if main:
            yield main
        await asyncio.sleep(0.35)


def chunk_text(text: str, *, max_chars: int, overlap: int = 200) -> list[str]:
    """Split ``text`` into overlapping segments of at most ``max_chars`` characters."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    step = max(1, max_chars - overlap)
    while start < len(text):
        end = min(start + max_chars, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start += step
    return chunks


__all__ = [
    "WIKI_USER_AGENT",
    "chunk_text",
    "extract_tfa_main_title_from_day_wikitext",
    "fetch_article_plaintext",
    "fetch_day_tfa_wikitext",
    "iter_tfa_titles_en_calendar_month",
    "strip_html_to_plaintext",
]
