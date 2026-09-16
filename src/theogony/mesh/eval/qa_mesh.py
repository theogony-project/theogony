"""The answer arm on a corpus the model does not know by heart (PHX-1110).

PHX-1098 closed the founding corpus as a control group: deepseek answers Hesiod
at 86% with no context at all, so on that corpus the Constellation arm measures
the price of being bound to the material, not the value of the graph. The
question "does the graph help answering" can only be asked where the prior is
low. HippoRAG's 2WikiMultihopQA is such a corpus (closed-book 24.8% EM, PHX-1089).

What PHX-1089 measured there was *passages*: retrieval hands the model whole
paragraphs, and Spreading Activation over a cheap spaCy graph chose them. What
it did not measure is the substrate's own consumption format — the
Constellation of entities and typed relations that `mesh ask` renders — on a
corpus the model has not memorised. That is this module.

Two pieces:

- **Replay ingestion.** `scripts/mesh_qa_kadmos.py` already paid for a Kadmos
  reading of every 2Wiki passage and cached it. A provider that answers the
  paragraph prompt from that cache lets the shipped write path build a real
  mesh from 6,119 passages without a single LLM call — the same linker, the
  same identity resolution, the same edges a user's corpus would get.

- **Five arms, one scorer.** `closed_book` (the prior), `passages` (top-k
  passages by cosine — PHX-1089's kNN arm, the bridge to published numbers),
  `vector_only` (top-k mesh entities by cosine, as descriptions),
  `constellation` (the same kind of entities plus the relations among them, the
  shipped rendering) and `constellation_typed` (the same, without the
  structural descriptors that make up 60% of the shipped relation list).
  Scored with SQuAD EM/F1 against the answer key, because the founding scorer
  strips digits and half of 2Wiki's answers are dates.

The comparison that matters is `constellation` against `vector_only`: same
node store, same embedding, and the only difference is whether the edges are
shown. The comparison against `passages` says whether the graph's rendering is
competitive with plain RAG at all, which is a different and harsher question.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from theogony.agents.llm import LLMResult
from theogony.mesh.eval.corpus_answers import _constellation_context, _vector_context
from theogony.mesh.eval.qa_answers import (
    QAAnswerResult,
    _normalise,
    best_over_golds,
    build_context,
)
from theogony.mesh.eval.qa_retrieval import QAPassage, QAQuestion
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.retrieval.defaults import DEFAULT_TOP_K
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

QA_ARMS = ("closed_book", "passages", "vector_only", "constellation", "constellation_typed")
DEFAULT_PASSAGE_K = 5

# ---------------------------------------------------------------------------
# Replay ingestion
# ---------------------------------------------------------------------------


def reading_key(text: str) -> str:
    """The key `scripts/mesh_qa_kadmos.py` stores a reading under: blake2b-128 of
    the passage *text* (not the title-prefixed paragraph Kadmos was shown)."""
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def paragraph_of(passage: QAPassage) -> str:
    """The paragraph Kadmos read: title and text on one line, as the cache was built.

    Stripped, because the reader strips each paragraph it splits out of the
    source text and the replay has to find it again under exactly that string.
    """
    return f"{passage.title}. {passage.text}".strip()


def load_readings(path: Path) -> dict[str, dict[str, Any]]:
    """The readings cache, keyed as written; unparsable lines are skipped."""
    cache: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
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


def readings_by_paragraph(
    passages: Sequence[QAPassage], readings: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Re-key the cache by the paragraph string the reader will send."""
    return {
        paragraph_of(p): readings[reading_key(p.text)]
        for p in passages
        if reading_key(p.text) in readings
    }


_PROMPT_HEAD = "PARAGRAPH:\n"
_PROMPT_TAIL = "\n\nExtract"


class ReplayReadingProvider:
    """An LLM that answers Kadmos's paragraph prompt from stored readings.

    Exact match on the paragraph, not prefix match: `StubLLMProvider` scans every
    key per call, which is fine for a test fixture and quadratic for six thousand
    paragraphs. A paragraph the cache does not hold gets an empty completion,
    which the reader records as a schema failure — visible in the read report
    rather than silently absorbed as a paragraph with no concepts.
    """

    def __init__(
        self,
        by_paragraph: dict[str, dict[str, Any]],
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
        if not prompt.startswith(_PROMPT_HEAD):
            return None
        body = prompt[len(_PROMPT_HEAD) :]
        end = body.rfind(_PROMPT_TAIL)
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
class ReplayIngestReport:
    paragraphs: int
    hits: int
    misses: int
    report: dict[str, Any]


async def ingest_cached_readings(
    runtime: MeshRuntime,
    passages: Sequence[QAPassage],
    readings: dict[str, dict[str, Any]],
    *,
    source_identifier: str = "qa_bench",
    title: str = "QA benchmark corpus",
    max_paragraphs: int = 0,
    on_call: Callable[[int], None] | None = None,
) -> ReplayIngestReport:
    """Write a corpus into a mesh through the shipped reader, readings replayed.

    One `read_text` call over the whole corpus, paragraphs separated by blank
    lines, so the corpus is one source anchor with one paragraph anchor per
    passage — the shape a book gets. The passages are joined the way the cache
    was keyed (`paragraph_of`), and none of the HippoRAG passages contains a
    blank line, so the reader's split recovers them exactly.
    """
    by_paragraph = readings_by_paragraph(passages, readings)
    provider = ReplayReadingProvider(by_paragraph, on_call=on_call)
    reader = MeshParagraphReader(runtime, llm=provider, max_paragraphs=max_paragraphs)
    text = "\n\n".join(paragraph_of(p) for p in passages)
    report = await reader.read_text(
        text=text,
        source_type="qa_bench",
        source_identifier=source_identifier,
        title=title,
        anchor=source_identifier,
    )
    return ReplayIngestReport(
        paragraphs=len(passages) if not max_paragraphs else min(len(passages), max_paragraphs),
        hits=provider.hits,
        misses=len(provider.misses),
        report=report,
    )


# ---------------------------------------------------------------------------
# The four arms
# ---------------------------------------------------------------------------

# The wording is PHX-1089's, so the closed-book arm here and there are the same
# measurement; only "passages" becomes "material", since two of the arms hand
# the model entities rather than paragraphs.
_ASK = (
    "Reply with the shortest span that answers it — a name, a date, a phrase — "
    "and nothing else. No sentence, no explanation."
)
_SYSTEM_MATERIAL = f"Answer the question using ONLY the material given. {_ASK}"
_SYSTEM_CLOSED = f"Answer the question from your own knowledge. {_ASK}"


def unit_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0.0, 1.0, norms)


def nearest_passages(passage_vectors: np.ndarray, query: Sequence[float], k: int) -> list[int]:
    """Top-k passages by cosine; `passage_vectors` must be row-normalised."""
    q = np.asarray(query, dtype=np.float32)
    norm = float(np.linalg.norm(q))
    if norm > 0.0:
        q = q / norm
    scores = passage_vectors @ q
    k = max(0, min(k, len(scores)))
    if k == 0:
        return []
    top = np.argpartition(-scores, k - 1)[:k]
    return [int(i) for i in top[np.argsort(-scores[top])]]


def _contains_any(context: str, golds: Sequence[str]) -> bool:
    haystack = f" {_normalise(context)} "
    return any(f" {_normalise(g)} " in haystack for g in golds if g)


@dataclass
class QAJob:
    result: QAAnswerResult
    system: str
    prompt: str
    golds: list[str]


def build_qa_jobs(
    runtime: MeshRuntime,
    embed: Callable[[str], Sequence[float]],
    questions: Sequence[QAQuestion],
    passages: Sequence[QAPassage],
    passage_vectors: np.ndarray | None,
    *,
    arms: Sequence[str] = QA_ARMS,
    top_k: int = DEFAULT_TOP_K,
    passage_k: int = DEFAULT_PASSAGE_K,
    **retrieve_kwargs: Any,
) -> list[QAJob]:
    """Every (question, arm) prompt, contexts built once.

    `gold_in_context` is filled here, on the exact text the model will read, as
    a token-boundary match on the SQuAD-normalised strings — the ceiling each
    arm worked against, which is what separates a reading problem from a
    retrieval problem (PHX-1089).
    """
    jobs: list[QAJob] = []
    for q in questions:
        vector = list(embed(q.question))
        golds = q.acceptable
        for arm in arms:
            if arm == "closed_book":
                context = ""
                system, prompt = _SYSTEM_CLOSED, f"Question: {q.question}"
            else:
                if arm == "passages":
                    if passage_vectors is None:
                        raise ValueError("the passages arm needs passage vectors")
                    hits = nearest_passages(passage_vectors, vector, passage_k)
                    context = build_context(list(passages), hits, top_k=passage_k)
                elif arm == "vector_only":
                    context = _vector_context(runtime, vector, top_k)
                elif arm in ("constellation", "constellation_typed"):
                    # `constellation_typed` is the same retrieval rendered without
                    # the structural descriptors — the shipped list is 60% of
                    # those, and whether they cost the reader anything is a
                    # question this run can answer for free.
                    context = _constellation_context(
                        runtime,
                        q.question,
                        vector,
                        top_k,
                        typed_only=arm == "constellation_typed",
                        **retrieve_kwargs,
                    )
                else:
                    raise ValueError(f"unknown arm {arm!r}")
                system = _SYSTEM_MATERIAL
                prompt = f"Material:\n{context}\n\nQuestion: {q.question}"
            jobs.append(
                QAJob(
                    result=QAAnswerResult(
                        qid=q.qid,
                        arm=arm,
                        question=q.question,
                        gold=q.answer,
                        answer="",
                        gold_in_context=bool(context) and _contains_any(context, golds),
                    ),
                    system=system,
                    prompt=prompt,
                    golds=list(golds),
                )
            )
    return jobs


async def _ask(
    llm: Any, system: str, prompt: str, semaphore: asyncio.Semaphore, max_output_tokens: int
) -> str:
    async with semaphore:
        for attempt in range(3):
            try:
                raw = await llm.complete(
                    prompt, system=system, max_output_tokens=max_output_tokens, temperature=0.0
                )
                return (getattr(raw, "text", None) or str(raw)).strip()
            except Exception:  # noqa: BLE001 - a transient provider error is not a result
                if attempt == 2:
                    return ""
                await asyncio.sleep(2.0 * (attempt + 1))
        return ""


async def answer_qa_set(
    runtime: MeshRuntime,
    embed: Callable[[str], Sequence[float]],
    llm: Any,
    questions: Sequence[QAQuestion],
    passages: Sequence[QAPassage],
    passage_vectors: np.ndarray | None,
    *,
    arms: Sequence[str] = QA_ARMS,
    top_k: int = DEFAULT_TOP_K,
    passage_k: int = DEFAULT_PASSAGE_K,
    concurrency: int = 8,
    max_output_tokens: int = 48,
    **retrieve_kwargs: Any,
) -> list[QAAnswerResult]:
    """Ask every question once per arm, concurrently, and score EM / F1.

    Retrieval never records a firing: a benchmark must not change the substrate
    it measures (PHX-1101). `retrieve_kwargs` reach the constellation arm only.
    """
    runtime.rebuild_csr()
    jobs = build_qa_jobs(
        runtime,
        embed,
        questions,
        passages,
        passage_vectors,
        arms=arms,
        top_k=top_k,
        passage_k=passage_k,
        **retrieve_kwargs,
    )
    semaphore = asyncio.Semaphore(max(1, concurrency))
    answers = await asyncio.gather(
        *(_ask(llm, j.system, j.prompt, semaphore, max_output_tokens) for j in jobs)
    )
    for job, answer in zip(jobs, answers, strict=True):
        job.result.answer = answer
        job.result.em, job.result.f1 = best_over_golds(answer, job.golds)
    return [j.result for j in jobs]


def sign_test_p(better: int, worse: int) -> float:
    """Exact two-sided sign test on the discordant pairs (McNemar without the
    normal approximation), which is the right test when both arms answered
    the same questions."""
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    tail = float(sum(math.comb(n, i) for i in range(k + 1))) / float(2**n)
    return float(min(1.0, 2.0 * tail))


def paired_qa(
    results: Sequence[QAAnswerResult], *, arm: str, baseline: str = "closed_book"
) -> dict[str, float]:
    """Question for question: how often `arm` beats `baseline` on EM and on F1.

    Totals move with the model's mood; the pairing does not. `p_em` is the sign
    test on the EM-discordant questions — the statistic PHX-1089 reported.
    """
    by: dict[tuple[str, str], QAAnswerResult] = {(r.qid, r.arm): r for r in results}
    qids = sorted({r.qid for r in results})
    em_better = em_worse = f1_better = f1_worse = paired = 0
    for qid in qids:
        a, b = by.get((qid, arm)), by.get((qid, baseline))
        if a is None or b is None:
            continue
        paired += 1
        em_better += a.em > b.em
        em_worse += a.em < b.em
        f1_better += a.f1 > b.f1 + 1e-9
        f1_worse += a.f1 < b.f1 - 1e-9
    return {
        "questions": float(paired),
        "em_better": float(em_better),
        "em_worse": float(em_worse),
        "em_equal": float(paired - em_better - em_worse),
        "p_em": sign_test_p(em_better, em_worse),
        "f1_better": float(f1_better),
        "f1_worse": float(f1_worse),
        "f1_equal": float(paired - f1_better - f1_worse),
        "p_f1": sign_test_p(f1_better, f1_worse),
    }
