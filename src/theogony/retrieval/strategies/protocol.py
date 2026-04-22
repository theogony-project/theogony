"""
``RetrievalStrategy`` Protocol (PHX-0056 Phase 1 / F3).

Strategies are the extension surface for multi-hop retrieval: each
implementation chooses how to turn a query embedding plus a
:class:`~theogony.retrieval.strategies.budget.RetrievalBudget` into a
:class:`~theogony.retrieval.multi_hop.MultiHopResult`. Downstream code
(:class:`~theogony.retrieval.pipeline.QueryPipeline`, reports) stays
unchanged.

Future tickets plug in here:

- PHX-0056 Phase 2 — ``VectorSimilarityBreadthFirst``, ``LLMHeuristicGuided``
- PHX-0057 — pheromone-aware behaviour via ``RetrievalBudget.pheromone_mode``
- PHX-0060 — ``ClusterNarrowingRetrievalStrategy``
- PHX-0061 — federation routing sits above strategies but shares the Protocol
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from theogony.core.model import Layer
from theogony.retrieval.strategies.budget import RetrievalBudget

if TYPE_CHECKING:
    from theogony.retrieval.multi_hop import MultiHopResult


@runtime_checkable
class RetrievalStrategy(Protocol):
    """One concrete retrieval strategy.

    Strategies receive a query embedding and a RetrievalBudget; they
    return a MultiHopResult. The store + the budget are the only
    dependencies — no LLM, no settings, no per-query state on the
    strategy itself. Implementations may carry construction-time
    configuration (e.g. an EdgeProductBreadthFirst's threshold); keep
    it on the instance, not on the call.
    """

    name: str

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult: ...


__all__ = ["RetrievalStrategy"]
