"""
OneirosWorker unit tests — Idiom-A fast clock (Plan §3.8 layer 4).

Per Plan §5 E8.5 test recipe: monkeypatch ``asyncio.sleep`` so the
loop yields without actually waiting, then drive ticks with manual
``await asyncio.sleep(0)`` (the real one, captured before the
monkeypatch). Assert ticks observed via the report writer's
captured calls.

Stays InMemory + StubLLM + ReportWriterStub — no Neo4j, no real
clock. The integration test (``test_memory_oneiros_integration.py``)
is the one place a real 0.1-s tick interval is exercised against
testcontainers.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from theogony.config.settings import Settings
from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.memory.oneiros import OneirosWorker
from theogony.reporting.models import OneirosTickReport, RunReportBase
from theogony.stores import InMemoryKnowledgeStore


class _ReportWriterStub:
    """Drop-in for :class:`RunReportWriter` that captures writes in memory."""

    def __init__(self) -> None:
        self.written_reports: list[RunReportBase] = []

    def write(self, report: RunReportBase) -> Path:
        self.written_reports.append(report)
        return Path(f"/tmp/oneiros-{report.run_id}.json")

    def directory_for(self, report_type: str) -> Path:  # pragma: no cover - unused
        return Path("/tmp") / report_type


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="bench", location=loc, language="en")


def _node(label: str, *, last_accessed: datetime | None = None) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=NodeType.OTHER,
        source_ref=_src(f"loc:{label}"),
        last_accessed=last_accessed if last_accessed is not None else datetime.now(UTC),
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings rooted at tmp_path; oneiros tick interval = 60s default."""
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
async def store_with_seed_nodes() -> InMemoryKnowledgeStore:
    store = InMemoryKnowledgeStore()
    for i in range(3):
        await store.upsert_node(_node(f"seed-{i}"))
    return store


# ---------------------------------------------------------------- main loop


class TestRunLoop:
    """``run()`` calls ``_tick()`` between ``asyncio.sleep`` calls and exits
    cleanly on cancellation."""

    async def test_run_drives_n_ticks_via_idiom_a_fast_clock(
        self,
        settings: Settings,
        store_with_seed_nodes: InMemoryKnowledgeStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target_ticks = 5
        sleep_calls = 0
        real_sleep = asyncio.sleep  # capture BEFORE monkeypatch

        async def fake_sleep(seconds: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            await real_sleep(0)  # yield to the event loop, do NOT actually sleep

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        writer = _ReportWriterStub()
        worker = OneirosWorker(store_with_seed_nodes, settings, writer, tick_interval_s=0.01)
        task = asyncio.create_task(worker.run())

        # Drive the loop: each fake_sleep call signals one completed tick.
        # 100 yields is the bounded budget (the recipe in Plan §5 E8.5
        # uses 50; we double it to absorb scheduler jitter on slow CI).
        for _ in range(100):
            await real_sleep(0)
            if sleep_calls >= target_ticks:
                break

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert sleep_calls >= target_ticks
        # One report written per completed tick. The fast-clock loop
        # may have completed one MORE tick than ``sleep_calls`` because
        # the cancellation happened between the tick and the sleep —
        # so we assert the count is at least target_ticks.
        assert len(writer.written_reports) >= target_ticks
        assert all(isinstance(r, OneirosTickReport) for r in writer.written_reports)
        assert all(r.report_type == "oneiros" for r in writer.written_reports)

    async def test_run_exits_on_cancellation_within_a_short_budget(
        self,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Idiom-A again, but the assertion this time is "cancellation
        # propagates and `await task` returns within 1 s on a fast tick".
        real_sleep = asyncio.sleep

        async def fake_sleep(_seconds: float) -> None:
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        store = InMemoryKnowledgeStore()
        writer = _ReportWriterStub()
        worker = OneirosWorker(store, settings, writer, tick_interval_s=0.01)
        task = asyncio.create_task(worker.run())
        await real_sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1.0)


# ---------------------------------------------------------------- _tick


class TestTickShape:
    """The ``_tick()`` shape — what it reads, what it writes, what report comes out."""

    async def test_tick_reads_ephemera_writes_one_report(
        self,
        settings: Settings,
        store_with_seed_nodes: InMemoryKnowledgeStore,
    ) -> None:
        writer = _ReportWriterStub()
        worker = OneirosWorker(store_with_seed_nodes, settings, writer, tick_interval_s=60.0)
        await worker._tick()

        assert len(writer.written_reports) == 1
        report = writer.written_reports[0]
        assert isinstance(report, OneirosTickReport)
        assert report.nodes_evaluated == 3
        # No nodes hit the 0.7 promote threshold on the seed scores
        # (default vitality of a fresh node is ~0.5); none degrade.
        assert report.nodes_promoted == 0
        assert report.nodes_degraded == 0
        assert report.duration_s >= 0.0

    async def test_tick_writes_via_batch_update_scores(
        self,
        settings: Settings,
        store_with_seed_nodes: InMemoryKnowledgeStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The worker's contract is "one batch_update_scores call per
        # tick with N rows, where N == nodes_evaluated". Wrap the
        # store's method to count calls + capture row counts.
        writer = _ReportWriterStub()
        worker = OneirosWorker(store_with_seed_nodes, settings, writer, tick_interval_s=60.0)

        original = store_with_seed_nodes.batch_update_scores
        observations: list[int] = []

        async def wrapped(updates):  # type: ignore[no-untyped-def]
            observations.append(len(list(updates)))
            await original(updates)

        monkeypatch.setattr(store_with_seed_nodes, "batch_update_scores", wrapped)

        await worker._tick()
        assert observations == [3]  # one call, three nodes

    async def test_tick_recomputes_freshness_from_idle_days(
        self,
        settings: Settings,
        tmp_path: Path,
    ) -> None:
        # A node 30 days idle should land at freshness ≈ 0 after the
        # tick (linear-30-day decay per Plan §5 E8.5 default horizon).
        store = InMemoryKnowledgeStore()
        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
        stale = _node("StaleOne", last_accessed=thirty_days_ago)
        # Pin the node's freshness to 1.0 so the tick has work to do.
        stale.scores.freshness = 1.0
        await store.upsert_node(stale)

        writer = _ReportWriterStub()
        worker = OneirosWorker(store, settings, writer, tick_interval_s=60.0)
        await worker._tick()

        fetched = await store.get_node(stale.id)
        assert fetched is not None
        # Freshness collapses to ~0 after a 30-day idle gap.
        assert fetched.scores.freshness <= 0.05

    async def test_tick_recomputes_connectivity_from_edge_count(
        self,
        settings: Settings,
    ) -> None:
        # Linear cap at 20 (default ``connectivity_full_credit_edges``).
        # 5 edges → 0.25 connectivity; 25 edges → 1.0 (capped).
        store = InMemoryKnowledgeStore()
        hub = _node("Hub")
        await store.upsert_node(hub)
        # Spawn 5 spokes + edges so the bulk degree-count returns 5.
        from theogony.core.model import KnowledgeEdge

        for i in range(5):
            spoke = _node(f"Spoke-{i}")
            await store.upsert_node(spoke)
            await store.upsert_edge(
                KnowledgeEdge(
                    source_id=hub.id,
                    target_id=spoke.id,
                    relation_type="LINKS_TO",
                )
            )

        writer = _ReportWriterStub()
        worker = OneirosWorker(store, settings, writer, tick_interval_s=60.0)
        await worker._tick()

        fetched = await store.get_node(hub.id)
        assert fetched is not None
        # 5 / 20 = 0.25 connectivity for hub.
        assert abs(fetched.scores.connectivity - 0.25) < 0.01

    async def test_tick_with_empty_ephemera_writes_partial_verdict_report(
        self, settings: Settings
    ) -> None:
        # No nodes → ``oneiros_verdict`` returns "poor" (worker is
        # starving). Plan §5 E8.5: the report still writes; "absence
        # of new reports" is the operator-observable failure signal.
        writer = _ReportWriterStub()
        worker = OneirosWorker(InMemoryKnowledgeStore(), settings, writer, tick_interval_s=60.0)
        await worker._tick()
        assert len(writer.written_reports) == 1
        report = writer.written_reports[0]
        assert report.nodes_evaluated == 0
        assert report.verdict == "poor"


# ---------------------------------------------------------------- constructor


class TestConstructor:
    def test_tick_interval_defaults_to_settings_value(self, settings: Settings) -> None:
        worker = OneirosWorker(InMemoryKnowledgeStore(), settings, _ReportWriterStub())
        assert worker._tick_interval_s == settings.oneiros.tick_interval_s

    def test_explicit_tick_interval_overrides_settings(self, settings: Settings) -> None:
        worker = OneirosWorker(
            InMemoryKnowledgeStore(),
            settings,
            _ReportWriterStub(),
            tick_interval_s=0.5,
        )
        assert worker._tick_interval_s == 0.5
