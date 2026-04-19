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

All formulas live inline per Plan §5 E8.5 (lifecycle math). The
worker does NOT use the existing ``core/vitality.py`` helpers —
those stay test-locked at their current shape; the worker carries
its own clearer-for-lifecycle-math formulas. PHX-0009 reconciles
the two homes if needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import statistics
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from theogony.config.logging import get_logger
from theogony.core.model import Layer, ScoreUpdate
from theogony.reporting.models import (
    OneirosTickReport,
    VitalityShift,
    new_run_id,
)
from theogony.reporting.verdict import oneiros_verdict

if TYPE_CHECKING:
    from theogony.config.settings import Settings
    from theogony.core.model import KnowledgeNode
    from theogony.core.store import KnowledgeStore
    from theogony.reporting.writer import RunReportWriter

log = get_logger("memory.oneiros")


def _aware(dt: datetime) -> datetime:
    """Coerce a naive datetime to UTC; pass aware datetimes through.

    Older :class:`KnowledgeNode` records on disk may have stored
    ``last_accessed`` as a naive datetime (UTC implicit). Subtraction
    against an aware ``datetime.now(UTC)`` raises; this helper
    normalises both sides to aware-UTC.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


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
    below is a line-for-line translation of that pseudo-code.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        settings: Settings,
        report_writer: RunReportWriter,
        *,
        tick_interval_s: float | None = None,
    ) -> None:
        # Q1: tick_interval_s=None falls back to Settings.oneiros.tick_interval_s.
        # Tests pass tick_interval_s=0.1 directly; production reads from Settings.
        self._store = store
        self._settings = settings
        self._writer = report_writer
        self._tick_interval_s = (
            tick_interval_s if tick_interval_s is not None else settings.oneiros.tick_interval_s
        )

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
        """One pass over EPHEMERA + MNEME. Matches Plan §5 E8.5 pseudo-code."""
        started = datetime.now(UTC)
        perf_started = time.perf_counter()
        cfg = self._settings.oneiros
        raised = False

        try:
            # 1. Snapshot EPHEMERA (one round-trip via export_layer iterator).
            nodes_ephemera: list[KnowledgeNode] = [
                n async for n in self._store.export_layer(Layer.EPHEMERA)
            ]

            # 2. Bulk neighbour-count for the layer (one round-trip).
            edge_counts = await self._store.count_neighbors_in_layer(Layer.EPHEMERA)

            # 3. Compute new connectivity, freshness, vitality client-side.
            updates: list[ScoreUpdate] = []
            pre_vitality: list[float] = []
            post_vitality: list[float] = []
            promote_targets: list[str] = []
            for node in nodes_ephemera:
                before = node.scores.vitality()
                pre_vitality.append(before)

                degree = edge_counts.get(node.id, 0)
                new_conn = min(1.0, degree / cfg.connectivity_full_credit_edges)
                idle_days = (started - _aware(node.last_accessed)).total_seconds() / 86400.0
                new_fresh = max(0.0, 1.0 - idle_days / cfg.freshness_horizon_days)

                new_scores = node.scores.model_copy(
                    update={"connectivity": new_conn, "freshness": new_fresh}
                )
                new_vitality = new_scores.vitality()
                post_vitality.append(new_vitality)

                updates.append(
                    ScoreUpdate(
                        node_id=node.id,
                        connectivity=new_conn,
                        freshness=new_fresh,
                        vitality=new_vitality,
                    )
                )
                if new_vitality >= cfg.promote_threshold:
                    promote_targets.append(node.id)

            # 4. Bulk write all score updates in one round-trip (PHX-0048).
            await self._store.batch_update_scores(updates)

            # 5. Promotion (one round-trip per promoted node — typically a
            #    small fraction of EPHEMERA per tick; not worth bulk-batching
            #    in Gen 1).
            promoted = 0
            for node_id in promote_targets:
                await self._store.promote(node_id)
                promoted += 1

            # 6. Degradation pass over MNEME with the hysteresis idle guard.
            degraded = 0
            min_idle_s = cfg.degrade_min_idle_days * 86400.0
            async for mnode in self._store.export_layer(Layer.MNEME):
                idle_s = (started - _aware(mnode.last_accessed)).total_seconds()
                if mnode.scores.vitality() <= cfg.degrade_threshold and idle_s >= min_idle_s:
                    await self._store.degrade(mnode.id)
                    degraded += 1
        except asyncio.CancelledError:
            raise
        except Exception:
            # The outer ``run`` loop catches + logs; mark raised=True so
            # the report is built with the failed verdict before
            # re-raising lets the loop log + sleep + retry.
            raised = True
            raise
        finally:
            duration_s = time.perf_counter() - perf_started
            # 7. Build OneirosTickReport, write via RunReportWriter.
            #    pre/post lists exist because we built them above; if the
            #    snapshot/recompute step raised before populating them,
            #    they are simply empty lists (mean/median return 0.0).
            try:
                report = self._finalize_report(
                    started_at=started,
                    duration_s=duration_s,
                    nodes_evaluated=len(nodes_ephemera) if not raised else 0,
                    nodes_promoted=promoted if not raised else 0,
                    nodes_degraded=degraded if not raised else 0,
                    pre_vitality=pre_vitality if not raised else [],
                    post_vitality=post_vitality if not raised else [],
                    raised=raised,
                )
                self._writer.write(report)
            except Exception:  # pragma: no cover - defensive
                # Report write itself failed: log but do not propagate;
                # the next tick gets its own fresh attempt.
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


_: type = contextlib.AbstractContextManager  # silence unused-import; reserved for future


__all__ = ["OneirosWorker"]
