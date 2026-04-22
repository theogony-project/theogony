"""Tests for blind-spot aggregation helpers (W3 / PHX-0058)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from theogony.clustering.hdbscan_strategy import HDBSCANStrategy
from theogony.config.settings import CuriositySettings
from theogony.core.model import NodeType
from theogony.curiosity.blind_spot_aggregator import aggregate_blind_spots
from theogony.reporting.models import (
    CitationQuality,
    MultiHopBreakdown,
    QueryRunReport,
    RegionDescriptor,
    StubVerdict,
    SynthesisBreakdown,
)


def _emb(prefix: float, dim: int = 8, *, jitter: float = 0.0) -> list[float]:
    """Slight jitter avoids HDBSCAN treating duplicate rows as all-noise."""
    v = [0.0] * dim
    v[0] = prefix + jitter
    return v


def _query_report(
    run_id: str,
    *,
    embedding: list[float],
    stub_strength: float = 0.5,
    cluster_id: str | None = "c-main",
    node_type: NodeType = NodeType.CONCEPT,
    started_at: datetime | None = None,
    with_descriptor: bool = True,
) -> QueryRunReport:
    t0 = started_at or datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)
    desc = (
        RegionDescriptor(
            query_embedding=embedding,
            seed_node_count=1,
            dominant_cluster_id=cluster_id,
            dominant_node_type=node_type,
            mean_seed_confidence=0.4,
        )
        if with_descriptor
        else None
    )
    return QueryRunReport(
        run_id=run_id,
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
            stub_signal_strength=stub_strength,
            is_stub=True,
        ),
        region_descriptor=desc,
    )


def test_aggregator_returns_empty_when_below_min_hits() -> None:
    cfg = CuriositySettings(min_hits=5)
    reports = [_query_report("01HZAAA", embedding=_emb(1.0))]
    out = aggregate_blind_spots(
        stub_reports=reports,
        clustering_strategy=HDBSCANStrategy(
            min_cluster_size=cfg.min_hits,
            min_samples=1,
            allow_single_cluster=True,
        ),
        thresholds=cfg,
    )
    assert out == []


def test_aggregator_skips_reports_without_region_descriptor() -> None:
    cfg = CuriositySettings(min_hits=3)
    reports = [
        _query_report("01HZ001", embedding=_emb(1.0), with_descriptor=False),
        _query_report("02HZ002", embedding=_emb(1.0), with_descriptor=False),
        _query_report("03HZ003", embedding=_emb(1.0), with_descriptor=False),
    ]
    out = aggregate_blind_spots(
        stub_reports=reports,
        clustering_strategy=HDBSCANStrategy(
            min_cluster_size=cfg.min_hits,
            min_samples=1,
            allow_single_cluster=True,
        ),
        thresholds=cfg,
    )
    assert out == []


def test_aggregator_emits_one_candidate_per_cluster() -> None:
    cfg = CuriositySettings(min_hits=3)
    reports = [
        _query_report(
            f"0{i}STUBCL",
            embedding=_emb(1.0, jitter=i * 1e-4),
            started_at=datetime(2026, 4, 22, 12, i, 0, tzinfo=UTC),
        )
        for i in range(5)
    ]
    out = aggregate_blind_spots(
        stub_reports=reports,
        clustering_strategy=HDBSCANStrategy(
            min_cluster_size=cfg.min_hits,
            min_samples=1,
            allow_single_cluster=True,
        ),
        thresholds=cfg,
    )
    assert len(out) == 1
    assert set(out[0].contributing_run_ids) == {r.run_id for r in reports}


def test_aggregator_aggregates_strength_across_contributing_reports() -> None:
    cfg = CuriositySettings(min_hits=3)
    strengths = [0.2, 0.4, 0.6]
    reports = [
        _query_report(
            f"0{i}STRENG",
            embedding=_emb(2.0, jitter=i * 1e-4),
            stub_strength=s,
            started_at=datetime(2026, 4, 22, 13, i, 0, tzinfo=UTC),
        )
        for i, s in enumerate(strengths)
    ]
    out = aggregate_blind_spots(
        stub_reports=reports,
        clustering_strategy=HDBSCANStrategy(
            min_cluster_size=cfg.min_hits,
            min_samples=1,
            allow_single_cluster=True,
        ),
        thresholds=cfg,
    )
    assert len(out) == 1
    assert out[0].stub_signal_strength == pytest.approx(sum(strengths) / len(strengths))


def test_aggregator_picks_most_common_dominant_cluster_id() -> None:
    cfg = CuriositySettings(min_hits=3)
    reports = [
        _query_report("01HZC1A", embedding=_emb(3.0, jitter=0.0), cluster_id="c-a"),
        _query_report("02HZC1B", embedding=_emb(3.0, jitter=1e-4), cluster_id="c-a"),
        _query_report("03HZC2C", embedding=_emb(3.0, jitter=2e-4), cluster_id="c-b"),
    ]
    out = aggregate_blind_spots(
        stub_reports=reports,
        clustering_strategy=HDBSCANStrategy(
            min_cluster_size=cfg.min_hits,
            min_samples=1,
            allow_single_cluster=True,
        ),
        thresholds=cfg,
    )
    assert len(out) == 1
    assert out[0].dominant_cluster_id == "c-a"
