"""Schema JSON round-trip and ``extra`` forbid."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
    src = SourceProvenance(
        source_type="test",
        source_identifier="fixture-1",
        extracted_at=now,
    )
    n = ChunkNode(
        id="01HZX8QZ7QZ7QZ7QZ7QZ7QZ7Q",
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


def test_edge_metadata_roundtrip() -> None:
    m = EdgeMetadata(
        source_id="01HZX8QZ7QZ7QZ7QZ7QZ7QZ7Q",
        target_id="01HZX8QZ7QZ7QZ7QZ7QZ7QZR",
        relation_kind="extraction",
        creation_context="kadmos_extraction",
    )
    restored = EdgeMetadata.model_validate_json(m.model_dump_json())
    assert restored == m


def test_qid_on_consolidated_node_roundtrip() -> None:
    now = datetime.now(UTC)
    q = QIDTag(qid="Q336997", confidence=0.9, attached_at=now)
    node = ConsolidatedNode(
        id="01HZX8QZ7QZ7QZ7QZ7QZ7QZ7S",
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.0] * 8,
        frame_vector=[0.0] * 4,
        qids=[q],
    )
    back = ConsolidatedNode.model_validate_json(node.model_dump_json())
    assert back.qids[0].qid == "Q336997"


def test_pid_tag_on_edge_roundtrip() -> None:
    now = datetime.now(UTC)
    p = PIDTag(pid="P19", confidence=0.8, attached_at=now)
    e = Edge(
        source_id="a",
        target_id="b",
        weight=1.0,
        born_at=now,
        last_fired_at=now,
        pids=[p],
    )
    restored = Edge.model_validate_json(e.model_dump_json())
    assert restored.pids[0].pid == "P19"


def test_extra_forbid() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        Edge.model_validate(
            {
                "source_id": "a",
                "target_id": "b",
                "weight": 1.0,
                "born_at": now,
                "last_fired_at": now,
                "typo_field": 123,
            }
        )
