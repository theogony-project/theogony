"""ErisCampaignReport (W16)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from theogony.curiosity.eris_report import (
    ErisCampaignReport,
    ErisCampaignSummary,
    ErisProbeResult,
    build_eris_campaign_report,
)
from theogony.reporting.writer import RunReportWriter


def _window() -> tuple[datetime, datetime]:
    t0 = datetime(2026, 4, 25, 11, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 11, 0, 2, tzinfo=UTC)
    return t0, t1


def test_eris_campaign_report_serializes_with_report_type_eris() -> None:
    started, finished = _window()
    summary = ErisCampaignSummary(
        campaign_label="t1",
        probes_run=1,
        passed=1,
        probe_results=[
            ErisProbeResult(
                probe_id="p1",
                probe_kind="source_poisoning_fixture",
                prompt_or_label="x",
                outcome="passed",
            )
        ],
    )
    r = build_eris_campaign_report(summary, started_at=started, finished_at=finished)
    assert r.report_type == "eris"
    again = ErisCampaignReport.model_validate_json(r.model_dump_json())
    assert again.campaign_label == "t1"


def test_run_report_writer_round_trips_eris_report(tmp_path: Path) -> None:
    started, finished = _window()
    writer = RunReportWriter(tmp_path)
    summary = ErisCampaignSummary(
        campaign_label="w16-fixture",
        probes_run=0,
        skipped_reason="eris disabled",
    )
    report = build_eris_campaign_report(summary, started_at=started, finished_at=finished)
    path = writer.write(report)
    assert path.parent.name == "eris"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["report_type"] == "eris"
    recent = writer.most_recent("eris")
    assert isinstance(recent, ErisCampaignReport)
