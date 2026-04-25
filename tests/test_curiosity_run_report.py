"""
CuriosityRunReport schema and writer integration (W7-A, PHX-0037 slice 1).

Mirrors the discipline of the BlindSpotReport tests: the report
serialises losslessly, the writer routes it to the correct
per-type directory, and the most-recent reader can round-trip it
back from disk.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from theogony.curiosity.run_report import AcquisitionDecision, CuriosityRunReport
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
    TriggerReason,
)
from theogony.reporting.models import RegionDescriptor
from theogony.reporting.writer import RunReportWriter


def _trigger() -> CuriosityTrigger:
    return CuriosityTrigger(
        origin_query="Wer war Sven Hedin?",
        origin_query_run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=1),
        stub_signal_strength=0.75,
        proposed_acquisition_spec=AcquisitionSpec(
            search_query="Sven Hedin Tibet",
            rationale="seed_node_count=1",
        ),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.WEAK_ANSWER,
        answer_verdict="partial",
        cited_node_count=1,
    )


def _report() -> CuriosityRunReport:
    started = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 4, 24, 12, 0, 1, tzinfo=UTC)
    return CuriosityRunReport(
        started_at=started,
        finished_at=finished,
        duration_s=1.0,
        status="completed",
        verdict="good",
        verdict_reasoning="research initiated for weak answer",
        trigger=_trigger(),
    )


class TestSchema:
    def test_round_trip_json(self) -> None:
        report = _report()
        payload = report.model_dump_json()
        restored = CuriosityRunReport.model_validate_json(payload)
        assert restored == report
        assert restored.report_type == "curiosity"
        assert restored.bytes_acquired == 0
        assert restored.decision.status == "pending"

    def test_extra_field_rejected(self) -> None:
        payload = json.loads(_report().model_dump_json())
        payload["surprise"] = "noise"
        with pytest.raises(ValidationError):
            CuriosityRunReport.model_validate(payload)

    def test_acquisition_decision_processed_shape(self) -> None:
        # Argus populates this; W7-A leaves the defaults. The schema
        # must accept the populated form without an extra schema bump.
        decision = AcquisitionDecision(
            candidate_source_type="gutenberg",
            candidate_identifier="43497",
            candidate_title="Trans-Himalaya",
            status="processed",
            reason="ingest completed",
            ingest_run_id="01ARZ3NDEKTSV4RRFFQ69G5FAW",
            pool_entry_id="pool-1",
        )
        report = _report()
        report = report.model_copy(update={"decision": decision, "bytes_acquired": 12345})
        assert report.decision.candidate_title == "Trans-Himalaya"
        assert report.bytes_acquired == 12345


class TestWriter:
    def test_writes_curiosity_to_correct_directory(self, tmp_path: Path) -> None:
        writer = RunReportWriter(tmp_path)
        report = _report()
        path = writer.write(report)
        assert path.exists()
        assert path.parent.name == "curiosity"
        # The file is the only entry in the directory.
        siblings = list(path.parent.iterdir())
        assert len(siblings) == 1
        # Round-trip through most_recent.
        recent = writer.most_recent("curiosity")
        assert isinstance(recent, CuriosityRunReport)
        assert recent.trigger.origin_query == "Wer war Sven Hedin?"

    def test_disk_payload_round_trip(self, tmp_path: Path) -> None:
        writer = RunReportWriter(tmp_path)
        report = _report()
        path = writer.write(report)
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["report_type"] == "curiosity"
        assert on_disk["trigger"]["gap_class"] == "region_thin"
        assert on_disk["decision"]["status"] == "pending"
