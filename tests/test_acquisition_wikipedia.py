"""W12 — WikipediaAdapter unit tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from theogony.acquisition.base import SourceCandidate
from theogony.acquisition.wikipedia import WikipediaAdapter, _looks_german

_FIXTURE_HTML = (Path(__file__).resolve().parent / "fixtures" / "wikipedia_sample.html").read_text(
    encoding="utf-8"
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("München history", True),
        ("der alte Mann", True),
        ("London bridge", False),
    ],
)
def test_looks_german_heuristic(query: str, expected: bool) -> None:
    assert _looks_german(query) is expected


@pytest.mark.asyncio
@respx.mock
async def test_wikipedia_search_returns_candidates_with_pageid() -> None:
    payload = {
        "pages": [
            {
                "id": 529134,
                "key": "Sven_Hedin",
                "title": "Sven Hedin",
                "excerpt": "Explorer",
                "description": "Swedish explorer",
            }
        ]
    }
    respx.get("https://en.wikipedia.org/w/rest.php/v1/search/page?q=Sven+Hedin&limit=3").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with WikipediaAdapter(inter_request_delay_s=0.0) as wiki:
        cands = await wiki.search("Sven Hedin", limit=3)
    assert len(cands) == 1
    assert cands[0].identifier == "Sven_Hedin"
    assert cands[0].metadata.get("wikipedia_pageid") == 529134
    assert cands[0].metadata.get("wikipedia_lang") == "en"


@pytest.mark.asyncio
@respx.mock
async def test_wikipedia_acquire_extracts_main_text_via_trafilatura() -> None:
    respx.get("https://en.wikipedia.org/w/rest.php/v1/page/Sven_Hedin/html").mock(
        return_value=httpx.Response(200, text=_FIXTURE_HTML)
    )
    respx.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "prop": "pageprops", "titles": "Sven_Hedin", "format": "json"},
    ).mock(return_value=httpx.Response(200, json={"query": {"pages": {}}}))
    cand = SourceCandidate(
        source_type="wikipedia",
        identifier="Sven_Hedin",
        title="Sven Hedin",
        authors=[],
        languages=["en"],
        url="https://en.wikipedia.org/wiki/Sven_Hedin",
        download_url="https://en.wikipedia.org/wiki/Sven_Hedin",
        metadata={"wikipedia_lang": "en", "wikipedia_pageid": 529134},
    )
    async with WikipediaAdapter(inter_request_delay_s=0.0) as wiki:
        raw = await wiki.acquire(cand)
    assert "Sven Hedin" in raw.content or "Central Asia" in raw.content
    assert raw.metadata.get("wikipedia_lang") == "en"
    assert raw.bytes_acquired == len(raw.content.encode("utf-8"))


@pytest.mark.asyncio
@respx.mock
async def test_wikipedia_acquire_records_wikidata_qid_in_metadata_when_present() -> None:
    respx.get("https://en.wikipedia.org/w/rest.php/v1/page/Sven_Hedin/html").mock(
        return_value=httpx.Response(200, text=_FIXTURE_HTML)
    )
    api_json = {
        "query": {
            "pages": {
                "529134": {
                    "pageprops": {"wikibase_item": "Q154759"},
                }
            }
        }
    }
    respx.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "prop": "pageprops", "titles": "Sven_Hedin", "format": "json"},
    ).mock(return_value=httpx.Response(200, json=api_json))
    cand = SourceCandidate(
        source_type="wikipedia",
        identifier="Sven_Hedin",
        title="Sven Hedin",
        authors=[],
        languages=["en"],
        url="https://en.wikipedia.org/wiki/Sven_Hedin",
        download_url="https://en.wikipedia.org/wiki/Sven_Hedin",
        metadata={"wikipedia_lang": "en"},
    )
    async with WikipediaAdapter(inter_request_delay_s=0.0) as wiki:
        raw = await wiki.acquire(cand)
    assert raw.metadata.get("wikidata_qid") == "Q154759"


@pytest.mark.asyncio
@respx.mock
async def test_wikipedia_german_query_tries_de_first() -> None:
    respx.route(
        method="GET", url__regex=r"https://de\.wikipedia\.org/w/rest\.php/v1/search/page\?.*"
    ).mock(return_value=httpx.Response(200, json={"pages": []}))
    en_payload = {
        "pages": [
            {
                "id": 1,
                "key": "Berlin",
                "title": "Berlin",
                "excerpt": "Capital",
                "description": "City",
            }
        ]
    }
    respx.route(
        method="GET", url__regex=r"https://en\.wikipedia\.org/w/rest\.php/v1/search/page\?.*"
    ).mock(return_value=httpx.Response(200, json=en_payload))
    async with WikipediaAdapter(inter_request_delay_s=0.0) as wiki:
        cands = await wiki.search("der Berlin", limit=2)
    assert len(cands) == 1
    assert cands[0].metadata.get("wikipedia_lang") == "en"
    assert cands[0].identifier == "Berlin"
