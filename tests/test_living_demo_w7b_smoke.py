"""
W7-B living-demo gate: stub Gutenberg adapter + real IngestionPipeline + InMemory store.

No Gutendex HTTP and no paid LLM — the ``FakeWikidataClient`` fixture data
from ``test_extraction_pipeline`` matches the bundled Hedin-shaped raw
content. Argus + HestiaLite + ``RealIngestRunner`` run for real; only the
acquisition transport is replaced by an in-process stub.

W11: the demo path runs Argus with planner + evaluator enabled (StubLLM),
Wikidata acquisition via the fake client ``search`` surface, and the legacy
Gutenberg adapter for executor wiring only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import trafilatura

from tests.test_extraction_pipeline import (
    FakeWikidataClient,
    _hedin_raw,
    _hedin_responses,
)
from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.agents.argus import ArgusOutcome
from theogony.agents.argus_ingest_runner import RealIngestRunner
from theogony.agents.llm import ResearchPlannerCost, StubLLMProvider
from theogony.clustering.cluster_index import ClusterIndex
from theogony.config.settings import Settings
from theogony.curiosity.argus_wiring import make_argus_agent
from theogony.curiosity.dispatcher import CuriosityDispatcher
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    ResearchStep,
    ResearchStepKind,
    TriggerBudget,
    TriggerReason,
)
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_client import WikidataCandidate
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


class _StubWikipediaAdapter:
    """Offline Wikipedia surface for the living-demo gate (W12)."""

    @property
    def source_type(self) -> str:
        return "wikipedia"

    def supports(self, source_type: str) -> bool:
        return source_type == "wikipedia"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        del query, limit
        return [
            SourceCandidate(
                source_type="wikipedia",
                identifier="Sven_Hedin",
                title="Sven Hedin",
                authors=[],
                languages=["en"],
                url="https://en.wikipedia.org/wiki/Sven_Hedin",
                download_url="https://en.wikipedia.org/wiki/Sven_Hedin",
                metadata={
                    "wikipedia_lang": "en",
                    "wikipedia_pageid": 529134,
                    "estimated_bytes": 500,
                    "summary": "explorer",
                },
            )
        ]

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        fixture = Path(__file__).resolve().parent / "fixtures" / "wikipedia_sample.html"
        html = fixture.read_text(encoding="utf-8")
        text = trafilatura.extract(html, url="https://en.wikipedia.org/wiki/Sven_Hedin") or ""
        return RawContent(
            source_type="wikipedia",
            identifier=candidate.identifier,
            title=candidate.title,
            language="en",
            content=text,
            content_format="text/plain; charset=utf-8",
            url=candidate.url,
            bytes_acquired=len(text.encode("utf-8")),
            metadata={"wikipedia_lang": "en", "wikidata_qid": "Q154759"},
        )

    async def aclose(self) -> None:
        return None


class _UnusedWebAdapter:
    @property
    def source_type(self) -> str:
        return "web"

    def supports(self, source_type: str) -> bool:
        return source_type == "web"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        raise NotImplementedError

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        raise AssertionError(candidate)

    async def aclose(self) -> None:
        return None


class _LivingDemoLLM(StubLLMProvider):
    """Stub planner + evaluator JSON for the living-demo gate."""

    def __init__(self) -> None:
        super().__init__(default="")
        self.add_response(
            '{"origin_query"',
            json.dumps({"selected": [1], "rejected": [], "rationale": "living_demo"}),
        )

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type,
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[object, ResearchPlannerCost]:
        del system_prompt, user_prompt, max_search_calls, max_total_tokens
        steps = [
            ResearchStep(
                kind=ResearchStepKind.WIKIDATA_LOOKUP,
                target="Sven",
                rationale="living_demo deterministic planner",
            ),
            ResearchStep(
                kind=ResearchStepKind.WIKIPEDIA_FETCH,
                target="Sven Hedin",
                rationale="living_demo wikipedia step",
            ),
        ]
        body = output_schema(steps=steps)
        cost = ResearchPlannerCost(
            usd_cost=0.0, eur_cost=0.0, search_call_count=0, model_id=self.model_id
        )
        return body, cost


@pytest.mark.living_demo
async def test_argus_happy_path_smoke(tmp_path: Path) -> None:
    """W7-B demo path: one pending curiosity report → stub acquire → ingest → disk update."""
    store = InMemoryKnowledgeStore()
    hed = _hedin_responses()
    search = dict(hed.search)
    search[("Sven", "en")] = [
        WikidataCandidate(
            qid="Q154759",
            label="Sven Hedin",
            description="Swedish explorer",
            match_text=None,
            language="en",
        )
    ]
    responses = hed.model_copy(update={"search": search})
    client = FakeWikidataClient(responses)
    resolver = EntityResolver(client=client)  # type: ignore[arg-type]
    cluster_index = ClusterIndex()
    await cluster_index.rebuild_from_store(store)
    demo_settings = Settings().model_copy(
        update={
            "data_dir": tmp_path,
            "curiosity": Settings().curiosity.model_copy(
                update={
                    "research_planner": Settings().curiosity.research_planner.model_copy(
                        update={"enabled": True}
                    ),
                    "evaluator": Settings().curiosity.evaluator.model_copy(
                        update={"enabled": True}
                    ),
                    "hestia_sentinel": Settings().curiosity.hestia_sentinel.model_copy(
                        update={"enabled": True, "llm_fallback_enabled": False}
                    ),
                }
            ),
        }
    )
    (demo_settings.run_reports_dir / "query").mkdir(parents=True, exist_ok=True)
    pipeline = IngestionPipeline(
        entity_resolver=resolver,
        store=store,
        settings=demo_settings,
        cluster_index=cluster_index,
        ner_sentence_limit=80,
    )
    runner = RealIngestRunner(pipeline)

    trig = CuriosityTrigger(
        origin_query="Sven Hedin explored Tibet",
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

    llm = _LivingDemoLLM()
    argus = make_argus_agent(
        settings=demo_settings,
        adapter=_StubGutenbergAdapter(),
        ingest_runner=runner,
        llm=llm,
        wd_client=client,  # type: ignore[arg-type]
        wikipedia=_StubWikipediaAdapter(),
        web_fetch=_UnusedWebAdapter(),
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
    assert on_disk.trigger.research_plan is not None
    assert len(on_disk.trigger.research_plan.steps) >= 2
    kinds = {s.kind for s in on_disk.trigger.research_plan.steps}
    assert ResearchStepKind.WIKIDATA_LOOKUP in kinds
    assert ResearchStepKind.WIKIPEDIA_FETCH in kinds
    assert on_disk.evaluator_decision is not None
