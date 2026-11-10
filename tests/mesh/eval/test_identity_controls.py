"""PHX-1122: the identity controls count where the paragraphs' concepts landed."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "mesh_identity_controls.py"
_spec = importlib.util.spec_from_file_location("mesh_identity_controls", _SCRIPT)
assert _spec is not None and _spec.loader is not None
controls = importlib.util.module_from_spec(_spec)
sys.modules["mesh_identity_controls"] = controls
_spec.loader.exec_module(controls)


def _edge(
    source: str,
    target: str,
    descriptor: str | None = "summarised_as",
    context: str = "kadmos_paragraph_concept",
) -> SimpleNamespace:
    return SimpleNamespace(
        source_id=source, target_id=target, relation_descriptor=descriptor, creation_context=context
    )


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
        _edge("c1", "goss", "mentions", "kadmos_mentions"),
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
        "paragraph_concept_nodes_an_entity_mention_links_onto": 0,
    }


def test_an_entity_node_holding_several_paragraphs_is_not_a_shared_paragraph_concept() -> None:
    nodes = {"goss": SimpleNamespace(tags=["Luke Goss", "actor"])}
    placed = controls.paragraph_concept_placement(nodes, [_edge("c1", "goss"), _edge("c2", "goss")])
    assert placed["on_an_entity_node"] == 2
    assert placed["shared_paragraph_concept_nodes"] == 0
    assert placed["largest_shared"] == 0


def test_a_paragraph_concept_node_an_entity_mention_links_onto_is_counted_beside_alone() -> None:
    # Under v2 an entity mention can land on a paragraph-concept node; the
    # concept is still alone among concepts, and the node is counted apart.
    nodes = {"career": SimpleNamespace(tags=["career", "paragraph_concept"])}
    edges = [
        _edge("c1", "career"),
        _edge("c2", "career", "mentions", "kadmos_mentions"),
    ]
    placed = controls.paragraph_concept_placement(nodes, edges)
    assert placed["alone_on_its_own_node"] == 1
    assert placed["paragraph_concept_nodes_an_entity_mention_links_onto"] == 1


_P1 = "Luke Goss played the drums in Bros."
_P2 = "Jackie Kong directed The Being."


def _reading(entity: str, concept: str) -> str:
    return json.dumps(
        {
            "concepts": [
                {
                    "qids": [],
                    "label": entity,
                    "entity_type": "person",
                    "tags": ["person"],
                    "description": f"{entity}, a person the paragraph is about",
                }
            ],
            "relations": [],
            "paragraph_concept": {
                "label": concept,
                "description": f"The paragraph is about {concept}.",
                "tags": [],
                "basis_concepts": [entity],
            },
        }
    )


def test_the_controls_read_the_placement_the_reader_writes(tmp_path: Path) -> None:
    """The count is tied to what MeshParagraphReader writes, not to a literal of
    this test: two paragraphs read by the shipped reader, each with a concept
    of its own, and the controls run on the workspace."""
    root = tmp_path / "mesh_ws"
    runtime = MeshRuntime(root, semantic_dim=8, frame_dim=4)
    responses = {
        f"PARAGRAPH:\n{_P1}": _reading("Luke Goss", "Luke Goss's career"),
        f"PARAGRAPH:\n{_P2}": _reading("Jackie Kong", "Jackie Kong's films"),
    }
    reader = MeshParagraphReader(runtime, llm=StubLLMProvider(responses=responses))
    asyncio.run(
        reader.read_text(
            text=f"{_P1}\n\n{_P2}",
            source_type="test",
            source_identifier="careers",
            title="Careers",
            anchor=str(tmp_path / "careers.txt"),
        )
    )
    out = controls.controls(root, None, tmp_path)
    placed = out["paragraph_concepts"]
    assert placed["paragraphs_with_a_concept"] == 2
    assert placed["alone_on_its_own_node"] == 2
    assert placed["on_a_node_not_in_the_store"] == 0
