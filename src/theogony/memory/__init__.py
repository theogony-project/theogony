"""
Public memory-layer API (Plan §4.3; E8).

For Gen 1, the memory module exposes the read-side write-back loop
(:class:`RelevanceTracker`) — the OneirosWorker that owns the full
lifecycle (promote / degrade / vitality decay) lands as a separate
post-E8 etappe per the E8 brief's scope decision.
"""

from __future__ import annotations

from theogony.memory.oneiros import OneirosWorker
from theogony.memory.relevance import DEFAULT_RELEVANCE_DELTA, RelevanceTracker

__all__ = ["DEFAULT_RELEVANCE_DELTA", "OneirosWorker", "RelevanceTracker"]
