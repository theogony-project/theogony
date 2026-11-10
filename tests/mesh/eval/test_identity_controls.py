"""PHX-1122: the identity controls count where the paragraphs' concepts landed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "mesh_identity_controls.py"
_spec = importlib.util.spec_from_file_location("mesh_identity_controls", _SCRIPT)
assert _spec is not None and _spec.loader is not None
controls = importlib.util.module_from_spec(_spec)
sys.modules["mesh_identity_controls"] = controls
_spec.loader.exec_module(controls)


def _edge(source: str, target: str, descriptor: str = "summarised_as") -> SimpleNamespace:
    return SimpleNamespace(source_id=source, target_id=target, relation_descriptor=descriptor)


def test_a_paragraph_concept_is_placed_alone_shared_or_on_an_entity() -> None:
    nodes = {
        "career": SimpleNamespace(tags=["career", "paragraph_concept"]),
        "own": SimpleNamespace(tags=["film", "paragraph_concept"]),
        "goss": SimpleNamespace(tags=["Luke Goss", "actor"]),
    }
    edges = [
        # three paragraphs: two share the career node, one has a node of its own
        _edge("c1", "career"),
        _edge("c2", "career"),
        _edge("c3", "own"),
        # one paragraph's concept landed on an entity's node
        _edge("c4", "goss"),
        # one on a node the store no longer holds
        _edge("c5", "gone"),
        # other edges from the same chunks are not placements
        _edge("c1", "goss", "mentions"),
        _edge("c4", "career", None),
    ]
    placed = controls.paragraph_concept_placement(nodes, edges)
    assert placed == {
        "paragraphs_with_a_concept": 5,
        "alone_on_its_own_node": 1,
        "on_a_shared_paragraph_concept_node": 2,
        "on_an_entity_node": 1,
        "on_a_node_not_in_the_store": 1,
        "shared_paragraph_concept_nodes": 1,
        "largest_shared": 2,
    }


def test_an_entity_node_holding_several_paragraphs_is_not_a_shared_paragraph_concept() -> None:
    nodes = {"goss": SimpleNamespace(tags=["Luke Goss", "actor"])}
    placed = controls.paragraph_concept_placement(nodes, [_edge("c1", "goss"), _edge("c2", "goss")])
    assert placed["on_an_entity_node"] == 2
    assert placed["shared_paragraph_concept_nodes"] == 0
    assert placed["largest_shared"] == 0
