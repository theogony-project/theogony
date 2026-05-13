"""Kadmos v2 ingestion pipeline test — small paragraph in, chunks + entities out."""

from __future__ import annotations

from theogony.mesh.ingestion.kadmos_v2 import MeshIngestionPipeline
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def test_ingest_empty_text_produces_zero_chunks(mesh_runtime: MeshRuntime) -> None:
    pipeline = MeshIngestionPipeline(mesh_runtime)
    result = pipeline.ingest(text="")
    assert result["chunks"] == 0
    assert result["edges"] == 0
    assert result["source_anchor_id"] is not None


def test_ingest_paragraph_produces_chunks_and_edges(mesh_runtime: MeshRuntime) -> None:
    pipeline = MeshIngestionPipeline(mesh_runtime)
    text = "Thomas Addison was an English physician. He discovered Addison's disease in 1855."
    result = pipeline.ingest(
        text=text,
        source_type="test",
        source_identifier="fixture-1",
        title="Thomas Addison Test",
    )
    assert result["chunks"] == 2  # two sentences
    assert result["edges"] == 2  # both chunks → source-anchor
    assert mesh_runtime.nodes.chunk_count() == 2
    assert mesh_runtime.nodes.consolidated_count() >= 1  # source-anchor
    assert mesh_runtime.edges.count_rows() == 2


def test_ingest_with_entities_creates_entity_edges(mesh_runtime: MeshRuntime) -> None:
    """Entities attached to chunks produce additional edges via eager linking (emergent)."""
    pipeline = MeshIngestionPipeline(mesh_runtime)
    text = "Thomas Addison was an English physician."
    entities = [
        [
            {
                "label": "Thomas Addison",
                "tags": ["physician", "19th-century"],
                "semantic_vector": [0.1] * 8,
                "description_vector": [0.2] * 8,
            }
        ]
    ]
    result = pipeline.ingest(
        text=text,
        entities=entities,
        source_type="test",
        source_identifier="fixture-2",
        title="Thomas Addison Test",
    )
    # 1 chunk + 1 entity reference → source-anchor edge + entity edge = 2
    assert result["chunks"] == 1
    assert result["edges"] == 2
    assert mesh_runtime.nodes.consolidated_count() >= 2
