"""W15 ChronosRecycler."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from theogony.agents.chronos import ChronosRecycler
from theogony.config.settings import ChronosSettings, Settings
from theogony.core.model import KnowledgeNode, NodeScores, NodeType, SourceRef
from theogony.curiosity.finding import Finding
from theogony.curiosity.verification_pool import VerificationPool
from theogony.stores.memory import InMemoryKnowledgeStore


def _settings(tmp_path: Path) -> Settings:
    return Settings().model_copy(update={"data_dir": tmp_path})


def _target_person(node_id: str, *, confidence: float = 0.9) -> KnowledgeNode:
    return KnowledgeNode(
        id=node_id,
        label="target",
        node_type=NodeType.PERSON,
        source_ref=SourceRef(source_type="test", identifier=node_id),
        scores=NodeScores(confidence=confidence),
    )


@pytest.mark.asyncio
async def test_chronos_disabled_returns_skipped(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = VerificationPool(settings)
    store = InMemoryKnowledgeStore()
    r = ChronosRecycler(
        store=store,
        pool=pool,
        settings=ChronosSettings(enabled=False),
    )
    s = await r.run_once()
    assert s.skipped_reason == "chronos disabled"


@pytest.mark.asyncio
async def test_chronos_no_eligible_entries(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = VerificationPool(settings)
    pool.register("only-unobserved")
    store = InMemoryKnowledgeStore()
    r = ChronosRecycler(
        store=store,
        pool=pool,
        settings=ChronosSettings(enabled=True),
    )
    s = await r.run_once()
    assert s.skipped_reason is None
    assert s.processed_entries == 0


@pytest.mark.asyncio
async def test_chronos_clears_no_issue_and_marks_pool(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = VerificationPool(settings)
    entry = pool.register("ok")
    finding_id = "FINDING-clear-1"
    sampled_at = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)
    f = Finding(
        finding_id=finding_id,
        finding_type="no_issue_observed",
        severity="info",
        pool_entry_id=entry.entry_id,
        sampled_at=sampled_at,
    )
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes([f.to_knowledge_node()])
    pool.mark_sampled_by_athene(entry.entry_id, finding_ids=[finding_id])

    r = ChronosRecycler(
        store=store,
        pool=pool,
        settings=ChronosSettings(enabled=True),
    )
    s = await r.run_once()
    assert s.pool_entries_cleared == 1
    assert s.findings_resolved == 1
    assert any(a.action == "cleared_no_issue" for a in s.actions)

    node = await store.get_node(finding_id)
    assert node is not None
    assert node.properties.get("resolution_action") == "annotated"

    cleared_entry = pool.get(entry.entry_id)
    assert cleared_entry is not None
    assert cleared_entry.lifecycle == "cleared"


@pytest.mark.asyncio
async def test_chronos_missing_finding_skips_pool_clear(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = VerificationPool(settings)
    entry = pool.register("ghost")
    pool.mark_sampled_by_athene(entry.entry_id, finding_ids=["FINDING-missing"])
    store = InMemoryKnowledgeStore()
    r = ChronosRecycler(
        store=store,
        pool=pool,
        settings=ChronosSettings(enabled=True),
    )
    s = await r.run_once()
    assert s.missing_findings == 1
    assert s.pool_entries_cleared == 0
    again = pool.get(entry.entry_id)
    assert again is not None
    assert again.lifecycle == "sampled_by_athene"


@pytest.mark.asyncio
async def test_chronos_factual_writes_contradicts_and_demotes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = VerificationPool(settings)
    entry = pool.register("fact")
    tid = "TARGET-f1"
    finding_id = "FINDING-fact-1"
    target = _target_person(tid, confidence=0.9)
    f = Finding(
        finding_id=finding_id,
        finding_type="factual_error_suspected",
        severity="medium",
        pool_entry_id=entry.entry_id,
        target_node_ids=[tid],
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes([target, f.to_knowledge_node()])
    pool.mark_sampled_by_athene(entry.entry_id, finding_ids=[finding_id])

    r = ChronosRecycler(
        store=store,
        pool=pool,
        settings=ChronosSettings(enabled=True, confidence_demote_delta=0.1),
    )
    s = await r.run_once()
    assert s.negative_edges_written >= 1
    assert s.nodes_demoted >= 1
    edges = await store.get_edges_among([tid, finding_id])
    assert any(e.relation_type == "CONTRADICTS" for e in edges)

    t2 = await store.get_node(tid)
    assert t2 is not None
    assert t2.scores.confidence == pytest.approx(0.8)
    assert pool.get(entry.entry_id) is not None
    assert pool.get(entry.entry_id).lifecycle == "cleared"


@pytest.mark.asyncio
async def test_chronos_ingest_failed_has_no_contradicts_may_demote(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = VerificationPool(settings)
    entry = pool.register("struct")
    tid = "TARGET-s1"
    finding_id = "FINDING-struct-1"
    target = _target_person(tid, confidence=0.85)
    f = Finding(
        finding_id=finding_id,
        finding_type="ingest_failed",
        severity="medium",
        pool_entry_id=entry.entry_id,
        target_node_ids=[tid],
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes([target, f.to_knowledge_node()])
    pool.mark_sampled_by_athene(entry.entry_id, finding_ids=[finding_id])

    r = ChronosRecycler(
        store=store,
        pool=pool,
        settings=ChronosSettings(enabled=True, confidence_demote_delta=0.05),
    )
    s = await r.run_once()
    assert s.negative_edges_written == 0
    edges = await store.get_edges_among([tid, finding_id])
    assert not any(e.relation_type == "CONTRADICTS" for e in edges)
    assert s.nodes_demoted >= 1
    assert any(a.action == "demoted" for a in s.actions)


@pytest.mark.asyncio
async def test_chronos_ingest_failed_info_skips_demotion(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = VerificationPool(settings)
    entry = pool.register("low-sev")
    tid = "TARGET-low"
    finding_id = "FINDING-low-1"
    target = _target_person(tid, confidence=0.9)
    f = Finding(
        finding_id=finding_id,
        finding_type="ingest_failed",
        severity="info",
        pool_entry_id=entry.entry_id,
        target_node_ids=[tid],
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes([target, f.to_knowledge_node()])
    pool.mark_sampled_by_athene(entry.entry_id, finding_ids=[finding_id])

    r = ChronosRecycler(
        store=store,
        pool=pool,
        settings=ChronosSettings(enabled=True),
    )
    s = await r.run_once()
    assert s.nodes_demoted == 0
    assert any(a.action == "annotated" for a in s.actions)
    t2 = await store.get_node(tid)
    assert t2 is not None
    assert t2.scores.confidence == pytest.approx(0.9)


def test_chronos_module_has_no_delete_or_store_degrade() -> None:
    chronos_path = (
        Path(__file__).resolve().parents[2] / "src" / "theogony" / "agents" / "chronos.py"
    )
    text = chronos_path.read_text(encoding="utf-8")
    assert "delete_node" not in text
    assert ".degrade(" not in text


def test_chronos_settings_hard_delete_default_off() -> None:
    assert ChronosSettings().hard_delete_enabled is False
