"""W15 negative-knowledge edge helpers (CONTRADICTS from Chronos)."""

from __future__ import annotations

from datetime import UTC, datetime

from theogony.curiosity.finding import Finding
from theogony.curiosity.negative_knowledge import (
    NEGATIVE_RELATION_TYPES,
    contradiction_edges_for_finding,
)


def test_contradiction_edges_empty_without_targets() -> None:
    f = Finding(
        finding_id="FINDING-x",
        finding_type="factual_error_suspected",
        severity="high",
        pool_entry_id="p1",
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
        target_node_ids=[],
    )
    assert contradiction_edges_for_finding(f, confidence=0.8, weight=0.7) == []


def test_contradiction_edges_empty_for_structural_finding() -> None:
    f = Finding(
        finding_id="FINDING-y",
        finding_type="ingest_failed",
        severity="medium",
        pool_entry_id="p1",
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
        target_node_ids=["T1"],
    )
    assert contradiction_edges_for_finding(f, confidence=0.8, weight=0.7) == []


def test_contradiction_edges_for_factual_types() -> None:
    f = Finding(
        finding_id="FINDING-f",
        finding_type="factual_error_suspected",
        severity="medium",
        pool_entry_id="p1",
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
        target_node_ids=["A", "B"],
    )
    edges = contradiction_edges_for_finding(f, confidence=0.55, weight=0.4)
    assert len(edges) == 2
    assert {e.source_id for e in edges} == {"A", "B"}
    assert {e.target_id for e in edges} == {f.finding_id}
    assert all(e.relation_type == "CONTRADICTS" for e in edges)
    assert all(e.confidence == 0.55 and e.weight == 0.4 for e in edges)


def test_negative_relation_types_includes_expected_strings() -> None:
    assert "CONTRADICTS" in NEGATIVE_RELATION_TYPES
    assert "SUPERSEDED_BY" in NEGATIVE_RELATION_TYPES
