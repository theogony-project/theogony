"""Making disagreement legible: the substrate learns what it doubts (PHX-1107).

`MESH_SUBSTRATE.md` §"Contradiction resolution" describes the mechanism this
module implements, in the voice of an agent that does not exist yet: "Argus
identifies two claims with directly contradicting frame-content combinations
... emits a `ContradictionFinding` linking the two and writes `CONTRADICTS`
edges between them ... Argus makes contradiction *legible*; the substrate's
dynamics decide which side the topology eventually favours."

Nothing did that, and `relation_kind` had ten values with no disagreement among
them, so PANTHEON_VISION's Non-Negotiable 2 — "contradiction, uncertainty and
competing interpretations are preserved" — had no representation anywhere in
the schema. A frame vocabulary alone does not fix that: a stance says how *one*
paragraph speaks, and a contradiction is a relation *between* two of them. A
paragraph-at-a-time reader cannot see it, because it never sees the other
paragraph.

## How a candidate is found

Structurally, then adjudicated — the same division of labour as Oneiros
consolidation (`runtime/consolidation.py`), for the same reason: structure is
cheap and recall-oriented, judgement is expensive and precision-oriented.

A candidate is two asserted relations that share an endpoint and a descriptor
but disagree about the other endpoint:

    Night  --bore-->  the Fates          (Theogony ll. 211-225)
    Themis --bore-->  the Fates          (Theogony ll. 901-906)

grouped by (target, descriptor) with two distinct sources; and the mirror,
grouped by (source, descriptor) with two distinct targets:

    Aphrodite --born_from--> the foam    (Theogony ll. 176-206)
    Aphrodite --born_from--> Zeus        (Hymn V l. 81)

**The filter that makes this precise is provenance, not semantics.** Two
relations written from the *same* paragraph are an enumeration — "Rhea bore
Hestia, Demeter, Hera" is three `parent_of` edges and no disagreement — so a
candidate requires that the two relations be witnessed by disjoint sets of
chunks. Without that filter every genealogy in the corpus is a contradiction.

What survives is still mostly compatible: Zeus fathers many children, and
`father_of` is not functional. That is what the adjudicator is for — it is
asked whether both can be true at once, not whether they look similar.

## What is written

For each confirmed contradiction, `contradicts` edges between the **chunks**
that witness the two sides (the doctrine's "edges between them"), and the
chunks' frames are moved to the `disputed` stance. The second half is what
makes the finding reach retrieval: a `contradiction` query profile
(`frames.QUERY_PROFILES`) attenuates every settled claim to zero and admits
exactly the disputed, superseded and refuted ones. Before this the profile had
nothing to find.

Nothing is deleted and no side is adjudicated as *wrong*. `MESH_SUBSTRATE` is
explicit that removal is for "demonstrably wrong with traceable evidence" and
that "disagreement and likelihood are handled by frame-tagging and
contradiction modelling, not by removal".
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from ulid import ULID

from theogony.mesh import frames
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge

CONTRADICTION_ACTION = "mesh_contradiction_pass"

# Relations Kadmos writes between two entities. Everything else — the
# chunk-to-entity `mentions`, the paragraph lattice, the source hierarchy — is
# bookkeeping about where text sat, not a claim about the world.
RELATION_CONTEXT = "kadmos_relation"
MENTION_CONTEXTS = ("kadmos_mentions", "kadmos_paragraph_concept")

# A group with more distinct partners than this is a hub, not a disagreement:
# `parent_of` on Zeus, `mentions` on a frequent name. Candidates come from the
# narrow groups, where two accounts compete rather than accumulate.
DEFAULT_MAX_GROUP = 4

# Descriptor classes, and why they are needed.
#
# The structural filter compares (endpoint, descriptor) pairs, so it only sees a
# disagreement when both sides spell the relation the same way. Kadmos does not:
# measured on the framed re-read, parenthood arrives under more than thirty
# spellings — `bore` 145, `son_of` 120, `fathered` 80, `daughter_of` 79,
# `father_of` 45, `mother_of` 45, `parent_of` 43, `child_of` 26, plus
# `bare_to`, `gave birth to`, `is_son_of` and the rest. "Night bore the Fates"
# and "Themis is_mother_of the Fates" are the same claim about the same slot and
# would never have met.
#
# Worse, half of those spellings run the other way: `son_of` points child to
# parent, `bore` points parent to child. Canonicalising the direction is what
# lets the two meet at all, and it is also what makes the grouping *functional*
# — a child has one mother, while a mother has many children, so the question
# worth asking is always "how many parents does this child have".
#
# This table is curated and covers kinship, because the founding corpus is a
# genealogy. A corpus about something else would need its own classes; nothing
# here derives them. `MESH_SUBSTRATE` calls the descriptor "a short string label
# intended for human and agent comprehension" whose truth lives in the topology,
# so normalising it for comparison changes no substrate state — the edges keep
# the words Kadmos wrote.
_PARENT_TO_CHILD = (
    "bore",
    "bare",
    "bare_to",
    "bare_children_to",
    "bore_to",
    "conceived_and_bore",
    "gave_birth_to",
    "gave_birth",
    "father_of",
    "fathered",
    "mother_of",
    "parent_of",
    "is_father_of",
    "is_mother_of",
    "begot",
    "begat",
    "sired",
    "children_of_",
)
_CHILD_TO_PARENT = (
    "son_of",
    "sons_of",
    "daughter_of",
    "daughters_of",
    "child_of",
    "children_of",
    "is_son_of",
    "is_daughter_of",
    "born_of",
    "born_from",
    "born_to",
    "descended_from",
    "offspring_of",
    "regarded_as_son_of",
    "makes_son_of",
    "names_as_son",
    "says_has_son",
)
PARENTHOOD = "parenthood"


def normalise_descriptor(descriptor: str | None) -> tuple[str, bool]:
    """A descriptor's comparison class and whether the edge must be flipped.

    Returns `(class, flipped)`. `flipped` means the edge points child-to-parent
    and should be read parent-to-child, so that both spellings land in one
    group. Anything outside the curated classes keeps its own spelling, folded
    to lower case with separators unified — which alone merges `mother of` with
    `mother_of`.
    """
    raw = (descriptor or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return "", False
    if raw in _PARENT_TO_CHILD:
        return PARENTHOOD, False
    if raw in _CHILD_TO_PARENT:
        return PARENTHOOD, True
    return raw, False


@dataclass(frozen=True)
class ContradictionCandidate:
    """Two relations that share an endpoint and a descriptor but not the rest."""

    shared_id: str
    shared_name: str
    descriptor: str
    # The endpoint each side disagrees about.
    left_id: str
    left_name: str
    right_id: str
    right_name: str
    # Which way the group was formed: `source` means both relations start at
    # `shared_id`, `target` means both end there.
    axis: str
    left_chunks: tuple[str, ...]
    right_chunks: tuple[str, ...]
    # The words Kadmos actually wrote on each side. `descriptor` is the class
    # the two were grouped under, which may be a normalised name no reader
    # would recognise ("parenthood"); the adjudicator must see the claim as the
    # text made it, or it is judging a paraphrase.
    left_descriptor: str = ""
    right_descriptor: str = ""

    @property
    def key(self) -> tuple[str, str, str, str]:
        left, right = sorted((self.left_id, self.right_id))
        return (self.shared_id, self.descriptor, left, right)

    def claim(self, side: str) -> str:
        other = self.left_name if side == "left" else self.right_name
        spelling = (self.left_descriptor if side == "left" else self.right_descriptor) or (
            self.descriptor
        )
        if self.axis == "source":
            return f"{self.shared_name} {spelling} {other}"
        return f"{other} {spelling} {self.shared_name}"


@dataclass(frozen=True)
class ContradictionVerdict:
    candidate: ContradictionCandidate
    verdict: str  # CONTRADICTION | COMPATIBLE | UNCERTAIN
    reason: str = ""

    @property
    def confirmed(self) -> bool:
        return self.verdict == "CONTRADICTION"


@dataclass
class ContradictionResult:
    candidates: int = 0
    adjudicated: int = 0
    confirmed: int = 0
    compatible: int = 0
    uncertain: int = 0
    edges_written: int = 0
    chunks_marked: int = 0
    audit_id: str | None = None
    adjudicator_model: str | None = None
    elapsed_s: float = 0.0
    findings: list[dict[str, Any]] = field(default_factory=list)


def _spelling(edges: Sequence[Edge]) -> str:
    """The descriptor as the text wrote it, for the claim shown to a judge."""
    for edge in edges:
        if edge.relation_descriptor:
            return str(edge.relation_descriptor)
    return ""


def _name(node: ConsolidatedNode | None, node_id: str) -> str:
    if node is None:
        return node_id
    if node.description:
        head = node.description.split(" — ", 1)[0].strip()
        if head:
            return head
    return node.tags[0] if node.tags else node_id


def witnesses(
    edges: Sequence[Edge],
) -> dict[str, set[str]]:
    """Chunk (and paragraph-concept) ids that mention each entity.

    The provenance filter needs to know which paragraph a relation came from,
    and the edge itself does not say: Kadmos writes entity-to-entity relations
    with no paragraph on them. What it does write is a `mentions` edge from the
    chunk to every entity the paragraph resolved, so a relation's witnesses are
    the chunks that mention *both* of its endpoints.
    """
    out: dict[str, set[str]] = {}
    for edge in edges:
        if edge.creation_context in MENTION_CONTEXTS:
            out.setdefault(str(edge.target_id), set()).add(str(edge.source_id))
    return out


def propose_contradictions(
    edges: Sequence[Edge],
    nodes: Mapping[str, ConsolidatedNode],
    *,
    max_group: int = DEFAULT_MAX_GROUP,
    limit: int = 0,
) -> list[ContradictionCandidate]:
    """Relations that compete for the same slot, witnessed by different text."""
    mentions = witnesses(edges)
    relations = [
        e
        for e in edges
        if e.creation_context == RELATION_CONTEXT
        and e.relation_descriptor
        and not frames.is_contradiction_kind(e.relation_kind)
    ]

    by_source: dict[tuple[str, str], dict[str, list[Edge]]] = {}
    by_target: dict[tuple[str, str], dict[str, list[Edge]]] = {}
    for edge in relations:
        src, tgt = str(edge.source_id), str(edge.target_id)
        desc, flipped = normalise_descriptor(edge.relation_descriptor)
        if not desc:
            continue
        if flipped:
            src, tgt = tgt, src
        by_source.setdefault((src, desc), {}).setdefault(tgt, []).append(edge)
        by_target.setdefault((tgt, desc), {}).setdefault(src, []).append(edge)

    seen: set[tuple[str, str, str, str]] = set()
    candidates: list[ContradictionCandidate] = []
    for axis, groups in (("source", by_source), ("target", by_target)):
        for (shared, desc), partners in groups.items():
            if not 2 <= len(partners) <= max_group:
                continue
            ordered = sorted(partners)
            for i, left in enumerate(ordered):
                for right in ordered[i + 1 :]:
                    left_w = mentions.get(left, set()) & mentions.get(shared, set())
                    right_w = mentions.get(right, set()) & mentions.get(shared, set())
                    # Same paragraph on both sides: an enumeration, not a
                    # disagreement. This one filter is what keeps every
                    # genealogy in the corpus out of the candidate set.
                    if not left_w or not right_w or left_w & right_w:
                        continue
                    candidate = ContradictionCandidate(
                        shared_id=shared,
                        shared_name=_name(nodes.get(shared), shared),
                        descriptor=desc,
                        left_id=left,
                        left_name=_name(nodes.get(left), left),
                        right_id=right,
                        right_name=_name(nodes.get(right), right),
                        axis=axis,
                        left_chunks=tuple(sorted(left_w)),
                        right_chunks=tuple(sorted(right_w)),
                        left_descriptor=_spelling(partners[left]),
                        right_descriptor=_spelling(partners[right]),
                    )
                    if candidate.key in seen:
                        continue
                    seen.add(candidate.key)
                    candidates.append(candidate)
    # Stable order so a truncated run is reproducible, and so the cheapest
    # disagreements (fewest witnesses, most specific) come first.
    candidates.sort(key=lambda c: (len(c.left_chunks) + len(c.right_chunks), c.key))
    return candidates[:limit] if limit else candidates


class ContradictionAdjudicator(Protocol):
    """Decides one candidate. Implemented by the LLM and by tests."""

    async def judge(self, candidate: ContradictionCandidate) -> ContradictionVerdict: ...


class LLMContradictionAdjudicator:
    """Asks a small model whether two claims can both be true."""

    def __init__(self, llm: Any, *, max_output_tokens: int = 120) -> None:
        self._llm = llm
        self._max_output_tokens = max_output_tokens

    @property
    def model_id(self) -> str:
        return str(getattr(self._llm, "model_id", "unknown"))

    async def judge(self, candidate: ContradictionCandidate) -> ContradictionVerdict:
        prompt = (
            f"Claim A: {candidate.claim('left')}\n"
            f"Claim B: {candidate.claim('right')}\n\n"
            "These come from different passages of one body of text. Can both be "
            "true at the same time?\n"
            "Answer CONTRADICTION if they cannot both hold: the slot admits one "
            "filler and they give two (two different mothers, two different "
            "birthplaces, two incompatible origins).\n"
            "Answer COMPATIBLE if both can hold. In particular: a father and a "
            "mother are both parents and do NOT conflict; one figure can have "
            "many children, many deeds and many epithets; and two names for the "
            "same figure (Helios / Helius, Apollo / Phoebus) do not conflict.\n"
            "Answer UNCERTAIN if you cannot tell, or if the two names might be "
            "different figures who happen to share a name.\n"
            "Reply with the single word, then a short reason."
        )
        try:
            result = await self._llm.complete(
                prompt,
                system=(
                    "You judge whether two claims about Greek myth conflict. Be "
                    "strict about what a conflict is: one figure having several "
                    "children is COMPATIBLE, a father plus a mother is "
                    "COMPATIBLE, two spellings of one name are COMPATIBLE. Two "
                    "different mothers for one child is a CONTRADICTION."
                ),
                max_output_tokens=self._max_output_tokens,
                temperature=0.0,
            )
            text = (getattr(result, "text", None) or str(result)).strip()
        except Exception as exc:  # noqa: BLE001
            return ContradictionVerdict(candidate, "UNCERTAIN", f"adjudicator failed: {exc}")
        head = text.split(maxsplit=1)
        word = head[0].strip(".,:;*").upper() if head else ""
        reason = head[1].strip()[:240] if len(head) > 1 else ""
        if word not in {"CONTRADICTION", "COMPATIBLE", "UNCERTAIN"}:
            upper = text.upper()
            word = (
                "CONTRADICTION"
                if "CONTRADICTION" in upper
                else "COMPATIBLE"
                if "COMPATIBLE" in upper
                else "UNCERTAIN"
            )
        return ContradictionVerdict(candidate, word, reason)


class ReplayAdjudicator:
    """Replays verdicts recorded by an earlier run — measurement without spend."""

    def __init__(self, verdicts: Mapping[tuple[str, str, str, str], str]) -> None:
        self._verdicts = dict(verdicts)

    @classmethod
    def from_findings(cls, findings: Iterable[Mapping[str, Any]]) -> ReplayAdjudicator:
        table: dict[tuple[str, str, str, str], str] = {}
        for row in findings:
            left, right = sorted((str(row["left_id"]), str(row["right_id"])))
            key = (str(row["shared_id"]), str(row["descriptor"]), left, right)
            table[key] = str(row["verdict"])
        return cls(table)

    @property
    def model_id(self) -> str:
        return "replay"

    async def judge(self, candidate: ContradictionCandidate) -> ContradictionVerdict:
        return ContradictionVerdict(candidate, self._verdicts.get(candidate.key, "UNCERTAIN"))


def contradiction_edges(
    verdict: ContradictionVerdict, *, now: datetime, weight: float = 1.0
) -> list[Edge]:
    """`contradicts` edges between the chunks that witness the two sides.

    Written in both directions because contradiction is symmetric and the CSR
    is not: a one-way edge would make the disagreement visible from one
    paragraph and invisible from the other.
    """
    candidate = verdict.candidate
    out: list[Edge] = []
    descriptor = f"contradicts_on_{candidate.descriptor}"[:120]
    for left in candidate.left_chunks:
        for right in candidate.right_chunks:
            for source, target in ((left, right), (right, left)):
                out.append(
                    Edge(
                        source_id=ULID.from_str(source),
                        target_id=ULID.from_str(target),
                        weight=weight,
                        born_at=now,
                        last_fired_at=now,
                        valid_from=now,
                        relation_kind="contradicts",
                        relation_descriptor=descriptor,
                        description=(
                            f"{candidate.claim('left')} / {candidate.claim('right')}"
                            + (f" — {verdict.reason}" if verdict.reason else "")
                        )[:500],
                        creation_context=CONTRADICTION_ACTION,
                        # A contradiction edge joins two claims that do *not*
                        # share a frame; saying so is what the field is for.
                        frame_consistency=0.0,
                    )
                )
    return out


def mark_disputed(chunk: ChunkNode, *, dim: int) -> ChunkNode:
    """Move a chunk's frame to the disputed stance, keeping everything else."""
    return chunk.model_copy(update={"frame_vector": frames.frame_vector("disputed", dim=dim)})


async def run_contradiction_pass(
    runtime: MeshRuntime,
    adjudicator: ContradictionAdjudicator,
    *,
    max_group: int = DEFAULT_MAX_GROUP,
    limit: int = 0,
    apply: bool = True,
    log: Any = None,
) -> ContradictionResult:
    """Find, judge and record the corpus's disagreements with itself."""
    started = time.monotonic()
    say = log or (lambda _msg: None)
    edges = runtime.edges.load_all_edges()
    nodes = {str(n.id): n for n in runtime.nodes.iter_consolidated(page_size=1024)}
    candidates = propose_contradictions(edges, nodes, max_group=max_group, limit=limit)
    result = ContradictionResult(candidates=len(candidates))
    result.adjudicator_model = str(getattr(adjudicator, "model_id", "unknown"))
    say(f"{len(candidates)} candidates from {len(edges)} edges, {len(nodes)} nodes")

    confirmed: list[ContradictionVerdict] = []
    for i, candidate in enumerate(candidates, 1):
        verdict = await adjudicator.judge(candidate)
        result.adjudicated += 1
        if verdict.confirmed:
            result.confirmed += 1
            confirmed.append(verdict)
        elif verdict.verdict == "COMPATIBLE":
            result.compatible += 1
        else:
            result.uncertain += 1
        result.findings.append(
            {
                "shared_id": candidate.shared_id,
                "shared_name": candidate.shared_name,
                "descriptor": candidate.descriptor,
                "left_id": candidate.left_id,
                "left_name": candidate.left_name,
                "right_id": candidate.right_id,
                "right_name": candidate.right_name,
                "axis": candidate.axis,
                "left_descriptor": candidate.left_descriptor,
                "right_descriptor": candidate.right_descriptor,
                "verdict": verdict.verdict,
                "reason": verdict.reason,
                "left_chunks": list(candidate.left_chunks),
                "right_chunks": list(candidate.right_chunks),
            }
        )
        if i % 25 == 0 or verdict.confirmed:
            say(
                f"[{i}/{len(candidates)}] {verdict.verdict:13s} "
                f"{candidate.claim('left')}  /  {candidate.claim('right')}"
            )

    if apply and confirmed:
        now = datetime.now(UTC)
        new_edges = [e for v in confirmed for e in contradiction_edges(v, now=now)]
        runtime.edges.append_edges(new_edges)
        result.edges_written = len(new_edges)

        disputed_ids = {c for v in confirmed for c in v.candidate.left_chunks}
        disputed_ids |= {c for v in confirmed for c in v.candidate.right_chunks}
        dim = runtime.frame_dim
        chunks = list(runtime.nodes.iter_chunks(page_size=1024))
        rewritten = [
            mark_disputed(chunk, dim=dim) if str(chunk.id) in disputed_ids else chunk
            for chunk in chunks
        ]
        # A chunk id that is really a paragraph-concept node lives in the
        # consolidated table, not the chunk table; those keep their own frame.
        result.chunks_marked = sum(1 for c in chunks if str(c.id) in disputed_ids)
        if result.chunks_marked:
            runtime.nodes.replace_all_chunks(rewritten)
        runtime.invalidate_csr_cache()

    result.elapsed_s = time.monotonic() - started
    result.audit_id = runtime.audit.append(
        action=CONTRADICTION_ACTION,
        detail={
            "candidates": result.candidates,
            "adjudicated": result.adjudicated,
            "confirmed": result.confirmed,
            "compatible": result.compatible,
            "uncertain": result.uncertain,
            "edges_written": result.edges_written,
            "chunks_marked": result.chunks_marked,
            "adjudicator_model": result.adjudicator_model,
            "max_group": max_group,
            "applied": apply,
            "elapsed_s": round(result.elapsed_s, 2),
        },
    )
    return result
