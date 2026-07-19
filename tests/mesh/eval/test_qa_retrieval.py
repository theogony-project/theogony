"""QA passage-retrieval benchmark — offline unit tests on synthetic fixtures.

The load-bearing test is ``test_sa_finds_multihop_bridge_that_knn_misses``: a
hand-built case where the gold passage is reachable from the query only through
a shared-entity bridge, so kNN (pure geometry) misses it while Spreading
Activation recovers it. If the harness cannot show that on a case constructed to
exhibit it, it cannot measure it on real data.
"""

from __future__ import annotations

import torch

from theogony.mesh.eval.qa_retrieval import (
    BM25,
    QAQuestion,
    build_qa_graph,
    density_sweep,
    evaluate_methods,
    mrr_at_k,
    recall_at_k,
)


def test_bm25_ranks_the_matching_document_first() -> None:
    docs = [["the", "cat", "sat"], ["a", "dog", "ran"], ["birds", "fly", "high"]]
    bm25 = BM25(docs=docs)
    scores = bm25.scores("dog")
    assert int(torch.argmax(scores).item()) == 1


def test_recall_and_mrr() -> None:
    ranked = [3, 1, 7, 2, 9]
    assert recall_at_k(ranked, {1, 2}, 2) == 0.5  # only passage 1 in top-2
    assert recall_at_k(ranked, {1, 2}, 5) == 1.0  # both in top-5
    assert recall_at_k(ranked, set(), 5) == 0.0
    assert mrr_at_k(ranked, {7}, 10) == 1.0 / 3.0
    assert mrr_at_k(ranked, {42}, 10) == 0.0


def test_graph_is_symmetric_and_passages_indexed_first() -> None:
    passage_emb = torch.eye(3)
    entity_emb = torch.eye(2, 3)
    ents = [{0}, {0, 1}, {1}]  # P0-e0, P1-e0+e1, P2-e1
    g = build_qa_graph(passage_emb, entity_emb, ents, knn_k=0)
    assert g.node_ids[:3] == ["p0", "p1", "p2"]
    assert g.passage_indices == [0, 1, 2]
    # containment is symmetric
    assert ("p0", "e0", 1.0) in g.containment_edges
    assert ("e0", "p0", 1.0) in g.containment_edges
    # e0 and e1 co-occur in P1 → one symmetric entity bridge
    ent_pairs = {(s, t) for s, t, _w in g.entity_edges}
    assert ("e0", "e1") in ent_pairs and ("e1", "e0") in ent_pairs


def _multihop_fixture() -> tuple[
    torch.Tensor, torch.Tensor, list[set[int]], list[QAQuestion], torch.Tensor
]:
    # P0 ~ query; P1 = gold (bridged to P0 via entity 0); P2, P3 = distractors.
    # P3 is geometrically close to the query but has NO bridge — the kNN trap.
    passage_emb = torch.tensor(
        [
            [1.0, 0.0, 0.0],  # P0 — query-relevant
            [0.0, 1.0, 0.0],  # P1 — gold, dissimilar to query
            [0.0, 0.0, 1.0],  # P2 — distractor
            [0.9, 0.1, 0.0],  # P3 — looks relevant to kNN, no bridge
        ]
    )
    # entity 0 shared by P0 and P1 (the bridge); entity 1 in P2; entity 2 in P3.
    entity_emb = torch.tensor([[0.5, 0.5, 0.0], [0.0, 0.0, 1.0], [0.9, 0.0, 0.1]])
    ents = [{0}, {0}, {1}, {2}]
    questions = [
        QAQuestion(qid="q0", question="who bridges via entity zero", answer="p1", gold_idxs={1})
    ]
    question_emb = torch.tensor([[1.0, 0.0, 0.0]])  # ~ P0
    return passage_emb, entity_emb, ents, questions, question_emb


def test_sa_finds_multihop_bridge_that_knn_misses() -> None:
    passage_emb, entity_emb, ents, questions, question_emb = _multihop_fixture()
    # knn_k=0: the ONLY path P0→P1 is the shared entity, isolating the structural signal.
    graph = build_qa_graph(passage_emb, entity_emb, ents, knn_k=0)
    bm25 = BM25(docs=[["p0"], ["p1"], ["p2"], ["p3"]])
    metrics = {
        m.method: m
        for m in evaluate_methods(graph, passage_emb, question_emb, bm25, questions, seed_top_s=1)
    }

    # kNN is trapped: top-2 = {P0, P3}, missing the gold P1.
    assert metrics["knn"].recall_at_2 == 0.0
    # Both SA variants ride the entity bridge P0 → e0 → P1 and recover the gold.
    assert metrics["sa_raw"].recall_at_2 == 1.0
    assert metrics["sa_ppr"].recall_at_2 == 1.0


def test_density_sweep_sa_pulls_away_from_knn_as_bridges_grow() -> None:
    passage_emb, entity_emb, ents, questions, question_emb = _multihop_fixture()
    graph = build_qa_graph(passage_emb, entity_emb, ents, knn_k=0)
    levels = density_sweep(
        graph, passage_emb, question_emb, questions, fractions=[0.0, 1.0], seed_top_s=1
    )
    by_frac = {lvl.entity_edge_fraction: lvl for lvl in levels}
    # With no bridges, SA cannot beat kNN on the trap; with bridges, it does.
    assert by_frac[0.0].sa_ppr_minus_knn_at_5 <= by_frac[1.0].sa_ppr_minus_knn_at_5
    assert by_frac[1.0].sa_ppr_recall_at_5 == 1.0
