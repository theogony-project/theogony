"""Tests for :class:`~theogony.clustering.recluster_phase.ReclusterPhase`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from theogony.clustering.recluster_phase import ReclusterPhase
from theogony.config.settings import OneirosSettings, Settings
from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.memory.tick_phase import TickContext
from theogony.reporting.models import ClusteringRunReport
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore


def _node(nid: str, emb: list[float]) -> KnowledgeNode:
    return KnowledgeNode(
        id=nid,
        label=nid,
        source_ref=SourceRef(source_type="t", identifier="1"),
        node_type=NodeType.CONCEPT,
        embedding=emb,
        embedding_dim=len(emb),
    )


@pytest.mark.asyncio
async def test_recluster_phase_skips_when_within_cadence(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    for i in range(25):
        await store.upsert_node(_node(f"n{i}", [1.0 if i % 2 == 0 else 0.0, 0.0, 1.0]))
    writer = RunReportWriter(tmp_path)
    recent = ClusteringRunReport(
        started_at=datetime.now(tz=UTC),
        finished_at=datetime.now(tz=UTC),
        duration_s=1.0,
        status="completed",
        verdict="good",
        algorithm="hdbscan",
        nodes_processed=25,
    )
    writer.write(recent)
    settings = Settings()
    settings.data_dir = tmp_path
    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=store,
        app_settings=settings,
        writer=writer,
    )
    await ReclusterPhase().run(ctx)
    assert "clustering_run" not in ctx.extras


@pytest.mark.asyncio
async def test_recluster_phase_runs_when_no_previous_report(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    for i in range(25):
        await store.upsert_node(_node(f"n{i}", [float((i % 5) == j) for j in range(4)]))
    writer = RunReportWriter(tmp_path)
    settings = Settings()
    settings.data_dir = tmp_path
    settings.clustering.min_cluster_size = 3
    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=store,
        app_settings=settings,
        writer=writer,
    )
    ctx.extras["recluster_force"] = True
    await ReclusterPhase().run(ctx)
    assert "clustering_run" in ctx.extras


@pytest.mark.asyncio
async def test_recluster_phase_skips_when_corpus_below_min(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    for i in range(5):
        await store.upsert_node(_node(f"n{i}", [1.0, 0.0, 0.0, 0.0]))
    writer = RunReportWriter(tmp_path)
    settings = Settings()
    settings.data_dir = tmp_path
    settings.clustering.min_corpus_size = 20
    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=store,
        app_settings=settings,
        writer=writer,
    )
    ctx.extras["recluster_force"] = True
    await ReclusterPhase().run(ctx)
    assert "clustering_run" not in ctx.extras


@pytest.mark.asyncio
async def test_recluster_phase_persists_and_refreshes_edges(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    a = _node("a", [1.0, 0.0, 0.0, 0.0])
    b = _node("b", [0.9, 0.1, 0.0, 0.0])
    from theogony.core.model import KnowledgeEdge

    await store.upsert_node(a)
    await store.upsert_node(b)
    e = KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="R", evidence_span="x")
    await store.assign_cluster(a.id, "c1")
    await store.assign_cluster(b.id, "c2")
    await store.upsert_edge(e)
    writer = RunReportWriter(tmp_path)
    settings = Settings()
    settings.data_dir = tmp_path
    settings.clustering.min_cluster_size = 2
    # many more nodes so HDBSCAN forms clusters
    for i in range(30):
        await store.upsert_node(_node(f"x{i}", [float((i % 3) == j) for j in range(4)]))
    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=store,
        app_settings=settings,
        writer=writer,
    )
    ctx.extras["recluster_force"] = True
    await ReclusterPhase().run(ctx)
    assert await store.list_clusters()


@pytest.mark.asyncio
async def test_recluster_phase_no_writer_skips(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=store,
        app_settings=Settings(data_dir=tmp_path),
        writer=None,
    )
    await ReclusterPhase().run(ctx)
    assert "clustering_run" not in ctx.extras


@pytest.mark.asyncio
async def test_recluster_phase_publishes_cluster_index_refresh(tmp_path: Path) -> None:
    store = InMemoryKnowledgeStore()
    for i in range(25):
        await store.upsert_node(_node(f"n{i}", [float((i % 4) == j) for j in range(4)]))
    writer = RunReportWriter(tmp_path)
    settings = Settings(data_dir=tmp_path)
    settings.clustering.min_cluster_size = 3
    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=store,
        app_settings=settings,
        writer=writer,
    )
    ctx.extras["recluster_force"] = True
    await ReclusterPhase().run(ctx)
    assert ctx.extras.get("cluster_index_refresh") is not None
