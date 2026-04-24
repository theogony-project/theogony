"""
W7-B living-demo gate: stub Gutenberg adapter + real IngestionPipeline + InMemory store.

No Gutendex HTTP and no paid LLM — the ``FakeWikidataClient`` fixture data
from ``test_extraction_pipeline`` matches the bundled Hedin-shaped raw
content. Argus + HestiaLite + ``RealIngestRunner`` run for real; only the
acquisition transport is replaced by an in-process stub.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_extraction_pipeline import (
    FakeWikidataClient,
    _hedin_raw,
    _hedin_responses,
)
from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.agents.argus import ArgusAgent, ArgusOutcome, ArgusSettings
from theogony.agents.argus_ingest_runner import RealIngestRunner
from theogony.agents.hestia_lite import HestiaLiteApproval
from theogony.clustering.cluster_index import ClusterIndex
from theogony.config.settings import HestiaLiteSettings, Settings
from theogony.curiosity.dispatcher import CuriosityDispatcher
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
    TriggerReason,
)
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.resolve import EntityResolver
from theogony.reporting.models import RegionDescriptor
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore


class _StubGutenbergAdapter:
    """Returns one Hedin-shaped candidate and the canonical test raw bytes."""

    @property
    def source_type(self) -> str:
        return "gutenberg"

    def supports(self, source_type: str) -> bool:
        return source_type == "gutenberg"

    async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
        del query, limit
        return [
            SourceCandidate(
                source_type="gutenberg",
                identifier="944",
                title="Seven Years in Tibet and Central Asia",
                authors=["Hedin, Sven"],
                languages=["en"],
                download_url="https://example.org/pg944.txt",
                metadata={"copyright": False, "download_count": 120},
            )
        ]

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        del candidate
        return _hedin_raw()

    async def aclose(self) -> None:
        return None


@pytest.mark.living_demo
async def test_argus_happy_path_smoke(tmp_path: Path) -> None:
    """W7-B demo path: one pending curiosity report → stub acquire → ingest → disk update."""
    store = InMemoryKnowledgeStore()
    client = FakeWikidataClient(_hedin_responses())
    resolver = EntityResolver(client=client)  # type: ignore[arg-type]
    cluster_index = ClusterIndex()
    await cluster_index.rebuild_from_store(store)
    pipeline = IngestionPipeline(
        entity_resolver=resolver,
        store=store,
        settings=Settings(),
        cluster_index=cluster_index,
        ner_sentence_limit=80,
    )
    runner = RealIngestRunner(pipeline)

    trig = CuriosityTrigger(
        origin_query="Who was Sven Hedin?",
        origin_query_run_id="query-run-1",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2, 0.3], seed_node_count=0),
        stub_signal_strength=0.9,
        proposed_acquisition_spec=AcquisitionSpec(search_query="Sven Hedin Tibet exploration"),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.WEAK_ANSWER,
        answer_verdict="partial",
        cited_node_count=0,
    )
    t0 = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 24, 12, 0, 2, tzinfo=UTC)
    report = CuriosityRunReport(
        started_at=t0,
        finished_at=t1,
        duration_s=2.0,
        status="completed",
        verdict="good",
        verdict_reasoning="curiosity trigger emitted",
        trigger=trig,
    )
    writer = RunReportWriter(tmp_path)
    path = writer.write(report)

    argus = ArgusAgent(
        adapter=_StubGutenbergAdapter(),
        hestia=HestiaLiteApproval(HestiaLiteSettings()),
        ingest_runner=runner,
        settings=ArgusSettings(enabled=True, min_candidate_score=0.0, search_limit=5),
    )
    dispatcher = CuriosityDispatcher(reports_dir=tmp_path, argus=argus, writer=writer)
    results = await dispatcher.process_pending(max_triggers=1, dry_run=False)

    assert len(results) == 1
    assert results[0].outcome == ArgusOutcome.APPROVED_AND_INGESTED
    assert results[0].bytes_acquired > 0
    assert results[0].decision.ingest_run_id is not None

    on_disk = CuriosityRunReport.model_validate_json(path.read_text(encoding="utf-8"))
    assert on_disk.decision.ingest_run_id == results[0].decision.ingest_run_id
    assert on_disk.bytes_acquired == results[0].bytes_acquired
    assert on_disk.decision.hestia_status == "approved"
