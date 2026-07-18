"""PHX-1053: identity evidence acquired at merge time must survive the process.

Measured live: Aphrodite (Q35500) merged into an existing hymn concept via the
label signal, `remember()` recorded the Q-ID only in the in-process registry,
and the founding mesh ended the ingest with no Q35500 anywhere. A merge that
brings new Q-IDs now writes them back to the stored node and the Q-ID index.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, QIDTag


def _node(description: str, vec: list[float], tags: list[str]) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description=description,
        description_vector=vec,
        tags=tags,
    )


def test_store_merge_identity_evidence_persists_new_qids(tmp_path: Path) -> None:
    rt = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    node = _node("Goddess of love in a hymn.", [1.0] + [0.0] * 7, ["aphrodite"])
    rt.nodes.append_consolidated(node)

    updated = rt.nodes.merge_identity_evidence(
        str(node.id), qids=[QIDTag(qid="Q35500", confidence=0.9, attached_at=datetime.now(UTC))]
    )
    assert updated is not None
    assert any(q.qid == "Q35500" for q in updated.qids)
    # Durable: readable back from Lance, and Q-ID-addressable via the index.
    reloaded = rt.nodes.get_consolidated(str(node.id))
    assert reloaded is not None and any(q.qid == "Q35500" for q in reloaded.qids)
    assert rt.nodes.get_consolidated_id_by_qid("Q35500") == str(node.id)


def test_store_merge_is_idempotent_for_known_qids(tmp_path: Path) -> None:
    rt = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    node = _node("Ruler of the gods.", [0.0, 1.0] + [0.0] * 6, ["zeus"])
    node = node.model_copy(
        update={"qids": [QIDTag(qid="Q34201", confidence=1.0, attached_at=datetime.now(UTC))]}
    )
    rt.nodes.append_consolidated(node)

    updated = rt.nodes.merge_identity_evidence(
        str(node.id), qids=[QIDTag(qid="Q34201", confidence=0.5, attached_at=datetime.now(UTC))]
    )
    assert updated is not None
    assert [q.qid for q in updated.qids] == ["Q34201"]


def test_linker_merge_persists_incoming_qid(tmp_path: Path) -> None:
    """End-to-end through link_reference: a tag-corroborated merge carrying a
    new Q-ID leaves the stored node Q-ID-addressable afterwards."""
    rt = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    hymn_aphrodite = _node(
        "Goddess of love celebrated in the hymn.", [1.0, 0.1] + [0.0] * 6, ["aphrodite"]
    )
    rt.nodes.append_consolidated(hymn_aphrodite)
    linker = EagerLinker(rt.nodes, rt.edges, semantic_dim=8, frame_dim=4)
    linker._registry.remember(hymn_aphrodite, aliases=["Aphrodite"], qids=[])

    decision = linker.link_reference(
        label="Aphrodite",
        description="The foam-born goddess who came ashore at Cyprus.",
        tags=["aphrodite", "foam-born"],
        qids=[QIDTag(qid="Q35500", confidence=0.9, attached_at=datetime.now(UTC))],
        semantic_vector=[0.98, 0.15] + [0.0] * 6,
        frame_vector=[0.0] * 4,
        description_vector=[0.98, 0.15] + [0.0] * 6,
    )
    assert not decision.is_new
    assert rt.nodes.get_consolidated_id_by_qid("Q35500") == str(hymn_aphrodite.id)
    # And the NEXT reference with the same Q-ID resolves via the qid signal.
    second = linker.link_reference(
        label="Venus",
        description="Roman name of the goddess of love.",
        tags=["venus"],
        qids=[QIDTag(qid="Q35500", confidence=1.0, attached_at=datetime.now(UTC))],
        semantic_vector=[0.9, 0.2] + [0.0] * 6,
        frame_vector=[0.0] * 4,
        description_vector=[0.9, 0.2] + [0.0] * 6,
    )
    assert not second.is_new
    assert str(second.node.id) == str(hymn_aphrodite.id)
