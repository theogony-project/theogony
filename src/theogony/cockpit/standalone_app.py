"""Minimal FastAPI app: Iris cockpit + Chronicle store (PHX-0074).

Loads **full** :class:`~theogony.config.settings.Settings` from the environment
(same as ``theogony serve`` for LLM keys and ``THEOGONY_LLM__*``), but pins
**384-dim BGE** embeddings so the bundled ``pantheon_self`` seed stays
vector-compatible when the DB is empty.

By default the chronicle backend is **in-memory** (Neo4j retired; see
``docs/etappes/RETIREMENT_NEO4J_MULTIHOP.md``). The bundled ``pantheon_self``
seed is loaded on every startup.
If ``build_llm_from_settings`` succeeds (e.g. ``ANTHROPIC_API_KEY``
set with provider ``anthropic``), the Explorer uses **real LLM synthesis**;
otherwise it falls back to **stub** + offline citation snippets so the app still
starts without secrets.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from theogony.cockpit.mesh_explorer import MeshExplorerService

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.cockpit import mount_cockpit
from theogony.config.logging import get_logger, setup_logging
from theogony.config.settings import EmbeddingSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.core.store import KnowledgeStore
from theogony.curiosity.stub_detector import StubDetector
from theogony.docs_ingest import read_dump
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.reporting.writer import RunReportWriter
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore

log = get_logger("cockpit.standalone")

_SEED_EMBEDDING = EmbeddingSettings(dim=384, model_id="BAAI/bge-small-en-v1.5")


def _standalone_settings() -> Settings:
    """Env-backed settings with embedding forced to the pantheon_self BGE layout."""
    base = Settings()
    return base.model_copy(update={"embedding": _SEED_EMBEDDING})


def _standalone_llm(settings: Settings) -> LLMProvider:
    try:
        llm = build_llm_from_settings(settings)
    except (ValueError, ImportError, NotImplementedError) as exc:
        log.warning(
            "cockpit standalone: no live LLM (%s); using StubLLMProvider",
            exc,
        )
        return StubLLMProvider(
            model_id=settings.llm.model_id or "stub-llm",
            default=(
                "(stub: set OPENAI_API_KEY, or ANTHROPIC for Claude-only, "
                "or THEOGONY_LLM__PROVIDER=stub)"
            ),
        )
    if isinstance(llm, StubLLMProvider):
        log.info("cockpit standalone: LLM provider is stub (THEOGONY_LLM__PROVIDER=stub)")
    else:
        log.info(
            "cockpit standalone: live LLM provider=%s model_id=%s",
            settings.llm.provider,
            getattr(llm, "model_id", type(llm).__name__),
        )
    return llm


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


def _resolve_mesh_root(settings: Settings) -> Path | None:
    """Configured cockpit.mesh_root, else auto-detect a seeded subnet (prefers 100k)."""
    configured = settings.cockpit.mesh_root
    if configured is not None:
        # A configured path resolves against the CWD (an operator-supplied path), not data_dir.
        return Path(configured).expanduser().resolve()
    for name in ("mesh-wiki-100k", "mesh-wiki-v1", "mesh"):
        candidate = settings.data_dir / name
        if (candidate / "lance").exists():
            return candidate
    return None


def _build_mesh_explorer(settings: Settings) -> MeshExplorerService | None:
    """Open the Mesh Explorer service when a non-empty mesh workspace is available."""
    root = _resolve_mesh_root(settings)
    if root is None or not (root / "lance").exists():
        log.info("cockpit standalone: no mesh workspace found; Mesh Explorer tab disabled")
        return None
    from theogony.cockpit.mesh_explorer import MeshExplorerService

    service = MeshExplorerService(root, embedder_name=settings.cockpit.mesh_embedder)
    if not service.has_data():
        log.info("cockpit standalone: mesh workspace %s has no edges; Mesh tab disabled", root)
        return None
    status = service.status()
    log.info(
        "cockpit standalone: Mesh Explorer enabled at %s (%d nodes, %d edges; "
        "activation index builds lazily on first query)",
        root,
        status["consolidated_nodes"],
        status["mesh_edges"],
    )
    return service


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = _standalone_settings()
    setup_logging(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.run_reports_dir.mkdir(parents=True, exist_ok=True)
    audit = ExtractionAuditLog(settings.data_dir / "audit.sqlite")
    audit.__enter__()
    store: KnowledgeStore
    try:
        store = InMemoryKnowledgeStore()
        _, nodes, edges = read_dump(pantheon_self_dump_path())
        node_objs = [n for n in nodes if isinstance(n, KnowledgeNode)]
        edge_objs = [e for e in edges if isinstance(e, KnowledgeEdge)]
        await store.batch_upsert_nodes(node_objs)
        await store.batch_upsert_edges(edge_objs)
        log.info(
            "cockpit standalone: loaded pantheon_self seed (%d nodes)",
            len(node_objs),
        )
        embedder = _build_embedder(settings)
        llm = _standalone_llm(settings)
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
        app.state.mesh_explorer = _build_mesh_explorer(settings)
        mesh_svc = app.state.mesh_explorer
        if mesh_svc is not None:

            async def _warm_mesh() -> None:
                try:
                    ms = await mesh_svc.ensure_index()
                    if ms > 0:
                        log.info("mesh explorer: background index warmup in %d ms", ms)
                    else:
                        log.info("mesh explorer: activation index already cached")
                    t0 = time.perf_counter()
                    await mesh_svc.embed("warmup probe")
                    embed_ms = int((time.perf_counter() - t0) * 1000.0)
                    log.info("mesh explorer: embedder warmup in %d ms", embed_ms)
                except Exception:  # pragma: no cover - best-effort warmup
                    log.exception("mesh explorer: background warmup failed")

            asyncio.create_task(_warm_mesh())
        if settings.cockpit.enabled:
            mount_cockpit(app, settings)
            log.info(
                "cockpit standalone at http://%s/cockpit/  store=memory embedder=%s",
                settings.cockpit.bind_host,
                getattr(embedder, "model_id", type(embedder).__name__),
            )
        yield
    finally:
        audit.__exit__(None, None, None)


app = FastAPI(title="Theogony Cockpit", lifespan=_lifespan)


@app.get("/health")
async def cockpit_health() -> JSONResponse:
    """Lightweight health endpoint for cockpit standalone mode."""
    store = getattr(app.state, "store", None)
    backend = "memory" if isinstance(store, InMemoryKnowledgeStore) else "unknown"
    llm = getattr(app.state, "llm", None)
    return JSONResponse(
        {
            "status": "ok",
            "app": "cockpit",
            "store": backend,
            "llm_model_id": getattr(llm, "model_id", "unknown"),
        }
    )


__all__ = ["app"]
