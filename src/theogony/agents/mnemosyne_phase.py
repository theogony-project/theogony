"""Mnemosyne aggregation tick phase (PHX-0071 Phase 1 / W5)."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from theogony.clustering.hdbscan_strategy import HDBSCANStrategy
from theogony.config.logging import get_logger
from theogony.config.settings import MnemosyneSettings
from theogony.core.model import NodeType
from theogony.curiosity.blind_spot_aggregator import load_query_reports_in_window
from theogony.memory.tick_phase import TickContext
from theogony.reporting.models import (
    MetaClassificationVerdict,
    MnemosyneObservationCluster,
    QueryRunReport,
    new_run_id,
)
from theogony.reporting.writer import RunReportWriter

log = get_logger("agents.mnemosyne_phase")


def load_self_referential_query_reports_in_window(
    writer: RunReportWriter,
    *,
    now: datetime,
    window_days: float,
) -> list[QueryRunReport]:
    """Query reports in the window with stub verdict present and meta = self-referential."""
    reports = load_query_reports_in_window(writer, now=now, window_days=window_days)
    out: list[QueryRunReport] = []
    for r in reports:
        if r.stub_verdict is None:
            continue
        mc = r.meta_classification
        if mc is None:
            continue
        if mc.verdict != MetaClassificationVerdict.SELF_REFERENTIAL:
            continue
        out.append(r)
    return out


def _build_cluster_report(
    contributing: Sequence[QueryRunReport],
    centroid: list[float],
    *,
    window_days: float,
    started_at: datetime,
    finished_at: datetime,
) -> MnemosyneObservationCluster:
    duration_s = max((finished_at - started_at).total_seconds(), 0.0)
    agg_kw = 0
    for r in contributing:
        m = r.meta_classification
        if m is not None:
            agg_kw += m.high_keyword_hits + m.mid_keyword_hits + m.cited_label_meta_hits

    type_counts: Counter[NodeType] = Counter()
    cluster_counts: Counter[str] = Counter()
    cited_counter: Counter[str] = Counter()
    for r in contributing:
        d = r.region_descriptor
        if d is not None:
            if d.dominant_node_type is not None:
                type_counts[d.dominant_node_type] += 1
            if d.dominant_cluster_id:
                cluster_counts[d.dominant_cluster_id] += 1
        for cid in r.cited_node_ids:
            cited_counter[cid] += 1

    top_cited = [nid for nid, _ in cited_counter.most_common(10)]

    return MnemosyneObservationCluster(
        run_id=new_run_id(),
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        status="completed",
        verdict="good",
        verdict_reasoning="mnemosyne observation clustering",
        anomalies=[],
        recommendations=[],
        audit_log_run_id=None,
        ingest_run_id=None,
        centroid_embedding=list(centroid),
        contributing_run_ids=[r.run_id for r in contributing],
        contributing_query_count=len(contributing),
        aggregate_keyword_hits=agg_kw,
        dominant_node_type=type_counts.most_common(1)[0][0] if type_counts else None,
        dominant_cluster_id=cluster_counts.most_common(1)[0][0] if cluster_counts else None,
        most_recurrent_cited_node_ids=top_cited,
        window_days=window_days,
    )


async def _cluster_observations_by_region(
    observations: list[QueryRunReport],
    *,
    min_cluster_size: int,
) -> list[MnemosyneObservationCluster]:
    descriptors = [
        (r.run_id, r.region_descriptor) for r in observations if r.region_descriptor is not None
    ]
    if len(descriptors) < min_cluster_size:
        return []

    node_ids = [run_id for run_id, _ in descriptors]
    embeddings = [d.query_embedding for _, d in descriptors]
    strategy = HDBSCANStrategy(
        min_cluster_size=min_cluster_size,
        min_samples=1,
        allow_single_cluster=True,
    )
    result = await asyncio.to_thread(strategy.cluster, node_ids, embeddings)

    by_run: dict[str, QueryRunReport] = {r.run_id: r for r in observations}
    clusters_out: list[MnemosyneObservationCluster] = []
    finished_at = datetime.now(UTC)
    for cluster_idx, centroid in result.centroids.items():
        members = [run_id for run_id, ci in result.assignments.items() if ci == cluster_idx]
        if len(members) < min_cluster_size:
            continue
        contributing = [by_run[rid] for rid in members if rid in by_run]
        if len(contributing) < min_cluster_size:
            continue
        started_at = min((r.started_at for r in contributing), default=finished_at)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        clusters_out.append(
            _build_cluster_report(
                contributing,
                centroid,
                window_days=0.0,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
    return clusters_out


async def run_mnemosyne_aggregation(
    writer: RunReportWriter,
    cfg: MnemosyneSettings,
    *,
    started_at: datetime,
    force: bool = False,
) -> tuple[list[MnemosyneObservationCluster], dict[str, object]]:
    """Scan self-referential query reports; optionally emit cluster reports."""
    extras: dict[str, object] = {}

    if not force:
        last = writer.most_recent("mnemosyne")
        if last is not None:
            elapsed_s = (started_at - last.started_at).total_seconds()
            if elapsed_s < cfg.aggregation_interval_s:
                extras["mnemosyne_aggregation"] = {
                    "skipped": "within cadence",
                    "elapsed_s": elapsed_s,
                }
                return [], extras

    observations = load_self_referential_query_reports_in_window(
        writer, now=started_at, window_days=cfg.window_days
    )
    if len(observations) < cfg.min_observations:
        extras["mnemosyne_aggregation"] = {
            "skipped": "below min_observations",
            "observations_in_window": len(observations),
        }
        return [], extras

    cluster_reports = await _cluster_observations_by_region(
        observations,
        min_cluster_size=cfg.min_observations,
    )

    finished_at = datetime.now(UTC)
    written: list[MnemosyneObservationCluster] = []
    for rep in cluster_reports:
        rep.window_days = cfg.window_days
        rep.finished_at = finished_at
        rep.duration_s = max((finished_at - rep.started_at).total_seconds(), 0.0)
        writer.write(rep)
        written.append(rep)

    extras["mnemosyne_aggregation"] = {
        "observations_scanned": len(observations),
        "clusters_emitted": len(written),
    }
    return written, extras


class MnemosyneAggregationPhase:
    name = "mnemosyne_aggregation"

    async def run(self, ctx: TickContext) -> None:
        writer = ctx.writer
        if writer is None:
            log.warning("mnemosyne_aggregation: no RunReportWriter on TickContext; skipping")
            return
        cfg = ctx.app_settings.mnemosyne
        force = bool(ctx.extras.get("mnemosyne_force"))
        _written, bag = await run_mnemosyne_aggregation(
            writer,
            cfg,
            started_at=ctx.started_at,
            force=force,
        )
        if "mnemosyne_aggregation" in bag:
            ctx.extras["mnemosyne_aggregation"] = cast(
                dict[str, object],
                bag["mnemosyne_aggregation"],
            )


__all__ = [
    "MnemosyneAggregationPhase",
    "load_self_referential_query_reports_in_window",
    "run_mnemosyne_aggregation",
]
