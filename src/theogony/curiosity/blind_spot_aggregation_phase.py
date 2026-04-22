"""Oneiros tick phase: aggregate recurring stub regions (PHX-0058 Phase 1 / W3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from theogony.config.logging import get_logger
from theogony.curiosity.blind_spot_aggregator import run_blind_spot_aggregation

if TYPE_CHECKING:
    from theogony.memory.tick_phase import TickContext

log = get_logger("curiosity.blind_spot_aggregation")


class BlindSpotAggregationPhase:
    name = "blind_spot_aggregation"

    async def run(self, ctx: TickContext) -> None:
        writer = ctx.writer
        if writer is None:
            log.warning("blind_spot_aggregation: no RunReportWriter on TickContext; skipping")
            return
        force = bool(ctx.extras.get("blind_spot_force"))
        _written, bag = await run_blind_spot_aggregation(
            writer,
            ctx.app_settings.curiosity,
            started_at=ctx.started_at,
            force=force,
        )
        if "blind_spot_aggregation" in bag:
            ctx.extras["blind_spot_aggregation"] = bag["blind_spot_aggregation"]


__all__ = ["BlindSpotAggregationPhase"]
