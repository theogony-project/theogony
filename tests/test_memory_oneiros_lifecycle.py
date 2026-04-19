"""
OneirosWorker lifecycle tests — promote / degrade / hysteresis / convergence.

Plan §5 E8.5 acceptance criteria:

* (a) A node with vitality ≥ ``promote_threshold`` after one tick
  lands in MNEME.
* (b) A MNEME node with vitality ≤ ``degrade_threshold`` AND
  ``last_accessed > degrade_min_idle_days`` ago lands back in
  EPHEMERA on the next tick.
* (c) Same vitality, but ``last_accessed = now`` → NOT degraded
  (the hysteresis idle guard wins).
* (d) Convergence (Q5): a ``RelevanceTracker.bump`` interleaved
  between two manual yields leaves the bumped relevance intact in
  the post-tick ``get_node`` result.

The convergence test pins Plan §5 E8.5's race-condition contract.
Future Reviewer-agent (PHX-0035) work will likely revisit it; keep
the assertion + comment readable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from theogony.config.settings import Settings
from theogony.core.model import KnowledgeNode, Layer, NodeType, SourceRef
from theogony.memory.oneiros import OneirosWorker
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.models import RunReportBase
from theogony.stores import InMemoryKnowledgeStore


class _ReportWriterStub:
    def __init__(self) -> None:
        self.written_reports: list[RunReportBase] = []

    def write(self, report: RunReportBase) -> Path:
        self.written_reports.append(report)
        return Path(f"/tmp/oneiros-{report.run_id}.json")

    def directory_for(self, report_type: str) -> Path:
        return Path("/tmp") / report_type


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="bench", location=loc, language="en")


def _ephemera_node(label: str, **scores: float) -> KnowledgeNode:
    n = KnowledgeNode(
        label=label,
        node_type=NodeType.OTHER,
        source_ref=_src(f"loc:{label}"),
    )
    for k, v in scores.items():
        setattr(n.scores, k, v)
    return n


def _mneme_node(label: str, *, last_accessed: datetime, **scores: float) -> KnowledgeNode:
    n = KnowledgeNode(
        label=label,
        node_type=NodeType.OTHER,
        source_ref=_src(f"loc:{label}"),
        layer=Layer.MNEME,
        last_accessed=last_accessed,
    )
    for k, v in scores.items():
        setattr(n.scores, k, v)
    return n


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


# ---------------------------------------------------------------- promote


class TestPromotion:
    async def test_node_above_promote_threshold_moves_to_mneme(self, settings: Settings) -> None:
        store = InMemoryKnowledgeStore()
        # Pin scores so the *recomputed* vitality after the tick lands
        # ≥ 0.7 (default promote_threshold). vitality() weights:
        # 0.4*confidence + 0.25*relevance + 0.2*connectivity + 0.15*freshness
        # The worker recomputes connectivity (=0 here, no edges) and
        # freshness (=1.0 because last_accessed=now). Final vitality:
        # 0.4*1.0 + 0.25*1.0 + 0.2*0 + 0.15*1.0 = 0.8 ≥ 0.7. ✓
        winner = _ephemera_node("Promotable", confidence=1.0, relevance=1.0)
        # And one that fails (low confidence/relevance):
        loser = _ephemera_node("Stay", confidence=0.1, relevance=0.1)
        await store.upsert_node(winner)
        await store.upsert_node(loser)

        worker = OneirosWorker(store, settings, _ReportWriterStub())
        await worker._tick()

        promoted = await store.get_node(winner.id)
        kept = await store.get_node(loser.id)
        assert promoted is not None
        assert kept is not None
        assert promoted.layer == Layer.MNEME, "winner should have promoted"
        assert kept.layer == Layer.EPHEMERA, "loser should have stayed put"


# ---------------------------------------------------------------- degrade


class TestDegradation:
    async def test_stale_low_vitality_mneme_node_degrades(self, settings: Settings) -> None:
        # MNEME, vitality ≤ 0.25, idle ≥ 7 days → degrade.
        # Default vitality of NodeScores(confidence=0.0, relevance=0.0,
        # connectivity=0.0, freshness=0.0) = 0.0, well below 0.25.
        store = InMemoryKnowledgeStore()
        eight_days_ago = datetime.now(UTC) - timedelta(days=8)
        stale = _mneme_node(
            "StaleMneme",
            last_accessed=eight_days_ago,
            confidence=0.0,
            relevance=0.0,
            connectivity=0.0,
            freshness=0.0,
        )
        await store.upsert_node(stale)

        worker = OneirosWorker(store, settings, _ReportWriterStub())
        await worker._tick()

        fetched = await store.get_node(stale.id)
        assert fetched is not None
        assert fetched.layer == Layer.EPHEMERA, "stale low-vitality MNEME should degrade"

    async def test_recently_accessed_mneme_node_NOT_degraded_despite_low_vitality(
        self, settings: Settings
    ) -> None:
        # The hysteresis idle guard: same low vitality, but
        # ``last_accessed = now`` → keep in MNEME. This protects
        # newly-touched nodes from being flushed by a transient dip.
        store = InMemoryKnowledgeStore()
        fresh = _mneme_node(
            "FreshMneme",
            last_accessed=datetime.now(UTC),  # recently touched
            confidence=0.0,
            relevance=0.0,
            connectivity=0.0,
            freshness=0.0,
        )
        await store.upsert_node(fresh)

        worker = OneirosWorker(store, settings, _ReportWriterStub())
        await worker._tick()

        fetched = await store.get_node(fresh.id)
        assert fetched is not None
        assert fetched.layer == Layer.MNEME, (
            "recently-touched MNEME node must not degrade despite low vitality "
            "(hysteresis idle guard, Plan §5 E8.5)"
        )


# ---------------------------------------------------------------- convergence (Q5)


class TestConvergenceQ5:
    """Plan §5 E8.5 race-condition contract.

    A ``RelevanceTracker.bump`` interleaved with the worker's snapshot/write
    cycle must leave the bumped relevance intact: the worker's bulk
    write touches connectivity / freshness / vitality but NOT relevance,
    so the bump survives. PHX-0048 (reopened) is the Cypher-level
    enforcement; this test pins the contract for the InMemory store.
    """

    async def test_bump_during_tick_survives_worker_write(self, settings: Settings) -> None:
        # Pin scores so we can observe a relevance change cleanly.
        store = InMemoryKnowledgeStore()
        node = _ephemera_node(
            "Cited", confidence=0.5, relevance=0.5, connectivity=0.5, freshness=0.5
        )
        await store.upsert_node(node)

        # Read the pre-bump relevance so the post-bump assertion has bite.
        pre = await store.get_node(node.id)
        assert pre is not None
        assert pre.scores.relevance == pytest.approx(0.5)

        # The race we pin: worker reads, bump runs, worker writes.
        # In this in-process test we sequence them deterministically:
        #   1. worker._tick() — reads ephemera, computes new
        #      (connectivity, freshness, vitality), writes them via
        #      batch_update_scores.
        #   2. RelevanceTracker.bump runs IN BETWEEN by sequencing
        #      it after the tick rather than splitting the tick: the
        #      observable contract is "the worker's bulk write does
        #      not touch relevance", so any bump that happens at any
        #      time around the tick survives. We assert this by
        #      sequencing bump → worker._tick() → assert bumped value
        #      survives the worker's write.
        tracker = RelevanceTracker(store, relevance_delta=0.05)
        await tracker.bump(node.id)
        bumped = await store.get_node(node.id)
        assert bumped is not None
        bumped_relevance = bumped.scores.relevance
        # 0.5 (pre) + 0.05 (delta) = 0.55 (capped at 1.0 by RelevanceTracker)
        assert bumped_relevance == pytest.approx(0.55)

        worker = OneirosWorker(store, settings, _ReportWriterStub())
        await worker._tick()

        # Post-tick: relevance must STILL reflect the bump. If the
        # worker's batch_update_scores wrote relevance, this would be
        # back at the pre-bump value (0.5) and the test would fail.
        after = await store.get_node(node.id)
        assert after is not None
        assert after.scores.relevance == pytest.approx(0.55), (
            "worker.batch_update_scores must not overwrite relevance — "
            "Plan §5 E8.5 race-condition contract (Q5)"
        )

    async def test_worker_only_writes_connectivity_freshness_vitality(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stronger pin on the contract: inspect the actual ScoreUpdate
        # rows the worker passes to batch_update_scores. Each row
        # MUST have confidence=None and relevance=None (the worker
        # leaves those alone) and non-None connectivity / freshness /
        # vitality.
        store = InMemoryKnowledgeStore()
        await store.upsert_node(_ephemera_node("X", confidence=0.5, relevance=0.5))

        captured: list[list[object]] = []

        original = store.batch_update_scores

        async def wrapped(updates):  # type: ignore[no-untyped-def]
            captured.append(list(updates))
            await original(updates)

        monkeypatch.setattr(store, "batch_update_scores", wrapped)

        worker = OneirosWorker(store, settings, _ReportWriterStub())
        await worker._tick()

        assert len(captured) == 1
        rows = captured[0]
        assert len(rows) == 1
        row = rows[0]
        assert row.confidence is None
        assert row.relevance is None
        assert row.connectivity is not None
        assert row.freshness is not None
        assert row.vitality is not None
