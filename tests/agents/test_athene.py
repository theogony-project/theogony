"""W14 AtheneVerifier."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from theogony.agents.athene import AtheneVerifier
from theogony.config.settings import AtheneSettings, Settings
from theogony.core.model import NodeType
from theogony.curiosity.verification_pool import VerificationPool
from theogony.reporting.models import (
    EmbeddingSummary,
    IngestRunReport,
    NerSummary,
    QualityFlags,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
)
from theogony.stores.memory import InMemoryKnowledgeStore


def _minimal_report(
    *,
    run_id: str = "ing-run-1",
    status: Literal["completed", "partial", "failed", "aborted"] = "completed",
    verdict: Literal["good", "partial", "poor", "failed"] = "good",
    verdict_reasoning: str = "",
    quality: QualityFlags | None = None,
) -> IngestRunReport:
    now = datetime.now(UTC)
    qf = quality or QualityFlags()
    return IngestRunReport(
        run_id=run_id,
        started_at=now,
        finished_at=now,
        duration_s=0.0,
        status=status,
        verdict=verdict,
        verdict_reasoning=verdict_reasoning,
        ingest_run_id=run_id,
        source_type="gutenberg",
        source_identifier="1",
        word_count=1,
        sentence_count=1,
        ner=NerSummary(total_mentions=0),
        resolution=ResolutionSummary(),
        relations=RelationSummary(),
        embedding=EmbeddingSummary(nodes_embedded=0, embedding_model_id="stub", duration_s=0.0),
        store=StoreSummary(nodes_upserted=0, edges_upserted=0),
        quality_flags=qf,
    )


def _settings_dir(tmp_path) -> Settings:
    return Settings().model_copy(update={"data_dir": tmp_path})


@pytest.mark.asyncio
async def test_athene_disabled_returns_skipped_summary(tmp_path: Path) -> None:
    settings = _settings_dir(tmp_path)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()
    v = AtheneVerifier(
        store=store,
        pool=pool,
        settings=AtheneSettings(enabled=False),
        run_reports_dir=settings.run_reports_dir,
    )
    s = await v.run_once(seed=1)
    assert s.skipped_reason == "athene disabled"
    assert s.sampled_count == 0


@pytest.mark.asyncio
async def test_athene_no_entries_returns_zero_summary(tmp_path: Path) -> None:
    settings = _settings_dir(tmp_path)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()
    v = AtheneVerifier(
        store=store,
        pool=pool,
        settings=AtheneSettings(enabled=True, sample_rate=0.0, min_entries_per_pass=0),
        run_reports_dir=settings.run_reports_dir,
    )
    s = await v.run_once(seed=1)
    assert s.skipped_reason is None
    assert s.sampled_count == 0
    assert s.findings_written == 0


@pytest.mark.asyncio
async def test_athene_missing_ingest_report_writes_medium_finding(tmp_path: Path) -> None:
    settings = _settings_dir(tmp_path)
    pool = VerificationPool(settings)
    pool.register("c", ingest_run_id="missing-report")
    store = InMemoryKnowledgeStore()
    v = AtheneVerifier(
        store=store,
        pool=pool,
        settings=AtheneSettings(enabled=True, sample_rate=1.0, min_entries_per_pass=1),
        run_reports_dir=settings.run_reports_dir,
    )
    s = await v.run_once(seed=0)
    assert s.sampled_count == 1
    assert s.findings_written == 1
    mem = store._nodes  # noqa: SLF001
    finding_nodes = [n for n in mem.values() if n.node_type == NodeType.FINDING]
    assert len(finding_nodes) == 1
    assert finding_nodes[0].properties["finding_type"] == "ingest_report_missing"


@pytest.mark.asyncio
async def test_athene_failed_ingest_report_writes_high_finding(tmp_path: Path) -> None:
    settings = _settings_dir(tmp_path)
    ingest_dir = settings.run_reports_dir / "ingest"
    ingest_dir.mkdir(parents=True)
    rid = "fail-1"
    ingest_dir.joinpath(f"{rid}.json").write_text(
        _minimal_report(
            run_id=rid, status="failed", verdict="failed", verdict_reasoning="boom"
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    pool = VerificationPool(settings)
    e = pool.register("c", ingest_run_id=rid)
    store = InMemoryKnowledgeStore()
    v = AtheneVerifier(
        store=store,
        pool=pool,
        settings=AtheneSettings(enabled=True, sample_rate=1.0, min_entries_per_pass=1),
        run_reports_dir=settings.run_reports_dir,
    )
    await v.run_once(seed=0)
    mem = store._nodes  # noqa: SLF001
    finding_nodes = [n for n in mem.values() if n.node_type == NodeType.FINDING]
    assert finding_nodes[0].properties["finding_type"] == "ingest_failed"
    updated = pool.get(e.entry_id)
    assert updated is not None
    assert updated.lifecycle == "sampled_by_athene"


@pytest.mark.asyncio
async def test_athene_clean_ingest_report_writes_no_issue_observed(tmp_path: Path) -> None:
    settings = _settings_dir(tmp_path)
    ingest_dir = settings.run_reports_dir / "ingest"
    ingest_dir.mkdir(parents=True)
    rid = "ok-1"
    ingest_dir.joinpath(f"{rid}.json").write_text(
        _minimal_report(run_id=rid).model_dump_json(indent=2),
        encoding="utf-8",
    )
    pool = VerificationPool(settings)
    pool.register("c", ingest_run_id=rid)
    store = InMemoryKnowledgeStore()
    v = AtheneVerifier(
        store=store,
        pool=pool,
        settings=AtheneSettings(enabled=True, sample_rate=1.0, min_entries_per_pass=1),
        run_reports_dir=settings.run_reports_dir,
    )
    await v.run_once(seed=0)
    mem = store._nodes  # noqa: SLF001
    finding_nodes = [n for n in mem.values() if n.node_type == NodeType.FINDING]
    assert finding_nodes[0].properties["finding_type"] == "no_issue_observed"


@pytest.mark.asyncio
async def test_athene_marks_pool_entry_sampled_after_writing_finding(tmp_path: Path) -> None:
    settings = _settings_dir(tmp_path)
    ingest_dir = settings.run_reports_dir / "ingest"
    ingest_dir.mkdir(parents=True)
    rid = "ok-2"
    ingest_dir.joinpath(f"{rid}.json").write_text(
        _minimal_report(run_id=rid).model_dump_json(indent=2),
        encoding="utf-8",
    )
    pool = VerificationPool(settings)
    e = pool.register("c", ingest_run_id=rid)
    store = InMemoryKnowledgeStore()
    v = AtheneVerifier(
        store=store,
        pool=pool,
        settings=AtheneSettings(enabled=True, sample_rate=1.0, min_entries_per_pass=1),
        run_reports_dir=settings.run_reports_dir,
    )
    await v.run_once(seed=0)
    updated = pool.get(e.entry_id)
    assert updated is not None
    assert updated.lifecycle == "sampled_by_athene"
    assert len(updated.finding_ids) == 1


def test_athene_never_calls_ingest_or_argus() -> None:
    import inspect

    from theogony.agents import athene as athene_mod

    src = inspect.getsource(athene_mod.AtheneVerifier)
    assert "IngestRunner" not in src
    assert "Argus" not in src
