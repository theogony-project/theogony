"""Tests for the self-verdict heuristics."""

from __future__ import annotations

import pytest

from theogony.config.settings import (
    IngestVerdictThresholds,
    OneirosVerdictThresholds,
    QueryVerdictThresholds,
)
from theogony.reporting.verdict import (
    ingest_verdict,
    oneiros_verdict,
    query_verdict,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ingest_thresholds() -> IngestVerdictThresholds:
    return IngestVerdictThresholds()  # plan defaults


@pytest.fixture
def query_thresholds() -> QueryVerdictThresholds:
    return QueryVerdictThresholds()


@pytest.fixture
def oneiros_thresholds() -> OneirosVerdictThresholds:
    return OneirosVerdictThresholds()


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class TestIngestVerdict:
    def test_failed_when_status_not_completed(
        self, ingest_thresholds: IngestVerdictThresholds
    ) -> None:
        verdict, reason = ingest_verdict(
            status="aborted",
            parse_error_rate=0.0,
            low_tier_ratio=0.0,
            anomalies=[],
            thresholds=ingest_thresholds,
        )
        assert verdict == "failed"
        assert "aborted" in reason

    def test_good_when_all_clear(self, ingest_thresholds: IngestVerdictThresholds) -> None:
        verdict, reason = ingest_verdict(
            status="completed",
            parse_error_rate=0.02,
            low_tier_ratio=0.10,
            anomalies=[],
            thresholds=ingest_thresholds,
        )
        assert verdict == "good"
        assert reason == "all clear"

    def test_poor_when_parse_error_above_poor_threshold(
        self, ingest_thresholds: IngestVerdictThresholds
    ) -> None:
        verdict, reason = ingest_verdict(
            status="completed",
            parse_error_rate=0.25,  # > 0.20
            low_tier_ratio=0.0,
            anomalies=[],
            thresholds=ingest_thresholds,
        )
        assert verdict == "poor"
        assert "parse_error_rate=0.25" in reason
        assert "poor-threshold" in reason

    def test_poor_when_low_tier_ratio_high(
        self, ingest_thresholds: IngestVerdictThresholds
    ) -> None:
        verdict, _ = ingest_verdict(
            status="completed",
            parse_error_rate=0.0,
            low_tier_ratio=0.70,  # > 0.60
            anomalies=[],
            thresholds=ingest_thresholds,
        )
        assert verdict == "poor"

    def test_poor_when_three_or_more_anomalies(
        self, ingest_thresholds: IngestVerdictThresholds
    ) -> None:
        verdict, reason = ingest_verdict(
            status="completed",
            parse_error_rate=0.0,
            low_tier_ratio=0.0,
            anomalies=["a", "b", "c"],
            thresholds=ingest_thresholds,
        )
        assert verdict == "poor"
        assert "3 anomalies" in reason

    def test_partial_when_parse_error_in_partial_band(
        self, ingest_thresholds: IngestVerdictThresholds
    ) -> None:
        verdict, reason = ingest_verdict(
            status="completed",
            parse_error_rate=0.10,  # > 0.05, <= 0.20
            low_tier_ratio=0.0,
            anomalies=[],
            thresholds=ingest_thresholds,
        )
        assert verdict == "partial"
        assert "partial-threshold" in reason

    def test_partial_when_low_tier_in_partial_band(
        self, ingest_thresholds: IngestVerdictThresholds
    ) -> None:
        verdict, _ = ingest_verdict(
            status="completed",
            parse_error_rate=0.0,
            low_tier_ratio=0.41,  # > 0.30, <= 0.60
            anomalies=[],
            thresholds=ingest_thresholds,
        )
        assert verdict == "partial"

    def test_partial_when_one_anomaly(self, ingest_thresholds: IngestVerdictThresholds) -> None:
        verdict, reason = ingest_verdict(
            status="completed",
            parse_error_rate=0.0,
            low_tier_ratio=0.0,
            anomalies=["stage_slow:relations_extracted"],
            thresholds=ingest_thresholds,
        )
        assert verdict == "partial"
        assert "1 anomaly" in reason

    def test_poor_overrides_partial_when_both_apply(
        self, ingest_thresholds: IngestVerdictThresholds
    ) -> None:
        # parse_error_rate above poor; low_tier in partial band
        verdict, _ = ingest_verdict(
            status="completed",
            parse_error_rate=0.30,
            low_tier_ratio=0.40,
            anomalies=[],
            thresholds=ingest_thresholds,
        )
        assert verdict == "poor"

    def test_thresholds_override_works(self) -> None:
        # tighten poor threshold to 0.10 — now 0.15 should be poor
        thresholds = IngestVerdictThresholds(poor_parse_error_rate=0.10)
        verdict, _ = ingest_verdict(
            status="completed",
            parse_error_rate=0.15,
            low_tier_ratio=0.0,
            anomalies=[],
            thresholds=thresholds,
        )
        assert verdict == "poor"


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQueryVerdict:
    def test_failed_when_raised(self, query_thresholds: QueryVerdictThresholds) -> None:
        verdict, reason = query_verdict(
            raised=True,
            cited_node_count=0,
            citations_with_high_confidence_source=0,
            synthesis_latency_ms=100,
            gaps_identified=0,
            thresholds=query_thresholds,
        )
        assert verdict == "failed"
        assert "empty" in reason

    def test_good_when_clean(self, query_thresholds: QueryVerdictThresholds) -> None:
        verdict, _ = query_verdict(
            raised=False,
            cited_node_count=4,
            citations_with_high_confidence_source=4,
            synthesis_latency_ms=2_000,
            gaps_identified=0,
            thresholds=query_thresholds,
        )
        assert verdict == "good"

    def test_poor_when_all_aka_only(self, query_thresholds: QueryVerdictThresholds) -> None:
        verdict, reason = query_verdict(
            raised=False,
            cited_node_count=5,
            citations_with_high_confidence_source=0,
            synthesis_latency_ms=2_000,
            gaps_identified=0,
            thresholds=query_thresholds,
        )
        assert verdict == "poor"
        assert "AKA-only" in reason

    def test_poor_when_latency_high(self, query_thresholds: QueryVerdictThresholds) -> None:
        verdict, reason = query_verdict(
            raised=False,
            cited_node_count=4,
            citations_with_high_confidence_source=4,
            synthesis_latency_ms=11_000,
            gaps_identified=0,
            thresholds=query_thresholds,
        )
        assert verdict == "poor"
        assert "11000" in reason

    def test_partial_when_low_high_conf_ratio(
        self, query_thresholds: QueryVerdictThresholds
    ) -> None:
        verdict, reason = query_verdict(
            raised=False,
            cited_node_count=10,
            citations_with_high_confidence_source=3,  # 0.30 < 0.5 good
            synthesis_latency_ms=1_000,
            gaps_identified=0,
            thresholds=query_thresholds,
        )
        assert verdict == "partial"
        assert "high_conf_ratio" in reason

    def test_partial_when_latency_in_band(self, query_thresholds: QueryVerdictThresholds) -> None:
        verdict, _ = query_verdict(
            raised=False,
            cited_node_count=4,
            citations_with_high_confidence_source=4,
            synthesis_latency_ms=7_000,  # 5_000 < x <= 10_000
            gaps_identified=0,
            thresholds=query_thresholds,
        )
        assert verdict == "partial"

    def test_partial_when_many_gaps(self, query_thresholds: QueryVerdictThresholds) -> None:
        verdict, reason = query_verdict(
            raised=False,
            cited_node_count=4,
            citations_with_high_confidence_source=4,
            synthesis_latency_ms=1_000,
            gaps_identified=3,  # >= 3
            thresholds=query_thresholds,
        )
        assert verdict == "partial"
        assert "gaps_identified=3" in reason

    def test_no_citations_does_not_trigger_poor(
        self, query_thresholds: QueryVerdictThresholds
    ) -> None:
        # Plan: poor when cited_node_count > 0 AND high-conf == 0.
        # cited_node_count == 0 ⇒ vacuously OK on this axis.
        verdict, _ = query_verdict(
            raised=False,
            cited_node_count=0,
            citations_with_high_confidence_source=0,
            synthesis_latency_ms=100,
            gaps_identified=0,
            thresholds=query_thresholds,
        )
        assert verdict == "good"


# ---------------------------------------------------------------------------
# Oneiros
# ---------------------------------------------------------------------------


class TestOneirosVerdict:
    def test_failed_when_raised(self, oneiros_thresholds: OneirosVerdictThresholds) -> None:
        verdict, _ = oneiros_verdict(
            raised=True,
            nodes_evaluated=10,
            nodes_promoted=0,
            nodes_degraded=0,
            median_vitality_shift=0.0,
            thresholds=oneiros_thresholds,
        )
        assert verdict == "failed"

    def test_good_when_active_and_stable(
        self, oneiros_thresholds: OneirosVerdictThresholds
    ) -> None:
        verdict, _ = oneiros_verdict(
            raised=False,
            nodes_evaluated=100,
            nodes_promoted=2,
            nodes_degraded=0,
            median_vitality_shift=0.01,
            thresholds=oneiros_thresholds,
        )
        assert verdict == "good"

    def test_poor_when_starving(self, oneiros_thresholds: OneirosVerdictThresholds) -> None:
        verdict, reason = oneiros_verdict(
            raised=False,
            nodes_evaluated=0,
            nodes_promoted=0,
            nodes_degraded=0,
            median_vitality_shift=0.0,
            thresholds=oneiros_thresholds,
        )
        assert verdict == "poor"
        assert "starving" in reason

    def test_poor_when_vitality_drops(self, oneiros_thresholds: OneirosVerdictThresholds) -> None:
        verdict, reason = oneiros_verdict(
            raised=False,
            nodes_evaluated=100,
            nodes_promoted=0,
            nodes_degraded=10,
            median_vitality_shift=-0.10,
            thresholds=oneiros_thresholds,
        )
        assert verdict == "poor"
        assert "wrong way" in reason

    def test_partial_when_no_promotions_or_degradations(
        self, oneiros_thresholds: OneirosVerdictThresholds
    ) -> None:
        verdict, reason = oneiros_verdict(
            raised=False,
            nodes_evaluated=100,
            nodes_promoted=0,
            nodes_degraded=0,
            median_vitality_shift=0.0,
            thresholds=oneiros_thresholds,
        )
        assert verdict == "partial"
        assert "threshold drift" in reason
