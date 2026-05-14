"""Small Wikipedia paragraph → expected chunks + entities linked."""

from __future__ import annotations

from theogony.mesh.ingestion.kadmos_v2 import MeshIngestionPipeline
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def test_ingest_paragraph_chunks_and_entities(mesh_runtime: MeshRuntime) -> None:
    """Two sentences → 2 chunks, 0 NER-like entities, 2 edges to source-anchor."""
    pipeline = MeshIngestionPipeline(mesh_runtime)
    text = "Thomas Addison was an English physician. He discovered Addison's disease in 1855."
    result = pipeline.ingest(
        text=text,
        source_type="test",
        source_identifier="fixture-1",
        title="Thomas Addison Test",
    )
    assert result["chunks"] == 2
    assert result["edges"] == 2  # only source-anchor edges
    assert mesh_runtime.nodes.chunk_count() == 2
    assert mesh_runtime.nodes.consolidated_count() >= 1  # source-anchor


def test_ingest_with_entities_creates_entity_candidates(mesh_runtime: MeshRuntime) -> None:
    """Entities attached to chunks create emergent candidates."""
    pipeline = MeshIngestionPipeline(mesh_runtime)
    entities = [
        [
            {
                "label": "Thomas Addison",
                "tags": ["physician", "19th-century"],
                "semantic_vector": [0.1] * mesh_runtime.semantic_dim,
            }
        ]
    ]
    result = pipeline.ingest(
        text="Thomas Addison was an English physician.",
        entities=entities,
        source_type="test",
        source_identifier="fixture-2",
        title="Thomas Addison Test",
    )
    # 1 chunk + 1 SA edge + 1 entity edge
    assert result["chunks"] == 1
    assert result["edges"] == 2
    assert mesh_runtime.nodes.consolidated_count() >= 2  # SA + candidate


def test_empty_text_produces_zero_chunks(mesh_runtime: MeshRuntime) -> None:
    pipeline = MeshIngestionPipeline(mesh_runtime)
    result = pipeline.ingest(text="")
    assert result["chunks"] == 0
    assert result["edges"] == 0
