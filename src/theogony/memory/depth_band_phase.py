"""Oneiros tick phase: depth-band ladder + layer crossings (PHX-0059 Phase 1 / W4)."""

from __future__ import annotations

from collections import Counter

from theogony.core.model import Layer
from theogony.memory.depth_band import (
    derive_depth_band,
    resolved_current_band,
    step_one_toward_target,
)
from theogony.memory.tick_phase import TickContext, _aware


class DepthBandPhase:
    name = "depth_band"

    async def run(self, ctx: TickContext) -> None:
        bonus_w = ctx.app_settings.depth_band.pheromone_bonus_weight
        transitions = 0
        layer_changes = 0

        # Legacy MNEME rows may still read ``depth_band=0`` from pre-W4 data.
        # Attach them silently to the MNEME ladder floor before stepping.
        async for n in ctx.store.export_layer(Layer.MNEME):
            if n.depth_band < 3:
                await ctx.store.update_depth_band(n.id, 3)

        promoted_ids: set[str] = set()

        for layer in (Layer.EPHEMERA, Layer.MNEME):
            nodes = [n async for n in ctx.store.export_layer(layer)]
            for node in nodes:
                if layer is Layer.MNEME and node.id in promoted_ids:
                    continue
                nb = await ctx.store.get_neighborhood(node.id, depth=1, min_weight=0.0)
                idle_s = (ctx.started_at - _aware(node.last_accessed)).total_seconds()
                idle_days = idle_s / 86400.0
                target = derive_depth_band(
                    node,
                    edges_for_node=list(nb.edges),
                    idle_days=idle_days,
                    pheromone_bonus_weight=bonus_w,
                )
                current = resolved_current_band(node, layer=layer)
                new_band = step_one_toward_target(current, target)
                if new_band == current:
                    continue

                if layer is Layer.EPHEMERA and new_band >= 3:
                    await ctx.store.promote(node.id)
                    promoted_ids.add(node.id)
                    layer_changes += 1
                elif layer is Layer.MNEME and new_band <= 2:
                    await ctx.store.degrade(node.id)
                    layer_changes += 1

                await ctx.store.update_depth_band(node.id, new_band)
                transitions += 1

        distribution: Counter[int] = Counter()
        for lyr in (Layer.EPHEMERA, Layer.MNEME):
            async for n in ctx.store.export_layer(lyr):
                distribution[n.depth_band] += 1

        ctx.extras["depth_band"] = {
            "transitions": transitions,
            "layer_changes": layer_changes,
            "distribution": dict(sorted(distribution.items())),
        }


__all__ = ["DepthBandPhase"]
