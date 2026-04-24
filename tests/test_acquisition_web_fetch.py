"""W12 — WebFetchAdapter unit tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from theogony.acquisition.base import SourceCandidate
from theogony.acquisition.web_fetch import (
    ContentExtractionFailedError,
    RobotsDisallowedError,
    WebFetchAdapter,
)

_FIXTURE_HTML = (Path(__file__).resolve().parent / "fixtures" / "wikipedia_sample.html").read_text(
    encoding="utf-8"
)


def _web_cand(url: str) -> SourceCandidate:
    return SourceCandidate(
        source_type="web",
        identifier="deadbeef",
        title=url,
        authors=[],
        languages=[],
        url=url,
        metadata={"estimated_bytes": 1024},
    )


def _web_adapter() -> WebFetchAdapter:
    return WebFetchAdapter(inter_request_delay_s=0.0)


@pytest.mark.asyncio
async def test_web_fetch_rejects_http_url() -> None:
    adapter = _web_adapter()
    with pytest.raises(ValueError, match="https"):
        await adapter.acquire(
            _web_cand("http://example.com/page"),
        )


@pytest.mark.asyncio
async def test_web_fetch_rejects_ip_literal_host() -> None:
    adapter = _web_adapter()
    with pytest.raises(ValueError, match="IP-literal"):
        await adapter.acquire(_web_cand("https://127.0.0.1/page"))


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_respects_robots_disallow() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nDisallow: /private\n",
        )
    )
    adapter = _web_adapter()
    with pytest.raises(RobotsDisallowedError):
        await adapter.acquire(_web_cand("https://example.com/private/doc"))


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_caches_robots_per_host_for_one_hour() -> None:
    robots_body = "User-agent: *\nAllow: /\n"
    robots_route = respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_body)
    )
    respx.get("https://example.com/a").mock(return_value=httpx.Response(200, text=_FIXTURE_HTML))
    respx.get("https://example.com/b").mock(return_value=httpx.Response(200, text=_FIXTURE_HTML))
    async with WebFetchAdapter(inter_request_delay_s=0.0) as w:
        await w.acquire(_web_cand("https://example.com/a"))
        await w.acquire(_web_cand("https://example.com/b"))
    assert robots_route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_extracts_text_via_trafilatura_with_5MB_cap() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://example.com/huge").mock(
        return_value=httpx.Response(200, content=b"z" * (5 * 1024 * 1024 + 1))
    )
    adapter = _web_adapter()
    with pytest.raises(ValueError, match="exceeds"):
        await adapter.acquire(_web_cand("https://example.com/huge"))


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_records_final_url_after_redirects() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://example.com/start").mock(
        return_value=httpx.Response(302, headers={"Location": "https://example.com/final"})
    )
    respx.get("https://example.com/final").mock(
        return_value=httpx.Response(200, text=_FIXTURE_HTML)
    )
    async with WebFetchAdapter(inter_request_delay_s=0.0) as w:
        raw = await w.acquire(_web_cand("https://example.com/start"))
    assert raw.metadata.get("final_url") == "https://example.com/final"
    assert raw.url == "https://example.com/final"


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_raises_content_extraction_failed_on_empty_trafilatura() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
    )
    respx.get("https://example.com/empty.html").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    async with WebFetchAdapter(inter_request_delay_s=0.0) as w:
        with pytest.raises(ContentExtractionFailedError):
            await w.acquire(_web_cand("https://example.com/empty.html"))
