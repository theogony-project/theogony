"""
Public retrieval API (Plan §2.6, §4.2; E8).

Re-exports the four E8 components plus the report-ready DTOs callers
need to compose their own pipelines (the CLI in E9 will).
"""

from __future__ import annotations

from theogony.retrieval.constellation import (
    GAP_NO_STRONG_MATCH,
    GAP_ORPHAN_PREFIX,
    STRONG_MATCH_THRESHOLD,
    ConstellationAssembler,
)
from theogony.retrieval.multi_hop import MultiHopResult, MultiHopRetriever
from theogony.retrieval.synthesize import Answer, AnswerSynthesizer

__all__ = [
    "GAP_NO_STRONG_MATCH",
    "GAP_ORPHAN_PREFIX",
    "HIGH_CONFIDENCE_FLOOR",
    "STRONG_MATCH_THRESHOLD",
    "Answer",
    "AnswerSynthesizer",
    "ConstellationAssembler",
    "MultiHopResult",
    "MultiHopRetriever",
    "QueryPipeline",
    "QueryResult",
]


def __getattr__(name: str) -> object:
    """Lazy exports from ``pipeline`` — avoids cycles with ``curiosity.stub_detector``."""

    if name == "QueryPipeline":
        from theogony.retrieval.pipeline import QueryPipeline

        return QueryPipeline
    if name == "QueryResult":
        from theogony.retrieval.pipeline import QueryResult

        return QueryResult
    if name == "HIGH_CONFIDENCE_FLOOR":
        from theogony.retrieval.pipeline import HIGH_CONFIDENCE_FLOOR

        return HIGH_CONFIDENCE_FLOOR
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
