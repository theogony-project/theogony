"""Unit tests for EntityResolver Stage 4 (Plan §3.4 Tier 2 / Tier 1)."""

from __future__ import annotations

import json

from pydantic import BaseModel

from theogony.agents.llm import StubLLMProvider
from theogony.core.model import SourceRef
from theogony.extraction.book_context import BookContext
from theogony.extraction.ner import Mention
from theogony.extraction.resolve import (
    TIER_0_CONFIDENCE,
    TIER_1_CONFIDENCE,
    TIER_2_CONFIDENCE,
    EntityResolver,
)
from theogony.extraction.sentence import Sentence
from theogony.extraction.wikidata_client import BioFacts, WikidataCandidate

# ---------------------------------------------------------------- fake client


class FakeWikidataResponses(BaseModel):
    search: dict[tuple[str, str], list[WikidataCandidate]] = {}
    aliases: dict[str, dict[str, list[str]]] = {}
    types: dict[str, set[str]] = {}
    bio_facts: dict[str, BioFacts] = {}


class FakeWikidataClient:
    """Reused stub mirroring the one in ``test_extraction_resolve.py``,
    extended for Stage-4's ``fetch_bio_facts`` call."""

    def __init__(self, responses: FakeWikidataResponses) -> None:
        self.responses = responses
        self.search_calls: list[tuple[str, str, int]] = []
        self.fetch_bio_facts_calls: list[tuple[tuple[str, ...], str]] = []

    async def search(self, mention, *, language, limit=10):  # type: ignore[no-untyped-def]
        self.search_calls.append((mention, language, limit))
        return list(self.responses.search.get((mention, language), []))

    async def search_multi_language(self, mention, *, languages, limit=10):  # type: ignore[no-untyped-def]
        return {lang: await self.search(mention, language=lang, limit=limit) for lang in languages}

    async def fetch_labels_aliases(self, qids, *, languages):  # type: ignore[no-untyped-def]
        out: dict[str, dict[str, list[str]]] = {}
        for qid in qids:
            qid_aliases = self.responses.aliases.get(qid, {})
            out[qid] = {lang: list(qid_aliases.get(lang, [])) for lang in languages}
        return out

    async def fetch_types(self, qids):  # type: ignore[no-untyped-def]
        return {qid: set(self.responses.types.get(qid, set())) for qid in qids}

    async def fetch_bio_facts(self, qids, *, language="en"):  # type: ignore[no-untyped-def]
        qid_tuple = tuple(qids)
        self.fetch_bio_facts_calls.append((qid_tuple, language))
        return {qid: self.responses.bio_facts.get(qid, BioFacts(qid=qid)) for qid in qid_tuple}


# ---------------------------------------------------------------- fixtures


def _book_source_ref() -> SourceRef:
    return SourceRef(
        source_type="gutenberg",
        identifier="944",
        url="https://www.gutenberg.org/ebooks/944",
        language="en",
    )


def _hedin_book_context() -> BookContext:
    return BookContext(
        time_period="1939-1951",
        places=["Tibet", "India", "Nepal"],
        people_descriptors=["German-speaking Austrian protagonists"],
        summary="Heinrich Harrer's escape from a British internment camp in India to Lhasa.",
        derived_from_book="gutenberg:944",
        derived_from_model_id="stub-llm",
    )


def _mention(
    text: str,
    label: str,
    *,
    sentence_index: int = 0,
    start_in_source: int = 0,
) -> Mention:
    return Mention(
        text=text,
        label=label,
        sentence_index=sentence_index,
        start_char_in_sentence=0,
        end_char_in_sentence=len(text),
        start_char_in_source=start_in_source,
        end_char_in_source=start_in_source + len(text),
    )


def _candidate(qid: str, language: str, label: str | None = None) -> WikidataCandidate:
    return WikidataCandidate(qid=qid, label=label or qid, language=language)


def _sentence(idx: int, text: str) -> Sentence:
    return Sentence(index=idx, text=text, start_char=0, end_char=len(text))


def _ambiguous_aufschnaiter_responses() -> FakeWikidataResponses:
    """Two surviving candidates, ambiguous on alias level (CASE-only,
    one language each), so neither Tier 4 nor Tier 3 fires.

    Q123456 is the real Peter Aufschnaiter (born 1899, mountaineer,
    worked in Tibet). Q789012 is a hypothetical footballer with the
    same surname.
    """
    return FakeWikidataResponses(
        search={
            ("Aufschnaiter", "en"): [_candidate("Q123456", "en", "Peter Aufschnaiter")],
            ("Aufschnaiter", "de"): [_candidate("Q789012", "de", "Hans Aufschnaiter")],
            ("Aufschnaiter", "fr"): [],
            ("Aufschnaiter", "it"): [],
        },
        aliases={
            "Q123456": {
                "en": ["Peter Aufschnaiter", "Aufschnaiter"],
                "de": [],
                "fr": [],
                "it": [],
            },
            "Q789012": {
                "en": [],
                "de": ["Hans Aufschnaiter", "Aufschnaiter"],
                "fr": [],
                "it": [],
            },
        },
        types={"Q123456": {"Q5"}, "Q789012": {"Q5"}},
        bio_facts={
            "Q123456": BioFacts(
                qid="Q123456",
                birth_date="1899-11-20T00:00:00Z",
                death_date="1973-10-12T00:00:00Z",
                birth_place="Kitzbühel",
                occupations=["mountaineer", "engineer", "agronomist"],
                work_locations=["Tibet", "Nepal"],
            ),
            "Q789012": BioFacts(
                qid="Q789012",
                birth_date="1950-03-15T00:00:00Z",
                birth_place="Munich",
                occupations=["footballer"],
                work_locations=["Germany"],
            ),
        },
    )


# ---------------------------------------------------------------- Tier 2


class TestTier2:
    """Tier 2: Stage 4 LLM picks a Q-ID and at least one survivor had bio facts.
    Confidence 0.65."""

    async def test_llm_picks_correct_aufschnaiter_with_bio_facts(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm_response = json.dumps(
            {
                "chosen": "Q123456",
                "confidence": 0.92,
                "reasoning": (
                    "Q123456 is a mountaineer born 1899 who worked in Tibet, "
                    "matching the book context (1939-1951, Tibet, "
                    "German-speaking Austrian protagonists). Q789012 is a "
                    "modern footballer; lifespan and occupation contradict."
                ),
            }
        )
        llm = StubLLMProvider(default=llm_response)
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )
        sentences = [_sentence(0, "After many days of climbing, Aufschnaiter and I reached Lhasa.")]
        m = _mention("Aufschnaiter", "PERSON")

        resolved = await resolver.resolve(m, source_ref=_book_source_ref(), sentences=sentences)

        assert resolved.tier == 2
        assert resolved.chosen_qid == "Q123456"
        assert resolved.node.external_ids == {"wikidata": "Q123456"}
        assert resolved.node.scores.confidence == TIER_2_CONFIDENCE
        assert resolved.node.resolution_tier == 2
        assert resolved.node.manual_resolution_needed is False
        # Stage 4 reasoning recorded for audit (Plan §3.4 / PHX-0035 Reviewer agent).
        assert resolved.node.properties["stage4_llm_reasoning"].startswith("Q123456")
        assert resolved.node.properties["stage4_llm_confidence"] == 0.92
        assert resolved.node.properties["stage4_llm_model_id"] == "stub-llm"

    async def test_llm_receives_book_context_and_sentence(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(
            default=json.dumps({"chosen": "Q123456", "confidence": 0.9, "reasoning": "..."})
        )
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )
        sentences = [_sentence(0, "Aufschnaiter and I crossed the Himalayas.")]

        await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
            sentences=sentences,
        )

        prompt = llm.calls[0]["prompt"]
        # Source sentence is in the prompt verbatim.
        assert "Aufschnaiter and I crossed the Himalayas." in prompt
        # Book context block fields appear.
        assert "1939-1951" in prompt
        assert "Tibet" in prompt
        # Each survivor's bio facts appear.
        assert "Q123456" in prompt
        assert "Q789012" in prompt
        assert "Kitzbühel" in prompt
        assert "footballer" in prompt
        # JSON schema enforced.
        assert llm.calls[0]["json_schema"] is not None
        assert llm.calls[0]["temperature"] == 0.0


# ---------------------------------------------------------------- Tier 1


class TestTier1:
    """Tier 1: Stage 4 LLM picks but every survivor had empty bio facts.
    Confidence 0.55."""

    async def test_no_bio_facts_anywhere_lands_tier_1(self) -> None:
        # Two surviving GPE candidates with no person bio facts.
        # Plan §3.4: Tier 1 is "LLM with sentence context only".
        responses = FakeWikidataResponses(
            search={
                ("Lhasa", "en"): [
                    _candidate("Q5869", "en", "Lhasa"),
                    _candidate("Q123", "en", "Other Lhasa"),
                ],
                ("Lhasa", "de"): [],
                ("Lhasa", "fr"): [],
                ("Lhasa", "it"): [],
            },
            aliases={
                "Q5869": {"en": ["Lhasa", "lhasa"]},
                "Q123": {"en": ["lhasa"]},
            },
            types={"Q5869": {"Q486972"}, "Q123": {"Q486972"}},
            # Bio facts dict empty — both candidates get empty BioFacts
            # via the fake's default-on-missing behaviour.
        )
        client = FakeWikidataClient(responses)
        llm_text = json.dumps(
            {"chosen": "Q5869", "confidence": 0.85, "reasoning": "Capital of Tibet."}
        )
        llm = StubLLMProvider(default=llm_text)
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )
        sentences = [_sentence(0, "We finally reached Lhasa.")]

        resolved = await resolver.resolve(
            _mention("Lhasa", "GPE"),
            source_ref=_book_source_ref(),
            sentences=sentences,
        )

        assert resolved.tier == 1
        assert resolved.chosen_qid == "Q5869"
        assert resolved.node.external_ids == {"wikidata": "Q5869"}
        assert resolved.node.scores.confidence == TIER_1_CONFIDENCE
        assert resolved.node.resolution_tier == 1
        assert resolved.node.properties["stage4_no_bio_facts"] is True
        assert resolved.node.properties["stage4_llm_reasoning"] == "Capital of Tibet."


# ---------------------------------------------------------------- Tier 0 paths


class TestStage4FailureModes:
    """Stage 4 falls back to Tier 0 with specific reasons on each failure mode."""

    async def test_llm_refuses_returns_tier_0(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(
            default=json.dumps({"chosen": None, "confidence": 0.3, "reasoning": "Cannot tell."})
        )
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )

        resolved = await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
            sentences=[_sentence(0, "An ambiguous sentence.")],
        )

        assert resolved.tier == 0
        assert resolved.failure_reason == "stage4_llm_refused"
        # Refusal reasoning kept on the Tier-0 node for audit.
        assert resolved.node.properties["stage4_llm_reasoning"] == "Cannot tell."
        assert resolved.node.properties["stage4_llm_confidence"] == 0.3
        assert resolved.node.scores.confidence == TIER_0_CONFIDENCE
        assert resolved.node.manual_resolution_needed is True

    async def test_llm_picks_invalid_qid_returns_tier_0(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(
            default=json.dumps(
                {"chosen": "Q9999999", "confidence": 0.9, "reasoning": "Invented Q-ID."}
            )
        )
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )

        resolved = await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
            sentences=[_sentence(0, "...")],
        )

        # Defends against LLM hallucinating Q-IDs not in the candidate list.
        assert resolved.tier == 0
        assert resolved.failure_reason == "stage4_llm_chose_invalid_qid"

    async def test_llm_returns_invalid_json_returns_tier_0(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(default="not valid JSON at all")
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )

        resolved = await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
            sentences=[_sentence(0, "...")],
        )

        assert resolved.tier == 0
        assert resolved.failure_reason.startswith("stage4_parse_error:")
        assert "json_decode" in resolved.failure_reason

    async def test_llm_returns_malformed_chosen_returns_tier_0(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(
            default=json.dumps({"chosen": "not-a-qid", "confidence": 0.9, "reasoning": "x"})
        )
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )

        resolved = await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
            sentences=[_sentence(0, "...")],
        )

        assert resolved.tier == 0
        assert "invalid_chosen_format" in resolved.failure_reason


# ---------------------------------------------------------------- backward compat


class TestBackwardCompatNoLLM:
    """Resolver constructed without an LLM behaves exactly as in E2."""

    async def test_weak_match_falls_to_tier_0_with_e2_reason(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        # No llm passed.
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        assert resolver.has_llm is False

        resolved = await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
        )

        assert resolved.tier == 0
        assert resolved.failure_reason == "weak_alias_match_no_llm_configured"
        # Confirm Stage 4 fields not added to a no-LLM Tier-0 node.
        assert "stage4_llm_reasoning" not in resolved.node.properties

    async def test_no_bio_facts_calls_when_llm_absent(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]

        await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
        )

        # Verifies the resolver does not eagerly fetch bio facts when
        # there is no LLM to consume them — saves one SPARQL call per
        # mention in E2-mode pipelines.
        assert client.fetch_bio_facts_calls == []


# ---------------------------------------------------------------- Tier 4 short-circuit


class TestTier4ShortCircuitsStage4:
    """When Stages 1-3 already give a Tier-4 answer, Stage 4 must not fire
    (saves one LLM call + one SPARQL bio-facts call per mention)."""

    async def test_tier_4_does_not_call_llm_or_fetch_bio_facts(self) -> None:
        # Single survivor with EXACT in 2 languages → Tier 4 (E2 path).
        responses = FakeWikidataResponses(
            search={
                ("Sven Hedin", "en"): [_candidate("Q154759", "en", "Sven Hedin")],
                ("Sven Hedin", "de"): [_candidate("Q154759", "de", "Sven Hedin")],
                ("Sven Hedin", "fr"): [],
                ("Sven Hedin", "it"): [],
            },
            aliases={
                "Q154759": {
                    "en": ["Sven Hedin", "Hedin"],
                    "de": ["Sven Hedin", "Hedin, Sven"],
                    "fr": [],
                    "it": [],
                }
            },
            types={"Q154759": {"Q5"}},
        )
        client = FakeWikidataClient(responses)
        llm_text = json.dumps({"chosen": "Q1", "confidence": 1.0, "reasoning": "x"})
        llm = StubLLMProvider(default=llm_text)
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )

        resolved = await resolver.resolve(
            _mention("Sven Hedin", "PERSON"),
            source_ref=_book_source_ref(),
        )

        assert resolved.tier == 4
        assert resolved.chosen_qid == "Q154759"
        # LLM not called — Tier 4 is the strongest signal, no need to spend tokens.
        assert llm.calls == []
        # Bio facts not fetched either.
        assert client.fetch_bio_facts_calls == []


# ---------------------------------------------------------------- input validation


class TestSentencesOptional:
    async def test_stage4_works_without_sentences_kwarg(self) -> None:
        # Sentence context absent — the prompt shows "(not available)"
        # but Stage 4 still runs and the LLM can still pick.
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm_text = json.dumps(
            {"chosen": "Q123456", "confidence": 0.7, "reasoning": "Bio facts match."}
        )
        llm = StubLLMProvider(default=llm_text)
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )

        resolved = await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
            # sentences omitted intentionally
        )

        assert resolved.tier == 2
        assert "Source sentence: (not available)" in llm.calls[0]["prompt"]

    async def test_out_of_range_sentence_index_does_not_crash(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(
            default=json.dumps({"chosen": "Q123456", "confidence": 0.8, "reasoning": "..."})
        )
        resolver = EntityResolver(
            client=client,  # type: ignore[arg-type]
            llm=llm,
            book_context=_hedin_book_context(),
        )

        # Mention claims sentence_index=99 but we only pass 1 sentence.
        m = _mention("Aufschnaiter", "PERSON", sentence_index=99)
        sentences = [_sentence(0, "Only one sentence in the list.")]

        resolved = await resolver.resolve(m, source_ref=_book_source_ref(), sentences=sentences)
        # Defensive lookup → no sentence text in prompt, but no crash.
        assert resolved.tier == 2
        assert "(not available)" in llm.calls[0]["prompt"]


class TestNoBookContextStillWorks:
    async def test_resolver_without_book_context_renders_not_available(self) -> None:
        responses = _ambiguous_aufschnaiter_responses()
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(
            default=json.dumps({"chosen": "Q123456", "confidence": 0.8, "reasoning": "Bio match."})
        )
        # llm but no book_context.
        resolver = EntityResolver(client=client, llm=llm)  # type: ignore[arg-type]

        resolved = await resolver.resolve(
            _mention("Aufschnaiter", "PERSON"),
            source_ref=_book_source_ref(),
            sentences=[_sentence(0, "...")],
        )
        assert resolved.tier == 2
        assert "Book context: (not available)" in llm.calls[0]["prompt"]
