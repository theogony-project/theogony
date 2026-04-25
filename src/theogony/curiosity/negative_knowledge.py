"""Negative-knowledge edge helpers (Living Demo W15, PHX-0062 partial)."""

from __future__ import annotations

from theogony.core.model import EdgeType, KnowledgeEdge, SourceRef
from theogony.curiosity.finding import Finding

NEGATIVE_RELATION_TYPES = frozenset({"CONTRADICTS", "SUPERSEDED_BY"})


def contradiction_edges_for_finding(
    finding: Finding,
    *,
    confidence: float,
    weight: float,
) -> list[KnowledgeEdge]:
    """``CONTRADICTS`` edges from each target node to the finding (factual types only)."""
    if not finding.target_node_ids:
        return []
    if finding.finding_type not in ("factual_error_suspected", "internal_contradiction"):
        return []
    edges: list[KnowledgeEdge] = []
    for target_node_id in finding.target_node_ids:
        edges.append(
            KnowledgeEdge(
                source_id=target_node_id,
                target_id=finding.finding_id,
                relation_type="CONTRADICTS",
                weight=weight,
                confidence=confidence,
                epistemic_type=EdgeType.AGENT,
                source_ref=SourceRef(
                    source_type="chronos",
                    identifier=finding.finding_id,
                ),
                properties={
                    "cell": "chronos",
                    "finding_type": finding.finding_type,
                    "pool_entry_id": finding.pool_entry_id,
                },
            )
        )
    return edges


__all__ = ["NEGATIVE_RELATION_TYPES", "contradiction_edges_for_finding"]
