"""Tests for Mnemosyne aggregation phase (PHX-0071 / W5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from theogony.agents.mnemosyne_phase import MnemosyneAggregationPhase, run_mnemosyne_aggregation
from theogony.config.settings import MnemosyneSettings, OneirosSettings, Settings
from theogony.core.model import NodeType
from theogony.memory.tick_phase import TickContext
from theogony.reporting.models import (
    CitationQuality,
    MetaClassification,
    MetaClassificationVerdict,
    MnemosyneObservationCluster,
    MultiHopBreakdown,
    QueryRunReport,
    RegionDescriptor,
    StubVerdict,
    SynthesisBreakdown,
    new_run_id,
)
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore


def _emb(prefix: float, dim: int = 8, *, jitter: float = 0.0) -> list[float]:
    v = [0.0] * dim
    v[0] = prefix + jitter
    return v


def _sr_report(
    run_id: str,
    *,
    embedding: list[float],
    started_at: datetime | None = None,
) -> QueryRunReport:
    t0 = started_at or datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)
    return QueryRunReport(
        run_id=run_id,
        started_at=t0,
        finished_at=t0,
        duration_s=0.01,
        status="completed",
        verdict="good",
        query="embedding schema question",
        query_length_chars=10,
        multi_hop=MultiHopBreakdown(seed_count=1, final_node_count=1, duration_ms=0),
        synthesis=SynthesisBreakdown(),
        citation_quality=CitationQuality(),
        stub_verdict=StubVerdict(is_stub=False, stub_signal_strength=0.0),
        region_descriptor=RegionDescriptor(
            query_embedding=embedding,
            seed_node_count=1,
            dominant_cluster_id="c1",
            dominant_node_type=NodeType.CONCEPT,
            mean_seed_confidence=0.5,
        ),
        meta_classification=MetaClassification(
            verdict=MetaClassificationVerdict.SELF_REFERENTIAL,
            high_keyword_hits=1,
            mid_keyword_hits=0,
        ),
        cited_node_ids=["AKA-one"],
    )


@pytest.mark.asyncio
async def test_phase_skips_when_within_cadence(tmp_path) -> None:
    writer = RunReportWriter(tmp_path / "rr")
    t0 = datetime.now(UTC)
    prev = MnemosyneObservationCluster(
        run_id=new_run_id(),
        started_at=t0 - timedelta(seconds=10),
        finished_at=t0 - timedelta(seconds=10),
        duration_s=1.0,
        status="completed",
        verdict="good",
        verdict_reasoning="x",
        centroid_embedding=[1.0, 0.0],
        contributing_run_ids=["a"],
        contributing_query_count=1,
        aggregate_keyword_hits=1,
        window_days=14.0,
    )
    writer.write(prev)

    ctx = TickContext(
        started_at=t0,
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=InMemoryKnowledgeStore(),
        app_settings=Settings(),
        writer=writer,
    )
    await MnemosyneAggregationPhase().run(ctx)
    bag = ctx.extras.get("mnemosyne_aggregation", {})
    assert bag.get("skipped") == "within cadence"


@pytest.mark.asyncio
async def test_phase_runs_when_no_previous_mnemosyne_report(tmp_path) -> None:
    writer = RunReportWriter(tmp_path / "rr")
    for i in range(4):
        writer.write(
            _sr_report(
                f"01MNPHASE{i:02d}",
                embedding=_emb(1.0, jitter=i * 1e-4),
                started_at=datetime(2026, 4, 22, 12, i, 0, tzinfo=UTC),
            )
        )
    ctx = TickContext(
        started_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=InMemoryKnowledgeStore(),
        app_settings=Settings(),
        writer=writer,
    )
    ctx.extras["mnemosyne_force"] = True
    await MnemosyneAggregationPhase().run(ctx)
    assert "mnemosyne_aggregation" in ctx.extras


@pytest.mark.asyncio
async def test_phase_skips_when_below_min_observations(tmp_path) -> None:
    writer = RunReportWriter(tmp_path / "rr")
    writer.write(_sr_report("01MNBELOW1", embedding=_emb(1.0)))
    cfg = MnemosyneSettings(min_observations=5)
    written, bag = await run_mnemosyne_aggregation(
        writer,
        cfg,
        started_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC),
        force=True,
    )
    assert written == []
    assert bag["mnemosyne_aggregation"]["skipped"] == "below min_observations"


@pytest.mark.asyncio
async def test_phase_writes_one_cluster_per_emergent_pattern(tmp_path) -> None:
    writer = RunReportWriter(tmp_path / "rr")
    for i in range(5):
        writer.write(
            _sr_report(
                f"01MNCLUSTER{i}",
                embedding=_emb(10.0 + float(i), jitter=i * 1e-4),
                started_at=datetime(2026, 4, 22, 12, i, 0, tzinfo=UTC),
            )
        )
    written, _bag = await run_mnemosyne_aggregation(
        writer,
        MnemosyneSettings(min_observations=3),
        started_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC),
        force=True,
    )
    assert len(written) >= 1


@pytest.mark.asyncio
async def test_phase_publishes_observability_to_ctx_extras(tmp_path) -> None:
    writer = RunReportWriter(tmp_path / "rr")
    for i in range(4):
        writer.write(
            _sr_report(
                f"01MNEXTRA{i}",
                embedding=_emb(2.0, jitter=i * 1e-4),
                started_at=datetime(2026, 4, 22, 12, i, 0, tzinfo=UTC),
            )
        )
    ctx = TickContext(
        started_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=InMemoryKnowledgeStore(),
        app_settings=Settings(),
        writer=writer,
    )
    ctx.extras["mnemosyne_force"] = True
    await MnemosyneAggregationPhase().run(ctx)
    bag = ctx.extras["mnemosyne_aggregation"]
    assert "observations_scanned" in bag or "clusters_emitted" in bag or "skipped" in bag
