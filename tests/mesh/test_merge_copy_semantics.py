"""What `merge_edge_deltas` copies, and what it deliberately does not.

The copy was deep, and it was a third of the whole maintenance pass: 1.63 s of a
4.90 s tick on the founding mesh, against 0.35 s shallow and 0.25 s with no copy.
Shallow is the chosen point on that curve — not the cheapest, because the caller
mutates the result. `decay_edges_inplace` writes `weight` on every returned edge,
and a shallow copy gives each scalar its own storage, so the input is untouched.

What a shallow copy does *not* give is independent list fields. That boundary is
pinned here rather than left to be discovered by whoever first calls
`.append()` on a merged edge's `pids` and silently rewrites the store's own
copy (PHX-1074).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.schemas import Edge, PIDTag
from theogony.mesh.storage.edges import decay_edges_inplace, merge_edge_deltas


def _edge(weight: float = 1.0, descriptor: str = "rel", **kw) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=kw.get("source") or ULID(),
        target_id=kw.get("target") or ULID(),
        weight=weight,
        born_at=now,
        last_fired_at=now,
        relation_kind="semantic",
        relation_descriptor=descriptor,
        creation_context="test",
        pids=kw.get("pids") or [],
    )


def test_mutating_the_result_leaves_the_input_alone() -> None:
    """The property the copy exists for."""
    base = [_edge(weight=1.0)]
    merged = merge_edge_deltas(base, [], w_max=1.0)

    decay_edges_inplace(merged, lam=0.5, dt=1.0)

    assert merged[0].weight < 1.0, "decay must have applied"
    assert base[0].weight == 1.0, "the input list must not have moved"


def test_assigning_a_list_field_on_the_result_is_safe() -> None:
    """How the P-ID backfill writes — assignment, not in-place mutation."""
    base = [_edge()]
    merged = merge_edge_deltas(base, [], w_max=1.0)

    merged[0].pids = [PIDTag(pid="P40", confidence=1.0, attached_at=datetime.now(UTC))]

    assert base[0].pids == [], "assignment must not reach through"


def test_list_fields_are_shared_and_that_is_documented() -> None:
    """The boundary, pinned so a change to it is deliberate rather than silent."""
    shared = [PIDTag(pid="P40", confidence=1.0, attached_at=datetime.now(UTC))]
    base = [_edge(pids=shared)]
    merged = merge_edge_deltas(base, [], w_max=1.0)

    merged[0].pids.append(PIDTag(pid="P22", confidence=1.0, attached_at=datetime.now(UTC)))

    assert len(base[0].pids) == 2, (
        "in-place list mutation does reach the input — if this ever needs to stop, "
        "the copy has to deepen and the tick pays 1.3 s for it"
    )


def test_duplicate_triples_still_collapse_to_the_strongest() -> None:
    """The dedup this function exists for, unchanged by the copy depth."""
    source, target = ULID(), ULID()
    base = [
        _edge(weight=0.3, source=source, target=target),
        _edge(weight=0.9, source=source, target=target),
        _edge(weight=0.5, source=source, target=target),
    ]
    merged = merge_edge_deltas(base, [], w_max=1.0)

    assert len(merged) == 1
    assert merged[0].weight == 0.9


def test_parallel_typed_relations_survive() -> None:
    """PHX-1033/1058: keying on the pair alone destroyed 2,520 relations."""
    source, target = ULID(), ULID()
    base = [
        _edge(descriptor="mentions", source=source, target=target),
        _edge(descriptor="father_of", source=source, target=target),
        _edge(descriptor="appears_in_source", source=source, target=target),
    ]
    assert len(merge_edge_deltas(base, [], w_max=1.0)) == 3
