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
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from theogony.mesh.eval.corpus_answers import _vector_context
from theogony.mesh.eval.qa_answers import (
    QAAnswerResult,
    _normalise,
    answered_by,
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
# The comparisons a run is read by, (arm, baseline): what the edges add, what
# the rendering is worth against plain retrieval and against the prior, and the
# two repairs. Here and not in the script, so that a finished run is re-read
# through the same pairs it was written with (PHX-1127).
QA_PAIRS: tuple[tuple[str, str], ...] = (
    ("constellation", "vector_only"),
    ("constellation", "passages"),
    ("constellation", "closed_book"),
    ("constellation_typed", "constellation"),
    ("constellation_typed", "vector_only"),
    ("constellation_typed", "passages"),
    ("constellation_typed", "closed_book"),
    ("vector_only", "closed_book"),
    ("passages", "closed_book"),
    # PHX-1113 / PHX-1114
    ("constellation_typed_yn", "constellation_typed"),
    ("constellation_sources", "constellation_typed"),
    ("constellation_sources", "passages"),
    ("constellation_sources_yn", "constellation_typed"),
    ("constellation_sources_yn", "constellation_sources"),
    ("constellation_sources_yn", "passages"),
)

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
    accrue_descriptions: bool = False,
    accrue_unnamed: bool = False,
    revise_identity_vector: bool = True,
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
        accrue_descriptions=accrue_descriptions,
        accrue_unnamed=accrue_unnamed,
        revise_identity_vector=revise_identity_vector,
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
                        question_type=q.question_type,
                    ),
                    system=system,
                    prompt=prompt,
                    golds=list(golds),
                )
            )
    return jobs


async def _ask(
    llm: Any, system: str, prompt: str, semaphore: asyncio.Semaphore, max_output_tokens: int
) -> tuple[str, str | None]:
    async with semaphore:
        for attempt in range(3):
            try:
                raw = await llm.complete(
                    prompt, system=system, max_output_tokens=max_output_tokens, temperature=0.0
                )
                return (getattr(raw, "text", None) or str(raw)).strip(), answered_by(raw, llm)
            except Exception:  # noqa: BLE001 - a transient provider error is not a result
                if attempt == 2:
                    return "", None
                await asyncio.sleep(2.0 * (attempt + 1))
        return "", None


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
    for job, (answer, model) in zip(jobs, answers, strict=True):
        job.result.answer, job.result.model = answer, model
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
    table = _rows_by_group(results, lambda r: (answer_kind(r.gold),))
    return {kind: {arm: _stats(rows) for arm, rows in arms.items()} for kind, arms in table.items()}


def _rows_by_group(
    results: Sequence[QAAnswerResult], groups_of: Callable[[QAAnswerResult], Sequence[str]]
) -> dict[str, dict[str, list[QAAnswerResult]]]:
    table: dict[str, dict[str, list[QAAnswerResult]]] = {}
    for r in results:
        for group in groups_of(r):
            table.setdefault(group, {}).setdefault(r.arm, []).append(r)
    return table


def _stats(rows: Sequence[QAAnswerResult]) -> dict[str, float]:
    return {
        "questions": float(len(rows)),
        "exact_match": sum(r.em for r in rows) / len(rows),
        "f1": sum(r.f1 for r in rows) / len(rows),
        "gold_in_context": sum(1.0 for r in rows if r.gold_in_context) / len(rows),
    }


def _type_groups(
    results: Sequence[QAAnswerResult], pooled: Mapping[str, Collection[str]] | None
) -> dict[str, tuple[str, ...]]:
    """Group name -> the question types it holds: every type on its own, most
    questions first, then the pools.

    A pool named like a type would put two sets of questions under one row and
    report neither, so it is refused — against the types the pools name as well
    as the ones these results hold, so that a slice of a run which happens to
    lack the type does not pass what the whole run would refuse.
    """
    counts: dict[str, set[str]] = {}
    for r in results:
        if r.question_type:
            counts.setdefault(r.question_type, set()).add(r.qid)
    types = sorted(counts, key=lambda t: (-len(counts[t]), t))
    groups: dict[str, tuple[str, ...]] = {t: (t,) for t in types}
    pools = dict(pooled or {})
    named = set(types) | {t for members in pools.values() for t in members}
    for name, members in pools.items():
        if name in named:
            raise ValueError(f"the pool {name!r} bears the name of a question type")
        held = tuple(t for t in types if t in members)
        if held:
            groups[name] = held
    return groups


def summarise_by_type(
    results: Sequence[QAAnswerResult], *, pooled: Mapping[str, Collection[str]] | None = None
) -> dict[str, dict[str, dict[str, float]]]:
    """`summarise_by_kind`, by the dataset's question type instead of the gold's shape.

    The kind says what the answer looks like; the type says what the question
    asks for. On 2WikiMultihopQA the edges of the mesh were worth eleven points
    where the question does not name its answer and cost ten on plain
    comparisons, and the one total, +3.6, said neither (PHX-1127).
    `pooled` adds rows that hold several types (`qa_datasets.POOLED_TYPES`).
    Results without a type are left out; a run with none returns ``{}``.

    One figure more than by kind: `exact_match_where_found`, the exact match on
    the questions whose answer stood in the material. It is left out where the
    answer stood in none — the prior's arm has no material — because an arm
    that found nothing has no rate at which it read, and a zero would say it
    had one. The rate is over each arm's own found questions, so two arms'
    rates are not over the same questions; `paired_by_found` compares them
    where both found the answer.
    """
    groups = _type_groups(results, pooled)
    table = _rows_by_group(
        results,
        lambda r: [name for name, held in groups.items() if r.question_type in held],
    )
    return {
        name: {arm: _stats_where_found(rows) for arm, rows in table[name].items()}
        for name in groups
    }


def _stats_where_found(rows: Sequence[QAAnswerResult]) -> dict[str, float]:
    stats = _stats(rows)
    found = [r for r in rows if r.gold_in_context]
    if found:
        stats["exact_match_where_found"] = sum(r.em for r in found) / len(found)
    return stats


#: The three tables a run is printed in by question type: the score, how often
#: the answer was found, and how much of the found was read out.
BY_TYPE_TABLES: tuple[tuple[str, str], ...] = (
    ("exact_match", "exact match by question type"),
    ("gold_in_context", "answer in the material, by question type"),
    ("exact_match_where_found", "exact match where the answer was in the material"),
)


def by_type_lines(
    by_type: Mapping[str, Mapping[str, Mapping[str, float]]],
    arms: Sequence[str],
    *,
    metric: str = "exact_match",
) -> list[str]:
    """`summarise_by_type` as text: one row per arm, one column per type or pool.

    Arms as rows: four of the eight share their first fourteen letters, and a
    column header cut to fit no longer told them apart. A dash where an arm has
    no such figure — no rows in the group, or nothing found to be read out.
    """
    names = list(by_type)
    width = max((len(a) for a in (*arms, "questions")), default=0) + 2
    # the most any arm answered: one arm short of rows must not shrink the count
    counts = [max(int(stats["questions"]) for stats in by_type[name].values()) for name in names]

    def cell(name: str, arm: str) -> str:
        value = by_type[name].get(arm, {}).get(metric)
        return f"{'-':>17s}" if value is None else f"{value:>17.1%}"

    return [
        " " * width + " ".join(f"{name:>17s}" for name in names),
        f"{'questions':<{width}}" + " ".join(f"{n:>17d}" for n in counts),
        *(f"{arm:<{width}}" + " ".join(cell(name, arm) for name in names) for arm in arms),
    ]


def paired_by_type(
    results: Sequence[QAAnswerResult],
    *,
    arm: str,
    baseline: str,
    pooled: Mapping[str, Collection[str]] | None = None,
) -> dict[str, dict[str, float]]:
    """`paired_qa` on each question type, then on each pool of them."""
    out: dict[str, dict[str, float]] = {}
    for name, held in _type_groups(results, pooled).items():
        subset = [r for r in results if r.question_type in held]
        pair = paired_qa(subset, arm=arm, baseline=baseline)
        if pair["questions"]:
            out[name] = pair
    return out


_FOUND_CELLS = ("both", "arm_only", "baseline_only", "neither")


def paired_by_found(
    results: Sequence[QAAnswerResult], *, arm: str, baseline: str
) -> dict[str, dict[str, float]]:
    """`paired_qa`, split by which of the two arms had the answer in its material.

    Two arms' reading rates are each over the questions that arm found, which
    are not the same questions; where both found the answer they can be
    compared. On 2Wiki's questions that do not name their answer the typed
    Constellation and five passages are even there (17 better, 19 worse), and
    the Constellation's lead is the 178 questions only it found against the 65
    only the passages did (PHX-1127). `neither` is where both materials lack
    the answer: what an arm scores there it has from the model's own
    knowledge, or has lost of it.
    """
    by = {(r.qid, r.arm): r for r in results}
    cells: dict[str, list[QAAnswerResult]] = {}
    for qid in sorted({r.qid for r in results}):
        a, b = by.get((qid, arm)), by.get((qid, baseline))
        if a is None or b is None:
            continue
        if a.gold_in_context:
            cell = "both" if b.gold_in_context else "arm_only"
        else:
            cell = "baseline_only" if b.gold_in_context else "neither"
        cells.setdefault(cell, []).extend((a, b))
    return {
        cell: paired_qa(cells[cell], arm=arm, baseline=baseline)
        for cell in _FOUND_CELLS
        if cell in cells
    }


def by_type_report(
    results: Sequence[QAAnswerResult],
    *,
    pooled: Mapping[str, Collection[str]] | None = None,
    pairs: Sequence[tuple[str, str]] = QA_PAIRS,
) -> dict[str, Any]:
    """A run read by question type: what the harness writes with a run, and what
    `scripts/mesh_qa_by_type.py` reads out of a finished one.

    `by_type` is `summarise_by_type`. `paired_by_type` is `paired_by_type` for
    every pair both of whose arms ran. `paired_in_pool` reads each pool once
    more, by which arm found the answer (`paired_by_found`) and by the shape
    of the gold (`paired_by_kind`): a pool is itself a total, and the first
    one drawn here hid that the lead on its entity answers reverses on its 52
    dates. Empty tables for a run without question types.
    """
    arms = {r.arm for r in results}
    pools = {
        name: held for name, held in _type_groups(results, pooled).items() if name in (pooled or {})
    }
    paired: dict[str, dict[str, dict[str, float]]] = {}
    in_pool: dict[str, dict[str, dict[str, dict[str, dict[str, float]]]]] = {}
    for arm, base in pairs:
        if arm not in arms or base not in arms:
            continue
        by_type = paired_by_type(results, arm=arm, baseline=base, pooled=pooled)
        if not by_type:
            continue
        key = f"{arm}_vs_{base}"
        paired[key] = by_type
        in_pool[key] = {}
        for name, held in pools.items():
            subset = [r for r in results if r.question_type in held]
            in_pool[key][name] = {
                "by_found": paired_by_found(subset, arm=arm, baseline=base),
                "by_kind": paired_by_kind(subset, arm=arm, baseline=base),
            }
    return {
        "by_type": summarise_by_type(results, pooled=pooled),
        "paired_by_type": paired,
        "paired_in_pool": in_pool,
    }


def pair_by_type_lines(
    by_type: Mapping[str, Mapping[str, float]],
    in_pool: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
) -> list[str]:
    """One pair of `by_type_report` as text: the types and pools, then each
    pool by where the answer stood and by the shape of the gold. Exact match,
    better / worse."""

    def cells(table: Mapping[str, Mapping[str, float]], *, p: bool) -> str:
        return " · ".join(
            f"{name} {t['em_better']:.0f}/{t['em_worse']:.0f}"
            + (f" (p={t['p_em']:.2g})" if p else "")
            for name, t in table.items()
        )

    lines = [f"    by type: {cells(by_type, p=True)}"]
    for pool, splits in in_pool.items():
        lines.append(f"    {pool}, by where the answer stood: {cells(splits['by_found'], p=False)}")
        lines.append(f"    {pool}, by answer kind: {cells(splits['by_kind'], p=False)}")
    return lines


def results_from_run(
    run: Mapping[str, Any],
    *,
    question_types: Mapping[str, str] | None = None,
    arm_suffix: str = "",
) -> list[QAAnswerResult]:
    """The answer rows of a run file of `scripts/mesh_qa_constellation.py`, as results.

    A row's own `question_type` is used where it has one; a run written before
    PHX-1127 has none and takes it from `question_types` (question id -> type,
    `qa_datasets.question_types`). `arm_suffix` tells the arms of two runs apart
    when they are paired question for question. Question ids are read as
    strings, as the dataset loader keys them, whatever the file holds.
    """
    types = question_types or {}
    return [
        QAAnswerResult(
            qid=str(a["qid"]),
            arm=f"{a['arm']}{arm_suffix}",
            question=a["question"],
            gold=a["gold"],
            answer=a["answer"],
            em=a["em"],
            f1=a["f1"],
            gold_in_context=a["gold_in_context"],
            attached_passages=a.get("attached_passages"),
            model=a.get("model"),
            question_type=a.get("question_type") or types.get(str(a["qid"])),
        )
        for a in run["answers"]
    ]


def sign_test_p(better: int, worse: int) -> float:
    """Exact two-sided sign test on the discordant pairs (McNemar without the
    normal approximation), which is the right test when both arms answered
    the same questions."""
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    # Integer over integer: Python divides big ints exactly and rounds once, where
    # float(2**n) overflows past n = 1,023 (a mention audit of 2,000 moves did).
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
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
    "BY_TYPE_TABLES",
    "DEFAULT_PASSAGE_K",
    "EXTRA_ARMS",
    "QA_ARMS",
    "QA_PAIRS",
    "QAJob",
    "SourceIndex",
    "ReplayIngestReport",
    "ReplayReadingProvider",
    "answer_kind",
    "answer_qa_set",
    "build_qa_jobs",
    "by_type_lines",
    "by_type_report",
    "ingest_cached_readings",
    "load_readings",
    "nearest_passages",
    "pair_by_type_lines",
    "paired_by_found",
    "paired_by_kind",
    "paired_by_type",
    "paired_qa",
    "paragraph_of",
    "reading_key",
    "readings_by_paragraph",
    "results_from_run",
    "seed_touching_entities",
    "sign_test_p",
    "sources_text",
    "summarise_by_kind",
    "summarise_by_type",
    "unit_rows",
]
