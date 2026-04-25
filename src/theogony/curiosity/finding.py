"""Athene Finding DTOs and Chronik projections (Living Demo W14)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

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
    "factual_error_suspected",
    "internal_contradiction",
    "confidence_inflation",
    "echo_chamber",
    "pheromone_autobahn",
    "persistent_contradiction",
    "adversarial_test_outcome",
]

FindingSeverity = Literal["info", "low", "medium", "high", "critical"]
FindingCell = Literal["athene", "chronos", "nemesis", "eris"]


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
            label=f"{self.cell.title()} finding: {self.finding_type}",
            description=description,
            epistemic_status=EpistemicStatus.OBSERVED,
            layer=Layer.EPHEMERA,
            source_ref=SourceRef(
                source_type=self.cell,
                identifier=self.finding_id,
                snippet=snippet or None,
            ),
            properties=props,
        )


def finding_from_node(node: KnowledgeNode) -> Finding:
    """Parse a :class:`Finding` from ``KnowledgeNode(node_type=finding)``."""
    if node.node_type != NodeType.FINDING:
        msg = f"expected node_type=finding, got {node.node_type!r}"
        raise ValueError(msg)
    props = node.properties or {}
    required = ("finding_id", "finding_type", "severity", "cell", "pool_entry_id", "sampled_at")
    missing = [k for k in required if k not in props or props[k] is None]
    if missing:
        msg = f"missing required finding properties: {', '.join(missing)}"
        raise ValueError(msg)
    sampled_raw = props["sampled_at"]
    if not isinstance(sampled_raw, str):
        msg = "finding sampled_at must be an ISO 8601 string"
        raise ValueError(msg)
    sampled_at = datetime.fromisoformat(sampled_raw.replace("Z", "+00:00"))
    resolved_at: datetime | None = None
    if props.get("resolved_at") is not None and isinstance(props["resolved_at"], str):
        resolved_at = datetime.fromisoformat(props["resolved_at"].replace("Z", "+00:00"))
    evidence = props.get("evidence") or []
    if not isinstance(evidence, list):
        msg = "finding evidence must be a list"
        raise ValueError(msg)
    target_ids = props.get("target_node_ids") or []
    if not isinstance(target_ids, list):
        msg = "finding target_node_ids must be a list"
        raise ValueError(msg)
    return Finding(
        finding_id=str(props["finding_id"]),
        finding_type=cast(FindingType, props["finding_type"]),
        severity=cast(FindingSeverity, props["severity"]),
        cell=cast(FindingCell, props["cell"]),
        pool_entry_id=str(props["pool_entry_id"]),
        ingest_run_id=str(props["ingest_run_id"]) if props.get("ingest_run_id") else None,
        target_node_ids=[str(x) for x in target_ids],
        evidence=[str(x) for x in evidence],
        sampled_at=sampled_at,
        resolved_at=resolved_at,
        resolution_action=cast(
            Literal["none", "annotated", "demoted", "deleted", "escalated_to_human"],
            props.get("resolution_action") or "none",
        ),
    )


def resolved_finding_node(
    finding: Finding,
    *,
    resolved_at: datetime,
    resolution_action: Literal["none", "annotated", "demoted", "deleted", "escalated_to_human"],
) -> KnowledgeNode:
    """Return an updated :class:`KnowledgeNode` with resolution fields changed."""
    updated = finding.model_copy(
        update={"resolved_at": resolved_at, "resolution_action": resolution_action},
    )
    return updated.to_knowledge_node()


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
                    source_type=finding.cell,
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
    "finding_from_node",
    "flag_edges_for_finding",
    "resolved_finding_node",
]
