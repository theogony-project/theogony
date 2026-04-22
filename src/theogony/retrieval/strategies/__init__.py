"""
Retrieval strategies (PHX-0056 Phase 1 / F3).

``FixedDepthStrategy`` / ``EdgeProductBreadthFirstStrategy`` are loaded
lazily so :mod:`theogony.retrieval.multi_hop` can import
:class:`RetrievalBudget` without import cycles.
"""

from __future__ import annotations

from typing import Any

from theogony.retrieval.strategies.budget import RetrievalBudget
from theogony.retrieval.strategies.protocol import RetrievalStrategy

__all__ = [
    "EdgeProductBreadthFirstStrategy",
    "FixedDepthStrategy",
    "RetrievalBudget",
    "RetrievalStrategy",
]


def __getattr__(name: str) -> Any:
    if name == "FixedDepthStrategy":
        from theogony.retrieval.strategies.fixed_depth import FixedDepthStrategy

        return FixedDepthStrategy
    if name == "EdgeProductBreadthFirstStrategy":
        from theogony.retrieval.strategies.edge_product import (
            EdgeProductBreadthFirstStrategy,
        )

        return EdgeProductBreadthFirstStrategy
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
