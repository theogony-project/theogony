"""Dense paragraph-local graph writing via StubLLM."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

_PARAGRAPH_1 = json.dumps(
    {
        "concepts": [
            {
                "label": "Sven Hedin",
                "entity_type": "person",
                "tags": ["explorer", "geographer"],
                "description": "Swedish explorer known for expeditions in Central Asia",
                "qids": [{"qid": "Q44114", "confidence": 0.99}],
            },
            {
                "label": "Tibetan Plateau",
                "entity_type": "place",
                "tags": ["plateau", "asia"],
                "description": "High plateau in Central Asia",
                "qids": [{"qid": "Q45973", "confidence": 0.98}],
            },
        ],
        "relations": [
            {
                "source": "Sven Hedin",
                "target": "Tibetan Plateau",
                "relation_descriptor": "crossed",
                "relation_kind": "semantic",
                "rationale": "The paragraph says Hedin crossed the plateau.",
            }
        ],
        "paragraph_concept": {
            "label": "Hedin's Tibetan exploration",
            "description": "The paragraph frames Sven Hedin as an explorer of the Tibetan Plateau.",
            "tags": ["exploration", "paragraph_concept"],
            "basis_concepts": ["Sven Hedin", "Tibetan Plateau"],
        },
    }
)

_PARAGRAPH_2 = json.dumps(
    {
        "concepts": [
            {
                "label": "Sven Hedin",
                "entity_type": "person",
                "tags": ["explorer", "geographer"],
                "description": "Swedish explorer known for expeditions in Central Asia",
                "qids": [{"qid": "Q44114", "confidence": 0.99}],
            },
            {
                "label": "Tibetan Plateau",
                "entity_type": "place",
                "tags": ["plateau", "asia"],
                "description": "High plateau in Central Asia",
                "qids": [{"qid": "Q45973", "confidence": 0.98}],
            },
            {
                "label": "Brahmaputra River",
                "entity_type": "place",
                "tags": ["river", "asia"],
                "description": "Major river flowing from the Tibetan Plateau",
                "qids": [],
            },
        ],
        "relations": [
            {
                "source": "Sven Hedin",
                "target": "Brahmaputra River",
                "relation_descriptor": "mapped",
                "relation_kind": "semantic",
                "rationale": "The paragraph says Hedin mapped river systems.",
            },
            {
                "source": "Brahmaputra River",
                "target": "Tibetan Plateau",
                "relation_descriptor": "originates_on",
                "relation_kind": "attribute",
                "rationale": "The paragraph locates the river on the plateau.",
            },
        ],
        "paragraph_concept": {
            "label": "Hedin's hydrological discoveries",
            "description": "The paragraph connects Hedin's expedition with mapped river systems.",
            "tags": ["hydrology", "paragraph_concept"],
            "basis_concepts": ["Sven Hedin", "Brahmaputra River", "Tibetan Plateau"],
        },
    }
)

_PARAGRAPH_WITH_STRING_QIDS = json.dumps(
    {
        "concepts": [
            {
                "label": "Sven Hedin",
                "entity_type": "person",
                "tags": ["explorer"],
                "description": "Swedish explorer of Central Asia",
                "qids": ["Q44114"],
            },
            {
                "label": "Tibet",
                "entity_type": "place",
                "tags": ["region"],
                "description": "Region on the Tibetan Plateau",
                "qids": ["Q172"],
            },
        ],
        "relations": [
            {
                "source": "Sven Hedin",
                "target": "Tibet",
                "relation_descriptor": "travelled_in",
                "relation_kind": "semantic",
                "rationale": "The paragraph places Hedin in Tibet.",
            }
        ],
        "paragraph_concept": None,
    }
)


def test_paragraph_reader_builds_dense_connected_mesh(
    mesh_runtime: MeshRuntime,
    tmp_path: Path,
) -> None:
    llm = StubLLMProvider(
        responses={
            "PARAGRAPH:\nSven Hedin crossed the Tibetan Plateau.": _PARAGRAPH_1,
            (
                "PARAGRAPH:\nSven Hedin mapped the Brahmaputra River on the Tibetan Plateau."
            ): _PARAGRAPH_2,
        }
    )
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=10)

    result = asyncio.run(
        reader.read_text(
            text=(
                "Sven Hedin crossed the Tibetan Plateau.\n\n"
                "Sven Hedin mapped the Brahmaputra River on the Tibetan Plateau."
            ),
            source_type="test",
            source_identifier="fixture-1",
            title="Hedin Test",
            anchor=str(tmp_path / "hedin.txt"),
        )
    )
    descriptions = {
        node.description
        for node in mesh_runtime.nodes.load_all_consolidated()
        if node.description is not None
    }

    assert result["paragraphs"] == 2
    assert result["concepts"] == 5
    assert result["relations"] == 3
    assert result["paragraph_concepts"] == 2
    assert result["paragraph_concept_nodes"] >= 1
    assert result["paragraph_anchor_count"] == 2
    assert result["cross_paragraph_links"] >= 2
    assert result["connectivity"]["largest_connected_component_ratio"] >= 0.9
    assert Path(result["report_path"]).is_file()
    text_anchor_description = next(
        desc for desc in descriptions if desc is not None and desc.startswith("test: Hedin Test")
    )
    assert "test: Hedin Test (" in text_anchor_description
    assert any("paragraph 1" in (desc or "") for desc in descriptions)
    assert any("paragraph 2" in (desc or "") for desc in descriptions)


def test_paragraph_reader_accepts_string_qids(mesh_runtime: MeshRuntime) -> None:
    llm = StubLLMProvider(
        responses={
            "PARAGRAPH:\nSven Hedin travelled in Tibet.": _PARAGRAPH_WITH_STRING_QIDS,
        }
    )
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=10)

    result = asyncio.run(
        reader.read_text(
            text="Sven Hedin travelled in Tibet.",
            source_type="test",
            source_identifier="fixture-string-qids",
            title="String QIDs",
            anchor="fixture://string-qids",
        )
    )

    assert result["concepts"] == 2
    assert result["relations"] == 1
    assert result["paragraph_concept_nodes"] == 0
    qids = {qid.qid for node in mesh_runtime.nodes.load_all_consolidated() for qid in node.qids}
    assert {"Q44114", "Q172"} <= qids
