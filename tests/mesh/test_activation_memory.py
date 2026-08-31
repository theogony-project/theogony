"""The substrate's record that something fired.

`fired_total` and `fired_recent` are declared on both node schemas and were **0
on every node of every mesh this repo has built** — nothing wrote them. Four
doctrine mechanisms read them (tier promotion, tier-modulated decay, Oneiros'
replay, RL eligibility), so all four were reading a history nobody kept
(PHX-1100, PHX-1101).

The tests that matter here are not "does the counter go up". They are the ones
that pin *how* it goes up, because each of those choices is a place the counter
could quietly become something else: a restatement of degree, a duplicate of its
own sibling, or a write on the read path that doctrine forbids outright.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge
from theogony.mesh.storage.nodes import NodeFiringBuffer, merge_node_firings

NOW = datetime(2026, 8, 31, tzinfo=UTC)


def _node(dim: int = 8, **kw: object) -> ConsolidatedNode:
    return ConsolidatedNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * dim,
        frame_vector=[0.1] * 4,
        description="X — a thing",
        **kw,  # type: ignore[arg-type]
    )


# ------------------------------------------------------------------ buffer


def test_one_append_per_pass_not_one_per_node(tmp_path: Path) -> None:
    """Doctrine says so in as many words.

    `MESH_IMPLEMENTATION.md` §"Writes — buffered, not synchronous": "The flush is
    a single append batch, not many small appends." The edge delta buffer next
    door does the opposite — one file open per delta under the lock, measured at
    3.05 ms for a single query's 64 deltas.
    """
    path = tmp_path / "node_firings.jsonl"
    buffer = NodeFiringBuffer(path)
    assert buffer.append_firing([f"n{i}" for i in range(50)]) == 50
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_a_node_named_twice_in_one_pass_fired_once(tmp_path: Path) -> None:
    """The counter is over passes, not over mentions.

    Doctrine gates tier promotion on "distinct activation *contexts*". A node that
    appears twice in one working set has not been reached from two directions.
    """
    buffer = NodeFiringBuffer(tmp_path / "f.jsonl")
    assert buffer.append_firing(["a", "b", "a"]) == 2
    rows = buffer.drain()
    assert rows[0]["node_ids"] == ["a", "b"]


def test_an_empty_pass_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    assert NodeFiringBuffer(path).append_firing([]) == 0
    assert not path.exists()


def test_a_torn_final_line_costs_one_pass_not_the_tick(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    buffer = NodeFiringBuffer(path)
    buffer.append_firing(["a"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"at": "2026-08-31T00:00:00+00:00", "node_ids": ["b"')
    assert len(buffer.drain()) == 1


# ------------------------------------------------------------- arithmetic


def test_fired_total_counts_passes() -> None:
    node = _node()
    rows = [{"at": NOW.isoformat(), "node_ids": [str(node.id)]} for _ in range(3)]
    out, touched, passes = merge_node_firings([node], rows)
    assert (out[0].fired_total, touched, passes) == (3, 1, 3)


def test_fired_recent_forgets_and_fired_total_does_not() -> None:
    """Otherwise `fired_recent` is a second copy of `fired_total`.

    Doctrine calls it a "rolling window counter", and the decay has to apply to
    **every** node rather than only the ones that fired — a node that stops firing
    must lose its recency, which is the whole difference between the two fields.
    """
    quiet = _node(fired_total=10, fired_recent=10)
    out, touched, _ = merge_node_firings([quiet], [], recent_decay=0.5)
    assert out[0].fired_total == 10
    assert out[0].fired_recent == 5
    assert touched == 0

    for _ in range(6):
        out, _, _ = merge_node_firings(out, [], recent_decay=0.5)
    assert out[0].fired_recent == 0
    assert out[0].fired_total == 10


def test_fired_recent_reaches_zero_at_the_shipped_decay() -> None:
    """The bug an integer counter invites, caught before it shipped.

    With `round()` and the default decay of 0.9, `round(1 * 0.9)` is 1 — a node
    that fired once would hold `fired_recent = 1` for ever and the field would
    never forget anything, which is the one thing it is for. Flooring terminates.
    """
    from theogony.mesh.storage.nodes import DEFAULT_FIRED_RECENT_DECAY

    out = [_node(fired_total=45, fired_recent=45)]
    for _ in range(60):
        out, _, _ = merge_node_firings(out, [], recent_decay=DEFAULT_FIRED_RECENT_DECAY)
    assert out[0].fired_recent == 0
    assert out[0].fired_total == 45

    once = [_node(fired_total=1, fired_recent=1)]
    once, _, _ = merge_node_firings(once, [], recent_decay=DEFAULT_FIRED_RECENT_DECAY)
    assert once[0].fired_recent == 0


def test_last_fired_at_only_moves_forward() -> None:
    """Passes can be drained out of order; a stale sidecar must not walk it back."""
    node = _node()
    later = NOW + timedelta(days=1)
    out, _, _ = merge_node_firings([node], [{"at": later.isoformat(), "node_ids": [str(node.id)]}])
    assert out[0].last_fired_at == later

    earlier = NOW - timedelta(days=1)
    out2, _, _ = merge_node_firings(out, [{"at": earlier.isoformat(), "node_ids": [str(node.id)]}])
    assert out2[0].last_fired_at == later
    assert out2[0].fired_total == 2


def test_a_node_nobody_named_is_returned_unchanged() -> None:
    node = _node()
    out, _, _ = merge_node_firings([node], [{"at": NOW.isoformat(), "node_ids": ["other"]}])
    assert out[0] is node


# ------------------------------------------------------------- end to end


def _mesh(tmp_path: Path) -> tuple[MeshRuntime, list[ConsolidatedNode]]:
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    nodes = [_node(), _node()]
    runtime.nodes.append_consolidated_many(nodes)
    runtime.edges.append_edges(
        [
            Edge(
                source_id=nodes[0].id,
                target_id=nodes[1].id,
                weight=0.5,
                born_at=NOW,
                last_fired_at=NOW,
            )
        ]
    )
    return runtime, nodes


def test_the_tick_folds_recorded_passes_into_the_nodes(tmp_path: Path) -> None:
    runtime, nodes = _mesh(tmp_path)
    runtime.firings.append_firing([str(nodes[0].id)])
    runtime.firings.append_firing([str(nodes[0].id), str(nodes[1].id)])

    result = runtime.run_minimal_tick()

    assert (result.firing_passes, result.nodes_fired) == (2, 2)
    stored = {str(n.id): n for n in runtime.nodes.iter_consolidated()}
    assert stored[str(nodes[0].id)].fired_total == 2
    assert stored[str(nodes[1].id)].fired_total == 1


def test_a_tick_without_firings_leaves_the_node_table_alone(tmp_path: Path) -> None:
    """The fold rewrites every consolidated row; it must not run for nothing."""
    runtime, _ = _mesh(tmp_path)
    before = runtime.nodes.consolidated_table.version
    result = runtime.run_minimal_tick()
    assert result.firing_passes == 0
    assert runtime.nodes.consolidated_table.version == before


def test_a_failed_fold_puts_the_passes_back(tmp_path: Path) -> None:
    """`drain()` unlinks the sidecar, so a raise here would destroy the record."""
    runtime, nodes = _mesh(tmp_path)
    runtime.firings.append_firing([str(nodes[0].id)])

    def boom(_: object) -> None:
        raise RuntimeError("lance said no")

    runtime.nodes.replace_all_consolidated = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        runtime.run_minimal_tick()
    assert runtime.firings.pending_passes() == 1


def test_recording_a_firing_does_not_move_a_lance_version(tmp_path: Path) -> None:
    """`MESH_IMPLEMENTATION.md` §"What is forbidden": reads may not mutate the
    version they read from. The record goes to a sidecar; the tick applies it."""
    runtime, nodes = _mesh(tmp_path)
    before = (
        runtime.nodes.consolidated_table.version,
        runtime.edges.edge_table.version,
    )
    assert runtime.firings.append_firing([str(n.id) for n in nodes]) == 2
    after = (
        runtime.nodes.consolidated_table.version,
        runtime.edges.edge_table.version,
    )
    assert before == after
    assert (runtime.root / "node_firings.jsonl").is_file()


def test_the_evaluators_do_not_record(tmp_path: Path) -> None:
    """A benchmark must not change the substrate it measures.

    Today a firing is observationally inert for retrieval — nothing on the read
    path reads the counters — so this is a guard set before it is needed rather
    than after. The moment tier promotion reads `fired_total`, a harness that
    recorded firings would be measuring its own last run.
    """
    import inspect

    from theogony.mesh.eval import corpus_answers, corpus_qa

    for module in (corpus_answers, corpus_qa):
        source = inspect.getsource(module)
        assert "record_firing=False" in source, module.__name__
