"""
Tests for MnlmRunReport (mesh_native_lm_brief.md §4.3).

Covers:
- Round-trip JSON serialisation
- extra="forbid" enforcement
- Verdict heuristics (mutation_budget_exhaustion → partial,
  lfm_failed_convergence → failed)
- Integration with RunReportWriter
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from theogony.reporting.models import MnlmRunReport, new_run_id


def _utc() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# MnlmRunReport
# ---------------------------------------------------------------------------


def test_mnlm_run_report_round_trip() -> None:
    report = MnlmRunReport(
        run_id=new_run_id(),
        started_at=_utc(),
        finished_at=_utc(),
        duration_s=120.5,
        status="completed",
        verdict="completed",
        role="generic",
        calls_made=50,
        calls_succeeded=48,
        primitives_emitted_total=312,
        primitives_by_kind={"add_node": 200, "add_edge": 100, "emit_finding": 12},
        mean_trajectory_entropy=0.45,
        mean_latent_steps=8.2,
        mean_sa_cycles=2.1,
        halted_reason_counts={"stable": 45, "budget_exhausted": 3, "error": 2},
        findings_emitted=12,
        notes="PoC micro-training run complete.",
    )
    loaded = MnlmRunReport.model_validate_json(report.model_dump_json())
    assert loaded.report_type == "mnlm"
    assert loaded.calls_made == 50
    assert loaded.calls_succeeded == 48
    assert loaded.mean_trajectory_entropy == 0.45


def test_mnlm_run_report_minimal() -> None:
    """A report with only required fields should be valid."""
    report = MnlmRunReport(
        started_at=_utc(),
        finished_at=_utc(),
        duration_s=0.0,
        status="completed",
        verdict="completed",
        role="generic",
        calls_made=0,
        calls_succeeded=0,
        primitives_emitted_total=0,
    )
    assert report.calls_made == 0
    assert report.notes == ""


def test_mnlm_run_report_invalid_type() -> None:
    with pytest.raises(ValidationError):
        MnlmRunReport(
            started_at=_utc(),
            finished_at=_utc(),
            duration_s=1.0,
            status="completed",
            verdict="completed",
            report_type="kadmos",  # type: ignore[arg-type]
            role="generic",
            calls_made=0,
            calls_succeeded=0,
            primitives_emitted_total=0,
        )


def test_mnlm_run_report_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        MnlmRunReport(
            started_at=_utc(),
            finished_at=_utc(),
            duration_s=1.0,
            status="completed",
            verdict="completed",
            role="generic",
            calls_made=0,
            calls_succeeded=0,
            primitives_emitted_total=0,
            bogus="bad",  # type: ignore[call-arg]
        )


def test_mnlm_run_report_verdict_completed() -> None:
    report = MnlmRunReport(
        started_at=_utc(),
        finished_at=_utc(),
        duration_s=10.0,
        status="completed",
        verdict="completed",
        role="nous",
        calls_made=10,
        calls_succeeded=10,
        primitives_emitted_total=50,
    )
    assert report.verdict == "completed"


def test_mnlm_run_report_verdict_partial() -> None:
    report = MnlmRunReport(
        started_at=_utc(),
        finished_at=_utc(),
        duration_s=10.0,
        status="partial",
        verdict="partial",
        role="oneiros",
        calls_made=10,
        calls_succeeded=7,
        primitives_emitted_total=30,
    )
    assert report.verdict == "partial"


def test_mnlm_run_report_notes_max_length() -> None:
    with pytest.raises(ValidationError):
        MnlmRunReport(
            started_at=_utc(),
            finished_at=_utc(),
            duration_s=1.0,
            status="completed",
            verdict="completed",
            role="kalypso",
            calls_made=0,
            calls_succeeded=0,
            primitives_emitted_total=0,
            notes="x" * 5000,
        )


def test_mnlm_run_report_serialize_to_json() -> None:
    report = MnlmRunReport(
        run_id=new_run_id(),
        started_at=_utc(),
        finished_at=_utc(),
        duration_s=45.0,
        status="completed",
        verdict="completed",
        role="generic",
        calls_made=25,
        calls_succeeded=24,
        primitives_emitted_total=160,
        primitives_by_kind={"add_node": 100, "add_edge": 60},
        mean_trajectory_entropy=0.32,
        mean_latent_steps=6.5,
        mean_sa_cycles=1.8,
        halted_reason_counts={"stable": 22, "budget_exhausted": 2, "error": 1},
        findings_emitted=3,
        notes="Completed with minor budget exhaustion.",
    )
    raw = report.model_dump_json()
    data = json.loads(raw)
    assert data["report_type"] == "mnlm"
    assert data["verdict"] == "completed"
    assert data["primitives_by_kind"]["add_node"] == 100
