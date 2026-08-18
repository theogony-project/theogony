"""The substrate builds the indices its own query patterns depend on.

It previously built none. Every lookup was a full table scan, so cost grew with
the mesh — measured on 2,436 nodes: `get_consolidated` 51.3 ms, the label lookup
215.5 ms, an ANN search 59.7 ms. With indices those are 2.5 / 14.5 / 8.0 ms, and
they stop growing linearly.

That was the last term in the ingestion-throughput collapse: batching cut how
*many* queries ran, indexing cuts what each one costs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode


def _nodes(runtime: MeshRuntime, count: int) -> None:
    now = datetime.now(UTC)
    batch = [
        ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            semantic_vector=[(i % 7) / 7.0] * runtime.semantic_dim,
            frame_vector=[0.0] * runtime.frame_dim,
            description=f"Entity {i}",
            description_vector=[(i % 5) / 5.0] * runtime.semantic_dim,
            tags=[f"tag-{i % 11}"],
        )
        for i in range(count)
    ]
    runtime.nodes.append_consolidated_many(batch)


def test_small_workspaces_are_not_indexed(mesh_runtime: MeshRuntime) -> None:
    """Below the threshold a scan wins and IVF cannot train — so do nothing."""
    _nodes(mesh_runtime, 20)
    status = mesh_runtime.nodes.ensure_indices()
    assert "skipped" in status
    assert mesh_runtime.nodes.consolidated_table.list_indices() == []


def test_indices_are_created_once_the_mesh_is_large_enough(mesh_runtime: MeshRuntime) -> None:
    _nodes(mesh_runtime, 600)
    status = mesh_runtime.nodes.ensure_indices()

    names = {idx.name for idx in mesh_runtime.nodes.consolidated_table.list_indices()}
    assert any("id" in n for n in names), status
    assert any("description_vector" in n for n in names), status


def test_ensure_indices_is_idempotent(mesh_runtime: MeshRuntime) -> None:
    """A second call must recognise existing indices instead of rebuilding."""
    _nodes(mesh_runtime, 600)
    mesh_runtime.nodes.ensure_indices()
    second = mesh_runtime.nodes.ensure_indices()
    assert any(value == "present" for value in second.values()), second


def test_queries_still_return_the_same_rows_after_indexing(mesh_runtime: MeshRuntime) -> None:
    """An index changes cost, never the answer — for exact lookups."""
    _nodes(mesh_runtime, 600)
    sample = [str(n.id) for n in mesh_runtime.nodes.iter_consolidated()][:5]
    before = {nid: mesh_runtime.nodes.get_consolidated(nid) for nid in sample}

    mesh_runtime.nodes.ensure_indices()

    for nid in sample:
        after = mesh_runtime.nodes.get_consolidated(nid)
        assert after is not None
        assert before[nid] is not None
        assert after.description == before[nid].description


def test_tick_reports_what_it_indexed(mesh_runtime: MeshRuntime) -> None:
    """Index upkeep belongs to the maintenance pass, and lands in its report."""
    _nodes(mesh_runtime, 600)
    result = mesh_runtime.run_minimal_tick()
    assert result.index_status
    assert any("created" in v or "present" in v for v in result.index_status.values())
