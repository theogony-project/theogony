"""
OneirosWorker — write-back lifecycle owner (Plan §4.3, §5 E8.5).

The long-running asyncio task that makes the Memory layer breathe.
Every ``tick_interval_s`` seconds it:

1. Snapshots EPHEMERA (one ``export_layer`` round-trip).
2. Bulk-counts neighbours per node id (one ``count_neighbors_in_layer``
   round-trip — Plan §3.1a range index on `:KnowledgeNode(layer)`).
3. Recomputes connectivity / freshness / vitality client-side for
   every snapshot node.
4. Bulk-writes the new scores (one ``batch_update_scores`` round-trip
   — PHX-0048; the bulk write touches connectivity / freshness /
   vitality but NOT relevance, so concurrent ``RelevanceTracker.bump``
   writes survive — Plan §5 E8.5 race-condition note Q5).
5. Promotes nodes that crossed ``promote_threshold`` (one round-trip
   per promoted node — typically a small fraction of EPHEMERA per tick).
6. Sweeps MNEME for ``vitality <= degrade_threshold ∧ idle >=
   degrade_min_idle_days`` candidates and degrades each (hysteresis
   protects against thrashing, idle guard protects recently-touched
   MNEME nodes).
7. Builds one :class:`OneirosTickReport` and writes it via the
   :class:`RunReportWriter` (retention cap enforced by the writer per
   ``Settings.report.oneiros_tick_retention``).

Each step is a :class:`~theogony.memory.tick_phase.TickPhase` (see
``tick_phases.py``). Linear freshness/connectivity math lives in
``theogony.core.vitality`` (PHX-0009 Phase 1 / F1).
"""

from __future__ import annotations

import asyncio
import statistics
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from theogony.clustering.cluster_index import ClusterIndex
from theogony.clustering.recluster_phase import ClusteringRunReportPayload, ReclusterPhase
from theogony.config.logging import get_logger
from theogony.core.model import ClusterSummary
from theogony.memory.tick_phase import TickContext, TickPhase, _aware
from theogony.memory.tick_phases import (
    CountNeighborsPhase,
    DegradeMnemePhase,
    PromotePhase,
    RecomputeScoresPhase,
    SnapshotEphemeraPhase,
    WriteScoresPhase,
)
from theogony.reporting.models import (
    ClusteringRunReport,
    OneirosTickReport,
    VitalityShift,
    new_run_id,
)
from theogony.reporting.verdict import oneiros_verdict

if TYPE_CHECKING:
    from theogony.config.settings import Settings
    from theogony.core.store import KnowledgeStore
    from theogony.reporting.writer import RunReportWriter

log = get_logger("memory.oneiros")

DEFAULT_PHASE_REGISTRY: dict[str, type[TickPhase]] = {
    "snapshot_ephemera": SnapshotEphemeraPhase,
    "count_neighbors": CountNeighborsPhase,
    "recompute_scores": RecomputeScoresPhase,
    "write_scores": WriteScoresPhase,
    "promote": PromotePhase,
    "degrade_mneme": DegradeMnemePhase,
    "recluster": ReclusterPhase,
}


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


class OneirosWorker:
    """Long-running asyncio task owning the §4.3 write-back lifecycle.

    Lifespan: instantiated in ``api/app.py:lifespan`` (E9 wired the
    slot; E8.5 fills it). ``await worker.run()`` runs until cancelled
    by the lifespan's shutdown ordering (Plan §4.4 5-second budget).

    See Plan §5 E8.5 for the full ``_tick()`` spec; the implementation
    is a pipeline of :class:`TickPhase` instances.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        settings: Settings,
        report_writer: RunReportWriter,
        *,
        tick_interval_s: float | None = None,
        phase_registry: dict[str, type[TickPhase]] | None = None,
        cluster_index: ClusterIndex | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._writer = report_writer
        self._cluster_index = cluster_index
        self._tick_interval_s = (
            tick_interval_s if tick_interval_s is not None else settings.oneiros.tick_interval_s
        )

        registry = phase_registry or DEFAULT_PHASE_REGISTRY
        self._phases: list[TickPhase] = [
            registry[name]() for name in settings.oneiros.enabled_phases if name in registry
        ]

    async def run(self) -> None:
        """Main loop. Plan §4.4 / §5 E8.5: strict-serial tick + sleep.

        The bare ``except Exception`` is intentional: a single failed
        tick must not crash the worker because the worker's contract
        is "the lifecycle keeps moving". The traceback is logged; the
        next tick re-reads fresh state. Recurring failures are
        operator-observable as the absence of new
        ``OneirosTickReport`` JSON files.
        """
        log.info("OneirosWorker.run start: tick_interval_s=%.2f", self._tick_interval_s)
        try:
            while True:
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("oneiros tick failed; sleeping and retrying")
                await asyncio.sleep(self._tick_interval_s)
        except asyncio.CancelledError:
            log.info("OneirosWorker.run cancelled cleanly")
            raise

    async def _tick(self) -> None:
        """One pass over EPHEMERA + MNEME. Pipeline of TickPhase instances.

        Phase ordering is fixed at construction-time from
        ``Settings.oneiros.enabled_phases``. Per-phase failures are
        caught at the tick boundary; the lifecycle keeps moving
        regardless.
        """
        # TODO(F2-followup): per-phase failure isolation. Today a phase
        # exception fails the whole tick. Future phases (pheromone-decay,
        # morpheus-associator) may benefit from per-phase try/except that
        # logs and continues. Land that when the first phase that wants
        # isolation arrives.
        started = datetime.now(UTC)
        perf_started = time.perf_counter()
        cfg = self._settings.oneiros
        raised = False

        ctx = TickContext(
            started_at=started,
            perf_started=perf_started,
            cfg=cfg,
            store=self._store,
            app_settings=self._settings,
            writer=self._writer,
        )

        try:
            for phase in self._phases:
                await phase.run(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            raised = True
            raise
        finally:
            duration_s = time.perf_counter() - perf_started
            try:
                report = self._finalize_report(
                    started_at=started,
                    duration_s=duration_s,
                    nodes_evaluated=len(ctx.nodes_ephemera) if not raised else 0,
                    nodes_promoted=ctx.nodes_promoted if not raised else 0,
                    nodes_degraded=ctx.nodes_degraded if not raised else 0,
                    pre_vitality=ctx.pre_vitality if not raised else [],
                    post_vitality=ctx.post_vitality if not raised else [],
                    raised=raised,
                )
                self._writer.write(report)
                if not raised:
                    raw_refresh = ctx.extras.get("cluster_index_refresh")
                    if (
                        raw_refresh is not None
                        and self._cluster_index is not None
                        and isinstance(raw_refresh, list)
                        and all(isinstance(x, ClusterSummary) for x in raw_refresh)
                    ):
                        self._cluster_index.replace(raw_refresh)
                    cp = ctx.extras.get("clustering_run")
                    if isinstance(cp, ClusteringRunReportPayload):
                        fin = datetime.now(UTC)
                        algo = cp.algorithm if cp.algorithm in ("hdbscan", "kmeans") else "hdbscan"
                        self._writer.write(
                            ClusteringRunReport(
                                run_id=new_run_id(),
                                started_at=started,
                                finished_at=fin,
                                duration_s=max((fin - started).total_seconds(), 0.0),
                                status="completed",
                                verdict="good",
                                verdict_reasoning="recluster pass",
                                algorithm=algo,
                                nodes_processed=cp.nodes_processed,
                                clusters_formed=cp.clusters_formed,
                                clusters_inherited=cp.clusters_inherited,
                                clusters_minted=cp.clusters_minted,
                                noise_node_count=cp.noise_node_count,
                                mean_cluster_size=cp.mean_cluster_size,
                                cluster_size_distribution=cp.cluster_size_distribution,
                                runtime_ms=cp.runtime_ms,
                            )
                        )
            except Exception:  # pragma: no cover - defensive
                log.exception("oneiros tick report write failed")

    def _finalize_report(
        self,
        *,
        started_at: datetime,
        duration_s: float,
        nodes_evaluated: int,
        nodes_promoted: int,
        nodes_degraded: int,
        pre_vitality: list[float],
        post_vitality: list[float],
        raised: bool,
    ) -> OneirosTickReport:
        """Compose one :class:`OneirosTickReport` from accumulated observations.

        Matches Plan §5 E8.5 step 7 verbatim. Verdict via
        :func:`oneiros_verdict` (Plan §2.11.2 thresholds from
        ``Settings.report.thresholds.oneiros``).
        """
        finished_at = datetime.now(UTC)
        shifts = [
            after - before for before, after in zip(pre_vitality, post_vitality, strict=False)
        ]
        median_shift = _median(shifts)
        verdict, reasoning = oneiros_verdict(
            raised=raised,
            nodes_evaluated=nodes_evaluated,
            nodes_promoted=nodes_promoted,
            nodes_degraded=nodes_degraded,
            median_vitality_shift=median_shift,
            thresholds=self._settings.report.thresholds.oneiros,
        )
        return OneirosTickReport(
            run_id=new_run_id(),
            started_at=started_at,
            finished_at=finished_at,
            duration_s=max(duration_s, 0.0),
            status="failed" if raised else "completed",
            verdict=verdict,
            verdict_reasoning=reasoning,
            anomalies=[],
            recommendations=[],
            audit_log_run_id=None,
            ingest_run_id=None,
            nodes_evaluated=nodes_evaluated,
            nodes_promoted=nodes_promoted,
            nodes_degraded=nodes_degraded,
            vitality=VitalityShift(
                nodes_evaluated=nodes_evaluated,
                mean_vitality_before=_mean(pre_vitality),
                mean_vitality_after=_mean(post_vitality),
                median_shift=median_shift,
            ),
        )


__all__ = ["OneirosWorker", "DEFAULT_PHASE_REGISTRY", "_aware"]
