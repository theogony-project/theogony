"""Oneiros tick phase: Morpheus associator (PHX-0059 Phase 1 / W4)."""

from __future__ import annotations

from theogony.memory.morpheus import MorpheusAssociator
from theogony.memory.tick_phase import TickContext


class MorpheusPhase:
    name = "morpheus"

    async def run(self, ctx: TickContext) -> None:
        cfg = ctx.app_settings.morpheus
        associator = MorpheusAssociator(ctx.store, cfg=cfg)

        proposal = await associator.propose_associations(run_id=ctx.run_id)
        if proposal.edges:
            await ctx.store.batch_upsert_edges(proposal.edges)

        skipped = proposal.candidates_skipped_no_neighbors_in_band
        ctx.extras["morpheus"] = {
            "candidates_considered": proposal.candidates_considered,
            "candidates_with_proposals": proposal.candidates_with_proposals,
            "candidates_skipped_no_neighbors_in_band": skipped,
            "edges_proposed": len(proposal.edges),
        }


__all__ = ["MorpheusPhase"]
