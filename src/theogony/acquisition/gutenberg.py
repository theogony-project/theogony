"""
GutenbergAdapter — discover and fetch books from Project Gutenberg.

Plan §2.4 lists this as the only acquisition adapter for Gen 1.
Discovery uses the Gutendex API (`https://gutendex.com`), a thin,
fast metadata layer over the Project Gutenberg catalogue with no
robots restrictions. Content download uses Project Gutenberg's
canonical text URLs from the candidate's ``formats`` map.

Politeness (Project Gutenberg robot policy, 2026):
- A descriptive User-Agent identifying Theogony with a contact URL.
- A configurable per-request delay (default 2 s) between sequential
  Gutenberg downloads — matches PG's published recommendation. The
  delay applies to ``acquire`` calls only; Gutendex queries are not
  rate-limited.
- Exponential-backoff retry on 503 / 429 responses.

For Gen 1's single-book demo (~1 download per ingest), this comfortably
stays inside PG's terms of service. Bulk ingest at any scale belongs
to PHX-0024 (self-hosted Wikidata mirror is its sibling) or to
acquisition via PG mirrors.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from theogony import __version__
from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.config.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

log = get_logger("acquisition.gutenberg")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_GUTENDEX_URL = "https://gutendex.com"
DEFAULT_USER_AGENT = (
    f"theogony/{__version__} "
    "(+https://github.com/theogony-project/theogony; "
    "open knowledge infrastructure)"
)
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_INTER_REQUEST_DELAY_S = 2.0  # PG robot policy recommendation
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_S = 1.0

# Preferred plain-text formats from Gutendex `formats` map, in order.
# UTF-8 first; fall back to us-ascii (some older PG books only ship that).
_PREFERRED_TEXT_FORMATS = (
    "text/plain; charset=utf-8",
    "text/plain; charset=us-ascii",
    "text/plain",
)

_RETRYABLE_STATUS = {429, 502, 503, 504}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _author_names(authors: list[dict[str, Any]]) -> list[str]:
    """Gutendex returns authors as ``[{"name": "...", "birth_year": ..., "death_year": ...}, ...]``.

    We keep the displayed-name string verbatim — for Hedin this is
    "Hedin, Sven Anders", which is the canonical form the source uses
    and the form a reader can disambiguate against Wikidata.
    """
    return [a.get("name", "").strip() for a in authors if a.get("name")]


def _primary_language(languages: list[str]) -> str | None:
    """Pick the first declared language; None when the source declares none."""
    return languages[0] if languages else None


def _pick_text_format(formats: Mapping[str, str]) -> tuple[str, str] | None:
    """Return ``(content_format, url)`` for the best plain-text format, or None.

    Uses the order in :data:`_PREFERRED_TEXT_FORMATS`. The mime keys
    in Gutendex are exact strings (with the charset suffix), so we
    look them up directly rather than trying to parse.
    """
    for mime in _PREFERRED_TEXT_FORMATS:
        url = formats.get(mime)
        if url:
            return mime, url
    return None


def _candidate_from_gutendex_book(book: dict[str, Any]) -> SourceCandidate | None:
    """Project a Gutendex `/books/<id>` payload into a SourceCandidate.

    Returns None when the book has no plain-text format we can fetch
    — better to skip silently than to produce a candidate ``acquire``
    will then reject.
    """
    book_id = book.get("id")
    title = book.get("title")
    if book_id is None or not title:
        return None
    formats: Mapping[str, str] = book.get("formats", {})
    pick = _pick_text_format(formats)
    if pick is None:
        return None
    _, download_url = pick
    return SourceCandidate(
        source_type="gutenberg",
        identifier=str(book_id),
        title=title,
        authors=_author_names(book.get("authors", [])),
        languages=list(book.get("languages", [])),
        url=f"https://www.gutenberg.org/ebooks/{book_id}",
        download_url=download_url,
        metadata={
            "download_count": book.get("download_count"),
            "subjects": book.get("subjects", []),
            "bookshelves": book.get("bookshelves", []),
            "copyright": book.get("copyright"),
            "media_type": book.get("media_type"),
            "formats": dict(formats),
        },
    )


def _content_format_for(url: str) -> str:
    """Infer content_format for a Gutenberg text URL.

    The url's filename suffix is the ground truth — `pg<id>-0.txt` is
    us-ascii by convention, `<id>.txt.utf-8` is utf-8. We could parse
    the response's Content-Type instead, but PG's headers are not
    always reliable; the URL is.
    """
    if "utf-8" in url:
        return "text/plain; charset=utf-8"
    if "us-ascii" in url or url.endswith("-0.txt"):
        return "text/plain; charset=us-ascii"
    return "text/plain"


# ---------------------------------------------------------------------------
# GutenbergAdapter
# ---------------------------------------------------------------------------


class GutenbergAdapter:
    """Acquire Project Gutenberg books via the Gutendex catalogue.

    Use as a context manager so the underlying ``httpx.AsyncClient``
    is closed cleanly::

        async with GutenbergAdapter() as adapter:
            candidates = await adapter.search("Tibet")
            raw = await adapter.acquire(candidates[0])

    Or pass an existing client (e.g. for tests or for sharing
    connection pools across adapters)::

        async with httpx.AsyncClient() as client:
            adapter = GutenbergAdapter(client=client)
            ...
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        gutendex_url: str = DEFAULT_GUTENDEX_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        inter_request_delay_s: float = DEFAULT_INTER_REQUEST_DELAY_S,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
    ) -> None:
        self._gutendex_url = gutendex_url.rstrip("/")
        self._user_agent = user_agent
        self._timeout_s = timeout_s
        self._inter_request_delay_s = inter_request_delay_s
        self._retry_attempts = max(1, retry_attempts)
        self._retry_backoff_s = retry_backoff_s
        self._client = client
        self._owns_client = client is None
        self._lock = asyncio.Lock()
        self._last_request_at: float | None = None

    # ----- protocol surface ------------------------------------------------

    @property
    def source_type(self) -> str:
        return "gutenberg"

    def supports(self, source_type: str) -> bool:
        return source_type == "gutenberg"

    async def get_by_id(self, book_id: str | int) -> SourceCandidate:
        """Look up a single book by its Project Gutenberg ID via Gutendex.

        Hits ``/books/{id}`` directly — cheaper and more deterministic
        than ``search`` (which is text-keyword indexing). Used by the
        ``theogony ingest <book_id>`` CLI command (Plan §3.7).

        Raises:
            ValueError: when Gutendex returns 404, or when the book
                exists but has no plain-text format we can fetch.
            httpx.HTTPStatusError: on persistent transport failure
                after exhausted retries.
        """
        client = self._ensure_client()
        url = f"{self._gutendex_url}/books/{book_id}"
        response = await self._request_with_retry(client, "GET", url)
        payload = response.json()
        # Gutendex's /books/{id} returns the book object directly
        # (not wrapped in a results list).
        cand = _candidate_from_gutendex_book(payload)
        if cand is None:
            raise ValueError(
                f"Gutenberg book id={book_id!r} exists in Gutendex but "
                "has no plain-text format we can ingest"
            )
        log.info("gutendex get_by_id id=%s title=%r", book_id, cand.title)
        return cand

    async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
        """Search Gutendex for books matching ``query``.

        Maps the JSON payload's ``results`` array into SourceCandidate
        objects. Skips books that have no plain-text format (rare;
        usually image-only scans or audio).
        """
        if limit <= 0:
            return []
        client = self._ensure_client()
        params = {"search": query}
        url = f"{self._gutendex_url}/books/"
        response = await self._request_with_retry(client, "GET", url, params=params)
        payload = response.json()
        results = payload.get("results", [])
        candidates: list[SourceCandidate] = []
        for book in results:
            cand = _candidate_from_gutendex_book(book)
            if cand is None:
                continue
            candidates.append(cand)
            if len(candidates) >= limit:
                break
        log.info("gutendex search query=%r returned=%d", query, len(candidates))
        return candidates

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        """Download the candidate's plain-text content.

        Errors:
            ValueError if the candidate is not a Gutenberg candidate
            or has no usable download URL.
            httpx.HTTPStatusError on persistent transport failure.
        """
        if not self.supports(candidate.source_type):
            raise ValueError(
                f"GutenbergAdapter cannot acquire source_type={candidate.source_type!r}"
            )
        download_url = candidate.download_url
        if not download_url:
            raise ValueError(
                f"candidate {candidate.identifier} has no download_url; "
                "search() should have populated this"
            )
        client = self._ensure_client()
        await self._respect_rate_limit()
        response = await self._request_with_retry(client, "GET", download_url)
        # Pin charset from the URL rather than the (sometimes wrong)
        # response Content-Type. PG's plain-text URLs encode their
        # charset in the path itself.
        content_format = _content_format_for(download_url)
        # httpx decodes per response.encoding; we override based on URL.
        if "utf-8" in content_format:
            response.encoding = "utf-8"
        elif "us-ascii" in content_format:
            response.encoding = "us-ascii"
        text = response.text
        raw = RawContent(
            source_type="gutenberg",
            identifier=candidate.identifier,
            title=candidate.title,
            authors=list(candidate.authors),
            language=_primary_language(candidate.languages),
            content=text,
            content_format=content_format,
            url=candidate.url,
            acquired_at=datetime.now(UTC),
            bytes_acquired=len(text.encode("utf-8")),
            metadata={
                **dict(candidate.metadata),
                "download_url": download_url,
                "http_status": response.status_code,
            },
        )
        log.info(
            "acquired gutenberg id=%s title=%r bytes=%d",
            candidate.identifier,
            candidate.title,
            raw.bytes_acquired,
        )
        return raw

    async def aclose(self) -> None:
        """Close the owned HTTP client. No-op when client was injected."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> GutenbergAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # ----- internals -------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_s,
                follow_redirects=True,
            )
        return self._client

    async def _respect_rate_limit(self) -> None:
        """Sleep so consecutive Gutenberg downloads are at least ``inter_request_delay_s`` apart.

        Implemented via a lock so concurrent ``acquire`` calls
        serialise their delays — matters once Gen 2 fans out across
        many books per ingest run.
        """
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

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """GET/POST with exponential-backoff retry on retryable status codes."""
        last_exc: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                response = await client.request(method, url, params=params)
            except httpx.RequestError as exc:
                last_exc = exc
                wait = self._retry_backoff_s * (2 ** (attempt - 1))
                log.warning(
                    "transport error url=%s attempt=%d/%d err=%s — retrying in %.1fs",
                    url,
                    attempt,
                    self._retry_attempts,
                    exc,
                    wait,
                )
                if attempt < self._retry_attempts:
                    await asyncio.sleep(wait)
                continue
            if response.status_code in _RETRYABLE_STATUS:
                wait = self._retry_backoff_s * (2 ** (attempt - 1))
                log.warning(
                    "retryable status=%d url=%s attempt=%d/%d — retrying in %.1fs",
                    response.status_code,
                    url,
                    attempt,
                    self._retry_attempts,
                    wait,
                )
                if attempt < self._retry_attempts:
                    await asyncio.sleep(wait)
                    continue
            response.raise_for_status()
            return response
        if last_exc is not None:
            raise last_exc
        # Last attempt was a retryable status that we exhausted; re-raise
        # by triggering raise_for_status one final time.
        response.raise_for_status()
        return response
