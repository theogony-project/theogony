"""The epistemic frame basis (PHX-1107).

What is pinned here is not the arithmetic but the *orderings* the doctrine
argues for. `MESH_RETRIEVAL` §"Frame-sensitive resonance" makes exactly one
falsifiable promise about frames — that a refuted claim and a current one are
far apart while their semantic vectors are not — and everything downstream
(frame routing, contradiction retrieval, the immune system's inputs) rests on
that ordering holding. A change to the axis weights that breaks it should fail
here rather than three tickets later on a benchmark.
"""

from __future__ import annotations

import pytest

from theogony.mesh.frames import (
    AXIS_INDEX,
    CONTRADICTION_KINDS,
    DEFAULT_FRAME_DIM,
    FRAME_AXES,
    QUERY_PROFILES,
    STANCE_PROFILES,
    STANCES,
    frame_cosine,
    frame_vector,
    is_contradiction_kind,
    neutral_frame,
    normalise_stance,
    query_frame,
    stance_of_relation,
    stances_in,
)
from theogony.mesh.retrieval.frame_routing import frame_consistency


def _cos(a: str, b: str) -> float:
    return frame_cosine(frame_vector(a), frame_vector(b))


def test_a_refuted_claim_is_opposed_to_the_current_one_it_refutes() -> None:
    """The one promise the doctrine makes about frames: 'Thyroxine is an
    oxindole derivative' and its refutation embed to nearly the same semantic
    point, so the frame has to carry the difference."""
    assert _cos("refuted_claim", "current_claim") < 0.0
    assert _cos("refuted_claim", "definition") < 0.0


def test_the_stances_order_themselves_the_way_the_doctrine_describes() -> None:
    """A definition is nearly a current claim; a historical claim is weighted
    down but present; a refuted one is gone (MESH_RETRIEVAL's worked example)."""
    assert _cos("definition", "current_claim") > 0.9
    assert 0.4 < _cos("historical_claim", "current_claim") < 0.8
    assert _cos("superseded", "current_claim") < _cos("historical_claim", "current_claim")
    assert _cos("refuted_claim", "current_claim") < _cos("superseded", "current_claim")


def test_a_quote_stays_retrievable_for_a_plain_question() -> None:
    """Found while building the basis: without positive veridicality a quote is
    orthogonal to every claim, so a what-is query attenuates it to zero — and
    the founding corpus is half direct speech."""
    assert _cos("direct_quote", "current_claim") > 0.5
    assert frame_consistency_of("direct_quote", "what_is") > 0.5


def frame_consistency_of(stance: str, profile: str) -> float:
    import torch

    frames = torch.tensor([frame_vector(stance)], dtype=torch.float32)
    return float(frame_consistency(frames, query_frame(profile))[0])


def test_the_contradiction_profile_admits_only_the_unsettled() -> None:
    """Argus's brille. Everything settled attenuates to zero; disputed,
    superseded and refuted all survive — which is the whole point, since the
    two sides of a contradiction need not be a claim and its negation."""
    for settled in ("definition", "current_claim", "historical_claim", "observation"):
        assert frame_consistency_of(settled, "contradiction") == pytest.approx(0.0, abs=1e-6)
    for unsettled in ("disputed", "superseded", "refuted_claim"):
        assert frame_consistency_of(unsettled, "contradiction") > 0.2


def test_the_contradiction_profile_is_written_in_axes_not_stances() -> None:
    """Built from stances it would inherit their positive veridicality, which
    outweighs everything else and admits every plain claim. The regression this
    guards against is someone 'simplifying' it back into a stance list."""
    stances, axes = QUERY_PROFILES["contradiction"]
    assert not stances and axes
    assert query_frame("contradiction")[AXIS_INDEX["veridicality"]] == 0.0


def test_a_query_profile_mixes_stances_so_the_old_belief_is_findable() -> None:
    """Neither stance alone retrieves the Kendall chunk: the historical claim
    affirms what the refutation denies, so they oppose each other. The profile
    that finds it is the mixture."""
    assert _cos("historical_claim", "refuted_claim") < 0.0
    assert frame_consistency_of("refuted_claim", "what_was_believed") > 0.3
    assert frame_consistency_of("historical_claim", "what_was_believed") > 0.3
    assert frame_consistency_of("refuted_claim", "what_is") == pytest.approx(0.0, abs=1e-6)


def test_a_thing_that_makes_no_claim_is_never_suppressed() -> None:
    """Entities and source anchors hold no stance. A zero frame is neutral by
    construction, in this module and in the routing that reads it."""
    assert frame_cosine(neutral_frame(), query_frame("what_is")) == 1.0
    assert frame_consistency_of("neutral", "contradiction") == pytest.approx(1.0)
    assert frame_vector("neutral") == [0.0] * DEFAULT_FRAME_DIM


def test_every_frame_is_a_unit_vector_in_the_declared_dimension() -> None:
    for stance in STANCES:
        vec = frame_vector(stance)
        assert len(vec) == DEFAULT_FRAME_DIM
        norm = sum(v * v for v in vec) ** 0.5
        assert norm == pytest.approx(0.0 if stance == "neutral" else 1.0)
        # only the axis dimensions are occupied; the rest awaits a trained encoder
        assert all(v == 0.0 for v in vec[len(FRAME_AXES) :])


def test_the_axis_order_is_the_vector_layout() -> None:
    """Reordering FRAME_AXES would make meshes written before and after
    disagree about what dimension 3 means, silently."""
    assert [a.name for a in FRAME_AXES][0] == "veridicality"
    assert {a.name: i for i, a in enumerate(FRAME_AXES)} == AXIS_INDEX
    assert frame_vector("hypothesis")[AXIS_INDEX["modality"]] < 0.0
    assert frame_vector("superseded")[AXIS_INDEX["force"]] < 0.0
    assert frame_vector("disputed")[AXIS_INDEX["standing"]] < 0.0


def test_veridicality_outweighs_the_other_axes() -> None:
    """Negation is the failure mode the frame exists for; a stance that only
    disagrees about polarity must still read as opposed."""
    assert FRAME_AXES[0].weight > max(a.weight for a in FRAME_AXES[1:])
    plain = frame_vector(axes={"veridicality": 1.0, "time": 1.0, "modality": 1.0})
    negated = frame_vector(axes={"veridicality": -1.0, "time": 1.0, "modality": 1.0})
    assert frame_cosine(plain, negated) < 0.0


def test_what_the_model_says_is_mapped_onto_a_stance_it_knows() -> None:
    assert normalise_stance("REFUTED") == "refuted_claim"
    assert normalise_stance("Historical Claim") == "historical_claim"
    assert normalise_stance("contested") == "disputed"
    assert normalise_stance(None) == "current_claim"
    # an invented value lands on the stance that claims least, never raises
    assert normalise_stance("vaguely_true_ish") == "current_claim"
    assert normalise_stance("") == "current_claim"


def test_a_mixture_is_the_mean_of_its_points() -> None:
    mixed = frame_vector("definition", "current_claim")
    assert frame_cosine(mixed, frame_vector("definition")) > 0.9
    assert frame_cosine(mixed, frame_vector("current_claim")) > 0.9
    assert frame_vector("definition", "definition") == pytest.approx(frame_vector("definition"))


def test_the_two_new_relation_kinds_carry_their_stance() -> None:
    """`contradicts` and `supersedes` are what the substrate could not say
    before: ten relation kinds and none of them a disagreement (PHX-1107)."""
    assert CONTRADICTION_KINDS == ("contradicts", "supersedes")
    assert stance_of_relation("contradicts", None) == "disputed"
    assert stance_of_relation("supersedes", None) == "superseded"
    assert stance_of_relation(None, "contradicts") == "disputed"
    assert stance_of_relation("semantic", "father_of") == "current_claim"
    assert is_contradiction_kind("Contradicts")
    assert not is_contradiction_kind("semantic")
    assert not is_contradiction_kind(None)


def test_a_zero_dimension_field_degrades_rather_than_raising() -> None:
    assert frame_vector("definition", dim=0) == []
    assert frame_cosine([], []) == 1.0
    # a field narrower than the axis count keeps the axes that fit
    narrow = frame_vector("superseded", dim=3)
    assert len(narrow) == 3


def test_stances_in_counts_what_a_read_produced() -> None:
    assert stances_in(["definition", "refuted", None, "definition"]) == {
        "definition": 2,
        "current_claim": 1,
        "refuted_claim": 1,
    }


def test_every_stance_profile_names_a_real_axis() -> None:
    known = set(AXIS_INDEX)
    for stance, profile in STANCE_PROFILES.items():
        unknown = set(profile) - known
        assert not unknown, f"{stance} sets unknown axes {unknown}"
        assert all(-1.0 <= v <= 1.0 for v in profile.values())
