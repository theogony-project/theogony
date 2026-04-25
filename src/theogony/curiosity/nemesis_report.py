"""Nemesis structural audit run report (Living Demo W16)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.reporting.models import RunReportBase

NemesisAuditKind = Literal[
    "confidence_inflation",
    "persistent_contradiction",
    "pheromone_autobahn",
]


class NemesisFindingRecord(BaseModel):
    """One Nemesis finding surfaced during a pass."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str
    finding_type: NemesisAuditKind
    severity: Literal["info", "low", "medium", "high", "critical"]
    target_node_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class NemesisRunSummary(BaseModel):
    """Accumulator for :meth:`~theogony.agents.nemesis.NemesisAuditor.run_once`."""

    model_config = ConfigDict(extra="forbid")

    audits_run: list[NemesisAuditKind] = Field(default_factory=list)
    findings_written: int = 0
    confidence_inflation_count: int = 0
    persistent_contradiction_count: int = 0
    pheromone_autobahn_count: int = 0
    missing_targets: int = 0
    skipped_reason: str | None = None
    audits_incomplete: bool = False
    findings: list[NemesisFindingRecord] = Field(default_factory=list)


class NemesisRunReport(RunReportBase):
    """Persisted audit of one Nemesis structural pass."""

    report_type: Literal["nemesis"] = "nemesis"
    audits_run: list[NemesisAuditKind] = Field(default_factory=list)
    findings_written: int = Field(ge=0)
    confidence_inflation_count: int = Field(default=0, ge=0)
    persistent_contradiction_count: int = Field(default=0, ge=0)
    pheromone_autobahn_count: int = Field(default=0, ge=0)
    findings: list[NemesisFindingRecord] = Field(default_factory=list)


def build_nemesis_run_report(
    summary: NemesisRunSummary,
    *,
    started_at: datetime,
    finished_at: datetime,
) -> NemesisRunReport:
    """Map a Nemesis pass summary into a persisted :class:`NemesisRunReport`."""
    duration_s = max((finished_at - started_at).total_seconds(), 0.0)
    anomalies: list[str] = []
    if summary.missing_targets:
        anomalies.append("missing_target_nodes")

    if summary.skipped_reason:
        verdict: Literal["good", "partial", "poor", "failed"] = "good"
        reasoning = summary.skipped_reason
    elif summary.audits_incomplete:
        verdict = "poor"
        reasoning = "parse or data issues prevented all Nemesis audits from completing"
    elif summary.missing_targets:
        verdict = "partial"
        reasoning = "one or more finding targets were missing from the store"
    else:
        verdict = "good"
        reasoning = "nemesis pass completed"

    return NemesisRunReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        status="completed",
        verdict=verdict,
        verdict_reasoning=reasoning,
        anomalies=anomalies,
        audits_run=list(summary.audits_run),
        findings_written=summary.findings_written,
        confidence_inflation_count=summary.confidence_inflation_count,
        persistent_contradiction_count=summary.persistent_contradiction_count,
        pheromone_autobahn_count=summary.pheromone_autobahn_count,
        findings=list(summary.findings),
    )


__all__ = [
    "NemesisAuditKind",
    "NemesisFindingRecord",
    "NemesisRunReport",
    "NemesisRunSummary",
    "build_nemesis_run_report",
]
