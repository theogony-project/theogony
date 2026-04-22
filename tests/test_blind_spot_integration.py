"""High-value integration gate for blind-spot aggregation (W3 / PHX-0058)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from theogony.config.settings import CuriositySettings
from theogony.core.model import NodeType
from theogony.curiosity.blind_spot_aggregator import run_blind_spot_aggregation
from theogony.reporting.models import (
    CitationQuality,
    MultiHopBreakdown,
    QueryRunReport,
    RegionDescriptor,
    StubVerdict,
    SynthesisBreakdown,
    new_run_id,
)
from theogony.reporting.writer import RunReportWriter


def _vec(a: float, b: float, c: float, dim: int = 8, *, jitter: float = 0.0) -> list[float]:
    v = [0.0] * dim
    v[0], v[1], v[2] = a + jitter, b, c
    return v


def _write_stub_query(writer: RunReportWriter, *, run_id: str, embedding: list[float]) -> None:
    t0 = datetime(2026, 4, 22, 20, 0, 0, tzinfo=UTC)
    rep = QueryRunReport(
        run_id=run_id,
        started_at=t0,
        finished_at=t0,
        duration_s=0.01,
        status="completed",
        verdict="good",
        query="thin-topic",
        query_length_chars=10,
        multi_hop=MultiHopBreakdown(seed_count=1, final_node_count=1, duration_ms=0),
        synthesis=SynthesisBreakdown(),
        citation_quality=CitationQuality(),
        stub_verdict=StubVerdict(
            low_node_count=True,
            stub_signal_strength=0.5,
            is_stub=True,
        ),
        region_descriptor=RegionDescriptor(
            query_embedding=embedding,
            seed_node_count=1,
            dominant_cluster_id="c-a",
            dominant_node_type=NodeType.CONCEPT,
            mean_seed_confidence=0.2,
        ),
    )
    writer.write(rep)


@pytest.mark.asyncio
async def test_ten_synthesized_query_reports_yield_one_blind_spot_candidate(tmp_path) -> None:
    """10 stub reports in three embedding blobs; only the 5-hit blob clusters at min_hits=5."""
    writer = RunReportWriter(tmp_path)
    main_ids: list[str] = []
    for i in range(5):
        rid = new_run_id()
        main_ids.append(rid)
        _write_stub_query(writer, run_id=rid, embedding=_vec(1.0, 0.0, 0.0, jitter=i * 1e-4))
    for j in range(3):
        _write_stub_query(
            writer, run_id=new_run_id(), embedding=_vec(0.0, 1.0, 0.0, jitter=j * 1e-4)
        )
    for k in range(2):
        _write_stub_query(
            writer, run_id=new_run_id(), embedding=_vec(0.0, 0.0, 1.0, jitter=k * 1e-4)
        )

    cfg = CuriositySettings(min_hits=5, window_days=30.0, aggregation_interval_s=0.0)
    written, _bag = await run_blind_spot_aggregation(
        writer,
        cfg,
        started_at=datetime(2026, 4, 22, 21, 0, 0, tzinfo=UTC),
        force=True,
    )
    assert len(written) == 1
    cand = written[0].candidate
    assert set(cand.contributing_run_ids) == set(main_ids)
