"""W16 NemesisAuditor."""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.agents.nemesis import NemesisAuditor
from theogony.config.settings import NemesisSettings
from theogony.core.model import (
    EdgeType,
    KnowledgeEdge,
    KnowledgeNode,
    NodeScores,
    NodeType,
    SourceRef,
)
from theogony.stores.memory import InMemoryKnowledgeStore


def _person(nid: str, *, confidence: float = 0.5, source_count: int | None = None) -> KnowledgeNode:
    props: dict = {}
    if source_count is not None:
        props["source_count"] = source_count
    return KnowledgeNode(
        id=nid,
        label=nid,
        node_type=NodeType.PERSON,
        source_ref=SourceRef(source_type="test", identifier=nid),
        scores=NodeScores(confidence=confidence),
        properties=props,
    )


@pytest.mark.asyncio
async def test_nemesis_disabled_returns_skipped_summary() -> None:
    store = InMemoryKnowledgeStore()
    auditor = NemesisAuditor(store=store, settings=NemesisSettings(enabled=False))
    s = await auditor.run_once()
    assert s.skipped_reason == "nemesis disabled"


@pytest.mark.asyncio
async def test_nemesis_confidence_inflation_proxy_writes_finding_node() -> None:
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes(
        [_person("P1", confidence=0.95, source_count=1), _person("P2", confidence=0.5)]
    )
    auditor = NemesisAuditor(
        store=store,
        settings=NemesisSettings(
            enabled=True,
            high_confidence_threshold=0.9,
            low_evidence_source_count=1,
            max_findings_per_pass=50,
        ),
    )
    s = await auditor.run_once()
    assert s.confidence_inflation_count >= 1
    assert s.findings_written >= 1
    n = await store.get_node(s.findings[0].finding_id)
    assert n is not None
    assert n.node_type == NodeType.FINDING


@pytest.mark.asyncio
async def test_nemesis_persistent_contradiction_writes_finding_node() -> None:
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes([_person("A"), _person("B")])
    await store.batch_upsert_edges(
        [
            KnowledgeEdge(
                source_id="A",
                target_id="B",
                relation_type="CONTRADICTS",
                weight=0.55,
                confidence=0.7,
                epistemic_type=EdgeType.AGENT,
                source_ref=SourceRef(source_type="chronos", identifier="FINDING-x"),
                pheromone_delta=0.0,
            )
        ]
    )
    auditor = NemesisAuditor(
        store=store,
        settings=NemesisSettings(
            enabled=True,
            contradiction_confidence_threshold=0.65,
            contradiction_weight_threshold=0.5,
            max_findings_per_pass=50,
        ),
    )
    s = await auditor.run_once()
    assert s.persistent_contradiction_count >= 1
    assert any(r.finding_type == "persistent_contradiction" for r in s.findings)


@pytest.mark.asyncio
async def test_nemesis_pheromone_autobahn_writes_finding_node() -> None:
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes([_person("X"), _person("Y")])
    await store.batch_upsert_edges(
        [
            KnowledgeEdge(
                source_id="X",
                target_id="Y",
                relation_type="P31",
                weight=0.9,
                confidence=0.5,
                epistemic_type=EdgeType.AGENT,
                source_ref=SourceRef(source_type="test", identifier="e1"),
                pheromone_delta=0.4,
            )
        ]
    )
    auditor = NemesisAuditor(
        store=store,
        settings=NemesisSettings(enabled=True, autobahn_pheromone_delta_threshold=0.25),
    )
    s = await auditor.run_once()
    assert s.pheromone_autobahn_count >= 1


@pytest.mark.asyncio
async def test_nemesis_caps_findings_per_pass() -> None:
    store = InMemoryKnowledgeStore()
    nodes = [_person(f"H{i}", confidence=0.99, source_count=1) for i in range(5)]
    await store.batch_upsert_nodes(nodes)
    auditor = NemesisAuditor(
        store=store,
        settings=NemesisSettings(
            enabled=True,
            high_confidence_threshold=0.9,
            low_evidence_source_count=2,
            max_findings_per_pass=2,
        ),
    )
    s = await auditor.run_once()
    assert s.findings_written == 2


def test_nemesis_does_not_demote_or_delete() -> None:
    nemesis_path = (
        Path(__file__).resolve().parents[2] / "src" / "theogony" / "agents" / "nemesis.py"
    )
    text = nemesis_path.read_text(encoding="utf-8")
    assert "delete_node" not in text
    assert "batch_update_scores" not in text
    assert ".degrade(" not in text
