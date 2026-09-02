"""Edges that are not fired weaken — and only those (PHX-1102).

`MESH_SUBSTRATE.md` §"2. Super-linear decay" has always said it. Until
PHX-1101 there was no firing record to honour it with, so decay ran
unconditionally and the substrate could only forget: measured on the founding
mesh, the strongest reinforcement a query can write is 17x smaller than one tick
of decay, and the most-used edges fell 0.594 -> 0.359 over 20 ticks of use.
Gating decay on firing is the one knob under which they hold (0.594) while
never-fired edges fade exactly as before (0.387 -> 0.270).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge
from theogony.mesh.storage.edges import decay_edges_inplace, fired_pairs

NOW = datetime(2026, 8, 31, tzinfo=UTC)


def _edge(a: ULID, b: ULID, w: float = 0.5) -> Edge:
    return Edge(source_id=a, target_id=b, weight=w, born_at=NOW, last_fired_at=NOW)


def _node() -> ConsolidatedNode:
    return ConsolidatedNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * 8,
        frame_vector=[0.1] * 4,
        description="X — a thing",
    )


def test_a_fired_edge_is_spared_and_an_unfired_one_decays() -> None:
    a, b, c = ULID(), ULID(), ULID()
    edges = [_edge(a, b), _edge(b, c)]
    fired = fired_pairs([{"node_ids": [str(a), str(b)]}])
    spared = decay_edges_inplace(edges, lam=0.05, fired=fired)
    assert spared == 1
    assert edges[0].weight == 0.5
    assert edges[1].weight < 0.5


def test_with_no_firing_record_the_tick_decays_everything_as_before() -> None:
    """The regression guard: a substrate nobody queried must behave as it always did."""
    a, b = ULID(), ULID()
    gated = [_edge(a, b)]
    ungated = [_edge(a, b)]
    assert decay_edges_inplace(gated, lam=0.05, fired=fired_pairs([])) == 0
    decay_edges_inplace(ungated, lam=0.05)
    assert gated[0].weight == ungated[0].weight < 0.5


def test_a_pair_fires_in_both_directions_and_never_with_itself() -> None:
    fired = fired_pairs([{"node_ids": ["a", "b"]}, {"node_ids": ["c"]}])
    assert ("a", "b") in fired and ("b", "a") in fired
    assert ("a", "a") not in fired
    assert ("a", "c") not in fired, "different passes do not co-fire"


def test_a_hebbian_delta_names_its_edge_as_fired_and_a_non_positive_one_does_not() -> None:
    fired = fired_pairs(
        [],
        [
            {"source_id": "x", "target_id": "y", "weight_delta": 0.1},
            {"source_id": "p", "target_id": "q", "weight_delta": 0.0},
        ],
    )
    assert ("x", "y") in fired
    assert ("y", "x") not in fired, "a delta names one stored direction"
    assert ("p", "q") not in fired, "the merge ignores it, so must the gate"


def test_the_index_stays_linear_in_pass_size() -> None:
    """The set of all ordered pairs is O(k^2): 5.5 GB for 5,000 passes of 100.

    Review measured it before this shipped. The index holds node -> passes and
    answers a pair by intersection, so 1,000 passes of 50 cost 50,000 entries,
    not 2.45 million tuples.
    """
    passes = [{"node_ids": [f"n{i}_{j}" for j in range(50)]} for i in range(1_000)]
    fired = fired_pairs(passes)
    assert sum(len(v) for v in fired._passes_by_node.values()) == 50_000
    assert ("n0_1", "n0_2") in fired
    assert ("n0_1", "n1_2") not in fired


def test_a_pass_that_already_gated_an_edge_commit_does_not_gate_it_again() -> None:
    fired = fired_pairs([{"node_ids": ["a", "b"], "edges_applied": True}])
    assert ("a", "b") not in fired
    assert not fired


def test_the_tick_spares_what_the_query_path_recorded(tmp_path: Path) -> None:
    """End to end: a pass records two nodes, the edge between them holds, another fades."""
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    used_a, used_b, idle = _node(), _node(), _node()
    runtime.nodes.append_consolidated_many([used_a, used_b, idle])
    runtime.edges.append_edges([_edge(used_a.id, used_b.id), _edge(used_b.id, idle.id)])
    runtime.firings.append_firing([str(used_a.id), str(used_b.id)])

    result = runtime.run_minimal_tick()

    assert result.edges_spared_from_decay == 1
    weights = {
        (str(e.source_id), str(e.target_id)): e.weight for e in runtime.edges.load_all_edges()
    }
    assert weights[(str(used_a.id), str(used_b.id))] == 0.5
    assert weights[(str(used_b.id), str(idle.id))] < 0.5


def test_the_gate_can_be_switched_off(tmp_path: Path) -> None:
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    a, b = _node(), _node()
    runtime.nodes.append_consolidated_many([a, b])
    runtime.edges.append_edges([_edge(a.id, b.id)])
    runtime.firings.append_firing([str(a.id), str(b.id)])
    result = runtime.run_minimal_tick(decay_gate=False)
    assert result.edges_spared_from_decay == 0
    assert runtime.edges.load_all_edges()[0].weight < 0.5


def test_a_failed_edge_write_restores_both_buffers(tmp_path: Path) -> None:
    """Firings are now drained before the edge write, so they need the same protection."""
    import pytest

    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    a, b = _node(), _node()
    runtime.nodes.append_consolidated_many([a, b])
    runtime.edges.append_edges([_edge(a.id, b.id)])
    runtime.firings.append_firing([str(a.id), str(b.id)])
    runtime.edges.delta.append_hebbian_delta(
        source_id=str(a.id), target_id=str(b.id), weight_delta=0.1
    )

    def boom(_: object) -> None:
        raise RuntimeError("lance said no")

    runtime.edges.replace_all_edges = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        runtime.run_minimal_tick()
    assert runtime.firings.pending_passes() == 1
    assert runtime.edges.delta.pending() == 1


def test_a_failed_node_fold_does_not_spare_the_same_edges_twice(tmp_path: Path) -> None:
    """The bug review caught: firings feed two commits now, and the second must
    not re-use what the first consumed.

    Tick 1: the edge commit succeeds with the gate, then the node fold fails. Tick
    2, with nothing new fired, must spare nothing — before the fix it spared the
    same edges again and reported a pass that had already happened.
    """
    import pytest

    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    a, b, idle = _node(), _node(), _node()
    runtime.nodes.append_consolidated_many([a, b, idle])
    runtime.edges.append_edges([_edge(a.id, b.id), _edge(b.id, idle.id)])
    runtime.firings.append_firing([str(a.id), str(b.id)])

    real = runtime.nodes.replace_all_consolidated

    def boom(_: object) -> None:
        raise RuntimeError("lance said no")

    runtime.nodes.replace_all_consolidated = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        runtime.run_minimal_tick()
    runtime.nodes.replace_all_consolidated = real  # type: ignore[method-assign]

    result = runtime.run_minimal_tick()
    assert result.edges_spared_from_decay == 0
    assert result.firing_passes == 1, "the pass still folds into the node counters"
    stored = {str(n.id): n for n in runtime.nodes.iter_consolidated()}
    assert stored[str(a.id)].fired_total == 1


def test_a_restored_pass_keeps_the_time_it_fired_at(tmp_path: Path) -> None:
    """Restoring with the restore time made every fired node look freshly fired."""
    from datetime import timedelta

    import pytest

    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    a, b = _node(), _node()
    runtime.nodes.append_consolidated_many([a, b])
    runtime.edges.append_edges([_edge(a.id, b.id)])
    fired_at = NOW - timedelta(days=30)
    runtime.firings.append_firing([str(a.id), str(b.id)], at=fired_at)

    def boom(_: object) -> None:
        raise RuntimeError("lance said no")

    runtime.edges.replace_all_edges = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        runtime.run_minimal_tick()
    rows = runtime.firings.drain()
    assert rows and rows[0]["at"] == fired_at.isoformat()


def test_the_audit_says_whether_the_gate_ran_and_what_it_spared(tmp_path: Path) -> None:
    import json

    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    a, b = _node(), _node()
    runtime.nodes.append_consolidated_many([a, b])
    runtime.edges.append_edges([_edge(a.id, b.id)])
    runtime.firings.append_firing([str(a.id), str(b.id)])
    runtime.run_minimal_tick()
    row = next(
        r for r in runtime.audit.list_recent(limit=5) if r["action"] == "mesh_oneiros_minimal_tick"
    )
    detail = json.loads(row["payload_json"])
    assert detail["decay_gate"] is True
    assert detail["edges_spared_from_decay"] == 1


def test_normalised_credit_lands_on_the_doctrine_s_scale() -> None:
    """Peak activation maps to 1.0, so no credit exceeds alpha and the strongest
    pair gets close to it; raw credit on the same constellation is far below."""
    from theogony.mesh.retrieval.constellation import (
        Constellation,
        ConstellationEdge,
        ConstellationNode,
    )
    from theogony.mesh.retrieval.retrieve import append_hebbian_deltas
    from theogony.mesh.storage.edges import EdgeDeltaBuffer

    class _Runtime:
        class edges:  # noqa: N801 - mimics MeshRuntime.edges.delta
            delta = EdgeDeltaBuffer()

    nodes = [
        ConstellationNode(node_id="s", name="s", activation=0.2),
        ConstellationNode(node_id="t", name="t", activation=0.1),
        ConstellationNode(node_id="u", name="u", activation=0.01),
    ]
    edges = [
        ConstellationEdge(
            source_id="s", target_id="t", source_name="s", target_name="t", weight=0.5
        ),
        ConstellationEdge(
            source_id="t", target_id="u", source_name="t", target_name="u", weight=0.5
        ),
    ]
    c = Constellation(nodes=nodes, edges=edges)

    append_hebbian_deltas(_Runtime(), c, learning_rate=0.01, normalize=False)  # type: ignore[arg-type]
    raw = sorted(r["weight_delta"] for r in _Runtime.edges.delta.drain())
    append_hebbian_deltas(_Runtime(), c, learning_rate=0.01, normalize=True)  # type: ignore[arg-type]
    norm = sorted(r["weight_delta"] for r in _Runtime.edges.delta.drain())

    assert max(norm) <= 0.01 + 1e-12
    assert max(norm) == pytest_approx(0.01 * 1.0 * 0.5)
    assert max(raw) == pytest_approx(0.01 * 0.2 * 0.1)
    assert max(norm) / max(raw) == pytest_approx(1 / 0.2**2)


def pytest_approx(value: float):  # noqa: ANN201 - tiny local helper
    import pytest

    return pytest.approx(value)
