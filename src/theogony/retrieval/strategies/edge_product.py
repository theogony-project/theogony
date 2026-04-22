"""
``EdgeProductBreadthFirstStrategy`` — breadth-first walk with path-product
pruning (PHX-0056 / F3).

Vector-seed → BFS from each seed using ``get_neighborhood`` depth-1
steps, multiplying edge ``weight`` along each path. Optional
``min_path_product`` / ``top_n_paths`` from the budget (or
construction-time defaults) prune the walk. ``nodes_per_hop`` records
unique first-seen counts per hop (hop 0 = seeds).
"""

from __future__ import annotations

import asyncio
import time

from theogony.core.model import Layer
from theogony.core.store import KnowledgeStore, ScoredNode
from theogony.retrieval.multi_hop import MultiHopResult
from theogony.retrieval.strategies.budget import RetrievalBudget


class EdgeProductBreadthFirstStrategy:
    """Breadth-first expansion with running path-product."""

    name = "edge_product"

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        default_min_path_product: float | None = None,
        default_top_n_paths: int | None = None,
    ) -> None:
        self._store = store
        self._default_min_path_product = default_min_path_product
        self._default_top_n_paths = default_top_n_paths

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        started = time.perf_counter()

        min_path_product = (
            budget.min_path_product
            if budget.min_path_product is not None
            else self._default_min_path_product
        )
        top_n_paths = (
            budget.top_n_paths if budget.top_n_paths is not None else self._default_top_n_paths
        )

        seeds = await self._store.vector_search(embedding, k=budget.max_nodes, layer=layer)
        if not seeds:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return MultiHopResult(
                scored_nodes=[],
                seed_count=0,
                nodes_per_hop=[0],
                final_node_count=0,
                duplicates_removed=0,
                duration_ms=duration_ms,
            )

        first_hop: dict[str, int] = {}
        for sn in seeds:
            first_hop[sn.node.id] = 0

        hop_counts: list[int] = [len(seeds)]

        paths: list[tuple[tuple[str, ...], float]] = [((s.node.id,), 1.0) for s in seeds]

        max_hops = min(budget.hops, 4)

        for _depth in range(max_hops):
            hop_idx = _depth + 1
            if not paths:
                hop_counts.append(0)
                continue

            ends = [p[-1] for p, _ in paths]
            unique_ends = list(dict.fromkeys(ends))

            nbs = await asyncio.gather(
                *(
                    self._store.get_neighborhood(uid, depth=1, min_weight=budget.min_edge_weight)
                    for uid in unique_ends
                )
            )
            uid_to_nb = dict(zip(unique_ends, nbs, strict=True))

            new_paths: list[tuple[tuple[str, ...], float]] = []
            discovered_here = 0

            for path, prod in paths:
                last = path[-1]
                nb = uid_to_nb[last]
                for edge in nb.edges:
                    other = edge.target_id if edge.source_id == last else edge.source_id
                    if other in path:
                        continue
                    w = edge.weight
                    if w < budget.min_edge_weight:
                        continue
                    new_prod = prod * w
                    if min_path_product is not None and new_prod < min_path_product:
                        continue
                    if other not in first_hop and len(first_hop) >= budget.max_nodes:
                        continue
                    new_path = path + (other,)
                    new_paths.append((new_path, new_prod))
                    if other not in first_hop:
                        first_hop[other] = hop_idx
                        discovered_here += 1

            paths = new_paths
            hop_counts.append(discovered_here)

        if top_n_paths is not None and len(paths) > top_n_paths:
            paths.sort(key=lambda t: t[1], reverse=True)
            paths = paths[:top_n_paths]

        node_best: dict[str, float] = {}
        raw_slots = 0
        for path, prod in paths:
            raw_slots += len(path)
            for nid in path:
                prev = node_best.get(nid, -1.0)
                if prod > prev:
                    node_best[nid] = prod

        duplicates_removed = max(0, raw_slots - len(node_best))

        ids = sorted(node_best.keys(), key=lambda i: (-node_best[i], i))
        nodes = await asyncio.gather(*(self._store.get_node(i) for i in ids))
        scored_nodes: list[ScoredNode] = []
        for nid, node in zip(ids, nodes, strict=True):
            if node is None:
                continue
            scored_nodes.append(ScoredNode(node=node, score=node_best[nid]))

        scored_nodes = scored_nodes[: budget.max_nodes]

        duration_ms = int((time.perf_counter() - started) * 1000)
        seed_count = min(budget.max_nodes, len(seeds))

        return MultiHopResult(
            scored_nodes=scored_nodes,
            seed_count=seed_count,
            nodes_per_hop=hop_counts,
            final_node_count=len(scored_nodes),
            duplicates_removed=duplicates_removed,
            duration_ms=duration_ms,
        )


__all__ = ["EdgeProductBreadthFirstStrategy"]
