"""Unit tests for :class:`EntityResolver` (Plan §3.4 Stages 1-3 + Tier 4/3/0).

All Wikidata calls are stubbed via a fake ``WikidataClient`` so the
resolver's tier-assignment logic is tested deterministically without
network or respx ceremony. The live smoke test that exercises the
real Wikidata API lives in ``tests/test_extraction_resolve_live.py``
and is gated behind a ``THEOGONY_LIVE_TESTS=1`` opt-in.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from pydantic import BaseModel

from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.extraction.ner import Mention
from theogony.extraction.resolve import (
    DEFAULT_LANGUAGES,
    TIER_0_CONFIDENCE,
    TIER_3_CONFIDENCE,
    TIER_4_CONFIDENCE,
    EntityResolver,
    ResolvedMention,
)
from theogony.extraction.wikidata_client import WikidataCandidate

# ---------------------------------------------------------------- fake client


class FakeWikidataResponses(BaseModel):
    """Scripted responses for the three :class:`WikidataClient` operations.

    Indexed so tests can declare exactly what each Stage returns. Used
    to verify the resolver's tier decisions without touching HTTP.
    """

    search: dict[tuple[str, str], list[WikidataCandidate]] = {}
    """Key: (mention, language). Empty dict ⇒ no candidates anywhere."""

    aliases: dict[str, dict[str, list[str]]] = {}
    """Key: qid. Value: {language: [label, alias, alias, ...]}."""

    types: dict[str, set[str]] = {}
    """Key: qid. Value: set of P31 Q-IDs."""


class FakeWikidataClient:
    """In-memory stand-in for :class:`WikidataClient`.

    Implements only the surface :class:`EntityResolver` calls. Records
    invocations so tests can assert on call count and arguments.
    """

    def __init__(self, responses: FakeWikidataResponses) -> None:
        self.responses = responses
        self.search_calls: list[tuple[str, str, int]] = []
        self.fetch_labels_calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        self.fetch_types_calls: list[tuple[str, ...]] = []

    async def search(
        self, mention: str, *, language: str, limit: int = 10
    ) -> list[WikidataCandidate]:
        self.search_calls.append((mention, language, limit))
        return list(self.responses.search.get((mention, language), []))

    async def search_multi_language(
        self,
        mention: str,
        *,
        languages: Iterable[str],
        limit: int = 10,
    ) -> dict[str, list[WikidataCandidate]]:
        out: dict[str, list[WikidataCandidate]] = {}
        for lang in languages:
            out[lang] = await self.search(mention, language=lang, limit=limit)
        return out

    async def fetch_labels_aliases(
        self,
        qids: Iterable[str],
        *,
        languages: Iterable[str],
    ) -> dict[str, dict[str, list[str]]]:
        qid_tuple = tuple(qids)
        lang_tuple = tuple(languages)
        self.fetch_labels_calls.append((qid_tuple, lang_tuple))
        out: dict[str, dict[str, list[str]]] = {}
        for qid in qid_tuple:
            qid_aliases = self.responses.aliases.get(qid, {})
            out[qid] = {lang: list(qid_aliases.get(lang, [])) for lang in lang_tuple}
        return out

    async def fetch_types(self, qids: Iterable[str]) -> dict[str, set[str]]:
        qid_tuple = tuple(qids)
        self.fetch_types_calls.append(qid_tuple)
        return {qid: set(self.responses.types.get(qid, set())) for qid in qid_tuple}


# ---------------------------------------------------------------- helpers


def _book_source_ref() -> SourceRef:
    """Book-level SourceRef used by the resolver to anchor minted nodes."""
    return SourceRef(
        source_type="gutenberg",
        identifier="43497",
        url="https://www.gutenberg.org/ebooks/43497",
        language="en",
    )


def _mention(
    text: str,
    label: str,
    *,
    sentence_index: int = 0,
    start_in_sentence: int = 0,
    start_in_source: int = 0,
) -> Mention:
    return Mention(
        text=text,
        label=label,
        sentence_index=sentence_index,
        start_char_in_sentence=start_in_sentence,
        end_char_in_sentence=start_in_sentence + len(text),
        start_char_in_source=start_in_source,
        end_char_in_source=start_in_source + len(text),
    )


def _candidate(qid: str, language: str, label: str | None = None) -> WikidataCandidate:
    return WikidataCandidate(qid=qid, label=label or qid, language=language)


# ---------------------------------------------------------------- Tier 4


class TestTier4:
    """Tier 4: exactly one candidate survives Stage 3 with EXACT alias
    match in ≥ 2 languages. Confidence 0.90."""

    async def test_unique_candidate_with_exact_in_two_languages(self) -> None:
        responses = FakeWikidataResponses(
            search={
                ("Sven Hedin", "en"): [_candidate("Q205184", "en", "Sven Hedin")],
                ("Sven Hedin", "de"): [_candidate("Q205184", "de", "Sven Hedin")],
                ("Sven Hedin", "fr"): [],
                ("Sven Hedin", "it"): [],
            },
            aliases={
                "Q205184": {
                    "en": ["Sven Hedin", "Hedin"],
                    "de": ["Sven Hedin", "Hedin, Sven"],
                    "fr": [],
                    "it": [],
                }
            },
            types={"Q205184": {"Q5"}},  # human
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]

        m = _mention("Sven Hedin", "PERSON")
        resolved = await resolver.resolve(m, source_ref=_book_source_ref())

        assert resolved.tier == 4
        assert resolved.chosen_qid == "Q205184"
        assert resolved.node.external_ids == {"wikidata": "Q205184"}
        assert resolved.node.scores.confidence == TIER_4_CONFIDENCE
        assert resolved.node.resolution_tier == 4
        assert resolved.node.manual_resolution_needed is False
        assert resolved.node.label == "Sven Hedin"
        assert resolved.node.node_type == NodeType.PERSON
        assert resolved.failure_reason is None

    async def test_exact_in_single_language_does_not_promote_to_tier_4(self) -> None:
        # Tier 4 requires ≥ 2 languages with EXACT match. Only EN has
        # exact aliases here → falls back to Tier 3 (CASE/EXACT in 1
        # language only is too weak for Tier 4 per Plan §3.4).
        responses = FakeWikidataResponses(
            search={("Tibet", "en"): [_candidate("Q17", "en", "Tibet")]},
            aliases={
                "Q17": {
                    "en": ["Tibet"],
                    "de": ["Tibet"],  # also exact in DE → forces Tier 4
                }
            },
            types={"Q17": {"Q486972"}},
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        # With exact in en + de, this is actually Tier 4. Now contrast:
        # remove DE alias → Tier 3 (only EN exact, but DE still has CASE
        # via labels[en] is "Tibet" — actually DE has empty alias list
        # → no match in DE → only 1 language exact → Tier 3 fallback).
        responses_single = FakeWikidataResponses(
            search={("Tibet", "en"): [_candidate("Q17", "en", "Tibet")]},
            aliases={
                "Q17": {
                    "en": ["Tibet"],
                    "de": [],  # no DE label/aliases
                    "fr": [],
                    "it": [],
                }
            },
            types={"Q17": {"Q486972"}},
        )
        client_single = FakeWikidataClient(responses_single)
        resolver_single = EntityResolver(client=client_single)  # type: ignore[arg-type]
        m = _mention("Tibet", "GPE")

        tier4_result = await resolver.resolve(m, source_ref=_book_source_ref())
        assert tier4_result.tier == 4

        tier3_result = await resolver_single.resolve(m, source_ref=_book_source_ref())
        # Only one language (EN) had exact match → Tier 3 with CASE-or-better
        # check still requires ≥ 2 languages. Only EN has any match here
        # → no Tier 3 either → Tier 0.
        assert tier3_result.tier == 0


# ---------------------------------------------------------------- Tier 3


class TestTier3:
    """Tier 3: at least one candidate survives Stage 3, best one has
    CASE-or-better matches in ≥ 2 languages but does not meet Tier 4
    (multiple survivors, or only some EXACT matches)."""

    async def test_multiple_survivors_picks_best_ranked(self) -> None:
        responses = FakeWikidataResponses(
            search={
                ("Tibet", "en"): [
                    _candidate("Q17", "en", "Tibet"),
                    _candidate("Q123", "en", "Tibet (other)"),
                ],
                ("Tibet", "de"): [_candidate("Q17", "de", "Tibet")],
                ("Tibet", "fr"): [_candidate("Q17", "fr", "Tibet")],
                ("Tibet", "it"): [],
            },
            aliases={
                "Q17": {
                    "en": ["Tibet", "TIBET"],
                    "de": ["Tibet"],
                    "fr": ["Tibet"],
                    "it": [],
                },
                "Q123": {
                    "en": ["tibet"],  # case match in en only
                    "de": [],
                    "fr": [],
                    "it": [],
                },
            },
            types={
                "Q17": {"Q486972"},
                "Q123": {"Q486972"},
            },
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        m = _mention("Tibet", "GPE")

        # Tier 4 requires unique survivor — two survive (Q17 and Q123).
        # So Tier 3 with best-ranked: Q17 has CASE-or-better in en+de+fr (3 langs)
        # vs Q123 in en only (1 lang). Q17 wins.
        resolved = await resolver.resolve(m, source_ref=_book_source_ref())
        assert resolved.tier == 3
        assert resolved.chosen_qid == "Q17"
        assert resolved.node.scores.confidence == TIER_3_CONFIDENCE
        assert resolved.node.external_ids == {"wikidata": "Q17"}

    async def test_unique_survivor_with_only_case_match_lands_tier_3(self) -> None:
        # Single survivor but no EXACT match in ≥ 2 languages → Tier 3
        # (still has CASE-or-better in 2+ languages).
        responses = FakeWikidataResponses(
            search={
                ("aufschnaiter", "en"): [_candidate("Q123456", "en", "Peter Aufschnaiter")],
                ("aufschnaiter", "de"): [_candidate("Q123456", "de", "Peter Aufschnaiter")],
                ("aufschnaiter", "fr"): [],
                ("aufschnaiter", "it"): [],
            },
            aliases={
                "Q123456": {
                    "en": ["Peter Aufschnaiter", "Aufschnaiter"],
                    "de": ["Peter Aufschnaiter", "Aufschnaiter"],
                    "fr": [],
                    "it": [],
                }
            },
            types={"Q123456": {"Q5"}},
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]

        m = _mention("aufschnaiter", "PERSON")  # lowercase mention
        resolved = await resolver.resolve(m, source_ref=_book_source_ref())
        # "aufschnaiter" exact-matches "Aufschnaiter" at CASE level;
        # not EXACT (case differs), so no Tier 4 even with 2 languages.
        assert resolved.tier == 3
        assert resolved.chosen_qid == "Q123456"


# ---------------------------------------------------------------- Tier 0


class TestTier0:
    """Tier 0: honest failure. No Q-ID assigned, manual_resolution_needed=True."""

    async def test_no_candidates_anywhere(self) -> None:
        client = FakeWikidataClient(FakeWikidataResponses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        m = _mention("Glorpzizzlewicket", "PERSON")
        resolved = await resolver.resolve(m, source_ref=_book_source_ref())

        assert resolved.tier == 0
        assert resolved.chosen_qid is None
        assert resolved.failure_reason == "no_candidates_from_search"
        assert resolved.node.external_ids == {}
        assert resolved.node.manual_resolution_needed is True
        assert resolved.node.scores.confidence == TIER_0_CONFIDENCE
        assert resolved.node.label == "Glorpzizzlewicket"
        assert resolved.node.properties["wikidata_search_attempted"] is True
        assert resolved.node.properties["wikidata_failure_reason"] == "no_candidates_from_search"

    async def test_all_candidates_fail_type_filter(self) -> None:
        # PERSON mention but only candidates have non-Q5 P31 (e.g. a town).
        responses = FakeWikidataResponses(
            search={("Aufschnaiter", "en"): [_candidate("Q999", "en", "Aufschnaiter")]},
            aliases={"Q999": {"en": ["Aufschnaiter"]}},
            types={"Q999": {"Q486972"}},  # human settlement, not Q5 (human)
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        m = _mention("Aufschnaiter", "PERSON")
        resolved = await resolver.resolve(m, source_ref=_book_source_ref())

        assert resolved.tier == 0
        assert resolved.failure_reason == "all_candidates_failed_type_filter"
        # Audit trail: candidates considered are recorded for review.
        assert "Q999" in resolved.candidates_considered
        assert resolved.node.properties["wikidata_candidates_considered"] == ["Q999"]

    async def test_weak_match_falls_to_tier_0_in_e2(self) -> None:
        # Survivor exists, but no language has a CASE-or-better match
        # in ≥ 2 languages. E2 cannot promote to Tier 2/1 (LLM); honest
        # failure to Tier 0 with the e2-specific reason.
        responses = FakeWikidataResponses(
            search={("Foo", "en"): [_candidate("Q42", "en", "Foo")]},
            aliases={
                "Q42": {
                    "en": ["completely different label"],  # no match at any level
                    "de": [],
                    "fr": [],
                    "it": [],
                }
            },
            types={"Q42": {"Q5"}},
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        m = _mention("Foo", "PERSON")
        resolved = await resolver.resolve(m, source_ref=_book_source_ref())

        assert resolved.tier == 0
        assert resolved.failure_reason == "weak_alias_match_no_llm_in_e2"
        assert resolved.candidates_considered == ["Q42"]

    async def test_non_resolvable_label_short_circuits_to_tier_0(self) -> None:
        client = FakeWikidataClient(FakeWikidataResponses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        m = _mention("twenty-one", "CARDINAL")  # CARDINAL never goes to Wikidata

        resolved = await resolver.resolve(m, source_ref=_book_source_ref())
        assert resolved.tier == 0
        assert resolved.failure_reason == "ner_label_not_resolvable"
        # Verifies short-circuit: no Wikidata calls were made.
        assert client.search_calls == []
        assert client.fetch_labels_calls == []
        assert client.fetch_types_calls == []


# ---------------------------------------------------------------- dedup


class TestDeduplication:
    async def test_repeated_mentions_share_one_node(self) -> None:
        responses = FakeWikidataResponses(
            search={
                ("Tibet", "en"): [_candidate("Q17", "en", "Tibet")],
                ("Tibet", "de"): [_candidate("Q17", "de", "Tibet")],
                ("Tibet", "fr"): [],
                ("Tibet", "it"): [],
            },
            aliases={"Q17": {"en": ["Tibet"], "de": ["Tibet"]}},
            types={"Q17": {"Q486972"}},
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        mentions = [
            _mention("Tibet", "GPE", sentence_index=0, start_in_source=10),
            _mention("Tibet", "GPE", sentence_index=5, start_in_source=200),
            _mention("Tibet", "GPE", sentence_index=10, start_in_source=400),
        ]

        results = await resolver.resolve_many(mentions, source_ref=_book_source_ref())

        assert len(results) == 1, "three mentions of 'Tibet' must collapse to one ResolvedMention"
        assert len(results[0].mentions) == 3
        assert results[0].node.properties["mention_count"] == 3
        # First-mention coordinates point to the earliest occurrence.
        assert results[0].node.properties["first_mention_sentence_index"] == 0
        assert results[0].node.properties["first_mention_start_char_in_source"] == 10
        # Wikidata called exactly once per language (one search per group).
        assert len(client.search_calls) == len(DEFAULT_LANGUAGES)

    async def test_case_variants_dedupe_under_full_normalisation(self) -> None:
        # "TIBET", "Tibet", "tibet" — same group via fully_normalise.
        responses = FakeWikidataResponses(
            search={
                ("TIBET", "en"): [_candidate("Q17", "en", "Tibet")],
                ("TIBET", "de"): [_candidate("Q17", "de", "Tibet")],
                ("TIBET", "fr"): [],
                ("TIBET", "it"): [],
            },
            aliases={"Q17": {"en": ["Tibet"], "de": ["Tibet"]}},
            types={"Q17": {"Q486972"}},
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        mentions = [
            _mention("TIBET", "GPE"),
            _mention("Tibet", "GPE", start_in_source=100),
            _mention("tibet", "GPE", start_in_source=200),
        ]

        results = await resolver.resolve_many(mentions, source_ref=_book_source_ref())
        assert len(results) == 1
        assert len(results[0].mentions) == 3
        # Representative text (most common form among the group, ties → first):
        # all three appear once → first wins.
        assert results[0].node.label == "Tibet"  # canonical from Wikidata since resolved

    async def test_different_labels_do_not_dedupe(self) -> None:
        # "Apple" the company vs "apple" the fruit — both PERSON-cased
        # mentions but different NER labels → two groups.
        responses = FakeWikidataResponses(
            search={("Apple", "en"): []},
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        mentions = [
            _mention("Apple", "ORG"),
            _mention("Apple", "PERSON"),  # hypothetical
        ]
        results = await resolver.resolve_many(mentions, source_ref=_book_source_ref())
        assert len(results) == 2


# ---------------------------------------------------------------- node-id collapse


class TestDeterministicId:
    """Plan §9.5 collisions: two ingests of the same book + entity must
    produce the same node id (so KnowledgeStore.upsert_node is a no-op
    on retry, satisfying OQ-7)."""

    async def test_same_inputs_produce_same_node_id(self) -> None:
        responses = FakeWikidataResponses(
            search={
                ("Tibet", "en"): [_candidate("Q17", "en", "Tibet")],
                ("Tibet", "de"): [_candidate("Q17", "de", "Tibet")],
                ("Tibet", "fr"): [],
                ("Tibet", "it"): [],
            },
            aliases={"Q17": {"en": ["Tibet"], "de": ["Tibet"]}},
            types={"Q17": {"Q486972"}},
        )
        client_a = FakeWikidataClient(responses)
        client_b = FakeWikidataClient(responses)
        resolver_a = EntityResolver(client=client_a)  # type: ignore[arg-type]
        resolver_b = EntityResolver(client=client_b)  # type: ignore[arg-type]
        m = _mention("Tibet", "GPE")

        a = await resolver_a.resolve(m, source_ref=_book_source_ref())
        b = await resolver_b.resolve(m, source_ref=_book_source_ref())
        # Resumable ingest depends on this. Re-running resolution
        # against the same source must mint the same KnowledgeNode id.
        assert a.node.id == b.node.id
        assert a.node.id.startswith("AKA-")

    async def test_tier0_node_id_is_also_deterministic(self) -> None:
        client_a = FakeWikidataClient(FakeWikidataResponses())
        client_b = FakeWikidataClient(FakeWikidataResponses())
        resolver_a = EntityResolver(client=client_a)  # type: ignore[arg-type]
        resolver_b = EntityResolver(client=client_b)  # type: ignore[arg-type]
        m = _mention("Glorpzizzlewicket", "PERSON")

        a = await resolver_a.resolve(m, source_ref=_book_source_ref())
        b = await resolver_b.resolve(m, source_ref=_book_source_ref())
        assert a.node.id == b.node.id


# ---------------------------------------------------------------- batching


class TestBatching:
    async def test_resolve_many_calls_search_per_unique_form_only(self) -> None:
        # 5 mentions of "Tibet" + 1 of "Hedin" → 2 groups → 2 × len(languages) calls.
        search_map: dict[tuple[str, str], list[WikidataCandidate]] = {}
        for lang in DEFAULT_LANGUAGES:
            search_map[("Tibet", lang)] = [_candidate("Q17", lang, "Tibet")]
            search_map[("Hedin", lang)] = [_candidate("Q205184", lang, "Sven Hedin")]
        responses = FakeWikidataResponses(
            search=search_map,
            aliases={
                "Q17": {lang: ["Tibet"] for lang in DEFAULT_LANGUAGES},
                "Q205184": {lang: ["Sven Hedin", "Hedin"] for lang in DEFAULT_LANGUAGES},
            },
            types={"Q17": {"Q486972"}, "Q205184": {"Q5"}},
        )
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        mentions = [_mention("Tibet", "GPE", start_in_source=i * 10) for i in range(5)] + [
            _mention("Hedin", "PERSON")
        ]
        results = await resolver.resolve_many(mentions, source_ref=_book_source_ref())
        assert len(results) == 2
        # Number of search calls = languages × unique groups
        assert len(client.search_calls) == len(DEFAULT_LANGUAGES) * 2


# ---------------------------------------------------------------- input validation


class TestInputValidation:
    def test_languages_must_be_non_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            EntityResolver(client=FakeWikidataClient(FakeWikidataResponses()), languages=[])  # type: ignore[arg-type]

    async def test_empty_mentions_returns_empty_list(self) -> None:
        client = FakeWikidataClient(FakeWikidataResponses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        assert await resolver.resolve_many([], source_ref=_book_source_ref()) == []
        assert client.search_calls == []


# ---------------------------------------------------------------- DTO discipline


class TestResolvedMentionModel:
    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            ResolvedMention(  # type: ignore[call-arg]
                mentions=[_mention("x", "PERSON")],
                node=KnowledgeNode(label="x", source_ref=_book_source_ref()),
                tier=0,
                bogus="field",
            )

    def test_tier_constrained_zero_to_four(self) -> None:
        with pytest.raises(ValueError):
            ResolvedMention(
                mentions=[_mention("x", "PERSON")],
                node=KnowledgeNode(label="x", source_ref=_book_source_ref()),
                tier=5,
            )
