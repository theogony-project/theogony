"""
Multi-hop retrieval facade and ``MultiHopResult`` (Plan §2.6, §4.2; E8; F3).

:class:`MultiHopRetriever` validates legacy parameters (``k``, ``hops``,
``min_weight``) and dispatches to a
:class:`~theogony.retrieval.strategies.protocol.RetrievalStrategy` via
:class:`~theogony.retrieval.strategies.budget.RetrievalBudget`. The
default strategy is
:class:`~theogony.retrieval.strategies.fixed_depth.FixedDepthStrategy`,
which delegates to ``KnowledgeStore.multi_hop_search`` — preserving
pre-F3 behaviour.

``MultiHopResult`` is the typed carrier for ``QueryRunReport.multi_hop``;
it lives here as a pipeline-level observation, not a domain object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.logging import get_logger
from theogony.core.model import Layer
from theogony.core.store import KnowledgeStore, ScoredNode
from theogony.retrieval.strategies.budget import RetrievalBudget

if TYPE_CHECKING:
    from theogony.retrieval.strategies.protocol import RetrievalStrategy

log = get_logger("retrieval.multi_hop")


class MultiHopResult(BaseModel):
    """Output of one ``MultiHopRetriever.retrieve`` call.

    Maps cleanly onto ``MultiHopBreakdown`` for the report. Lives in
    this module by design — not in ``core/model.py`` because the
    Chronik does not surface it; it is a pipeline-level observation.
    """

    model_config = ConfigDict(extra="forbid")

    scored_nodes: list[ScoredNode] = Field(default_factory=list)
    seed_count: int = Field(default=0, ge=0)
    # PHX-0051: ``None`` signals "store does not expose per-hop visibility";
    # ``final_node_count`` carries the truthful deduped result count.
    nodes_per_hop: list[int] | None = Field(default=None)
    final_node_count: int = Field(default=0, ge=0)
    duplicates_removed: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class MultiHopRetriever:
    """Thin async facade over a :class:`~theogony.retrieval.strategies.protocol.RetrievalStrategy`.

    Preserved for callers that constructed the original ``MultiHopRetriever``
    shape directly. The default strategy is :class:`FixedDepthStrategy`,
    which preserves Plan §4.2 behaviour. New code may pass an explicit
    strategy or build one via :func:`theogony.retrieval.strategy_factory.build_retrieval_strategy`.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        strategy: RetrievalStrategy | None = None,
    ) -> None:
        self._store = store
        if strategy is None:
            from theogony.retrieval.strategies.fixed_depth import FixedDepthStrategy

            strategy = FixedDepthStrategy(store)
        self._strategy = strategy

    @property
    def store(self) -> KnowledgeStore:
        return self._store

    async def retrieve(
        self,
        query_embedding: list[float],
        *,
        k: int = 10,
        hops: int = 2,
        min_weight: float = 0.3,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        """Run multi-hop retrieval and emit observations.

        Plan §4.2 defaults: ``k=10, hops=2``. Plan §2.6 floor:
        ``min_weight=0.3`` — do not lower without an explicit Plan
        amendment (low-weight edges become noisy beyond this floor).

        PHX-0051 schema choice (Option A): the protocol does not
        expose per-hop visibility, so ``nodes_per_hop`` is left
        ``None`` (the truthful "store cannot tell us" signal) and the
        always-populated ``final_node_count`` carries the deduped
        result count. A future per-hop-aware retriever can fill
        ``nodes_per_hop`` with the real list without touching either
        the schema or downstream consumers.
        """
        if k <= 0:
            raise ValueError(f"k must be positive; got {k}")
        if hops < 0:
            raise ValueError(f"hops must be non-negative; got {hops}")
        if not 0.0 <= min_weight <= 1.0:
            raise ValueError(f"min_weight must be in [0,1]; got {min_weight}")

        budget = RetrievalBudget(
            max_nodes=k,
            hops=hops,
            min_edge_weight=min_weight,
        )
        result = await self._strategy.retrieve(
            query_embedding, budget=budget, layer=layer
        )

        log.debug(
            "multi_hop k=%d hops=%d min_weight=%.2f layer=%s -> %d nodes in %d ms",
            k,
            hops,
            min_weight,
            layer.value if layer is not None else "any",
            result.final_node_count,
            result.duration_ms,
        )

        return result


__all__ = ["MultiHopResult", "MultiHopRetriever"]
