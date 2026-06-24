"""Unit tests for the link-prediction eval harness.

These run on a tiny synthetic CSR — no Lance, no embedding model — so they are
fast and deterministic, and they pin the ranking/metric maths that the headline
number depends on.

Graph (directed, unit weights)::

    0 -> 1     0 -> 2     1 -> 3     2 -> 3

so node 3 is reachable from 0 only via two hops.
"""

from __future__ import annotations

import math

import torch

from theogony.mesh.eval.link_prediction import (
    build_context,
    build_csr_over_nodes,
    build_heldout_testset,
    evaluate,
    filtered_rank,
    in_degree_from_csr,
    propagate,
    rank_metrics,
    row_normalized_values,
    score_head,
    split_edge_rows,
)
from theogony.mesh.storage.edges import EdgeCSR


def _tiny_csr() -> EdgeCSR:
    # out-edges: 0->1, 0->2, 1->3, 2->3
    return EdgeCSR(
        crow_indices=torch.tensor([0, 2, 3, 4, 4], dtype=torch.int64),
        col_indices=torch.tensor([1, 2, 3, 3], dtype=torch.int64),
        values=torch.tensor([1.0, 1.0, 1.0, 1.0], dtype=torch.float32),
        node_ids=["0", "1", "2", "3"],
        id_to_index={"0": 0, "1": 1, "2": 2, "3": 3},
    )


def test_in_degree_counts_incoming_edges() -> None:
    deg = in_degree_from_csr(_tiny_csr())
    assert deg.tolist() == [0.0, 1.0, 1.0, 2.0]


def test_row_normalized_values_divide_by_out_strength() -> None:
    vals = row_normalized_values(_tiny_csr())
    # node 0 has two out-edges -> 0.5 each; nodes 1,2 have one -> 1.0
    assert torch.allclose(vals, torch.tensor([0.5, 0.5, 1.0, 1.0]))


def test_propagate_reaches_two_hop_neighbour() -> None:
    csr = _tiny_csr()
    adj = torch.sparse_csr_tensor(
        csr.crow_indices, csr.col_indices, csr.values, size=(4, 4), dtype=torch.float32
    )
    one_hop = propagate(adj, head_index=0, n=4, hops=1, damping=1.0)
    assert one_hop.tolist() == [0.0, 1.0, 1.0, 0.0]
    two_hop = propagate(adj, head_index=0, n=4, hops=2, damping=1.0)
    assert two_hop.tolist() == [0.0, 0.0, 0.0, 2.0]


def test_filtered_rank_no_ties() -> None:
    scores = torch.tensor([0.0, 0.0, 0.0, 2.0])
    # head 0 excluded; tail 3 has the unique top score among {1,2,3}
    assert filtered_rank(scores, head_index=0, tail_index=3, known_tail_indices=set()) == 1.0


def test_filtered_rank_averages_ties() -> None:
    scores = torch.tensor([5.0, 1.0, 1.0, 1.0])
    # candidates {1,2,3} all tie at 1.0 -> average rank (1+2+3)/3 = 2.0
    assert filtered_rank(scores, head_index=0, tail_index=1, known_tail_indices=set()) == 2.0


def test_filtered_rank_removes_other_known_tails() -> None:
    scores = torch.tensor([5.0, 1.0, 1.0, 1.0])
    # known tail 2 is filtered out -> candidates {1,3} tie -> rank (1+2)/2 = 1.5
    assert filtered_rank(scores, head_index=0, tail_index=1, known_tail_indices={2}) == 1.5


def test_rank_metrics_mrr_and_hits() -> None:
    metrics = rank_metrics("x", [1.0, 2.0, 4.0])
    assert math.isclose(metrics.mrr, (1.0 + 0.5 + 0.25) / 3, rel_tol=1e-9)
    assert math.isclose(metrics.hits_at_1, 1 / 3, rel_tol=1e-9)
    assert math.isclose(metrics.hits_at_3, 2 / 3, rel_tol=1e-9)
    assert metrics.hits_at_10 == 1.0
    assert math.isclose(metrics.mean_rank, 7 / 3, rel_tol=1e-9)


def test_rank_metrics_empty_is_zeroed() -> None:
    metrics = rank_metrics("x", [])
    assert metrics.mrr == 0.0 and metrics.mean_rank == 0.0


def test_score_head_degree_and_knn() -> None:
    csr = _tiny_csr()
    sem = torch.eye(4, dtype=torch.float32)  # orthonormal -> knn picks the head only
    ctx = build_context(csr, sem)
    degree = score_head(ctx, "degree", 0, hops=2, damping=0.5)
    assert degree.tolist() == [0.0, 1.0, 1.0, 2.0]
    knn = score_head(ctx, "knn", 1, hops=2, damping=0.5)
    assert knn.argmax().item() == 1


def test_evaluate_ranks_true_tail_top_for_structure() -> None:
    csr = _tiny_csr()
    sem = torch.eye(4, dtype=torch.float32)
    ctx = build_context(csr, sem)
    # held-out target: predict tail 3 from head 0 (true 2-hop relation)
    metrics = evaluate(
        ctx,
        test_pairs=[(0, 3)],
        known_tails_by_head={0: {1, 2}},  # 0's direct neighbours are "known"
        hops=2,
        damping=1.0,
    )
    # sa_raw / sa_degnorm should rank node 3 first (only activated node after 2 hops)
    assert metrics["sa_raw"].mrr == 1.0
    assert metrics["sa_degnorm"].mrr == 1.0


def test_build_heldout_testset_filters_and_samples(tmp_path) -> None:
    triplet_file = tmp_path / "triplets.txt"
    triplet_file.write_text(
        "\n".join(
            [
                "Q1\tP1\tQ2",  # qualifies
                "Q2\tP2\tQ3",  # qualifies
                "Q1\tP3\tQ1",  # self-loop -> excluded
                "Q1\tP4\tQ9",  # Q9 not in mesh -> excluded
                "Q3\tP5\tQ1",  # already a known edge -> excluded
                "Q2\tP6\tQ1",  # qualifies
            ]
        ),
        encoding="utf-8",
    )
    mesh_qids = {"Q1", "Q2", "Q3"}
    known_pairs = {("Q3", "Q1")}
    triples = build_heldout_testset(triplet_file, mesh_qids, known_pairs, max_test=10, seed=0)
    pairs = {(h, t) for h, _r, t in triples}
    assert pairs == {("Q1", "Q2"), ("Q2", "Q3"), ("Q2", "Q1")}
    assert all(h != t for h, _r, t in triples)


def test_split_edge_rows_is_deterministic_and_partitions() -> None:
    rows = [(str(i), str(i + 1), 1.0) for i in range(10)]
    train, test = split_edge_rows(rows, test_fraction=0.3, seed=7)
    assert len(test) == 3
    assert len(train) == 7
    # disjoint and complete
    assert set(train).isdisjoint(set(test))
    assert set(train) | set(test) == set(rows)
    # deterministic given the seed
    train2, test2 = split_edge_rows(rows, test_fraction=0.3, seed=7)
    assert train == train2 and test == test2


def test_build_csr_over_nodes_pins_universe_and_fills_train_only() -> None:
    node_ids = ["0", "1", "2", "3"]
    # only the 0->1 train edge survives; node 3 has no edges but stays in universe
    csr = build_csr_over_nodes(node_ids, [("0", "1", 2.0), ("9", "1", 1.0)])
    assert csr.node_ids == node_ids
    assert len(csr.crow_indices) == len(node_ids) + 1
    # the out-of-universe ("9") row is dropped; only one nnz remains
    assert csr.values.tolist() == [2.0]
    assert csr.col_indices.tolist() == [1]
    assert in_degree_from_csr(csr).tolist() == [0.0, 1.0, 0.0, 0.0]


def test_build_heldout_testset_respects_max_test(tmp_path) -> None:
    triplet_file = tmp_path / "triplets.txt"
    triplet_file.write_text("\n".join(f"Q1\tP1\tQ{i}" for i in range(2, 50)), encoding="utf-8")
    mesh_qids = {f"Q{i}" for i in range(1, 50)}
    triples = build_heldout_testset(triplet_file, mesh_qids, set(), max_test=5, seed=0)
    assert len(triples) == 5
