"""W14 Finding → KnowledgeNode and FLAGGED_BY edges."""

from __future__ import annotations

from datetime import UTC, datetime

from theogony.core.model import EdgeType, EpistemicStatus, Layer, NodeType
from theogony.curiosity.finding import Finding, flag_edges_for_finding


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
