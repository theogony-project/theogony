"""Kadmos v2 ingestion pipeline test — real components with mocked fixture dims."""

from __future__ import annotations

import pytest

from theogony.mesh.ingestion.kadmos_v2 import MeshIngestionPipeline
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


@pytest.mark.asyncio
async def test_ingest_empty_text_produces_zero_chunks(mesh_runtime: MeshRuntime) -> None:
    pipeline = MeshIngestionPipeline(mesh_runtime)
    result = await pipeline.ingest_sentences(sentences=[])
    assert result["chunks"] == 0
    assert result["edges"] == 0
    assert result["source_anchor_id"] is not None


@pytest.mark.asyncio
async def test_ingest_paragraph_produces_chunks_and_edges(mesh_runtime: MeshRuntime) -> None:
    pipeline = MeshIngestionPipeline(mesh_runtime)
    text = "Thomas Addison was an English physician. He discovered Addison's disease in 1855."
    result = await pipeline.ingest_sentences(
        sentences=[s.strip() for s in text.split(".") if s.strip()],
        source_type="test",
        source_identifier="fixture-1",
        title="Thomas Addison Test",
    )
    assert result["chunks"] == 2  # two sentences
    assert result["edges"] >= 2  # at least source-anchor edges
    assert mesh_runtime.nodes.chunk_count() == 2
    assert mesh_runtime.nodes.consolidated_count() >= 1  # source-anchor
    assert mesh_runtime.edges.count_rows() >= 2


@pytest.mark.asyncio
async def test_ingest_with_entities_creates_entity_edges(mesh_runtime: MeshRuntime) -> None:
    """Entities attached to chunks produce additional edges via eager linking (emergent)."""
    pipeline = MeshIngestionPipeline(mesh_runtime)
    text = "Thomas Addison was an English physician."
    result = await pipeline.ingest_sentences(
        sentences=[text],
        source_type="test",
        source_identifier="fixture-2",
        title="Thomas Addison Test",
    )
    # With real NER, "Thomas Addison" is recognized as PERSON → edge created
    assert result["chunks"] == 1
    assert result["edges"] >= 2  # source-anchor edge + at least one entity edge (if NER fires)
    assert mesh_runtime.nodes.consolidated_count() >= 2  # source-anchor + entity candidate(s)
