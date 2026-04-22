"""Region descriptor for blind-spot aggregation (PHX-0058 Phase 1 / W3)."""

from __future__ import annotations

from theogony.core.model import Constellation, NodeType
from theogony.reporting.models import RegionDescriptor
from theogony.retrieval.multi_hop import MultiHopResult


def compute_region_descriptor(
    *,
    query_embedding: list[float],
    constellation: Constellation,
    retrieval_result: MultiHopResult,
) -> RegionDescriptor:
    seed_count = retrieval_result.seed_count
    nodes = constellation.nodes

    cluster_counts: dict[str, int] = {}
    for n in nodes:
        cid = n.cluster_id
        if cid:
            cluster_counts[cid] = cluster_counts.get(cid, 0) + 1
    dominant_cluster_id = (
        max(cluster_counts, key=lambda k: cluster_counts[k]) if cluster_counts else None
    )

    type_counts: dict[NodeType, int] = {}
    for n in nodes:
        type_counts[n.node_type] = type_counts.get(n.node_type, 0) + 1
    dominant_node_type = max(type_counts, key=lambda k: type_counts[k]) if type_counts else None

    mean_conf = sum(n.confidence for n in nodes) / max(1, len(nodes)) if nodes else 0.0

    return RegionDescriptor(
        query_embedding=list(query_embedding),
        seed_node_count=seed_count,
        dominant_cluster_id=dominant_cluster_id,
        dominant_node_type=dominant_node_type,
        mean_seed_confidence=mean_conf,
    )


__all__ = ["compute_region_descriptor"]
