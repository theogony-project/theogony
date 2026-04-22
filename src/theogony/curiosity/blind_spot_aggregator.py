"""Blind-spot clustering over stub QueryRunReports (PHX-0058 Phase 1 / W3)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from theogony.clustering.protocol import ClusteringStrategy
from theogony.config.settings import CuriositySettings
from theogony.core.model import NodeType
from theogony.reporting.models import (
    BlindSpotCandidate,
    BlindSpotReport,
    QueryRunReport,
    StubVerdict,
    new_run_id,
)
from theogony.reporting.writer import RunReportWriter


def load_query_reports_in_window(
    writer: RunReportWriter,
    *,
    now: datetime,
    window_days: float,
) -> list[QueryRunReport]:
    """Load recent query reports whose ``started_at`` falls inside the window."""
    d: Path = writer.directory_for("query")
    if window_days <= 0.0:
        cutoff = datetime.min.replace(tzinfo=UTC)
    else:
        cutoff = now - timedelta(seconds=window_days * 86400.0)
    out: list[QueryRunReport] = []
    paths = sorted(
        (p for p in d.iterdir() if p.is_file() and p.suffix == ".json"),
        key=lambda p: p.stem,
        reverse=True,
    )
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if raw.get("report_type") != "query":
            continue
        try:
            report = QueryRunReport.model_validate(raw)
        except Exception:
            continue
        st = report.started_at
        if st.tzinfo is None:
            st = st.replace(tzinfo=UTC)
        if st < cutoff:
            break
        out.append(report)
    return out


def aggregate_blind_spots(
    *,
    stub_reports: Sequence[QueryRunReport],
    clustering_strategy: ClusteringStrategy,
    thresholds: CuriositySettings,
) -> list[BlindSpotCandidate]:
    """Cluster stub-firing region descriptors; emit one candidate per cluster."""
    descriptors = [
        (r.run_id, r.region_descriptor) for r in stub_reports if r.region_descriptor is not None
    ]
    if len(descriptors) < thresholds.min_hits:
        return []

    node_ids = [run_id for run_id, _ in descriptors]
    embeddings = [d.query_embedding for _, d in descriptors]

    result = clustering_strategy.cluster(node_ids, embeddings)

    candidates: list[BlindSpotCandidate] = []
    for cluster_idx, _centroid in result.centroids.items():
        members = [run_id for run_id, ci in result.assignments.items() if ci == cluster_idx]
        if len(members) < thresholds.min_hits:
            continue

        contributing: list[tuple[QueryRunReport, StubVerdict]] = []
        for r in stub_reports:
            if r.run_id in members and r.stub_verdict is not None:
                contributing.append((r, r.stub_verdict))
        if not contributing:
            continue
        agg_strength = sum(sv.stub_signal_strength for _r, sv in contributing) / len(contributing)

        cluster_id_counts: dict[str, int] = {}
        node_type_counts: dict[NodeType, int] = {}
        for r, _sv in contributing:
            d = r.region_descriptor
            if d is None:
                continue
            if d.dominant_cluster_id:
                cluster_id_counts[d.dominant_cluster_id] = (
                    cluster_id_counts.get(d.dominant_cluster_id, 0) + 1
                )
            if d.dominant_node_type:
                node_type_counts[d.dominant_node_type] = (
                    node_type_counts.get(d.dominant_node_type, 0) + 1
                )

        candidates.append(
            BlindSpotCandidate(
                contributing_run_ids=members,
                centroid_embedding=list(result.centroids[cluster_idx]),
                stub_signal_strength=min(1.0, max(0.0, agg_strength)),
                dominant_cluster_id=(
                    max(cluster_id_counts, key=lambda k: cluster_id_counts[k])
                    if cluster_id_counts
                    else None
                ),
                dominant_node_type=(
                    max(node_type_counts, key=lambda k: node_type_counts[k])
                    if node_type_counts
                    else None
                ),
                requires_hestia_review=False,
                hestia_review_status="not_required",
            )
        )
    return candidates


def build_blind_spot_report(
    candidate: BlindSpotCandidate,
    *,
    window_days: float,
    stub_reports_scanned: int,
    aggregator_algorithm: Literal["hdbscan", "kmeans"],
    started_at: datetime,
    finished_at: datetime,
) -> BlindSpotReport:
    duration_s = max((finished_at - started_at).total_seconds(), 0.0)
    return BlindSpotReport(
        run_id=new_run_id(),
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        status="completed",
        verdict="good",
        verdict_reasoning="blind spot aggregation",
        candidate=candidate,
        window_days=window_days,
        aggregator_algorithm=aggregator_algorithm,
        stub_reports_scanned=stub_reports_scanned,
    )


async def run_blind_spot_aggregation(
    writer: RunReportWriter,
    settings: CuriositySettings,
    *,
    started_at: datetime,
    force: bool = False,
) -> tuple[list[BlindSpotReport], dict[str, object]]:
    """Scan query reports, optionally emit :class:`BlindSpotReport` files."""
    cfg = settings
    extras: dict[str, object] = {}

    if not force:
        last = writer.most_recent("blindspot")
        if last is not None:
            elapsed_s = (started_at - last.started_at).total_seconds()
            if elapsed_s < cfg.aggregation_interval_s:
                extras["blind_spot_aggregation"] = {
                    "skipped": "within cadence",
                    "elapsed_s": elapsed_s,
                }
                return [], extras

    reports = load_query_reports_in_window(writer, now=started_at, window_days=cfg.window_days)
    stub_reports = [r for r in reports if r.stub_verdict is not None and r.stub_verdict.is_stub]
    if len(stub_reports) < cfg.min_hits:
        extras["blind_spot_aggregation"] = {
            "skipped": "below min_hits",
            "stub_reports_in_window": len(stub_reports),
        }
        return [], extras

    from theogony.clustering.hdbscan_strategy import HDBSCANStrategy

    strategy = HDBSCANStrategy(
        min_cluster_size=cfg.min_hits,
        min_samples=1,
        allow_single_cluster=True,
    )

    candidates = await asyncio.to_thread(
        lambda: aggregate_blind_spots(
            stub_reports=list(stub_reports),
            clustering_strategy=strategy,
            thresholds=cfg,
        )
    )

    finished_at = datetime.now(UTC)
    written: list[BlindSpotReport] = []
    for cand in candidates:
        rep = build_blind_spot_report(
            cand,
            window_days=cfg.window_days,
            stub_reports_scanned=len(stub_reports),
            aggregator_algorithm=cast(Literal["hdbscan", "kmeans"], strategy.name),
            started_at=started_at,
            finished_at=finished_at,
        )
        writer.write(rep)
        written.append(rep)

    extras["blind_spot_aggregation"] = {
        "stub_reports_scanned": len(stub_reports),
        "candidates_emitted": len(candidates),
    }
    return written, extras


__all__ = [
    "aggregate_blind_spots",
    "build_blind_spot_report",
    "load_query_reports_in_window",
    "run_blind_spot_aggregation",
]
