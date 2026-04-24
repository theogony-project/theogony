"""CuriosityDispatcher batch behaviour (W7-B)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from theogony.agents.argus import ArgusOutcome, ArgusResult
from theogony.curiosity.dispatcher import CuriosityDispatcher, pending_curiosity_report_count
from theogony.curiosity.run_report import AcquisitionDecision, CuriosityRunReport
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
)
from theogony.reporting.models import RegionDescriptor, new_run_id
from theogony.reporting.writer import RunReportWriter


def _minimal_report(search_query: str = "test query") -> CuriosityRunReport:
    trig = CuriosityTrigger(
        origin_query="origin",
        origin_query_run_id="qrun",
        gap_class=GapClass.EDGE_DENSITY_LOW,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=0),
        stub_signal_strength=0.6,
        proposed_acquisition_spec=AcquisitionSpec(search_query=search_query),
        budget=TriggerBudget(),
    )
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
    return CuriosityRunReport(
        started_at=t0,
        finished_at=t1,
        duration_s=1.0,
        status="completed",
        verdict="good",
        verdict_reasoning="curiosity trigger emitted",
        trigger=trig,
    )


class _StubArgus:
    def __init__(self, outcomes: list[ArgusOutcome]) -> None:
        self._outcomes = list(outcomes)
        self._i = 0

    async def process(self, trigger: CuriosityTrigger, *, dry_run: bool = False) -> ArgusResult:
        del trigger, dry_run
        outcome = self._outcomes[min(self._i, len(self._outcomes) - 1)]
        self._i += 1
        dec = AcquisitionDecision(
            candidate_source_type="gutenberg",
            candidate_identifier="1",
            candidate_title="T",
            hestia_status="approved",
            hestia_reason="stub",
            ingest_run_id="01INGESTRUNIDTEST01",
        )
        return ArgusResult(
            outcome=outcome,
            decision=dec,
            bytes_acquired=100,
            reason="stub-argus",
        )


async def test_dispatcher_processes_only_not_evaluated(tmp_path: Path) -> None:
    writer = RunReportWriter(tmp_path)
    done = _minimal_report()
    done = done.model_copy(
        update={
            "decision": AcquisitionDecision(
                candidate_source_type="gutenberg",
                hestia_status="approved",
                hestia_reason="done",
            )
        }
    )
    writer.write(done)
    pending = _minimal_report(search_query="other")
    writer.write(pending)

    assert pending_curiosity_report_count(tmp_path) == 1

    stub = _StubArgus([ArgusOutcome.APPROVED_AND_INGESTED])
    dispatcher = CuriosityDispatcher(reports_dir=tmp_path, argus=stub, writer=writer)
    results = await dispatcher.process_pending(max_triggers=5, dry_run=False)
    assert len(results) == 1


async def test_dispatcher_updates_report_on_disk(tmp_path: Path) -> None:
    writer = RunReportWriter(tmp_path)
    rep = _minimal_report()
    path = writer.write(rep)

    stub = _StubArgus([ArgusOutcome.APPROVED_AND_INGESTED])
    dispatcher = CuriosityDispatcher(reports_dir=tmp_path, argus=stub, writer=writer)
    await dispatcher.process_pending(max_triggers=5, dry_run=False)

    updated = CuriosityRunReport.model_validate_json(path.read_text(encoding="utf-8"))
    assert updated.decision.ingest_run_id == "01INGESTRUNIDTEST01"
    assert updated.bytes_acquired == 100
    assert "argus:approved_and_ingested" in updated.verdict_reasoning


async def test_dispatcher_max_cap_respected(tmp_path: Path) -> None:
    writer = RunReportWriter(tmp_path)
    for i in range(4):
        r = _minimal_report(search_query=f"q{i}")
        r = r.model_copy(update={"run_id": new_run_id()})
        writer.write(r)

    stub = _StubArgus([ArgusOutcome.DRY_RUN] * 10)
    dispatcher = CuriosityDispatcher(reports_dir=tmp_path, argus=stub, writer=writer)
    results = await dispatcher.process_pending(max_triggers=2, dry_run=True)
    assert len(results) == 2


async def test_dispatcher_dry_run_does_not_write(tmp_path: Path) -> None:
    writer = RunReportWriter(tmp_path)
    rep = _minimal_report()
    path = writer.write(rep)
    before = path.read_text(encoding="utf-8")

    stub = _StubArgus([ArgusOutcome.APPROVED_AND_INGESTED])
    dispatcher = CuriosityDispatcher(reports_dir=tmp_path, argus=stub, writer=writer)
    await dispatcher.process_pending(max_triggers=5, dry_run=True)

    assert path.read_text(encoding="utf-8") == before
