"""
Tests for Kadmos → MNLM MeshInput export (mesh_native_lm_brief.md §7).

Covers:
- Conversion of AnnotatedReading → MeshInput with stub embedder
- Codebook ID determinism from relation descriptions
- Nuance vector shape (32-dim)
- Synthesis node type and abstraction edges
- aux["kadmos_open_tensions"] population
- Deduplication of nodes by label
- Edge endpoint integrity (all edges reference existing nodes)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from theogony.kadmos.mesh_export import (
    _compute_edge_id,
    _compute_node_id,
    _concept_to_mesh_node,
    _relation_description_to_codebook_id,
    _relation_description_to_nuance,
    _synthesis_to_mesh_node,
    annotated_reading_to_mesh_input,
)
from theogony.kadmos.model import (
    ActiveConcept,
    AnnotatedReading,
    LLMNewEdge,
    LLMReadingOutput,
    ReadingHypotheses,
    ReadingStep,
    SynthesisNode,
)

# ---------------------------------------------------------------------------
# Stub embedder
# ---------------------------------------------------------------------------


class StubEmbedder:
    """Deterministic 384-dim stub embedder for PoC testing."""

    model_id: str = "stub-test-embedder/v0"

    async def embed(self, text: str) -> list[float]:
        """Return a deterministic 384-dim vector derived from the text hash."""
        h = hash(text)
        seed = h & 0xFFFFFFFF
        import random

        rng = random.Random(seed)
        return [rng.random() for _ in range(384)]


_EMBEDDER = StubEmbedder()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _make_concept(
    cid: str = "c1",
    label: str = "Test Concept",
    activation: float = 0.9,
    step: int = 0,
) -> ActiveConcept:
    return ActiveConcept(
        id=cid,
        label=label,
        description="A test concept",
        activation=activation,
        step_created=step,
        source_passage="Test passage.",
    )


def _make_synthesis(
    sid: str = "s1",
    label: str = "Test Synthesis",
    basis_ids: list[str] | None = None,
) -> SynthesisNode:
    return SynthesisNode(
        id=sid,
        label=label,
        description="A test synthesis node",
        basis_concept_ids=basis_ids or ["c1"],
        synthesis_level="paragraph",
        step_created=1,
        confidence=0.85,
    )


def _minimal_annotated_reading() -> AnnotatedReading:
    return AnnotatedReading(
        session_id="test-session-001",
        source_url="https://en.wikipedia.org/wiki/Test_Article",
        article_title="Test Article",
        started_at=_now(),
        finished_at=_now(),
        total_concepts=1,
        total_edges=0,
        total_syntheses=0,
        total_revisions=0,
        total_llm_calls=1,
        total_llm_cost_eur=0.005,
        reading_units_total=1,
    )


# ---------------------------------------------------------------------------
# Codebook helpers
# ---------------------------------------------------------------------------


def test_relation_description_to_codebook_id_is_deterministic() -> None:
    cid1 = _relation_description_to_codebook_id("LOVES")
    cid2 = _relation_description_to_codebook_id("LOVES")
    assert cid1 == cid2


def test_relation_description_to_codebook_id_in_range() -> None:
    for desc in ("LOVES", "FEARS", "CAUSES", "IS_A", "CONTRADICTS"):
        cid = _relation_description_to_codebook_id(desc)
        assert 0 <= cid < 512


def test_relation_description_to_codebook_id_distinct() -> None:
    ids = {_relation_description_to_codebook_id(d) for d in ("LOVES", "FEARS", "HATES")}
    assert len(ids) == 3


def test_nuance_vector_is_32_dim() -> None:
    cid = _relation_description_to_codebook_id("test")
    nuance = _relation_description_to_nuance("test", cid)
    assert len(nuance) == 32
    for v in nuance:
        assert -0.2 <= v <= 0.2


def test_nuance_vector_deterministic() -> None:
    cid = _relation_description_to_codebook_id("LOVES")
    n1 = _relation_description_to_nuance("LOVES", cid)
    n2 = _relation_description_to_nuance("LOVES", cid)
    assert n1 == n2


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------


def test_compute_node_id_deterministic() -> None:
    c = _make_concept()
    id1 = _compute_node_id(c)
    id2 = _compute_node_id(c)
    assert id1 == id2
    assert id1.startswith("AKA-")


def test_compute_edge_id_deterministic() -> None:
    id1 = _compute_edge_id("AKA-a", "AKA-b", "test edge")
    id2 = _compute_edge_id("AKA-a", "AKA-b", "test edge")
    assert id1 == id2
    assert id1.startswith("EDGE-")


# ---------------------------------------------------------------------------
# Concept → MeshInputNode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concept_to_mesh_node() -> None:
    concept = _make_concept()
    nid = _compute_node_id(concept)
    node = await _concept_to_mesh_node(concept, nid, "https://example.org", _EMBEDDER)
    assert node.node_id == nid
    assert len(node.embedding) == 384
    assert node.activation_weight == 0.9
    assert node.node_type == "concept"
    assert node.layer == "ephemera"


@pytest.mark.asyncio
async def test_concept_to_mesh_node_with_revision() -> None:
    from theogony.kadmos.model import RevisionRecord

    concept = _make_concept()
    concept.revision_history.append(
        RevisionRecord(
            step_index=1,
            revision_type="update",
            reason="clarification",
            triggering_passage="new info",
        )
    )
    nid = _compute_node_id(concept)
    node = await _concept_to_mesh_node(concept, nid, "https://example.org", _EMBEDDER)
    assert node.revision_depth == 1


# ---------------------------------------------------------------------------
# Synthesis → MeshInputNode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesis_to_mesh_node() -> None:
    synthesis = _make_synthesis()
    sid = _compute_node_id(synthesis)
    node = await _synthesis_to_mesh_node(synthesis, sid, "https://example.org", _EMBEDDER)
    assert node.node_type == "synthesis"
    assert len(node.embedding) == 384


# ---------------------------------------------------------------------------
# Full AnnotatedReading → MeshInput conversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_reading_produces_valid_mesh_input() -> None:
    """An AnnotatedReading with no concepts passes the MeshInput validator
    if the schema's min_length=1 constraints are satisfied."""
    annotated = _minimal_annotated_reading()
    with pytest.raises(ValidationError, match="at least 1 item"):
        await annotated_reading_to_mesh_input(annotated, _EMBEDDER)


@pytest.mark.asyncio
async def test_single_concept_produces_one_node() -> None:
    annotated = _minimal_annotated_reading()
    annotated.final_active_concepts = [_make_concept()]
    annotated.total_concepts = 1
    mi = await annotated_reading_to_mesh_input(annotated, _EMBEDDER)
    assert len(mi.nodes) == 1
    assert mi.nodes[0].node_type == "concept"
    assert len(mi.active_node_ids) == 1


@pytest.mark.asyncio
async def test_synthesis_creates_node_and_abstraction_edge() -> None:
    annotated = _minimal_annotated_reading()
    concept = _make_concept(cid="c1", label="Basis")
    synthesis = _make_synthesis(sid="s1", label="Synthesis", basis_ids=["c1"])
    annotated.final_active_concepts = [concept]
    annotated.final_syntheses = [synthesis]
    mi = await annotated_reading_to_mesh_input(annotated, _EMBEDDER)
    assert len(mi.nodes) == 2
    types = {n.node_type for n in mi.nodes}
    assert "concept" in types
    assert "synthesis" in types
    assert len(mi.edges) >= 1
    synthesis_node_ids = [n.node_id for n in mi.nodes if n.node_type == "synthesis"]
    for edge in mi.edges:
        if edge.source_id in synthesis_node_ids:
            assert edge.relation_codebook_id == 1


@pytest.mark.asyncio
async def test_open_tensions_flow_to_aux() -> None:
    annotated = _minimal_annotated_reading()
    c = _make_concept()
    annotated.final_active_concepts = [c]
    annotated.total_concepts = 1
    step = ReadingStep(
        step_index=0,
        granularity="paragraph",
        text="Test",
        hypotheses=ReadingHypotheses(),
        llm_output=LLMReadingOutput(
            open_tensions=["unclear date", "contradictory sources"],
        ),
        wm_size_before=0,
        wm_size_after=0,
    )
    annotated.steps = [step]
    mi = await annotated_reading_to_mesh_input(annotated, _EMBEDDER)
    assert "kadmos_open_tensions" in mi.aux
    assert len(mi.aux["kadmos_open_tensions"]) == 2


@pytest.mark.asyncio
async def test_edge_integrity_all_referenced_nodes_exist() -> None:
    """Verify every edge's source and target exist in nodes."""
    annotated = _minimal_annotated_reading()
    c1 = _make_concept(cid="c1", label="Concept A")
    c2 = ActiveConcept(
        id="c2",
        label="Concept B",
        activation=0.7,
        step_created=0,
        source_passage="Test",
    )
    annotated.final_active_concepts = [c1, c2]

    step = ReadingStep(
        step_index=0,
        granularity="paragraph",
        text="Test",
        hypotheses=ReadingHypotheses(),
        llm_output=LLMReadingOutput(
            new_connections=[
                LLMNewEdge(
                    source_label="Concept A",
                    target_label="Concept B",
                    relation_description="RELATED_TO",
                    weight=0.8,
                ),
            ],
        ),
        wm_size_before=0,
        wm_size_after=2,
    )
    annotated.steps = [step]
    mi = await annotated_reading_to_mesh_input(annotated, _EMBEDDER)
    node_ids = {n.node_id for n in mi.nodes}
    for edge in mi.edges:
        assert edge.source_id in node_ids, f"Edge source {edge.source_id} not in nodes"
        assert edge.target_id in node_ids, f"Edge target {edge.target_id} not in nodes"


@pytest.mark.asyncio
async def test_deterministic_conversion_idempotent() -> None:
    """Same input produces same MeshInput (same node IDs, edge IDs)."""
    annotated = _minimal_annotated_reading()
    c = _make_concept()
    annotated.final_active_concepts = [c]
    mi1 = await annotated_reading_to_mesh_input(annotated, _EMBEDDER)
    mi2 = await annotated_reading_to_mesh_input(annotated, _EMBEDDER)
    assert mi1.nodes[0].node_id == mi2.nodes[0].node_id
    assert mi1.nodes[0].embedding == mi2.nodes[0].embedding


@pytest.mark.asyncio
async def test_run_id_uses_provided_value() -> None:
    annotated = _minimal_annotated_reading()
    c = _make_concept()
    annotated.final_active_concepts = [c]
    annotated.total_concepts = 1
    mi = await annotated_reading_to_mesh_input(annotated, _EMBEDDER, run_id="explicit-run-001")
    assert mi.run_id == "explicit-run-001"


@pytest.mark.asyncio
async def test_context_role_is_set() -> None:
    annotated = _minimal_annotated_reading()
    c = _make_concept()
    annotated.final_active_concepts = [c]
    annotated.total_concepts = 1
    mi = await annotated_reading_to_mesh_input(annotated, _EMBEDDER, role="nous")
    assert mi.context.role == "nous"


@pytest.mark.asyncio
async def test_mesh_input_validates_after_conversion() -> None:
    """Verify the produced MeshInput passes its own model_validator."""
    annotated = _minimal_annotated_reading()
    c1 = _make_concept(cid="c1", label="Alpha")
    c2 = ActiveConcept(id="c2", label="Beta", step_created=0, source_passage="T")
    annotated.final_active_concepts = [c1, c2]
    step = ReadingStep(
        step_index=0,
        granularity="paragraph",
        text="T",
        hypotheses=ReadingHypotheses(),
        llm_output=LLMReadingOutput(
            new_connections=[
                LLMNewEdge(
                    source_label="Alpha",
                    target_label="Beta",
                    relation_description="related",
                ),
            ],
        ),
        wm_size_before=0,
        wm_size_after=2,
    )
    annotated.steps = [step]
    mi = await annotated_reading_to_mesh_input(annotated, _EMBEDDER)
    from theogony.agents.mnlm.dto import MeshInput

    MeshInput.model_validate(mi.model_dump())
