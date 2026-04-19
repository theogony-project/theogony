"""Tests for GutenbergAdapter (Plan §2.4).

Unit tests use respx to mock httpx; no network calls. The fixture
payloads are modelled on real Gutendex responses (verified
2026-04-17) so future schema drift surfaces here, not in production.

The live integration test against Hedin Trans-Himalaya Bd. 1
(Gutenberg #43497) lives in :mod:`tests.test_acquisition_gutenberg_live`
and is gated by THEOGONY_RUN_GUTENBERG_INTEGRATION=1.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from theogony.acquisition.gutenberg import (
    DEFAULT_GUTENDEX_URL,
    GutenbergAdapter,
    _candidate_from_gutendex_book,
    _content_format_for,
    _pick_text_format,
    _primary_language,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_HEDIN_BOOK_PAYLOAD: dict[str, Any] = {
    "id": 43497,
    "title": "Trans-Himalaya: Discoveries and Adventurers in Tibet. Vol. 1 (of 2)",
    "authors": [{"name": "Hedin, Sven Anders", "birth_year": 1865, "death_year": 1952}],
    "summaries": ["A historical account..."],
    "translators": [],
    "subjects": [
        "Hedin, Sven Anders, 1865-1952 -- Travel -- China -- Tibet Autonomous Region",
        "Tibet Autonomous Region (China) -- Description and travel",
    ],
    "bookshelves": ["Category: Adventure", "Category: Travel Writing"],
    "languages": ["en"],
    "copyright": False,
    "media_type": "Text",
    "formats": {
        "text/plain; charset=utf-8": ("https://www.gutenberg.org/ebooks/43497.txt.utf-8"),
        "text/plain; charset=us-ascii": ("https://www.gutenberg.org/files/43497/43497-0.txt"),
        "text/html": "https://www.gutenberg.org/ebooks/43497.html.images",
        "application/epub+zip": "https://www.gutenberg.org/ebooks/43497.epub3.images",
    },
    "download_count": 1398,
}


_GUTENDEX_SEARCH_PAYLOAD = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [_HEDIN_BOOK_PAYLOAD],
}


_HEDIN_SAMPLE_TEXT = (
    "*** START OF THIS PROJECT GUTENBERG EBOOK TRANS-HIMALAYA, VOL. 1 ***\n\n"
    "Trans-Himalaya: Discoveries and Adventurers in Tibet, Vol. 1\n"
    "by Sven Hedin\n\n"
    "I had long been planning a fresh journey through Tibet... "
    "the British authorities, however, were reluctant.\n\n"
    "*** END OF THIS PROJECT GUTENBERG EBOOK ***\n"
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_pick_text_format_prefers_utf8(self) -> None:
        formats = {
            "text/html": "https://example.com/h",
            "text/plain; charset=us-ascii": "https://example.com/a",
            "text/plain; charset=utf-8": "https://example.com/u",
        }
        result = _pick_text_format(formats)
        assert result is not None
        mime, url = result
        assert mime == "text/plain; charset=utf-8"
        assert url == "https://example.com/u"

    def test_pick_text_format_falls_back_to_ascii(self) -> None:
        formats = {
            "text/html": "https://example.com/h",
            "text/plain; charset=us-ascii": "https://example.com/a",
        }
        result = _pick_text_format(formats)
        assert result is not None
        mime, _ = result
        assert mime == "text/plain; charset=us-ascii"

    def test_pick_text_format_returns_none_when_no_text(self) -> None:
        formats = {"application/epub+zip": "https://example.com/e"}
        assert _pick_text_format(formats) is None

    def test_content_format_for_url_pattern(self) -> None:
        assert (
            _content_format_for("https://www.gutenberg.org/ebooks/43497.txt.utf-8")
            == "text/plain; charset=utf-8"
        )
        assert (
            _content_format_for("https://www.gutenberg.org/files/43497/43497-0.txt")
            == "text/plain; charset=us-ascii"
        )
        assert _content_format_for("https://example.com/random.txt") == "text/plain"

    def test_primary_language(self) -> None:
        assert _primary_language(["en", "de"]) == "en"
        assert _primary_language([]) is None


class TestCandidateProjection:
    def test_full_payload_roundtrips(self) -> None:
        cand = _candidate_from_gutendex_book(_HEDIN_BOOK_PAYLOAD)
        assert cand is not None
        assert cand.source_type == "gutenberg"
        assert cand.identifier == "43497"
        assert cand.title.startswith("Trans-Himalaya")
        assert cand.authors == ["Hedin, Sven Anders"]
        assert cand.languages == ["en"]
        assert cand.url == "https://www.gutenberg.org/ebooks/43497"
        assert cand.download_url == "https://www.gutenberg.org/ebooks/43497.txt.utf-8"
        assert cand.metadata["download_count"] == 1398

    def test_skips_when_no_text_format(self) -> None:
        payload = {**_HEDIN_BOOK_PAYLOAD, "formats": {"text/html": "..."}}
        assert _candidate_from_gutendex_book(payload) is None

    def test_skips_when_missing_id_or_title(self) -> None:
        assert _candidate_from_gutendex_book({"id": None, "title": "x"}) is None
        assert _candidate_from_gutendex_book({"id": 1, "title": ""}) is None

    def test_authors_strips_whitespace_and_drops_empties(self) -> None:
        payload = {
            **_HEDIN_BOOK_PAYLOAD,
            "authors": [
                {"name": "  A. Author  "},
                {"name": ""},
                {"name": "B. Other"},
            ],
        }
        cand = _candidate_from_gutendex_book(payload)
        assert cand is not None
        assert cand.authors == ["A. Author", "B. Other"]


# ---------------------------------------------------------------------------
# search() — respx-mocked
# ---------------------------------------------------------------------------


class TestGetById:
    @respx.mock
    async def test_returns_candidate_for_existing_id(self) -> None:
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/43497").mock(
            return_value=httpx.Response(200, json=_HEDIN_BOOK_PAYLOAD)
        )
        async with GutenbergAdapter() as adapter:
            cand = await adapter.get_by_id("43497")
        assert cand.identifier == "43497"
        assert cand.title.startswith("Trans-Himalaya")
        assert cand.download_url is not None

    @respx.mock
    async def test_accepts_int_id(self) -> None:
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/43497").mock(
            return_value=httpx.Response(200, json=_HEDIN_BOOK_PAYLOAD)
        )
        async with GutenbergAdapter() as adapter:
            cand = await adapter.get_by_id(43497)
        assert cand.identifier == "43497"

    @respx.mock
    async def test_raises_value_error_for_book_without_text_format(self) -> None:
        no_text = {**_HEDIN_BOOK_PAYLOAD, "formats": {"text/html": "..."}}
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/99").mock(
            return_value=httpx.Response(200, json=no_text)
        )
        async with GutenbergAdapter() as adapter:
            with pytest.raises(ValueError, match="no plain-text format"):
                await adapter.get_by_id("99")

    @respx.mock
    async def test_propagates_404(self) -> None:
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/99999999").mock(
            return_value=httpx.Response(404, json={"detail": "Not found."})
        )
        async with GutenbergAdapter(retry_attempts=1) as adapter:
            with pytest.raises(httpx.HTTPStatusError):
                await adapter.get_by_id("99999999")


class TestSearch:
    @respx.mock
    async def test_returns_mapped_candidates(self) -> None:
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/", params={"search": "Tibet"}).mock(
            return_value=httpx.Response(200, json=_GUTENDEX_SEARCH_PAYLOAD)
        )
        async with GutenbergAdapter() as adapter:
            cands = await adapter.search("Tibet")
        assert len(cands) == 1
        assert cands[0].title.startswith("Trans-Himalaya")
        assert cands[0].identifier == "43497"

    @respx.mock
    async def test_limit_caps_results(self) -> None:
        many = {"results": [_HEDIN_BOOK_PAYLOAD] * 5}
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/").mock(
            return_value=httpx.Response(200, json=many)
        )
        async with GutenbergAdapter() as adapter:
            cands = await adapter.search("Tibet", limit=3)
        assert len(cands) == 3

    @respx.mock
    async def test_zero_limit_returns_empty_without_request(self) -> None:
        # No respx route — if the adapter tries to GET, respx raises.
        async with GutenbergAdapter() as adapter:
            cands = await adapter.search("Tibet", limit=0)
        assert cands == []

    @respx.mock
    async def test_skips_non_text_books_in_results(self) -> None:
        non_text = {**_HEDIN_BOOK_PAYLOAD, "id": 99, "formats": {"text/html": "..."}}
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/").mock(
            return_value=httpx.Response(200, json={"results": [non_text, _HEDIN_BOOK_PAYLOAD]})
        )
        async with GutenbergAdapter() as adapter:
            cands = await adapter.search("Tibet")
        assert {c.identifier for c in cands} == {"43497"}


# ---------------------------------------------------------------------------
# acquire() — respx-mocked
# ---------------------------------------------------------------------------


class TestAcquire:
    @respx.mock
    async def test_downloads_text_and_populates_raw_content(self) -> None:
        cand = _candidate_from_gutendex_book(_HEDIN_BOOK_PAYLOAD)
        assert cand is not None
        respx.get(cand.download_url).mock(  # type: ignore[arg-type]
            return_value=httpx.Response(200, text=_HEDIN_SAMPLE_TEXT)
        )
        # Disable inter-request delay so the unit test runs instantly.
        async with GutenbergAdapter(inter_request_delay_s=0.0) as adapter:
            raw = await adapter.acquire(cand)
        assert raw.source_type == "gutenberg"
        assert raw.identifier == "43497"
        assert raw.title == cand.title
        assert raw.authors == cand.authors
        assert raw.language == "en"
        assert raw.content == _HEDIN_SAMPLE_TEXT
        assert raw.content_format == "text/plain; charset=utf-8"
        assert raw.url == cand.url
        assert raw.bytes_acquired == len(_HEDIN_SAMPLE_TEXT.encode("utf-8"))
        assert raw.metadata["download_url"] == cand.download_url
        assert raw.metadata["http_status"] == 200

    async def test_rejects_non_gutenberg_candidate(self) -> None:
        from theogony.acquisition.base import SourceCandidate

        bad = SourceCandidate(
            source_type="web",
            identifier="example.com",
            title="x",
            download_url="https://example.com/x",
        )
        async with GutenbergAdapter() as adapter:
            with pytest.raises(ValueError, match="cannot acquire"):
                await adapter.acquire(bad)

    async def test_rejects_candidate_without_download_url(self) -> None:
        from theogony.acquisition.base import SourceCandidate

        bad = SourceCandidate(
            source_type="gutenberg",
            identifier="43497",
            title="x",
            download_url=None,
        )
        async with GutenbergAdapter() as adapter:
            with pytest.raises(ValueError, match="no download_url"):
                await adapter.acquire(bad)

    @respx.mock
    async def test_us_ascii_url_sets_correct_format(self) -> None:
        ascii_payload: dict[str, Any] = {
            **_HEDIN_BOOK_PAYLOAD,
            "id": 100,
            "formats": {
                "text/plain; charset=us-ascii": ("https://www.gutenberg.org/files/100/100-0.txt")
            },
        }
        cand = _candidate_from_gutendex_book(ascii_payload)
        assert cand is not None
        assert cand.download_url is not None
        respx.get(cand.download_url).mock(
            return_value=httpx.Response(200, text="ascii-only content")
        )
        async with GutenbergAdapter(inter_request_delay_s=0.0) as adapter:
            raw = await adapter.acquire(cand)
        assert raw.content_format == "text/plain; charset=us-ascii"


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


class TestRetry:
    @respx.mock
    async def test_retries_on_503_then_succeeds(self) -> None:
        cand = _candidate_from_gutendex_book(_HEDIN_BOOK_PAYLOAD)
        assert cand is not None
        assert cand.download_url is not None
        route = respx.get(cand.download_url).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, text="recovered"),
            ]
        )
        async with GutenbergAdapter(
            inter_request_delay_s=0.0,
            retry_backoff_s=0.0,  # don't actually wait between retries in tests
        ) as adapter:
            raw = await adapter.acquire(cand)
        assert raw.content == "recovered"
        assert route.call_count == 2

    @respx.mock
    async def test_gives_up_after_max_attempts(self) -> None:
        cand = _candidate_from_gutendex_book(_HEDIN_BOOK_PAYLOAD)
        assert cand is not None
        assert cand.download_url is not None
        respx.get(cand.download_url).mock(return_value=httpx.Response(503))
        async with GutenbergAdapter(
            inter_request_delay_s=0.0,
            retry_backoff_s=0.0,
            retry_attempts=2,
        ) as adapter:
            with pytest.raises(httpx.HTTPStatusError):
                await adapter.acquire(cand)

    @respx.mock
    async def test_retries_on_transport_error(self) -> None:
        cand = _candidate_from_gutendex_book(_HEDIN_BOOK_PAYLOAD)
        assert cand is not None
        assert cand.download_url is not None
        route = respx.get(cand.download_url).mock(
            side_effect=[
                httpx.ConnectError("nope"),
                httpx.Response(200, text="recovered"),
            ]
        )
        async with GutenbergAdapter(inter_request_delay_s=0.0, retry_backoff_s=0.0) as adapter:
            raw = await adapter.acquire(cand)
        assert raw.content == "recovered"
        assert route.call_count == 2


# ---------------------------------------------------------------------------
# Lifecycle / context-manager
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_aclose_closes_owned_client(self) -> None:
        adapter = GutenbergAdapter()
        client = adapter._ensure_client()
        assert not client.is_closed
        await adapter.aclose()
        assert client.is_closed

    async def test_aclose_does_not_close_injected_client(self) -> None:
        client = httpx.AsyncClient()
        adapter = GutenbergAdapter(client=client)
        await adapter.aclose()
        assert not client.is_closed
        await client.aclose()

    async def test_async_context_manager(self) -> None:
        adapter: GutenbergAdapter
        async with GutenbergAdapter() as a:
            adapter = a
            client = adapter._ensure_client()
            assert not client.is_closed
        # Exiting the context closes the owned client.
        assert client.is_closed


# ---------------------------------------------------------------------------
# Politeness
# ---------------------------------------------------------------------------


class TestPoliteness:
    @respx.mock
    async def test_user_agent_is_sent(self) -> None:
        respx.get(f"{DEFAULT_GUTENDEX_URL}/books/").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        async with GutenbergAdapter() as adapter:
            await adapter.search("anything")
        call = respx.calls.last
        assert call is not None
        ua = call.request.headers["user-agent"]
        assert "theogony" in ua.lower()
        assert "github.com/theogony-project" in ua

    @respx.mock
    async def test_inter_request_delay_serialises_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Replace asyncio.sleep with a tracker so we don't actually wait
        # but can verify it was called with a positive duration.
        slept: list[float] = []

        async def _fake_sleep(d: float) -> None:
            slept.append(d)

        monkeypatch.setattr("theogony.acquisition.gutenberg.asyncio.sleep", _fake_sleep)

        cand = _candidate_from_gutendex_book(_HEDIN_BOOK_PAYLOAD)
        assert cand is not None
        assert cand.download_url is not None
        respx.get(cand.download_url).mock(return_value=httpx.Response(200, text="x"))
        async with GutenbergAdapter(inter_request_delay_s=2.0) as adapter:
            await adapter.acquire(cand)
            await adapter.acquire(cand)
        # First call has no prior request so no sleep; second call should
        # see a positive sleep close to 2.0s (less if the test machinery
        # took non-zero wall time between the two acquire() calls).
        assert any(0.0 < s <= 2.0 for s in slept), slept


# ---------------------------------------------------------------------------
# Smoke: candidate.json against real Gutendex schema
# ---------------------------------------------------------------------------


class TestGutendexSchemaSnapshot:
    """Pin the assumed Gutendex shape so future schema drift surfaces here.

    If Gutendex starts returning a different `formats` mime, or removes
    the `download_count` field, etc., this test will catch it the next
    time we update the snapshot — long before production sees it.
    """

    def test_hedin_payload_parses(self) -> None:
        # round-trip JSON to make sure our fixture is valid JSON, then
        # project to a SourceCandidate.
        roundtripped = json.loads(json.dumps(_HEDIN_BOOK_PAYLOAD))
        cand = _candidate_from_gutendex_book(roundtripped)
        assert cand is not None
        assert cand.identifier == "43497"
