"""PHX-1049 — the structural lattice is capped without disconnecting the mesh.

`shares_entities_with` linked every entity-sharing paragraph pair, which is
O(P²): on the founding mesh the lattice alone was 51% of all edges, and a full
read grew ~33% slower per 100-paragraph batch because the pass writes two edges
and an audit row per qualifying pair.

The ticket's constraint is what makes this delicate: that lattice is *why* the
founding mesh is one connected component with no isolated nodes. A cap that
disconnects the graph trades a real property for a performance number. Selection
is therefore union-based — a pair survives if *either* endpoint ranks it — and
these tests pin that, not just the edge count.
"""

from __future__ import annotations

from theogony.mesh.ingestion.kadmos_v2 import _ParagraphUnit, _select_structural_pairs


def _unit(number: int, entities: set[str]) -> _ParagraphUnit:
    return _ParagraphUnit(
        paragraph_number=number,
        paragraph_anchor_id=f"anchor-{number}",
        chunk_id=f"chunk-{number}",
        entity_ids=entities,
        paragraph_concept_id=f"concept-{number}",
        local_node_ids=set(),
        local_edge_count=0,
    )


def _component_count(units: list[_ParagraphUnit], pairs: list[tuple]) -> int:
    """Connected components over the kept structural pairs."""
    parent = {u.paragraph_number: u.paragraph_number for u in units}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for left, right, _count in pairs:
        a, b = find(left.paragraph_number), find(right.paragraph_number)
        if a != b:
            parent[a] = b
    return len({find(u.paragraph_number) for u in units})


def test_uncapped_is_the_control_arm() -> None:
    """max_neighbours <= 0 must reproduce the old all-pairs behaviour exactly."""
    units = [_unit(i, {"shared", f"own-{i}"}) for i in range(6)]
    pairs, dropped = _select_structural_pairs(units, max_neighbours=0)
    assert dropped == 0
    assert len(pairs) == 6 * 5 // 2  # every pair shares "shared"


def test_cap_limits_pairs_and_reports_what_it_dropped() -> None:
    units = [_unit(i, {"shared"}) for i in range(20)]
    pairs, dropped = _select_structural_pairs(units, max_neighbours=3)
    total = 20 * 19 // 2
    assert len(pairs) < total
    assert dropped == total - len(pairs)  # accounting closes — nothing vanishes silently


def test_capped_lattice_stays_one_connected_component() -> None:
    """The property the lattice exists for must survive the cap."""
    units = [_unit(i, {"shared"}) for i in range(30)]
    pairs, _ = _select_structural_pairs(units, max_neighbours=2)
    assert _component_count(units, pairs) == 1


def test_a_weakly_linked_paragraph_keeps_its_only_partner() -> None:
    """Union selection: a lone link survives even among popular partners.

    Intersection-based selection would drop it — the hub's top-k is full of its
    other partners — and the paragraph would fall out of the graph entirely.
    """
    units = [_unit(i, {"hub"}) for i in range(10)]
    # Paragraph 99 shares exactly one entity with paragraph 0 and nothing else.
    units[0].entity_ids.add("rare")
    lonely = _unit(99, {"rare"})
    units.append(lonely)

    pairs, _ = _select_structural_pairs(units, max_neighbours=2)
    kept_numbers = {(left.paragraph_number, right.paragraph_number) for left, right, _ in pairs}
    assert (0, 99) in kept_numbers or (99, 0) in kept_numbers
    assert _component_count(units, pairs) == 1


def test_strongest_overlaps_are_preferred() -> None:
    """The cap keeps the most-shared partners, not arbitrary ones."""
    anchor = _unit(0, {"a", "b", "c"})
    strong = _unit(1, {"a", "b", "c"})  # 3 shared
    medium = _unit(2, {"a", "b"})  # 2 shared
    weak = _unit(3, {"a"})  # 1 shared
    pairs, _ = _select_structural_pairs([anchor, strong, medium, weak], max_neighbours=1)

    with_anchor = {
        (right.paragraph_number if left.paragraph_number == 0 else left.paragraph_number)
        for left, right, _ in pairs
        if 0 in (left.paragraph_number, right.paragraph_number)
    }
    assert 1 in with_anchor, "the strongest partner must be kept"


def test_pairs_without_shared_entities_are_never_linked() -> None:
    units = [_unit(0, {"x"}), _unit(1, {"y"}), _unit(2, {"z"})]
    pairs, dropped = _select_structural_pairs(units, max_neighbours=5)
    assert pairs == []
    assert dropped == 0


def test_selection_is_deterministic() -> None:
    units = [_unit(i, {"shared", f"own-{i % 3}"}) for i in range(12)]
    first, _ = _select_structural_pairs(units, max_neighbours=4)
    second, _ = _select_structural_pairs(units, max_neighbours=4)
    assert [(x.paragraph_number, y.paragraph_number, n) for x, y, n in first] == [
        (x.paragraph_number, y.paragraph_number, n) for x, y, n in second
    ]
