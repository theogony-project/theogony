"""CSR construction drops self-loops (source == target).

A self-loop carries no Spreading-Activation signal — activation cannot propagate
from a node to itself, and PPR / PageRank zero the diagonal by construction — yet
before this guard a stored self-loop inflated a node's out-degree and cloned
itself into every Constellation. The live symptom was the founding mesh's
identity-attractor `fed_with` self-loops on the poem hub (PHX-1051): a single
query's induced sub-graph was 123 identical self-loops on one node.

These pin the guard in the one shared builder (`build_csr_from_columns`), through
which every CSR consumer — the query hot path (`csr_from_store`), the dream eval,
and `build_csr_from_edges` — flows.
"""

from __future__ import annotations

from theogony.mesh.storage.edges import build_csr_from_columns


def test_self_loop_is_dropped_but_endpoints_survive() -> None:
    csr = build_csr_from_columns(
        source_ids=["A", "A"],
        target_ids=["A", "B"],  # A->A is a self-loop, A->B is real
        weights=[1.0, 0.5],
    )
    # Both nodes stay in the index space (A must remain addressable as a seed).
    assert set(csr.node_ids) == {"A", "B"}
    # Only the real edge survives; the self-loop contributes no nnz.
    assert csr.values.numel() == 1
    ai, bi = csr.id_to_index["A"], csr.id_to_index["B"]
    # The one surviving edge is A->B, and there is no diagonal (A->A) entry.
    row_start = int(csr.crow_indices[ai].item())
    row_end = int(csr.crow_indices[ai + 1].item())
    targets = {int(csr.col_indices[p].item()) for p in range(row_start, row_end)}
    assert targets == {bi}
    assert ai not in targets


def test_node_with_only_a_self_loop_stays_indexed_with_no_edges() -> None:
    csr = build_csr_from_columns(
        source_ids=["X"],
        target_ids=["X"],
        weights=[0.9],
    )
    assert csr.node_ids == ["X"]
    assert csr.values.numel() == 0
    # crow is monotonic and encodes zero out-edges for X.
    assert int(csr.crow_indices[-1].item()) == 0


def test_duplicate_self_loops_all_dropped_real_edges_preserved() -> None:
    # The founding-mesh shape: many identical self-loops on one hub plus a few
    # genuine edges. All self-loops vanish; the genuine edges (and weights) remain.
    hub = "HUB"
    sources = [hub] * 123 + [hub, "P"]
    targets = [hub] * 123 + ["Q", "R"]
    weights = [1.0] * 123 + [0.4, 0.7]
    csr = build_csr_from_columns(source_ids=sources, target_ids=targets, weights=weights)

    assert set(csr.node_ids) == {hub, "P", "Q", "R"}
    assert csr.values.numel() == 2
    vals = sorted(round(v, 3) for v in csr.values.tolist())
    assert vals == [0.4, 0.7]


def test_frame_consistency_still_scales_surviving_edges() -> None:
    csr = build_csr_from_columns(
        source_ids=["A", "B"],
        target_ids=["A", "C"],  # A->A dropped; B->C kept
        weights=[1.0, 1.0],
        frame_consistencies=[0.0, 0.5],
    )
    # conductance = weight * frame_consistency, computed only for the kept edge.
    assert csr.values.numel() == 1
    assert round(float(csr.values[0].item()), 3) == 0.5
