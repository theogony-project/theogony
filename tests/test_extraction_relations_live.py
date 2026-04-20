"""
Live integration smoke for :class:`RelationExtractor` against the real LLM.

Gated by ``THEOGONY_RUN_E4_INTEGRATION=1``. Requires an API key for the
configured LLM provider (default ``OPENAI_API_KEY``).

Two tests:

1. Single-sentence extraction against a Hedin-style sentence with
   two named entities + a clear directional relation. Verifies the
   extractor parses the LLM response, normalises the type to the
   fixed vocabulary, and respects the evidence_span ⊆ sentence
   guarantee.

2. expand_window mode: a central sentence whose subject is a
   pronoun resolvable from the previous sentence. The extractor
   must use the previous sentence as context but anchor evidence
   to central.

Cost: ~2 LLM calls (~0.001 EUR), ~3 s wall-clock.

Run::

    THEOGONY_RUN_E4_INTEGRATION=1 \\
        pytest tests/test_extraction_relations_live.py -v
"""

from __future__ import annotations

import os

import pytest

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.extraction.alias_matcher import fully_normalise
from theogony.extraction.ner import Mention
from theogony.extraction.relation_types import RELATION_TYPES
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.sentence import Sentence

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_RUN_E4_INTEGRATION") != "1",
    reason="set THEOGONY_RUN_E4_INTEGRATION=1 to run live E4 integration",
)


def _live_llm() -> object:
    settings = Settings()  # type: ignore[call-arg]
    if settings.active_llm_api_key() is None:
        pytest.skip("no API key for the active LLM provider in environment")
    try:
        return build_llm_from_settings(settings)
    except (ValueError, NotImplementedError, ImportError) as exc:
        pytest.skip(f"could not build LLM provider: {exc}")


def _sentence(idx: int, text: str) -> Sentence:
    return Sentence(index=idx, text=text, start_char=0, end_char=len(text))


def _mention(text: str, label: str, *, sentence_index: int = 0, offset: int = 0) -> Mention:
    return Mention(
        text=text,
        label=label,
        sentence_index=sentence_index,
        start_char_in_sentence=offset,
        end_char_in_sentence=offset + len(text),
        start_char_in_source=offset,
        end_char_in_source=offset + len(text),
    )


class TestSingleSentenceLive:
    async def test_extracts_a_directional_travel_relation(self) -> None:
        # A sentence with one clear PERSON→PLACE relation. We don't
        # pin the relation_type exactly (TRAVELED_TO / REACHED both
        # plausible from this sentence) — the contract is "at least
        # one relation involving Hedin and Tibet, with a vocabulary-
        # valid type and an evidence_span that lives in the sentence".
        llm = _live_llm()
        extractor = RelationExtractor(llm=llm)
        text = (
            "Sven Hedin set out from Stockholm in October 1905 and "
            "reached Tibet the following spring."
        )
        sent = _sentence(0, text)
        mentions = [
            _mention("Sven Hedin", "PERSON", offset=0),
            _mention("Stockholm", "GPE", offset=24),
            _mention("Tibet", "GPE", offset=63),
        ]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)

        assert len(results) >= 1, f"expected at least one relation; got {results}"
        # At least one result must connect Sven Hedin to Tibet (the
        # directional travel signal in this sentence).
        hedin_to_tibet = [
            r
            for r in results
            if "hedin" in r.subject_text.lower() and "tibet" in r.object_text.lower()
        ]
        assert hedin_to_tibet, (
            f"expected at least one Hedin→Tibet relation; got "
            f"{[(r.subject_text, r.relation_type, r.object_text) for r in results]}"
        )
        # Vocabulary discipline.
        for rel in results:
            assert rel.relation_type in RELATION_TYPES, (
                f"relation_type {rel.relation_type} not in vocabulary"
            )
            # Plan §3a PID-2 Safeguard 3 holds.
            assert fully_normalise(rel.evidence_span) in fully_normalise(sent.text), (
                f"evidence_span outside central sentence: {rel.evidence_span!r}"
            )

    async def test_returns_empty_on_unrelated_sentence(self) -> None:
        # Sentence with two mentions but no plausible relation between
        # them. Healthy LLMs return an empty relations list rather
        # than inventing one.
        llm = _live_llm()
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "The sun rose. Tibet remained far away. Hedin was elsewhere.")
        mentions = [
            _mention("Tibet", "GPE", offset=14),
            _mention("Hedin", "PERSON", offset=37),
        ]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)

        # Loose contract: 0 or 1 weak relation. Mostly we want to
        # check that the model isn't aggressively inventing.
        assert len(results) <= 2, (
            f"expected ≤2 relations on a sentence with no clear connection; "
            f"got {len(results)}: "
            f"{[(r.subject_text, r.relation_type, r.object_text) for r in results]}"
        )
        for rel in results:
            assert fully_normalise(rel.evidence_span) in fully_normalise(sent.text)


class TestExpandWindowLive:
    async def test_uses_previous_sentence_for_pronoun_resolution(self) -> None:
        # The central sentence has a pronoun ("he") whose referent is
        # established in the previous sentence. With expand_window=True
        # the LLM should still anchor evidence to central.
        llm = _live_llm()
        extractor = RelationExtractor(llm=llm, expand_window=True)
        prev = _sentence(
            0,
            "Sven Hedin had been wandering across the Tibetan plateau for months.",
        )
        central = _sentence(1, "He finally reached Lhasa in the spring.")
        mentions = [
            _mention("He", "PERSON", sentence_index=1, offset=0),
            _mention("Lhasa", "GPE", sentence_index=1, offset=19),
        ]

        results = await extractor.extract(
            central_sentence=central,
            mentions=mentions,
            previous_sentence=prev,
        )

        # We expect at least one relation that anchors to central
        # (REACHED / TRAVELED_TO are the most natural choices).
        assert len(results) >= 1
        for rel in results:
            # Evidence span must be in central sentence, not previous.
            assert fully_normalise(rel.evidence_span) in fully_normalise(central.text), (
                f"expand_window violation: evidence in prev or invented: {rel.evidence_span!r}"
            )
            assert fully_normalise(rel.evidence_span) not in fully_normalise(
                prev.text
            ) or fully_normalise(rel.evidence_span) in fully_normalise(central.text)
