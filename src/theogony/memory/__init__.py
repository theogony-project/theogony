"""
Public memory-layer API (Plan §4.3; E8).

For Gen 1, the memory module exposes the read-side write-back loop
(:class:`RelevanceTracker`) — the OneirosWorker that owns the full
lifecycle (promote / degrade / vitality decay) lands as a separate
post-E8 etappe per the E8 brief's scope decision.
"""

from __future__ import annotations

from theogony.memory.relevance import DEFAULT_RELEVANCE_DELTA, RelevanceTracker


def __getattr__(name: str) -> object:
    """Lazy import for :class:`~theogony.memory.oneiros.OneirosWorker`.

    Eagerly importing it in this package ``__init__`` would execute
    ``oneiros.py`` on every ``from theogony.memory.tick_phase import …``,
    which pulls in ``curiosity`` tick phases and creates an import cycle
    with ``blind_spot_aggregator`` → ``clustering`` → ``memory`` (PHX-0058).
    """

    if name == "OneirosWorker":
        from theogony.memory.oneiros import OneirosWorker

        return OneirosWorker
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = ["DEFAULT_RELEVANCE_DELTA", "OneirosWorker", "RelevanceTracker"]
