"""WikipediaAdapter — REST search + HTML fetch, trafilatura extraction (W12)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from theogony import __version__
from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.config.logging import get_logger

log = get_logger("acquisition.wikipedia")

DEFAULT_USER_AGENT = (
    f"theogony/{__version__} "
    "(+https://github.com/theogony-project/theogony; "
    "open knowledge infrastructure)"
)
DEFAULT_TIMEOUT_S = 30.0
_MAX_TEXT_BYTES = 200 * 1024

_GERMAN_STOPWORDS: frozenset[str] = frozenset(
    {
        "der",
        "die",
        "das",
        "und",
        "ist",
        "nicht",
        "ein",
        "eine",
        "was",
        "wer",
        "wann",
        "wie",
        "war",
    }
)


def _looks_german(query: str) -> bool:
    if any(ch in query for ch in "äöüßÄÖÜ"):
        return True
    tokens = {t.lower() for t in query.replace(",", " ").split() if t}
    return bool(tokens & _GERMAN_STOPWORDS)


def _truncate_utf8(text: str, max_bytes: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    return data[:max_bytes].decode("utf-8", errors="ignore")


class WikipediaAdapter:
    """Wikipedia REST API + trafilatura plain text (optional ``theogony[research]``)."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        inter_request_delay_s: float = 2.0,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_s = timeout_s
        self._inter_request_delay_s = inter_request_delay_s
        self._client = client
        self._owns_client = client is None
        self._lock = asyncio.Lock()
        self._last_request_at: float | None = None

    @property
    def source_type(self) -> str:
        return "wikipedia"

    def supports(self, source_type: str) -> bool:
        return source_type == "wikipedia"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        if limit <= 0:
            return []
        langs = ("de", "en") if _looks_german(query) else ("en",)
        for lang in langs:
            cands = await self._search_host(lang, query, limit)
            if cands:
                return cands
        return []

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        if not self.supports(candidate.source_type):
            raise ValueError(
                f"WikipediaAdapter cannot acquire source_type={candidate.source_type!r}"
            )
        import trafilatura

        lang = str(candidate.metadata.get("wikipedia_lang") or "en")
        page_key = candidate.identifier
        host = f"{lang}.wikipedia.org"
        html_path = f"/w/rest.php/v1/page/{quote(page_key, safe='')}/html"
        html_url = f"https://{host}{html_path}"

        client = self._ensure_client()
        await self._respect_rate_limit()
        html_resp = await client.get(html_url)
        html_resp.raise_for_status()
        html = html_resp.text
        extracted = trafilatura.extract(html, url=html_url) or ""
        text = _truncate_utf8(extracted, _MAX_TEXT_BYTES)
        if not text.strip():
            raise ValueError("trafilatura returned empty body for Wikipedia HTML")

        wikidata_qid = await self._fetch_wikidata_qid(client, host=host, page_key=page_key)
        meta: dict[str, Any] = {
            **dict(candidate.metadata),
            "wikipedia_lang": lang,
            "http_status": html_resp.status_code,
            "html_url": html_url,
        }
        if wikidata_qid:
            meta["wikidata_qid"] = wikidata_qid

        raw = RawContent(
            source_type="wikipedia",
            identifier=candidate.identifier,
            title=candidate.title,
            authors=list(candidate.authors),
            language=lang,
            content=text,
            content_format="text/plain; charset=utf-8",
            url=f"https://{lang}.wikipedia.org/wiki/{page_key}",
            acquired_at=datetime.now(UTC),
            bytes_acquired=len(text.encode("utf-8")),
            metadata=meta,
        )
        log.info(
            "acquired wikipedia key=%s lang=%s bytes=%d",
            page_key,
            lang,
            raw.bytes_acquired,
        )
        return raw

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> WikipediaAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_s,
                follow_redirects=True,
            )
        return self._client

    async def _respect_rate_limit(self) -> None:
        if self._inter_request_delay_s <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if self._last_request_at is not None:
                elapsed = now - self._last_request_at
                deficit = self._inter_request_delay_s - elapsed
                if deficit > 0:
                    await asyncio.sleep(deficit)
            self._last_request_at = loop.time()

    async def _search_host(self, lang: str, query: str, limit: int) -> list[SourceCandidate]:
        host = f"{lang}.wikipedia.org"
        q = urlencode({"q": query, "limit": str(limit)})
        url = f"https://{host}/w/rest.php/v1/search/page?{q}"
        client = self._ensure_client()
        await self._respect_rate_limit()
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
        pages = payload.get("pages") or []
        out: list[SourceCandidate] = []
        for p in pages:
            if not isinstance(p, dict):
                continue
            key = p.get("key")
            title = p.get("title")
            pid = p.get("id")
            if not key or not title or pid is None:
                continue
            desc = p.get("description") or ""
            excerpt = p.get("excerpt") or ""
            summary_bits = [s for s in (desc, excerpt) if s]
            summary = " — ".join(summary_bits) if summary_bits else ""
            page_url = f"https://{lang}.wikipedia.org/wiki/{key}"
            out.append(
                SourceCandidate(
                    source_type="wikipedia",
                    identifier=str(key),
                    title=str(title),
                    authors=[],
                    languages=[lang],
                    url=page_url,
                    download_url=page_url,
                    metadata={
                        "wikipedia_pageid": int(pid),
                        "wikipedia_lang": lang,
                        "estimated_bytes": _MAX_TEXT_BYTES,
                        "wikipedia_excerpt_plain": excerpt,
                        "wikipedia_description": desc,
                        "summary": summary,
                    },
                )
            )
            if len(out) >= limit:
                break
        return out

    async def _fetch_wikidata_qid(
        self, client: httpx.AsyncClient, *, host: str, page_key: str
    ) -> str | None:
        api = f"https://{host}/w/api.php"
        params = {"action": "query", "prop": "pageprops", "titles": page_key, "format": "json"}
        await self._respect_rate_limit()
        r = await client.get(api, params=params)
        r.raise_for_status()
        data = r.json()
        pages = (data.get("query") or {}).get("pages") or {}
        for _pid, page in pages.items():
            if not isinstance(page, dict):
                continue
            props = page.get("pageprops") or {}
            qid = props.get("wikibase_item")
            if isinstance(qid, str) and qid.startswith("Q") and qid[1:].isdigit():
                return qid
        return None


__all__ = ["WikipediaAdapter", "_looks_german"]
