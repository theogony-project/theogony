"""One-shot re-cluster entry point (CLI + tests)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, cast

from theogony.clustering.recluster_phase import ClusteringRunReportPayload, ReclusterPhase
from theogony.memory.tick_phase import TickContext

if TYPE_CHECKING:
    from theogony.config.settings import Settings
    from theogony.core.store import KnowledgeStore
    from theogony.reporting.models import ClusteringRunReport
    from theogony.reporting.writer import RunReportWriter


async def run_one_recluster_pass(
    store: KnowledgeStore,
    settings: Settings,
    writer: RunReportWriter,
    *,
    force: bool = False,
) -> ClusteringRunReport | None:
    """Run :class:`ReclusterPhase` once and persist a :class:`ClusteringRunReport`."""
    from theogony.reporting.models import ClusteringRunReport, new_run_id

    phase = ReclusterPhase()
    started = datetime.now(UTC)
    ctx = TickContext(
        started_at=started,
        perf_started=0.0,
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=writer,
    )
    if force:
        ctx.extras["recluster_force"] = True
    await phase.run(ctx)
    payload_raw = ctx.extras.get("clustering_run")
    if not isinstance(payload_raw, ClusteringRunReportPayload):
        return None
    payload = payload_raw
    finished = datetime.now(UTC)
    _algo: Literal["hdbscan", "kmeans"] = (
        cast(Literal["hdbscan", "kmeans"], payload.algorithm)
        if payload.algorithm in ("hdbscan", "kmeans")
        else "hdbscan"
    )
    report = ClusteringRunReport(
        run_id=new_run_id(),
        started_at=started,
        finished_at=finished,
        duration_s=max((finished - started).total_seconds(), 0.0),
        status="completed",
        verdict="good",
        verdict_reasoning="recluster pass",
        algorithm=_algo,
        nodes_processed=payload.nodes_processed,
        clusters_formed=payload.clusters_formed,
        clusters_inherited=payload.clusters_inherited,
        clusters_minted=payload.clusters_minted,
        noise_node_count=payload.noise_node_count,
        mean_cluster_size=payload.mean_cluster_size,
        cluster_size_distribution=payload.cluster_size_distribution,
        runtime_ms=payload.runtime_ms,
    )
    writer.write(report)
    return report
