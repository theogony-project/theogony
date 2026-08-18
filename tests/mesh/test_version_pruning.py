"""Version history is storage debris, and keeping it makes every write slower.

The substrate writes one node at a time across three tables, so a single ingest
batch leaves thousands of Lance version snapshots behind. Measured on a
2,325-node mesh, that history is what makes an append cost 83.3 ms where the
same rows written without the pile-up cost 2.6 ms — the node count is not the
driver, a mesh with *more* index rows and the same nodes appends in 2.6 ms when
it has 13 versions instead of 1,871 (PHX-1060).

What the mesh did and when is recorded in `mesh_audit` and the RunReports.
Nothing in this codebase reads an old Lance version — there is no `checkout`,
`restore` or `as_of` anywhere — which is why the maintenance pass is allowed to
drop them. These tests hold that line: the snapshots go, the content stays.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode


def _append_one_by_one(runtime: MeshRuntime, count: int, prefix: str = "n") -> list[str]:
    """Write nodes the way the eager linker does — one transaction each."""
    now = datetime.now(UTC)
    ids = []
    for i in range(count):
        node = ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            semantic_vector=[0.1] * runtime.semantic_dim,
            frame_vector=[0.0] * runtime.frame_dim,
            description=f"{prefix} {i}",
            description_vector=[0.1] * runtime.semantic_dim,
            tags=[f"{prefix}-tag-{i}"],
        )
        runtime.nodes.append_consolidated(node)
        ids.append(str(node.id))
    return ids


def test_pruning_collapses_the_version_pile(mesh_runtime: MeshRuntime) -> None:
    _append_one_by_one(mesh_runtime, 25)
    before = len(mesh_runtime.nodes.consolidated_table.list_versions())
    assert before > 20, "one transaction per node should leave a version each"

    removed = mesh_runtime.nodes.prune_history()

    assert removed["consolidated_nodes"] > 0
    assert len(mesh_runtime.nodes.consolidated_table.list_versions()) < before


def test_pruning_keeps_every_row(mesh_runtime: MeshRuntime) -> None:
    """Snapshots are dropped; content is not."""
    ids = _append_one_by_one(mesh_runtime, 15)
    before = {nid: mesh_runtime.nodes.get_consolidated(nid) for nid in ids}

    mesh_runtime.nodes.prune_history()

    assert mesh_runtime.nodes.consolidated_table.count_rows() == len(ids)
    for nid in ids:
        after = mesh_runtime.nodes.get_consolidated(nid)
        assert after is not None
        assert before[nid] is not None
        assert after.description == before[nid].description
        assert after.tags == before[nid].tags


def test_retention_window_is_honoured(mesh_runtime: MeshRuntime) -> None:
    """A caller that wants the history kept says so and keeps it."""
    _append_one_by_one(mesh_runtime, 20)
    before = len(mesh_runtime.nodes.consolidated_table.list_versions())

    removed = mesh_runtime.nodes.prune_history(retention=timedelta(days=3650))

    assert removed["consolidated_nodes"] == 0
    assert len(mesh_runtime.nodes.consolidated_table.list_versions()) >= before


def test_the_tick_prunes_and_reports_it(mesh_runtime: MeshRuntime) -> None:
    """Pruning belongs to the pass that has just committed a consistent state."""
    _append_one_by_one(mesh_runtime, 25)

    result = mesh_runtime.run_minimal_tick()

    assert sum(result.versions_pruned.values()) > 0
    assert "consolidated_nodes" in result.versions_pruned
    assert "mesh_edges" in result.versions_pruned


def test_the_tick_can_be_told_to_keep_history(mesh_runtime: MeshRuntime) -> None:
    _append_one_by_one(mesh_runtime, 20)

    result = mesh_runtime.run_minimal_tick(version_retention=timedelta(days=3650))

    assert sum(result.versions_pruned.values()) == 0


def test_the_audit_trail_survives_pruning(mesh_runtime: MeshRuntime) -> None:
    """The substrate's own record is not what gets dropped."""
    _append_one_by_one(mesh_runtime, 25)
    first = mesh_runtime.run_minimal_tick()
    second = mesh_runtime.run_minimal_tick()

    ids = {row["id"] for row in mesh_runtime.audit.list_recent(limit=50)}
    assert first.audit_id in ids
    assert second.audit_id in ids
