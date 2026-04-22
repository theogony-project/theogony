"""Edge pheromone bump for cited paths (PHX-0057 Phase 1 / W2)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from theogony.core.store import KnowledgeStore

DEFAULT_EDGE_PHEROMONE_DELTA = 0.015


class EdgePheromoneTracker:
    """Apply the pheromone bump for cited edges."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        delta: float = DEFAULT_EDGE_PHEROMONE_DELTA,
    ) -> None:
        if not 0.0 <= delta <= 1.0:
            raise ValueError(f"delta must be in [0,1]; got {delta}")
        self._store = store
        self._delta = delta

    async def bump_all(self, edge_ids: Iterable[str]) -> None:
        """Bump every distinct edge id once (preserving first-seen order)."""
        seen: set[str] = set()
        ordered: list[str] = []
        for eid in edge_ids:
            if eid in seen:
                continue
            seen.add(eid)
            ordered.append(eid)
        if not ordered:
            return
        await self._store.batch_bump_edges(ordered, delta=self._delta, ts=datetime.now(UTC))


__all__ = ["DEFAULT_EDGE_PHEROMONE_DELTA", "EdgePheromoneTracker"]
