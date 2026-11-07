"""PHX-1120: the instrument that judges where the moved mentions went."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from theogony.mesh.runtime.oneiros_tick import MeshRuntime

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "mesh_mention_audit.py"
_spec = importlib.util.spec_from_file_location("mesh_mention_audit", _SCRIPT)
assert _spec is not None and _spec.loader is not None
audit = importlib.util.module_from_spec(_spec)
sys.modules["mesh_mention_audit"] = audit
_spec.loader.exec_module(audit)


def _node(name: str, description: str = "", revised: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        tags=[name, "place"],
        description=f"{name} — {description}" if description else name,
        description_source_chunks=["c1"] if revised else [],
    )


def test_the_verdict_is_the_first_word_whatever_wraps_it() -> None:
    assert audit.parse_verdict("same") == "same"
    assert audit.parse_verdict("**Different.**") == "different"
    assert audit.parse_verdict("  Unclear — the paragraph is short") == "unclear"
    assert audit.parse_verdict("I think they are the same") == "unparsed"
    assert audit.parse_verdict("") == "unparsed"


def test_two_verdicts_make_one_outcome() -> None:
    assert audit.outcome("different", "same") == "better"
    assert audit.outcome("same", "different") == "worse"
    assert audit.outcome("same", "same") == "both_same"
    assert audit.outcome("different", "different") == "both_different"
    assert audit.outcome("unclear", "same") == "unclear"
    assert audit.outcome("same", "unparsed") == "unclear"


def test_kappa_is_one_for_agreement_and_zero_for_chance() -> None:
    assert audit.kappa([("same", "same"), ("different", "different")]) == 1.0
    # raters who agree only as often as their marginals predict
    chance = [
        ("same", "same"),
        ("same", "different"),
        ("different", "same"),
        ("different", "different"),
    ]
    assert audit.kappa(chance) == pytest.approx(0.0)


def test_the_prompt_shows_one_candidate_and_never_the_build() -> None:
    item = {
        "title": "Gare de Montluçon-Ville",
        "text": "The station serves Montluçon, Allier, France.",
        "mention": {"label": "France", "description": "Country where the station is"},
        "a": {"name": "France", "description": "France — Country in Europe"},
        "b": {"name": "Rhône", "description": "Rhône — Department in France"},
    }
    prompt_a, prompt_b = audit.judge_prompt(item, "a"), audit.judge_prompt(item, "b")
    assert "NODE: France — France — Country in Europe" in prompt_a and "Rhône" not in prompt_a
    assert "NODE: Rhône" in prompt_b and "Country in Europe" not in prompt_b
    for prompt in (prompt_a, prompt_b):
        assert "build" not in prompt.lower() and "accrual" not in prompt.lower()


def test_a_mention_moves_when_its_nodes_name_differs_between_builds() -> None:
    nodes_a = {"n1": _node("France"), "n2": _node("Rhône")}
    nodes_b = {"m1": _node("France", revised=True), "m2": _node("Rhône", revised=True)}
    dec_a = {
        (1, "France", 0): {"node_id": "n1"},
        (2, "France", 0): {"node_id": "n1"},
        (3, "Lyon", 0): {"node_id": "gone"},
    }
    dec_b = {
        (1, "France", 0): {"node_id": "m1"},
        (2, "France", 0): {"node_id": "m2"},
        (3, "Lyon", 0): {"node_id": "m1"},
        (4, "Paris", 0): {"node_id": "m1"},
    }
    moved, stayed = audit.split_moves(dec_a, dec_b, nodes_a, nodes_b)
    assert moved == [(2, "France", 0)]
    assert stayed == [(1, "France", 0)]  # a missing node or a one-build mention is neither


def test_the_decisions_are_keyed_by_paragraph_label_and_occurrence(tmp_path: Path) -> None:
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    for node_id in ("n1", "n2", "n3"):
        runtime.audit.stage(
            action="mesh_ingest_link_decision",
            detail={"label": "Hedin", "node_id": node_id, "paragraph": 7, "signal": "tag"},
        )
    for before in (55, 30):
        runtime.audit.stage(
            action="mesh_ingest_description_revised",
            detail={"node_id": "n1", "chars_before": before, "paragraph": 7},
        )
    decisions, created_chars = audit._audit(runtime)
    assert sorted(decisions) == [(7, "Hedin", 0), (7, "Hedin", 1), (7, "Hedin", 2)]
    assert [decisions[(7, "Hedin", k)]["node_id"] for k in range(3)] == ["n1", "n2", "n3"]
    assert created_chars == {"n1": 30}, "the first revision's starting length"


def test_a_node_is_judged_on_the_description_it_was_created_with() -> None:
    node = SimpleNamespace(
        tags=["Rhône", "department"],
        description="Rhône — Department in France where Lyon is located. The country in which "
        "the Allier department is located.",
        description_source_chunks=["c1"],
    )
    view = audit._node_view(node, len("Rhône — Department in France where Lyon is located."))
    assert view["description"] == "Rhône — Department in France where Lyon is located."
    assert view["accrued_description"].endswith("Allier department is located.")
    assert audit._node_view(node)["description"] == node.description  # unrevised: as stored


def test_a_blind_batch_never_holds_both_candidates_of_one_mention() -> None:
    items = [
        {
            "id": f"p{k}:0:X",
            "group": "moved" if k % 2 else "control",
            "title": "T",
            "text": "x",
            "mention": {"label": "X", "description": ""},
            "a": {"name": "A", "description": "A — a"},
            "b": {"name": "B", "description": "B — b"},
        }
        for k in range(30)
    ]
    batches = audit.blind_batches(items, size=7, seed=1120)
    units = [u["unit_id"] for batch in batches for u in batch]
    assert len(units) == len(set(units)) == 15 * 2 + 15
    for batch in batches:
        mentions = [u["unit_id"].rsplit("|", 1)[0] for u in batch]
        assert len(mentions) == len(set(mentions))
        assert len({u["unit_id"].rsplit("|", 1)[1] for u in batch}) == 1, "one side per batch"
    assert audit.blind_batches(items, size=7, seed=1120) == batches, "seeded"
