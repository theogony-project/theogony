"""
Named anomaly rules for IngestRunReport (Plan §2.11.2).

Four named rules, each implemented as a tiny pure function. The
``detect_ingest_anomalies`` umbrella function calls them in fixed
order and returns a list of human-readable strings — exactly what
``RunReportBase.anomalies`` expects.

Plan §2.11.4: "No anomaly detection beyond the simple rules above."
This module is the *only* place anomalies are detected; cross-run
distribution comparison is the future Reviewer agent's job
(PHX-0035), not ours.
"""

from __future__ import annotations

import math

from theogony.config.settings import AnomalyThresholds, IngestStageBaselines

# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------


def stage_slow_anomalies(
    stage_durations_s: dict[str, float],
    baselines: IngestStageBaselines,
    multiplier: float,
) -> list[str]:
    """Rule 1: a stage took > ``multiplier`` × its baseline duration.

    Returns one string per offending stage in the format
    ``"stage_slow:<stage_name>=<ratio>x baseline"`` (e.g.
    ``"stage_slow:relations_extracted=4.2x baseline"``) so the
    string in the verdict reasoning matches Plan §2.11.2's example
    verbatim.
    """
    baseline_map = baselines.model_dump()
    out: list[str] = []
    for stage_name, observed in stage_durations_s.items():
        baseline = baseline_map.get(stage_name)
        if baseline is None or baseline <= 0:
            continue
        ratio = observed / baseline
        if ratio > multiplier:
            out.append(f"stage_slow:{stage_name}={ratio:.1f}x baseline")
    return out


def cost_spike_anomaly(
    current_cost_eur: float,
    prior_costs_eur: list[float],
    multiplier: float,
    min_history: int,
) -> str | None:
    """Rule 2: total LLM cost > ``multiplier`` × rolling-median of prior runs.

    Skips the check when fewer than ``min_history`` prior runs exist
    — exactly the Plan §2.11.2 caveat ("in Gen 1 with the demo book
    this rarely fires"). Returns the anomaly string or None.
    """
    if len(prior_costs_eur) < min_history:
        return None
    sorted_priors = sorted(prior_costs_eur)
    n = len(sorted_priors)
    if n % 2 == 0:
        median = (sorted_priors[n // 2 - 1] + sorted_priors[n // 2]) / 2
    else:
        median = sorted_priors[n // 2]
    if median <= 0:
        return None
    if current_cost_eur > multiplier * median:
        return (
            f"cost_spike:current={current_cost_eur:.2f} EUR "
            f"({current_cost_eur / median:.1f}x rolling median {median:.2f})"
        )
    return None


def wikidata_failure_burst_anomaly(
    failures: int,
    total_requests: int,
    rate_threshold: float,
) -> str | None:
    """Rule 3: > ``rate_threshold`` of wbsearchentities calls failed after retry.

    Returns None when no requests were made (no signal to evaluate).
    """
    if total_requests == 0:
        return None
    rate = failures / total_requests
    if rate > rate_threshold:
        return (
            f"wikidata_failure_burst:rate={rate:.2%} "
            f"(>{rate_threshold:.2%} threshold; {failures}/{total_requests})"
        )
    return None


def embedding_skew_anomaly(
    batch_latencies_ms: list[float],
    stddev_multiplier: float,
) -> str | None:
    """Rule 4: stddev of embedding-batch latency > multiplier × mean.

    Signals a runaway batch — most batches behaving normally but at
    least one egregiously slow. Returns None when there are fewer
    than 2 batches (need >=2 to compute stddev), or when the mean
    is zero (degenerate input).
    """
    if len(batch_latencies_ms) < 2:
        return None
    mean = sum(batch_latencies_ms) / len(batch_latencies_ms)
    if mean <= 0:
        return None
    variance = sum((x - mean) ** 2 for x in batch_latencies_ms) / len(batch_latencies_ms)
    stddev = math.sqrt(variance)
    if stddev > stddev_multiplier * mean:
        return f"embedding_skew:stddev={stddev:.0f}ms (>{stddev_multiplier:.1f}x mean {mean:.0f}ms)"
    return None


# ---------------------------------------------------------------------------
# Umbrella
# ---------------------------------------------------------------------------


def detect_ingest_anomalies(
    *,
    stage_durations_s: dict[str, float],
    current_cost_eur: float,
    prior_costs_eur: list[float],
    wikidata_failures: int,
    wikidata_total_requests: int,
    embedding_batch_latencies_ms: list[float],
    anomaly: AnomalyThresholds,
    baselines: IngestStageBaselines,
) -> list[str]:
    """Run all four rules in fixed order and collect the anomaly strings.

    Order is documented for stability — a Reviewer agent doing string
    comparison across reports relies on it. Stage-slow is first
    because there can be multiple; the other three return at most one
    each.
    """
    anomalies: list[str] = []
    anomalies.extend(
        stage_slow_anomalies(
            stage_durations_s,
            baselines=baselines,
            multiplier=anomaly.stage_slow_multiplier,
        )
    )
    cost = cost_spike_anomaly(
        current_cost_eur,
        prior_costs_eur,
        multiplier=anomaly.cost_spike_multiplier,
        min_history=anomaly.cost_spike_min_history,
    )
    if cost is not None:
        anomalies.append(cost)
    wd = wikidata_failure_burst_anomaly(
        wikidata_failures,
        wikidata_total_requests,
        rate_threshold=anomaly.wikidata_failure_rate,
    )
    if wd is not None:
        anomalies.append(wd)
    emb = embedding_skew_anomaly(
        embedding_batch_latencies_ms,
        stddev_multiplier=anomaly.embedding_skew_stddev_multiplier,
    )
    if emb is not None:
        anomalies.append(emb)
    return anomalies
