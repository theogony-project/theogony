"""
NerExtractor — find named-entity mentions per sentence (Plan §2.5).

Plan §2.5 specifies spaCy ``en_core_web_sm`` (default) with optional
upgrade to ``en_core_web_trf`` (~440 MB). Mentions are anchored
to sentences per Plan §3a PID-1 — every Mention carries its
sentence_index plus char offsets *within that sentence*. The
EntityResolver, RelationExtractor, and source-citation layers all
walk this back to a SourceRef using ``RawContent.to_source_ref``.

Discipline:

- **Lazy model load.** Importing this module costs nothing.
  ``spacy.load(model_name)`` happens on first ``extract`` call.
- **Async wrapper.** spaCy's pipeline is synchronous CPU work; we
  run it in a thread executor so concurrent ingest tasks can keep
  the event loop responsive.
- **Honest failure.** When ``en_core_web_sm`` is not installed,
  the first ``extract`` call raises a clear instruction
  ("python -m spacy download en_core_web_sm") rather than a raw
  spaCy OSError. Catches the most common new-contributor stumble.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.logging import get_logger
from theogony.extraction.sentence import Sentence

log = get_logger("extraction.ner")

DEFAULT_NER_MODEL = "en_core_web_sm"


class Mention(BaseModel):
    """A named-entity mention anchored to one sentence (Plan §3a PID-1).

    Two coordinate systems are recorded:

    - ``sentence_index`` + ``start_char_in_sentence`` /
      ``end_char_in_sentence``: the sentence-relative address. This is
      what the RelationExtractor's ``evidence_span`` substring check
      operates on (Plan §3a PID-2 + §9.5).

    - ``start_char_in_source`` / ``end_char_in_source``: the absolute
      offset in the cleaned source text. This is what
      ``SourceRef.location`` records (Plan §1 demo:
      "chapter 3, offset 18433–18601").
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="The verbatim mention substring.")
    label: str = Field(
        description=(
            "spaCy NER label: PERSON, GPE (countries/cities/states), LOC "
            "(non-GPE locations), ORG, DATE, EVENT, WORK_OF_ART, ... "
            "Mapped to wikidata-aware types in EntityResolver Stage 3."
        ),
    )
    sentence_index: int = Field(ge=0)
    start_char_in_sentence: int = Field(ge=0)
    end_char_in_sentence: int = Field(ge=0)
    start_char_in_source: int = Field(ge=0)
    end_char_in_source: int = Field(ge=0)


class NerExtractor:
    """Run spaCy NER over a list of sentences, returning per-sentence mentions.

    Stateless after construction (modulo the lazy-loaded model).
    Safe to share across asyncio tasks.
    """

    def __init__(self, *, model_name: str = DEFAULT_NER_MODEL) -> None:
        self._model_name = model_name
        self._nlp: Any | None = None  # lazy spacy.Language

    @property
    def model_name(self) -> str:
        return self._model_name

    def _load_model(self) -> Any:
        """Lazy spaCy model load with a friendly error message on miss."""
        if self._nlp is not None:
            return self._nlp
        try:
            import spacy
        except ImportError as exc:  # pragma: no cover - spaCy is a hard dep
            raise ImportError(
                "NerExtractor requires the spacy package — included in core "
                "dependencies. If this fires you have a broken environment."
            ) from exc
        try:
            self._nlp = spacy.load(self._model_name)
        except OSError as exc:
            raise RuntimeError(
                f"spaCy model {self._model_name!r} is not installed. "
                f"Run: python -m spacy download {self._model_name}"
            ) from exc
        log.info("loaded spacy model %s", self._model_name)
        return self._nlp

    def _extract_sync(self, sentences: list[Sentence]) -> list[list[Mention]]:
        """Run NER on each sentence individually.

        Per-sentence calls keep entity offsets sentence-local without
        having to back-out boundaries from a doc-level Doc. Slightly
        slower than ``nlp.pipe`` over a single concatenated string but
        the data model wants sentence-relative offsets and we don't
        want a re-mapping pass.
        """
        nlp = self._load_model()
        out: list[list[Mention]] = []
        for sent in sentences:
            doc = nlp(sent.text)
            mentions: list[Mention] = []
            for ent in doc.ents:
                if not ent.text.strip():
                    continue
                mentions.append(
                    Mention(
                        text=ent.text,
                        label=ent.label_,
                        sentence_index=sent.index,
                        start_char_in_sentence=ent.start_char,
                        end_char_in_sentence=ent.end_char,
                        start_char_in_source=sent.start_char + ent.start_char,
                        end_char_in_source=sent.start_char + ent.end_char,
                    )
                )
            out.append(mentions)
        return out

    async def extract(self, sentences: list[Sentence]) -> list[list[Mention]]:
        """Return one list of mentions per sentence, in input order.

        Empty input ⇒ empty output, no model load. Useful for
        early-out paths before paying the spaCy cold-start cost.
        """
        if not sentences:
            return []
        return await asyncio.to_thread(self._extract_sync, sentences)

    async def extract_flat(self, sentences: list[Sentence]) -> list[Mention]:
        """Convenience: flatten the per-sentence lists into a single list.

        Order: every mention from sentence 0 first, then every mention
        from sentence 1, etc. Most callers (the IngestionPipeline,
        the report's NerSummary) want the flat form; ``extract``
        returns the structured form for callers that need to know
        which sentence a mention came from independently of
        ``Mention.sentence_index``.
        """
        return [m for per_sentence in await self.extract(sentences) for m in per_sentence]
