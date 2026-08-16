"""A tick must not destroy parallel typed relations.

`merge_edge_deltas` keyed edges by ``(source, target)`` alone, so every relation
between the same two nodes collapsed into whichever row happened to be last.
Measured before the fix, with **no deltas at all**:

    smoke mesh        152 rows ->  47   (79 distinct triples existed)
    founding mesh  27,824 rows -> 15,628, taking 2,520 distinct typed relations

Neither decay nor saturation contributed: decay zeroed nothing, and the smoke
mesh's largest out-degree is 5 against a cap of 64. The loss was entirely the
merge key — and `theogony mesh tick` made a dormant bug reachable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import merge_edge_deltas


def _edge(src: str, tgt: str, relation: str | None, weight: float = 0.5) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=src,  # type: ignore[arg-type]
        target_id=tgt,  # type: ignore[arg-type]
        weight=weight,
        born_at=now,
        last_fired_at=now,
        relation_descriptor=relation,
    )


def test_parallel_typed_relations_survive_a_merge() -> None:
    """The regression: three relations between one pair must stay three edges."""
    a, b = str(ULID()), str(ULID())
    base = [
        _edge(a, b, "mentions"),
        _edge(a, b, "co_mentions_in_paragraph"),
        _edge(a, b, "appears_in_source"),
    ]
    merged = merge_edge_deltas(base, [], w_max=1.0)
    assert len(merged) == 3
    assert {e.relation_descriptor for e in merged} == {
        "mentions",
        "co_mentions_in_paragraph",
        "appears_in_source",
    }


def test_duplicate_rows_of_one_relation_collapse_to_the_strongest() -> None:
    """Same triple repeated is one relation observed repeatedly, not three edges.

    Ingestion appends a row per occurrence, so these duplicates are real; folding
    them must not weaken the relation, which keeping "whichever was last" would.
    """
    a, b = str(ULID()), str(ULID())
    base = [
        _edge(a, b, "mentions", weight=0.2),
        _edge(a, b, "mentions", weight=0.9),
        _edge(a, b, "mentions", weight=0.4),
    ]
    merged = merge_edge_deltas(base, [], w_max=1.0)
    assert len(merged) == 1
    assert merged[0].weight == 0.9


def test_a_delta_reinforces_the_named_relation_only() -> None:
    a, b = str(ULID()), str(ULID())
    base = [_edge(a, b, "mentions", weight=0.5), _edge(a, b, "cites", weight=0.5)]
    merged = merge_edge_deltas(
        base,
        [{"source_id": a, "target_id": b, "weight_delta": 0.3, "relation_descriptor": "cites"}],
        w_max=1.0,
    )
    by_relation = {e.relation_descriptor: e.weight for e in merged}
    assert by_relation["cites"] == 0.8
    assert by_relation["mentions"] == 0.5  # untouched


def test_an_unnamed_delta_does_not_retype_an_existing_relation() -> None:
    """Without a relation the delta addresses the untyped edge, creating it if needed.

    Otherwise reinforcement would silently graft itself onto whatever typed
    relation happened to share the pair.
    """
    a, b = str(ULID()), str(ULID())
    base = [_edge(a, b, "mentions", weight=0.5)]
    merged = merge_edge_deltas(
        base, [{"source_id": a, "target_id": b, "weight_delta": 0.3}], w_max=1.0
    )
    by_relation = {e.relation_descriptor: e.weight for e in merged}
    assert by_relation["mentions"] == 0.5
    assert by_relation[None] == 0.3


def test_tick_on_a_typed_mesh_keeps_every_relation(mesh_runtime: MeshRuntime) -> None:
    """End to end through the command that made this reachable."""
    a, b, c = str(ULID()), str(ULID()), str(ULID())
    mesh_runtime.edges.append_edges(
        [
            _edge(a, b, "mentions"),
            _edge(a, b, "co_mentions_in_paragraph"),
            _edge(a, b, "appears_in_source"),
            _edge(b, c, "mentions"),
        ]
    )
    assert mesh_runtime.edges.count_rows() == 4

    result = mesh_runtime.run_minimal_tick(lam=0.0)
    assert result.edges_before == 4
    assert result.edges_after == 4, "a tick must not collapse distinct typed relations"
