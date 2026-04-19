"""
RelevanceTracker — post-answer "the user found this useful" write-back.

Plan §4.3; E8 brief.

Bridges *retrieval* (the user got an answer with citations) into
*memory lifecycle* (the chronicle remembers which nodes carry their
weight). For each cited node, ``bump`` advances ``last_accessed`` to
``now()`` and increments ``relevance`` by ``δ``, capped at 1.0. The
default δ is 0.05 — Plan §4.3's reference value.

Round-trip cost. The protocol's ``update_scores`` writes ``NodeScores``
fields (confidence/relevance/connectivity/freshness) but not
``last_accessed`` — that field lives on ``KnowledgeNode`` itself.
The tracker therefore reads the full node via ``get_node``, mutates
``last_accessed`` and ``scores.relevance`` in memory, and writes
back via ``upsert_node``. That is two Bolt round-trips per cited
node. Acceptable for Gen 1's ≤ 10-cited-nodes-per-answer cardinality;
PHX-0048 (atomic single-roundtrip update) supersedes this once
landed. The two-roundtrip pattern matches what the Neo4j store
already does internally for vitality denormalisation
(``Neo4jKnowledgeStore.update_scores`` re-reads first), so we are
not adding a new perf cliff — we are matching an existing one.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from theogony.config.logging import get_logger
from theogony.core.store import KnowledgeStore

log = get_logger("memory.relevance")

#: Plan §4.3 reference δ. Small on purpose — relevance accumulates
#: over many answers, so a tiny per-call bump keeps the lifecycle
#: signal stable without giving any single retrieval too much weight.
DEFAULT_RELEVANCE_DELTA = 0.05


class RelevanceTracker:
    """Apply the §4.3 write-back loop for cited nodes."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        relevance_delta: float = DEFAULT_RELEVANCE_DELTA,
    ) -> None:
        if not 0.0 <= relevance_delta <= 1.0:
            raise ValueError(f"relevance_delta must be in [0,1]; got {relevance_delta}")
        self._store = store
        self._delta = relevance_delta

    async def bump(self, node_id: str) -> None:
        """Bump ``last_accessed`` and ``relevance`` for one node.

        Idempotent in the sense that two consecutive bumps both move
        the node forward — we do not deduplicate inside ``bump``
        itself; ``bump_all`` does the dedupe across a single
        retrieval's cited list. A nonexistent node id is a silent
        no-op (matches ``KnowledgeStore.update_scores`` and
        ``KnowledgeStore.promote`` semantics).
        """
        node = await self._store.get_node(node_id)
        if node is None:
            log.debug("bump skipped: node %s not found", node_id)
            return
        node.last_accessed = datetime.now(UTC)
        new_relevance = min(1.0, node.scores.relevance + self._delta)
        node.scores.relevance = new_relevance
        await self._store.upsert_node(node)

    async def bump_all(self, node_ids: Iterable[str]) -> None:
        """Bump every distinct id once (preserving first-seen order).

        Dedupe is critical when a single answer cites the same node
        twice — without it we would double-count one citation. The
        order is preserved across the dedupe so the audit trail
        (read sequentially from logs) reflects the citation sequence.
        """
        seen: set[str] = set()
        ordered: list[str] = []
        for nid in node_ids:
            if nid in seen:
                continue
            seen.add(nid)
            ordered.append(nid)
        for nid in ordered:
            await self.bump(nid)


__all__ = ["DEFAULT_RELEVANCE_DELTA", "RelevanceTracker"]
