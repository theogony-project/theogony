"""Typed edges conduct more strongly than observed adjacency — when asked to.

An edge saying `father_of` asserts a relation; one saying
`co_mentions_in_paragraph` records that two names shared a paragraph.
Propagation cannot tell them apart, and on the founding mesh the second kind
outnumbers the first fifteen to one. This scales the first kind up.

The lever is off by default and these tests pin that as hard as they pin the
behaviour: a substrate whose retrieval quietly changed under a library upgrade
would be worse than one that never had the lever.
"""

from __future__ import annotations

from datetime import UTC, datetime

import torch
from ulid import ULID

from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import EdgeCSR, build_csr_from_edges
from theogony.mesh.typed_edges import build_typed_boosted_csr, typed_edge_mask


def _mesh() -> tuple[EdgeCSR, dict[tuple[str, str], str | None]]:
    """Three nodes joined twice: once by a claim, once by a co-mention."""
    now = datetime.now(UTC)
    ids = [ULID() for _ in range(3)]
    edges = [
        Edge(source_id=ids[0], target_id=ids[1], weight=1.0, born_at=now, last_fired_at=now),
        Edge(source_id=ids[1], target_id=ids[2], weight=1.0, born_at=now, last_fired_at=now),
    ]
    descriptors: dict[tuple[str, str], str | None] = {
        (str(ids[0]), str(ids[1])): "father_of",  # resolves to P40
        (str(ids[1]), str(ids[2])): "co_mentions_in_paragraph",  # resolves to nothing
    }
    return build_csr_from_edges(edges), descriptors


def test_only_the_asserted_edge_is_marked_typed() -> None:
    csr, descriptors = _mesh()
    mask = typed_edge_mask(csr, descriptors)
    assert mask.sum().item() == 1, "a co-mention is not a claim about a relation"


def test_the_boost_scales_typed_edges_and_leaves_the_rest_alone() -> None:
    csr, descriptors = _mesh()
    boosted = build_typed_boosted_csr(csr, descriptors, boost=30.0)
    mask = typed_edge_mask(csr, descriptors)
    assert torch.allclose(boosted.values[mask], csr.values[mask] * 30.0)
    assert torch.allclose(boosted.values[~mask], csr.values[~mask])


def test_boost_of_one_is_the_identity_and_costs_nothing() -> None:
    """The lever is off by default; off must mean the same object, not an equal one."""
    csr, descriptors = _mesh()
    assert build_typed_boosted_csr(csr, descriptors, boost=1.0) is csr


def test_the_shape_of_the_graph_is_untouched() -> None:
    """Re-weighting, not rewiring — every node stays reachable.

    This is the whole reason the lever weights rather than selects. Restricting
    propagation to typed edges scored fourteen points worse on narrative
    questions, because the typed subgraph reached only 121 of 163 gold entities
    (PHX-1070). Nothing here may drop an edge.
    """
    csr, descriptors = _mesh()
    boosted = build_typed_boosted_csr(csr, descriptors, boost=30.0)
    assert boosted.node_ids == csr.node_ids
    assert torch.equal(boosted.crow_indices, csr.crow_indices)
    assert torch.equal(boosted.col_indices, csr.col_indices)
    assert (boosted.values > 0).all(), "no edge may be zeroed"


def test_an_empty_mesh_does_not_raise() -> None:
    empty = build_csr_from_edges([])
    assert build_typed_boosted_csr(empty, {}, boost=30.0) is empty
    assert typed_edge_mask(empty, {}).numel() == 0
