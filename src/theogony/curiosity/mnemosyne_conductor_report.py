"""Mnemosyne conductor run report (Living Demo W17)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.reporting.models import RunReportBase


class ImmuneMetricSnapshot(BaseModel):
    """Point-in-time immune-system metrics consumed by the conductor."""

    model_config = ConfigDict(extra="forbid")

    pool_total: int = 0
    pool_unobserved: int = 0
    pool_sampled_by_athene: int = 0
    pool_cleared: int = 0
    pool_findings_total: int = 0

    finding_count_by_cell: dict[str, int] = Field(default_factory=dict)
    finding_count_by_type: dict[str, int] = Field(default_factory=dict)
    finding_count_by_severity: dict[str, int] = Field(default_factory=dict)
    unresolved_finding_count: int = 0

    latest_chronos_findings_seen: int = 0
    latest_chronos_findings_resolved: int = 0
    latest_chronos_negative_edges_written: int = 0
    latest_chronos_nodes_demoted: int = 0
    latest_chronos_pool_entries_cleared: int = 0

    latest_nemesis_findings_written: int = 0
    latest_eris_probes_run: int = 0
    latest_eris_failed: int = 0

    query_reports_scanned: int = 0
    query_verdict_counts: dict[str, int] = Field(default_factory=dict)
    ingest_reports_scanned: int = 0
    ingest_verdict_counts: dict[str, int] = Field(default_factory=dict)


class MetricDefinition(BaseModel):
    """One success metric for the immune system."""

    model_config = ConfigDict(extra="forbid")

    metric_id: str
    name: str
    rationale: str
    numerator: str
    denominator: str
    desired_direction: Literal["increase", "decrease", "stabilize"]
    current_value: float | None = None
    target_value: float | None = None
    source: Literal["llm", "fixture"]


class ExperimentProposal(BaseModel):
    """Dry-run experiment proposal (not auto-applied in W17)."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    metric_id: str
    hypothesis: str
    regime_a: dict[str, str]
    regime_b: dict[str, str]
    expected_effect: str
    risk: Literal["low", "medium", "high"]
    auto_apply_allowed: bool = False


class BacklogProposalDraft(BaseModel):
    """Draft Phoenix-style ticket written under run_reports only."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    title: str
    rationale: str
    suggested_category: Literal["bug", "test", "refactor", "feature", "vision", "ops"]
    source_metric_ids: list[str] = Field(default_factory=list)
    source_report_ids: list[str] = Field(default_factory=list)
    proposed_acceptance_criteria: list[str] = Field(default_factory=list)


class MnemosyneExperimentNodePayload(BaseModel):
    """Summary payload mirrored on experiment nodes (W17)."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    metric_id: str
    hypothesis: str


class MnemosyneConductorSummary(BaseModel):
    """Outcome accumulator for one conductor pass."""

    model_config = ConfigDict(extra="forbid")

    metrics_defined: int = 0
    experiment_nodes_written: int = 0
    backlog_drafts_written: int = 0
    skipped_reason: str | None = None
    llm_cost_eur: float = 0.0
    fixture_fallback_used: bool = False
    metric_definitions: list[MetricDefinition] = Field(default_factory=list)
    experiment_proposals: list[ExperimentProposal] = Field(default_factory=list)
    backlog_drafts: list[BacklogProposalDraft] = Field(default_factory=list)


class MnemosyneConductorReport(RunReportBase):
    """Persisted audit of one Mnemosyne conductor pass."""

    report_type: Literal["mnemosyne_conductor"] = "mnemosyne_conductor"
    snapshot: ImmuneMetricSnapshot
    metrics_defined: int = Field(ge=0)
    experiment_nodes_written: int = Field(ge=0)
    backlog_drafts_written: int = Field(ge=0)
    llm_cost_eur: float = Field(default=0.0, ge=0.0)
    metric_definitions: list[MetricDefinition] = Field(default_factory=list)
    experiment_proposals: list[ExperimentProposal] = Field(default_factory=list)
    backlog_drafts: list[BacklogProposalDraft] = Field(default_factory=list)


def _snapshot_nonempty(snap: ImmuneMetricSnapshot) -> bool:
    if snap.pool_total > 0:
        return True
    if sum(snap.finding_count_by_cell.values()) > 0:
        return True
    if snap.query_reports_scanned > 0 or snap.ingest_reports_scanned > 0:
        return True
    if snap.latest_chronos_findings_seen > 0 or snap.latest_nemesis_findings_written > 0:
        return True
    return snap.latest_eris_probes_run > 0


def build_mnemosyne_conductor_report(
    summary: MnemosyneConductorSummary,
    *,
    snapshot: ImmuneMetricSnapshot,
    started_at: datetime,
    finished_at: datetime,
) -> MnemosyneConductorReport:
    """Map conductor summary + snapshot into a persisted :class:`MnemosyneConductorReport`."""
    duration_s = max((finished_at - started_at).total_seconds(), 0.0)
    recommendations: list[str] = []
    if summary.skipped_reason:
        verdict: Literal["good", "partial", "poor", "failed"] = "good"
        reasoning = summary.skipped_reason
    elif summary.fixture_fallback_used:
        verdict = "partial"
        reasoning = "LLM metric definition unavailable; used fixture fallback"
        recommendations.append("Consider fixing LLM connectivity or schema validation for metrics.")
    elif summary.metrics_defined == 0 and _snapshot_nonempty(snapshot):
        verdict = "poor"
        reasoning = "no metrics defined despite non-empty immune snapshot"
    else:
        verdict = "good"
        reasoning = "mnemosyne conductor pass completed"

    return MnemosyneConductorReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        status="completed",
        verdict=verdict,
        verdict_reasoning=reasoning,
        recommendations=recommendations,
        snapshot=snapshot,
        metrics_defined=summary.metrics_defined,
        experiment_nodes_written=summary.experiment_nodes_written,
        backlog_drafts_written=summary.backlog_drafts_written,
        llm_cost_eur=summary.llm_cost_eur,
        metric_definitions=list(summary.metric_definitions),
        experiment_proposals=list(summary.experiment_proposals),
        backlog_drafts=list(summary.backlog_drafts),
    )


__all__ = [
    "BacklogProposalDraft",
    "ExperimentProposal",
    "ImmuneMetricSnapshot",
    "MetricDefinition",
    "MnemosyneConductorReport",
    "MnemosyneConductorSummary",
    "MnemosyneExperimentNodePayload",
    "build_mnemosyne_conductor_report",
]
