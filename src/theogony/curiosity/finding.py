"""Athene Finding DTOs and Chronik projections (Living Demo W14)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.core.model import (
    EdgeType,
    EpistemicStatus,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
    NodeType,
    SourceRef,
)

FindingType = Literal[
    "no_issue_observed",
    "ingest_report_missing",
    "ingest_failed",
    "ingest_partial",
    "low_resolution_quality",
    "high_schema_violation_rate",
    "high_parse_error_rate",
]

FindingSeverity = Literal["info", "low", "medium", "high", "critical"]
FindingCell = Literal["athene"]


class Finding(BaseModel):
    """Post-hoc immune observation; persisted as a :class:`KnowledgeNode`."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(default_factory=lambda: f"FINDING-{uuid.uuid4()}")
    finding_type: FindingType
    severity: FindingSeverity
    cell: FindingCell = "athene"
    pool_entry_id: str
    ingest_run_id: str | None = None
    target_node_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    sampled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolution_action: Literal["none", "annotated", "demoted", "deleted", "escalated_to_human"] = (
        "none"
    )

    def to_knowledge_node(self) -> KnowledgeNode:
        """Materialise as an ordinary ``KnowledgeNode`` (``node_type=finding``)."""
        ingest_bit = f", ingest_run_id={self.ingest_run_id}" if self.ingest_run_id else ""
        description = (
            f"{self.severity} severity for pool entry {self.pool_entry_id}{ingest_bit} "
            f"({self.finding_type})."
        )
        snippet = "; ".join(self.evidence[:3])
        props: dict[str, Any] = {
            "finding_id": self.finding_id,
            "finding_type": self.finding_type,
            "severity": self.severity,
            "cell": self.cell,
            "pool_entry_id": self.pool_entry_id,
            "ingest_run_id": self.ingest_run_id,
            "target_node_ids": list(self.target_node_ids),
            "evidence": list(self.evidence),
            "sampled_at": self.sampled_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_action": self.resolution_action,
        }
        return KnowledgeNode(
            id=self.finding_id,
            node_type=NodeType.FINDING,
            label=f"Athene finding: {self.finding_type}",
            description=description,
            epistemic_status=EpistemicStatus.OBSERVED,
            layer=Layer.EPHEMERA,
            source_ref=SourceRef(
                source_type="athene",
                identifier=self.finding_id,
                snippet=snippet or None,
            ),
            properties=props,
        )


def flag_edges_for_finding(finding: Finding) -> list[KnowledgeEdge]:
    """One ``FLAGGED_BY`` edge per target node (source node → finding)."""
    edges: list[KnowledgeEdge] = []
    for target_node_id in finding.target_node_ids:
        edges.append(
            KnowledgeEdge(
                source_id=target_node_id,
                target_id=finding.finding_id,
                relation_type="FLAGGED_BY",
                weight=0.5,
                confidence=0.8,
                epistemic_type=EdgeType.AGENT,
                source_ref=SourceRef(
                    source_type="athene",
                    identifier=finding.finding_id,
                ),
            )
        )
    return edges


__all__ = [
    "Finding",
    "FindingCell",
    "FindingSeverity",
    "FindingType",
    "flag_edges_for_finding",
]
