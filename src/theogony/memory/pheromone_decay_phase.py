"""Oneiros tick phase: decay idle edge pheromone deltas (PHX-0057 Phase 1 / W2)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from theogony.config.logging import get_logger

if TYPE_CHECKING:
    from theogony.memory.tick_phase import TickContext

log = get_logger("memory.pheromone_decay")


class PheromoneDecayPhase:
    name = "pheromone_decay"

    async def run(self, ctx: TickContext) -> None:
        cfg = ctx.cfg.edge_pheromone
        horizon = ctx.started_at - timedelta(days=cfg.decay_horizon_days)

        aged = await ctx.store.list_aged_pheromone_edges(horizon=horizon, epsilon=cfg.decay_epsilon)

        updates: list[tuple[str, float]] = []
        for edge_id, current_delta in aged:
            new_delta = current_delta * (1.0 - cfg.decay_rate)
            if abs(new_delta) < cfg.decay_epsilon:
                new_delta = 0.0
            updates.append((edge_id, new_delta))

        if updates:
            await ctx.store.batch_update_pheromone_deltas(updates)

        ctx.extras["pheromone_decay"] = {
            "edges_decayed": len(updates),
            "horizon_days": cfg.decay_horizon_days,
            "decay_rate": cfg.decay_rate,
        }


__all__ = ["PheromoneDecayPhase"]
