"""Eris red-team campaign report (Living Demo W16)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.reporting.models import RunReportBase

ErisProbeKind = Literal["adversarial_query", "source_poisoning_fixture", "coverage_axis_fixture"]
ErisProbeOutcome = Literal["passed", "failed", "not_run"]


class ErisProbeResult(BaseModel):
    """Outcome of one probe in a campaign."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str
    probe_kind: ErisProbeKind
    prompt_or_label: str
    expected_verdict: str | None = None
    observed_verdict: str | None = None
    outcome: ErisProbeOutcome
    evidence: list[str] = Field(default_factory=list)
    finding_id: str | None = None


class ErisCampaignSummary(BaseModel):
    """Accumulator for :meth:`~theogony.agents.eris.ErisRedTeam.run_once`."""

    model_config = ConfigDict(extra="forbid")

    campaign_label: str = "w16-fixture"
    fixture_mode: bool = True
    probes_run: int = 0
    passed: int = 0
    failed: int = 0
    not_run: int = 0
    findings_written: int = 0
    probe_results: list[ErisProbeResult] = Field(default_factory=list)
    skipped_reason: str | None = None


class ErisCampaignReport(RunReportBase):
    """Persisted audit of one Eris campaign."""

    report_type: Literal["eris"] = "eris"
    campaign_label: str
    fixture_mode: bool = True
    probes_run: int = Field(ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    not_run: int = Field(default=0, ge=0)
    findings_written: int = Field(default=0, ge=0)
    probe_results: list[ErisProbeResult] = Field(default_factory=list)


def build_eris_campaign_report(
    summary: ErisCampaignSummary,
    *,
    started_at: datetime,
    finished_at: datetime,
) -> ErisCampaignReport:
    """Map an Eris campaign summary into a persisted :class:`ErisCampaignReport`."""
    duration_s = max((finished_at - started_at).total_seconds(), 0.0)

    if summary.skipped_reason:
        verdict: Literal["good", "partial", "poor", "failed"] = "good"
        reasoning = summary.skipped_reason
    else:
        executed = summary.passed + summary.failed
        if executed > 0 and summary.failed == executed:
            verdict = "poor"
            reasoning = "all executed probes failed"
        elif summary.failed > 0:
            verdict = "partial"
            reasoning = "some probes failed"
        else:
            verdict = "good"
            reasoning = "campaign completed"

    return ErisCampaignReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        status="completed",
        verdict=verdict,
        verdict_reasoning=reasoning,
        campaign_label=summary.campaign_label,
        fixture_mode=summary.fixture_mode,
        probes_run=summary.probes_run,
        passed=summary.passed,
        failed=summary.failed,
        not_run=summary.not_run,
        findings_written=summary.findings_written,
        probe_results=list(summary.probe_results),
    )


__all__ = [
    "ErisCampaignReport",
    "ErisCampaignSummary",
    "ErisProbeKind",
    "ErisProbeOutcome",
    "ErisProbeResult",
    "build_eris_campaign_report",
]
