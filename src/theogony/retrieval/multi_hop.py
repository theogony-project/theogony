"""
MultiHopRetriever — thin orchestration over ``KnowledgeStore.multi_hop_search``.

Plan §2.6, §4.2; E8 brief.

The store does the actual work (vector seed + graph expansion + dedupe
+ rank). This component owns the *parameter discipline* (k, hops,
min_weight, layer) and the *observation* it emits onto the
``QueryRunReport`` via ``MultiHopBreakdown``.

Two reasons for the wrapper rather than calling ``store.multi_hop_search``
directly from the pipeline:

1. **Defaults belong with the consumer, not the protocol.** The
   protocol takes whatever the caller passes; the retriever pins the
   Plan §4.2 defaults (``k=10, hops=2``) so the pipeline does not
   accidentally drift from spec.
2. **Reporting boundary.** ``MultiHopResult`` is the typed
   carrier for the per-hop instrumentation the pipeline writes onto
   ``QueryRunReport.multi_hop``. Computing it here keeps the pipeline
   focused on orchestration.

``MultiHopResult`` lives in this module — it is a pipeline-internal
observation, not a domain object.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.logging import get_logger
from theogony.core.model import Layer
from theogony.core.store import KnowledgeStore, ScoredNode

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
    nodes_per_hop: list[int] = Field(default_factory=list)
    duplicates_removed: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class MultiHopRetriever:
    """Thin async wrapper around the store's combined retrieval call.

    Pure orchestration; does not embed the query (the pipeline handles
    that), does not assemble the constellation (the assembler does).
    """

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

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

        ``nodes_per_hop`` and ``duplicates_removed`` are best-effort
        observations: the protocol does not give us per-hop visibility
        into the store's expansion (it returns the deduped, ranked
        list directly), so we approximate by capturing the seed count
        (top-``k`` vector hits) and the final dedupe-already-applied
        count. A future PHX may expose richer instrumentation; today
        the report has enough to detect "no seeds" and "expansion
        moved zero new nodes" failure modes.
        """
        if k <= 0:
            raise ValueError(f"k must be positive; got {k}")
        if hops < 0:
            raise ValueError(f"hops must be non-negative; got {hops}")
        if not 0.0 <= min_weight <= 1.0:
            raise ValueError(f"min_weight must be in [0,1]; got {min_weight}")

        started = time.perf_counter()
        scored = await self._store.multi_hop_search(
            embedding=query_embedding,
            k=k,
            hops=hops,
            min_weight=min_weight,
            layer=layer,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        # The store's multi_hop already deduplicates internally. We
        # record the seed count as min(k, len(scored)) because the
        # store guarantees the top-k vector hits are present (or fewer
        # if the corpus has < k embedded nodes). nodes_per_hop is a
        # single-element list with the final count — truthful within
        # the protocol's resolution.
        seed_count = min(k, len(scored))
        nodes_per_hop = [len(scored)]

        log.debug(
            "multi_hop k=%d hops=%d min_weight=%.2f layer=%s -> %d nodes in %d ms",
            k,
            hops,
            min_weight,
            layer.value if layer is not None else "any",
            len(scored),
            duration_ms,
        )

        return MultiHopResult(
            scored_nodes=scored,
            seed_count=seed_count,
            nodes_per_hop=nodes_per_hop,
            duplicates_removed=0,
            duration_ms=duration_ms,
        )


__all__ = ["MultiHopResult", "MultiHopRetriever"]
