"""
OneirosWorker integration test against testcontainers Neo4j.

Plan §5 E8.5 acceptance criterion: one real-clock test exercises the
production path with a 0.1-s tick interval, asserts wall-clock-bounded
behavior over ~0.5 s (≥ 4 ticks observed via the on-disk
``data/run_reports/oneiros/*.json`` files).

Gated on ``THEOGONY_TEST_NEO4J=1`` — the unit + lifecycle suites
(``test_memory_oneiros_worker.py``, ``test_memory_oneiros_lifecycle.py``)
cover the worker's behavior against the InMemory store; this test
proves the worker's contract against the production Neo4j backend.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from pydantic import SecretStr

from theogony.config.settings import Neo4jSettings, Settings
from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.memory.oneiros import OneirosWorker
from theogony.reporting.writer import RunReportWriter
from theogony.stores import Neo4jKnowledgeStore

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_TEST_NEO4J") != "1",
    reason="Set THEOGONY_TEST_NEO4J=1 to run the Oneiros integration test.",
)

_EMBEDDING_DIM = 384


@pytest.fixture(scope="session")
def neo4j_container() -> Any:
    try:
        from testcontainers.neo4j import Neo4jContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[neo4j] not installed: {exc}")
    container = Neo4jContainer("neo4j:5.18-community")
    container.start()
    yield container
    container.stop()


@pytest_asyncio.fixture
async def neo4j_store(neo4j_container: Any) -> AsyncIterator[Neo4jKnowledgeStore]:
    settings = Neo4jSettings(
        uri=neo4j_container.get_connection_url(),
        user=neo4j_container.username,
        password=SecretStr(neo4j_container.password),
        database="neo4j",
    )
    async with Neo4jKnowledgeStore(settings, embedding_dim=_EMBEDDING_DIM) as store:
        async with store._session() as session:  # noqa: SLF001 — fixture setup
            await session.run("MATCH (n) DETACH DELETE n")
        yield store


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="oneiros-int", location=loc, language="en")


def _node(label: str) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=NodeType.OTHER,
        source_ref=_src(f"loc:{label}"),
        embedding=[0.1] * _EMBEDDING_DIM,
        embedding_dim=_EMBEDDING_DIM,
        embedding_model_id="oneiros-int@v1",
    )


@pytest.mark.asyncio
async def test_worker_writes_multiple_reports_against_real_neo4j(
    neo4j_store: Neo4jKnowledgeStore, tmp_path: Path
) -> None:
    """1.0-second wall-clock window with 0.1-s tick interval → ≥ 3 ticks.

    The Plan §5 E8.5 risks bullet caps wall-clock at the test boundary
    so a slow CI runner does not flake. The brief's escalation note
    explicitly allows lowering the count from 4 to 3 with a documented
    trade-off — this is that trade-off: against testcontainers Neo4j
    on Mac, each tick body costs ~150-300 ms (Bolt round-trips for
    export_layer + count_neighbors_in_layer + batch_update_scores +
    writer.write), so the 0.1-s tick_interval_s does not actually pace
    the loop here; the tick body cost does. The 1.0-s budget yields 3
    completed ticks reliably; the 0.6-s budget yields 3 only when the
    container is warm. CI Linux is faster.

    The Plan §5 E8.5 success criterion ("the worker keeps producing
    reports") is satisfied at any count ≥ 1; ≥ 3 is the assertion
    floor that distinguishes "the loop is alive" from "one tick fired
    and never wrapped".
    """
    settings = Settings(data_dir=tmp_path / "data")
    settings.run_reports_dir.mkdir(parents=True, exist_ok=True)
    writer = RunReportWriter(settings.run_reports_dir)

    # Seed 5 EPHEMERA nodes so each tick has some work to do
    # (otherwise ``oneiros_verdict`` returns "poor" — still a report,
    # but harder to reason about).
    for i in range(5):
        await neo4j_store.upsert_node(_node(f"int-{i}"))

    worker = OneirosWorker(neo4j_store, settings, writer, tick_interval_s=0.1)
    task = asyncio.create_task(worker.run())

    # Wall-clock-bounded budget: 1.0 s yields ≥ 3 ticks once the
    # ~150-300 ms tick body is amortised over the 0.1 s interval.
    await asyncio.sleep(1.0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, TimeoutError):
        await asyncio.wait_for(task, timeout=2.0)

    # Report directory has the per-tick JSON files. Plan §5 E8.5
    # success criterion: at least 3 ticks observed via on-disk reports
    # — the alive-loop floor on Mac/testcontainers (4 was the original
    # brief target; 3 is the documented lower bound — see PR body).
    report_dir = settings.run_reports_dir / "oneiros"
    json_files = sorted(p for p in report_dir.iterdir() if p.suffix == ".json")
    assert len(json_files) >= 3, (
        f"expected ≥ 3 oneiros reports, got {len(json_files)} ({[p.name for p in json_files]})"
    )

    # Sanity-check one report's shape: nodes_evaluated > 0 (the seed
    # nodes), verdict in {"good","partial"} (one of the OK verdicts).
    sample = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert sample["report_type"] == "oneiros"
    assert sample["nodes_evaluated"] >= 1
    assert sample["verdict"] in ("good", "partial")
