"""Unit tests for :class:`WikidataCache` and the cache-aware
:class:`WikidataClient` wiring (W6, PR #33).

Two layers of coverage live here:

1. **Cache module direct tests.** Exercise :class:`WikidataCache`'s
   per-namespace get/put round-trips with the actual DTOs the client
   stores (``WikidataCandidate``, ``BioFacts``, sets of P31 Q-IDs).
2. **Cache-aware client integration.** Hit each of the four
   :class:`WikidataClient` reads twice: first call goes to mocked
   HTTP, second is served from cache without the wire being touched.
   The partial-batch tests assert that hits *and* misses can coexist
   in one call: the misses fan through to upstream while the hits
   stay local. The persistence test bridges two client lifetimes
   over the same SQLite file.

Network is mocked with ``respx`` throughout — these tests never
contact real Wikidata. The existing live smoke
(``tests/test_extraction_resolve_live.py``) stays gated and
unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from theogony.extraction.wikidata_cache import WikidataCache
from theogony.extraction.wikidata_client import (
    DEFAULT_API_URL,
    DEFAULT_SPARQL_URL,
    BioFacts,
    WikidataCandidate,
    WikidataClient,
)

# ---------------------------------------------------------------- helpers
# Mirror the response shapes from test_extraction_wikidata_client.py
# verbatim — keeping the same skeletons here means the integration
# tests below assert against the real WikidataClient parser, not a
# bespoke happy-path stub.


def _wbsearch_response(hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {"searchinfo": {"search": "test"}, "search": hits, "success": 1}


def _wbgetentities_response(entities: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"entities": entities, "success": 1}


def _sparql_p31_response(rows: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "head": {"vars": ["item", "type"]},
        "results": {
            "bindings": [
                {
                    "item": {"type": "uri", "value": f"http://www.wikidata.org/entity/{item}"},
                    "type": {"type": "uri", "value": f"http://www.wikidata.org/entity/{tp}"},
                }
                for item, tp in rows
            ]
        },
    }


def _bio_facts_response(rows: list[dict[str, Any]]) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = []
    for row in rows:
        binding: dict[str, Any] = {}
        item = row.get("item")
        if item:
            binding["item"] = {"type": "uri", "value": f"http://www.wikidata.org/entity/{item}"}
        for key in ("birth", "death"):
            val = row.get(key)
            if val is not None:
                binding[key] = {"type": "literal", "value": val}
        for key in ("occupationLabel", "birthPlaceLabel", "workLocationLabel"):
            val = row.get(key)
            if val is not None:
                binding[key] = {"type": "literal", "value": val}
        bindings.append(binding)
    return {
        "head": {
            "vars": [
                "item",
                "birth",
                "death",
                "occupationLabel",
                "birthPlaceLabel",
                "workLocationLabel",
            ]
        },
        "results": {"bindings": bindings},
    }


# ============================================================ cache module


class TestWikidataCacheModule:
    """Exercise the cache module in isolation, no client involved."""

    def test_search_round_trip_in_memory(self) -> None:
        with WikidataCache() as cache:
            assert cache.get_search("Sven Hedin", language="en", limit=10) is None
            cands = [
                WikidataCandidate(qid="Q154759", label="Sven Hedin", language="en"),
                WikidataCandidate(qid="Q42", label="Other Hedin", language="en"),
            ]
            cache.put_search("Sven Hedin", language="en", limit=10, candidates=cands)
            got = cache.get_search("Sven Hedin", language="en", limit=10)
            assert got is not None
            assert [c.qid for c in got] == ["Q154759", "Q42"]

    def test_search_key_is_normalised_for_case_and_whitespace(self) -> None:
        # The brief asks for "fully normalised mention string". Casing
        # and internal-whitespace differences must collapse to one
        # cache entry — Wikidata's wbsearchentities is itself
        # case- and whitespace-tolerant, so this loses no upstream
        # distinction.
        with WikidataCache() as cache:
            cache.put_search(
                "Sven Hedin",
                language="en",
                limit=10,
                candidates=[WikidataCandidate(qid="Q154759", label="Sven Hedin", language="en")],
            )
            assert cache.get_search("sven hedin", language="en", limit=10) is not None
            assert cache.get_search("  Sven  Hedin  ", language="en", limit=10) is not None

    def test_search_empty_success_is_cacheable(self) -> None:
        # Wikidata cleanly answered "no hits"; we cache that so reruns
        # don't re-probe.
        with WikidataCache() as cache:
            cache.put_search("Nonsense Mention", language="en", limit=10, candidates=[])
            got = cache.get_search("Nonsense Mention", language="en", limit=10)
            assert got == []

    def test_labels_aliases_round_trip(self) -> None:
        with WikidataCache() as cache:
            assert cache.get_labels_aliases("Q154759", languages=["en", "de"]) is None
            cache.put_labels_aliases(
                "Q154759",
                languages=["en", "de"],
                per_language={"en": ["Sven Hedin", "Hedin"], "de": ["Sven Hedin"]},
            )
            # Order-insensitive language tuple: ["de","en"] hits the
            # same entry as ["en","de"]. Important for callers that
            # don't sort their language list.
            got = cache.get_labels_aliases("Q154759", languages=["de", "en"])
            assert got == {"en": ["Sven Hedin", "Hedin"], "de": ["Sven Hedin"]}

    def test_types_round_trip(self) -> None:
        with WikidataCache() as cache:
            assert cache.get_types("Q42") is None
            cache.put_types("Q42", types={"Q5", "Q486972"})
            got = cache.get_types("Q42")
            assert got == {"Q5", "Q486972"}
            # Empty set caches as empty success — distinct from None.
            cache.put_types("Q999", types=set())
            assert cache.get_types("Q999") == set()

    def test_bio_facts_round_trip(self) -> None:
        with WikidataCache() as cache:
            facts = BioFacts(
                qid="Q154759",
                birth_date="1865-02-19T00:00:00Z",
                occupations=["explorer", "geographer"],
            )
            assert cache.get_bio_facts("Q154759", language="en") is None
            cache.put_bio_facts("Q154759", language="en", facts=facts)
            got = cache.get_bio_facts("Q154759", language="en")
            assert got is not None
            assert got.birth_date == "1865-02-19T00:00:00Z"
            assert got.occupations == ["explorer", "geographer"]
            # Same Q-ID different language is a separate entry — the
            # SPARQL queries fetch labels in `language`, so the cached
            # payload is only valid for that exact language.
            assert cache.get_bio_facts("Q154759", language="de") is None

    def test_persists_across_open_close_close_open(self, tmp_path: Path) -> None:
        # A second WikidataCache instance reading the same file must
        # see writes from the first.
        path = tmp_path / "wikidata_cache.sqlite"
        with WikidataCache(path) as cache_a:
            cache_a.put_types("Q42", types={"Q5"})
        assert path.exists()
        with WikidataCache(path) as cache_b:
            assert cache_b.get_types("Q42") == {"Q5"}

    def test_row_count_namespaced(self) -> None:
        with WikidataCache() as cache:
            cache.put_types("Q1", types={"Q5"})
            cache.put_types("Q2", types={"Q5"})
            cache.put_search("x", language="en", limit=10, candidates=[])
            assert cache.row_count() == 3
            assert cache.row_count(namespace="types") == 2
            assert cache.row_count(namespace="search") == 1


# ============================================================ client × cache


class TestSearchCacheIntegration:
    @respx.mock
    async def test_second_call_skips_http(self) -> None:
        # First call hits mocked HTTP; second identical call must be
        # served from cache without a wire trip. respx's call_count is
        # the truth here — if the cache failed, count would be 2.
        route = respx.get(DEFAULT_API_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wbsearch_response([{"id": "Q154759", "label": "Sven Hedin"}]),
            )
        )
        with WikidataCache() as cache:
            async with WikidataClient(inter_request_delay_s=0, cache=cache) as client:
                first = await client.search("Sven Hedin", language="en")
                second = await client.search("Sven Hedin", language="en")

        assert route.call_count == 1
        assert [c.qid for c in first] == ["Q154759"]
        assert [c.qid for c in second] == ["Q154759"]

    @respx.mock
    async def test_counters_reflect_cache_use(self) -> None:
        respx.get(DEFAULT_API_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wbsearch_response([{"id": "Q42", "label": "Test"}]),
            )
        )
        with WikidataCache() as cache:
            async with WikidataClient(inter_request_delay_s=0, cache=cache) as client:
                await client.search("Test", language="en")
                await client.search("Test", language="en")
                await client.search("Test", language="en")
                # 1 upstream call (first) + 2 cache hits (second & third).
                assert client.api_requests == 1
                assert client.cache_hits == 2
                assert client.failures_after_retry == 0

    @respx.mock
    async def test_cache_disabled_makes_all_calls_upstream(self) -> None:
        # Sanity check on the opt-out: cache=None preserves the legacy
        # always-upstream behaviour, including api_requests counting up.
        route = respx.get(DEFAULT_API_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wbsearch_response([{"id": "Q42", "label": "Test"}]),
            )
        )
        async with WikidataClient(inter_request_delay_s=0, cache=None) as client:
            await client.search("Test", language="en")
            await client.search("Test", language="en")
        assert route.call_count == 2
        assert client.api_requests == 2
        assert client.cache_hits == 0


class TestLabelsAliasesPartialBatch:
    @respx.mock
    async def test_misses_only_fetched_hits_served_locally(self) -> None:
        # Pre-seed the cache for Q1 + Q2; only Q3 should hit the wire.
        # The post-fetch merged result must include all three with the
        # right shape.
        captured_ids: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_ids.append(request.url.params.get("ids", ""))
            return httpx.Response(
                200,
                json=_wbgetentities_response(
                    {
                        "Q3": {
                            "labels": {"en": {"language": "en", "value": "Three"}},
                            "aliases": {},
                        }
                    }
                ),
            )

        respx.get(DEFAULT_API_URL).mock(side_effect=handler)
        with WikidataCache() as cache:
            cache.put_labels_aliases("Q1", languages=["en"], per_language={"en": ["One"]})
            cache.put_labels_aliases("Q2", languages=["en"], per_language={"en": ["Two"]})
            async with WikidataClient(inter_request_delay_s=0, cache=cache) as client:
                result = await client.fetch_labels_aliases(["Q1", "Q2", "Q3"], languages=["en"])
                assert client.cache_hits == 2
                assert client.api_requests == 1

        assert captured_ids == ["Q3"]
        assert result["Q1"]["en"] == ["One"]
        assert result["Q2"]["en"] == ["Two"]
        assert result["Q3"]["en"] == ["Three"]

    @respx.mock
    async def test_full_batch_hit_skips_http_entirely(self) -> None:
        with WikidataCache() as cache:
            for qid in ("Q1", "Q2", "Q3"):
                cache.put_labels_aliases(qid, languages=["en"], per_language={"en": [qid]})
            # No respx route registered — if the client tried to GET,
            # respx would raise.
            async with WikidataClient(inter_request_delay_s=0, cache=cache) as client:
                result = await client.fetch_labels_aliases(["Q1", "Q2", "Q3"], languages=["en"])
                assert client.api_requests == 0
                assert client.cache_hits == 3
        assert set(result.keys()) == {"Q1", "Q2", "Q3"}


class TestTypesPartialBatch:
    @respx.mock
    async def test_partial_batch_hit_for_types(self) -> None:
        # Pre-seed Q1; Q2 + Q3 are misses. Only one SPARQL call.
        sparql_route = respx.post(DEFAULT_SPARQL_URL).mock(
            return_value=httpx.Response(
                200,
                json=_sparql_p31_response([("Q2", "Q5"), ("Q3", "Q515")]),
            )
        )
        with WikidataCache() as cache:
            cache.put_types("Q1", types={"Q5"})
            async with WikidataClient(inter_request_delay_s=0, cache=cache) as client:
                result = await client.fetch_types(["Q1", "Q2", "Q3"])
                assert client.cache_hits == 1
                assert client.api_requests == 1

        assert sparql_route.call_count == 1
        assert result["Q1"] == {"Q5"}
        assert result["Q2"] == {"Q5"}
        assert result["Q3"] == {"Q515"}

    @respx.mock
    async def test_writes_back_misses_to_cache(self) -> None:
        respx.post(DEFAULT_SPARQL_URL).mock(
            return_value=httpx.Response(
                200,
                json=_sparql_p31_response([("Q42", "Q5")]),
            )
        )
        with WikidataCache() as cache:
            async with WikidataClient(inter_request_delay_s=0, cache=cache) as client:
                await client.fetch_types(["Q42", "Q43"])
            # Both Q-IDs should now be cached: Q42 with its P31, Q43
            # with the explicit empty set so reruns don't re-probe.
            assert cache.get_types("Q42") == {"Q5"}
            assert cache.get_types("Q43") == set()


class TestBioFactsPartialBatch:
    @respx.mock
    async def test_partial_batch_hit_for_bio_facts(self) -> None:
        sparql_route = respx.post(DEFAULT_SPARQL_URL).mock(
            return_value=httpx.Response(
                200,
                json=_bio_facts_response(
                    [
                        {
                            "item": "Q43",
                            "birth": "1900-01-01T00:00:00Z",
                            "occupationLabel": "writer",
                        }
                    ]
                ),
            )
        )
        with WikidataCache() as cache:
            cache.put_bio_facts(
                "Q42",
                language="en",
                facts=BioFacts(
                    qid="Q42",
                    birth_date="1865-02-19T00:00:00Z",
                    occupations=["explorer"],
                ),
            )
            async with WikidataClient(inter_request_delay_s=0, cache=cache) as client:
                result = await client.fetch_bio_facts(["Q42", "Q43"])
                assert client.cache_hits == 1
                assert client.api_requests == 1

        assert sparql_route.call_count == 1
        # Cached Q-ID keeps cached fields; freshly fetched Q-ID has new fields.
        assert result["Q42"].birth_date == "1865-02-19T00:00:00Z"
        assert result["Q42"].occupations == ["explorer"]
        assert result["Q43"].birth_date == "1900-01-01T00:00:00Z"
        assert result["Q43"].occupations == ["writer"]


class TestPersistenceAcrossClientLifetimes:
    @respx.mock
    async def test_second_client_serves_from_persisted_cache(self, tmp_path: Path) -> None:
        # Build cache + client #1, populate via mocked HTTP.
        path = tmp_path / "wikidata_cache.sqlite"
        respx.get(DEFAULT_API_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wbsearch_response([{"id": "Q154759", "label": "Sven Hedin"}]),
            )
        )
        with WikidataCache(path) as cache_a:
            async with WikidataClient(inter_request_delay_s=0, cache=cache_a) as client_a:
                first = await client_a.search("Sven Hedin", language="en")
                assert client_a.api_requests == 1

        # Build cache + client #2 — same file, fresh client. No new HTTP
        # mock registered (the prior one is torn down with @respx.mock
        # ending). If the cache persisted, the second search must serve
        # from disk; otherwise httpx will try to call out and fail
        # because respx is no longer mocking.
        with respx.mock, WikidataCache(path) as cache_b:
            async with WikidataClient(inter_request_delay_s=0, cache=cache_b) as client_b:
                second = await client_b.search("Sven Hedin", language="en")
                assert client_b.api_requests == 0
                assert client_b.cache_hits == 1

        assert [c.qid for c in first] == ["Q154759"]
        assert [c.qid for c in second] == ["Q154759"]


# ============================================================ failure counters


class TestFailureAfterRetry:
    @respx.mock
    async def test_failure_counter_increments_when_retries_exhausted(self) -> None:
        # 503 indefinitely; retry exhausts after retry_attempts. The
        # counter should reflect exactly one logical "failed even after
        # retries" event regardless of how many wire attempts happened.
        respx.get(DEFAULT_API_URL).mock(return_value=httpx.Response(503))
        async with WikidataClient(
            inter_request_delay_s=0,
            retry_backoff_s=0.0,
            retry_attempts=2,
        ) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.search("test", language="en")
            assert client.failures_after_retry == 1
            # api_requests counts the logical attempt too — the call
            # was definitely routed to upstream, even though it never
            # came back with a usable payload.
            assert client.api_requests == 1

    @respx.mock
    async def test_failed_call_does_not_pollute_cache(self) -> None:
        respx.get(DEFAULT_API_URL).mock(return_value=httpx.Response(503))
        with WikidataCache() as cache:
            async with WikidataClient(
                inter_request_delay_s=0,
                retry_backoff_s=0.0,
                retry_attempts=2,
                cache=cache,
            ) as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.search("test", language="en")
            # Crucially: the cache must not be holding the failed call.
            assert cache.get_search("test", language="en", limit=10) is None
            assert cache.row_count() == 0
