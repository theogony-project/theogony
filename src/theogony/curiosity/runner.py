"""One-shot blind-spot aggregation (PHX-0058 Phase 1 / W3)."""

from __future__ import annotations

from datetime import UTC, datetime

from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.blind_spot_aggregator import run_blind_spot_aggregation
from theogony.reporting.models import BlindSpotReport
from theogony.reporting.writer import RunReportWriter


async def run_one_aggregation_pass(
    store: KnowledgeStore,  # noqa: ARG001 — reserved for future store-backed signals
    settings: Settings,
    writer: RunReportWriter,
    *,
    force: bool = False,
) -> list[BlindSpotReport]:
    """Run aggregation once; used by CLI ``curiosity blindspots`` and tests."""
    started_at = datetime.now(UTC)
    written, _ = await run_blind_spot_aggregation(
        writer,
        settings.curiosity,
        started_at=started_at,
        force=force,
    )
    return written


__all__ = ["run_one_aggregation_pass"]
