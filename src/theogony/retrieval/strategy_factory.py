"""
Construction helpers for :class:`~theogony.retrieval.strategies.protocol.RetrievalStrategy`.

Keeps strategy dispatch out of FastAPI and the CLI so both call the same
factory (PHX-0056 Phase 1 / F3).
"""

from __future__ import annotations

from typing import Literal

from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.retrieval.strategies.cluster_narrowing import ClusterNarrowingRetrievalStrategy
from theogony.retrieval.strategies.edge_product import EdgeProductBreadthFirstStrategy
from theogony.retrieval.strategies.fixed_depth import FixedDepthStrategy
from theogony.retrieval.strategies.protocol import RetrievalStrategy

StrategyName = Literal["fixed_depth", "edge_product", "cluster_narrow"]


def build_retrieval_strategy(
    store: KnowledgeStore,
    settings: Settings,
    *,
    override: StrategyName | None = None,
) -> RetrievalStrategy:
    """Instantiate the active strategy from settings, optionally overridden by name."""
    name = override if override is not None else settings.retrieval.strategy
    if name == "fixed_depth":
        return FixedDepthStrategy(store)
    if name == "edge_product":
        return EdgeProductBreadthFirstStrategy(
            store,
            default_min_path_product=settings.retrieval.edge_product_min_path_product,
            default_top_n_paths=settings.retrieval.edge_product_top_n_paths,
        )
    if name == "cluster_narrow":
        inner_name = settings.retrieval.cluster_narrow_inner_strategy
        if inner_name == "edge_product":
            inner: RetrievalStrategy = EdgeProductBreadthFirstStrategy(
                store,
                default_min_path_product=settings.retrieval.edge_product_min_path_product,
                default_top_n_paths=settings.retrieval.edge_product_top_n_paths,
            )
        else:
            inner = FixedDepthStrategy(store)
        return ClusterNarrowingRetrievalStrategy(
            store,
            top_n_clusters=settings.retrieval.cluster_narrow_top_n_clusters,
            inner_strategy=inner,
        )
    raise ValueError(f"unknown retrieval strategy: {name!r}")


__all__ = ["StrategyName", "build_retrieval_strategy"]
