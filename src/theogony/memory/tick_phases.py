"""Concrete :class:`~theogony.memory.tick_phase.TickPhase` implementations for Gen 1.

The default registry lives in ``oneiros`` as ``DEFAULT_PHASE_REGISTRY``.
Tests may inject a partial ``phase_registry`` on :class:`~theogony.memory.oneiros.OneirosWorker`.
"""

from __future__ import annotations

from theogony.core.model import Layer, ScoreUpdate
from theogony.core.vitality import compute_connectivity_linear, compute_freshness_linear
from theogony.memory.tick_phase import TickContext, _aware


class SnapshotEphemeraPhase:
    name = "snapshot_ephemera"

    async def run(self, ctx: TickContext) -> None:
        ctx.nodes_ephemera = [n async for n in ctx.store.export_layer(Layer.EPHEMERA)]


class CountNeighborsPhase:
    name = "count_neighbors"

    async def run(self, ctx: TickContext) -> None:
        ctx.edge_counts = await ctx.store.count_neighbors_in_layer(Layer.EPHEMERA)


class RecomputeScoresPhase:
    name = "recompute_scores"

    async def run(self, ctx: TickContext) -> None:
        for node in ctx.nodes_ephemera:
            before = node.scores.vitality()
            ctx.pre_vitality.append(before)

            degree = ctx.edge_counts.get(node.id, 0)
            new_conn = compute_connectivity_linear(
                degree=degree,
                full_credit_edges=ctx.cfg.connectivity_full_credit_edges,
            )
            new_fresh = compute_freshness_linear(
                node.last_accessed,
                horizon_days=ctx.cfg.freshness_horizon_days,
                now=ctx.started_at,
            )

            new_scores = node.scores.model_copy(
                update={"connectivity": new_conn, "freshness": new_fresh}
            )
            new_vitality = new_scores.vitality()
            ctx.post_vitality.append(new_vitality)

            ctx.updates.append(
                ScoreUpdate(
                    node_id=node.id,
                    connectivity=new_conn,
                    freshness=new_fresh,
                    vitality=new_vitality,
                )
            )
            if new_vitality >= ctx.cfg.promote_threshold:
                ctx.promote_targets.append(node.id)


class WriteScoresPhase:
    name = "write_scores"

    async def run(self, ctx: TickContext) -> None:
        await ctx.store.batch_update_scores(ctx.updates)


class PromotePhase:
    name = "promote"

    async def run(self, ctx: TickContext) -> None:
        for node_id in ctx.promote_targets:
            await ctx.store.promote(node_id)
            ctx.nodes_promoted += 1


class DegradeMnemePhase:
    name = "degrade_mneme"

    async def run(self, ctx: TickContext) -> None:
        min_idle_s = ctx.cfg.degrade_min_idle_days * 86400.0
        async for mnode in ctx.store.export_layer(Layer.MNEME):
            idle_s = (ctx.started_at - _aware(mnode.last_accessed)).total_seconds()
            if mnode.scores.vitality() <= ctx.cfg.degrade_threshold and idle_s >= min_idle_s:
                await ctx.store.degrade(mnode.id)
                ctx.nodes_degraded += 1
