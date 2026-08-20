"""Evaluate the live substrate against a corpus gold set.

`qa_retrieval.py` next door benchmarks retrieval *methods* against HippoRAG
datasets on a graph it builds itself. This does something different and
narrower: it asks the substrate as it actually stands — `MeshRuntime` plus
`retrieve()` — questions whose answers are quotable from the corpus that was
read into it.

The reason it exists is a failure mode rather than a feature. Every retrieval
claim made about the founding mesh so far rested on a gold set invented at the
moment of measurement, from a single question. Three diagnoses were drawn from
that and all three were wrong. A fixed, reviewable question set with quoted
evidence is the cheapest instrument that would have caught them.

Two things it reports separately, because conflating them caused those errors:

  coverage — does a node for this entity exist in the mesh at all?
  recall   — of the entities that do exist, how many reach the constellation?

A run whose coverage is 0.4 and whose recall is 0.9 needs more reading. One
whose coverage is 0.95 and whose recall is 0.2 needs better retrieval. The
aggregate number alone cannot tell those apart, and the difference is the whole
question.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from theogony.mesh.retrieval.retrieve import retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

# JSON rather than YAML: pyyaml is not a declared dependency of this package,
# and this repo has been broken three times in one day by relying on a
# transitively-present library resolving differently in CI (AGENTS.md §5).
GOLD_PATH = Path(__file__).parent / "gold" / "founding_corpus.json"


def _normalise(name: str) -> str:
    """Fold a name to its comparable core.

    Digits are stripped because the corpus carries inline footnote markers —
    the succession passage reads "Hestia 1618" — and those reach node names.
    """
    text = re.sub(r"\d+", " ", (name or "").lower())
    text = re.sub(r"[^a-z\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class GoldQuestion:
    id: str
    question: str
    expect: list[str]
    evidence: str


@dataclass
class QuestionResult:
    id: str
    question: str
    expected: list[str]
    present: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    retrieved: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return len(self.present) / len(self.expected) if self.expected else 0.0

    @property
    def recall(self) -> float:
        """Recall over the entities that exist — retrieval's share of the blame."""
        return len(self.retrieved) / len(self.present) if self.present else 0.0


def load_gold(path: Path | None = None) -> list[GoldQuestion]:
    raw: dict[str, Any] = json.loads((path or GOLD_PATH).read_text(encoding="utf-8"))
    return [
        GoldQuestion(
            id=q["id"], question=q["question"], expect=list(q["expect"]), evidence=q["evidence"]
        )
        for q in raw["questions"]
    ]


def _name_index(runtime: MeshRuntime) -> dict[str, set[str]]:
    """Map every normalised name a node answers to onto that node's id.

    Built from tags and from the head of the description, which is where the
    entity's name lives since PHX-1065 ("Zeus — King of the gods, ...").
    """
    index: dict[str, set[str]] = {}
    for node in runtime.nodes.iter_consolidated():
        if node.is_source_anchor:
            continue
        keys = {_normalise(tag) for tag in (node.tags or [])}
        head = (node.description or "").split("—")[0]
        keys.add(_normalise(head))
        for key in keys:
            if key and key not in {"concept", "paragraph concept"}:
                index.setdefault(key, set()).add(str(node.id))
    return index


def evaluate(
    runtime: MeshRuntime,
    embed: Any,
    *,
    gold: list[GoldQuestion] | None = None,
    top_k: int = 30,
    **retrieve_kwargs: Any,
) -> list[QuestionResult]:
    """Run every gold question and score coverage and recall separately.

    ``embed`` is any callable turning a question into a query vector.
    """
    questions = gold if gold is not None else load_gold()
    names = _name_index(runtime)
    runtime.rebuild_csr()

    results: list[QuestionResult] = []
    for gq in questions:
        result = QuestionResult(id=gq.id, question=gq.question, expected=list(gq.expect))
        wanted: dict[str, set[str]] = {}
        for name in gq.expect:
            ids = names.get(_normalise(name), set())
            if ids:
                result.present.append(name)
                wanted[name] = ids
            else:
                result.missing.append(name)

        found = {
            node.node_id
            for node in retrieve(
                runtime,
                embed(gq.question),
                top_k=top_k,
                # The question text, the way `mesh ask` passes it. Retrieval uses
                # it to seed on entities the question names outright, so an
                # evaluator that withheld it would measure a different pipeline
                # than the one users run.
                query=gq.question,
                **retrieve_kwargs,
            ).constellation.nodes
        }
        result.retrieved = [name for name, ids in wanted.items() if ids & found]
        results.append(result)
    return results


def recall_curve(
    runtime: MeshRuntime,
    embed: Any,
    *,
    ks: Sequence[int] = (10, 20, 30, 50, 100, 200),
    gold: list[GoldQuestion] | None = None,
    **retrieve_kwargs: Any,
) -> dict[int, float]:
    """Recall as a function of the answer budget.

    A single number at one ``top_k`` reads as "retrieval finds 65% of the
    answers", which is the wrong picture. Measured on the founding mesh, recall
    is 65% at 30 and **95% at 200** — the top 4% of a 5,002-node substrate. The
    ranking is largely right; what is tight is the budget. Confusing "cannot
    find" with "cannot fit" points the next piece of work at the wrong place,
    so the curve is reported rather than a point.

    Cost is not what makes the budget small: 30 -> 50 is 4 ms, 30 -> 100 is
    16 ms. Whether a wider constellation actually helps the consumer is a
    separate question that recall cannot settle — more context can dilute an
    answer as easily as complete it.
    """
    questions = gold if gold is not None else load_gold()
    return {
        k: summarise(evaluate(runtime, embed, gold=questions, top_k=k, **retrieve_kwargs))[
            "recall_given_coverage"
        ]
        for k in ks
    }


def summarise(results: list[QuestionResult]) -> dict[str, float]:
    expected = sum(len(r.expected) for r in results)
    present = sum(len(r.present) for r in results)
    retrieved = sum(len(r.retrieved) for r in results)
    fully = sum(1 for r in results if r.present and len(r.retrieved) == len(r.present))
    return {
        "questions": float(len(results)),
        "entities_expected": float(expected),
        "entities_in_mesh": float(present),
        "entities_retrieved": float(retrieved),
        "coverage": present / expected if expected else 0.0,
        "recall_given_coverage": retrieved / present if present else 0.0,
        "end_to_end": retrieved / expected if expected else 0.0,
        "questions_fully_answered": float(fully),
    }
