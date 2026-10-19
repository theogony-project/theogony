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
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from theogony.mesh.eval.corpus_answers import _vector_context
from theogony.mesh.eval.qa_answers import (
    QAAnswerResult,
    _normalise,
    best_over_golds,
    build_context,
)
from theogony.mesh.eval.qa_retrieval import QAPassage, QAQuestion
from theogony.mesh.ingestion.replay import (
    ReplayReadingProvider,
    ReplayReport,
    load_readings,
    reading_key,
    replay_text,
)
from theogony.mesh.retrieval.constellation import render_constellation
from theogony.mesh.retrieval.defaults import DEFAULT_TOP_K
from theogony.mesh.retrieval.retrieve import RetrievalResult, retrieve
from theogony.mesh.runtime.contradiction import MENTION_CONTEXTS
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

QA_ARMS = ("closed_book", "passages", "vector_only", "constellation", "constellation_typed")
# The two repairs PHX-1110 asked for, as arms beside the measured five (PHX-1113,
# PHX-1114): a prompt that lets a yes/no question be answered yes or no, and the
# source paragraphs of the seed-touching entities laid beside the typed
# Constellation. `_yn` suffixes the prompt variant onto an arm.
EXTRA_ARMS = ("constellation_typed_yn", "constellation_sources", "constellation_sources_yn")
ALL_ARMS = QA_ARMS + EXTRA_ARMS
DEFAULT_PASSAGE_K = 5

# ---------------------------------------------------------------------------
# Replay ingestion — the provider and the key live in `mesh.ingestion.replay`
# since PHX-1112 made the replay a shipped path; re-exported here because the
# scripts and tests of PHX-1110 import them from this module.
# ---------------------------------------------------------------------------


def paragraph_of(passage: QAPassage) -> str:
    """The paragraph Kadmos read: title and text on one line, as the cache was built.

    Stripped, because the reader strips each paragraph it splits out of the
    source text and the replay has to find it again under exactly that string.
    """
    return f"{passage.title}. {passage.text}".strip()


def readings_by_paragraph(
    passages: Sequence[QAPassage], readings: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Re-key the cache by the paragraph string the reader will send."""
    return {
        paragraph_of(p): readings[reading_key(p.text)]
        for p in passages
        if reading_key(p.text) in readings
    }


# The name PHX-1110's scripts and tests know the report by.
ReplayIngestReport = ReplayReport


async def ingest_cached_readings(
    runtime: MeshRuntime,
    passages: Sequence[QAPassage],
    readings: dict[str, dict[str, Any]],
    *,
    source_identifier: str = "qa_bench",
    title: str = "QA benchmark corpus",
    max_paragraphs: int = 0,
    compact_every: int = 200,
    on_call: Callable[[int], None] | None = None,
) -> ReplayIngestReport:
    """Write a corpus into a mesh through the shipped reader, readings replayed.

    One `read_text` call over the whole corpus, paragraphs separated by blank
    lines, so the corpus is one source anchor with one paragraph anchor per
    passage — the shape a book gets. The passages are joined the way the cache
    was keyed (`paragraph_of`), and none of the HippoRAG passages contains a
    blank line, so the reader's split recovers them exactly.
    """
    text = "\n\n".join(paragraph_of(p) for p in passages)
    # The replay keys by the paragraph string; the cache was keyed by the
    # passage text. Re-key once so `replay_text` finds every passage.
    by_text = {
        reading_key(paragraph_of(p)): readings[reading_key(p.text)]
        for p in passages
        if reading_key(p.text) in readings
    }
    result = await replay_text(
        runtime,
        text,
        by_text,
        source_type="qa_bench",
        source_identifier=source_identifier,
        title=title,
        anchor=source_identifier,
        max_paragraphs=max_paragraphs,
        compact_every=compact_every,
        on_call=on_call,
    )
    return ReplayIngestReport(
        paragraphs=len(passages) if not max_paragraphs else min(len(passages), max_paragraphs),
        hits=result.hits,
        misses=result.misses,
        report=result.report,
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
# PHX-1113: a list of entities tempted the model into an entity where the
# question asked whether something is the case — "Iran" for "are both villages
# in the same country?" — on 30 of 110 yes/no questions. One sentence names the
# question form and the two answers it takes; nothing else changes.
_YES_NO = (
    "If the question is a yes/no question — it begins with Are, Is, Do, Does, Did, "
    "Was, Were or Has — answer yes or no."
)
_SYSTEM_MATERIAL_YN = f"{_SYSTEM_MATERIAL} {_YES_NO}"


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


# ---------------------------------------------------------------------------
# The source paragraphs behind a Constellation (PHX-1114)
# ---------------------------------------------------------------------------

_PARAGRAPH_REF = re.compile(r"#p(\d+)$")


@dataclass
class SourceIndex:
    """From an entity to the passages whose paragraphs mention it.

    The mesh holds no paragraph text, only a reference on each chunk
    (`raw_text_ref`, ``<source>#p<N>`` with N counted from one, as the reader
    numbers paragraphs) and a witness edge from the chunk to every entity the
    reader found in it — the two creation contexts the substrate itself counts
    as a mention (`MENTION_CONTEXTS`). The benchmark holds the passage texts,
    so the two together put the paragraph an entity was read from back beside
    it.
    """

    entity_chunks: dict[str, list[str]]
    chunk_passage: dict[str, int]
    chunk_entities: dict[str, set[str]]

    @classmethod
    def from_runtime(cls, runtime: MeshRuntime) -> SourceIndex:
        chunk_passage: dict[str, int] = {}
        for chunk in runtime.nodes.iter_chunks(page_size=1024):
            match = _PARAGRAPH_REF.search(str(chunk.raw_text_ref or ""))
            if match:
                chunk_passage[str(chunk.id)] = int(match.group(1)) - 1
        entity_chunks: dict[str, list[str]] = {}
        chunk_entities: dict[str, set[str]] = {}
        # One scan of the edge table, once per run — 650k edges in about ten
        # seconds on the 2Wiki mesh; a per-question read would be the
        # one-transaction-per-item defect this substrate keeps having.
        for edge in runtime.edges.load_all_edges():
            if edge.creation_context not in MENTION_CONTEXTS:
                continue
            source, target = str(edge.source_id), str(edge.target_id)
            if source in chunk_passage:
                entity_chunks.setdefault(target, []).append(source)
                chunk_entities.setdefault(source, set()).add(target)
        if not entity_chunks:
            # Silently the sources arm would then be the typed arm under another name.
            raise ValueError(
                "SourceIndex is empty: no chunk with a '<source>#p<N>' raw_text_ref is "
                "reached by a mention edge; this mesh was not read by the shipped reader "
                "from a passage list"
            )
        return cls(
            entity_chunks=entity_chunks, chunk_passage=chunk_passage, chunk_entities=chunk_entities
        )

    def check_passages(self, passages: Sequence[QAPassage]) -> None:
        """The passage list must be the one the mesh was read from."""
        highest = max(self.chunk_passage.values())
        if highest >= len(passages):
            raise ValueError(
                f"the mesh refers to paragraph #{highest + 1} but the passage list holds "
                f"{len(passages)}; these are not the same corpus"
            )

    def passages_for(self, entity_ids: Sequence[str], *, limit: int) -> list[int]:
        """Up to ``limit`` passages for the entities, the ones that join them first.

        A paragraph that mentions several of the entities is where their
        relation was read from — the second hop of a comparison question, where
        PHX-1114's dates stand — so candidates are ranked by how many of the
        listed entities they mention, then by the position of the first entity
        that brought them, then in the order the reader appended them. Without
        the ranking a seed read from ``limit`` or more paragraphs fills the
        budget alone with its first paragraphs in corpus order, and no
        neighbour's paragraph is reached (found by review before this shipped).
        """
        listed = {e: pos for pos, e in enumerate(entity_ids)}
        first_seen: dict[str, tuple[int, int]] = {}
        order = 0
        for pos, entity_id in enumerate(entity_ids):
            for chunk_id in self.entity_chunks.get(entity_id, ()):
                if chunk_id not in first_seen:
                    first_seen[chunk_id] = (pos, order)
                    order += 1
        ranked = sorted(
            first_seen,
            key=lambda c: (
                -len(self.chunk_entities.get(c, set()) & listed.keys()),
                first_seen[c],
            ),
        )
        seen: set[int] = set()
        out: list[int] = []
        for chunk_id in ranked:
            index = self.chunk_passage.get(chunk_id)
            if index is None or index in seen:
                continue
            seen.add(index)
            out.append(index)
            if len(out) >= limit:
                break
        return out


def seed_touching_entities(constellation: Any) -> list[str]:
    """The seeds in the order retrieval ranked them, then the other endpoints
    of the edges that touch a seed, in the Constellation's edge order.

    Wider than the relations `render_constellation(typed_only=True)` shows:
    every seed-touching edge counts, structural descriptors included, so a
    neighbour reached only over `co_mentions_in_paragraph` or a source anchor
    can appear here. Ids without chunks contribute no passage.
    """
    seeds = list(constellation.seed_node_ids)
    seed_set = set(seeds)
    ordered = list(seeds)
    for edge in constellation.edges:
        if edge.source_id not in seed_set and edge.target_id not in seed_set:
            continue
        for node_id in (edge.source_id, edge.target_id):
            if node_id not in seed_set and node_id not in ordered:
                ordered.append(node_id)
    return ordered


def sources_text(
    constellation: Any,
    passages: Sequence[QAPassage],
    index: SourceIndex,
    passage_k: int,
) -> tuple[str, int]:
    """The typed Constellation, then the paragraphs its seed-touching entities
    were read from; returns the text and how many paragraphs it attached."""
    text = render_constellation(constellation, typed_only=True)
    hits = index.passages_for(seed_touching_entities(constellation), limit=passage_k)
    if hits:
        text += "\n\nSource passages:\n" + build_context(list(passages), hits, top_k=passage_k)
    return text, len(hits)


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
    source_index: SourceIndex | None = None,
    **retrieve_kwargs: Any,
) -> list[QAJob]:
    """Every (question, arm) prompt, contexts built once.

    `gold_in_context` is filled here, on the exact text the model will read, as
    a token-boundary match on the SQuAD-normalised strings — the ceiling each
    arm worked against, which is what separates a reading problem from a
    retrieval problem (PHX-1089).

    An arm ending in ``_yn`` is its base arm with the yes/no sentence appended
    to the system prompt and nothing else changed (PHX-1113).
    """
    unknown = [a for a in arms if a not in ALL_ARMS]
    if unknown:
        raise ValueError(f"unknown arm(s) {unknown!r}; choose from {ALL_ARMS}")
    if any(a.startswith("constellation_sources") for a in arms):
        if source_index is None:
            raise ValueError("the sources arms need a SourceIndex (SourceIndex.from_runtime)")
        source_index.check_passages(passages)
    jobs: list[QAJob] = []
    for q in questions:
        vector = list(embed(q.question))
        golds = q.acceptable
        # One retrieval per question for the whole constellation family: the
        # arms differ in how the Constellation is rendered and asked about, not
        # in what was retrieved, and sharing the object says so (contract 7).
        retrieved: RetrievalResult | None = None

        def once(question: str = q.question, vec: list[float] = vector) -> RetrievalResult:
            nonlocal retrieved
            if retrieved is None:
                retrieved = retrieve(
                    runtime,
                    vec,
                    query=question,
                    top_k=top_k,
                    record_firing=False,
                    **retrieve_kwargs,
                )
            return retrieved

        for arm in arms:
            attached: int | None = None
            yes_no = arm.endswith("_yn")
            base = arm.removesuffix("_yn")
            if base == "closed_book":
                context = ""
                system, prompt = _SYSTEM_CLOSED, f"Question: {q.question}"
            else:
                if base == "passages":
                    if passage_vectors is None:
                        raise ValueError("the passages arm needs passage vectors")
                    hits = nearest_passages(passage_vectors, vector, passage_k)
                    context = build_context(list(passages), hits, top_k=passage_k)
                elif base == "vector_only":
                    context = _vector_context(runtime, vector, top_k)
                elif base in ("constellation", "constellation_typed"):
                    # `constellation_typed` is the same retrieval rendered without
                    # the structural descriptors — the shipped list is 60% of
                    # those, and whether they cost the reader anything is a
                    # question this run can answer for free.
                    context = render_constellation(
                        once().constellation, typed_only=base == "constellation_typed"
                    )
                elif base == "constellation_sources":
                    assert source_index is not None  # checked above
                    context, attached = sources_text(
                        once().constellation, passages, source_index, passage_k
                    )
                else:  # pragma: no cover - ALL_ARMS is checked above
                    raise ValueError(f"unknown arm {arm!r}")
                system = _SYSTEM_MATERIAL_YN if yes_no else _SYSTEM_MATERIAL
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
                        attached_passages=attached,
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
    source_index: SourceIndex | None = None,
    **retrieve_kwargs: Any,
) -> list[QAAnswerResult]:
    """Ask every question once per arm, concurrently, and score EM / F1.

    Retrieval never records a firing: a benchmark must not change the substrate
    it measures (PHX-1101). `retrieve_kwargs` reach the constellation arms only.
    """
    runtime.rebuild_csr()
    if source_index is None and any(a.startswith("constellation_sources") for a in arms):
        source_index = SourceIndex.from_runtime(runtime)
    jobs = build_qa_jobs(
        runtime,
        embed,
        questions,
        passages,
        passage_vectors,
        arms=arms,
        top_k=top_k,
        passage_k=passage_k,
        source_index=source_index,
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


_YEAR = re.compile(r"\b\d{3,4}\b")


def answer_kind(gold: str) -> str:
    """`yes_no`, `date` or `entity` — by the shape of the gold answer.

    The three behave differently enough under a graph context that one total
    hides all of it (PHX-1110): on 2WikiMultihopQA the typed Constellation beat
    five passages by 5.6 points on entity answers, fell 20 points *below the
    model's unaided prior* on yes/no questions, and carried almost none of the
    dates. A year anywhere in the gold string counts as a date.
    """
    text = gold.strip().lower()
    if text in ("yes", "no"):
        return "yes_no"
    return "date" if _YEAR.search(text) else "entity"


def summarise_by_kind(results: Sequence[QAAnswerResult]) -> dict[str, dict[str, dict[str, float]]]:
    """Per answer kind and arm: questions, exact match, F1, and the ceiling.

    ``{kind: {arm: {"questions", "exact_match", "f1", "gold_in_context"}}}`` —
    the ceiling (how often the answer stood in the material) beside the score,
    because PHX-1114 asks whether an arm fails to find or fails to read.
    """
    table: dict[str, dict[str, list[QAAnswerResult]]] = {}
    for r in results:
        table.setdefault(answer_kind(r.gold), {}).setdefault(r.arm, []).append(r)
    return {
        kind: {
            arm: {
                "questions": float(len(rows)),
                "exact_match": sum(r.em for r in rows) / len(rows),
                "f1": sum(r.f1 for r in rows) / len(rows),
                "gold_in_context": sum(1.0 for r in rows if r.gold_in_context) / len(rows),
            }
            for arm, rows in arms.items()
        }
        for kind, arms in table.items()
    }


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


def paired_by_kind(
    results: Sequence[QAAnswerResult], *, arm: str, baseline: str
) -> dict[str, dict[str, float]]:
    """`paired_qa` on each answer kind, and on everything that is not yes/no.

    PHX-1113's finish line is two numbers from one run: the variant on the
    yes/no questions, and what it costs on the other 890 — so the pairing has
    to be read by kind, not only overall.
    """
    out: dict[str, dict[str, float]] = {}
    for kind in ("entity", "yes_no", "date"):
        subset = [r for r in results if answer_kind(r.gold) == kind]
        if subset:
            out[kind] = paired_qa(subset, arm=arm, baseline=baseline)
    rest = [r for r in results if answer_kind(r.gold) != "yes_no"]
    if rest:
        out["not_yes_no"] = paired_qa(rest, arm=arm, baseline=baseline)
    return out


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


__all__ = [
    "ALL_ARMS",
    "DEFAULT_PASSAGE_K",
    "EXTRA_ARMS",
    "QA_ARMS",
    "QAJob",
    "SourceIndex",
    "ReplayIngestReport",
    "ReplayReadingProvider",
    "answer_kind",
    "answer_qa_set",
    "build_qa_jobs",
    "ingest_cached_readings",
    "load_readings",
    "nearest_passages",
    "paired_by_kind",
    "paired_qa",
    "paragraph_of",
    "reading_key",
    "readings_by_paragraph",
    "seed_touching_entities",
    "sign_test_p",
    "sources_text",
    "summarise_by_kind",
    "unit_rows",
]
