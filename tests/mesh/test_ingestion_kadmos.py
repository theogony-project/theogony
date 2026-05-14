"""Small Wikipedia paragraph → expected chunks + concepts + relations via StubLLM."""

from __future__ import annotations

import json

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

_STUB_CONCEPTS = json.dumps(
    [
        {
            "label": "Thomas Addison",
            "entity_type": "person",
            "tags": ["physician", "19th-century"],
            "description": "English physician who discovered Addison's disease",
        }
    ]
)


_STUB_RESPONSE_1 = json.dumps(
    {
        "concepts": json.loads(_STUB_CONCEPTS),
        "relations": [],
        "synthesis": None,
    }
)


def test_paragraph_reader_basic(mesh_runtime: MeshRuntime) -> None:
    """One paragraph → one chunk, one concept, one edge to source-anchor."""
    llm = StubLLMProvider(
        responses={
            "PARAGRAPH:\nThomas Addison": _STUB_RESPONSE_1,
        },
    )
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=10)
    import asyncio

    result = asyncio.run(
        reader.read_text(
            text="Thomas Addison was an English physician.",
            source_type="test",
            source_identifier="fixture-1",
            title="Addison Test",
        )
    )
    assert result["concepts"] >= 1
    assert result["relations"] == 0
    assert result["llm_calls"] == 1
    assert mesh_runtime.nodes.chunk_count() >= 1
    assert mesh_runtime.nodes.consolidated_count() >= 2  # SA + concept
