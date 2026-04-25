"""ChronosRunReport mapping (W15)."""

from __future__ import annotations

from datetime import UTC, datetime

from theogony.curiosity.chronos_report import (
    ChronosAction,
    ChronosRunSummary,
    build_chronos_run_report,
)


def _window() -> tuple[datetime, datetime]:
    t0 = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 10, 0, 5, tzinfo=UTC)
    return t0, t1


def test_build_chronos_run_report_skipped_is_good() -> None:
    started, finished = _window()
    summary = ChronosRunSummary(skipped_reason="chronos disabled")
    r = build_chronos_run_report(summary, started_at=started, finished_at=finished)
    assert r.report_type == "chronos"
    assert r.verdict == "good"
    assert "disabled" in r.verdict_reasoning
    assert r.duration_s >= 0.0


def test_build_chronos_run_report_poor_when_findings_but_no_pool_clear() -> None:
    started, finished = _window()
    summary = ChronosRunSummary(
        processed_entries=1,
        findings_seen=2,
        pool_entries_cleared=0,
    )
    r = build_chronos_run_report(summary, started_at=started, finished_at=finished)
    assert r.verdict == "poor"
    assert "cleared" in r.verdict_reasoning.lower()


def test_build_chronos_run_report_partial_on_missing_nodes() -> None:
    started, finished = _window()
    summary = ChronosRunSummary(
        processed_entries=1,
        findings_seen=1,
        findings_resolved=1,
        pool_entries_cleared=1,
        missing_findings=1,
    )
    r = build_chronos_run_report(summary, started_at=started, finished_at=finished)
    assert r.verdict == "partial"
    assert "missing_finding_nodes" in r.anomalies


def test_chronos_run_report_round_trip_json() -> None:
    started, finished = _window()
    summary = ChronosRunSummary(
        processed_entries=1,
        findings_seen=1,
        findings_resolved=1,
        pool_entries_cleared=1,
        actions=[
            ChronosAction(
                pool_entry_id="e1",
                finding_id="FINDING-1",
                finding_type="no_issue_observed",
                severity="info",
                action="cleared_no_issue",
            )
        ],
    )
    r = build_chronos_run_report(summary, started_at=started, finished_at=finished)
    again = type(r).model_validate_json(r.model_dump_json())
    assert again.findings_seen == 1
    assert again.actions[0].action == "cleared_no_issue"
