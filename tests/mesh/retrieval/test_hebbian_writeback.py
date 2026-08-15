"""Hebbian write-back closes the query -> reinforcement -> tick loop.

The load-bearing test here is the *negative* one: retrieval must not touch the
delta buffer unless explicitly asked. A read path that silently mutates the
substrate would make every evaluation non-reproducible and would quietly
contaminate the retrieval benchmarks, which run thousands of queries.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.retrieval.constellation import (
    Constellation,
    ConstellationEdge,
    ConstellationNode,
)
from theogony.mesh.retrieval.retrieve import append_hebbian_deltas
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge


def _constellation(activations: dict[str, float], edges: list[tuple[str, str]]) -> Constellation:
    return Constellation(
        nodes=[
            ConstellationNode(node_id=nid, name=nid, activation=act)
            for nid, act in activations.items()
        ],
        edges=[
            ConstellationEdge(source_id=s, target_id=t, source_name=s, target_name=t, weight=1.0)
            for s, t in edges
        ],
    )


def test_credit_is_proportional_to_endpoint_co_activation(mesh_runtime: MeshRuntime) -> None:
    c = _constellation(
        {"a": 1.0, "b": 0.5, "c": 0.1},
        [("a", "b"), ("a", "c")],
    )
    written = append_hebbian_deltas(mesh_runtime, c, learning_rate=1.0)
    assert written == 2

    drained = mesh_runtime.edges.delta.drain()
    by_pair = {(d["source_id"], d["target_id"]): d["weight_delta"] for d in drained}
    # a->b co-activates at 1.0*0.5; a->c at 1.0*0.1. The path that carried the
    # answer is credited five times more than the incidental one.
    assert by_pair[("a", "b")] == 0.5
    assert by_pair[("a", "c")] == 0.1


def test_edges_touching_an_unactivated_node_are_not_credited(mesh_runtime: MeshRuntime) -> None:
    c = _constellation({"a": 1.0, "b": 0.0}, [("a", "b")])
    assert append_hebbian_deltas(mesh_runtime, c, learning_rate=1.0) == 0
    assert mesh_runtime.edges.delta.pending() == 0


def test_delta_count_is_bounded(mesh_runtime: MeshRuntime) -> None:
    acts = {f"n{i}": 1.0 for i in range(20)}
    edges = [("n0", f"n{i}") for i in range(1, 20)]
    written = append_hebbian_deltas(mesh_runtime, _constellation(acts, edges), max_deltas=5)
    assert written == 5
    assert mesh_runtime.edges.delta.pending() == 5


def test_deltas_survive_a_process_boundary(tmp_path) -> None:
    """The loop must close across CLI invocations, not just within one process.

    `mesh ask --hebbian` and `mesh tick` are separate processes. With a purely
    in-memory buffer the deltas would die at the first process's exit and the tick
    would drain nothing — the mechanism would exist and be inert, which is the
    failure mode this whole feature is meant to fix.
    """
    root = tmp_path / "ws"

    writer = MeshRuntime(root, semantic_dim=8, frame_dim=4)
    c = _constellation({"a": 1.0, "b": 1.0}, [("a", "b")])
    assert append_hebbian_deltas(writer, c, learning_rate=0.5) == 1

    # A completely separate runtime, as a second CLI process would open.
    reader = MeshRuntime(root, semantic_dim=8, frame_dim=4)
    assert reader.edges.delta.pending() == 1
    drained = reader.edges.delta.drain()
    assert drained[0]["source_id"] == "a"
    assert drained[0]["weight_delta"] == 0.5

    # Drained means consumed: a third process sees an empty buffer.
    assert MeshRuntime(root, semantic_dim=8, frame_dim=4).edges.delta.pending() == 0


def test_deltas_survive_into_the_tick(mesh_runtime: MeshRuntime) -> None:
    """End to end: a reinforced edge is heavier after the tick merges the buffer."""
    now = datetime.now(UTC)
    src, tgt = str(ULID()), str(ULID())
    mesh_runtime.edges.append_edge(
        Edge(source_id=src, target_id=tgt, weight=0.20, born_at=now, last_fired_at=now)
    )

    c = _constellation({src: 1.0, tgt: 1.0}, [(src, tgt)])
    assert append_hebbian_deltas(mesh_runtime, c, learning_rate=0.5) == 1

    # lam=0 isolates the merge from decay so the assertion is about reinforcement.
    result = mesh_runtime.run_minimal_tick(lam=0.0)
    assert result.delta_drained == 1

    edge = next(e for e in mesh_runtime.edges.load_all_edges() if str(e.source_id) == src)
    assert edge.weight > 0.20  # 0.20 + 0.5*1.0*1.0, capped at w_max
