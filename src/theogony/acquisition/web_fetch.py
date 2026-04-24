"""WebFetchAdapter — HTTPS fetch with robots.txt and trafilatura (W12)."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from theogony import __version__
from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.config.logging import get_logger

log = get_logger("acquisition.web_fetch")

DEFAULT_USER_AGENT = (
    f"theogony/{__version__} "
    "(+https://github.com/theogony-project/theogony; "
    "open knowledge infrastructure)"
)
DEFAULT_TIMEOUT_S = 30.0
_ROBOTS_TTL_S = 3600
_MAX_BODY_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 5
_DEFAULT_INTER_REQUEST_DELAY_S = 2.0


class RobotsDisallowedError(Exception):
    """robots.txt disallows our user-agent for this URL."""


class ContentExtractionFailedError(Exception):
    """trafilatura produced no usable text from the response body."""


@dataclass
class _CachedRobots:
    parser: RobotFileParser
    fetched_loop: float


def _sha16(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _hostname_has_registered_tld(host: str) -> bool:
    host = host.strip().lower().strip(".")
    if not host or "." not in host:
        return False
    tld = host.rsplit(".", 1)[-1]
    if len(tld) < 2:
        return False
    return all(c.isalnum() or c == "-" for c in tld)


class WebFetchAdapter:
    """Generic HTTPS fetch with urllib.robotparser + trafilatura."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        inter_request_delay_s: float = _DEFAULT_INTER_REQUEST_DELAY_S,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_s = timeout_s
        self._inter_request_delay_s = inter_request_delay_s
        self._client = client
        self._owns_client = client is None
        self._robots_cache: dict[str, _CachedRobots] = {}
        self._robots_lock = asyncio.Lock()
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_request_mono_by_host: dict[str, float] = {}

    @property
    def source_type(self) -> str:
        return "web"

    def supports(self, source_type: str) -> bool:
        return source_type == "web"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        del query, limit
        raise NotImplementedError("WebFetchAdapter does not implement search")

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        if not self.supports(candidate.source_type):
            raise ValueError(
                f"WebFetchAdapter cannot acquire source_type={candidate.source_type!r}"
            )
        import trafilatura

        url = candidate.url or candidate.download_url
        if not url:
            raise ValueError("web candidate requires url")
        if not str(url).lower().startswith("https://"):
            raise ValueError("only https:// URLs are allowed for web fetch")

        parsed = urlparse(str(url))
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("invalid host or TLD for web fetch")
        try:
            import ipaddress

            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            pass
        else:
            raise ValueError("IP-literal hosts are not allowed for web fetch")
        if not _hostname_has_registered_tld(host):
            raise ValueError("invalid host or TLD for web fetch")

        client = self._ensure_client()
        hlock = self._host_lock(host)
        async with hlock:
            await self._pace_host(host)
            await self._robots_allow_unlocked(client, url=url, host=host)
            await self._pace_host(host)
            response = await client.get(str(url))
            response.raise_for_status()
            body = response.content
            if len(body) > _MAX_BODY_BYTES:
                raise ValueError(f"response body {len(body)} B exceeds {_MAX_BODY_BYTES} B cap")

            enc = response.encoding or "utf-8"
            html = body.decode(enc, errors="replace")
            final_url = str(response.url)
            extracted = trafilatura.extract(html, url=final_url)
            if not (extracted or "").strip():
                raise ContentExtractionFailedError("trafilatura returned empty body")

            text = extracted
            raw = RawContent(
                source_type="web",
                identifier=_sha16(str(url)),
                title=candidate.title or final_url,
                authors=list(candidate.authors),
                language=candidate.languages[0] if candidate.languages else None,
                content=text,
                content_format="text/plain; charset=utf-8",
                url=final_url,
                acquired_at=datetime.now(UTC),
                bytes_acquired=len(text.encode("utf-8")),
                metadata={
                    "http_status": response.status_code,
                    "final_url": final_url,
                    "content_length": len(response.content),
                },
            )
            self._touch_host(host)
            log.info("acquired web id=%s bytes=%d", raw.identifier, raw.bytes_acquired)
            return raw

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> WebFetchAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_s,
                follow_redirects=True,
                max_redirects=_MAX_REDIRECTS,
            )
        return self._client

    def _host_lock(self, host: str) -> asyncio.Lock:
        if host not in self._host_locks:
            self._host_locks[host] = asyncio.Lock()
        return self._host_locks[host]

    async def _pace_host(self, host: str) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()
        last = self._last_request_mono_by_host.get(host)
        if last is not None and self._inter_request_delay_s > 0:
            wait = self._inter_request_delay_s - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)

    def _touch_host(self, host: str) -> None:
        self._last_request_mono_by_host[host] = asyncio.get_running_loop().time()

    async def _robots_allow_unlocked(
        self, client: httpx.AsyncClient, *, url: str, host: str
    ) -> None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{host}"
        robots_url = f"{origin}/robots.txt"

        parser: RobotFileParser | None = None
        loop = asyncio.get_running_loop()
        now = loop.time()
        async with self._robots_lock:
            cached = self._robots_cache.get(host)
            if cached is not None and (now - cached.fetched_loop) < _ROBOTS_TTL_S:
                parser = cached.parser

        if parser is None:
            try:
                r = await client.get(robots_url)
                raw = "" if r.status_code >= 400 else r.text
            except httpx.HTTPError:
                raw = ""
            self._touch_host(host)
            parser = RobotFileParser()
            parser.set_url(robots_url)
            await asyncio.to_thread(parser.parse, raw.splitlines())
            async with self._robots_lock:
                self._robots_cache[host] = _CachedRobots(parser=parser, fetched_loop=loop.time())

        def _can() -> bool:
            assert parser is not None
            return parser.can_fetch(self._user_agent, url)

        allowed = await asyncio.to_thread(_can)
        if not allowed:
            raise RobotsDisallowedError(f"robots.txt disallows fetch for {url!r}")


__all__ = [
    "ContentExtractionFailedError",
    "RobotsDisallowedError",
    "WebFetchAdapter",
]
