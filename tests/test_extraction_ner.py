"""Tests for NerExtractor + Mention DTO (Plan §2.5)."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from theogony.extraction.ner import DEFAULT_NER_MODEL, Mention, NerExtractor
from theogony.extraction.sentence import Sentence

# ---------------------------------------------------------------------------
# Mention DTO
# ---------------------------------------------------------------------------


class TestMentionDTO:
    def _kwargs(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "text": "Lhasa",
            "label": "GPE",
            "sentence_index": 5,
            "start_char_in_sentence": 12,
            "end_char_in_sentence": 17,
            "start_char_in_source": 412,
            "end_char_in_source": 417,
        }
        base.update(overrides)
        return base

    def test_basic_construction(self) -> None:
        m = Mention(**self._kwargs())
        assert m.text == "Lhasa"
        assert m.label == "GPE"
        assert m.sentence_index == 5

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Mention(**self._kwargs(typo_field="oops"))

    def test_negative_offset_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Mention(**self._kwargs(start_char_in_sentence=-1))
        with pytest.raises(ValidationError):
            Mention(**self._kwargs(start_char_in_source=-1))

    def test_round_trip_json(self) -> None:
        m = Mention(**self._kwargs())
        restored = Mention.model_validate_json(m.model_dump_json())
        assert restored == m


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_ent(text: str, label: str, start_char: int, end_char: int) -> MagicMock:
    ent = MagicMock()
    ent.text = text
    ent.label_ = label
    ent.start_char = start_char
    ent.end_char = end_char
    return ent


def _fake_doc(ents: list[MagicMock]) -> MagicMock:
    doc = MagicMock()
    doc.ents = ents
    return doc


def _fake_nlp(per_text: dict[str, list[MagicMock]]) -> MagicMock:
    """A spacy.Language-like callable that returns scripted Docs by sentence text."""
    nlp = MagicMock()

    def _call(text: str) -> MagicMock:
        return _fake_doc(per_text.get(text, []))

    nlp.side_effect = _call
    return nlp


def _make_sentence(
    *,
    index: int,
    text: str,
    start_char: int,
) -> Sentence:
    return Sentence(
        index=index,
        text=text,
        start_char=start_char,
        end_char=start_char + len(text),
    )


# ---------------------------------------------------------------------------
# Lazy load + error path (no model required)
# ---------------------------------------------------------------------------


class TestLazyLoad:
    def test_model_not_loaded_until_first_extract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        load_count = 0

        def _counted_load() -> Any:
            nonlocal load_count
            load_count += 1
            return _fake_nlp({})

        ner = NerExtractor()
        monkeypatch.setattr(ner, "_load_model", _counted_load)
        # Construction does not load.
        assert load_count == 0

        import asyncio as _aio

        _aio.run(ner.extract([_make_sentence(index=0, text="x.", start_char=0)]))
        assert load_count == 1

    def test_missing_model_raises_friendly_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Most common new-contributor stumble: forgetting `python -m spacy download`."""
        import spacy

        def _raising_load(name: str) -> Any:
            raise OSError(f"[E050] Can't find model {name!r}")

        monkeypatch.setattr(spacy, "load", _raising_load)
        ner = NerExtractor(model_name="not_real_model")
        with pytest.raises(RuntimeError, match="python -m spacy download"):
            ner._load_model()


# ---------------------------------------------------------------------------
# extract() with mocked spaCy (covers all wrapper logic without the model)
# ---------------------------------------------------------------------------


class TestExtractMocked:
    async def test_empty_input_returns_empty_without_load(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel = MagicMock()
        ner = NerExtractor()
        monkeypatch.setattr(ner, "_load_model", lambda: sentinel)
        result = await ner.extract([])
        assert result == []
        sentinel.assert_not_called()  # model never loaded for empty input

    async def test_basic_extraction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent_text = "Harrer reached Lhasa at midnight."
        nlp = _fake_nlp(
            {
                sent_text: [
                    _fake_ent("Harrer", "PERSON", 0, 6),
                    _fake_ent("Lhasa", "GPE", 15, 20),
                ]
            }
        )
        ner = NerExtractor()
        monkeypatch.setattr(ner, "_load_model", lambda: nlp)
        sentences = [_make_sentence(index=0, text=sent_text, start_char=42)]
        result = await ner.extract(sentences)
        assert len(result) == 1
        ms = result[0]
        assert [m.text for m in ms] == ["Harrer", "Lhasa"]
        assert [m.label for m in ms] == ["PERSON", "GPE"]
        assert [m.sentence_index for m in ms] == [0, 0]
        # Sentence-relative offsets pass through.
        assert ms[0].start_char_in_sentence == 0
        assert ms[1].start_char_in_sentence == 15
        # Source-absolute offsets = sentence start + ent start.
        assert ms[0].start_char_in_source == 42  # 42 + 0
        assert ms[1].start_char_in_source == 42 + 15

    async def test_per_sentence_structure_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nlp = _fake_nlp(
            {
                "Harrer was Austrian.": [_fake_ent("Harrer", "PERSON", 0, 6)],
                "Lhasa is the capital.": [_fake_ent("Lhasa", "GPE", 0, 5)],
                "Empty sentence here.": [],
            }
        )
        ner = NerExtractor()
        monkeypatch.setattr(ner, "_load_model", lambda: nlp)
        sentences = [
            _make_sentence(index=0, text="Harrer was Austrian.", start_char=0),
            _make_sentence(index=1, text="Lhasa is the capital.", start_char=21),
            _make_sentence(index=2, text="Empty sentence here.", start_char=43),
        ]
        result = await ner.extract(sentences)
        assert len(result) == 3
        assert [len(per) for per in result] == [1, 1, 0]
        assert result[0][0].sentence_index == 0
        assert result[1][0].sentence_index == 1

    async def test_blank_text_entities_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent_text = "Real sentence."
        nlp = _fake_nlp(
            {
                sent_text: [
                    _fake_ent("", "PERSON", 0, 0),
                    _fake_ent("   ", "GPE", 5, 8),
                    _fake_ent("Real", "ORG", 0, 4),
                ]
            }
        )
        ner = NerExtractor()
        monkeypatch.setattr(ner, "_load_model", lambda: nlp)
        result = await ner.extract([_make_sentence(index=0, text=sent_text, start_char=0)])
        assert len(result[0]) == 1
        assert result[0][0].text == "Real"


class TestExtractFlat:
    async def test_flattens_in_sentence_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        nlp = _fake_nlp(
            {
                "S0.": [_fake_ent("E0a", "X", 0, 3), _fake_ent("E0b", "X", 4, 7)],
                "S1.": [_fake_ent("E1a", "X", 0, 3)],
                "S2.": [],
                "S3.": [_fake_ent("E3a", "X", 0, 3)],
            }
        )
        ner = NerExtractor()
        monkeypatch.setattr(ner, "_load_model", lambda: nlp)
        sentences = [_make_sentence(index=i, text=f"S{i}.", start_char=i * 4) for i in range(4)]
        flat = await ner.extract_flat(sentences)
        assert [m.text for m in flat] == ["E0a", "E0b", "E1a", "E3a"]
        assert [m.sentence_index for m in flat] == [0, 0, 1, 3]


# ---------------------------------------------------------------------------
# Real en_core_web_sm integration (gated)
# ---------------------------------------------------------------------------


class TestRealNerIntegration:
    """Integration test against a real spaCy ``en_core_web_sm`` model.

    Skipped unless THEOGONY_RUN_NER_INTEGRATION=1 is set AND the model
    is installed (``python -m spacy download en_core_web_sm``).
    """

    @pytest.mark.skipif(
        os.environ.get("THEOGONY_RUN_NER_INTEGRATION") != "1",
        reason="set THEOGONY_RUN_NER_INTEGRATION=1 to run real spaCy NER",
    )
    async def test_real_ner_finds_persons_and_places(self) -> None:
        ner = NerExtractor()
        sentences = [
            _make_sentence(
                index=0,
                text=("Heinrich Harrer reached Lhasa in 1944 after a long journey from India."),
                start_char=0,
            )
        ]
        result = await ner.extract(sentences)
        labels = {m.label for m in result[0]}
        # Real spaCy en_core_web_sm reliably tags Harrer as PERSON and
        # Lhasa as GPE on this English sentence.
        assert "PERSON" in labels
        assert "GPE" in labels
        # Substring invariant: every mention's text equals the source slice.
        for sent_mentions in result:
            for m in sent_mentions:
                src_text = sentences[m.sentence_index].text
                assert src_text[m.start_char_in_sentence : m.end_char_in_sentence] == m.text

    @pytest.mark.skipif(
        os.environ.get("THEOGONY_RUN_NER_INTEGRATION") != "1",
        reason="set THEOGONY_RUN_NER_INTEGRATION=1 to run real spaCy NER",
    )
    async def test_default_model_name_is_en_core_web_sm(self) -> None:
        # Sanity: the default really is what Plan §2.5 names.
        assert NerExtractor().model_name == DEFAULT_NER_MODEL == "en_core_web_sm"
