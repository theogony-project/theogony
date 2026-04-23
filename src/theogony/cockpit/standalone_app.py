"""Minimal FastAPI app: bundled seed + Iris cockpit only (PHX-0074).

The standalone cockpit now ships with the **real BGE-small embedder** so the
bundled `pantheon_self` seed (which already carries 384-dim BGE vectors) is
queryable by meaning, and an **OfflineAnswerSynthesizer** so the answer
panel shows real citation-anchored snippets — not a stub placeholder. There
is still no LLM prose (use ``theogony serve`` for that), but the Explorer
finally feels useful out of the box.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from theogony.agents.llm import StubLLMProvider
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.cockpit import mount_cockpit
from theogony.config.logging import get_logger, setup_logging
from theogony.config.settings import EmbeddingSettings, LLMSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.curiosity.stub_detector import StubDetector
from theogony.docs_ingest import read_dump
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.reporting.writer import RunReportWriter
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore

log = get_logger("cockpit.standalone")


class _ConstantEmbedder:
    """Last-ditch fallback when sentence-transformers cannot load (offline CI).

    Returns a constant vector matching the seed's BGE dim so cosine still
    runs without dimension errors. The Explorer will look "lifeless"
    because every query gets identical scores — but it will not crash.
    """

    @property
    def model_id(self) -> str:
        return "cockpit-standalone-fallback@v1"

    @property
    def dim(self) -> int:
        return 384

    async def embed(self, text: str) -> list[float]:
        return [0.0] * self._dim_int()

    def _dim_int(self) -> int:
        return self.dim

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def _build_embedder(settings: Settings) -> object:
    """BGE-small if loadable; otherwise a 384-dim constant fallback."""
    cache_dir = settings.data_dir / "st_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        return LocalSentenceTransformerEmbedder(cache_folder=str(cache_dir))
    except Exception as exc:  # pragma: no cover - environmental
        log.warning("falling back to constant embedder: %s", exc)
        return _ConstantEmbedder()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings(
        embedding=EmbeddingSettings(dim=384, model_id="BAAI/bge-small-en-v1.5@v1"),
        llm=LLMSettings(provider="stub"),
    )
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
    embedder = _build_embedder(settings)
    llm = StubLLMProvider(default="(stub: no LLM configured)")
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
        log.info(
            "cockpit standalone at http://%s/cockpit/  embedder=%s",
            settings.cockpit.bind_host,
            getattr(embedder, "model_id", type(embedder).__name__),
        )
    try:
        yield
    finally:
        audit.__exit__(None, None, None)


app = FastAPI(title="Theogony Cockpit", lifespan=_lifespan)
__all__ = ["app"]
