"""
``RetrievalBudget`` — per-call envelope for :class:`RetrievalStrategy`.

Every strategy **must** honour ``max_nodes`` and ``min_edge_weight``.
Other fields are hints; strategies **should** ignore fields they do
not understand and **must not** silently exceed explicit caps.

Field ownership:

- ``hops`` — honoured by :class:`FixedDepthStrategy` and
  :class:`EdgeProductBreadthFirstStrategy` (max graph depth, capped at 4).
- ``min_path_product``, ``top_n_paths`` — honoured by
  ``EdgeProductBreadthFirstStrategy`` only in F3.
- ``pheromone_mode`` — reserved for PHX-0057 (behaviour ships later).
- ``token_cap``, ``wall_clock_ms_cap`` — reserved for PHX-0056 Phase 2
  ``LLMHeuristicGuided``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetrievalBudget(BaseModel):
    """Per-call resource and parameter envelope for a RetrievalStrategy."""

    model_config = ConfigDict(extra="forbid")

    max_nodes: int = Field(default=10, ge=1, le=200)
    min_edge_weight: float = Field(default=0.3, ge=0.0, le=1.0)

    hops: int = Field(default=2, ge=0, le=4)

    min_path_product: float | None = Field(default=None, ge=0.0, le=1.0)
    top_n_paths: int | None = Field(default=None, ge=1, le=200)

    pheromone_mode: Literal["follow", "ignore", "invert"] = "follow"

    token_cap: int | None = Field(default=None, ge=1)
    wall_clock_ms_cap: int | None = Field(default=None, ge=1)


__all__ = ["RetrievalBudget"]
