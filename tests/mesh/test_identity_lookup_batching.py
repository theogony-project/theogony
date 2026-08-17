"""Identity lookups batch their reads without changing what they select.

`find_consolidated_by_labels` fetched every matching node with its own Lance
query, which made a single concept's tag match cost ~595 ms on a 2.4k-node mesh —
the dominant term in identity resolution. Only the *hydration* is batched now.

That distinction is the point of this file. A faster variant that also merged the
per-label index reads into one `label IN (...)` query was measured and rejected:
it changed which candidates survive truncation when a generic tag matches more
nodes than the limit (15 differing candidate sets out of 60 real label/tag
combinations). The eager linker scores whatever candidates it is handed, so a
changed candidate set is a changed identity decision — not an acceptable price
for latency.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode


def _node(runtime: MeshRuntime, description: str, tags: list[str]) -> ConsolidatedNode:
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * runtime.semantic_dim,
        frame_vector=[0.0] * runtime.frame_dim,
        description=description,
        description_vector=[0.1] * runtime.semantic_dim,
        tags=tags,
    )
    runtime.nodes.append_consolidated(node)
    return node


def test_label_priority_is_preserved(mesh_runtime: MeshRuntime) -> None:
    """The incoming label must rank above its tags — the linker relies on it."""
    by_tag = _node(mesh_runtime, "Matched by tag only", ["shared-tag"])
    by_label = _node(mesh_runtime, "Zeus", ["shared-tag"])

    found = mesh_runtime.nodes.find_consolidated_by_labels(["Zeus", "shared-tag"], limit=10)
    ids = [str(n.id) for n in found]

    assert str(by_label.id) in ids
    assert str(by_tag.id) in ids
    assert ids.index(str(by_label.id)) < ids.index(str(by_tag.id))


def test_limit_is_respected(mesh_runtime: MeshRuntime) -> None:
    for i in range(12):
        _node(mesh_runtime, f"Node {i}", ["common"])
    assert len(mesh_runtime.nodes.find_consolidated_by_labels(["common"], limit=5)) == 5
    assert mesh_runtime.nodes.find_consolidated_by_labels(["common"], limit=0) == []


def test_a_node_matching_several_labels_appears_once(mesh_runtime: MeshRuntime) -> None:
    node = _node(mesh_runtime, "Aphrodite", ["goddess", "olympian"])
    found = mesh_runtime.nodes.find_consolidated_by_labels(
        ["Aphrodite", "goddess", "olympian"], limit=10
    )
    assert [str(n.id) for n in found].count(str(node.id)) == 1


def test_batched_hydration_returns_the_same_nodes_as_individual_reads(
    mesh_runtime: MeshRuntime,
) -> None:
    """The batching must be invisible in its result, only in its cost."""
    created = [_node(mesh_runtime, f"Entity {i}", ["batch-probe"]) for i in range(6)]
    found = mesh_runtime.nodes.find_consolidated_by_labels(["batch-probe"], limit=10)

    for node in found:
        individually = mesh_runtime.nodes.get_consolidated(str(node.id))
        assert individually is not None
        assert individually.description == node.description
        assert individually.tags == node.tags
    assert {str(n.id) for n in found} == {str(n.id) for n in created}


def test_unknown_and_empty_labels_are_tolerated(mesh_runtime: MeshRuntime) -> None:
    _node(mesh_runtime, "Known", ["tag"])
    assert mesh_runtime.nodes.find_consolidated_by_labels(["nothing-matches-this"]) == []
    assert mesh_runtime.nodes.find_consolidated_by_labels(["", "   "]) == []
    assert mesh_runtime.nodes.find_consolidated_by_labels([]) == []
