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
    graph_inputs_from_extractions,
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


def test_extractions_intern_entities_across_passages_and_keep_declared_relations() -> None:
    extractions = [
        {
            "concepts": [{"label": "Marie Curie"}, {"label": "Polonium"}],
            "relations": [{"source": "Marie Curie", "target": "Polonium"}],
        },
        # Same entity, different casing/punctuation -> must fold to one node.
        {
            "concepts": [{"label": "marie curie."}, {"label": "Sorbonne"}],
            "relations": [
                {"source": "Marie Curie", "target": "Sorbonne"},
                # endpoint never declared as a concept here -> dropped, not invented
                {"source": "Marie Curie", "target": "Pierre Curie"},
            ],
        },
    ]
    names, per_passage, pairs = graph_inputs_from_extractions(extractions)

    assert names.count("marie curie") == 1  # interned once across passages
    curie = names.index("marie curie")
    assert curie in per_passage[0] and curie in per_passage[1]
    # Two real bridges; the relation to the undeclared "Pierre Curie" is not bridged.
    assert len(pairs) == 2
    assert all(curie in pair for pair in pairs)


def test_normalize_reading_payload_maps_provider_aliases() -> None:
    from theogony.mesh.ingestion.reading_schemas import (
        ParagraphReadingOutput,
        normalize_reading_payload,
    )

    # Shape DeepSeek actually returns: `name`/`wikidata_id` instead of `label`/`qids`,
    # `subject`/`predicate`/`object` instead of source/relation_descriptor/target.
    raw = {
        "concepts": [
            {"name": "Marie Curie", "wikidata_id": "Q7186", "type": "person"},
            {"label": "Polonium", "description": "an element"},
            {"description": "no label -> dropped"},
        ],
        "relations": [
            {"subject": "Marie Curie", "predicate": "discovered", "object": "Polonium"},
            {"subject": "Marie Curie"},  # missing target -> dropped
        ],
        "paragraph_concept": {"name": "Curie's discovery"},
    }
    payload = normalize_reading_payload(raw)

    # Validates against the real Kadmos schema (extra="forbid") after normalisation.
    parsed = ParagraphReadingOutput.model_validate(payload)
    assert [c.label for c in parsed.concepts] == ["Marie Curie", "Polonium"]
    assert parsed.concepts[0].entity_type == "person"
    assert len(parsed.relations) == 1
    rel = parsed.relations[0]
    assert (rel.source, rel.relation_descriptor, rel.target) == (
        "Marie Curie",
        "discovered",
        "Polonium",
    )
    assert parsed.paragraph_concept is not None
    assert parsed.paragraph_concept.label == "Curie's discovery"


def test_failed_extraction_contributes_nothing_but_does_not_break() -> None:
    names, per_passage, pairs = graph_inputs_from_extractions(
        [{}, {"concepts": [{"label": "Ada Lovelace"}], "relations": []}]
    )
    assert per_passage[0] == set()  # failed passage carries no entities
    assert names == ["ada lovelace"]
    assert pairs == {}


def test_relation_bridges_are_sparser_than_cooccurrence_on_the_same_passages() -> None:
    # One passage naming four entities: co-occurrence bridges all 6 pairs;
    # the extractor asserted only 1 real relation. Sparser + targeted is the
    # whole point of Kadmos-grade construction.
    extraction = {
        "concepts": [
            {"label": "Alpha"},
            {"label": "Beta"},
            {"label": "Gamma"},
            {"label": "Delta"},
        ],
        "relations": [{"source": "Alpha", "target": "Beta"}],
    }
    _names, per_passage, pairs = graph_inputs_from_extractions([extraction])
    emb_p = torch.eye(1, 3)
    emb_e = torch.eye(4, 3)

    cheap = build_qa_graph(emb_p, emb_e, per_passage, knn_k=0)
    kadmos = build_qa_graph(emb_p, emb_e, per_passage, knn_k=0, relation_pairs=pairs)

    assert len(cheap.entity_edges) == 12  # 6 undirected pairs, both directions
    assert len(kadmos.entity_edges) == 2  # 1 undirected pair, both directions
    # Containment is identical — only the bridges differ.
    assert cheap.containment_edges == kadmos.containment_edges


def test_entity_seeding_places_mass_on_entity_nodes_not_passages() -> None:
    from theogony.mesh.eval.qa_retrieval import build_seed_vector

    passage_unit = torch.eye(2, 3)
    entity_unit = torch.tensor([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    query = torch.tensor([0.0, 1.0, 0.0])  # matches passage 1 and entity 0
    n_nodes = 4  # 2 passages + 2 entities

    passage_seed = build_seed_vector(
        query, passage_unit, entity_unit, n_nodes, mode="passage", top_s=1
    )
    entity_seed = build_seed_vector(
        query, passage_unit, entity_unit, n_nodes, mode="entity", top_s=1
    )
    hybrid = build_seed_vector(query, passage_unit, entity_unit, n_nodes, mode="hybrid", top_s=1)

    assert passage_seed[:2].sum() > 0 and passage_seed[2:].sum() == 0
    assert entity_seed[:2].sum() == 0 and entity_seed[2:].sum() > 0  # entity indices offset by P
    assert hybrid[:2].sum() > 0 and hybrid[2:].sum() > 0


def test_rescue_rate_is_zero_when_the_graph_cannot_reach_missed_gold() -> None:
    """A disconnected gold passage can never be rescued — the diagnostic must say so.

    Needs a corpus meaningfully larger than k: at 5 or fewer passages every recall@5
    is trivially 1.0 and the diagnostic cannot discriminate. Here the gold sits at a
    high index with no edges, while six other passages receive real activation and
    crowd it out of the top-5.
    """
    from theogony.mesh.eval.qa_retrieval import evaluate_seeding

    n = 10
    passage_emb = torch.zeros((n, 3))
    passage_emb[0] = torch.tensor([1.0, 0.0, 0.0])  # query match, gets seeded
    for i in range(1, 7):  # reachable neighbours, pulled up by the shared entity
        passage_emb[i] = torch.tensor([0.0, 1.0, 0.0])
    passage_emb[9] = torch.tensor([0.0, 0.0, 1.0])  # the gold: dissimilar and isolated
    entity_emb = torch.tensor([[1.0, 0.0, 0.0]])
    ents: list[set[int]] = [{0}] + [{0}] * 6 + [set(), set(), set()]

    graph = build_qa_graph(passage_emb, entity_emb, ents, knn_k=0)
    questions = [QAQuestion(qid="q", question="q", answer="a", gold_idxs={9})]
    question_emb = torch.tensor([[1.0, 0.0, 0.0]])

    res = evaluate_seeding(
        graph, passage_emb, question_emb, questions, modes=["passage"], seed_counts=[1]
    )[0]
    assert res.gold_missed_by_seeds == 1  # the gold was not seeded
    assert res.rescued_gold == 0  # and the graph cannot reach it
    assert res.rescue_rate == 0.0


def test_rescue_rate_counts_gold_the_graph_reaches_beyond_the_seeds() -> None:
    from theogony.mesh.eval.qa_retrieval import evaluate_seeding

    # P0 matches the query and shares entity 0 with the gold P1; P2/P3 are noise.
    passage_emb = torch.tensor(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]
    )
    entity_emb = torch.tensor([[0.5, 0.5, 0.0]])
    ents: list[set[int]] = [{0}, {0}, set(), set()]  # the bridge P0 -> e0 -> P1
    graph = build_qa_graph(passage_emb, entity_emb, ents, knn_k=0)
    questions = [QAQuestion(qid="q", question="q", answer="a", gold_idxs={1})]
    question_emb = torch.tensor([[1.0, 0.0, 0.0]])

    res = evaluate_seeding(
        graph, passage_emb, question_emb, questions, modes=["passage"], seed_counts=[1]
    )[0]
    # Seeding only reaches P0, so the gold P1 is "missed by seeds" — and the entity
    # bridge rescues it into the top-5. That is exactly SA's unique contribution.
    assert res.gold_missed_by_seeds == 1
    assert res.rescued_gold == 1
    assert res.rescue_rate == 1.0
    assert res.sa_recall_at_5 == 1.0


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
