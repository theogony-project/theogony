"""Q-ID uniqueness — same Q-ID creates one Tier-1 node across paragraphs."""

from __future__ import annotations

import asyncio
import json

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def test_same_qid_creates_one_tier1_node(mesh_runtime: MeshRuntime) -> None:
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

    qid_nodes = [
        node
        for node in mesh_runtime.nodes.load_all_consolidated()
        if any(qid.qid == "Q336997" for qid in node.qids)
    ]
    assert len(qid_nodes) == 1
