"""What a merge learns about a name has to outlive the paragraph.

The eager linker discovers, on every merge, that some span refers to a node it
already holds. That went to an in-memory registry and died with the run, so the
substrate could not match on it the next time it read — six separate Zeus nodes
in the founding mesh, every one carrying `Zeus` in its own tags (PHX-1071).

The guard matters as much as the feature. A referring expression is not a name:
"her father" written onto Zeus would pull every later occurrence of that phrase
onto him, and in the next passage it is someone else — the PHX-1051 attractor
rebuilt from the other side.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, QIDTag
from theogony.mesh.storage.nodes import _mergeable_aliases


def test_a_proper_name_is_kept() -> None:
    assert _mergeable_aliases(["Earth-Shaker"], ["Poseidon"]) == ["Earth-Shaker"]


def test_referring_expressions_are_refused() -> None:
    """The whole reason the filter exists."""
    refused = ["her father", "The god", "his mother", "a king", "those who voyage"]
    assert _mergeable_aliases(refused, ["Zeus"]) == []


def test_lowercase_spans_are_refused() -> None:
    assert _mergeable_aliases(["thief", "far-shooter"], ["Hermes"]) == []


def test_a_description_is_not_a_tag() -> None:
    """`remember()` hands over label *and* description; only one is a name."""
    long_text = "Greek goddess of love and beauty, born from the foam of the sea near Cythera"
    assert _mergeable_aliases([long_text], ["Aphrodite"]) == []


def test_aliases_already_on_the_node_are_not_repeated() -> None:
    assert _mergeable_aliases(["Zeus", "zeus", "Jove"], ["Zeus"]) == ["Jove"]


def test_the_alias_reaches_the_store_and_the_label_index(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * mesh_runtime.semantic_dim,
        frame_vector=[0.0] * mesh_runtime.frame_dim,
        description="Poseidon — god of the sea",
        description_vector=[0.1] * mesh_runtime.semantic_dim,
        tags=["Poseidon"],
    )
    mesh_runtime.nodes.append_consolidated(node)

    updated = mesh_runtime.nodes.merge_identity_evidence(
        str(node.id), qids=[], aliases=["Earth-Shaker"]
    )

    assert updated is not None
    assert "Earth-Shaker" in updated.tags
    found = mesh_runtime.nodes.find_consolidated_by_labels(["Earth-Shaker"], limit=5)
    assert [str(n.id) for n in found] == [str(node.id)], "the alias must be findable"


def test_a_merge_that_learns_nothing_writes_nothing(mesh_runtime: MeshRuntime) -> None:
    """No Q-ID, no new alias — the row must not be rewritten for nothing."""
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * mesh_runtime.semantic_dim,
        frame_vector=[0.0] * mesh_runtime.frame_dim,
        description="Zeus — king of the gods",
        description_vector=[0.1] * mesh_runtime.semantic_dim,
        tags=["Zeus"],
    )
    mesh_runtime.nodes.append_consolidated(node)
    before = mesh_runtime.nodes.consolidated_table.count_rows()

    same = mesh_runtime.nodes.merge_identity_evidence(str(node.id), qids=[], aliases=["Zeus"])

    assert same is not None
    assert same.tags == ["Zeus"]
    assert mesh_runtime.nodes.consolidated_table.count_rows() == before


def test_qids_still_persist_alongside(mesh_runtime: MeshRuntime) -> None:
    """PHX-1053's guarantee is unchanged by adding the alias half."""
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * mesh_runtime.semantic_dim,
        frame_vector=[0.0] * mesh_runtime.frame_dim,
        description="Aphrodite — goddess of love",
        description_vector=[0.1] * mesh_runtime.semantic_dim,
        tags=["Aphrodite"],
    )
    mesh_runtime.nodes.append_consolidated(node)

    updated = mesh_runtime.nodes.merge_identity_evidence(
        str(node.id),
        qids=[QIDTag(qid="Q35500", confidence=0.99, attached_at=now)],
        aliases=["Cytherea"],
    )

    assert updated is not None
    assert [q.qid for q in updated.qids] == ["Q35500"]
    assert "Cytherea" in updated.tags
    assert mesh_runtime.nodes.get_consolidated_by_qid("Q35500") is not None
