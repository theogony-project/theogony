"""W11 — WikidataAdapter."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from theogony.acquisition.wikidata import WikidataAdapter
from theogony.extraction.wikidata_client import DEFAULT_API_URL, WikidataClient


def _wbsearch_response(hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {"searchinfo": {"search": "test"}, "search": hits, "success": 1}


def _wbgetentities_response(entities: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"entities": entities, "success": 1}


@pytest.mark.asyncio
@respx.mock
async def test_wikidata_adapter_search_by_name_returns_candidates() -> None:
    respx.get(DEFAULT_API_URL).mock(
        return_value=httpx.Response(
            200,
            json=_wbsearch_response(
                [
                    {
                        "id": "Q205184",
                        "label": "Sven Hedin",
                        "description": "Swedish geographer and explorer",
                        "match": {"text": "Sven Hedin", "language": "en"},
                    }
                ]
            ),
        )
    )
    async with WikidataClient(inter_request_delay_s=0) as client:
        ad = WikidataAdapter(client=client)
        cands = await ad.search("Sven Hedin", limit=5)
    assert len(cands) == 1
    assert cands[0].identifier == "Q205184"
    assert cands[0].download_url == "https://www.wikidata.org/wiki/Q205184"


@pytest.mark.asyncio
@respx.mock
async def test_wikidata_adapter_search_by_qid_returns_one_candidate() -> None:
    respx.get(DEFAULT_API_URL).mock(
        return_value=httpx.Response(
            200,
            json=_wbgetentities_response(
                {
                    "Q205184": {
                        "labels": {"en": {"language": "en", "value": "Sven Hedin"}},
                        "aliases": {},
                    }
                }
            ),
        )
    )
    async with WikidataClient(inter_request_delay_s=0) as client:
        ad = WikidataAdapter(client=client)
        cands = await ad.search("Q205184", limit=5)
    assert len(cands) == 1
    assert cands[0].identifier == "Q205184"


@pytest.mark.asyncio
@respx.mock
async def test_wikidata_adapter_acquire_builds_raw_content_with_qid_metadata() -> None:
    respx.get(DEFAULT_API_URL).mock(
        return_value=httpx.Response(
            200,
            json=_wbgetentities_response(
                {
                    "Q205184": {
                        "labels": {
                            "en": {"language": "en", "value": "Sven Hedin"},
                            "de": {"language": "de", "value": "Sven Hedin"},
                        },
                        "aliases": {"en": [{"language": "en", "value": "Hedin"}]},
                    }
                }
            ),
        )
    )
    async with WikidataClient(inter_request_delay_s=0) as client:
        ad = WikidataAdapter(client=client)
        raw = await ad.acquire((await ad.search("Q205184", limit=1))[0])
    assert raw.source_type == "wikidata"
    assert raw.metadata.get("wikidata_qid") == "Q205184"
    assert "Q205184" in raw.content
    assert raw.bytes_acquired > 0
