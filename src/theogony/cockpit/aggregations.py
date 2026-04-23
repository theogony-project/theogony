"""Read-side aggregations for Iris cockpit (PHX-0074)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer, NodeType
from theogony.core.store import KnowledgeStore
from theogony.extraction.embedding import EmbeddingProvider
from theogony.reporting.writer import RunReportWriter


def _metric_int(health: dict[str, object], *keys: str) -> int:
    for k in keys:
        v = health.get(k)
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
    return 0


async def _iter_nodes(store: KnowledgeStore) -> list[KnowledgeNode]:
    out: list[KnowledgeNode] = []
    for layer in (Layer.EPHEMERA, Layer.MNEME):
        async for n in store.export_layer(layer):
            out.append(n)
    return out


class NodeRowView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    node_type: str
    layer: str
    confidence: float


class ClusterSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cluster_id: str
    cluster_label: str | None
    member_count: int
    dominant_node_type: str | None
    dominant_source_type: str | None


class ReportRowView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    report_type: str
    verdict: str
    status: str
    duration_s: float


@dataclass(frozen=True)
class StatusSnapshot:
    node_count: int
    edge_count: int
    store_backend: str
    embedding_model: str
    embedding_dim: int
    uptime_s: int
    layer_distribution: dict[str, int]
    depth_band_distribution: dict[int, int]
    edge_type_distribution: dict[str, int]
    activity_24h: dict[str, int]
    verdict_mix_24h: dict[str, int]
    cost_summary_eur: dict[str, float]


async def compute_status_snapshot(
    store: KnowledgeStore,
    writer: RunReportWriter,
    settings: Settings,
    *,
    uptime_s: int = 0,
) -> StatusSnapshot:
    health = await store.health()
    node_count = _metric_int(health, "nodes", "node_count")
    edge_count = _metric_int(health, "edges", "edge_count")
    backend = str(health.get("backend", "unknown"))
    nodes = await _iter_nodes(store)
    layer_distribution = Counter(n.layer.value for n in nodes)
    depth_band_distribution: Counter[int] = Counter()
    for n in nodes:
        depth_band_distribution[int(n.depth_band)] += 1
    edge_type_distribution: dict[str, int] = {}
    raw_edges = getattr(store, "_edges", None)
    if isinstance(raw_edges, dict):
        for e in raw_edges.values():
            if isinstance(e, KnowledgeEdge):
                edge_type_distribution[e.relation_type] = (
                    edge_type_distribution.get(e.relation_type, 0) + 1
                )
    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    activity_24h: dict[str, int] = Counter()
    verdict_mix_24h: dict[str, int] = Counter()
    cost_today = cost_week = cost_month = 0.0
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    for rtype in ("ingest", "query", "oneiros", "clustering", "blindspot", "mnemosyne"):
        d = writer.directory_for(rtype)
        if not d.exists():
            continue
        for path in d.iterdir():
            if not path.is_file() or path.suffix != ".json":
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            finished = raw.get("finished_at")
            if not finished:
                continue
            try:
                fts = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
            except ValueError:
                continue
            if fts.tzinfo is None:
                fts = fts.replace(tzinfo=UTC)
            if fts >= since:
                activity_24h[rtype] += 1
                v = raw.get("verdict")
                if isinstance(v, str):
                    verdict_mix_24h[v] += 1
            if rtype == "query" and isinstance(raw.get("synthesis"), dict):
                ce = float(raw["synthesis"].get("cost_eur") or 0.0)
                if fts >= now.replace(hour=0, minute=0, second=0, microsecond=0):
                    cost_today += ce
                if fts >= week_ago:
                    cost_week += ce
                if fts >= month_ago:
                    cost_month += ce
    return StatusSnapshot(
        node_count=node_count,
        edge_count=edge_count,
        store_backend=backend,
        embedding_model=settings.embedding.model_id,
        embedding_dim=settings.embedding.dim,
        uptime_s=uptime_s,
        layer_distribution=dict(layer_distribution),
        depth_band_distribution=dict(depth_band_distribution),
        edge_type_distribution=edge_type_distribution,
        activity_24h=dict(activity_24h),
        verdict_mix_24h=dict(verdict_mix_24h),
        cost_summary_eur={"today": cost_today, "week": cost_week, "month": cost_month},
    )


async def list_clusters_summary(
    store: KnowledgeStore,
    *,
    limit: int | None = None,
) -> list[ClusterSummaryView]:
    summaries = await store.list_clusters()
    rows = [
        ClusterSummaryView(
            cluster_id=s.cluster_id,
            cluster_label=s.cluster_label,
            member_count=s.member_count,
            dominant_node_type=s.dominant_node_type.value if s.dominant_node_type else None,
            dominant_source_type=s.dominant_source_type,
        )
        for s in summaries
    ]
    rows.sort(key=lambda r: r.member_count, reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return rows


async def list_recent_reports(
    writer: RunReportWriter,
    report_type: str,
    *,
    limit: int = 50,
    verdict_filter: str | None = None,
    since: datetime | None = None,
) -> list[ReportRowView]:
    d: Path = writer.directory_for(report_type)
    if not d.exists():
        return []
    paths = sorted(
        (p for p in d.iterdir() if p.is_file() and p.suffix == ".json"),
        key=lambda p: p.stem,
        reverse=True,
    )
    rows: list[ReportRowView] = []
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        verdict = str(raw.get("verdict", "?"))
        if verdict_filter and verdict != verdict_filter:
            continue
        finished = raw.get("finished_at")
        if since is not None and finished:
            try:
                fts = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
                if fts.tzinfo is None:
                    fts = fts.replace(tzinfo=UTC)
                if fts < since:
                    continue
            except ValueError:
                pass
        rows.append(
            ReportRowView(
                run_id=str(raw.get("run_id", path.stem)),
                report_type=str(raw.get("report_type", report_type)),
                verdict=verdict,
                status=str(raw.get("status", "?")),
                duration_s=float(raw.get("duration_s") or 0.0),
            )
        )
        if len(rows) >= limit:
            break
    return rows


async def search_nodes(
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    *,
    query: str,
    limit: int = 20,
    node_type: NodeType | None = None,
    layer: Layer | None = None,
    cluster_id: str | None = None,
) -> list[NodeRowView]:
    q = query.strip()
    if not q:
        return []
    hits: list[NodeRowView] = []
    node = await store.get_node(q)
    if node is not None:
        hits.append(
            NodeRowView(
                id=node.id,
                label=node.label,
                node_type=node.node_type.value,
                layer=node.layer.value,
                confidence=node.scores.confidence,
            )
        )
    nodes = await _iter_nodes(store)
    for n in nodes:
        if hits and n.id == q:
            continue
        if node_type is not None and n.node_type != node_type:
            continue
        if layer is not None and n.layer != layer:
            continue
        if cluster_id is not None and n.cluster_id != cluster_id:
            continue
        if q.lower() in n.label.lower() or q == n.id:
            hits.append(
                NodeRowView(
                    id=n.id,
                    label=n.label,
                    node_type=n.node_type.value,
                    layer=n.layer.value,
                    confidence=n.scores.confidence,
                )
            )
    if len(hits) < min(3, limit) and q:
        emb = await embedder.embed(q)
        scored = await store.vector_search(emb, k=limit * 2, layer=layer)
        for sn in scored:
            n = sn.node
            if node_type is not None and n.node_type != node_type:
                continue
            if cluster_id is not None and n.cluster_id != cluster_id:
                continue
            if any(h.id == n.id for h in hits):
                continue
            hits.append(
                NodeRowView(
                    id=n.id,
                    label=n.label,
                    node_type=n.node_type.value,
                    layer=n.layer.value,
                    confidence=n.scores.confidence,
                )
            )
            if len(hits) >= limit:
                break
    return hits[:limit]


async def build_hover_lupe_payload(
    store: KnowledgeStore,
    *,
    center_id: str,
    min_weight: float = 0.15,
) -> dict[str, Any]:
    n = await store.get_node(center_id)
    if n is None:
        return {"nodes": [], "edges": []}
    hood = await store.get_neighborhood(center_id, depth=1, min_weight=min_weight)
    nodes_payload = []
    seen: set[str] = set()
    for node in hood.nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        if hasattr(node, "scores"):
            conf = float(node.scores.confidence)
        else:
            conf = float(getattr(node, "confidence", 0.0))
        nodes_payload.append(
            {
                "id": node.id,
                "label": node.label,
                "node_type": node.node_type.value,
                "confidence": conf,
            }
        )
    edges_payload = []
    for e in hood.edges:
        eid = getattr(e, "id", None) or getattr(e, "edge_id", "") or ""
        w = max(0.0, min(1.0, e.weight + getattr(e, "pheromone_delta", 0.0)))
        edges_payload.append(
            {
                "id": eid,
                "source": e.source_id,
                "target": e.target_id,
                "weight": w,
                "relation_type": e.relation_type,
            }
        )
    return {"nodes": nodes_payload, "edges": edges_payload}
