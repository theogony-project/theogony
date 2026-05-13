"""Eager-linking uniqueness test — same Q-ID produces one Tier-1 node."""

from __future__ import annotations

from datetime import UTC, datetime

from theogony.mesh.ingestion.kadmos_v2 import MeshIngestionPipeline
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def test_same_qid_links_to_existing_node(mesh_runtime: MeshRuntime) -> None:
    """Two sentences with the same Q-ID reference create one Tier-1 node; the
    second chunk's reference edge attaches to the existing node (signal: qid).
    """
    pipeline = MeshIngestionPipeline(mesh_runtime)
    text = "Thomas Addison was an English physician. He discovered a disease."
    qid_ref = {
        "qids": [{"qid": "Q336997", "confidence": 0.95, "attached_at": datetime.now(UTC)}],
        "label": "Thomas Addison",
        "tags": ["physician"],
        "semantic_vector": [0.1] * 8,
    }
    entities = [[qid_ref], [qid_ref]]
    result = pipeline.ingest(
        text=text,
        entities=entities,
        source_type="test",
        source_identifier="qid-unique",
        title="Uniqueness Test",
    )
    # 2 chunks, 4 edges: 2 SA + 2 entity, but only 1 entity node created (second links)
    assert result["chunks"] == 2
    assert result["edges"] == 4

    # Exactly 1 Q-ID-bearing consolidated node + 1 source-anchor = 2
    consolidated_count = mesh_runtime.nodes.consolidated_count()
    # We expect: 1 source-anchor + 1 entity (the Q-ID-bearing one)
    # The second reference links to the existing node, not creating a new one.
    # But source_anchor is also consolidated, so:
    assert consolidated_count == 2, f"Expected 2 consolidated nodes, got {consolidated_count}"
