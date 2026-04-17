"""Tests for core data models."""

from datetime import UTC, datetime

import pytest

from theogony.core.model import (
    Constellation,
    ConstellationEdge,
    ConstellationNode,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
    NodeScores,
    NodeType,
    SourceRef,
)
from theogony.core.vitality import (
    compute_freshness,
    connectivity_score,
    dynamic_vitality_threshold,
    promotion_ready,
)


def make_source_ref() -> SourceRef:
    return SourceRef(
        source_type="gutenberg",
        identifier="Gutenberg:12345",
        location="chapter_03:offset_18433",
        snippet="After long wandering we reached the temple city of Uttar Kashi around midnight.",
        language="en",
    )


def make_node(label: str = "Test Node", layer: Layer = Layer.EPHEMERA) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=NodeType.PLACE,
        layer=layer,
        source_ref=make_source_ref(),
    )


class TestKnowledgeNode:
    def test_id_is_generated(self) -> None:
        node = make_node()
        assert node.id.startswith("AKA-")

    def test_default_layer_is_ephemera(self) -> None:
        node = make_node()
        assert node.layer == Layer.EPHEMERA

    def test_vitality_within_range(self) -> None:
        node = make_node()
        assert 0.0 <= node.vitality <= 1.0

    def test_can_be_promoted_when_scores_sufficient(self) -> None:
        node = make_node()
        node.scores.confidence = 0.8
        node.scores.connectivity = 0.4
        assert node.can_be_promoted()

    def test_cannot_be_promoted_with_low_connectivity(self) -> None:
        node = make_node()
        node.scores.confidence = 0.9
        node.scores.connectivity = 0.05
        assert not node.can_be_promoted()

    def test_cannot_be_promoted_with_low_confidence(self) -> None:
        node = make_node()
        node.scores.confidence = 0.3
        node.scores.connectivity = 0.8
        assert not node.can_be_promoted()

    def test_wikidata_id_extraction(self) -> None:
        node = make_node()
        node.external_ids["wikidata"] = "Q806463"
        assert node.wikidata_id == "Q806463"

    def test_wikidata_id_none_when_absent(self) -> None:
        node = make_node()
        assert node.wikidata_id is None

    def test_embedding_model_id_default_is_none(self) -> None:
        node = make_node()
        assert node.embedding_model_id is None
        assert node.embedding_dim is None

    def test_embedding_model_id_can_be_set(self) -> None:
        node = KnowledgeNode(
            label="Uttarkashi",
            source_ref=make_source_ref(),
            embedding=[0.1] * 384,
            embedding_model_id="BAAI/bge-small-en-v1.5@v1",
            embedding_dim=384,
        )
        assert node.embedding_model_id == "BAAI/bge-small-en-v1.5@v1"
        assert node.embedding_dim == 384

    def test_embedding_dim_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            KnowledgeNode(
                label="x",
                source_ref=make_source_ref(),
                embedding_dim=0,
            )


class TestKnowledgeEdge:
    def test_id_is_generated(self) -> None:
        edge = KnowledgeEdge(
            source_id="AKA-abc",
            target_id="AKA-def",
            relation_type="P131",
        )
        assert edge.id.startswith("EDGE-")

    def test_weight_within_range(self) -> None:
        edge = KnowledgeEdge(
            source_id="AKA-abc",
            target_id="AKA-def",
            relation_type="REACHED",
            weight=0.72,
        )
        assert 0.0 <= edge.weight <= 1.0

    def test_evidence_span_default_is_none(self) -> None:
        edge = KnowledgeEdge(
            source_id="AKA-abc",
            target_id="AKA-def",
            relation_type="MET",
        )
        assert edge.evidence_span is None

    def test_evidence_span_carries_verbatim_substring(self) -> None:
        sentence = "Harrer reached Uttarkashi at midnight."
        edge = KnowledgeEdge(
            source_id="AKA-harrer",
            target_id="AKA-uttarkashi",
            relation_type="REACHED",
            evidence_span="reached Uttarkashi",
        )
        assert edge.evidence_span is not None
        assert edge.evidence_span in sentence


class TestNodeScores:
    def test_vitality_computation(self) -> None:
        scores = NodeScores(
            confidence=1.0,
            relevance=1.0,
            connectivity=1.0,
            freshness=1.0,
        )
        assert scores.vitality() == pytest.approx(1.0)

    def test_vitality_all_zero(self) -> None:
        scores = NodeScores(
            confidence=0.0,
            relevance=0.0,
            connectivity=0.0,
            freshness=0.0,
        )
        assert scores.vitality() == pytest.approx(0.0)


class TestConstellation:
    def test_empty_constellation_is_not_sufficient(self) -> None:
        c = Constellation(query="test")
        assert not c.is_sufficient

    def test_constellation_with_nodes_and_edges_may_be_sufficient(self) -> None:
        full_nodes = [make_node(f"Node {i}") for i in range(3)]
        full_edge = KnowledgeEdge(
            source_id=full_nodes[0].id,
            target_id=full_nodes[1].id,
            relation_type="RELATED_TO",
        )
        c = Constellation(
            query="test",
            nodes=[ConstellationNode.from_knowledge_node(n) for n in full_nodes],
            edges=[ConstellationEdge.from_knowledge_edge(full_edge)],
        )
        assert c.is_sufficient


class TestConstellationDTOs:
    def test_constellation_node_omits_embedding(self) -> None:
        node = make_node("Heinrich Harrer")
        node.embedding = [0.1, 0.2, 0.3]
        ConstellationNode.from_knowledge_node(node)  # constructs OK
        assert "embedding" not in ConstellationNode.model_fields

    def test_constellation_node_carries_label_and_source_ref(self) -> None:
        node = make_node("Uttarkashi")
        slim = ConstellationNode.from_knowledge_node(node)
        assert slim.id == node.id
        assert slim.label == "Uttarkashi"
        assert slim.node_type == NodeType.PLACE
        assert slim.layer == Layer.EPHEMERA
        assert slim.confidence == node.scores.confidence
        assert slim.source_ref.source_type == "gutenberg"

    def test_constellation_edge_strips_provenance(self) -> None:
        edge = KnowledgeEdge(
            source_id="AKA-a",
            target_id="AKA-b",
            relation_type="MET",
            weight=0.7,
            confidence=0.6,
        )
        slim = ConstellationEdge.from_knowledge_edge(edge)
        assert slim.source_id == "AKA-a"
        assert slim.target_id == "AKA-b"
        assert slim.relation_type == "MET"
        assert slim.weight == 0.7
        assert slim.confidence == 0.6
        assert "source_ref" not in ConstellationEdge.model_fields
        assert "properties" not in ConstellationEdge.model_fields

    def test_serialised_constellation_does_not_leak_embeddings(self) -> None:
        nodes = [make_node(f"Node {i}") for i in range(3)]
        for n in nodes:
            n.embedding = [0.42] * 384
        full_edge = KnowledgeEdge(
            source_id=nodes[0].id,
            target_id=nodes[1].id,
            relation_type="RELATED_TO",
        )
        c = Constellation(
            query="test",
            nodes=[ConstellationNode.from_knowledge_node(n) for n in nodes],
            edges=[ConstellationEdge.from_knowledge_edge(full_edge)],
        )
        dumped = c.model_dump_json()
        assert "0.42" not in dumped
        assert "embedding" not in dumped


class TestVitality:
    def test_freshness_starts_at_one_for_new_node(self) -> None:
        now = datetime.now(tz=UTC)
        score = compute_freshness(created_at=now)
        assert score > 0.99

    def test_freshness_decays_over_time(self) -> None:
        from datetime import timedelta
        old = datetime.now(tz=UTC) - timedelta(days=365)
        score = compute_freshness(created_at=old, half_life_days=365.0)
        assert abs(score - 0.5) < 0.01

    def test_dynamic_threshold_rises_under_pressure(self) -> None:
        baseline = dynamic_vitality_threshold(storage_pressure=0.0)
        high = dynamic_vitality_threshold(storage_pressure=0.9)
        assert high > baseline

    def test_connectivity_score_zero_edges(self) -> None:
        assert connectivity_score(0) == 0.0

    def test_connectivity_score_saturates(self) -> None:
        assert connectivity_score(10000) == pytest.approx(1.0)

    def test_promotion_ready(self) -> None:
        assert promotion_ready(confidence=0.8, connectivity=0.4)
        assert not promotion_ready(confidence=0.3, connectivity=0.8)
        assert not promotion_ready(confidence=0.8, connectivity=0.05)
