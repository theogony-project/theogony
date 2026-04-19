"""
ConstellationAssembler — turn a ``MultiHopResult`` into a slim ``Constellation``.

Plan §9.1, §2.6; E8 brief.

The assembler is pure store + DTO: it does not call the LLM and does
not embed the query (the pipeline does both). Its job is to:

1. Project each retrieved ``KnowledgeNode`` into the slim
   ``ConstellationNode`` (Plan §9.1: keep embeddings out of the
   synthesizer's context window).
2. Collect edges among the retrieved nodes via
   ``KnowledgeStore.get_neighborhood`` for each seed (depth=1
   suffices because multi_hop already discovered the broader
   topology). Dedupe by ``(source_id, target_id, relation_type)``.
3. Identify gaps (Plan §9.1: ``Constellation.gaps``):
     * ``"no_strong_match"`` — the top-1 node's similarity to the
       query embedding is below the strong-match threshold (0.3).

  PHX-0050 semantic note: the previous implementation also surfaced
  an ``"orphan_target:<id>"`` gap for any edge endpoint not in the
  retrieved set. The bulk ``get_edges_among`` Cypher only returns
  within-set edges by definition (``WHERE a.id IN $ids AND b.id
  IN $ids``), so the orphan-target gap kind is now structurally
  unreachable from this code path and the constant
  ``GAP_ORPHAN_PREFIX`` is preserved for future consumers (e.g. a
  separate diagnostic query) but no longer emitted by ``assemble``.
4. Populate ``suggested_sources`` from each node's ``source_ref``
   (deduped on ``(source_type, identifier)``).
5. Set ``path="fast"`` (Plan §9.1; ``"slow"`` is reserved for Gen 2).

Two gap kinds is a deliberate scope decision (E8 brief): we document
both in the assembler docstring so the synthesizer prompt and the
Reviewer agent can grep for them by exact tag.
"""

from __future__ import annotations

from theogony.config.logging import get_logger
from theogony.core.model import (
    Constellation,
    ConstellationEdge,
    ConstellationNode,
    SourceRef,
)
from theogony.core.store import KnowledgeStore
from theogony.retrieval.multi_hop import MultiHopResult

log = get_logger("retrieval.constellation")

#: Minimum cosine similarity to the top-1 node below which we record
#: a ``no_strong_match`` gap. 0.3 mirrors the Plan §2.6 ``min_weight``
#: floor — both express "below this, the signal is too weak to trust".
STRONG_MATCH_THRESHOLD = 0.3

#: Tag prefix for the orphan-target gap. The full tag is
#: ``"orphan_target:<node_id>"`` so the Reviewer agent can extract
#: the offending id with a single regex.
GAP_ORPHAN_PREFIX = "orphan_target:"

#: Tag for the no-strong-match gap.
GAP_NO_STRONG_MATCH = "no_strong_match"


class ConstellationAssembler:
    """Materialise a ``Constellation`` from a ``MultiHopResult``."""

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    async def assemble(
        self,
        query: str,
        retrieval_result: MultiHopResult,
        query_embedding: list[float] | None = None,
    ) -> Constellation:
        """Build the slim constellation. See module docstring for steps.

        ``query_embedding`` is needed for the ``no_strong_match`` gap
        check; pass ``None`` if you want to skip that gap entirely
        (the orphan-target gap is always evaluated since edges already
        carry the necessary information).
        """
        # 1. Slim nodes; preserve retrieval order (the multi_hop result is
        #    already ranked by score).
        retrieved_nodes = [s.node for s in retrieval_result.scored_nodes]
        constellation_nodes = [ConstellationNode.from_knowledge_node(n) for n in retrieved_nodes]
        retrieved_ids = {n.id for n in constellation_nodes}

        # 2. Edges via depth-1 neighbourhood probes per retrieved node.
        #    Multi-hop already expanded; depth-1 here just collects edges
        #    *between* the retrieved set in **one** store round-trip.
        #    PHX-0050: the previous implementation looped k get_neighborhood
        #    calls (k=10 round-trips per assemble), throwing away most of
        #    each neighbourhood through the (source_id, target_id,
        #    relation_type) dedup. The bulk get_edges_among Cypher runs a
        #    single MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids
        #    on the production Neo4j backend — same answer, one round-trip,
        #    range-index-served on both endpoint id lookups (Plan §3.1a).
        seen_edge_keys: set[tuple[str, str, str]] = set()
        constellation_edges: list[ConstellationEdge] = []
        endpoint_ids: set[str] = set()
        try:
            full_edges = await self._store.get_edges_among(
                [n.id for n in retrieved_nodes], min_weight=0.0
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("get_edges_among failed: %s — assembling without edges", exc)
            full_edges = []
        for edge in full_edges:
            key = (edge.source_id, edge.target_id, edge.relation_type)
            if key in seen_edge_keys:
                continue
            seen_edge_keys.add(key)
            constellation_edges.append(ConstellationEdge.from_knowledge_edge(edge))
            endpoint_ids.add(edge.source_id)
            endpoint_ids.add(edge.target_id)

        # 3. Gap detection.
        gaps: list[str] = []
        # 3a. Orphan-target gap: structurally unreachable under the
        #     PHX-0050 bulk-edges semantics — get_edges_among only
        #     returns within-set edges (WHERE a.id IN $ids AND
        #     b.id IN $ids), so endpoint_ids ⊆ retrieved_ids by
        #     definition. We compute the set difference anyway as a
        #     correctness check; a non-empty orphan set would mean
        #     the store violated the get_edges_among contract.
        orphans = sorted(endpoint_ids - retrieved_ids)
        for orphan in orphans:  # pragma: no cover - structurally unreachable
            gaps.append(f"{GAP_ORPHAN_PREFIX}{orphan}")
        # 3b. No-strong-match: only when we have an embedding and the
        #     top-1 retrieval score is below the threshold.
        if (
            query_embedding is not None
            and retrieval_result.scored_nodes
            and retrieval_result.scored_nodes[0].score < STRONG_MATCH_THRESHOLD
        ):
            gaps.append(GAP_NO_STRONG_MATCH)

        # 4. Suggested sources, deduped on (source_type, identifier).
        #    identifier is Optional on SourceRef; we coerce to "" so the
        #    dedupe key is always hashable and a None-identifier source
        #    is treated as a single anonymous source per source_type
        #    (rather than collapsing distinct types together).
        suggested_sources: list[SourceRef] = []
        seen_source_keys: set[tuple[str, str]] = set()
        for node in retrieved_nodes:
            sr = node.source_ref
            source_key = (sr.source_type, sr.identifier or "")
            if source_key in seen_source_keys:
                continue
            seen_source_keys.add(source_key)
            suggested_sources.append(sr)

        # 5. Always fast path in Gen 1.
        return Constellation(
            query=query,
            nodes=constellation_nodes,
            edges=constellation_edges,
            suggested_sources=suggested_sources,
            gaps=gaps,
            path="fast",
        )


__all__ = [
    "GAP_NO_STRONG_MATCH",
    "GAP_ORPHAN_PREFIX",
    "STRONG_MATCH_THRESHOLD",
    "ConstellationAssembler",
]
