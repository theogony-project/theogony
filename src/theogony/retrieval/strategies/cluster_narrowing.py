"""Top-N centroid narrowing before inner retrieval (PHX-0060 Phase 1)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from theogony.core.model import ClusterSummary
from theogony.retrieval.multi_hop import MultiHopResult
from theogony.retrieval.strategies.budget import RetrievalBudget
from theogony.retrieval.strategies.fixed_depth import FixedDepthStrategy
from theogony.retrieval.strategies.protocol import RetrievalStrategy

if TYPE_CHECKING:
    from theogony.core.model import Layer
    from theogony.core.store import KnowledgeStore


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        return list(v)
    return [x / n for x in v]


def _rank_clusters_by_similarity(
    embedding: list[float],
    summaries: list[ClusterSummary],
) -> list[ClusterSummary]:
    u = _unit(embedding)

    def score(s: ClusterSummary) -> float:
        if not s.centroid:
            return -1.0
        cv = _unit(s.centroid)
        return sum(a * b for a, b in zip(u, cv, strict=True))

    return sorted(summaries, key=score, reverse=True)


class ClusterNarrowingRetrievalStrategy:
    name = "cluster_narrow"

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        top_n_clusters: int = 3,
        inner_strategy: RetrievalStrategy | None = None,
    ) -> None:
        self._store = store
        self._top_n_clusters = top_n_clusters
        self._inner = inner_strategy or FixedDepthStrategy(store)

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        summaries = await self._store.list_clusters()
        if not summaries:
            return await self._inner.retrieve(embedding, budget=budget, layer=layer)

        ranked = _rank_clusters_by_similarity(embedding, summaries)
        top = ranked[: self._top_n_clusters]

        candidate_ids: set[str] = set()
        for summary in top:
            async for node_id in self._store.get_cluster_members(summary.cluster_id):
                candidate_ids.add(node_id)

        coverage_floor = max(budget.max_nodes, 20)
        if len(candidate_ids) < coverage_floor:
            return await self._inner.retrieve(embedding, budget=budget, layer=layer)

        inner_result = await self._inner.retrieve(embedding, budget=budget, layer=layer)
        filtered = [
            scored for scored in inner_result.scored_nodes if scored.node.id in candidate_ids
        ]
        return MultiHopResult(
            scored_nodes=filtered,
            seed_count=inner_result.seed_count,
            nodes_per_hop=inner_result.nodes_per_hop,
            final_node_count=len(filtered),
            duplicates_removed=inner_result.duplicates_removed,
            duration_ms=inner_result.duration_ms,
        )
