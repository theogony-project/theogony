"""
Shared FastAPI test fixtures (Plan §3.8 layer 4).

PHX-0074: when ``settings.cockpit.enabled`` is true (the default),
``mount_cockpit`` is applied so ``tests/cockpit`` shares the same
``api_app`` fixture without relying on a sibling-only ``conftest.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from theogony.agents.llm import StubLLMProvider
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.api.dependencies import get_query_pipeline, get_settings, get_store
from theogony.api.routes import (
    health_router,
    ingest_router,
    node_router,
    query_router,
)
from theogony.cockpit import mount_cockpit
from theogony.config.settings import EmbeddingSettings, Settings
from theogony.curiosity.stub_detector import StubDetector
from theogony.extraction.audit import ExtractionAuditLog
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores import InMemoryKnowledgeStore


class _TinyEmbedder:
    @property
    def model_id(self) -> str:
        return "test-embedder@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


@pytest.fixture
def api_store() -> InMemoryKnowledgeStore:
    return InMemoryKnowledgeStore()


@pytest.fixture
def api_llm() -> StubLLMProvider:
    return StubLLMProvider(default="placeholder answer with no citations")


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        data_dir=tmp_path / "data",
        embedding=EmbeddingSettings(dim=4, model_id="test-embed@v1"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.run_reports_dir.mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
def api_audit(tmp_path: Path) -> Iterator[ExtractionAuditLog]:
    with ExtractionAuditLog(tmp_path / "audit.sqlite") as audit:
        yield audit


@pytest.fixture
def api_app(
    api_store: InMemoryKnowledgeStore,
    api_llm: StubLLMProvider,
    api_settings: Settings,
    api_audit: ExtractionAuditLog,
) -> Iterator[FastAPI]:
    app = FastAPI(title="Theogony test app")
    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(node_router)
    app.include_router(ingest_router)

    embedder = _TinyEmbedder()
    app.state.settings = api_settings
    app.state.audit = api_audit
    app.state.embedder = embedder
    app.state.llm = api_llm
    app.state.store = api_store
    app.state.report_writer = RunReportWriter(api_settings.run_reports_dir)
    app.state.stub_detector = StubDetector(api_settings.curiosity.stub_thresholds)
    app.state.mnemosyne_classifier = build_mnemosyne_classifier(api_settings, api_llm)
    app.state.oneiros = None
    app.state.oneiros_task = None

    app.dependency_overrides[get_settings] = lambda: api_settings
    app.dependency_overrides[get_store] = lambda: api_store

    def _make_pipeline() -> QueryPipeline:
        return QueryPipeline(
            embedder=embedder,
            retriever=MultiHopRetriever(
                api_store,
                strategy=build_retrieval_strategy(api_store, api_settings),
            ),
            assembler=ConstellationAssembler(api_store),
            synthesizer=AnswerSynthesizer(api_llm, audit_log=api_audit),
            relevance=RelevanceTracker(
                api_store,
                relevance_delta=api_settings.relevance.relevance_delta,
            ),
            settings=api_settings,
            report_writer=app.state.report_writer,
            mnemosyne=build_mnemosyne_classifier(api_settings, api_llm),
            entry_planner_llm=api_llm,
        )

    app.dependency_overrides[get_query_pipeline] = _make_pipeline

    if api_settings.cockpit.enabled:
        mount_cockpit(app, api_settings)

    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def api_client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as client:
        yield client


__all__: list[str] = []
_ = AsyncIterator
