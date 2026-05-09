"""
Unit tests for Kadmos v2 Pydantic models (E1).

Covers:
- Round-trip JSON serialisation for every model
- extra="forbid" enforcement
- Literal rejection for invalid values
- KadmosRunReport in reporting/models.py
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from theogony.kadmos.model import (
    ActiveConcept,
    ActiveEdge,
    AnnotatedReading,
    HypothesisCandidate,
    LLMNewConcept,
    LLMNewEdge,
    LLMReadingOutput,
    LLMSynthesisOutput,
    ReadingHypotheses,
    ReadingState,
    ReadingStep,
    RevisionRecord,
    RevisionRequest,
    SynthesisNode,
)
from theogony.reporting.models import KadmosRunReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _concept(cid: str = "c1", label: str = "Tibet", step: int = 0) -> ActiveConcept:
    return ActiveConcept(id=cid, label=label, step_created=step)


def _edge(eid: str = "e1", src: str = "c1", tgt: str = "c2") -> ActiveEdge:
    return ActiveEdge(
        id=eid,
        source_id=src,
        target_id=tgt,
        relation_description="Tibet is explored by Hedin",
        step_created=0,
    )


# ---------------------------------------------------------------------------
# RevisionRecord
# ---------------------------------------------------------------------------


def test_revision_record_round_trip() -> None:
    rr = RevisionRecord(
        step_index=3,
        revision_type="update",
        reason="New passage clarifies the meaning",
        triggering_passage="Hedin crossed Tibet in 1906",
        old_understanding="Tibet was unknown",
        new_understanding="Tibet was explored by Hedin",
    )
    loaded = RevisionRecord.model_validate_json(rr.model_dump_json())
    assert loaded == rr


def test_revision_record_invalid_type() -> None:
    with pytest.raises(ValidationError):
        RevisionRecord(
            step_index=0,
            revision_type="delete",  # type: ignore[arg-type]
            reason="x",
            triggering_passage="x",
        )


# ---------------------------------------------------------------------------
# ActiveConcept
# ---------------------------------------------------------------------------


def test_active_concept_round_trip() -> None:
    c = _concept()
    loaded = ActiveConcept.model_validate_json(c.model_dump_json())
    assert loaded == c


def test_active_concept_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        ActiveConcept(id="c1", label="x", step_created=0, bogus="bad")  # type: ignore[call-arg]


def test_active_concept_default_activation() -> None:
    c = _concept()
    assert c.activation == 1.0
    assert not c.invalidated


def test_active_concept_with_revision_history() -> None:
    rr = RevisionRecord(
        step_index=2, revision_type="invalidate", reason="r", triggering_passage="t"
    )
    c = ActiveConcept(id="c1", label="X", step_created=0, revision_history=[rr])
    loaded = ActiveConcept.model_validate_json(c.model_dump_json())
    assert len(loaded.revision_history) == 1


# ---------------------------------------------------------------------------
# ActiveEdge
# ---------------------------------------------------------------------------


def test_active_edge_round_trip() -> None:
    e = _edge()
    loaded = ActiveEdge.model_validate_json(e.model_dump_json())
    assert loaded == e


def test_active_edge_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        ActiveEdge(
            id="e1",
            source_id="c1",
            target_id="c2",
            relation_description="x",
            step_created=0,
            unknown=1,  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# SynthesisNode
# ---------------------------------------------------------------------------


def test_synthesis_node_round_trip() -> None:
    s = SynthesisNode(
        id="s1",
        label="Tibetan Exploration",
        description="Synthesis of exploration concepts",
        basis_concept_ids=["c1", "c2"],
        synthesis_level="paragraph",
        step_created=5,
        confidence=0.9,
    )
    loaded = SynthesisNode.model_validate_json(s.model_dump_json())
    assert loaded == s


def test_synthesis_node_invalid_level() -> None:
    with pytest.raises(ValidationError):
        SynthesisNode(
            id="s1",
            label="X",
            description="x",
            basis_concept_ids=[],
            synthesis_level="sentence",  # type: ignore[arg-type]
            step_created=0,
        )


# ---------------------------------------------------------------------------
# ReadingHypotheses + HypothesisCandidate
# ---------------------------------------------------------------------------


def test_reading_hypotheses_round_trip() -> None:
    h = ReadingHypotheses(
        similarity_candidates=[
            HypothesisCandidate(
                concept_id="c1", label="Tibet", score=0.91, hypothesis_type="similarity"
            )
        ],
        traversal_candidates=[
            HypothesisCandidate(
                concept_id="c2", label="Hedin", score=0.7, hypothesis_type="traversal"
            )
        ],
    )
    loaded = ReadingHypotheses.model_validate_json(h.model_dump_json())
    assert loaded == h


def test_hypothesis_candidate_invalid_type() -> None:
    with pytest.raises(ValidationError):
        HypothesisCandidate(concept_id="c1", label="X", score=0.5, hypothesis_type="random")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LLMReadingOutput
# ---------------------------------------------------------------------------


def test_llm_reading_output_minimal() -> None:
    out = LLMReadingOutput()
    assert out.new_concepts == []
    assert out.synthesis is None
    assert out.revisions == []
    assert out.next_granularity == "paragraph"


def test_llm_reading_output_round_trip() -> None:
    out = LLMReadingOutput(
        new_concepts=[LLMNewConcept(label="Sven Hedin", description="Swedish explorer")],
        new_connections=[
            LLMNewEdge(
                source_label="Sven Hedin",
                target_label="Tibet",
                relation_description="Hedin explored Tibet",
                weight=0.9,
            )
        ],
        confirmed_hypotheses=["c1"],
        rejected_hypotheses=["c2"],
        revisions=[
            RevisionRequest(
                target_concept_id="c3",
                revision_type="update",
                reason="new passage",
                triggering_passage="Tibet was crossed",
            )
        ],
        synthesis=LLMSynthesisOutput(
            label="Tibetan Exploration",
            description="Synthesis",
            basis_concept_ids=["c1", "c2"],
            synthesis_level="paragraph",
            confidence=0.85,
        ),
        open_tensions=["unclear date"],
        next_granularity="sentence",
    )
    loaded = LLMReadingOutput.model_validate_json(out.model_dump_json())
    assert loaded.synthesis is not None
    assert loaded.synthesis.label == "Tibetan Exploration"
    assert loaded.next_granularity == "sentence"


def test_llm_reading_output_extra_ignored() -> None:
    """Extra fields are silently ignored (DeepSeek compatibility)."""
    out = LLMReadingOutput(unknown_field=True)  # type: ignore[call-arg]
    assert out.new_concepts == []


def test_llm_reading_output_invalid_granularity() -> None:
    with pytest.raises(ValidationError):
        LLMReadingOutput(next_granularity="page")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ReadingStep
# ---------------------------------------------------------------------------


def test_reading_step_round_trip() -> None:
    step = ReadingStep(
        step_index=0,
        granularity="paragraph",
        text="Sven Hedin crossed the Himalayas in 1906.",
        section_title="Early Expeditions",
        hypotheses=ReadingHypotheses(),
        llm_output=LLMReadingOutput(),
        concepts_added=["c1"],
        edges_added=["e1"],
        wm_size_before=0,
        wm_size_after=1,
        llm_cost_eur=0.002,
        llm_latency_ms=1200,
    )
    loaded = ReadingStep.model_validate_json(step.model_dump_json())
    assert loaded == step


def test_reading_step_failed_flag() -> None:
    step = ReadingStep(
        step_index=5,
        granularity="paragraph",
        text="x",
        hypotheses=ReadingHypotheses(),
        llm_output=LLMReadingOutput(),
        wm_size_before=3,
        wm_size_after=3,
        parse_failed=True,
    )
    assert step.parse_failed is True


# ---------------------------------------------------------------------------
# ReadingState
# ---------------------------------------------------------------------------


def test_reading_state_round_trip() -> None:
    state = ReadingState(session_id="sess-001")
    loaded = ReadingState.model_validate_json(state.model_dump_json())
    assert loaded.session_id == "sess-001"
    assert loaded.current_granularity == "paragraph"


def test_reading_state_default_empty() -> None:
    state = ReadingState(session_id="s")
    assert state.active_concepts == {}
    assert state.active_edges == {}
    assert state.syntheses == {}
    assert state.open_tensions == []


# ---------------------------------------------------------------------------
# AnnotatedReading
# ---------------------------------------------------------------------------


def test_annotated_reading_round_trip() -> None:
    ar = AnnotatedReading(
        session_id="sess-001",
        source_url="https://en.wikipedia.org/wiki/Sven_Hedin",
        article_title="Sven Hedin",
        started_at=_now(),
        finished_at=_now(),
        total_concepts=15,
        total_edges=42,
        total_syntheses=3,
        total_revisions=2,
        total_llm_calls=10,
        total_llm_cost_eur=0.18,
        reading_units_total=10,
    )
    loaded = AnnotatedReading.model_validate_json(ar.model_dump_json())
    assert loaded.session_id == "sess-001"
    assert loaded.total_concepts == 15


def test_annotated_reading_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        AnnotatedReading(
            session_id="x",
            source_url="http://example.com",
            article_title="X",
            started_at=_now(),
            finished_at=_now(),
            total_concepts=0,
            total_edges=0,
            total_syntheses=0,
            total_revisions=0,
            total_llm_calls=0,
            total_llm_cost_eur=0.0,
            reading_units_total=0,
            bogus_field="bad",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# KadmosRunReport
# ---------------------------------------------------------------------------


def test_kadmos_run_report_round_trip() -> None:
    report = KadmosRunReport(
        session_id="sess-001",
        source_url="https://en.wikipedia.org/wiki/Sven_Hedin",
        started_at=_now(),
        finished_at=_now(),
        duration_s=45.0,
        status="completed",
        verdict="good",
        reading_units_total=47,
        total_concepts=312,
        total_edges=1104,
        total_syntheses=12,
        total_revisions=5,
        llm_calls=47,
        llm_cost_eur=0.21,
        wall_clock_s=45.0,
        annotated_reading_path="data/kadmos/sess-001.json",
        lancedb_path="data/kadmos/sess-001.lance",
    )
    loaded = KadmosRunReport.model_validate_json(report.model_dump_json())
    assert loaded.report_type == "kadmos"
    assert loaded.total_concepts == 312


def test_kadmos_run_report_invalid_type() -> None:
    with pytest.raises(ValidationError):
        KadmosRunReport(
            session_id="s",
            source_url="http://example.com",
            started_at=_now(),
            finished_at=_now(),
            duration_s=1.0,
            status="completed",
            verdict="good",
            report_type="nous",  # type: ignore[arg-type]
            reading_units_total=0,
            total_concepts=0,
            total_edges=0,
            total_syntheses=0,
            total_revisions=0,
            llm_calls=0,
            llm_cost_eur=0.0,
            wall_clock_s=0.0,
        )
