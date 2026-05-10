"""
Typed retrieval result carrier for :class:`~theogony.retrieval.pipeline.QueryPipeline`.

Historically named ``MultiHop*``; retrieval is **spreading-activation** only.
The shape is preserved so :class:`~theogony.reporting.models.QueryRunReport`
and planners stay stable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from theogony.core.store import ScoredNode


class MultiHopResult(BaseModel):
    """Output of one retrieval call (spreading activation today).

    Maps onto ``MultiHopBreakdown`` for the report.
    """

    model_config = ConfigDict(extra="forbid")

    scored_nodes: list[ScoredNode] = Field(default_factory=list)
    seed_count: int = Field(default=0, ge=0)
    nodes_per_hop: list[int] | None = Field(default=None)
    final_node_count: int = Field(default=0, ge=0)
    duplicates_removed: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


__all__ = ["MultiHopResult"]
