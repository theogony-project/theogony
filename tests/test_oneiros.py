"""Canonical Oneiros tick regression path (etappe brief naming).

The full worker suite lives in ``test_memory_oneiros_worker.py``; this
module holds a minimal smoke test so ``pytest tests/test_oneiros.py``
exercises the same tick contract in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from theogony.config.settings import Settings
from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.memory.oneiros import OneirosWorker
from theogony.reporting.models import OneirosTickReport, RunReportBase
from theogony.stores import InMemoryKnowledgeStore


class _ReportWriterStub:
    def __init__(self) -> None:
        self.written_reports: list[RunReportBase] = []

    def write(self, report: RunReportBase) -> Path:
        self.written_reports.append(report)
        return Path(f"/tmp/oneiros-{report.run_id}.json")

    def directory_for(self, report_type: str) -> Path:  # pragma: no cover
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
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
async def store_with_seed_nodes() -> InMemoryKnowledgeStore:
    store = InMemoryKnowledgeStore()
    for i in range(3):
        await store.upsert_node(_node(f"seed-{i}"))
    return store


@pytest.mark.asyncio
async def test_tick_reads_ephemera_writes_one_report(
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
    assert report.nodes_promoted == 0
    assert report.nodes_degraded == 0
    assert report.duration_s >= 0.0
