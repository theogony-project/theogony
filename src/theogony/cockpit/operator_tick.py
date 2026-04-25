"""One-shot immune + Mnemosyne pass for Cockpit operator UI (Wave 3).

Mirrors ``demo/run_wave3_workers.sh`` against an *already open*
:class:`~theogony.core.store.KnowledgeStore` so the Cockpit process
mutates the same chronicle it serves.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.athene import AtheneVerifier
from theogony.agents.chronos import ChronosRecycler
from theogony.agents.eris import ErisRedTeam
from theogony.agents.factory import build_llm_from_settings
from theogony.agents.mnemosyne_conductor import MnemosyneConductor
from theogony.agents.nemesis import NemesisAuditor
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.chronos_report import ChronosRunSummary, build_chronos_run_report
from theogony.curiosity.eris_report import ErisCampaignSummary, build_eris_campaign_report
from theogony.curiosity.mnemosyne_conductor_report import build_mnemosyne_conductor_report
from theogony.curiosity.nemesis_report import NemesisRunSummary, build_nemesis_run_report
from theogony.curiosity.verification_pool import VerificationPool
from theogony.reporting.writer import RunReportWriter


class OperatorTickStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    ok: bool = Field(description="False only when the step raised unexpectedly.")
    message: str = ""


async def run_wave3_worker_pass(
    *,
    store: KnowledgeStore,
    settings: Settings,
    report_writer: RunReportWriter,
    mnemosyne_metric_mode: Literal["llm", "fixture"] | None = "fixture",
) -> list[OperatorTickStep]:
    """Run Athene → Chronos → Nemesis → Eris (fixture) → Mnemosyne conductor once."""
    out: list[OperatorTickStep] = []

    out.append(await _tick_athene(store, settings))
    out.append(await _tick_chronos(store, settings, report_writer))
    out.append(await _tick_nemesis(store, settings, report_writer))
    out.append(await _tick_eris(store, settings, report_writer))

    mnemo_settings = settings
    if mnemosyne_metric_mode is not None:
        mnemo_settings = mnemo_settings.model_copy(
            update={
                "mnemosyne": mnemo_settings.mnemosyne.model_copy(
                    update={"metric_definition_mode": mnemosyne_metric_mode},
                )
            }
        )
    out.append(await _tick_mnemosyne(store, mnemo_settings, report_writer))
    return out


async def _tick_athene(store: KnowledgeStore, settings: Settings) -> OperatorTickStep:
    if not settings.curiosity.athene.enabled:
        return OperatorTickStep(step="athene", ok=True, message="skipped (disabled)")
    try:
        pool = VerificationPool(settings)
        verifier = AtheneVerifier(
            store=store,
            pool=pool,
            settings=settings.curiosity.athene,
            run_reports_dir=settings.run_reports_dir,
        )
        summary = await verifier.run_once(seed=None)
        if summary.skipped_reason:
            return OperatorTickStep(step="athene", ok=True, message=summary.skipped_reason)
        return OperatorTickStep(
            step="athene",
            ok=True,
            message=(
                f"sampled={summary.sampled_count} findings={summary.findings_written} "
                f"pool_marked={summary.pool_entries_marked}"
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return OperatorTickStep(step="athene", ok=False, message=str(exc))


async def _tick_chronos(
    store: KnowledgeStore, settings: Settings, report_writer: RunReportWriter
) -> OperatorTickStep:
    started_at = datetime.now(UTC)
    if not settings.curiosity.chronos.enabled:
        summary = ChronosRunSummary(skipped_reason="chronos disabled")
        finished_at = datetime.now(UTC)
        report_writer.write(
            build_chronos_run_report(summary, started_at=started_at, finished_at=finished_at)
        )
        return OperatorTickStep(step="chronos", ok=True, message=summary.skipped_reason or "")
    try:
        pool = VerificationPool(settings)
        recycler = ChronosRecycler(
            store=store,
            pool=pool,
            settings=settings.curiosity.chronos,
        )
        summary = await recycler.run_once()
        finished_at = datetime.now(UTC)
        report_writer.write(
            build_chronos_run_report(summary, started_at=started_at, finished_at=finished_at)
        )
        if summary.skipped_reason:
            return OperatorTickStep(step="chronos", ok=True, message=summary.skipped_reason)
        return OperatorTickStep(
            step="chronos",
            ok=True,
            message=(
                f"processed={summary.processed_entries} findings={summary.findings_seen} "
                f"cleared={summary.pool_entries_cleared}"
            ),
        )
    except Exception as exc:  # pragma: no cover
        return OperatorTickStep(step="chronos", ok=False, message=str(exc))


async def _tick_nemesis(
    store: KnowledgeStore, settings: Settings, report_writer: RunReportWriter
) -> OperatorTickStep:
    started_at = datetime.now(UTC)
    if not settings.curiosity.nemesis.enabled:
        summary = NemesisRunSummary(skipped_reason="nemesis disabled")
        finished_at = datetime.now(UTC)
        report_writer.write(
            build_nemesis_run_report(summary, started_at=started_at, finished_at=finished_at)
        )
        return OperatorTickStep(step="nemesis", ok=True, message=summary.skipped_reason or "")
    try:
        auditor = NemesisAuditor(store=store, settings=settings.curiosity.nemesis)
        summary = await auditor.run_once()
        finished_at = datetime.now(UTC)
        report_writer.write(
            build_nemesis_run_report(summary, started_at=started_at, finished_at=finished_at)
        )
        if summary.skipped_reason:
            return OperatorTickStep(step="nemesis", ok=True, message=summary.skipped_reason)
        return OperatorTickStep(
            step="nemesis",
            ok=True,
            message=(
                f"findings={summary.findings_written} "
                f"confidence={summary.confidence_inflation_count} "
                f"contradictions={summary.persistent_contradiction_count}"
            ),
        )
    except Exception as exc:  # pragma: no cover
        return OperatorTickStep(step="nemesis", ok=False, message=str(exc))


async def _tick_eris(
    store: KnowledgeStore, settings: Settings, report_writer: RunReportWriter
) -> OperatorTickStep:
    started_at = datetime.now(UTC)
    if not settings.curiosity.eris.enabled:
        summary = ErisCampaignSummary(skipped_reason="eris disabled")
        finished_at = datetime.now(UTC)
        report_writer.write(
            build_eris_campaign_report(summary, started_at=started_at, finished_at=finished_at)
        )
        return OperatorTickStep(step="eris", ok=True, message=summary.skipped_reason or "")
    try:
        team = ErisRedTeam(store=store, settings=settings.curiosity.eris, answerer=None)
        summary = await team.run_once()
        finished_at = datetime.now(UTC)
        report_writer.write(
            build_eris_campaign_report(summary, started_at=started_at, finished_at=finished_at)
        )
        if summary.skipped_reason:
            return OperatorTickStep(step="eris", ok=True, message=summary.skipped_reason)
        return OperatorTickStep(
            step="eris",
            ok=True,
            message=(
                f"probes={summary.probes_run} passed={summary.passed} failed={summary.failed} "
                f"findings={summary.findings_written}"
            ),
        )
    except Exception as exc:  # pragma: no cover
        return OperatorTickStep(step="eris", ok=False, message=str(exc))


async def _tick_mnemosyne(
    store: KnowledgeStore, settings: Settings, report_writer: RunReportWriter
) -> OperatorTickStep:
    started_at = datetime.now(UTC)
    pool = VerificationPool(settings)
    llm = None
    with contextlib.suppress(ValueError):
        llm = build_llm_from_settings(settings)
    try:
        conductor = MnemosyneConductor(
            store=store,
            pool=pool,
            writer=report_writer,
            settings=settings,
            llm=llm,
        )
        summary, snapshot = await conductor.run_once()
        finished_at = datetime.now(UTC)
        report = build_mnemosyne_conductor_report(
            summary, snapshot=snapshot, started_at=started_at, finished_at=finished_at
        )
        report_writer.write(report)
        if not settings.mnemosyne.conductor_enabled:
            return OperatorTickStep(
                step="mnemosyne",
                ok=True,
                message="Mnemosyne conductor disabled",
            )
        if summary.skipped_reason:
            return OperatorTickStep(step="mnemosyne", ok=True, message=summary.skipped_reason)
        return OperatorTickStep(
            step="mnemosyne",
            ok=True,
            message=(
                f"metrics={summary.metrics_defined} experiments={summary.experiment_nodes_written} "
                f"drafts={summary.backlog_drafts_written}"
            ),
        )
    except Exception as exc:  # pragma: no cover
        return OperatorTickStep(step="mnemosyne", ok=False, message=str(exc))


class OperatorWorkerTickResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[OperatorTickStep]
