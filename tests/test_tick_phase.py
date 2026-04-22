"""Tests for :class:`~theogony.memory.tick_phase.TickPhase` and :class:`TickContext`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from theogony.config.settings import OneirosSettings, Settings
from theogony.memory.oneiros import OneirosWorker
from theogony.memory.tick_phase import TickContext, TickPhase
from theogony.memory.tick_phases import SnapshotEphemeraPhase
from theogony.reporting.models import OneirosTickReport
from theogony.stores import InMemoryKnowledgeStore


def test_tick_phase_protocol_runtime_checkable() -> None:
    assert isinstance(SnapshotEphemeraPhase(), TickPhase)


def test_tick_context_default_field_initialisation() -> None:
    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=MagicMock(),
    )
    assert ctx.nodes_ephemera == []
    assert ctx.edge_counts == {}
    assert ctx.updates == []
    assert ctx.pre_vitality == []
    assert ctx.post_vitality == []
    assert ctx.promote_targets == []
    assert ctx.nodes_promoted == 0
    assert ctx.nodes_degraded == 0
    assert ctx.extras == {}


@pytest.mark.asyncio
async def test_phase_pipeline_runs_in_registered_order() -> None:
    class PhaseA:
        name = "phase_a"

        async def run(self, ctx: TickContext) -> None:
            ctx.extras.setdefault("call_order", []).append("a")

    class PhaseB:
        name = "phase_b"

        async def run(self, ctx: TickContext) -> None:
            ctx.extras.setdefault("call_order", []).append("b")

    ctx = TickContext(
        started_at=datetime.now(tz=UTC),
        perf_started=0.0,
        cfg=OneirosSettings(),
        store=MagicMock(),
    )
    for phase in (PhaseA(), PhaseB()):
        await phase.run(ctx)
    assert ctx.extras["call_order"] == ["a", "b"]


class _CaptureWriter:
    def __init__(self) -> None:
        self.written: list[OneirosTickReport] = []

    def write(self, report: OneirosTickReport) -> Path:
        self.written.append(report)
        return Path("/tmp/x.json")

    def directory_for(self, report_type: str) -> Path:  # pragma: no cover
        return Path("/tmp") / report_type


@pytest.mark.asyncio
async def test_phase_can_be_disabled_via_settings(tmp_path: Path) -> None:
    calls: list[str] = []

    class FakeSnap:
        name = "snapshot_ephemera"

        async def run(self, ctx: TickContext) -> None:
            calls.append("snap")

    class FakeCount:
        name = "count_neighbors"

        async def run(self, ctx: TickContext) -> None:
            calls.append("count")

    settings = Settings(
        data_dir=tmp_path / "data",
        oneiros=OneirosSettings(
            enabled_phases=["snapshot_ephemera", "count_neighbors"],
        ),
    )
    writer = _CaptureWriter()
    worker = OneirosWorker(
        InMemoryKnowledgeStore(),
        settings,
        writer,
        phase_registry={
            "snapshot_ephemera": FakeSnap,
            "count_neighbors": FakeCount,
        },
    )
    await worker._tick()
    assert calls == ["snap", "count"]


@pytest.mark.asyncio
async def test_unknown_phase_name_in_settings_silently_skipped(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        oneiros=OneirosSettings(enabled_phases=["nonexistent"]),
    )
    writer = _CaptureWriter()
    worker = OneirosWorker(InMemoryKnowledgeStore(), settings, writer)
    await worker._tick()
    assert len(writer.written) == 1


@pytest.mark.asyncio
async def test_phase_exception_propagates_and_marks_tick_failed(tmp_path: Path) -> None:
    class Boom:
        name = "boom"

        async def run(self, ctx: TickContext) -> None:
            raise RuntimeError("tick boom")

    settings = Settings(
        data_dir=tmp_path / "data",
        oneiros=OneirosSettings(enabled_phases=["boom"]),
    )
    writer = _CaptureWriter()
    worker = OneirosWorker(
        InMemoryKnowledgeStore(),
        settings,
        writer,
        phase_registry={"boom": Boom},
    )
    with pytest.raises(RuntimeError, match="tick boom"):
        await worker._tick()
    assert len(writer.written) == 1
    assert writer.written[0].status == "failed"
