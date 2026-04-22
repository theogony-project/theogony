"""Stable cluster id mapping across re-cluster passes (PHX-0060 Phase 1)."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from theogony.core.model import ClusterSummary, KnowledgeNode, NodeType


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    u = a | b
    if not u:
        return 0.0
    return len(a & b) / len(u)


@dataclass
class ClusterIdentityResult:
    """Outcome of mapping a fresh clustering onto previous cluster ids."""

    summaries: list[ClusterSummary]
    assignments: dict[str, str | None]
    inherited_count: int
    minted_count: int
    noise_count: int


def map_cluster_identity(
    *,
    new_assignments: dict[str, int],
    new_centroids: dict[int, list[float]],
    previous_summaries: list[ClusterSummary],
    previous_members: dict[str, set[str]],
    jaccard_threshold: float,
    nodes_by_id: Mapping[str, KnowledgeNode],
) -> ClusterIdentityResult:
    """Greedy Jaccard matching; deterministic tie-break by ascending previous id."""
    # --- noise ---
    noise_nodes = {nid for nid, loc in new_assignments.items() if loc == -1}
    assignments: dict[str, str | None] = {nid: None for nid in noise_nodes}
    noise_count = len(noise_nodes)

    # --- group non-noise by local index ---
    by_local: dict[int, set[str]] = {}
    for nid, loc in new_assignments.items():
        if loc == -1:
            continue
        by_local.setdefault(loc, set()).add(nid)

    # stable ordering: size desc, then local index asc
    new_clusters_sorted = sorted(
        by_local.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )

    prev_by_id = {s.cluster_id: s for s in previous_summaries}
    claimed_prev: set[str] = set()
    inherited_count = 0
    minted_count = 0

    local_to_stable: dict[int, str] = {}
    local_to_label: dict[int, str | None] = {}

    for local_idx, members in new_clusters_sorted:
        best_prev: str | None = None
        candidates: list[tuple[float, str]] = []
        for prev_id, prev_set in previous_members.items():
            if prev_id in claimed_prev:
                continue
            j = _jaccard(members, prev_set)
            if j >= jaccard_threshold:
                candidates.append((j, prev_id))
        if candidates:
            candidates.sort(key=lambda t: (-t[0], t[1]))
            best_prev = candidates[0][1]
        if best_prev is not None:
            claimed_prev.add(best_prev)
            local_to_stable[local_idx] = best_prev
            prev = prev_by_id.get(best_prev)
            local_to_label[local_idx] = prev.cluster_label if prev is not None else None
            inherited_count += 1
        else:
            new_id = "cluster-" + uuid.uuid4().hex[:12]
            local_to_stable[local_idx] = new_id
            local_to_label[local_idx] = None
            minted_count += 1

    for nid, loc in new_assignments.items():
        if loc == -1:
            continue
        assignments[nid] = local_to_stable[loc]

    # --- summaries (one per formed cluster, sorted by cluster_id) ---
    summaries: list[ClusterSummary] = []
    for local_idx in sorted(local_to_stable.keys()):
        members = by_local[local_idx]
        cid = local_to_stable[local_idx]
        centroid = list(new_centroids.get(local_idx, []))
        types: list[NodeType] = []
        sources: list[str] = []
        for mid in members:
            node = nodes_by_id.get(mid)
            if node is None:
                continue
            types.append(node.node_type)
            sources.append(node.source_ref.source_type)
        dom_type: NodeType | None = None
        if types:
            dom_type = Counter(types).most_common(1)[0][0]
        dom_src: str | None = None
        if sources:
            dom_src = Counter(sources).most_common(1)[0][0]
        summaries.append(
            ClusterSummary(
                cluster_id=cid,
                cluster_label=local_to_label[local_idx],
                member_count=len(members),
                centroid=centroid,
                dominant_node_type=dom_type,
                dominant_source_type=dom_src,
                properties={},
            )
        )

    summaries.sort(key=lambda s: s.cluster_id)

    return ClusterIdentityResult(
        summaries=summaries,
        assignments=assignments,
        inherited_count=inherited_count,
        minted_count=minted_count,
        noise_count=noise_count,
    )
