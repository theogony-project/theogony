"""Mnemosyne conductor run report (W17)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from theogony.curiosity.mnemosyne_conductor_report import (
    ImmuneMetricSnapshot,
    MetricDefinition,
    MnemosyneConductorReport,
    MnemosyneConductorSummary,
    build_mnemosyne_conductor_report,
)
from theogony.reporting.writer import RunReportWriter


def test_mnemosyne_conductor_report_serializes_with_report_type() -> None:
    snap = ImmuneMetricSnapshot()
    m = MetricDefinition(
        metric_id="pool_clearance_ratio",
        name="Pool clearance ratio",
        rationale="test",
        numerator="a",
        denominator="b",
        desired_direction="increase",
        source="fixture",
    )
    summary = MnemosyneConductorSummary(
        metrics_defined=1,
        metric_definitions=[m],
    )
    started = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 4, 25, 12, 0, 1, tzinfo=UTC)
    rep = build_mnemosyne_conductor_report(
        summary, snapshot=snap, started_at=started, finished_at=finished
    )
    data = json.loads(rep.model_dump_json())
    assert data["report_type"] == "mnemosyne_conductor"


def test_run_report_writer_round_trips_mnemosyne_conductor_report(tmp_path: Path) -> None:
    writer = RunReportWriter(tmp_path)
    snap = ImmuneMetricSnapshot(pool_total=2, pool_cleared=1)
    m = MetricDefinition(
        metric_id="pool_clearance_ratio",
        name="Pool clearance ratio",
        rationale="test",
        numerator="pool_cleared",
        denominator="pool_total",
        desired_direction="increase",
        current_value=0.5,
        target_value=0.8,
        source="fixture",
    )
    summary = MnemosyneConductorSummary(
        metrics_defined=1,
        metric_definitions=[m],
    )
    started = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 4, 25, 12, 0, 2, tzinfo=UTC)
    rep = build_mnemosyne_conductor_report(
        summary, snapshot=snap, started_at=started, finished_at=finished
    )
    writer.write(rep)
    loaded = writer.most_recent("mnemosyne_conductor")
    assert isinstance(loaded, MnemosyneConductorReport)
    assert loaded.report_type == "mnemosyne_conductor"
    assert loaded.metrics_defined == 1
    assert loaded.snapshot.pool_total == 2


def test_build_report_marks_partial_when_llm_fallback_used() -> None:
    snap = ImmuneMetricSnapshot(query_reports_scanned=1)
    summary = MnemosyneConductorSummary(
        metrics_defined=2,
        fixture_fallback_used=True,
        metric_definitions=[
            MetricDefinition(
                metric_id="x",
                name="X",
                rationale="r",
                numerator="n",
                denominator="d",
                desired_direction="stabilize",
                source="fixture",
            )
        ],
    )
    started = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 4, 25, 12, 0, 1, tzinfo=UTC)
    rep = build_mnemosyne_conductor_report(
        summary, snapshot=snap, started_at=started, finished_at=finished
    )
    assert rep.verdict == "partial"
    assert rep.recommendations
