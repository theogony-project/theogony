"""Minimal FastAPI app: bundled seed + Iris cockpit only (PHX-0074)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from theogony.agents.llm import StubLLMProvider
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.cockpit import mount_cockpit
from theogony.config.logging import get_logger, setup_logging
from theogony.config.settings import EmbeddingSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.curiosity.stub_detector import StubDetector
from theogony.docs_ingest import read_dump
from theogony.extraction.audit import ExtractionAuditLog
from theogony.reporting.writer import RunReportWriter
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore

log = get_logger("cockpit.standalone")


class _TinyEmbedder:
    @property
    def model_id(self) -> str:
        return "cockpit-standalone@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings(embedding=EmbeddingSettings(dim=4, model_id="cockpit-standalone@v1"))
    setup_logging(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.run_reports_dir.mkdir(parents=True, exist_ok=True)
    audit = ExtractionAuditLog(settings.data_dir / "audit.sqlite")
    audit.__enter__()
    store = InMemoryKnowledgeStore()
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    node_objs = [n for n in nodes if isinstance(n, KnowledgeNode)]
    edge_objs = [e for e in edges if isinstance(e, KnowledgeEdge)]
    await store.batch_upsert_nodes(node_objs)
    await store.batch_upsert_edges(edge_objs)
    embedder = _TinyEmbedder()
    llm = StubLLMProvider(default="cockpit standalone")
    writer = RunReportWriter(settings.run_reports_dir)
    app.state.settings = settings
    app.state.audit = audit
    app.state.embedder = embedder
    app.state.llm = llm
    app.state.store = store
    app.state.report_writer = writer
    app.state.stub_detector = StubDetector(settings.curiosity.stub_thresholds)
    app.state.mnemosyne_classifier = build_mnemosyne_classifier(settings, llm)
    app.state.oneiros = None
    app.state.oneiros_task = None
    if settings.cockpit.enabled:
        mount_cockpit(app, settings)
        log.info("cockpit standalone at http://%s/cockpit/", settings.cockpit.bind_host)
    try:
        yield
    finally:
        audit.__exit__(None, None, None)


app = FastAPI(title="Theogony Cockpit", lifespan=_lifespan)
__all__ = ["app"]
