"""
Unit tests for Nous Pydantic models (nous_implementation_brief §5, E1).

Covers:
- Round-trip JSON serialisation for every model
- extra="forbid" enforcement (unknown fields must raise)
- Literal rejection for invalid values
- NousRunReport round-trips correctly via reporting/models.py
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from theogony.core.model import KnowledgeEdge, KnowledgeNode, SourceRef
from theogony.nous.model import (
    AnnotatedReading,
    ChronicleHint,
    LLMReadingOutput,
    ReadingStep,
    RepairEvent,
    ResolutionUpdate,
    SynthesisOutput,
    WorkingMemoryState,
)
from theogony.reporting.models import NousRunReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _wm(step: int = 0) -> WorkingMemoryState:
    return WorkingMemoryState(
        step_index=step,
        concepts={"AKA-abc": 0.8, "AKA-def": 0.4},
        pooled_embedding=[0.1, 0.2, 0.3],
        open_tensions=[("AKA-abc", "contradicts earlier claim")],
    )


# ---------------------------------------------------------------------------
# ChronicleHint
# ---------------------------------------------------------------------------


def test_chronicle_hint_round_trip() -> None:
    hint = ChronicleHint(
        id="AKA-abc123",
        label="Sven Hedin",
        similarity=0.91,
        source="gutenberg:43497",
    )
    loaded = ChronicleHint.model_validate_json(hint.model_dump_json())
    assert loaded == hint


def test_chronicle_hint_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ChronicleHint(id="AKA-x", label="X", similarity=0.5, source="s", unknown="bad")  # type: ignore[call-arg]


def test_chronicle_hint_tension_flag() -> None:
    hint = ChronicleHint(id="AKA-x", label="X", similarity=0.5, source="s", tension=True)
    assert hint.tension is True


# ---------------------------------------------------------------------------
# WorkingMemoryState
# ---------------------------------------------------------------------------


def test_working_memory_round_trip() -> None:
    wm = _wm(step=3)
    loaded = WorkingMemoryState.model_validate_json(wm.model_dump_json())
    assert loaded == wm


def test_working_memory_empty_tensions() -> None:
    wm = WorkingMemoryState(step_index=0, concepts={}, pooled_embedding=[])
    assert wm.open_tensions == []


# ---------------------------------------------------------------------------
# ResolutionUpdate
# ---------------------------------------------------------------------------


def test_resolution_update_round_trip() -> None:
    ru = ResolutionUpdate(
        node_id="AKA-abc",
        previous_tier=1,
        new_tier=3,
        new_wikidata_id="Q123",
        reason="Full paragraph context confirmed match",
    )
    loaded = ResolutionUpdate.model_validate_json(ru.model_dump_json())
    assert loaded == ru


def test_resolution_update_no_previous_tier() -> None:
    ru = ResolutionUpdate(node_id="AKA-abc", new_tier=0, reason="No match found")
    assert ru.previous_tier is None


# ---------------------------------------------------------------------------
# SynthesisOutput
# ---------------------------------------------------------------------------


def test_synthesis_output_round_trip() -> None:
    so = SynthesisOutput(
        label="Tibetan Exploration",
        description="Synthesis of exploration concepts in this section",
        basis_node_ids=["AKA-abc", "AKA-def"],
        diagonal_edges=[("AKA-abc", "BINDS_TO", "AKA-theme1")],
        synthesis_level="paragraph",
        confidence=0.85,
    )
    loaded = SynthesisOutput.model_validate_json(so.model_dump_json())
    assert loaded == so


def test_synthesis_output_invalid_level() -> None:
    with pytest.raises(ValidationError):
        SynthesisOutput(
            label="X",
            basis_node_ids=[],
            synthesis_level="sentence",  # type: ignore[arg-type]  # not a valid synthesis level
            confidence=0.5,
        )


# ---------------------------------------------------------------------------
# RepairEvent
# ---------------------------------------------------------------------------


def test_repair_event_round_trip() -> None:
    re_ = RepairEvent(
        revised_node_id="AKA-abc",
        reason="New sentence contradicts earlier claim",
        old_description="Tibet was never explored",
        new_description="Tibet was explored by Hedin in 1906",
        tension_source="llm_detected",
    )
    loaded = RepairEvent.model_validate_json(re_.model_dump_json())
    assert loaded == re_


def test_repair_event_invalid_tension_source() -> None:
    with pytest.raises(ValidationError):
        RepairEvent(
            revised_node_id="AKA-abc",
            reason="x",
            tension_source="unknown_source",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# LLMReadingOutput
# ---------------------------------------------------------------------------


def test_llm_reading_output_minimal() -> None:
    out = LLMReadingOutput()
    assert out.new_concepts == []
    assert out.synthesis_event is None
    assert out.repair_events == []


def test_llm_reading_output_with_synthesis() -> None:
    so = SynthesisOutput(
        label="Tibet",
        basis_node_ids=["AKA-abc"],
        synthesis_level="paragraph",
        confidence=0.7,
    )
    out = LLMReadingOutput(
        new_concepts=[{"label": "Exploration", "node_type": "concept"}],
        chronicle_hits_used=["AKA-abc"],
        synthesis_event=so,
    )
    loaded = LLMReadingOutput.model_validate_json(out.model_dump_json())
    assert loaded.synthesis_event is not None
    assert loaded.synthesis_event.label == "Tibet"


def test_llm_reading_output_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMReadingOutput(bogus_field="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ReadingStep
# ---------------------------------------------------------------------------


def test_reading_step_round_trip() -> None:
    step = ReadingStep(
        step_index=0,
        paragraph_text="Sven Hedin crossed the Himalayas.",
        section_title="Exploration",
        synthesis_level_context="paragraph",
        working_memory_before=_wm(),
        chronicle_hints_offered=[
            ChronicleHint(
                id="AKA-abc", label="Sven Hedin", similarity=0.9, source="gutenberg:43497"
            )
        ],
        llm_output=LLMReadingOutput(),
        nodes_written=["AKA-new1"],
        edges_written=["EDGE-xyz"],
        llm_cost_eur=0.002,
        llm_latency_ms=1200,
    )
    loaded = ReadingStep.model_validate_json(step.model_dump_json())
    assert loaded == step


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
        final_working_memory=_wm(),
        total_nodes_written=5,
        total_edges_written=12,
        total_synthesis_events=2,
        total_repair_events=0,
        chronicle_seeded=False,
    )
    loaded = AnnotatedReading.model_validate_json(ar.model_dump_json())
    assert loaded.session_id == "sess-001"
    assert loaded.chronicle_seeded is False


def test_annotated_reading_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        AnnotatedReading(
            session_id="x",
            source_url="http://example.com",
            article_title="X",
            started_at=_now(),
            finished_at=_now(),
            final_working_memory=_wm(),
            total_nodes_written=0,
            total_edges_written=0,
            total_synthesis_events=0,
            total_repair_events=0,
            chronicle_seeded=True,
            unexpected_field="oops",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# NousRunReport
# ---------------------------------------------------------------------------


def test_nous_run_report_round_trip() -> None:
    report = NousRunReport(
        session_id="sess-001",
        source_url="https://en.wikipedia.org/wiki/Sven_Hedin",
        started_at=_now(),
        finished_at=_now(),
        duration_s=42.5,
        status="completed",
        verdict="good",
        reading_units_total=47,
        nodes_written=312,
        edges_written=1104,
        synthesis_events=12,
        repair_events=3,
        chronicle_hits_offered=235,
        chronicle_hits_used=88,
        llm_calls=47,
        llm_cost_eur=0.21,
        wall_clock_s=252.0,
        chronicle_seeded=True,
        annotated_reading_path="data/nous/sess-001.json",
    )
    loaded = NousRunReport.model_validate_json(report.model_dump_json())
    assert loaded.report_type == "nous"
    assert loaded.session_id == "sess-001"
    assert loaded.nodes_written == 312


def test_nous_run_report_invalid_report_type_rejected() -> None:
    """Assigning the wrong literal must fail."""
    with pytest.raises(ValidationError):
        NousRunReport(
            session_id="s",
            source_url="http://example.com",
            started_at=_now(),
            finished_at=_now(),
            duration_s=1.0,
            status="completed",
            verdict="good",
            report_type="ingest",  # type: ignore[arg-type]
            reading_units_total=0,
            nodes_written=0,
            edges_written=0,
            synthesis_events=0,
            repair_events=0,
            chronicle_hits_offered=0,
            chronicle_hits_used=0,
            llm_calls=0,
            llm_cost_eur=0.0,
            wall_clock_s=0.0,
            chronicle_seeded=False,
        )


# ---------------------------------------------------------------------------
# core/model.py additions: KnowledgeNode + KnowledgeEdge new fields
# ---------------------------------------------------------------------------


def _base_source() -> SourceRef:
    return SourceRef(source_type="test", identifier="test-001")


def test_knowledge_node_nous_fields_default_none() -> None:
    node = KnowledgeNode(
        label="Sven Hedin",
        source_ref=_base_source(),
    )
    assert node.nous_session_id is None
    assert node.synthesis_level is None


def test_knowledge_node_nous_fields_set() -> None:
    node = KnowledgeNode(
        label="Tibetan Exploration",
        source_ref=_base_source(),
        nous_session_id="sess-001",
        synthesis_level="paragraph",
    )
    assert node.nous_session_id == "sess-001"
    assert node.synthesis_level == "paragraph"


def test_knowledge_node_invalid_synthesis_level() -> None:
    with pytest.raises(ValidationError):
        KnowledgeNode(
            label="X",
            source_ref=_base_source(),
            synthesis_level="domain",  # type: ignore[arg-type]
        )


def test_knowledge_edge_relation_codebook_default_none() -> None:
    edge = KnowledgeEdge(
        source_id="AKA-abc",
        target_id="AKA-def",
        relation_type="BINDS_TO",
    )
    assert edge.relation_codebook is None


def test_knowledge_edge_relation_codebook_set() -> None:
    edge = KnowledgeEdge(
        source_id="AKA-abc",
        target_id="AKA-def",
        relation_type="BINDS_TO",
        relation_codebook="BINDS_TO",
    )
    assert edge.relation_codebook == "BINDS_TO"
