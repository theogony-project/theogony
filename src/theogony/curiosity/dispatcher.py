"""
CuriosityDispatcher — manual batch runner for Argus over on-disk reports (W7-B).

Reads ``CuriosityRunReport`` JSON files whose ``decision.hestia_status`` is
still ``not_evaluated``, runs :class:`~theogony.agents.argus.ArgusAgent`
sequentially (no ``asyncio.gather``), and persists the merged outcome back
through :class:`~theogony.reporting.writer.RunReportWriter`.

There is **no** background worker in W7-B — only the CLI entry point
``theogony curiosity run-pending`` invokes this type.
"""

from __future__ import annotations

import json
from pathlib import Path

from theogony.agents.argus import ArgusProcessable, ArgusResult
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.reporting.writer import RunReportWriter


def pending_curiosity_report_count(run_reports_dir: Path) -> int:
    """Return how many on-disk curiosity reports still await Argus (``hestia_status``)."""
    return len(_pending_curiosity_paths(Path(run_reports_dir) / "curiosity"))


def _pending_curiosity_paths(curiosity_dir: Path) -> list[Path]:
    if not curiosity_dir.is_dir():
        return []
    paths = sorted(
        (p for p in curiosity_dir.iterdir() if p.is_file() and p.suffix == ".json"),
        key=lambda p: p.stem,
    )
    pending: list[Path] = []
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("report_type") != "curiosity":
            continue
        dec = raw.get("decision") or {}
        if dec.get("hestia_status") == "not_evaluated":
            pending.append(path)
    return pending


class CuriosityDispatcher:
    """Watches the curiosity reports directory; dispatches Argus per emitted trigger."""

    def __init__(
        self,
        *,
        reports_dir: Path,
        argus: ArgusProcessable,
        writer: RunReportWriter,
    ) -> None:
        self._curiosity_dir = Path(reports_dir) / "curiosity"
        self._argus = argus
        self._writer = writer

    def _list_pending_paths(self) -> list[Path]:
        return _pending_curiosity_paths(self._curiosity_dir)

    async def process_pending(
        self,
        *,
        max_triggers: int = 5,
        dry_run: bool = False,
        argus_enabled: bool = True,
    ) -> list[ArgusResult]:
        """Oldest pending reports first, capped at ``max_triggers``."""
        if not argus_enabled:
            return []
        paths = self._list_pending_paths()[:max_triggers]
        results: list[ArgusResult] = []
        for path in paths:
            report = CuriosityRunReport.model_validate_json(path.read_text(encoding="utf-8"))
            result = await self._argus.process(report.trigger, dry_run=dry_run)
            results.append(result)
            if not dry_run:
                updated = _merge_curiosity_report(report, result)
                self._writer.write(updated)
        return results


def _merge_curiosity_report(report: CuriosityRunReport, result: ArgusResult) -> CuriosityRunReport:
    extra = f"argus:{result.outcome.value}"
    if result.reason:
        extra += f":{result.reason}"
    vr = report.verdict_reasoning
    new_vr = f"{vr} | {extra}" if vr else extra
    trig = result.updated_trigger if result.updated_trigger is not None else report.trigger
    ev = (
        result.evaluator_decision
        if result.evaluator_decision is not None
        else report.evaluator_decision
    )
    return report.model_copy(
        update={
            "trigger": trig,
            "decision": result.decision,
            "bytes_acquired": result.bytes_acquired,
            "verdict_reasoning": new_vr[:5000],
            "evaluator_decision": ev,
        }
    )


__all__ = ["CuriosityDispatcher", "pending_curiosity_report_count"]
