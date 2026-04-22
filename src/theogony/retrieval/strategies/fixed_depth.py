"""
``FixedDepthStrategy`` — Plan §4.2 default retrieval (PHX-0056 / F3).

Delegates to :meth:`theogony.core.store.KnowledgeStore.multi_hop_search`
with the budget's ``max_nodes`` / ``hops`` / ``min_edge_weight``. This is
the byte-for-byte successor to the pre-F3 ``MultiHopRetriever.retrieve``
body (``nodes_per_hop`` stays ``None`` per PHX-0051).
"""

from __future__ import annotations

import time

from theogony.core.model import Layer
from theogony.core.store import KnowledgeStore
from theogony.retrieval.multi_hop import MultiHopResult
from theogony.retrieval.strategies.budget import RetrievalBudget


class FixedDepthStrategy:
    """Default retrieval: vector seed + fixed-depth hop expansion."""

    name = "fixed_depth"

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        started = time.perf_counter()
        scored = await self._store.multi_hop_search(
            embedding=embedding,
            k=budget.max_nodes,
            hops=budget.hops,
            min_weight=budget.min_edge_weight,
            layer=layer,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        seed_count = min(budget.max_nodes, len(scored))
        return MultiHopResult(
            scored_nodes=scored,
            seed_count=seed_count,
            nodes_per_hop=None,
            final_node_count=len(scored),
            duplicates_removed=0,
            duration_ms=duration_ms,
        )


__all__ = ["FixedDepthStrategy"]
