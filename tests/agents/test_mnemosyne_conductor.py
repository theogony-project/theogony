"""Mnemosyne conductor agent (W17)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from theogony.agents.mnemosyne_conductor import (
    FixtureMetricDefiner,
    ImmuneMetricCollector,
    MnemosyneConductor,
)
from theogony.config.settings import Settings
from theogony.core.model import Layer, NodeType
from theogony.curiosity.chronos_report import (
    ChronosRunSummary,
    build_chronos_run_report,
)
from theogony.curiosity.eris_report import ErisCampaignSummary, build_eris_campaign_report
from theogony.curiosity.finding import Finding
from theogony.curiosity.mnemosyne_conductor_report import ImmuneMetricSnapshot
from theogony.curiosity.nemesis_report import NemesisRunSummary, build_nemesis_run_report
from theogony.curiosity.verification_pool import VerificationPool
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("THEOGONY_DATA_DIR", str(tmp_path / "data"))
    return Settings()


def test_collector_counts_pool_stats(isolated_settings: Settings) -> None:
    pool = VerificationPool(isolated_settings)
    pool.register("e1")
    pool.register("e2")
    writer = RunReportWriter(isolated_settings.run_reports_dir)
    store = InMemoryKnowledgeStore()
    collector = ImmuneMetricCollector(store=store, pool=pool, writer=writer)

    snap = asyncio.run(collector.collect())
    assert snap.pool_total == 2


def test_collector_counts_finding_nodes_by_cell_type_severity(
    isolated_settings: Settings,
) -> None:
    pool = VerificationPool(isolated_settings)
    writer = RunReportWriter(isolated_settings.run_reports_dir)
    store = InMemoryKnowledgeStore()
    t = datetime(2026, 4, 25, tzinfo=UTC)
    f1 = Finding(
        finding_id="F1",
        finding_type="no_issue_observed",
        severity="info",
        cell="athene",
        pool_entry_id="p1",
        sampled_at=t,
    )
    f2 = Finding(
        finding_id="F2",
        finding_type="confidence_inflation",
        severity="high",
        cell="nemesis",
        pool_entry_id="p2",
        sampled_at=t,
        resolution_action="annotated",
        resolved_at=t,
    )

    async def _seed() -> None:
        await store.batch_upsert_nodes([f1.to_knowledge_node(), f2.to_knowledge_node()])

    asyncio.run(_seed())
    collector = ImmuneMetricCollector(store=store, pool=pool, writer=writer)
    snap = asyncio.run(collector.collect())
    assert snap.finding_count_by_cell["athene"] == 1
    assert snap.finding_count_by_cell["nemesis"] == 1
    assert snap.finding_count_by_type["no_issue_observed"] == 1
    assert snap.finding_count_by_severity["info"] == 1
    assert snap.unresolved_finding_count == 1


def test_collector_reads_latest_chronos_nemesis_eris_reports(isolated_settings: Settings) -> None:
    writer = RunReportWriter(isolated_settings.run_reports_dir)
    pool = VerificationPool(isolated_settings)
    store = InMemoryKnowledgeStore()
    t0 = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 10, 0, 5, tzinfo=UTC)
    writer.write(
        build_chronos_run_report(
            ChronosRunSummary(
                findings_seen=4,
                findings_resolved=2,
                negative_edges_written=1,
                nodes_demoted=1,
                pool_entries_cleared=3,
            ),
            started_at=t0,
            finished_at=t1,
        )
    )
    writer.write(
        build_nemesis_run_report(
            NemesisRunSummary(findings_written=5, audits_run=["confidence_inflation"]),
            started_at=t0,
            finished_at=t1,
        )
    )
    writer.write(
        build_eris_campaign_report(
            ErisCampaignSummary(probes_run=10, failed=2, passed=8, fixture_mode=True),
            started_at=t0,
            finished_at=t1,
        )
    )
    collector = ImmuneMetricCollector(store=store, pool=pool, writer=writer)

    snap = asyncio.run(collector.collect())
    assert snap.latest_chronos_findings_seen == 4
    assert snap.latest_chronos_pool_entries_cleared == 3
    assert snap.latest_nemesis_findings_written == 5
    assert snap.latest_eris_probes_run == 10
    assert snap.latest_eris_failed == 2


def test_collector_counts_query_and_ingest_verdicts(isolated_settings: Settings) -> None:
    writer = RunReportWriter(isolated_settings.run_reports_dir)
    pool = VerificationPool(isolated_settings)
    store = InMemoryKnowledgeStore()
    qdir = writer.directory_for("query")
    idir = writer.directory_for("ingest")
    finished = "2026-04-25T12:00:00+00:00"
    (qdir / "01JQUERY00000000000000000001.json").write_text(
        json.dumps({"verdict": "good", "finished_at": finished}),
        encoding="utf-8",
    )
    (qdir / "01JQUERY00000000000000000002.json").write_text(
        json.dumps({"verdict": "poor", "finished_at": finished}),
        encoding="utf-8",
    )
    (idir / "01JINGEST0000000000000000001.json").write_text(
        json.dumps({"verdict": "partial", "finished_at": finished}),
        encoding="utf-8",
    )
    collector = ImmuneMetricCollector(store=store, pool=pool, writer=writer)

    snap = asyncio.run(collector.collect())
    assert snap.query_reports_scanned == 2
    assert snap.query_verdict_counts == {"good": 1, "poor": 1}
    assert snap.ingest_reports_scanned == 1
    assert snap.ingest_verdict_counts == {"partial": 1}


def test_conductor_disabled_returns_snapshot_and_skipped_summary(
    isolated_settings: Settings,
) -> None:
    settings = isolated_settings.model_copy(
        update={
            "mnemosyne": isolated_settings.mnemosyne.model_copy(update={"conductor_enabled": False})
        }
    )
    writer = RunReportWriter(settings.run_reports_dir)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()
    conductor = MnemosyneConductor(
        store=store,
        pool=pool,
        writer=writer,
        settings=settings,
    )

    summary, snap = asyncio.run(conductor.run_once())
    assert summary.skipped_reason == "mnemosyne conductor disabled"
    assert summary.metrics_defined == 0
    assert isinstance(snap, ImmuneMetricSnapshot)


@pytest.mark.asyncio
async def test_fixture_metric_definer_defines_expected_metrics() -> None:
    snap = ImmuneMetricSnapshot(
        pool_total=10, pool_cleared=5, pool_findings_total=4, unresolved_finding_count=1
    )
    snap.latest_eris_failed = 3
    snap.latest_eris_probes_run = 10
    defs, cost = await FixtureMetricDefiner().define_metrics(snap)
    assert cost == 0.0
    ids = {d.metric_id for d in defs}
    assert ids == {"pool_clearance_ratio", "unresolved_finding_ratio", "red_team_failure_count"}
    red = next(d for d in defs if d.metric_id == "red_team_failure_count")
    assert red.current_value == 3.0


def test_conductor_writes_experiment_nodes(isolated_settings: Settings) -> None:
    settings = isolated_settings.model_copy(
        update={
            "mnemosyne": isolated_settings.mnemosyne.model_copy(update={"conductor_enabled": True})
        }
    )
    writer = RunReportWriter(settings.run_reports_dir)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()

    async def _run() -> None:
        c = MnemosyneConductor(store=store, pool=pool, writer=writer, settings=settings)
        summary, _ = await c.run_once()
        assert summary.experiment_nodes_written >= 1

    asyncio.run(_run())
    found = False

    async def _scan() -> None:
        nonlocal found
        async for n in store.export_layer(Layer.EPHEMERA):
            if n.node_type == NodeType.EXPERIMENT:
                found = True
                break

    asyncio.run(_scan())
    assert found


def test_conductor_writes_backlog_draft_json_files(isolated_settings: Settings) -> None:
    settings = isolated_settings.model_copy(
        update={
            "mnemosyne": isolated_settings.mnemosyne.model_copy(update={"conductor_enabled": True})
        }
    )
    writer = RunReportWriter(settings.run_reports_dir)
    t0 = datetime(2026, 4, 25, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 10, 0, 1, tzinfo=UTC)
    writer.write(
        build_eris_campaign_report(
            ErisCampaignSummary(probes_run=2, failed=1, passed=1, fixture_mode=True),
            started_at=t0,
            finished_at=t1,
        )
    )
    pool = VerificationPool(settings)
    for _ in range(3):
        pool.register("draft-test")
    store = InMemoryKnowledgeStore()

    async def _run() -> None:
        c = MnemosyneConductor(store=store, pool=pool, writer=writer, settings=settings)
        await c.run_once()

    asyncio.run(_run())
    draft_dir = settings.run_reports_dir / settings.mnemosyne.backlog_draft_dir_name
    assert draft_dir.is_dir()
    json_files = list(draft_dir.glob("*.json"))
    assert json_files


class _RaisingLLM:
    """Non-stub LLM that fails structured completion (exercises fixture fallback)."""

    @property
    def model_id(self) -> str:
        return "raising-llm"

    async def complete(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("simulated provider failure")


def test_conductor_falls_back_to_fixture_when_llm_unavailable(isolated_settings: Settings) -> None:
    settings = isolated_settings.model_copy(
        update={
            "mnemosyne": isolated_settings.mnemosyne.model_copy(
                update={"conductor_enabled": True, "metric_definition_mode": "llm"}
            )
        }
    )
    writer = RunReportWriter(settings.run_reports_dir)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()
    conductor = MnemosyneConductor(
        store=store,
        pool=pool,
        writer=writer,
        settings=settings,
        llm=_RaisingLLM(),
    )

    summary, _ = asyncio.run(conductor.run_once())
    assert summary.fixture_fallback_used
    assert summary.metrics_defined >= 1


def test_conductor_does_not_modify_settings_even_when_auto_apply_enabled(
    isolated_settings: Settings,
) -> None:
    settings = isolated_settings.model_copy(
        update={
            "mnemosyne": isolated_settings.mnemosyne.model_copy(
                update={
                    "conductor_enabled": True,
                    "metric_definition_mode": "fixture",
                    "auto_apply_enabled": True,
                }
            )
        }
    )
    before = settings.model_dump()
    writer = RunReportWriter(settings.run_reports_dir)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()
    conductor = MnemosyneConductor(store=store, pool=pool, writer=writer, settings=settings)

    asyncio.run(conductor.run_once())
    assert settings.model_dump() == before


def test_conductor_never_writes_to_phoenix_backlog(isolated_settings: Settings) -> None:
    """Draft JSON lives under run_reports only, not the repo backlog directory name."""
    forbidden = "phoenix" + "-backlog"
    settings = isolated_settings.model_copy(
        update={
            "mnemosyne": isolated_settings.mnemosyne.model_copy(update={"conductor_enabled": True})
        }
    )
    writer = RunReportWriter(settings.run_reports_dir)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()
    conductor = MnemosyneConductor(store=store, pool=pool, writer=writer, settings=settings)

    asyncio.run(conductor.run_once())
    assert not (isolated_settings.data_dir.parent / forbidden).exists()
