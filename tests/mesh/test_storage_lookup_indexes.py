from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.schemas import ConsolidatedNode, QIDTag


def _node(*, qid: str, description: str, tags: list[str]) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        semantic_vector=[0.1] * 8,
        frame_vector=[0.0] * 4,
        description_vector=[0.1] * 8,
        description=description,
        tags=tags,
        qids=[QIDTag(qid=qid, confidence=1.0, attached_at=now)],
    )


def test_node_store_supports_qid_and_label_lookups(mesh_runtime) -> None:
    alice = _node(qid="Q1", description="Alice Example", tags=["explorer", "writer"])
    bob = _node(qid="Q2", description="Bob Example", tags=["scientist"])
    mesh_runtime.nodes.append_consolidated_many([alice, bob])

    by_qid = mesh_runtime.nodes.get_consolidated_by_qid("Q1")
    by_label = mesh_runtime.nodes.get_consolidated_by_label("Alice Example")
    by_tag = mesh_runtime.nodes.find_consolidated_by_labels(["scientist"], limit=4)

    assert by_qid is not None
    assert str(by_qid.id) == str(alice.id)
    assert by_label is not None
    assert str(by_label.id) == str(alice.id)
    assert [str(node.id) for node in by_tag] == [str(bob.id)]
