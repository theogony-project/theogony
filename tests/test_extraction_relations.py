"""Unit tests for :class:`RelationExtractor` (Plan §2.5, §3.3, §3a PID-2)."""

from __future__ import annotations

import json

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.extraction.ner import Mention
from theogony.extraction.relation_types import RelationType
from theogony.extraction.relations import ExtractedRelation, RelationExtractor
from theogony.extraction.sentence import Sentence

# ---------------------------------------------------------------- fixtures


def _sentence(idx: int, text: str, *, start: int = 0) -> Sentence:
    return Sentence(index=idx, text=text, start_char=start, end_char=start + len(text))


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


def _scripted_relations(rels: list[dict[str, object]]) -> str:
    return json.dumps({"relations": rels})


# ---------------------------------------------------------------- DTO


class TestExtractedRelation:
    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            ExtractedRelation(  # type: ignore[call-arg]
                subject_text="X",
                object_text="Y",
                relation_type="LOCATED_IN",
                evidence_span="X is in Y",
                confidence=0.8,
                bogus="field",
            )

    def test_confidence_must_be_in_range(self) -> None:
        with pytest.raises(ValueError):
            ExtractedRelation(
                subject_text="X",
                object_text="Y",
                relation_type="LOCATED_IN",
                evidence_span="X is in Y",
                confidence=1.5,
            )

    def test_empty_strings_rejected(self) -> None:
        with pytest.raises(ValueError):
            ExtractedRelation(
                subject_text="",
                object_text="Y",
                relation_type="LOCATED_IN",
                evidence_span="X is in Y",
                confidence=0.8,
            )


# ---------------------------------------------------------------- happy path


class TestExtraction:
    async def test_extracts_single_relation(self) -> None:
        scripted = _scripted_relations(
            [
                {
                    "subject": "Harrer",
                    "object": "Uttarkashi",
                    "relation_type": "REACHED",
                    "evidence_span": "Harrer reached Uttarkashi",
                    "confidence": 0.92,
                    "reasoning": "Direct verb 'reached' connects subject to place.",
                }
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer reached Uttarkashi at midnight.")
        mentions = [
            _mention("Harrer", "PERSON", offset=0),
            _mention("Uttarkashi", "GPE", offset=15),
        ]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)

        assert len(results) == 1
        rel = results[0]
        assert rel.subject_text == "Harrer"
        assert rel.object_text == "Uttarkashi"
        assert rel.relation_type == "REACHED"
        assert rel.evidence_span == "Harrer reached Uttarkashi"
        assert rel.confidence == 0.92
        assert rel.is_other is False

    async def test_extracts_multiple_relations(self) -> None:
        scripted = _scripted_relations(
            [
                {
                    "subject": "Harrer",
                    "object": "Aufschnaiter",
                    "relation_type": "MET",
                    "evidence_span": "Harrer met Aufschnaiter",
                    "confidence": 0.9,
                },
                {
                    "subject": "Aufschnaiter",
                    "object": "Lhasa",
                    "relation_type": "TRAVELED_TO",
                    "evidence_span": "traveled to Lhasa",
                    "confidence": 0.85,
                },
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(
            0,
            "Harrer met Aufschnaiter and they traveled to Lhasa together.",
        )
        mentions = [
            _mention("Harrer", "PERSON"),
            _mention("Aufschnaiter", "PERSON"),
            _mention("Lhasa", "GPE"),
        ]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)

        assert len(results) == 2
        assert {r.relation_type for r in results} == {"MET", "TRAVELED_TO"}

    async def test_returns_empty_when_no_relations_found(self) -> None:
        llm = StubLLMProvider(default=_scripted_relations([]))
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "The sky was bright that morning.")
        mentions = [
            _mention("sky", "OTHER"),
            _mention("morning", "TIME"),
        ]
        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert results == []


# ---------------------------------------------------------------- short-circuits


class TestShortCircuits:
    async def test_fewer_than_two_mentions_skips_llm(self) -> None:
        llm = StubLLMProvider(default=_scripted_relations([{"foo": "bar"}]))
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Just one entity here: Tibet.")
        mentions = [_mention("Tibet", "GPE")]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)

        assert results == []
        # Confirms the short-circuit: no LLM call was made.
        assert llm.calls == []

    async def test_zero_mentions_skips_llm(self) -> None:
        llm = StubLLMProvider(default=_scripted_relations([]))
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "A sentence with no entities.")
        results = await extractor.extract(central_sentence=sent, mentions=[])
        assert results == []
        assert llm.calls == []


# ---------------------------------------------------------------- evidence_span enforcement


class TestEvidenceSpanEnforcement:
    """Plan §3a PID-2 Safeguard 3: drop relations whose evidence_span
    is not a substring of the central sentence (after Unicode
    normalisation per §3.4 alias matching)."""

    async def test_drops_relation_with_evidence_span_outside_central(self) -> None:
        # The LLM hallucinates an evidence span that does not appear
        # in the central sentence — must be dropped.
        scripted = _scripted_relations(
            [
                {
                    "subject": "Harrer",
                    "object": "Lhasa",
                    "relation_type": "TRAVELED_TO",
                    "evidence_span": "Harrer flew to Lhasa by airplane",
                    "confidence": 0.9,
                }
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm)
        # The actual sentence does NOT contain "flew" or "airplane".
        sent = _sentence(0, "Harrer reached Lhasa after months on foot.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Lhasa", "GPE")]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert results == []

    async def test_keeps_relation_with_unicode_normalised_substring(self) -> None:
        # Evidence span has different case + extra whitespace; should
        # match after normalisation.
        scripted = _scripted_relations(
            [
                {
                    "subject": "Harrer",
                    "object": "Lhasa",
                    "relation_type": "REACHED",
                    "evidence_span": "HARRER  REACHED LHASA",
                    "confidence": 0.85,
                }
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer reached Lhasa.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Lhasa", "GPE")]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert len(results) == 1


# ---------------------------------------------------------------- type normalisation


class TestRelationTypeNormalisation:
    async def test_lowercase_type_normalises_to_canonical(self) -> None:
        scripted = _scripted_relations(
            [
                {
                    "subject": "Harrer",
                    "object": "Lhasa",
                    "relation_type": "traveled_to",  # lowercase
                    "evidence_span": "Harrer reached Lhasa",
                    "confidence": 0.9,
                }
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer reached Lhasa.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Lhasa", "GPE")]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert len(results) == 1
        assert results[0].relation_type == "TRAVELED_TO"
        assert results[0].is_other is False

    async def test_unknown_type_falls_to_other_with_flag(self) -> None:
        scripted = _scripted_relations(
            [
                {
                    "subject": "Harrer",
                    "object": "Aufschnaiter",
                    "relation_type": "BEFRIENDED",  # not in vocabulary
                    "evidence_span": "Harrer met Aufschnaiter",
                    "confidence": 0.7,
                }
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer met Aufschnaiter at the camp.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Aufschnaiter", "PERSON")]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert len(results) == 1
        # Plan §3.3: unknown types preserved as OTHER + flagged.
        assert results[0].relation_type == RelationType.OTHER.value
        assert results[0].is_other is True


# ---------------------------------------------------------------- LLM failure modes


class TestLLMFailureModes:
    """Honest-failure: bad LLM output → empty list, never raise into pipeline."""

    async def test_invalid_json_returns_empty_list(self) -> None:
        llm = StubLLMProvider(default="this is not JSON at all")
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer met Aufschnaiter.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Aufschnaiter", "PERSON")]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert results == []

    async def test_non_object_payload_returns_empty(self) -> None:
        llm = StubLLMProvider(default=json.dumps([1, 2, 3]))
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer met Aufschnaiter.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Aufschnaiter", "PERSON")]
        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert results == []

    async def test_relations_not_a_list_returns_empty(self) -> None:
        llm = StubLLMProvider(default=json.dumps({"relations": "broken"}))
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer met Aufschnaiter.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Aufschnaiter", "PERSON")]
        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        assert results == []

    async def test_individual_malformed_relations_dropped(self) -> None:
        # Mix of valid and invalid relations — valid ones survive.
        scripted = _scripted_relations(
            [
                {  # missing subject
                    "object": "Lhasa",
                    "relation_type": "TRAVELED_TO",
                    "evidence_span": "Harrer reached Lhasa",
                    "confidence": 0.9,
                },
                {  # valid
                    "subject": "Harrer",
                    "object": "Lhasa",
                    "relation_type": "REACHED",
                    "evidence_span": "Harrer reached Lhasa",
                    "confidence": 0.85,
                },
                {  # confidence wrong type
                    "subject": "Harrer",
                    "object": "Lhasa",
                    "relation_type": "MET",
                    "evidence_span": "Harrer reached Lhasa",
                    "confidence": "high",
                },
                {  # evidence_span empty
                    "subject": "Harrer",
                    "object": "Lhasa",
                    "relation_type": "MET",
                    "evidence_span": "",
                    "confidence": 0.5,
                },
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(0, "Harrer reached Lhasa after years.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Lhasa", "GPE")]

        results = await extractor.extract(central_sentence=sent, mentions=mentions)
        # Only the well-formed REACHED relation survives.
        assert len(results) == 1
        assert results[0].relation_type == "REACHED"


# ---------------------------------------------------------------- prompt assembly


class TestPromptAssembly:
    async def test_single_sentence_prompt_omits_window_sections(self) -> None:
        llm = StubLLMProvider(default=_scripted_relations([]))
        extractor = RelationExtractor(llm=llm, expand_window=False)
        sent = _sentence(0, "Harrer met Aufschnaiter.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Aufschnaiter", "PERSON")]
        await extractor.extract(central_sentence=sent, mentions=mentions)

        prompt = llm.calls[0]["prompt"]
        assert "PREVIOUS SENTENCE" not in prompt
        assert "NEXT SENTENCE" not in prompt
        assert "Harrer met Aufschnaiter" in prompt
        # Mentions block present.
        assert "Harrer" in prompt and "Aufschnaiter" in prompt
        # Allowed types listed.
        assert "LOCATED_IN" in prompt
        assert "OTHER" in prompt
        # JSON schema enforced.
        assert llm.calls[0]["json_schema"] is not None
        assert llm.calls[0]["temperature"] == 0.0

    async def test_mentions_block_dedupes_repeated_surface_forms(self) -> None:
        llm = StubLLMProvider(default=_scripted_relations([]))
        extractor = RelationExtractor(llm=llm)
        sent = _sentence(
            0,
            "Tibet is great. Tibet is high. Tibet is cold. Hedin came to Tibet.",
        )
        mentions = [
            _mention("Tibet", "GPE", offset=0),
            _mention("Tibet", "GPE", offset=14),
            _mention("Tibet", "GPE", offset=28),
            _mention("Hedin", "PERSON", offset=42),
            _mention("Tibet", "GPE", offset=58),
        ]
        await extractor.extract(central_sentence=sent, mentions=mentions)

        prompt = llm.calls[0]["prompt"]
        # "Tibet" should appear only once in the mentions block,
        # not four times (saves tokens, sharper signal to LLM).
        mentions_section = prompt.split("Mentioned entities (from NER):")[1].split(
            "Allowed relation types"
        )[0]
        assert mentions_section.count('"Tibet"') == 1


# ---------------------------------------------------------------- expand_window


class TestExpandWindow:
    async def test_expand_window_includes_three_sections(self) -> None:
        llm = StubLLMProvider(default=_scripted_relations([]))
        extractor = RelationExtractor(llm=llm, expand_window=True)
        prev = _sentence(0, "He had been wandering for weeks.")
        central = _sentence(1, "Harrer reached Uttarkashi at midnight.")
        nxt = _sentence(2, "There he met the Marchese for the first time.")
        mentions = [
            _mention("Harrer", "PERSON", sentence_index=1),
            _mention("Uttarkashi", "GPE", sentence_index=1),
        ]

        await extractor.extract(
            central_sentence=central,
            mentions=mentions,
            previous_sentence=prev,
            next_sentence=nxt,
        )

        prompt = llm.calls[0]["prompt"]
        # Three sections, with the "(context only)" / "(extract from
        # here)" annotations Plan §3a PID-2 calls out by name.
        assert "PREVIOUS SENTENCE" in prompt
        assert "CENTRAL SENTENCE" in prompt
        assert "NEXT SENTENCE" in prompt
        assert "context only" in prompt
        assert "extract relations FROM HERE" in prompt
        # Sentences appear verbatim.
        assert "He had been wandering for weeks." in prompt
        assert "Harrer reached Uttarkashi at midnight." in prompt
        assert "There he met the Marchese for the first time." in prompt

    async def test_expand_window_false_ignores_neighbours(self) -> None:
        # Even when prev/next supplied, expand_window=False omits them.
        llm = StubLLMProvider(default=_scripted_relations([]))
        extractor = RelationExtractor(llm=llm, expand_window=False)
        prev = _sentence(0, "Previous text.")
        central = _sentence(1, "Harrer met Aufschnaiter.")
        nxt = _sentence(2, "Next text.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Aufschnaiter", "PERSON")]

        await extractor.extract(
            central_sentence=central,
            mentions=mentions,
            previous_sentence=prev,
            next_sentence=nxt,
        )

        prompt = llm.calls[0]["prompt"]
        assert "Previous text." not in prompt
        assert "Next text." not in prompt
        assert "PREVIOUS SENTENCE" not in prompt

    async def test_expand_window_with_only_previous(self) -> None:
        # Expanded mode with only previous sentence — next renders "(none)".
        llm = StubLLMProvider(default=_scripted_relations([]))
        extractor = RelationExtractor(llm=llm, expand_window=True)
        prev = _sentence(0, "He was tired.")
        central = _sentence(1, "Harrer met Aufschnaiter.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Aufschnaiter", "PERSON")]

        await extractor.extract(central_sentence=central, mentions=mentions, previous_sentence=prev)
        prompt = llm.calls[0]["prompt"]
        assert "He was tired." in prompt
        # Next-section placeholder in the renderer.
        assert "(none)" in prompt

    async def test_expand_window_drops_relation_with_span_in_previous(self) -> None:
        # The LLM mistakenly extracts a relation with evidence span
        # only in the previous sentence — must still be dropped per
        # PID-2 Safeguard 3 (substring check is against CENTRAL only).
        scripted = _scripted_relations(
            [
                {
                    "subject": "He",
                    "object": "weeks",
                    "relation_type": "OTHER",
                    "evidence_span": "wandering for weeks",
                    "confidence": 0.5,
                }
            ]
        )
        llm = StubLLMProvider(default=scripted)
        extractor = RelationExtractor(llm=llm, expand_window=True)
        prev = _sentence(0, "He had been wandering for weeks.")
        central = _sentence(1, "Harrer reached Uttarkashi at midnight.")
        mentions = [_mention("Harrer", "PERSON"), _mention("Uttarkashi", "GPE")]

        results = await extractor.extract(
            central_sentence=central,
            mentions=mentions,
            previous_sentence=prev,
        )
        # The "wandering for weeks" span lives in PREVIOUS, not CENTRAL.
        assert results == []
