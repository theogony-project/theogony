"""OneirosWorker tick phase: periodic full-store re-clustering (PHX-0060)."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from theogony.clustering.hdbscan_strategy import HDBSCANStrategy
from theogony.clustering.identity import ClusterIdentityResult, map_cluster_identity
from theogony.clustering.kmeans_strategy import KMeansStrategy
from theogony.clustering.protocol import ClusteringResult, ClusteringStrategy
from theogony.config.logging import get_logger
from theogony.config.settings import ClusteringSettings
from theogony.core.model import ClusterSummary, KnowledgeNode, Layer
from theogony.stores.memory import InMemoryKnowledgeStore
from theogony.stores.neo4j_store import Neo4jKnowledgeStore

if TYPE_CHECKING:
    from theogony.core.store import KnowledgeStore
    from theogony.memory.tick_phase import TickContext
    from theogony.reporting.writer import RunReportWriter

log = get_logger("clustering.recluster")


@dataclass(frozen=True)
class ClusteringRunReportPayload:
    """Stashed on ``TickContext.extras`` for the worker to persist."""

    algorithm: str
    nodes_processed: int
    clusters_formed: int
    clusters_inherited: int
    clusters_minted: int
    mean_cluster_size: float
    cluster_size_distribution: list[int]
    noise_node_count: int
    runtime_ms: int


class ReclusterPhase:
    name = "recluster"

    async def run(self, ctx: TickContext) -> None:
        writer = ctx.writer
        if writer is None:
            log.warning("recluster: no RunReportWriter on TickContext; skipping")
            return
        cfg = ctx.app_settings.clustering
        if not _should_recluster(ctx, writer, cfg):
            return

        all_nodes = await _collect_all_embedded_nodes(ctx.store)
        if len(all_nodes) < cfg.min_corpus_size:
            log.info("recluster: corpus below min_corpus_size; skipping")
            return

        node_ids = [n.id for n in all_nodes]
        embeddings = [n.embedding for n in all_nodes]
        emb_by_id = {n.id: n.embedding for n in all_nodes}
        nodes_by_id = {n.id: n for n in all_nodes}

        strategy = _select_strategy(cfg, len(all_nodes))
        result = await asyncio.to_thread(strategy.cluster, node_ids, embeddings)

        previous = await ctx.store.list_clusters()
        previous_members = await _materialise_previous_members(ctx.store, previous)
        identity = map_cluster_identity(
            new_assignments=result.assignments,
            new_centroids=result.centroids,
            previous_summaries=previous,
            previous_members=previous_members,
            jaccard_threshold=cfg.identity_jaccard_threshold,
            nodes_by_id=nodes_by_id,
        )

        _assign_noise_to_nearest_clusters(
            result=result,
            identity_assignments=identity.assignments,
            emb_by_id=emb_by_id,
            new_assignments=result.assignments,
        )

        await _persist_assignments(ctx.store, identity.assignments, identity.summaries)
        await _refresh_cross_cluster_flags(ctx.store)

        ctx.extras["cluster_index_refresh"] = identity.summaries
        ctx.extras["clustering_run"] = ClusteringRunReportPayload(
            algorithm=result.algorithm,
            nodes_processed=len(all_nodes),
            clusters_formed=len(identity.summaries),
            clusters_inherited=identity.inherited_count,
            clusters_minted=identity.minted_count,
            mean_cluster_size=_mean_cluster_size(identity),
            cluster_size_distribution=_size_distribution(identity),
            noise_node_count=identity.noise_count,
            runtime_ms=result.runtime_ms,
        )


def _should_recluster(ctx: TickContext, writer: RunReportWriter, cfg: ClusteringSettings) -> bool:
    if ctx.extras.get("recluster_force"):
        return True
    from theogony.reporting.models import ClusteringRunReport

    last = writer.most_recent("clustering")
    if last is None:
        return True
    if not isinstance(last, ClusteringRunReport):
        return True
    elapsed_days = (ctx.started_at - last.started_at).total_seconds() / 86400.0
    return elapsed_days >= cfg.recluster_interval_days


async def _collect_all_embedded_nodes(store: KnowledgeStore) -> list[KnowledgeNode]:
    out: list[KnowledgeNode] = []
    for layer in (Layer.EPHEMERA, Layer.MNEME):
        async for node in store.export_layer(layer):
            if node.embedding:
                out.append(node)
    return out


def _select_strategy(cfg: ClusteringSettings, n_nodes: int) -> ClusteringStrategy:
    if cfg.algorithm == "kmeans":
        k = max(cfg.min_cluster_size, int(math.sqrt(n_nodes)))
        return KMeansStrategy(n_clusters=min(k, n_nodes))
    if cfg.algorithm == "hdbscan":
        return HDBSCANStrategy(min_cluster_size=cfg.min_cluster_size)
    # auto
    if n_nodes >= cfg.corpus_size_kmeans_threshold:
        k = max(cfg.min_cluster_size, int(math.sqrt(n_nodes)))
        return KMeansStrategy(n_clusters=min(k, n_nodes))
    return HDBSCANStrategy(min_cluster_size=cfg.min_cluster_size)


async def _materialise_previous_members(
    store: KnowledgeStore,
    previous: list[ClusterSummary],
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for s in previous:
        members: set[str] = set()
        async for nid in store.get_cluster_members(s.cluster_id):
            members.add(nid)
        out[s.cluster_id] = members
    return out


def _local_idx_to_cluster_id(
    new_assignments: dict[str, int],
    stable_assignments: dict[str, str | None],
) -> dict[int, str]:
    m: dict[int, str] = {}
    for nid, loc in new_assignments.items():
        if loc == -1:
            continue
        cid = stable_assignments.get(nid)
        if cid is not None:
            m[loc] = cid
    return m


def _assign_noise_to_nearest_clusters(
    *,
    result: ClusteringResult,
    identity_assignments: dict[str, str | None],
    emb_by_id: dict[str, list[float]],
    new_assignments: dict[str, int],
) -> None:
    """Mutates ``identity_assignments`` for HDBSCAN noise points."""
    if not result.centroids:
        return
    local_to_cid = _local_idx_to_cluster_id(new_assignments, identity_assignments)
    if not local_to_cid:
        return
    centroids = {k: v for k, v in result.centroids.items() if k != -1}
    for nid, loc in new_assignments.items():
        if loc != -1:
            continue
        emb = emb_by_id.get(nid)
        if not emb:
            continue
        u = _unit_vector(emb)
        best_li: int | None = None
        best_score = -2.0
        for li, cvec in centroids.items():
            score = _dot(u, _unit_vector(cvec))
            if score > best_score:
                best_score = score
                best_li = li
        if best_li is not None and best_li in local_to_cid:
            identity_assignments[nid] = local_to_cid[best_li]


def _unit_vector(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        return list(v)
    return [x / n for x in v]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def _persist_assignments(
    store: KnowledgeStore,
    assignments: dict[str, str | None],
    summaries: list[ClusterSummary],
) -> None:
    label_by_cluster = {s.cluster_id: s.cluster_label for s in summaries}
    for nid, cid in assignments.items():
        if cid is None:
            await store.assign_cluster(nid, None, cluster_label=None)
        else:
            await store.assign_cluster(
                nid,
                cid,
                cluster_label=label_by_cluster.get(cid),
            )


async def _refresh_cross_cluster_flags(store: KnowledgeStore) -> None:
    if isinstance(store, InMemoryKnowledgeStore):
        await _refresh_cross_cluster_memory(store)
    elif isinstance(store, Neo4jKnowledgeStore):
        await store.refresh_cross_cluster_edge_flags()
    else:
        log.warning(
            "recluster: unknown store type for cross_cluster refresh: %s",
            type(store).__name__,
        )


async def _refresh_cross_cluster_memory(store: InMemoryKnowledgeStore) -> None:
    for edge in store._edges.values():  # noqa: SLF001 — store-internal sweep
        s = store._nodes.get(edge.source_id)  # noqa: SLF001
        t = store._nodes.get(edge.target_id)  # noqa: SLF001
        sc = s.cluster_id if s is not None else None
        tc = t.cluster_id if t is not None else None
        edge.properties["cross_cluster"] = bool(sc and tc and sc != tc)


def _mean_cluster_size(identity: ClusterIdentityResult) -> float:
    if not identity.summaries:
        return 0.0
    total = sum(s.member_count for s in identity.summaries)
    return float(total) / float(len(identity.summaries))


def _size_distribution(identity: ClusterIdentityResult) -> list[int]:
    sizes = sorted((s.member_count for s in identity.summaries), reverse=True)
    return list(sizes)


__all__ = ["ClusteringRunReportPayload", "ReclusterPhase"]
