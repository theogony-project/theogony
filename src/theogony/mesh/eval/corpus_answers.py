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
    result = retrieve(runtime, vector, query=question, top_k=top_k, **retrieve_kwargs)
    lines = ["Entities:"]
    lines += [f"- {n.name}" for n in result.constellation.nodes if not n.is_source_anchor]
    described = [e for e in result.constellation.edges if e.relation_descriptor]
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
    **retrieve_kwargs: Any,
) -> list[AnswerResult]:
    """Ask every gold question once per arm and score what comes back.

    ``retrieve_kwargs`` reach the constellation arm only — the vector arm is a
    plain ANN read by construction. `k_seeds` is the one worth sweeping: the
    HippoRAG run (PHX-1089) found Spreading Activation's whole advantage lives at
    *narrow* seeding, +5.0 exact match at S=2 and nothing at S=10, so a founding
    measurement taken at the default 8 may be measuring the same ceiling.
    """
    questions = gold if gold is not None else load_gold()
    runtime.rebuild_csr()
    results: list[AnswerResult] = []

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
                )
            )
    return results


def summarise_answers(results: list[AnswerResult]) -> dict[str, dict[str, float]]:
    """Per arm: answer recall, complete answers, and how often it declined."""
    out: dict[str, dict[str, float]] = {}
    for arm in sorted({r.arm for r in results}):
        rows = [r for r in results if r.arm == arm]
        expected = sum(len(r.expected) for r in rows)
        found = sum(len(r.found) for r in rows)
        out[arm] = {
            "questions": float(len(rows)),
            "entities_expected": float(expected),
            "entities_named": float(found),
            "answer_recall": found / expected if expected else 0.0,
            "complete_answers": float(sum(1 for r in rows if r.complete)),
            "declined": float(sum(1 for r in rows if r.said_unknown)),
        }
    return out
