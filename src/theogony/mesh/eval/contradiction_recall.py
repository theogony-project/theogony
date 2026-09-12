"""Does a question about a disputed matter return both sides? (PHX-1107)

Every retrieval number this repo has published asks whether the *right* answer
reached the working set. A contradiction has no right answer: the corpus says
Night bore the Fates and it says Themis bore them, and a Chronik that returns
one and not the other has silently picked a winner — the encyclopaedia
behaviour PANTHEON_VISION's Non-Negotiable 2 forbids.

So this scores something the other harnesses cannot express: **both-sides
recall**. A question counts only when at least one entity from side A and one
from side B are in the Constellation. Carrying four entities from one side and
none from the other scores zero.

The comparison that matters is not against a baseline retriever but between
frame profiles on the *same* substrate. `any` routes nothing and is what the
substrate does today; `contradiction` (`frames.QUERY_PROFILES`) attenuates
every settled claim to zero and admits the disputed, superseded and refuted —
so it can only help if something in the mesh actually carries those stances.
Running both is what tells us whether the frames are signal or decoration.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from theogony.mesh import frames
from theogony.mesh.eval.corpus_qa import _name_index, _normalise
from theogony.mesh.retrieval.defaults import DEFAULT_TOP_K
from theogony.mesh.retrieval.retrieve import retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

GOLD_PATH = Path(__file__).resolve().parent / "gold" / "founding_contradictions.json"


@dataclass
class ContradictionSide:
    label: str
    expect: list[str]
    work: str
    evidence: str = ""


@dataclass
class ContradictionQuestion:
    id: str
    question: str
    sides: list[ContradictionSide]
    strength: str = "DIRECT"
    scope: str = "cross-work"
    shared: list[str] = field(default_factory=list)


def load_contradictions(path: Path | None = None) -> list[ContradictionQuestion]:
    raw: dict[str, Any] = json.loads((path or GOLD_PATH).read_text(encoding="utf-8"))
    return [
        ContradictionQuestion(
            id=q["id"],
            question=q["question"],
            strength=q.get("strength", "DIRECT"),
            scope=q.get("scope", "cross-work"),
            shared=list(q.get("shared", [])),
            sides=[
                ContradictionSide(
                    label=s["label"],
                    expect=list(s["expect"]),
                    work=s["work"],
                    evidence=s.get("evidence", ""),
                )
                for s in q["sides"]
            ],
        )
        for q in raw["questions"]
    ]


@dataclass
class SideResult:
    label: str
    expect: list[str]
    found: list[str]

    @property
    def present(self) -> bool:
        return bool(self.found)


@dataclass
class ContradictionResult:
    id: str
    question: str
    profile: str
    sides: list[SideResult]
    nodes: int
    contradiction_edges: int = 0

    @property
    def both_sides(self) -> bool:
        return all(side.present for side in self.sides)

    @property
    def any_side(self) -> bool:
        return any(side.present for side in self.sides)

    @property
    def sides_found(self) -> int:
        return sum(1 for side in self.sides if side.present)


def evaluate_contradictions(
    runtime: MeshRuntime,
    embed: Callable[[str], Sequence[float]],
    *,
    profile: str = "any",
    gold: list[ContradictionQuestion] | None = None,
    top_k: int = DEFAULT_TOP_K,
    frame_threshold: float = 0.0,
    **retrieve_kwargs: Any,
) -> list[ContradictionResult]:
    """Ask every contradiction question and score whether both sides came back."""
    questions = gold if gold is not None else load_contradictions()
    names = _name_index(runtime)
    runtime.rebuild_csr()
    query_frame = frames.query_frame(profile, dim=runtime.frame_dim)
    routed = any(abs(v) > 0.0 for v in query_frame)

    results: list[ContradictionResult] = []
    for question in questions:
        result = retrieve(
            runtime,
            embed(question.question),
            query=question.question,
            top_k=top_k,
            record_firing=False,
            query_frame=query_frame if routed else None,
            frame_threshold=frame_threshold,
            **retrieve_kwargs,
        )
        constellation = result.constellation
        present_ids = {n.node_id for n in constellation.nodes}
        sides = []
        for side in question.sides:
            found = [
                name for name in side.expect if names.get(_normalise(name), set()) & present_ids
            ]
            sides.append(SideResult(label=side.label, expect=list(side.expect), found=found))
        results.append(
            ContradictionResult(
                id=question.id,
                question=question.question,
                profile=profile,
                sides=sides,
                nodes=len(constellation.nodes),
                contradiction_edges=sum(
                    1
                    for e in constellation.edges
                    if frames.is_contradiction_kind(e.relation_descriptor)
                    or (e.relation_descriptor or "").startswith("contradicts_on_")
                ),
            )
        )
    return results


def summarise(results: Sequence[ContradictionResult]) -> dict[str, float]:
    """Both-sides recall, one-side recall, and the mean number of sides found."""
    if not results:
        return {"questions": 0.0, "both_sides": 0.0, "any_side": 0.0, "sides_mean": 0.0}
    return {
        "questions": float(len(results)),
        "both_sides": sum(r.both_sides for r in results) / len(results),
        "any_side": sum(r.any_side for r in results) / len(results),
        "sides_mean": sum(r.sides_found for r in results) / len(results),
        "contradiction_edges": sum(r.contradiction_edges for r in results) / len(results),
    }
