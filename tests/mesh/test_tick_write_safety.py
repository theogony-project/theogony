"""A failing tick must not leave the substrate emptier than it found it.

`replace_all_edges` was three `delete("true")` calls followed by three `add()`
calls, and its docstring called that atomic. It was not: an exception anywhere in
the second half left `mesh_edges`, `edge_metadata` and `edge_dedup_index` all at
zero rows. Reproduced by making the first `add` raise (PHX-1082).

The edges turned out to be recoverable — `prune_history` runs later in the tick,
so the previous Lance snapshot survived — but nothing in this codebase calls
`restore`, so recovery depended on someone knowing to try it. The drained
Hebbian deltas had no snapshot at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge


def _edges(n: int) -> list[Edge]:
    now = datetime.now(UTC)
    return [
        Edge(
            source_id=ULID(),
            target_id=ULID(),
            weight=0.5,
            relation_descriptor=f"rel_{i}",
            relation_kind="semantic",
            born_at=now,
            last_fired_at=now,
        )
        for i in range(n)
    ]


def test_a_write_that_raises_does_not_empty_the_edge_tables(
    mesh_runtime: MeshRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect itself: no window in which the tables are empty."""
    mesh_runtime.edges.append_edges(_edges(5))
    assert mesh_runtime.edges.count_rows() == 5

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(mesh_runtime.edges.edge_table, "add", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        mesh_runtime.edges.replace_all_edges(_edges(3))

    monkeypatch.undo()
    assert mesh_runtime.edges.count_rows() == 5, "the old edges must still be there"


def test_a_failed_tick_gives_the_hebbian_deltas_back(
    mesh_runtime: MeshRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`drain()` unlinks the durable sidecar before the write.

    The edge tables are versioned by Lance and recoverable; the delta buffer is
    not. Reinforcement that a user paid for with `mesh ask --hebbian` would
    simply be gone.
    """
    edges = _edges(3)
    mesh_runtime.edges.append_edges(edges)
    for edge in edges:
        mesh_runtime.edges.delta.append_hebbian_delta(
            source_id=str(edge.source_id),
            target_id=str(edge.target_id),
            weight_delta=0.01,
            relation_descriptor=edge.relation_descriptor,
        )
    assert mesh_runtime.edges.delta.pending() == 3

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(mesh_runtime.edges.edge_table, "add", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        mesh_runtime.run_minimal_tick()

    monkeypatch.undo()
    assert mesh_runtime.edges.delta.pending() == 3, "drained deltas must be put back"


def test_a_successful_tick_still_consumes_the_deltas(mesh_runtime: MeshRuntime) -> None:
    """The restore path must not fire on the happy path."""
    edges = _edges(3)
    mesh_runtime.edges.append_edges(edges)
    for edge in edges:
        mesh_runtime.edges.delta.append_hebbian_delta(
            source_id=str(edge.source_id),
            target_id=str(edge.target_id),
            weight_delta=0.01,
            relation_descriptor=edge.relation_descriptor,
        )
    result = mesh_runtime.run_minimal_tick()
    assert result.delta_drained == 3
    assert mesh_runtime.edges.delta.pending() == 0


def test_the_dedup_index_is_pruned_like_its_siblings(mesh_runtime: MeshRuntime) -> None:
    """It was absent from the prune list and kept every version ever written.

    237 of them on the founding mesh, against 1 for `mesh_edges` and
    `edge_metadata`.
    """
    from datetime import timedelta

    mesh_runtime.edges.append_edges(_edges(2))
    mesh_runtime.edges.append_edges(_edges(2))
    removed = mesh_runtime.edges.prune_history(retention=timedelta(0))
    assert set(removed) == {"mesh_edges", "edge_metadata", "edge_dedup_index"}
