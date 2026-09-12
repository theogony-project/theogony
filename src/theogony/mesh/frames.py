"""Epistemic frames: the stance a claim is made in, as a vector (PHX-1107).

`MESH_RETRIEVAL.md` §"Frame-sensitive resonance" lifts polarity out of the
semantic vector and into a separate `frame_vector`, because "Thyroxine is an
oxindole derivative" and "Thyroxine is *not* an oxindole derivative" embed to
nearly the same point and no realistic semantic encoder separates them. The
frame is where the substrate is supposed to keep *how* a thing is claimed:
asserted, denied, supposed, reported, disputed, superseded.

Until now it kept a salted SHA-256 projection of the label (PHX-1095). 5,002
nodes, 4,977 distinct vectors, no stance anywhere in them — so frame routing
could only mask edges by a hash, and every mechanism downstream of the frame
(the immune system, contradiction resolution, Argus, the Chronik's "disputed"
status) had nothing to read. This module is the signal those mechanisms wait
for.

## The construction

The doctrine names seven frames — definition, current claim, historical claim,
refuted claim, hypothesis, observation, direct quote — and says they are
"learned embedding regions", with a rule-bootstrapped encoder as the explicit
interim (`MESH_IMPLEMENTATION.md` §"Open implementation questions"). This is
that bootstrap, and it is **factored rather than enumerated**: the seven frames
are not seven labels in a lookup table but seven points in a space spanned by
independent epistemic axes.

    veridicality   asserted      <-> negated          weight 2.0
    modality       factual       <-> hypothetical     weight 1.0
    time           current       <-> historical       weight 1.0
    standing       uncontested   <-> disputed         weight 1.0
    force          in_force      <-> superseded       weight 1.0
    attribution    direct        <-> attributed       weight 0.5
    register       definition    <-> observation      weight 0.5

Each axis occupies one dimension of the 64-d field; the remaining 57 stay zero
and are what a trained encoder would later fill. Factoring matters because the
combinations are the point: a historical claim that was also refuted is *both*
`time = -1` and `veridicality = -1`, and no enumeration of seven labels can
express it. Kadmos still emits a label, because a label is what a language
model can reliably produce; the label names a point, and points compose.

Veridicality carries twice the weight of the other axes because it is the one
the doctrine builds its whole argument around — negation is the failure mode
that motivates having a frame vector at all. The rest are equal except
attribution and register, which colour a claim without changing whether it is
being made.

## What the cosine then does

`frame_consistency` (in `retrieval/frame_routing.py`) takes the cosine of a
node's frame against the query's, clamps it to [0, 1], and scales the node's
edges by it. With this basis that arithmetic carries the doctrine's own worked
example:

    definition      vs current claim     0.98   (both admitted)
    observation     vs current claim     0.77   (admitted, slightly off-axis)
    historical      vs current claim     0.65   (weighted down, still present)
    superseded      vs current claim     0.50   (halved)
    refuted         vs current claim    -0.50 -> 0.0  (fully attenuated)
    refuted         vs historical       -0.49 -> 0.0  (they disagree, and the
                                                 axes say so: one affirms what
                                                 the other denies)

which is the Kendall/thyroxine behaviour `MESH_RETRIEVAL` describes: "What is
thyroxine?" does not retrieve the refuted 1915 structure. The query that *does*
retrieve it is not the historical stance alone but the profile that mixes the
two (`what_was_believed`), which is why `QUERY_PROFILES` exists. A zero frame
(an entity, a source anchor — things that hold no stance) is neutral by
construction and is never suppressed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

DEFAULT_FRAME_DIM = 64


@dataclass(frozen=True)
class FrameAxis:
    """One epistemic dimension, with the two poles it runs between."""

    name: str
    positive: str
    negative: str
    weight: float


# Order is load-bearing: an axis's index in this tuple is its dimension in the
# frame vector, and meshes written before a reordering would silently disagree
# with meshes written after one. Append, never reorder.
FRAME_AXES: tuple[FrameAxis, ...] = (
    FrameAxis("veridicality", "asserted", "negated", 2.0),
    FrameAxis("modality", "factual", "hypothetical", 1.0),
    FrameAxis("time", "current", "historical", 1.0),
    FrameAxis("standing", "uncontested", "disputed", 1.0),
    FrameAxis("force", "in_force", "superseded", 1.0),
    FrameAxis("attribution", "direct", "attributed", 0.5),
    FrameAxis("register", "general", "particular", 0.5),
)

AXIS_INDEX: Mapping[str, int] = {axis.name: i for i, axis in enumerate(FRAME_AXES)}

# The doctrine's seven frames as coordinates, plus the two the Chronik needs to
# say that something is contested or has been overtaken (`MESH_SUBSTRATE.md`
# §"Contradiction resolution", PANTHEON_VISION §"Non-Negotiable Principles" 2
# and 3). An axis left out of a profile is 0 — not asserted either way, which
# is what "this stance says nothing about time" should mean.
STANCE_PROFILES: Mapping[str, Mapping[str, float]] = {
    # "Thyroxine is iodothyronine." Timeless, general, plainly asserted.
    "definition": {"veridicality": 1.0, "modality": 1.0, "time": 1.0, "register": 1.0},
    # "Treatment X is effective for condition Y." Asserted about now.
    "current_claim": {"veridicality": 1.0, "modality": 1.0, "time": 1.0},
    # "In 1915, Kendall held thyroxine to be an oxindole derivative."
    "historical_claim": {"veridicality": 1.0, "modality": 1.0, "time": -1.0, "attribution": -1.0},
    # "Thyroxine is *not* an oxindole derivative." Denied, and what it denies
    # no longer holds.
    "refuted_claim": {"veridicality": -1.0, "modality": 1.0, "force": -1.0},
    # "It is hypothesised that X."
    "hypothesis": {"modality": -1.0, "time": 1.0},
    # "The patient reported X." A particular, witnessed thing: strongly
    # particular, mildly second-hand.
    "observation": {"veridicality": 1.0, "register": -1.0, "attribution": -0.5},
    # "X said: 'Y'." The substrate vouches for the saying, not the said — so
    # veridicality is positive (the saying is asserted) and attribution carries
    # the distance to the content. Without the positive veridicality a quote is
    # exactly orthogonal to every plain claim and a what-is query attenuates it
    # to zero, which on a corpus that is half direct speech would delete half
    # the substrate from retrieval (measured while building this basis).
    #
    # The two are told apart by which axis dominates: a quote is wholly
    # somebody else's words (attribution -1), an observation is wholly a
    # particular event (register -1). Written with both at -1 they came out
    # *identical*, and two of the doctrine's seven frames collapsed into one —
    # found by the round-trip test, not by reading the table.
    "direct_quote": {"veridicality": 1.0, "attribution": -1.0, "register": -0.5},
    # Two accounts stand, the substrate holds both (Non-Negotiable 2).
    "disputed": {"veridicality": 1.0, "standing": -1.0},
    # Once held, since overtaken (Non-Negotiable 3).
    "superseded": {"veridicality": 1.0, "time": -1.0, "force": -1.0},
    # Nothing is claimed: an entity, a source anchor, a container. The zero
    # vector, which `frame_consistency` treats as neutral rather than opposed.
    "neutral": {},
}

STANCES: tuple[str, ...] = tuple(STANCE_PROFILES)

# What Kadmos is allowed to emit, and what an unrecognised value falls back to.
# A model that invents "uncertain" should not poison a frame with a hash or an
# exception; it should land on the stance that claims least.
DEFAULT_STANCE = "current_claim"
UNKNOWN_STANCE = "current_claim"

# Synonyms worth honouring rather than discarding — the same tolerance
# `reading_schemas.normalize_reading_payload` applies to field names.
_STANCE_ALIASES: Mapping[str, str] = {
    "asserted": "current_claim",
    "assertion": "current_claim",
    "claim": "current_claim",
    "fact": "current_claim",
    "statement": "current_claim",
    "definitional": "definition",
    "historical": "historical_claim",
    "history": "historical_claim",
    "past_claim": "historical_claim",
    "refuted": "refuted_claim",
    "refutation": "refuted_claim",
    "negated": "refuted_claim",
    "denial": "refuted_claim",
    "denied": "refuted_claim",
    "hypothetical": "hypothesis",
    "supposition": "hypothesis",
    "conjecture": "hypothesis",
    "speculation": "hypothesis",
    "observed": "observation",
    "report": "observation",
    "reported": "observation",
    "quote": "direct_quote",
    "quotation": "direct_quote",
    "speech": "direct_quote",
    "contested": "disputed",
    "variant": "disputed",
    "alternative": "disputed",
    "conflicting": "disputed",
    "obsolete": "superseded",
    "replaced": "superseded",
    "overtaken": "superseded",
    "none": "neutral",
    "entity": "neutral",
}


def normalise_stance(value: str | None) -> str:
    """Map whatever the model said onto a stance this module knows."""
    if not value:
        return DEFAULT_STANCE
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    if key in STANCE_PROFILES:
        return key
    return _STANCE_ALIASES.get(key, UNKNOWN_STANCE)


def axis_profile(stances: Sequence[str]) -> dict[str, float]:
    """Mean axis coordinates over one or more stances.

    A query usually *seeks* several frames at once — `MESH_RETRIEVAL`'s table
    pairs "definition + current claim" for a what-is question and "historical
    claim + refuted claim" for a what-did-they-think question — so a profile is
    an average of points, not a single point.
    """
    profile: dict[str, float] = {}
    resolved = [normalise_stance(s) for s in stances] or [DEFAULT_STANCE]
    for stance in resolved:
        for axis, value in STANCE_PROFILES[stance].items():
            profile[axis] = profile.get(axis, 0.0) + value
    return {axis: value / len(resolved) for axis, value in profile.items()}


def frame_vector(
    *stances: str,
    dim: int = DEFAULT_FRAME_DIM,
    axes: Mapping[str, float] | None = None,
) -> list[float]:
    """The unit frame vector for these stances, weighted by axis.

    `axes` overrides or extends the stance profile for callers that know an
    axis directly (a `supersedes` edge setting `force = -1` without naming a
    stance). An all-zero profile stays the zero vector: neutral, never opposed.
    """
    profile = dict(axis_profile(list(stances))) if stances else {}
    if axes:
        profile.update(axes)
    values = [0.0] * max(dim, 0)
    if dim <= 0:
        return values
    for axis in FRAME_AXES:
        idx = AXIS_INDEX[axis.name]
        if idx >= dim:
            break
        values[idx] = profile.get(axis.name, 0.0) * axis.weight
    norm = sum(v * v for v in values) ** 0.5
    if norm == 0.0:
        return values
    return [v / norm for v in values]


NEUTRAL_STANCE = "neutral"


def neutral_frame(dim: int = DEFAULT_FRAME_DIM) -> list[float]:
    """The frame of something that makes no claim — an entity, a source anchor."""
    return [0.0] * max(dim, 0)


def frame_cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine between two frames; 1.0 when either is neutral (the zero vector).

    Mirrors `retrieval.frame_routing.frame_consistency`'s neutrality rule so
    that ingestion-time `frame_consistency` and retrieval-time routing agree
    about what an absent stance means.
    """
    n = min(len(left), len(right))
    if n == 0:
        return 1.0
    dot = sum(float(left[i]) * float(right[i]) for i in range(n))
    ln = sum(float(left[i]) ** 2 for i in range(n)) ** 0.5
    rn = sum(float(right[i]) ** 2 for i in range(n)) ** 0.5
    if ln < 1e-12 or rn < 1e-12:
        return 1.0
    return float(dot / (ln * rn))


def describe_stance(stance: str) -> str:
    """One line naming the axes a stance sets — for audits and `mesh status`."""
    resolved = normalise_stance(stance)
    profile = STANCE_PROFILES[resolved]
    if not profile:
        return f"{resolved}: no epistemic commitment"
    parts = []
    for axis in FRAME_AXES:
        value = profile.get(axis.name)
        if value:
            parts.append(axis.positive if value > 0 else axis.negative)
    return f"{resolved}: {', '.join(parts)}"


# Query-side profiles, from `MESH_RETRIEVAL` §"Frame routing during Spreading
# Activation". A caller asking "what is X" wants definitions and current
# claims; one asking what was once believed wants the historical and the
# refuted.
#
# `contradiction` is the profile that seeks the *unsettled* — the query Argus
# and the Chronik need and that nothing could express before (PHX-1107). It is
# written in axes rather than stances on purpose: built from stances it
# inherits their positive veridicality, which then dominates (weight 2.0) and
# admits every plain claim while attenuating the refuted one to zero — the
# opposite of what it is for. Stated as "contested or overtaken, and silent
# about whether it is true", it attenuates settled current claims to zero and
# admits disputed, superseded and refuted alike.
QUERY_PROFILES: Mapping[str, tuple[tuple[str, ...], Mapping[str, float]]] = {
    "what_is": (("definition", "current_claim"), {}),
    "what_was_believed": (("historical_claim", "refuted_claim"), {}),
    "evidence": (("observation", "direct_quote"), {}),
    "contradiction": ((), {"standing": -1.0, "force": -1.0}),
    "any": ((), {}),
}


def query_frame(profile: str, *, dim: int = DEFAULT_FRAME_DIM) -> list[float]:
    """The frame vector a named query profile routes with. `any` is neutral."""
    entry = QUERY_PROFILES.get(profile)
    if entry is None:
        raise ValueError(f"unknown query profile {profile!r}; choose from {sorted(QUERY_PROFILES)}")
    stances, axes = entry
    if not stances and not axes:
        return neutral_frame(dim)
    return frame_vector(*stances, dim=dim, axes=dict(axes) if axes else None)


def stance_of_relation(relation_kind: str | None, descriptor: str | None) -> str:
    """The stance an edge carries, from what the relation says it is.

    `contradicts` and `supersedes` are the two the substrate could not express
    before; they are the reason this function exists rather than every edge
    inheriting its source node's frame.
    """
    kind = (relation_kind or "").strip().lower()
    desc = (descriptor or "").strip().lower()
    if kind in _RELATION_STANCES:
        return _RELATION_STANCES[kind]
    if desc in _RELATION_STANCES:
        return _RELATION_STANCES[desc]
    return DEFAULT_STANCE


_RELATION_STANCES: Mapping[str, str] = {
    "contradicts": "disputed",
    "contradicted_by": "disputed",
    "supersedes": "superseded",
    "superseded_by": "superseded",
    "disputes": "disputed",
    "hypothesis": "hypothesis",
    "quotes": "direct_quote",
}

# The relation kinds the substrate gained with PHX-1107. `contradicts` is
# symmetric in meaning but stored directed, like every other edge; `supersedes`
# is inherently directed and carries the arrow of time that
# PANTHEON_VISION's Non-Negotiable 3 asks for.
CONTRADICTION_KINDS: tuple[str, ...] = ("contradicts", "supersedes")


def is_contradiction_kind(relation_kind: str | None) -> bool:
    return (relation_kind or "").strip().lower() in CONTRADICTION_KINDS


def stances_in(values: Iterable[str | None]) -> dict[str, int]:
    """Histogram of stances, for reporting what a read actually produced."""
    counts: dict[str, int] = {}
    for value in values:
        stance = normalise_stance(value)
        counts[stance] = counts.get(stance, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
