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
from theogony.retrieval.pipeline import HIGH_CONFIDENCE_FLOOR, QueryPipeline, QueryResult
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
