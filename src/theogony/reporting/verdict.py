"""
Self-verdict heuristics for the three RunReport kinds (Plan §2.11.2).

Each ``*_verdict`` function takes the report-specific facts plus a
threshold settings object and returns ``(verdict, reasoning)`` — the
two fields the pipeline writes onto the report header before the
RunReportWriter saves it.

Pure functions, no I/O, no Pydantic mutation. The pipeline calls
them from its ``_finalize_report()`` hook with the values it already
has, and the result is recorded on the report.

Thresholds are NEVER hardcoded here — they come from
``Settings.report.thresholds.*`` per Plan §2.11.2 so the future
Reviewer agent can re-tune from observed data without code changes.
"""

from __future__ import annotations

from typing import Literal

from theogony.config.settings import (
    IngestVerdictThresholds,
    OneirosVerdictThresholds,
    QueryVerdictThresholds,
)

Verdict = Literal["good", "partial", "poor", "failed"]
RunStatus = Literal["completed", "partial", "failed", "aborted"]

# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def ingest_verdict(
    *,
    status: RunStatus,
    parse_error_rate: float,
    low_tier_ratio: float,
    anomalies: list[str],
    thresholds: IngestVerdictThresholds,
) -> tuple[Verdict, str]:
    """Compute ``(verdict, reasoning)`` for an IngestRunReport (Plan §2.11.2).

    Order of evaluation matches the plan's table verbatim:

        failed   if status != "completed"
        poor     if parse_error_rate > poor.parse_error_rate
                 OR low_tier_ratio  > poor.low_tier_ratio
                 OR len(anomalies)  >= poor.anomaly_count
        partial  if partial.parse_error_rate < parse_error_rate <= poor.parse_error_rate
                 OR partial.low_tier_ratio  < low_tier_ratio  <= poor.low_tier_ratio
                 OR 0 < len(anomalies) < poor.anomaly_count
        good     otherwise

    The ``reasoning`` is a one-line concatenation of the rules that
    fired, formatted exactly the way Plan §2.11.2 example shows so a
    Reviewer agent can grep for ``low_tier_ratio=`` etc.
    """
    if status != "completed":
        return "failed", f"status={status}"

    poor_reasons: list[str] = []
    if parse_error_rate > thresholds.poor_parse_error_rate:
        poor_reasons.append(
            f"parse_error_rate={parse_error_rate:.2f} "
            f"(>{thresholds.poor_parse_error_rate:.2f} poor-threshold)"
        )
    if low_tier_ratio > thresholds.poor_low_tier_ratio:
        poor_reasons.append(
            f"low_tier_ratio={low_tier_ratio:.2f} "
            f"(>{thresholds.poor_low_tier_ratio:.2f} poor-threshold)"
        )
    if len(anomalies) >= thresholds.poor_anomaly_count:
        poor_reasons.append(f"{len(anomalies)} anomalies: {', '.join(anomalies)}")
    if poor_reasons:
        return "poor", "; ".join(poor_reasons)

    partial_reasons: list[str] = []
    if thresholds.partial_parse_error_rate < parse_error_rate <= thresholds.poor_parse_error_rate:
        partial_reasons.append(
            f"parse_error_rate={parse_error_rate:.2f} "
            f"(>{thresholds.partial_parse_error_rate:.2f} partial-threshold)"
        )
    if thresholds.partial_low_tier_ratio < low_tier_ratio <= thresholds.poor_low_tier_ratio:
        partial_reasons.append(
            f"low_tier_ratio={low_tier_ratio:.2f} "
            f"(>{thresholds.partial_low_tier_ratio:.2f} partial-threshold)"
        )
    if 0 < len(anomalies) < thresholds.poor_anomaly_count:
        partial_reasons.append(f"{len(anomalies)} anomaly: {', '.join(anomalies)}")
    if partial_reasons:
        return "partial", "; ".join(partial_reasons)

    return "good", "all clear"


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def query_verdict(
    *,
    raised: bool,
    cited_node_count: int,
    citations_with_high_confidence_source: int,
    synthesis_latency_ms: int,
    gaps_identified: int,
    thresholds: QueryVerdictThresholds,
) -> tuple[Verdict, str]:
    """Compute ``(verdict, reasoning)`` for a QueryRunReport (Plan §2.11.2).

    ``raised=True`` ↔ synthesis produced no usable answer text (including
    LLM transport failures swallowed into an empty answer).

    Order of evaluation per the plan table:

        failed   if raised
        poor     if (cited_node_count > 0 AND high_conf_citations == 0)
                 OR synthesis_latency_ms > poor.latency_ms
        partial  if 0 < high_conf_ratio < good_high_conf_ratio
                 OR partial.latency_ms < latency_ms <= poor.latency_ms
                 OR gaps_identified >= partial_gaps_count
        good     otherwise
    """
    if raised:
        return "failed", "synthesis returned empty answer"

    poor_reasons: list[str] = []
    if cited_node_count > 0 and citations_with_high_confidence_source == 0:
        poor_reasons.append(
            f"all {cited_node_count} citations are AKA-only (no high-confidence source)"
        )
    if synthesis_latency_ms > thresholds.poor_latency_ms:
        poor_reasons.append(
            f"synthesis_latency_ms={synthesis_latency_ms} "
            f"(>{thresholds.poor_latency_ms} poor-threshold)"
        )
    if poor_reasons:
        return "poor", "; ".join(poor_reasons)

    high_conf_ratio = (
        citations_with_high_confidence_source / cited_node_count
        if cited_node_count > 0
        else 1.0  # no citations to evaluate ⇒ vacuously OK on this axis
    )
    partial_reasons: list[str] = []
    if cited_node_count > 0 and high_conf_ratio < thresholds.good_high_conf_ratio:
        partial_reasons.append(
            f"high_conf_ratio={high_conf_ratio:.2f} "
            f"(<{thresholds.good_high_conf_ratio:.2f} good-threshold)"
        )
    if thresholds.partial_latency_ms < synthesis_latency_ms <= thresholds.poor_latency_ms:
        partial_reasons.append(
            f"synthesis_latency_ms={synthesis_latency_ms} "
            f"(>{thresholds.partial_latency_ms} partial-threshold)"
        )
    if gaps_identified >= thresholds.partial_gaps_count:
        partial_reasons.append(
            f"gaps_identified={gaps_identified} "
            f"(>={thresholds.partial_gaps_count} partial-threshold)"
        )
    if partial_reasons:
        return "partial", "; ".join(partial_reasons)

    return "good", "all clear"


# ---------------------------------------------------------------------------
# Oneiros
# ---------------------------------------------------------------------------


def oneiros_verdict(
    *,
    raised: bool,
    nodes_evaluated: int,
    nodes_promoted: int,
    nodes_degraded: int,
    median_vitality_shift: float,
    thresholds: OneirosVerdictThresholds,
) -> tuple[Verdict, str]:
    """Compute ``(verdict, reasoning)`` for an OneirosTickReport (Plan §2.11.2).

    Order:

        failed   if raised
        poor     if nodes_evaluated == 0 (worker is starving)
                 OR median_vitality_shift < poor_median_vitality_shift
                    (system is losing trust on average)
        partial  if nodes_promoted == 0 AND nodes_degraded == 0
                    (worker did work but moved nothing — threshold drift?)
        good     otherwise
    """
    if raised:
        return "failed", "tick raised before completion"

    poor_reasons: list[str] = []
    if nodes_evaluated == 0:
        poor_reasons.append("nodes_evaluated=0 (worker is starving)")
    if median_vitality_shift < thresholds.poor_median_vitality_shift:
        poor_reasons.append(
            f"median_vitality_shift={median_vitality_shift:+.3f} "
            f"(<{thresholds.poor_median_vitality_shift:+.3f} poor-threshold; "
            f"consolidation moving the wrong way)"
        )
    if poor_reasons:
        return "poor", "; ".join(poor_reasons)

    if nodes_promoted == 0 and nodes_degraded == 0:
        return "partial", "no promotions or degradations (possible threshold drift)"

    return "good", "all clear"
