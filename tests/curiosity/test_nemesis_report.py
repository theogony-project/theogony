"""NemesisRunReport (W16)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from theogony.curiosity.nemesis_report import (
    NemesisFindingRecord,
    NemesisRunReport,
    NemesisRunSummary,
    build_nemesis_run_report,
)
from theogony.reporting.writer import RunReportWriter


def _window() -> tuple[datetime, datetime]:
    t0 = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 10, 0, 3, tzinfo=UTC)
    return t0, t1


def test_nemesis_run_report_serializes_with_report_type_nemesis() -> None:
    started, finished = _window()
    summary = NemesisRunSummary(
        audits_run=["confidence_inflation"],
        findings_written=1,
        confidence_inflation_count=1,
        findings=[
            NemesisFindingRecord(
                finding_id="FINDING-1",
                finding_type="confidence_inflation",
                severity="medium",
                target_node_ids=["N1"],
                evidence=["x"],
            )
        ],
    )
    r = build_nemesis_run_report(summary, started_at=started, finished_at=finished)
    assert r.report_type == "nemesis"
    again = NemesisRunReport.model_validate_json(r.model_dump_json())
    assert again.findings_written == 1
    assert again.findings[0].finding_type == "confidence_inflation"


def test_run_report_writer_round_trips_nemesis_report(tmp_path: Path) -> None:
    started, finished = _window()
    writer = RunReportWriter(tmp_path)
    summary = NemesisRunSummary(findings_written=0, audits_run=["pheromone_autobahn"])
    report = build_nemesis_run_report(summary, started_at=started, finished_at=finished)
    path = writer.write(report)
    assert path.parent.name == "nemesis"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["report_type"] == "nemesis"
    recent = writer.most_recent("nemesis")
    assert isinstance(recent, NemesisRunReport)
