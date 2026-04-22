"""Morpheus deterministic associator (PHX-0059 Phase 1 / W4)."""

from __future__ import annotations

from dataclasses import dataclass

from theogony.config.settings import MorpheusSettings
from theogony.core.model import EdgeType, KnowledgeEdge, KnowledgeNode, Layer
from theogony.core.store import KnowledgeStore


def _build_proposal(
    *,
    src: KnowledgeNode,
    tgt: KnowledgeNode,
    signal: str,
    signal_value: str,
    run_id: str,
) -> KnowledgeEdge:
    return KnowledgeEdge(
        source_id=src.id,
        target_id=tgt.id,
        relation_type="ASSOCIATED_WITH",
        weight=0.5,
        confidence=0.4,
        epistemic_type=EdgeType.INFERENCE,
        source_ref=None,
        evidence_span=None,
        properties={
            "proposed_by": "morpheus",
            "signal": signal,
            "signal_value": signal_value,
            "tick_run_id": run_id,
            "cross_cluster": src.cluster_id != tgt.cluster_id,
        },
    )


def _signal_rank(edge: KnowledgeEdge) -> tuple[float, float]:
    """Higher is better for dedupe (embedding beats co-occurrence on ties)."""
    sig = str(edge.properties.get("signal", ""))
    raw = edge.properties.get("signal_value", "")
    if sig == "embedding":
        try:
            return (2.0, float(raw))
        except (TypeError, ValueError):
            return (2.0, 0.0)
    if sig == "cooccurrence":
        return (1.0, 0.0)
    return (0.0, 0.0)


def _dedupe_pairs(edges: list[KnowledgeEdge]) -> list[KnowledgeEdge]:
    best: dict[tuple[str, str], KnowledgeEdge] = {}
    for e in edges:
        key = (e.source_id, e.target_id)
        cur = best.get(key)
        if cur is None or _signal_rank(e) > _signal_rank(cur):
            best[key] = e
    return list(best.values())


async def _direct_edge_exists(store: KnowledgeStore, a: str, b: str) -> bool:
    edges = await store.get_edges_among([a, b], min_weight=0.0)
    return any(
        (e.source_id == a and e.target_id == b) or (e.source_id == b and e.target_id == a)
        for e in edges
    )


@dataclass(frozen=True)
class AssociationProposal:
    """Output of one :meth:`MorpheusAssociator.propose_associations` call."""

    edges: list[KnowledgeEdge]
    candidates_considered: int
    candidates_with_proposals: int
    candidates_skipped_no_neighbors_in_band: int


class MorpheusAssociator:
    """Deterministic association proposals (PHX-0059 Phase 1)."""

    name = "morpheus"

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        cfg: MorpheusSettings,
    ) -> None:
        self._store = store
        self._cfg = cfg

    async def propose_associations(
        self,
        *,
        run_id: str,
    ) -> AssociationProposal:
        candidates = await self._store.list_low_connectivity_nodes(
            layer=Layer.EPHEMERA,
            max_edges=self._cfg.candidate_isolation_max_edges,
            batch_size=self._cfg.batch_size,
        )

        all_proposals: list[KnowledgeEdge] = []
        candidates_with = 0
        candidates_no_band = 0

        for cand in candidates:
            proposals_for_cand: list[KnowledgeEdge] = []

            if cand.embedding:
                excl = {cand.id}
                similar = await self._store.find_similar_nodes_in_band(
                    cand.embedding,
                    band_low=self._cfg.embedding_band_low,
                    band_high=self._cfg.embedding_band_high,
                    exclude_ids=excl,
                    top_k=self._cfg.proposals_per_node_cap,
                )
                for scored in similar:
                    if scored.node.id == cand.id:
                        continue
                    if (
                        self._cfg.cluster_scope == "within_only"
                        and scored.node.cluster_id != cand.cluster_id
                    ):
                        continue
                    if await _direct_edge_exists(self._store, cand.id, scored.node.id):
                        continue
                    proposals_for_cand.append(
                        _build_proposal(
                            src=cand,
                            tgt=scored.node,
                            signal="embedding",
                            signal_value=str(scored.score),
                            run_id=run_id,
                        )
                    )

            ident = cand.source_ref.identifier if cand.source_ref else None
            if ident:
                cooccurring = await self._store.list_nodes_by_source_identifier(
                    identifier=ident,
                    exclude_id=cand.id,
                )
                for other in cooccurring:
                    if other.id == cand.id:
                        continue
                    if (
                        self._cfg.cluster_scope == "within_only"
                        and other.cluster_id != cand.cluster_id
                    ):
                        continue
                    if await _direct_edge_exists(self._store, cand.id, other.id):
                        continue
                    proposals_for_cand.append(
                        _build_proposal(
                            src=cand,
                            tgt=other,
                            signal="cooccurrence",
                            signal_value=ident,
                            run_id=run_id,
                        )
                    )

            proposals_for_cand = _dedupe_pairs(proposals_for_cand)
            proposals_for_cand = proposals_for_cand[: self._cfg.proposals_per_node_cap]

            if proposals_for_cand:
                candidates_with += 1
                all_proposals.extend(proposals_for_cand)
            else:
                candidates_no_band += 1

        return AssociationProposal(
            edges=all_proposals,
            candidates_considered=len(candidates),
            candidates_with_proposals=candidates_with,
            candidates_skipped_no_neighbors_in_band=candidates_no_band,
        )


__all__ = ["AssociationProposal", "MorpheusAssociator"]
