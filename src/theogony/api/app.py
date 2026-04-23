"""
FastAPI application + lifespan (Plan §4.4, §3.7; E9).

The lifespan is the **single owner** of long-lived resources: settings,
audit log, embedder, LLM client, store, report writer. It owns the
``OneirosWorker`` slot conditionally — E9 wires the slot but does not
populate it (E8.5 will). Routes consume these via FastAPI ``Depends(...)``
so tests can override per-request without monkeypatching.

The deliberate manual ``__enter__`` / ``__aenter__`` / ``__exit__`` /
``__aexit__`` calls (rather than nested ``with`` / ``async with`` blocks)
are required because the lifespan needs to keep all resources alive
across the ``yield`` and only tear them down in the ``finally``. The
brief documents this choice; do not refactor to ``AsyncExitStack``
unless mypy or a real concurrency bug forces it.

Embedder warm-up is intentional: the BGE-small model lazy-loads on
first ``embed`` call (~33 MB / few hundred ms). Loading it during
startup makes the first ``/query`` request honest about latency
budgets (Plan §4.2 p95 < 2 s).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.api.routes import (
    health_router,
    ingest_router,
    node_router,
    query_router,
)
from theogony.clustering.cluster_index import ClusterIndex
from theogony.config.logging import get_logger, setup_logging
from theogony.config.settings import Settings
from theogony.curiosity.stub_detector import StubDetector
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.memory.oneiros import OneirosWorker
from theogony.reporting.writer import RunReportWriter
from theogony.stores.neo4j_store import Neo4jKnowledgeStore

log = get_logger("api.app")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire the long-lived resources for the FastAPI surface.

    Startup ordering matters: settings → audit (synchronous open) →
    embedder warm-up (load + one-shot embed) → LLM factory (validates
    keys without calling out) → Neo4j store (opens the Bolt
    connection + ensures schema) → report writer.

    Shutdown reverses the order. The ``OneirosWorker`` background
    task (``app.state.oneiros_task``) is cancelled first; the
    ``contextlib.suppress(CancelledError)`` plus
    ``asyncio.wait_for(..., timeout=5.0)`` enforce the Plan §4.4
    graceful-shutdown budget. E8.5 fills the slot the E9 lifespan
    wired as a conditional; the conditional shape stays for forward
    compatibility (e.g. tests that swap the worker out).
    """
    settings = Settings()
    setup_logging(settings)

    # Audit log: synchronous context manager. We open it via __enter__
    # so the connection survives across the lifespan yield.
    audit = ExtractionAuditLog(settings.data_dir / "audit.sqlite")
    audit.__enter__()

    # Wikidata cache (W6, PR #33): one persistent SQLite per data_dir,
    # opt-out via THEOGONY_WIKIDATA_CACHE__ENABLED=false. Same lifespan
    # ownership pattern as the audit log so background ingest tasks
    # share one connection.
    wd_cache: WikidataCache | None = None
    if settings.wikidata_cache.enabled:
        wd_cache = WikidataCache(settings.wikidata_cache_path)
        wd_cache.__enter__()

    embedder = LocalSentenceTransformerEmbedder(
        model_id=settings.embedding.model_id,
        dim=settings.embedding.dim,
    )
    # Eager warm-up: makes the first /query honest about latency.
    await embedder.embed("warmup")

    llm = build_llm_from_settings(settings)

    # Neo4j store: async context manager. We open it via __aenter__ so
    # the driver + schema bootstrap survive across the lifespan yield.
    store = Neo4jKnowledgeStore(settings.neo4j, embedding_dim=embedder.dim)
    await store.__aenter__()

    report_writer = RunReportWriter(settings.run_reports_dir)

    cluster_index = ClusterIndex()
    await cluster_index.rebuild_from_store(store)

    app.state.settings = settings
    app.state.audit = audit
    app.state.wikidata_cache = wd_cache
    app.state.embedder = embedder
    app.state.llm = llm
    app.state.store = store
    app.state.report_writer = report_writer
    app.state.cluster_index = cluster_index
    app.state.stub_detector = StubDetector(settings.curiosity.stub_thresholds)
    app.state.mnemosyne_classifier = build_mnemosyne_classifier(settings, llm)

    # OneirosWorker slot (E8.5): owns the §4.3 write-back lifecycle.
    # The lifespan owns the long-lived task; shutdown cancels it
    # within the §4.4 5-second budget (see the finally block below).
    worker = OneirosWorker(store, settings, report_writer, cluster_index=cluster_index)
    app.state.oneiros = worker
    app.state.oneiros_task = asyncio.create_task(worker.run())

    log.info(
        "api lifespan: startup complete (store=neo4j embedding_dim=%d)",
        settings.embedding.dim,
    )
    try:
        yield
    finally:
        if app.state.oneiros_task is not None:
            app.state.oneiros_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(app.state.oneiros_task, timeout=5.0)
        await app.state.store.__aexit__(None, None, None)
        if hasattr(app.state.llm, "aclose"):
            await app.state.llm.aclose()
        if app.state.wikidata_cache is not None:
            app.state.wikidata_cache.__exit__(None, None, None)
        app.state.audit.__exit__(None, None, None)
        log.info("api lifespan: shutdown complete")


def create_app() -> FastAPI:
    """Construct the FastAPI app with all routers wired.

    Exposed as a factory so tests can build a fresh app per session
    (lifespan + DI overrides). Production uses the module-level
    ``app`` instance below.
    """
    fastapi_app = FastAPI(
        title="Theogony",
        description="A living vector-graph knowledge network.",
        version=_get_version(),
        lifespan=lifespan,
    )
    fastapi_app.include_router(health_router)
    fastapi_app.include_router(query_router)
    fastapi_app.include_router(node_router)
    fastapi_app.include_router(ingest_router)
    return fastapi_app


def _get_version() -> str:
    """Lazy import to avoid widening the api/app.py import surface unnecessarily."""
    from theogony import __version__

    return __version__


#: Module-level app instance — what ``uvicorn theogony.api.app:app`` looks for.
app = create_app()


__all__ = ["app", "create_app", "lifespan"]
