"""Integration test: Gutenberg book ingestion into the MESH substrate.

Requires network access (Gutendex API + Gutenberg content download).
"""

from __future__ import annotations

import pytest

from theogony.mesh.ingestion.kadmos_v2 import MeshIngestionPipeline
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


@pytest.mark.asyncio
@pytest.mark.live_gutenberg
async def test_gutenberg_43497_with_100_sentences(mesh_runtime: MeshRuntime) -> None:
    """Ingest 100 sentences from Sven Hedin's Trans-Himalaya.

    Verifies the S2 DoD: >100 Tier-0 chunks, >20 Tier-1 nodes.
    """
    pipeline = MeshIngestionPipeline(mesh_runtime)
    result = await pipeline.ingest_gutenberg("43497", max_sentences=100)

    assert result["chunks"] == 100
    assert result["ner_mentions"] > 50
    assert result["verdict"] == "good"
    assert result["report_run_id"] is not None

    chunks = mesh_runtime.nodes.chunk_count()
    consolidated = mesh_runtime.nodes.consolidated_count()
    edges = mesh_runtime.edges.count_rows()

    assert chunks >= 100
    assert consolidated > 20, f"Need >20 Tier-1 nodes, got {consolidated}"
    assert edges >= chunks  # at least one edge per chunk
