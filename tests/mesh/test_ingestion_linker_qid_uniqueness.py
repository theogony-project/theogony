"""One node per entity across paragraphs — without trusting the model's Q-ID.

The same figure mentioned in two paragraphs must end up as one node. It used to
be the asserted Q-ID that made that happen; it no longer is. Model-asserted
Q-IDs are refused as identity evidence (3 of 130 correct on the founding mesh —
PHX-1063), so the merge has to hold on corroborated signal, which is what this
test now pins down. If it ever fails, deduplication has genuinely regressed
rather than merely lost a shortcut.
"""

from __future__ import annotations

import asyncio
import json

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def test_one_node_per_entity_across_paragraphs(mesh_runtime: MeshRuntime) -> None:
    response = json.dumps(
        {
            "concepts": [
                {
                    "label": "Thomas Addison",
                    "entity_type": "person",
                    "tags": ["physician"],
                    "description": "English physician who described Addison's disease",
                    "qids": [{"qid": "Q336997", "confidence": 0.98}],
                }
            ],
            "relations": [],
            "paragraph_concept": None,
        }
    )
    llm = StubLLMProvider(
        responses={
            "PARAGRAPH:\nThomas Addison was an English physician.": response,
            "PARAGRAPH:\nAddison studied disease in London.": response,
        }
    )
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=10)

    asyncio.run(
        reader.read_text(
            text=("Thomas Addison was an English physician.\n\nAddison studied disease in London."),
            source_type="test",
            source_identifier="qid-unique",
            title="QID Uniqueness",
            anchor="fixture://qid-unique",
        )
    )

    addison = [
        node
        for node in mesh_runtime.nodes.load_all_consolidated()
        if "Addison" in (node.description or "")
    ]
    assert len(addison) == 1, "the same figure in two paragraphs must be one node"
    # And the guess itself was not written into the substrate.
    stored = {qid.qid for node in mesh_runtime.nodes.load_all_consolidated() for qid in node.qids}
    assert "Q336997" not in stored
