"""Unit tests for :class:`WikidataClient` (Plan §3.4 Stages 1-3 endpoints).

Network mocked with ``respx``; no real Wikidata calls in this file.
The live smoke test against the real API lives in
``tests/test_extraction_resolve_live.py`` and is gated.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from theogony.extraction.wikidata_client import (
    DEFAULT_API_URL,
    DEFAULT_SPARQL_URL,
    WikidataCandidate,
    WikidataClient,
)

# ---------------------------------------------------------------- fixtures


def _wbsearch_response(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Skeleton of a wbsearchentities JSON payload.

    Only the fields :class:`WikidataClient` consumes are populated;
    real Wikidata returns more (``pageid``, ``title``, ``url`` etc.)
    and ignoring them is what we want to test.
    """
    return {"searchinfo": {"search": "test"}, "search": hits, "success": 1}


def _wbgetentities_response(entities: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"entities": entities, "success": 1}


def _sparql_p31_response(rows: list[tuple[str, str]]) -> dict[str, Any]:
    """Build a SPARQL JSON payload for a P31 query.

    Each row is ``(item_qid, type_qid)``; multiple rows for the same
    item produce a multi-type result (a real-world common case).
    """
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


# ---------------------------------------------------------------- search


class TestSearch:
    @respx.mock
    async def test_returns_candidates_from_wbsearchentities(self) -> None:
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
                        },
                        {"id": "Q123", "label": "Some Hedin", "description": None},
                    ]
                ),
            )
        )
        async with WikidataClient(inter_request_delay_s=0) as client:
            results = await client.search("Sven Hedin", language="en")

        assert len(results) == 2
        assert results[0].qid == "Q205184"
        assert results[0].label == "Sven Hedin"
        assert results[0].description == "Swedish geographer and explorer"
        assert results[0].match_text == "Sven Hedin"
        assert results[0].language == "en"
        # Second hit had no match block — match_text is None, not error.
        assert results[1].match_text is None

    @respx.mock
    async def test_empty_mention_short_circuits(self) -> None:
        # No respx route registered — if the client tries to GET, respx raises.
        async with WikidataClient(inter_request_delay_s=0) as client:
            assert await client.search("", language="en") == []
            assert await client.search("   ", language="en") == []

    @respx.mock
    async def test_skips_hits_without_qid(self) -> None:
        # Defensive: malformed payload (missing ``id`` or non-Q-prefix)
        # is logged as silent skip, not crash.
        respx.get(DEFAULT_API_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wbsearch_response(
                    [
                        {"id": None, "label": "broken"},
                        {"id": "Q42", "label": "ok"},
                        {"id": "X42", "label": "not-a-q-id"},
                    ]
                ),
            )
        )
        async with WikidataClient(inter_request_delay_s=0) as client:
            results = await client.search("test", language="en")
        assert [c.qid for c in results] == ["Q42"]


class TestSearchMultiLanguage:
    @respx.mock
    async def test_concurrent_calls_per_language(self) -> None:
        # One mock route handles all four languages — respx matches by
        # URL only, so the same route fires four times. That is the
        # behaviour we want to verify (one call per language).
        route = respx.get(DEFAULT_API_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wbsearch_response([{"id": "Q205184", "label": "Sven Hedin"}]),
            )
        )
        async with WikidataClient(inter_request_delay_s=0) as client:
            results = await client.search_multi_language(
                "Sven Hedin",
                languages=["en", "de", "fr", "it"],
            )
        assert route.call_count == 4
        assert set(results.keys()) == {"en", "de", "fr", "it"}
        assert all(len(cands) == 1 for cands in results.values())

    @respx.mock
    async def test_empty_languages_returns_empty_dict(self) -> None:
        async with WikidataClient(inter_request_delay_s=0) as client:
            assert await client.search_multi_language("Tibet", languages=[]) == {}


# ---------------------------------------------------------------- labels/aliases


class TestFetchLabelsAliases:
    @respx.mock
    async def test_returns_label_then_aliases_per_language(self) -> None:
        respx.get(DEFAULT_API_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wbgetentities_response(
                    {
                        "Q205184": {
                            "id": "Q205184",
                            "labels": {
                                "en": {"language": "en", "value": "Sven Hedin"},
                                "de": {"language": "de", "value": "Sven Hedin"},
                            },
                            "aliases": {
                                "en": [
                                    {"language": "en", "value": "Hedin"},
                                    {"language": "en", "value": "Sven Anders Hedin"},
                                ],
                                "de": [{"language": "de", "value": "Hedin, Sven"}],
                            },
                        }
                    }
                ),
            )
        )
        async with WikidataClient(inter_request_delay_s=0) as client:
            result = await client.fetch_labels_aliases(["Q205184"], languages=["en", "de"])

        assert "Q205184" in result
        # Label first, aliases after, in returned order.
        assert result["Q205184"]["en"] == ["Sven Hedin", "Hedin", "Sven Anders Hedin"]
        assert result["Q205184"]["de"] == ["Sven Hedin", "Hedin, Sven"]

    @respx.mock
    async def test_missing_language_returns_empty_list_not_absent(self) -> None:
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
            result = await client.fetch_labels_aliases(["Q205184"], languages=["en", "fr"])
        # Explicit empty list — easier for callers than KeyError.
        assert result["Q205184"]["fr"] == []
        assert result["Q205184"]["en"] == ["Sven Hedin"]

    @respx.mock
    async def test_batches_above_50_qids(self) -> None:
        # 75 Q-IDs should produce two HTTP calls (50 + 25).
        qids = [f"Q{i}" for i in range(1, 76)]

        def _entry(q: str) -> dict[str, Any]:
            return {"labels": {"en": {"language": "en", "value": q}}, "aliases": {}}

        responses_per_call = [
            _wbgetentities_response({q: _entry(q) for q in qids[:50]}),
            _wbgetentities_response({q: _entry(q) for q in qids[50:]}),
        ]
        call_iter = iter(responses_per_call)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=next(call_iter))

        route = respx.get(DEFAULT_API_URL).mock(side_effect=handler)
        async with WikidataClient(inter_request_delay_s=0, batch_size=50) as client:
            result = await client.fetch_labels_aliases(qids, languages=["en"])

        assert route.call_count == 2
        assert len(result) == 75

    @respx.mock
    async def test_empty_inputs_skip_http(self) -> None:
        async with WikidataClient(inter_request_delay_s=0) as client:
            assert await client.fetch_labels_aliases([], languages=["en"]) == {}
            assert await client.fetch_labels_aliases(["Q1"], languages=[]) == {}


# ---------------------------------------------------------------- types


class TestFetchTypes:
    @respx.mock
    async def test_returns_p31_set_per_qid(self) -> None:
        respx.post(DEFAULT_SPARQL_URL).mock(
            return_value=httpx.Response(
                200,
                json=_sparql_p31_response(
                    [
                        ("Q205184", "Q5"),
                        ("Q64", "Q515"),
                        ("Q64", "Q486972"),
                    ]
                ),
            )
        )
        async with WikidataClient(inter_request_delay_s=0) as client:
            result = await client.fetch_types(["Q205184", "Q64", "Q999"])

        assert result["Q205184"] == {"Q5"}
        # Multi-type: Berlin is both Q515 (city) and Q486972 (settlement).
        assert result["Q64"] == {"Q515", "Q486972"}
        # Q-ID with no P31 binding still appears, with empty set.
        assert result["Q999"] == set()

    @respx.mock
    async def test_empty_qid_list_skips_http(self) -> None:
        async with WikidataClient(inter_request_delay_s=0) as client:
            assert await client.fetch_types([]) == {}

    @respx.mock
    async def test_batches_large_qid_lists(self) -> None:
        # 60 Q-IDs at batch_size=25 → 3 SPARQL calls.
        qids = [f"Q{i}" for i in range(1, 61)]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_sparql_p31_response([]))

        route = respx.post(DEFAULT_SPARQL_URL).mock(side_effect=handler)
        async with WikidataClient(inter_request_delay_s=0, batch_size=25) as client:
            result = await client.fetch_types(qids)
        assert route.call_count == 3
        assert len(result) == 60


# ---------------------------------------------------------------- retries


class TestRetryAndPoliteness:
    @respx.mock
    async def test_retries_on_429_then_succeeds(self) -> None:
        responses = iter(
            [
                httpx.Response(429),
                httpx.Response(200, json=_wbsearch_response([{"id": "Q42", "label": "OK"}])),
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return next(responses)

        route = respx.get(DEFAULT_API_URL).mock(side_effect=handler)
        async with WikidataClient(
            inter_request_delay_s=0,
            retry_backoff_s=0.0,
            retry_attempts=3,
        ) as client:
            results = await client.search("test", language="en")
        assert route.call_count == 2
        assert results[0].qid == "Q42"

    @respx.mock
    async def test_raises_after_exhausted_retries(self) -> None:
        respx.get(DEFAULT_API_URL).mock(return_value=httpx.Response(503))
        async with WikidataClient(
            inter_request_delay_s=0,
            retry_backoff_s=0.0,
            retry_attempts=2,
        ) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.search("test", language="en")

    @respx.mock
    async def test_user_agent_is_sent(self) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["user_agent"] = request.headers.get("user-agent", "")
            return httpx.Response(200, json=_wbsearch_response([]))

        respx.get(DEFAULT_API_URL).mock(side_effect=handler)
        async with WikidataClient(inter_request_delay_s=0) as client:
            await client.search("test", language="en")

        # Wikidata blocks anonymous (no UA) requests at the WAF; we
        # always send a descriptive UA.
        assert "theogony" in captured["user_agent"].lower()


# ---------------------------------------------------------------- DTO


class TestCandidateModel:
    def test_qid_pattern_is_enforced(self) -> None:
        # Catches the obvious "I passed in a label by accident" bug.
        with pytest.raises(ValueError):
            WikidataCandidate(qid="not-a-qid", language="en")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            WikidataCandidate(qid="Q1", language="en", unknown="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------- batch_size sanity


class TestConstructorValidation:
    def test_batch_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            WikidataClient(batch_size=0)
        with pytest.raises(ValueError):
            WikidataClient(batch_size=-1)
