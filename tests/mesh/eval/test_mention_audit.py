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


def test_a_mention_that_moved_to_another_node_of_its_name_is_found_by_the_minting_mention() -> None:
    """*Paris* the city on *Paris* the prince (PHX-1120): one name, two nodes, so a
    join on names cannot see the move; the mention that minted each node can."""
    dec_a = {
        (173, "Paris", 0): {"node_id": "prince", "signal": "emergent"},
        (293, "Paris", 0): {"node_id": "prince", "signal": "description"},
        (511, "Paris", 0): {"node_id": "city", "signal": "emergent"},
        (520, "Paris", 0): {"node_id": "city", "signal": "description"},
        (600, "Hedin", 0): {"node_id": "pc-node", "signal": "description"},
    }
    dec_b = {
        (173, "Paris", 0): {"node_id": "prince2", "signal": "emergent"},
        (293, "Paris", 0): {"node_id": "prince2", "signal": "description"},
        (511, "Paris", 0): {"node_id": "prince2", "signal": "description"},
        (520, "Paris", 0): {"node_id": "city2", "signal": "emergent"},
        (600, "Hedin", 0): {"node_id": "pc-node2", "signal": "description"},
    }
    assert audit.minted_by(dec_a) == {"prince": (173, "Paris", 0), "city": (511, "Paris", 0)}
    moved, still, unknown = audit.split_same_name(sorted(dec_a), dec_a, dec_b)
    # 511 left the city's node (minted by 511) for the prince's (minted by 173);
    # 520 left it for a node it minted itself
    assert moved == [(511, "Paris", 0), (520, "Paris", 0)]
    assert still == [(173, "Paris", 0), (293, "Paris", 0), (600, "Hedin", 0)]
    assert unknown == 1, "a node no link decision minted cannot be matched"


def _judged(item_id: str, a: str, b: str | None = None) -> dict:
    rows = {(item_id, "a"): {"verdict": a, "model": "m"}}
    if b is not None:
        rows[(item_id, "b")] = {"verdict": b, "model": "m"}
    return rows


def test_moves_by_name_and_to_a_namesake_are_reported_apart_and_together() -> None:
    items = [
        {
            "id": "m1",
            "group": "moved",
            "a": {"signal": "tag"},
            "b": {"signal": "description", "revised": False},
        },
        {
            "id": "m2",
            "group": "moved",
            "a": {"signal": "tag"},
            "b": {"signal": "description", "revised": False},
        },
        {
            "id": "s1",
            "group": "moved_same_name",
            "a": {"signal": "emergent"},
            "b": {"signal": "description", "revised": True},
        },
        {"id": "c1", "group": "control", "a": {"signal": "tag"}, "b": {"signal": "tag"}},
    ]
    assert audit.judged_sides(items[2]) == ("a", "b") and audit.judged_sides(items[3]) == ("a",)
    verdicts = {
        **_judged("m1", "same", "different"),
        **_judged("m2", "different", "same"),
        **_judged("s1", "same", "different"),
        **_judged("c1", "same"),
    }
    one = audit.summarise_one(items, verdicts)
    assert one["outcomes"] == {"worse": 1, "better": 1}, "the by-name moves as before"
    assert one["same_name_outcomes"] == {"worse": 1}
    assert one["all_moves_outcomes"] == {"worse": 2, "better": 1}
    assert one["control_verdicts"] == {"same": 1}


def test_the_control_sample_is_drawn_without_the_same_name_moves() -> None:
    nodes_a = {"city": _node("Paris"), "prince": _node("Paris")}
    nodes_b = {"city2": _node("Paris"), "prince2": _node("Paris")}
    dec_a = {
        (173, "Paris", 0): {"node_id": "prince", "signal": "emergent"},
        (511, "Paris", 0): {"node_id": "city", "signal": "emergent"},
        (520, "Paris", 0): {"node_id": "city", "signal": "description"},
    }
    dec_b = {
        (173, "Paris", 0): {"node_id": "prince2", "signal": "emergent"},
        (511, "Paris", 0): {"node_id": "prince2", "signal": "description"},
        (520, "Paris", 0): {"node_id": "city2", "signal": "emergent"},
    }
    moved, same, control, stayed, _ = audit.select_mentions(
        dec_a, dec_b, nodes_a, nodes_b, same_name=True, control=400, seed=0
    )
    assert moved == [] and same == [(511, "Paris", 0), (520, "Paris", 0)]
    assert control == [(173, "Paris", 0)] and stayed == 1
    # without the flag, the PHX-1120 population: every mention that kept its name
    _, same, control, stayed, _ = audit.select_mentions(
        dec_a, dec_b, nodes_a, nodes_b, same_name=False, control=400, seed=0
    )
    assert same == [] and stayed == 3 and len(control) == 3


def test_two_judges_agree_on_same_name_moves_apart_and_with_the_others(tmp_path: Path) -> None:
    import json
    from argparse import Namespace

    items = [
        {
            "id": "m1",
            "group": "moved",
            "a": {"signal": "tag"},
            "b": {"signal": "description", "revised": False},
        },
        {
            "id": "s1",
            "group": "moved_same_name",
            "a": {"signal": "emergent"},
            "b": {"signal": "description", "revised": True},
        },
        {
            "id": "s2",
            "group": "moved_same_name",
            "a": {"signal": "emergent"},
            "b": {"signal": "description", "revised": True},
        },
        {"id": "c1", "group": "control", "a": {"signal": "tag"}, "b": {"signal": "tag"}},
    ]
    first = {
        ("m1", "a"): "same",
        ("m1", "b"): "different",
        ("s1", "a"): "same",
        ("s1", "b"): "different",
        ("s2", "a"): "different",
        ("s2", "b"): "same",
        ("c1", "a"): "same",
    }
    second = dict(first)
    second[("s2", "a")] = "same"  # the judges disagree on s2: it counts for neither
    paths = {}
    for name, rows in (("items", items), ("first", first), ("second", second)):
        path = tmp_path / f"{name}.jsonl"
        if name == "items":
            path.write_text("".join(json.dumps(i) + "\n" for i in rows))
        else:
            path.write_text(
                "".join(
                    json.dumps({"item_id": k[0], "side": k[1], "verdict": v}) + "\n"
                    for k, v in rows.items()
                )
            )
        paths[name] = path
    out = tmp_path / "summary.json"
    audit.summarise(
        Namespace(items=paths["items"], judgments=paths["first"], second=paths["second"], json=out)
    )
    summary = json.loads(out.read_text())
    assert summary["agreed_outcomes"] == {"worse": 1}
    assert summary["agreed_outcomes_same_name"] == {"worse": 1}
    assert summary["agreed_outcomes_all_moves"] == {"worse": 2}
