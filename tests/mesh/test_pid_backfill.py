"""The maintenance pass gives existing relations their Wikidata property.

`Edge.pids` was empty on every one of 94,490 edges, and the mapping added in
PHX-1072 only takes effect when something is written. A re-read of the corpus
would have cost an hour and a half to produce a number that is deterministic
from data already in the mesh — ceremony, not measurement.

The tick already rewrites every edge (load, merge, decay, saturate, replace), so
annotating them there costs nothing beyond the lookup. It normalises rather than
asserts: the descriptor is already on the edge, and the table gives it its
authoritative name. That is why a maintenance pass is allowed to do it at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import _backfill_relation_pids
from theogony.mesh.schemas import Edge, PIDTag


def _edge(descriptor: str, *, pids: list[PIDTag] | None = None) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=ULID(),
        target_id=ULID(),
        weight=1.0,
        born_at=now,
        last_fired_at=now,
        relation_kind="semantic",
        relation_descriptor=descriptor,
        creation_context="kadmos_relation",
        pids=pids or [],
    )


def test_a_mapped_descriptor_gets_its_property() -> None:
    edges = [_edge("father_of")]
    assert _backfill_relation_pids(edges) == 1
    assert [p.pid for p in edges[0].pids] == ["P40"]


def test_spelling_variants_land_on_one_property() -> None:
    """The point of the exercise: `father_of` and `father of` were two relations."""
    edges = [_edge("father_of"), _edge("father of"), _edge("Father-Of")]
    _backfill_relation_pids(edges)
    assert {e.pids[0].pid for e in edges} == {"P40"}


def test_the_unmapped_tail_is_left_alone() -> None:
    edges = [_edge("roamed in"), _edge("killed"), _edge("")]
    assert _backfill_relation_pids(edges) == 0
    assert all(not e.pids for e in edges)


def test_an_edge_that_already_has_a_pid_is_not_touched() -> None:
    """Idempotent, because it runs on every tick and not once."""
    existing = PIDTag(pid="P22", confidence=0.9, attached_at=datetime.now(UTC))
    edges = [_edge("father_of", pids=[existing])]
    assert _backfill_relation_pids(edges) == 0
    assert edges[0].pids == [existing]


def test_running_twice_changes_nothing_the_second_time() -> None:
    edges = [_edge("son_of"), _edge("married"), _edge("unmapped thing")]
    first = _backfill_relation_pids(edges)
    second = _backfill_relation_pids(edges)
    assert first == 2
    assert second == 0
