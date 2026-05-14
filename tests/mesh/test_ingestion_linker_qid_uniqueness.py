"""Q-ID uniqueness — same Q-ID creates one Tier-1 node, second link attaches."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.ingestion.kadmos_v2 import MeshIngestionPipeline
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, QIDTag


def test_same_qid_links_to_existing_node(mesh_runtime: MeshRuntime) -> None:
    """Pre-seed a Tier-1 node with Q-ID Q336997. Two chunks referencing it
    each should link to the existing node (signal: qid) without creating a
    second Q-ID-bearing node.
    """
    now = datetime.now(UTC)
    existing = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        semantic_vector=[0.1] * mesh_runtime.semantic_dim,
        frame_vector=[0.1] * mesh_runtime.frame_dim,
        description="Thomas Addison",
        tags=["physician"],
        qids=[QIDTag(qid="Q336997", confidence=0.95, attached_at=now)],
    )
    mesh_runtime.nodes.append_consolidated(existing)

    pipeline = MeshIngestionPipeline(mesh_runtime)
    qid_ref = {
        "qids": [{"qid": "Q336997", "confidence": 0.95, "attached_at": now.isoformat()}],
        "label": "Thomas Addison",
        "tags": ["physician"],
        "semantic_vector": [0.1] * mesh_runtime.semantic_dim,
    }
    entities = [[qid_ref], [qid_ref]]

    result = pipeline.ingest(
        text="Thomas Addison was an English physician. He discovered a disease.",
        entities=entities,
        source_type="test",
        source_identifier="qid-unique",
        title="Uniqueness Test",
    )
    assert result["chunks"] == 2
    assert result["edges"] == 4  # 2 SA + 2 entity edges

    # We should NOT have a second consolidated node with Q336997
    cons_rows = mesh_runtime.nodes.consolidated_table.search().limit(100).to_arrow().to_pylist()
    qid_count = 0
    for r in cons_rows:
        payload = ConsolidatedNode.model_validate_json(r["payload_json"])
        qid_count += sum(1 for q in payload.qids if q.qid == "Q336997")
    assert qid_count == 1, f"Expected 1 Q336997 node, found {qid_count}"
