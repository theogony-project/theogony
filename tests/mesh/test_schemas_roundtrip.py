"""JSON round-trip and ``extra="forbid"`` enforcement for every schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from ulid import ULID

from theogony.mesh.schemas import (
    ChunkNode,
    ConsolidatedNode,
    Edge,
    EdgeMetadata,
    PIDTag,
    QIDTag,
    SourceProvenance,
)


def test_chunk_node_roundtrip() -> None:
    now = datetime.now(UTC)
    src = SourceProvenance(source_type="test", source_identifier="fixture-1", extracted_at=now)
    n = ChunkNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * 8,
        frame_vector=[0.2] * 4,
        source=src,
        raw_text_ref="blob://chunk/1",
    )
    data = n.model_dump(mode="json")
    restored = ChunkNode.model_validate(data)
    assert restored == n
    assert isinstance(restored.id, ULID)
    assert str(restored.id) == str(n.id)


def test_consolidated_node_roundtrip() -> None:
    now = datetime.now(UTC)
    n = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.0] * 8,
        frame_vector=[0.0] * 4,
        description="test entity",
        tags=["chemistry", "19th-century"],
    )
    data = n.model_dump(mode="json")
    restored = ConsolidatedNode.model_validate(data)
    assert restored == n


def test_edge_roundtrip() -> None:
    now = datetime.now(UTC)
    e = Edge(
        source_id=ULID(),
        target_id=ULID(),
        weight=0.75,
        born_at=now,
        last_fired_at=now,
        relation_descriptor="born_in",
        relation_kind="attribute",
        creation_context="kadmos_extraction",
    )
    restored = Edge.model_validate_json(e.model_dump_json())
    assert restored == e
    assert isinstance(restored.source_id, ULID)


def test_edge_metadata_roundtrip() -> None:
    m = EdgeMetadata(
        source_id=ULID(),
        target_id=ULID(),
        relation_kind="extraction",
        creation_context="kadmos_extraction",
    )
    restored = EdgeMetadata.model_validate_json(m.model_dump_json())
    assert restored == m


def test_qid_pid_roundrip() -> None:
    now = datetime.now(UTC)
    q = QIDTag(qid="Q336997", confidence=0.95, attached_at=now)
    p = PIDTag(pid="P19", confidence=0.90, attached_at=now)

    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.0] * 8,
        frame_vector=[0.0] * 4,
        qids=[q],
    )
    back = ConsolidatedNode.model_validate_json(node.model_dump_json())
    assert back.qids[0].qid == "Q336997"

    edge = Edge(
        source_id=ULID(),
        target_id=ULID(),
        weight=1.0,
        born_at=now,
        last_fired_at=now,
        pids=[p],
    )
    recovered = Edge.model_validate_json(edge.model_dump_json())
    assert recovered.pids[0].pid == "P19"


def test_extra_forbid() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        Edge.model_validate(
            {
                "source_id": str(ULID()),
                "target_id": str(ULID()),
                "weight": 1.0,
                "born_at": now,
                "last_fired_at": now,
                "bogus_field": 42,
            }
        )

    with pytest.raises(ValidationError):
        ChunkNode.model_validate(
            {
                "id": str(ULID()),
                "born_at": now,
                "last_fired_at": now,
                "semantic_vector": [0.0] * 8,
                "frame_vector": [0.0] * 4,
                "source": {
                    "source_type": "x",
                    "source_identifier": "y",
                    "extracted_at": now,
                    "extra": True,
                },
                "raw_text_ref": "ref",
            }
        )
