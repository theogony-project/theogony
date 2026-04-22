"""Tests for :class:`~theogony.curiosity.blind_spot_aggregation_phase.BlindSpotAggregationPhase`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from theogony.config.settings import CuriositySettings, OneirosSettings, Settings
from theogony.core.model import NodeType
from theogony.curiosity.blind_spot_aggregation_phase import BlindSpotAggregationPhase
from theogony.memory.tick_phase import TickContext
from theogony.reporting.models import (
    BlindSpotCandidate,
    BlindSpotReport,
    CitationQuality,
    MultiHopBreakdown,
    QueryRunReport,
    RegionDescriptor,
    StubVerdict,
    SynthesisBreakdown,
)
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore


def _emb(x: float, dim: int = 8, *, jitter: float = 0.0) -> list[float]:
    v = [0.0] * dim
    v[0] = x + jitter
    return v


def _stub_query(tmp_writer: RunReportWriter, rid: str, emb: list[float]) -> None:
    t0 = datetime(2026, 4, 22, 15, 0, 0, tzinfo=UTC)
    rep = QueryRunReport(
        run_id=rid,
        started_at=t0,
        finished_at=t0,
        duration_s=0.01,
        status="completed",
        verdict="good",
        query="q",
        query_length_chars=1,
        multi_hop=MultiHopBreakdown(seed_count=1, final_node_count=1, duration_ms=0),
        synthesis=SynthesisBreakdown(),
        citation_quality=CitationQuality(),
        stub_verdict=StubVerdict(
            low_node_count=True,
            stub_signal_strength=0.5,
            is_stub=True,
        ),
        region_descriptor=RegionDescriptor(
            query_embedding=emb,
            seed_node_count=1,
            dominant_cluster_id="c",
            dominant_node_type=NodeType.CONCEPT,
            mean_seed_confidence=0.3,
        ),
    )
    tmp_writer.write(rep)


def _ctx(
    *,
    writer: RunReportWriter | None,
    started_at: datetime,
    curiosity: CuriositySettings | None = None,
) -> TickContext:
    store = InMemoryKnowledgeStore()
    app = Settings()
    if curiosity is not None:
        app = app.model_copy(update={"curiosity": curiosity})
    return TickContext(
        started_at=started_at,
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=store,
        app_settings=app,
        writer=writer,
    )


@pytest.mark.asyncio
async def test_phase_skips_when_within_cadence(tmp_path) -> None:
    writer = RunReportWriter(tmp_path)
    last_t = datetime(2026, 4, 22, 10, 0, 0, tzinfo=UTC)
    prev = BlindSpotReport(
        run_id="01HZPREVBLINDSPOT00",
        started_at=last_t,
        finished_at=last_t,
        duration_s=0.0,
        status="completed",
        verdict="good",
        candidate=BlindSpotCandidate(
            contributing_run_ids=["x"],
            centroid_embedding=_emb(0.0),
            stub_signal_strength=0.1,
        ),
        window_days=30.0,
        stub_reports_scanned=1,
    )
    writer.write(prev)

    phase = BlindSpotAggregationPhase()
    ctx = _ctx(
        writer=writer,
        started_at=last_t + timedelta(seconds=30),
        curiosity=CuriositySettings(aggregation_interval_s=3600.0),
    )
    await phase.run(ctx)
    assert ctx.extras["blind_spot_aggregation"]["skipped"] == "within cadence"


@pytest.mark.asyncio
async def test_phase_runs_when_no_previous_blindspot_report(tmp_path) -> None:
    writer = RunReportWriter(tmp_path)
    for i in range(3):
        _stub_query(writer, f"01HZNEWSTUB{i:02d}00000000", _emb(9.0, jitter=i * 1e-4))
    phase = BlindSpotAggregationPhase()
    ctx = _ctx(writer=writer, started_at=datetime(2026, 4, 22, 16, 0, 0, tzinfo=UTC))
    await phase.run(ctx)
    blind_dir = tmp_path / "blindspot"
    assert blind_dir.exists()
    files = list(blind_dir.glob("*.json"))
    assert len(files) >= 1
    assert ctx.extras["blind_spot_aggregation"]["candidates_emitted"] == 1


@pytest.mark.asyncio
async def test_phase_skips_when_below_min_hits(tmp_path) -> None:
    writer = RunReportWriter(tmp_path)
    _stub_query(writer, "01HZONLYONE00000000000", _emb(1.0))
    _stub_query(writer, "01HZONLYTWO00000000000", _emb(1.0))
    phase = BlindSpotAggregationPhase()
    ctx = _ctx(
        writer=writer,
        started_at=datetime(2026, 4, 22, 17, 0, 0, tzinfo=UTC),
        curiosity=CuriositySettings(min_hits=3),
    )
    await phase.run(ctx)
    assert ctx.extras["blind_spot_aggregation"]["skipped"] == "below min_hits"


@pytest.mark.asyncio
async def test_phase_writes_one_report_per_candidate(tmp_path) -> None:
    writer = RunReportWriter(tmp_path)
    for i in range(5):
        _stub_query(writer, f"01HZCAND{i:02d}00000000000", _emb(7.0, jitter=i * 1e-4))
    phase = BlindSpotAggregationPhase()
    ctx = _ctx(
        writer=writer,
        started_at=datetime(2026, 4, 22, 18, 0, 0, tzinfo=UTC),
        curiosity=CuriositySettings(min_hits=4),
    )
    await phase.run(ctx)
    files = list((tmp_path / "blindspot").glob("*.json"))
    assert len(files) == 1


@pytest.mark.asyncio
async def test_phase_publishes_observability_to_ctx_extras(tmp_path) -> None:
    writer = RunReportWriter(tmp_path)
    for i in range(3):
        _stub_query(writer, f"01HZEXTRA{i:02d}0000000000", _emb(5.0, jitter=i * 1e-4))
    phase = BlindSpotAggregationPhase()
    ctx = _ctx(writer=writer, started_at=datetime(2026, 4, 22, 19, 0, 0, tzinfo=UTC))
    await phase.run(ctx)
    assert "blind_spot_aggregation" in ctx.extras
    payload = ctx.extras["blind_spot_aggregation"]
    assert isinstance(payload, dict)
    assert "stub_reports_scanned" in payload or "skipped" in payload


@pytest.mark.asyncio
async def test_phase_force_bypasses_cadence(tmp_path) -> None:
    writer = RunReportWriter(tmp_path)
    last_t = datetime(2026, 4, 22, 10, 0, 0, tzinfo=UTC)
    writer.write(
        BlindSpotReport(
            run_id="01HZPREVFORCE0000000",
            started_at=last_t,
            finished_at=last_t,
            duration_s=0.0,
            status="completed",
            verdict="good",
            candidate=BlindSpotCandidate(
                contributing_run_ids=["x"],
                centroid_embedding=_emb(0.0),
                stub_signal_strength=0.1,
            ),
            window_days=30.0,
            stub_reports_scanned=1,
        )
    )
    for i in range(4):
        _stub_query(writer, f"01HZFORCED{i:02d}000000000", _emb(8.0, jitter=i * 1e-4))
    phase = BlindSpotAggregationPhase()
    ctx = _ctx(
        writer=writer,
        started_at=last_t + timedelta(seconds=10),
        curiosity=CuriositySettings(aggregation_interval_s=999999.0, min_hits=4),
    )
    ctx.extras["blind_spot_force"] = True
    await phase.run(ctx)
    assert ctx.extras["blind_spot_aggregation"].get("candidates_emitted", 0) >= 1
