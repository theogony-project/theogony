"""Does a Constellation help a language model answer, or only look like it should?

Every number this repo has ever published about retrieval is a *retrieval*
number: did the expected entity reach the working set. Nothing measured the
thing the working set exists for — an answer. `mesh ask` returns a Constellation
and synthesises nothing, and the question was explicitly deferred when the answer
budget moved to 50: "whether more context completes an answer or dilutes it is
not a question recall can settle" (PHX-1069).

This settles it, by asking the same model the same questions three ways:

  closed_book    no context at all
  vector_only    the top-k nodes by cosine, as plain text — an ordinary RAG
                 baseline over the same substrate content
  constellation  the Constellation: the same nodes, plus the edges among them
                 and what those edges assert

**The closed-book arm is not a formality.** The founding corpus is Hesiod, and a
language model has read Hesiod. Without it, a constellation arm scoring 80% would
prove nothing at all — the model may simply know that Cronus fathered Zeus. Any
claim this module supports is a claim about the *difference* between arms, never
about one arm's number.

`vector_only` is the arm that can falsify the project. If the graph adds nothing
over plain nearest-neighbour text at equal budget, the substrate is an expensive
vector store. It is given the same node count as the Constellation so the
comparison is about structure rather than about how much text each arm got.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from theogony.mesh.eval.corpus_qa import GoldQuestion, _normalise, load_gold
from theogony.mesh.retrieval.defaults import DEFAULT_TOP_K
from theogony.mesh.retrieval.retrieve import retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

ARMS = ("closed_book", "vector_only", "constellation")

# The prompt is a measured choice, not a formality. The first version ended with
# "if the material does not contain the answer, reply exactly: UNKNOWN", and it
# cost 21 points: the model declined 20 of 47 questions whose answers were sitting
# in the material, and scored 31% where this wording scores 52%. Measured on the
# same constellations, same model, same temperature:
#
#     with the UNKNOWN escape          31%   10/47 complete   20 declined
#     exhaustive, no escape            47%   17/47             0
#     exhaustive + explicit scan step  52%   18/47             0
#
# The instruction not to collapse a list of names into the name of their group is
# there for a reason too: asked which children Earth bore to Heaven, the model
# answered "Cyclopes, Hecatoncheires, Titans" while every Titan was in front of it.
#
# All three arms share the wording apart from where the material comes from, so
# the comparison between arms is about the material and not about the asking.
_ASK = (
    "First scan the whole material for every entry that answers the question, then "
    "reply with those names only, comma-separated. Be exhaustive; do not replace a "
    "list of names with the name of the group they belong to."
)
_SYSTEM = f"Answer the question using ONLY the material given. {_ASK}"
_SYSTEM_CLOSED = (
    "Answer the question about Greek mythology from your own knowledge. "
    "First recall every name that answers it, then reply with those names only, "
    "comma-separated. Be exhaustive; do not replace a list of names with the name "
    "of the group they belong to."
)


@dataclass
class AnswerResult:
    id: str
    arm: str
    kind: str
    question: str
    expected: list[str]
    answer: str
    found: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    said_unknown: bool = False
    run: int = 0

    @property
    def recall(self) -> float:
        return len(self.found) / len(self.expected) if self.expected else 0.0

    @property
    def complete(self) -> bool:
        return bool(self.expected) and len(self.found) == len(self.expected)


def _score(answer: str, expected: list[str]) -> tuple[list[str], list[str]]:
    """Which expected names the answer actually names.

    Substring match on the normalised text, which is generous — a verbose answer
    can name an entity in passing. That generosity is identical across arms, so
    it cannot manufacture a difference between them, which is the only thing this
    module claims.
    """
    haystack = f" {_normalise(answer)} "
    found = [name for name in expected if f" {_normalise(name)} " in haystack]
    return found, [name for name in expected if name not in found]


def _constellation_context(
    runtime: MeshRuntime,
    question: str,
    vector: Any,
    top_k: int,
    **retrieve_kwargs: Any,
) -> str:
    # `record_firing=False`: a benchmark must not change the substrate it
    # measures. Today a firing is observationally inert for retrieval, but the
    # counters exist so that tier promotion can read them, and on the day it does
    # a harness that recorded firings would be measuring its own last run
    # (PHX-1101).
    result = retrieve(
        runtime, vector, query=question, top_k=top_k, record_firing=False, **retrieve_kwargs
    )
    constellation = result.constellation
    lines = ["Entities:"]
    lines += [f"- {n.name}" for n in constellation.nodes if not n.is_source_anchor]

    # Only the relations that touch a seed. A seed is where the query entered the
    # graph, so an edge touching one lies on a path from the question into the
    # substrate; the rest is scenery propagation happened to light up.
    #
    # This is a consumer's choice, not a change to what the Constellation carries.
    # The Constellation ranks seed-touching edges first (PHX-1096) and still holds
    # the others; a prompt is where showing them stops paying. Measured on the 47
    # gold questions, answer recall through the model, three runs per arm:
    #
    #     entities only, no relations at all       57 / 52 / 52
    #     every edge in the Constellation          50 / 50 / 51    <- the old default
    #     ranked seed-first but not cut            52 / 52 / 53
    #     cut to the edges touching a seed         50 / 53 / 53    <- this
    #
    # About three points over the old default, and the honest reading is that the
    # spread is nearly the size of the effect. The same arm measured through an
    # ad-hoc renderer scored 56 / 53 / 56; the only difference was the header
    # wording ("Relations:" against "Relations between them:"), and three words of
    # prompt are worth two to three points on this instrument (PHX-1087). The
    # figures above are the shipped path's, because those are the ones a user gets.
    #
    # What is solid across all of it: the unscoped list is the worst arm, in six
    # runs out of six — **worse than showing no relations at all**. Ranking alone
    # does not fix that; the non-seed tail still occupies the prompt.
    seeds = set(constellation.seed_node_ids)
    described = [
        e
        for e in constellation.edges
        if e.relation_descriptor and (e.source_id in seeds or e.target_id in seeds)
    ]
    if described:
        lines.append("")
        lines.append("Relations between them:")
        lines += [
            f"- {e.source_name.split(' — ')[0]} {e.relation_descriptor} "
            f"{e.target_name.split(' — ')[0]}"
            for e in described[:120]
        ]
    return "\n".join(lines)


def _vector_context(runtime: MeshRuntime, vector: Any, top_k: int) -> str:
    hits = runtime.nodes.search_consolidated_by_vector(
        list(vector), vector_column_name="semantic_vector", limit=top_k
    )
    lines = ["Entities:"]
    lines += [
        f"- {h.description or (h.tags[0] if h.tags else h.id)}"
        for h in hits
        if not h.is_source_anchor
    ]
    return "\n".join(lines)


def answer_gold_set(
    runtime: MeshRuntime,
    embed: Any,
    llm: Any,
    *,
    arms: tuple[str, ...] = ARMS,
    gold: list[GoldQuestion] | None = None,
    top_k: int = DEFAULT_TOP_K,
    max_output_tokens: int = 120,
    repeat: int = 1,
    **retrieve_kwargs: Any,
) -> list[AnswerResult]:
    """Ask every gold question once per arm and score what comes back.

    ``retrieve_kwargs`` reach the constellation arm only — the vector arm is a
    plain ANN read by construction. `k_seeds` is the one worth sweeping: the
    HippoRAG run (PHX-1089) found Spreading Activation's whole advantage lives at
    *narrow* seeding, +5.0 exact match at S=2 and nothing at S=10, so a founding
    measurement taken at the default 8 may be measuring the same ceiling.

    ``repeat`` asks the same prompts again. It exists because this instrument was
    quoted to three points for four rounds and cannot resolve them: measured
    across four runs of the founding gold set, the **closed-book** arm — which
    receives no material at all, so it cannot see the mesh, the seed count or the
    top_k — scored 50%, 51%, 51% and **43%**. Nine points of spread on the one
    arm that is constant by construction, at temperature 0 (which no provider
    guarantees to be deterministic, and a mixture-of-experts model batched across
    tenants certainly is not).

    Contexts are built once and reused across repeats, so a repeat measures the
    *model's* variance and nothing else. Retrieval is deterministic here; paying
    for it again would only add noise to the measurement of noise.
    """
    questions = gold if gold is not None else load_gold()
    runtime.rebuild_csr()

    asked: list[tuple[GoldQuestion, str, str, str]] = []
    for gq in questions:
        vector = embed(gq.question)
        for arm in arms:
            if arm == "closed_book":
                system, prompt = _SYSTEM_CLOSED, f"Question: {gq.question}"
            else:
                context = (
                    _constellation_context(runtime, gq.question, vector, top_k, **retrieve_kwargs)
                    if arm == "constellation"
                    else _vector_context(runtime, vector, top_k)
                )
                system = _SYSTEM
                prompt = f"Material:\n{context}\n\nQuestion: {gq.question}"
            asked.append((gq, arm, system, prompt))

    results: list[AnswerResult] = []
    for run in range(max(1, repeat)):
        for gq, arm, system, prompt in asked:
            raw = asyncio.run(
                llm.complete(
                    prompt,
                    system=system,
                    max_output_tokens=max_output_tokens,
                    temperature=0.0,
                )
            )
            answer = (getattr(raw, "text", None) or str(raw)).strip()
            found, missed = _score(answer, gq.expect)
            results.append(
                AnswerResult(
                    id=gq.id,
                    arm=arm,
                    kind=gq.kind,
                    question=gq.question,
                    expected=list(gq.expect),
                    answer=answer,
                    found=found,
                    missed=missed,
                    said_unknown=bool(re.fullmatch(r"\W*unknown\W*", answer, re.I)),
                    run=run,
                )
            )
    return results


def summarise_answers(results: list[AnswerResult]) -> dict[str, dict[str, float]]:
    """Per arm: answer recall, complete answers, how often it declined, and the spread.

    With ``repeat > 1`` the headline figures are means over runs and
    ``answer_recall_min`` / ``answer_recall_max`` bound them. Report the bound
    whenever it exists: the closed-book arm, which cannot see the mesh or any
    retrieval parameter, has been observed at 43% and at 52% on the same 47
    questions at temperature 0. A single number from this instrument is a sample,
    not a measurement, and four rounds of three-point claims were read off it as
    if it were one.
    """
    out: dict[str, dict[str, float]] = {}
    for arm in sorted({r.arm for r in results}):
        rows = [r for r in results if r.arm == arm]
        runs = sorted({r.run for r in rows})
        per_run: list[tuple[float, int]] = []
        for run in runs:
            in_run = [r for r in rows if r.run == run]
            expected = sum(len(r.expected) for r in in_run)
            found = sum(len(r.found) for r in in_run)
            per_run.append(
                (found / expected if expected else 0.0, sum(1 for r in in_run if r.complete))
            )
        recalls = [recall for recall, _ in per_run]
        completes = [float(complete) for _, complete in per_run]
        out[arm] = {
            "questions": float(len(rows) / max(1, len(runs))),
            "runs": float(len(runs)),
            "entities_expected": float(sum(len(r.expected) for r in rows) / max(1, len(runs))),
            "entities_named": float(sum(len(r.found) for r in rows) / max(1, len(runs))),
            "answer_recall": sum(recalls) / len(recalls) if recalls else 0.0,
            "answer_recall_min": min(recalls) if recalls else 0.0,
            "answer_recall_max": max(recalls) if recalls else 0.0,
            "complete_answers": sum(completes) / len(completes) if completes else 0.0,
            "complete_answers_min": min(completes) if completes else 0.0,
            "complete_answers_max": max(completes) if completes else 0.0,
            "declined": float(sum(1 for r in rows if r.said_unknown) / max(1, len(runs))),
        }
    return out


def paired_against(
    results: list[AnswerResult], *, arm: str, baseline: str = "closed_book"
) -> dict[str, float]:
    """Compare two arms question by question instead of arm total by arm total.

    The totals are the wrong comparison when the control is this noisy, because
    both arms' totals move with the model's mood while the *pairing* does not:
    each question is asked of both arms from the same process on the same day.

    Also reports the arm's recall on the **discriminating slice** — the questions
    the baseline failed to answer fully. On a corpus the model has read (the
    founding corpus is Hesiod) the aggregate cannot separate the arms at all;
    what the substrate contributes is only visible where prior knowledge ran out.
    """
    by_id: dict[str, dict[str, list[AnswerResult]]] = {}
    for row in results:
        by_id.setdefault(row.id, {}).setdefault(row.arm, []).append(row)

    def mean_found(rows: list[AnswerResult]) -> float:
        return sum(len(r.found) for r in rows) / len(rows) if rows else 0.0

    better = worse = equal = 0
    slice_found = slice_expected = 0.0
    slice_questions = 0
    for per_arm in by_id.values():
        if arm not in per_arm or baseline not in per_arm:
            continue
        mine, theirs = mean_found(per_arm[arm]), mean_found(per_arm[baseline])
        if mine > theirs:
            better += 1
        elif mine < theirs:
            worse += 1
        else:
            equal += 1
        expected = len(per_arm[arm][0].expected)
        if theirs < expected:  # the baseline did not answer this one fully
            slice_questions += 1
            slice_found += mine
            slice_expected += expected
    return {
        "better": float(better),
        "worse": float(worse),
        "equal": float(equal),
        "slice_questions": float(slice_questions),
        "slice_recall": slice_found / slice_expected if slice_expected else 0.0,
    }
