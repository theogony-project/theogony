"""W14 Finding → KnowledgeNode and FLAGGED_BY edges."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from theogony.core.model import EdgeType, EpistemicStatus, KnowledgeNode, Layer, NodeType, SourceRef
from theogony.curiosity.finding import (
    Finding,
    finding_from_node,
    flag_edges_for_finding,
    resolved_finding_node,
)


def test_finding_to_knowledge_node_uses_node_type_finding() -> None:
    f = Finding(
        finding_type="no_issue_observed",
        severity="info",
        pool_entry_id="pool-1",
        ingest_run_id="ing-1",
        sampled_at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
    )
    node = f.to_knowledge_node()
    assert node.node_type == NodeType.FINDING
    assert node.id == f.finding_id
    assert node.layer == Layer.EPHEMERA
    assert node.epistemic_status == EpistemicStatus.OBSERVED
    assert node.source_ref.source_type == "athene"
    assert node.source_ref.identifier == f.finding_id


def test_finding_node_properties_include_pool_entry_and_evidence() -> None:
    f = Finding(
        finding_type="ingest_failed",
        severity="high",
        pool_entry_id="e1",
        evidence=["a", "b"],
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    node = f.to_knowledge_node()
    assert node.properties["pool_entry_id"] == "e1"
    assert node.properties["evidence"] == ["a", "b"]
    assert node.properties["finding_type"] == "ingest_failed"


def test_flag_edges_for_finding_creates_flagged_by_edges() -> None:
    f = Finding(
        finding_type="no_issue_observed",
        severity="info",
        pool_entry_id="p",
        target_node_ids=["N1", "N2"],
    )
    edges = flag_edges_for_finding(f)
    assert len(edges) == 2
    assert edges[0].source_id == "N1"
    assert edges[0].target_id == f.finding_id
    assert edges[0].relation_type == "FLAGGED_BY"
    assert edges[0].confidence == 0.8
    assert edges[0].weight == 0.5
    assert edges[0].epistemic_type == EdgeType.AGENT
    assert edges[0].source_ref is not None
    assert edges[0].source_ref.identifier == f.finding_id
    assert edges[1].source_id == "N2"


def test_flag_edges_for_finding_empty_targets_returns_empty_list() -> None:
    f = Finding(finding_type="no_issue_observed", severity="info", pool_entry_id="p")
    assert flag_edges_for_finding(f) == []


def test_finding_from_node_round_trips_w14_finding() -> None:
    f = Finding(
        finding_id="FINDING-round-1",
        finding_type="no_issue_observed",
        severity="info",
        pool_entry_id="pool-x",
        ingest_run_id="ing-9",
        evidence=["e1"],
        sampled_at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
    )
    node = f.to_knowledge_node()
    back = finding_from_node(node)
    assert back.finding_id == f.finding_id
    assert back.finding_type == f.finding_type
    assert back.severity == f.severity
    assert back.pool_entry_id == f.pool_entry_id
    assert back.ingest_run_id == f.ingest_run_id
    assert back.evidence == f.evidence


def test_finding_from_node_rejects_non_finding_node() -> None:
    n = KnowledgeNode(
        label="x",
        node_type=NodeType.PERSON,
        source_ref=SourceRef(source_type="test", identifier="1"),
    )
    with pytest.raises(ValueError, match="finding"):
        finding_from_node(n)


def test_resolved_finding_node_updates_resolution_fields_only() -> None:
    f = Finding(
        finding_id="FINDING-r1",
        finding_type="ingest_failed",
        severity="high",
        pool_entry_id="p1",
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    when = datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC)
    node = resolved_finding_node(f, resolved_at=when, resolution_action="annotated")
    assert node.properties["resolution_action"] == "annotated"
    assert node.properties["resolved_at"] == when.isoformat()
    assert node.properties["finding_type"] == "ingest_failed"
    assert node.properties["finding_id"] == f.finding_id
