"""Chronos run report schema (Living Demo W15)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.reporting.models import RunReportBase


class ChronosAction(BaseModel):
    """One Chronos decision for a pool entry / finding pair."""

    model_config = ConfigDict(extra="forbid")

    pool_entry_id: str
    finding_id: str
    finding_type: str
    severity: str
    action: Literal[
        "cleared_no_issue",
        "annotated",
        "demoted",
        "negative_edge_written",
        "skipped_missing_finding",
    ]
    target_node_ids: list[str] = Field(default_factory=list)
    edges_written: int = Field(default=0, ge=0)
    nodes_demoted: int = Field(default=0, ge=0)
    reason: str = ""


class ChronosRunSummary(BaseModel):
    """Outcome of a single :meth:`~theogony.agents.chronos.ChronosRecycler.run_once` pass."""

    model_config = ConfigDict(extra="forbid")

    processed_entries: int = 0
    findings_seen: int = 0
    findings_resolved: int = 0
    negative_edges_written: int = 0
    nodes_demoted: int = 0
    pool_entries_cleared: int = 0
    skipped_reason: str | None = None
    actions: list[ChronosAction] = Field(default_factory=list)
    missing_findings: int = 0
    missing_targets: int = 0


class ChronosRunReport(RunReportBase):
    """Persisted audit of one Chronos recycler pass."""

    report_type: Literal["chronos"] = "chronos"
    processed_entries: int = Field(ge=0)
    findings_seen: int = Field(ge=0)
    findings_resolved: int = Field(ge=0)
    negative_edges_written: int = Field(ge=0)
    nodes_demoted: int = Field(ge=0)
    pool_entries_cleared: int = Field(ge=0)
    actions: list[ChronosAction] = Field(default_factory=list)


def build_chronos_run_report(
    summary: ChronosRunSummary,
    *,
    started_at: datetime,
    finished_at: datetime,
) -> ChronosRunReport:
    """Map a recycler summary into a persisted :class:`ChronosRunReport`."""
    duration_s = max((finished_at - started_at).total_seconds(), 0.0)
    anomalies: list[str] = []
    if summary.missing_findings:
        anomalies.append("missing_finding_nodes")
    if summary.missing_targets:
        anomalies.append("missing_target_nodes")

    if summary.skipped_reason:
        verdict: Literal["good", "partial", "poor", "failed"] = "good"
        reasoning = summary.skipped_reason
    elif summary.findings_seen > 0 and summary.pool_entries_cleared == 0:
        verdict = "poor"
        reasoning = "findings seen but no pool entries cleared"
    elif summary.missing_findings or summary.missing_targets:
        verdict = "partial"
        reasoning = "missing finding or target nodes during pass"
    else:
        verdict = "good"
        reasoning = "chronos pass completed"

    return ChronosRunReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        status="completed",
        verdict=verdict,
        verdict_reasoning=reasoning,
        anomalies=anomalies,
        processed_entries=summary.processed_entries,
        findings_seen=summary.findings_seen,
        findings_resolved=summary.findings_resolved,
        negative_edges_written=summary.negative_edges_written,
        nodes_demoted=summary.nodes_demoted,
        pool_entries_cleared=summary.pool_entries_cleared,
        actions=list(summary.actions),
    )


__all__ = ["ChronosAction", "ChronosRunReport", "ChronosRunSummary", "build_chronos_run_report"]
