"""Unit tests for edge materialisation (Plan §2.5, §9.5)."""

from __future__ import annotations

from theogony.core.model import EdgeType, KnowledgeNode, NodeScores, NodeType, SourceRef
from theogony.extraction.edges import (
    EdgeMaterialisation,
    build_resolved_lookup,
    materialise_edges,
)
from theogony.extraction.ner import Mention
from theogony.extraction.relations import ExtractedRelation
from theogony.extraction.resolve import ResolvedMention
from theogony.extraction.sentence import Sentence

# ---------------------------------------------------------------- fixtures


def _book_ref() -> SourceRef:
    return SourceRef(
        source_type="gutenberg",
        identifier="944",
        url="https://www.gutenberg.org/ebooks/944",
        language="en",
    )


def _node(label: str, *, node_type: NodeType = NodeType.PERSON) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=node_type,
        external_ids={"wikidata": f"Q{abs(hash(label)) % 1_000_000}"},
        source_ref=_book_ref(),
        scores=NodeScores(confidence=0.75),
        resolution_tier=3,
    )


def _mention(text: str, label: str, *, sentence_index: int = 0, offset: int = 0) -> Mention:
    return Mention(
        text=text,
        label=label,
        sentence_index=sentence_index,
        start_char_in_sentence=offset,
        end_char_in_sentence=offset + len(text),
        start_char_in_source=offset,
        end_char_in_source=offset + len(text),
    )


def _resolved(text: str, label: str, node: KnowledgeNode) -> ResolvedMention:
    return ResolvedMention(
        mentions=[_mention(text, label)],
        node=node,
        tier=node.resolution_tier or 3,
        chosen_qid=node.external_ids.get("wikidata"),
        candidates_considered=[],
    )


def _relation(
    subject: str,
    obj: str,
    *,
    relation_type: str = "REACHED",
    evidence_span: str = "",
    confidence: float = 0.85,
    is_other: bool = False,
) -> ExtractedRelation:
    return ExtractedRelation(
        subject_text=subject,
        object_text=obj,
        relation_type=relation_type,
        evidence_span=evidence_span or f"{subject} {relation_type.lower()} {obj}",
        confidence=confidence,
        is_other=is_other,
    )


def _sentence(idx: int, text: str) -> Sentence:
    return Sentence(index=idx, text=text, start_char=0, end_char=len(text))


# ---------------------------------------------------------------- lookup


class TestBuildResolvedLookup:
    def test_maps_every_mention_surface(self) -> None:
        node_h = _node("Harrer")
        node_l = _node("Lhasa", node_type=NodeType.PLACE)
        rm_h = _resolved("Harrer", "PERSON", node_h)
        rm_l = _resolved("Lhasa", "GPE", node_l)
        lookup = build_resolved_lookup([rm_h, rm_l])
        assert lookup["harrer"] == node_h.id
        assert lookup["lhasa"] == node_l.id

    def test_dedup_group_maps_all_surface_variants(self) -> None:
        # ResolvedMention contains multiple Mentions for repeated
        # surface forms ("Tibet", "TIBET", "tibet") — every variant
        # must map to the same node.id under fully_normalise.
        node_t = _node("Tibet", node_type=NodeType.PLACE)
        rm = ResolvedMention(
            mentions=[
                _mention("Tibet", "GPE", sentence_index=0),
                _mention("TIBET", "GPE", sentence_index=5, offset=10),
                _mention("tibet", "GPE", sentence_index=12, offset=20),
            ],
            node=node_t,
            tier=4,
            chosen_qid="Q17",
            candidates_considered=[],
        )
        lookup = build_resolved_lookup([rm])
        # All three surface forms normalise to the same key.
        assert len(lookup) == 1
        assert lookup["tibet"] == node_t.id

    def test_collision_logs_and_keeps_last(self, caplog) -> None:  # type: ignore[no-untyped-def]
        # Two ResolvedMentions with the same normalised surface
        # ("Apple" PERSON vs ORG) — last one wins, warning logged.
        n1 = _node("Apple", node_type=NodeType.PERSON)
        n2 = _node("Apple Inc.", node_type=NodeType.ORGANIZATION)
        rm1 = _resolved("Apple", "PERSON", n1)
        rm2 = _resolved("Apple", "ORG", n2)
        with caplog.at_level("WARNING"):
            lookup = build_resolved_lookup([rm1, rm2])
        # Last wins.
        assert lookup["apple"] == n2.id
        assert any("two distinct node IDs" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------- materialisation


class TestMaterialiseEdges:
    def test_happy_path_creates_edge_with_evidence_and_source_ref(self) -> None:
        node_h = _node("Harrer")
        node_l = _node("Lhasa", node_type=NodeType.PLACE)
        lookup = build_resolved_lookup(
            [_resolved("Harrer", "PERSON", node_h), _resolved("Lhasa", "GPE", node_l)]
        )
        rel = _relation("Harrer", "Lhasa", relation_type="REACHED")
        sent = _sentence(7, "Harrer reached Lhasa.")

        result = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=sent,
        )

        assert len(result.edges) == 1
        edge = result.edges[0]
        assert edge.source_id == node_h.id
        assert edge.target_id == node_l.id
        assert edge.relation_type == "REACHED"
        assert edge.confidence == 0.85
        assert edge.evidence_span == "Harrer reached Lhasa"
        assert edge.epistemic_type == EdgeType.EXTRACTION
        # Sentence-scoped SourceRef on the edge.
        assert edge.source_ref is not None
        assert edge.source_ref.location == "sentence:7"
        assert edge.source_ref.snippet == "Harrer reached Lhasa."
        assert edge.source_ref.identifier == "944"
        # Audit fields preserved on the edge.
        assert edge.properties["extracted_subject_text"] == "Harrer"
        assert edge.properties["extracted_object_text"] == "Lhasa"
        assert edge.properties["is_other_bucket"] is False

    def test_drop_subject_unresolved(self) -> None:
        node_l = _node("Lhasa", node_type=NodeType.PLACE)
        lookup = build_resolved_lookup([_resolved("Lhasa", "GPE", node_l)])
        rel = _relation("Harrer", "Lhasa")  # Harrer NOT in lookup

        result = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )

        assert result.edges == []
        assert result.dropped_subject_unresolved == 1
        assert result.dropped_object_unresolved == 0

    def test_drop_object_unresolved(self) -> None:
        node_h = _node("Harrer")
        lookup = build_resolved_lookup([_resolved("Harrer", "PERSON", node_h)])
        rel = _relation("Harrer", "Lhasa")  # Lhasa NOT in lookup

        result = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )

        assert result.edges == []
        assert result.dropped_object_unresolved == 1
        assert result.dropped_subject_unresolved == 0

    def test_drop_self_loop(self) -> None:
        # Plan §2.11.4: "no edges with source_id == target_id".
        node_h = _node("Harrer")
        lookup = build_resolved_lookup([_resolved("Harrer", "PERSON", node_h)])
        rel = _relation("Harrer", "Harrer", relation_type="MET")

        result = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "Harrer met Harrer."),
        )

        assert result.edges == []
        assert result.dropped_self_loop == 1

    def test_case_variant_subject_resolves_via_normalisation(self) -> None:
        # LLM returns "HARRER" (uppercase); resolver minted under
        # "Harrer". fully_normalise unifies them.
        node_h = _node("Harrer")
        node_l = _node("Lhasa", node_type=NodeType.PLACE)
        lookup = build_resolved_lookup(
            [_resolved("Harrer", "PERSON", node_h), _resolved("Lhasa", "GPE", node_l)]
        )
        rel = _relation("HARRER", "lhasa")

        result = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )
        assert len(result.edges) == 1

    def test_other_bucket_relation_is_kept_with_flag(self) -> None:
        node_h = _node("Harrer")
        node_a = _node("Aufschnaiter")
        lookup = build_resolved_lookup(
            [_resolved("Harrer", "PERSON", node_h), _resolved("Aufschnaiter", "PERSON", node_a)]
        )
        rel = _relation(
            "Harrer",
            "Aufschnaiter",
            relation_type="OTHER",
            is_other=True,
        )

        result = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )
        assert len(result.edges) == 1
        assert result.edges[0].relation_type == "OTHER"
        assert result.edges[0].properties["is_other_bucket"] is True

    def test_no_central_sentence_omits_source_ref(self) -> None:
        node_h = _node("Harrer")
        node_l = _node("Lhasa", node_type=NodeType.PLACE)
        lookup = build_resolved_lookup(
            [_resolved("Harrer", "PERSON", node_h), _resolved("Lhasa", "GPE", node_l)]
        )
        result = materialise_edges(
            relations=[_relation("Harrer", "Lhasa")],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=None,
        )
        assert len(result.edges) == 1
        assert result.edges[0].source_ref is None

    def test_empty_relations_returns_empty(self) -> None:
        result = materialise_edges(
            relations=[],
            resolved_lookup={},
            book_source_ref=_book_ref(),
            central_sentence=None,
        )
        assert result.edges == []
        assert result.dropped_total == 0


# ---------------------------------------------------------------- DTO


class TestEdgeMaterialisationModel:
    def test_extra_fields_forbidden(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            EdgeMaterialisation(bogus="x")  # type: ignore[call-arg]

    def test_dropped_total_aggregates(self) -> None:
        m = EdgeMaterialisation(
            dropped_subject_unresolved=3,
            dropped_object_unresolved=2,
            dropped_self_loop=1,
        )
        assert m.dropped_total == 6


# ---------------------------------------------------------------- determinism


class TestDeterministicEdgeId:
    """Same inputs → same edge.id (Plan §9.5 / §9.5a)."""

    def test_identical_inputs_yield_same_edge_id(self) -> None:
        node_h = _node("Harrer")
        node_l = _node("Lhasa", node_type=NodeType.PLACE)
        lookup = build_resolved_lookup(
            [_resolved("Harrer", "PERSON", node_h), _resolved("Lhasa", "GPE", node_l)]
        )
        rel = _relation("Harrer", "Lhasa", evidence_span="Harrer reached Lhasa")

        # Materialise twice with the same inputs.
        a = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )
        b = materialise_edges(
            relations=[rel],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )
        assert a.edges[0].id == b.edges[0].id
        assert a.edges[0].id.startswith("EDGE-")

    def test_different_evidence_yields_different_edge_id(self) -> None:
        # Plan §9.5a: same (source, relation, target) with different
        # evidence_spans = two distinct edges.
        node_h = _node("Harrer")
        node_l = _node("Lhasa", node_type=NodeType.PLACE)
        lookup = build_resolved_lookup(
            [_resolved("Harrer", "PERSON", node_h), _resolved("Lhasa", "GPE", node_l)]
        )
        rel_a = _relation("Harrer", "Lhasa", evidence_span="Harrer reached Lhasa")
        rel_b = _relation("Harrer", "Lhasa", evidence_span="he arrived in Lhasa")

        a = materialise_edges(
            relations=[rel_a],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )
        b = materialise_edges(
            relations=[rel_b],
            resolved_lookup=lookup,
            book_source_ref=_book_ref(),
            central_sentence=_sentence(0, "x"),
        )
        assert a.edges[0].id != b.edges[0].id
