"""A Tier-1 node must carry the entity's name, not only its discriminators.

MESH_SUBSTRATE §"Tier-1+ — Consolidated Node" specifies `description` as "short
discriminating text — for entities: name + key discriminators". The reading
model returns those apart, and the write path used to keep only the second half.

Measured before this changed: 8 of 8 concepts lost their name on the way in. No
node in a 6,816-node Theogony mesh was called Cronus; three distinct nymphs all
read "A nymph whose name derives from a land over which she presides"; eight
separate nodes described Zeus as son of Cronos without any of them saying Zeus.
Identity matching, deduplication and name lookup were all running on text with
the name removed (PHX-1065).

These tests hold the two halves of the repair: the name reaches the description,
and it reaches the label index so the node can be found by it.
"""

from __future__ import annotations

import asyncio
import json

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import (
    MeshParagraphReader,
    _concept_tags,
    _entity_description,
)
from theogony.mesh.ingestion.reading_schemas import LLMConcept
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def test_the_name_leads_the_description() -> None:
    assert _entity_description("Zeus", "King of the gods") == "Zeus — King of the gods"


def test_a_description_that_already_leads_with_the_name_is_left_alone() -> None:
    """No doubling — and the head stays the name either way."""
    assert _entity_description("Zeus", "Zeus, king of the gods") == "Zeus, king of the gods"


def test_either_half_alone_still_yields_something_usable() -> None:
    assert _entity_description("Zeus", "") == "Zeus"
    assert _entity_description("", "King of the gods") == "King of the gods"
    assert _entity_description("  ", "  ") == ""


def test_the_name_is_the_first_tag() -> None:
    """The label index is built from description plus tags, so the name must be in one."""
    concept = LLMConcept(
        label="Zeus", entity_type="person", tags=["god", "olympian"], description="King"
    )
    assert _concept_tags(concept)[0] == "Zeus"


def test_a_nameless_concept_still_gets_a_tag() -> None:
    concept = LLMConcept(label="", entity_type="", tags=[], description="")
    assert _concept_tags(concept) == ["concept"]


def test_the_node_can_be_found_by_its_name(mesh_runtime: MeshRuntime) -> None:
    """The end the whole change exists for.

    Before this, `find_consolidated_by_labels("Zeus")` could only match a node
    whose description text happened to contain the word. On the real corpus that
    meant zero hits for Zeus, Cronos and Rhea in a passage about nothing else.
    """
    reading = json.dumps(
        {
            "concepts": [
                {
                    "label": "Zeus",
                    "entity_type": "person",
                    "tags": ["god"],
                    "description": "King of the gods, son of Cronos",
                    "qids": [],
                }
            ],
            "relations": [],
            "paragraph_concept": None,
        }
    )
    text = "Zeus ruled from Olympus."
    llm = StubLLMProvider(responses={f"PARAGRAPH:\n{text}": reading})
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=5)
    asyncio.run(
        reader.read_text(
            text=text,
            source_type="test",
            source_identifier="phx-1065",
            title="Name survival",
            anchor="fixture://phx-1065",
        )
    )

    found = mesh_runtime.nodes.find_consolidated_by_labels(["Zeus"], limit=10)

    assert found, "the entity is not findable by its own name"
    assert any((n.description or "").startswith("Zeus") for n in found)
