"""Tests for the four named anomaly rules (Plan §2.11.2)."""

from __future__ import annotations

import pytest

from theogony.config.settings import AnomalyThresholds, IngestStageBaselines
from theogony.reporting.anomaly import (
    cost_spike_anomaly,
    detect_ingest_anomalies,
    embedding_skew_anomaly,
    stage_slow_anomalies,
    wikidata_failure_burst_anomaly,
)

# ---------------------------------------------------------------------------
# Stage slow
# ---------------------------------------------------------------------------


class TestStageSlow:
    def test_no_anomalies_when_within_baseline(self) -> None:
        b = IngestStageBaselines()
        # All stages at exactly 50% of baseline → no anomaly
        observed = {"acquired": 1.0, "relations_extracted": 90.0}
        assert stage_slow_anomalies(observed, b, multiplier=2.0) == []

    def test_anomaly_when_above_threshold(self) -> None:
        b = IngestStageBaselines(relations_extracted=100.0)
        observed = {"relations_extracted": 250.0}  # 2.5x
        result = stage_slow_anomalies(observed, b, multiplier=2.0)
        assert len(result) == 1
        assert "stage_slow:relations_extracted=2.5x" in result[0]

    def test_multiple_offenders_listed(self) -> None:
        b = IngestStageBaselines(acquired=2.0, relations_extracted=100.0)
        observed = {"acquired": 10.0, "relations_extracted": 500.0}
        result = stage_slow_anomalies(observed, b, multiplier=2.0)
        assert len(result) == 2

    def test_unknown_stage_silently_ignored(self) -> None:
        b = IngestStageBaselines()
        # "weird_stage" not in baselines model — must not raise
        result = stage_slow_anomalies({"weird_stage": 99999.0}, b, multiplier=2.0)
        assert result == []

    def test_format_matches_plan_example(self) -> None:
        b = IngestStageBaselines(relations_extracted=100.0)
        observed = {"relations_extracted": 420.0}  # 4.2x
        result = stage_slow_anomalies(observed, b, multiplier=2.0)
        # Plan §2.11.2 example: "stage_slow:relations_extracted=4.2x baseline"
        assert result == ["stage_slow:relations_extracted=4.2x baseline"]


# ---------------------------------------------------------------------------
# Cost spike
# ---------------------------------------------------------------------------


class TestCostSpike:
    def test_skipped_when_too_few_priors(self) -> None:
        result = cost_spike_anomaly(
            current_cost_eur=10.0,
            prior_costs_eur=[0.1, 0.1, 0.1],
            multiplier=1.5,
            min_history=5,
        )
        assert result is None

    def test_no_anomaly_when_close_to_median(self) -> None:
        result = cost_spike_anomaly(
            current_cost_eur=0.13,
            prior_costs_eur=[0.10, 0.11, 0.12, 0.13, 0.14],
            multiplier=1.5,
            min_history=5,
        )
        assert result is None

    def test_anomaly_when_above_multiplier(self) -> None:
        # median(0.10, 0.11, 0.12, 0.13, 0.14) = 0.12; 1.5x = 0.18
        result = cost_spike_anomaly(
            current_cost_eur=0.50,
            prior_costs_eur=[0.10, 0.11, 0.12, 0.13, 0.14],
            multiplier=1.5,
            min_history=5,
        )
        assert result is not None
        assert "cost_spike" in result
        assert "0.50" in result

    def test_zero_median_returns_none(self) -> None:
        result = cost_spike_anomaly(
            current_cost_eur=1.0,
            prior_costs_eur=[0.0, 0.0, 0.0, 0.0, 0.0],
            multiplier=1.5,
            min_history=5,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Wikidata failure burst
# ---------------------------------------------------------------------------


class TestWikidataFailureBurst:
    def test_no_requests_no_signal(self) -> None:
        assert wikidata_failure_burst_anomaly(0, 0, rate_threshold=0.10) is None

    def test_no_anomaly_below_threshold(self) -> None:
        assert wikidata_failure_burst_anomaly(5, 100, rate_threshold=0.10) is None

    def test_anomaly_above_threshold(self) -> None:
        result = wikidata_failure_burst_anomaly(15, 100, rate_threshold=0.10)
        assert result is not None
        assert "wikidata_failure_burst" in result
        assert "15.00%" in result

    def test_anomaly_at_exact_threshold_does_not_fire(self) -> None:
        # Plan: ">10%" is the threshold; 10% itself is OK.
        assert wikidata_failure_burst_anomaly(10, 100, rate_threshold=0.10) is None


# ---------------------------------------------------------------------------
# Embedding skew
# ---------------------------------------------------------------------------


class TestEmbeddingSkew:
    def test_too_few_batches_returns_none(self) -> None:
        assert embedding_skew_anomaly([100.0], stddev_multiplier=3.0) is None
        assert embedding_skew_anomaly([], stddev_multiplier=3.0) is None

    def test_zero_mean_returns_none(self) -> None:
        assert embedding_skew_anomaly([0.0, 0.0], stddev_multiplier=3.0) is None

    def test_uniform_batches_no_anomaly(self) -> None:
        latencies = [100.0] * 10
        assert embedding_skew_anomaly(latencies, stddev_multiplier=3.0) is None

    def test_anomaly_with_runaway_batch(self) -> None:
        # The rule is "stddev > 3 × mean", which is mathematically tight:
        # one huge outlier among n small values needs n/sqrt(n+1) > 3 to
        # fire. n=15 small + 1 huge clears that.
        latencies = [50.0] * 15 + [100_000.0]
        result = embedding_skew_anomaly(latencies, stddev_multiplier=3.0)
        assert result is not None
        assert "embedding_skew" in result

    def test_no_anomaly_with_mild_outlier(self) -> None:
        # Two batches at 100ms each — uniform — no skew.
        # Compare to one ~10x outlier at the threshold of detection;
        # for n=9 small + 1 large the ratio is too low to fire.
        latencies = [50.0] * 9 + [10_000.0]
        assert embedding_skew_anomaly(latencies, stddev_multiplier=3.0) is None


# ---------------------------------------------------------------------------
# Umbrella
# ---------------------------------------------------------------------------


class TestDetectIngestAnomalies:
    @pytest.fixture
    def thresholds(self) -> AnomalyThresholds:
        return AnomalyThresholds()

    @pytest.fixture
    def baselines(self) -> IngestStageBaselines:
        return IngestStageBaselines()

    def test_no_anomalies_when_clean(
        self,
        thresholds: AnomalyThresholds,
        baselines: IngestStageBaselines,
    ) -> None:
        result = detect_ingest_anomalies(
            stage_durations_s={"acquired": 1.0},
            current_cost_eur=0.12,
            prior_costs_eur=[0.10] * 5,
            wikidata_failures=0,
            wikidata_total_requests=100,
            embedding_batch_latencies_ms=[100.0] * 10,
            anomaly=thresholds,
            baselines=baselines,
        )
        assert result == []

    def test_all_four_can_fire_at_once(
        self,
        thresholds: AnomalyThresholds,
        baselines: IngestStageBaselines,
    ) -> None:
        result = detect_ingest_anomalies(
            stage_durations_s={"relations_extracted": 600.0},  # > 2x 180
            current_cost_eur=10.0,  # >> 1.5x median 0.10
            prior_costs_eur=[0.10] * 5,
            wikidata_failures=20,
            wikidata_total_requests=100,  # 20% > 10%
            embedding_batch_latencies_ms=[50.0] * 15 + [100_000.0],
            anomaly=thresholds,
            baselines=baselines,
        )
        assert len(result) == 4
        assert any("stage_slow" in s for s in result)
        assert any("cost_spike" in s for s in result)
        assert any("wikidata_failure_burst" in s for s in result)
        assert any("embedding_skew" in s for s in result)

    def test_order_is_stable(
        self,
        thresholds: AnomalyThresholds,
        baselines: IngestStageBaselines,
    ) -> None:
        # Order documented in module docstring: stage_slow* (multiple),
        # then cost_spike, then wikidata, then embedding.
        result = detect_ingest_anomalies(
            stage_durations_s={"acquired": 5.0, "relations_extracted": 600.0},
            current_cost_eur=10.0,
            prior_costs_eur=[0.10] * 5,
            wikidata_failures=20,
            wikidata_total_requests=100,
            embedding_batch_latencies_ms=[50.0] * 15 + [100_000.0],
            anomaly=thresholds,
            baselines=baselines,
        )
        cost_idx = next(i for i, s in enumerate(result) if "cost_spike" in s)
        wd_idx = next(i for i, s in enumerate(result) if "wikidata_failure" in s)
        emb_idx = next(i for i, s in enumerate(result) if "embedding_skew" in s)
        assert cost_idx < wd_idx < emb_idx
