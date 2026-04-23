"""
Shared FastAPI test fixtures (Plan §3.8 layer 4).

Builds an isolated FastAPI app per test session that uses
``InMemoryKnowledgeStore`` + ``StubLLMProvider`` instead of the
production Neo4j + Gemini lifespan resources. Tests override the
DI dependencies surgically via ``app.dependency_overrides`` rather
than monkeypatching modules — this is the FastAPI-recommended
pattern and keeps the production code paths untouched.

Why we don't run the real ``lifespan``: the production lifespan
opens a Bolt connection, downloads BGE-small, and validates the
Gemini key. None of those should run for a /query unit test.
``LIFESPAN_DISABLED_APP`` is the offline shadow.
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
    """4-dim constant-axis embedder for API tests.

    Production uses BGE-small (384-dim) — irrelevant for API
    contract assertions. The InMemoryKnowledgeStore does not enforce
    a fixed dim (Neo4j does, but we use InMemory in tests), so a
    short visual vector keeps fixtures readable.
    """

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
    """A fresh empty in-memory store per test (no leakage)."""
    return InMemoryKnowledgeStore()


@pytest.fixture
def api_llm() -> StubLLMProvider:
    """Stub LLM with a default placeholder; tests can override per case."""
    return StubLLMProvider(default="placeholder answer with no citations")


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    """Settings rooted at tmp_path so audit / reports stay test-local.

    ``run_reports_dir`` is a derived property on Settings (it equals
    ``data_dir / "run_reports"``); we only set ``data_dir`` and the
    derived path follows.

    ``embedding.dim`` matches :class:`_TinyEmbedder` (4) so Explorer append
    and query paths do not trip the Neo4j dim guard in CI.
    """
    settings = Settings(
        data_dir=tmp_path / "data",
        embedding=EmbeddingSettings(dim=4, model_id="test-embed@v1"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.run_reports_dir.mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
def api_audit(tmp_path: Path) -> Iterator[ExtractionAuditLog]:
    """Per-test audit log, opened + closed around the test body."""
    with ExtractionAuditLog(tmp_path / "audit.sqlite") as audit:
        yield audit


@pytest.fixture
def api_app(
    api_store: InMemoryKnowledgeStore,
    api_llm: StubLLMProvider,
    api_settings: Settings,
    api_audit: ExtractionAuditLog,
) -> Iterator[FastAPI]:
    """Build a FastAPI app with the lifespan resources injected directly.

    We **bypass** the production lifespan (no Bolt / no BGE download /
    no Gemini key validation) by constructing a vanilla FastAPI() with
    no lifespan and wiring the same routers + state directly. The DI
    overrides point routes at the in-memory deps; ``app.state``
    carries the per-app handles the dependencies introspect.
    """
    app = FastAPI(title="Theogony test app")
    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(node_router)
    app.include_router(ingest_router)

    # Inject the lifespan resources.
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

    # DI overrides — these win even if the lifespan ran (which it did
    # not). Tests targeting the lifespan itself reach into app.state
    # directly.
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
        )

    app.dependency_overrides[get_query_pipeline] = _make_pipeline

    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def api_client(api_app: FastAPI) -> Iterator[TestClient]:
    """A starlette ``TestClient`` against the offline app.

    NB: ``TestClient`` does NOT trigger the lifespan when the app is
    used inside ``with TestClient(app):`` (it does when constructed
    directly, but our app.state is already populated). We use the
    fixture-injected resources path; the lifespan path has its own
    dedicated test (``test_api_lifespan.py``).
    """
    with TestClient(api_app) as client:
        yield client


# Mark the module as containing only async-friendly fixtures; specific
# test files opt into asyncio.
__all__: list[str] = []
_ = AsyncIterator  # silence unused-import warning; future async fixtures will use it
