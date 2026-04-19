"""
Sentencizer — split cleaned text into sentence units (Plan §2.5, §3a PID-1).

PID-1 locks sentence-level granularity for every downstream stage:
NER mentions, RelationExtractor evidence spans, KnowledgeNode source
locations all anchor to a single sentence. This module is what
produces those sentences.

Plan §2.5 names spaCy ``en_core_web_sm`` as the segmenter. Etappe-E1
ships **spaCy's rule-based** ``sentencizer`` instead — it is part of
spaCy core (no model download required), is deterministic, and is
adequate for the English narrative prose Gen 1 ingests. If a future
Etappe finds the model-based segmenter materially better on
historical-prose punctuation, swapping is one constructor argument
(``language_pipeline=...``).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.logging import get_logger
from theogony.extraction.clean import CleanedContent

if TYPE_CHECKING:
    pass

log = get_logger("extraction.sentence")


class Sentence(BaseModel):
    """One sentence carved out of a CleanedContent.

    ``index`` is the 0-based position in the source — the natural
    sentence-level address Plan §3a PID-1 wants. ``start_char`` /
    ``end_char`` are offsets into the **cleaned** text (CleanedContent.content),
    not the raw source. The cleaner's forensic offsets bridge back
    when needed.
    """

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    text: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)


class Sentencizer:
    """Split cleaned text into a list of :class:`Sentence` objects.

    Stateless once initialised; safe to share across asyncio tasks.
    The underlying spaCy pipeline is built lazily on first call so
    importing this module costs nothing.
    """

    def __init__(self, *, min_chars: int = 1) -> None:
        # Sentences shorter than this are dropped (rare — single-character
        # "sentences" are usually punctuation artefacts after clean).
        self._min_chars = max(0, min_chars)
        self._nlp: Any | None = None  # lazy spaCy pipeline

    def _load_pipeline(self) -> Any:
        """Lazy-build a spaCy English pipeline with the rule-based sentencizer.

        Synchronous; called inside :meth:`asyncio.to_thread` from
        :meth:`sentencize`. ``spacy.lang.en.English`` is part of
        spaCy core — no model download.
        """
        if self._nlp is None:
            from spacy.lang.en import English

            log.info("loading spacy english pipeline + rule-based sentencizer")
            nlp = English()
            nlp.add_pipe("sentencizer")
            self._nlp = nlp
        return self._nlp

    def _sentencize_sync(self, text: str) -> list[Sentence]:
        nlp = self._load_pipeline()
        doc = nlp(text)
        sentences: list[Sentence] = []
        idx = 0
        for span in doc.sents:
            sentence_text = span.text
            stripped = sentence_text.strip()
            if len(stripped) < self._min_chars:
                continue
            sentences.append(
                Sentence(
                    index=idx,
                    text=sentence_text,
                    start_char=span.start_char,
                    end_char=span.end_char,
                )
            )
            idx += 1
        return sentences

    async def sentencize(self, content: str | CleanedContent) -> list[Sentence]:
        """Split ``content`` into sentences.

        Accepts either a plain string or a :class:`CleanedContent` —
        the latter is the natural pipeline input from TextCleaner.
        """
        text = content.content if isinstance(content, CleanedContent) else content
        if not text:
            return []
        return await asyncio.to_thread(self._sentencize_sync, text)
