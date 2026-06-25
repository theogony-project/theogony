"""Diversified injection (S3b): MMR ordering + weight-class stratification."""

from __future__ import annotations

from theogony.mesh.retrieval.diversified import (
    SeedCandidate,
    mmr_order,
    select_seeds,
    weight_classes,
)


def test_mmr_prefers_diverse_second_pick() -> None:
    """With a diversity-leaning lambda, MMR picks the novel candidate over a near-duplicate.

    (At lambda=0.5 a near-duplicate of the *query* ties the orthogonal candidate because
    relevance and redundancy cancel; diversity only bites when lambda favours it.)
    """
    query = [1.0, 0.0]
    vectors = [
        [1.0, 0.0],  # 0: identical to query (most relevant)
        [0.98, 0.02],  # 1: near-duplicate of 0 (high relevance, high redundancy)
        [0.0, 1.0],  # 2: orthogonal (low relevance, zero redundancy)
    ]
    order = mmr_order(query, vectors, lambda_=0.3)
    assert order[0] == 0  # most relevant first
    assert order[1] == 2  # diversity beats the redundant near-duplicate


def test_mmr_high_lambda_is_relevance_ranking() -> None:
    query = [1.0, 0.0]
    vectors = [[0.2, 0.98], [0.7, 0.7], [1.0, 0.0]]
    order = mmr_order(query, vectors, lambda_=1.0)
    assert order[0] == 2  # pure relevance -> closest to query first


def test_weight_classes_quantiles() -> None:
    classes = weight_classes([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], n_classes=4)
    assert min(classes) == 0
    assert max(classes) == 3  # a hub class exists
    # Monotone: a larger potential never lands in a lower class.
    assert classes[0] <= classes[-1]


def test_select_seeds_caps_hub_domination() -> None:
    """The most-relevant candidates are all hubs; the cap forces in non-hub seeds."""
    query = [1.0, 0.0, 0.0]
    candidates = []
    # Four high-potential "hub" candidates very close to the query.
    for i in range(4):
        candidates.append(
            SeedCandidate(index=i, node_id=f"hub{i}", vector=[1.0, 0.01 * i, 0.0], potential=100.0)
        )
    # Four low-potential candidates, still query-relevant.
    for i in range(4):
        candidates.append(
            SeedCandidate(
                index=10 + i, node_id=f"leaf{i}", vector=[0.9, 0.1, 0.05 * i], potential=1.0
            )
        )
    seeds = select_seeds(query, candidates, k=6, lambda_=0.6, n_classes=4, max_hub_fraction=0.5)
    assert len(seeds) == 6
    hub_indices = {0, 1, 2, 3}
    chosen_hubs = sum(1 for idx in seeds if idx in hub_indices)
    # With max_hub_fraction=0.5 and k=6, at most 3 hubs may be seeds.
    assert chosen_hubs <= 3
    # And at least one non-hub seed made it in.
    assert any(idx not in hub_indices for idx in seeds)


def test_select_seeds_empty() -> None:
    assert select_seeds([1.0, 0.0], [], k=5) == {}
