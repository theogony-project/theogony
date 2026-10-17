"""Rebuild a mesh from recorded Kadmos readings — the shipped write path, no LLM.

A reading is what the language model answered when Kadmos showed it one
paragraph: concepts, relations, a paragraph concept, a stance. Record those
once and a mesh can be built from them anywhere, by anyone, deterministically
and without a key: the same linker, the same identity resolution, the same
typed edges and frames a live read produces, because the reader is the same
reader — only its language model is a lookup table.

Built for the 2WikiMultihopQA answer arm (PHX-1110), where it rebuilt a mesh
from 6,119 cached readings in 82 minutes without one LLM call. It lives here
rather than in `mesh.eval` since PHX-1112 made it a shipped path: the demo
mesh an arriving agent builds from the bundled readings of Hesiod's Theogony
(`theogony mesh demo`) is a replay.

The lookup is keyed by the paragraph text, hashed (:func:`reading_key`), so a
readings file carries no copy of the corpus; and the key is taken from the
stripped paragraph exactly as the reader strips it, so the replay finds the
paragraph under the identical string.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from theogony.agents.llm import LLMResult
from theogony.config.settings import Settings
from theogony.mesh.ingestion.kadmos_v2 import (
    PARAGRAPH_PROMPT_HEAD,
    PARAGRAPH_PROMPT_TAIL,
    MeshParagraphReader,
    _split_paragraphs,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

# Shorter than the reader's own cut-off would be pointless: the reader skips
# paragraphs under ten characters, so a recorder reading them records nothing
# the replay could use.
MIN_PARAGRAPH_CHARS = 10


def reading_key(text: str) -> str:
    """blake2b-128 of a paragraph — the key a reading is stored under.

    Also the key `scripts/mesh_qa_kadmos.py` wrote six thousand cached 2Wiki
    rows under (of the passage *text*, there); a drift between the two would
    silently miss every row.
    """
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def load_readings(path: Path) -> dict[str, dict[str, Any]]:
    """The readings file, keyed as written; gzip or plain.

    Rows without a ``key`` are skipped — a file may open with a ``meta`` row
    saying what was recorded, with which model, when — and so are lines that
    do not parse. A reading that is ``null`` or empty is kept out, so a
    paragraph whose reading failed is a miss at replay time, not a paragraph
    with no concepts.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    cache: dict[str, dict[str, Any]] = {}
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("key")
            if isinstance(key, str):
                cache[key] = row.get("reading") or {}
    return cache


def load_readings_meta(path: Path) -> dict[str, Any]:
    """The ``meta`` row of a readings file, or an empty dict."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                return {}
            meta = row.get("meta")
            return dict(meta) if isinstance(meta, dict) else {}
    return {}


def paragraphs_of(text: str, *, max_paragraphs: int = 0) -> list[str]:
    """The paragraphs the reader will read from ``text``, in order.

    Mirrors the reader's own order — cap first, then skip what is under ten
    characters — so that a recorder, a replay and a plan agree on the count
    even when a heading or a lone number sits inside the first ``max_paragraphs``.
    """
    raw = _split_paragraphs(text)
    if max_paragraphs > 0:
        raw = raw[:max_paragraphs]
    return [p.strip() for p in raw if len(p.strip()) >= MIN_PARAGRAPH_CHARS]


def readings_for_text(
    text: str, readings: Mapping[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Re-key a readings cache by the paragraph strings the reader will send."""
    return {
        p: readings[reading_key(p)]
        for p in paragraphs_of(text)
        if reading_key(p) in readings and readings[reading_key(p)]
    }


class ReplayReadingProvider:
    """An LLM that answers Kadmos's paragraph prompt from stored readings.

    Exact match on the paragraph, not prefix match: `StubLLMProvider` scans
    every key per call, which is fine for a test fixture and quadratic for six
    thousand paragraphs. A paragraph the cache does not hold gets an empty
    completion, which the reader records as a schema failure — visible in the
    read report rather than silently absorbed as a paragraph with no concepts.
    """

    def __init__(
        self,
        by_paragraph: Mapping[str, dict[str, Any]],
        *,
        model_id: str = "kadmos-replay",
        on_call: Callable[[int], None] | None = None,
    ) -> None:
        self._readings = by_paragraph
        self._model_id = model_id
        self._on_call = on_call
        self.hits = 0
        self.misses: list[str] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    @staticmethod
    def paragraph_in(prompt: str) -> str | None:
        """The paragraph between the prompt's head and its instruction tail."""
        if not prompt.startswith(PARAGRAPH_PROMPT_HEAD):
            return None
        body = prompt[len(PARAGRAPH_PROMPT_HEAD) :]
        end = body.rfind(PARAGRAPH_PROMPT_TAIL)
        return (body if end < 0 else body[:end]).strip()

    async def complete(self, prompt: str, *, system: str | None = None, **_: Any) -> LLMResult:
        paragraph = self.paragraph_in(prompt)
        reading = self._readings.get(paragraph) if paragraph is not None else None
        if self._on_call is not None:
            self._on_call(self.hits + len(self.misses) + 1)
        if not reading:
            self.misses.append(paragraph if paragraph is not None else prompt[:80])
            return LLMResult(text="", model_id=self._model_id)
        self.hits += 1
        return LLMResult(text=json.dumps(reading), model_id=self._model_id)

    async def complete_with_web_search_for_research_plan(self, **_: Any) -> Any:
        """Protocol member no reader calls; a replay has nothing to search."""
        raise NotImplementedError("the replay provider only answers paragraph prompts")


@dataclass
class ReplayReport:
    paragraphs: int
    hits: int
    misses: int
    report: dict[str, Any]


async def replay_text(
    runtime: MeshRuntime,
    text: str,
    readings: Mapping[str, dict[str, Any]],
    *,
    source_type: str,
    source_identifier: str,
    title: str,
    anchor: str,
    max_paragraphs: int = 0,
    compact_every: int = 200,
    on_call: Callable[[int], None] | None = None,
    settings: Settings | None = None,
) -> ReplayReport:
    """Write ``text`` into a mesh through the shipped reader, readings replayed.

    The reader splits, strips, embeds, resolves identities, links and writes
    exactly as it does on a live read; only the paragraph reading comes from
    ``readings`` instead of a language model. The embedder is the live one, so
    the workspace's vectors are the configured embedding model's — pass a
    ``runtime`` whose ``semantic_dim`` is that model's dimension or the
    vectoriser falls back to hash projections.
    """
    by_paragraph = readings_for_text(text, readings)
    provider = ReplayReadingProvider(by_paragraph, on_call=on_call)
    reader = MeshParagraphReader(
        runtime,
        llm=provider,
        max_paragraphs=max_paragraphs,
        compact_every=compact_every,
        settings=settings,
    )
    report = await reader.read_text(
        text=text,
        source_type=source_type,
        source_identifier=source_identifier,
        title=title,
        anchor=anchor,
    )
    # Counted, not computed: every paragraph the reader read reached the
    # provider once, as a hit or as a miss.
    return ReplayReport(
        paragraphs=provider.hits + len(provider.misses),
        hits=provider.hits,
        misses=len(provider.misses),
        report=report,
    )


__all__ = [
    "MIN_PARAGRAPH_CHARS",
    "ReplayReadingProvider",
    "ReplayReport",
    "load_readings",
    "load_readings_meta",
    "paragraphs_of",
    "reading_key",
    "readings_for_text",
    "replay_text",
]
