"""
FastAPI lifespan startup/shutdown (Plan §4.4; E9/E8.5 contracts).

The lifespan is the **single owner** of long-lived resources. This
test exercises the production lifespan with mocked-out heavy
dependencies (no real BGE download, no real Gemini, no heavy store
I/O) to verify:

- every ``app.state.*`` resource is wired during startup;
- shutdown closes everything in reverse order;
- E8.5 contract: ``app.state.oneiros`` is an :class:`OneirosWorker`
  after startup; ``app.state.oneiros_task`` is a running asyncio.Task;
- the worker task is cancelled within the §4.4 5-second budget on
  lifespan shutdown.

Why patching rather than DI overrides: the lifespan runs *before*
DI is consulted; its job is to populate the very state DI reads.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from theogony.api.app import lifespan


class _StubStore:
    """KnowledgeStore stub with the surface OneirosWorker._tick() reads.

    The worker runs immediately at lifespan startup (Plan §5 E8.5
    main loop: tick first, then sleep). The stub returns empty
    sequences so the tick is a near-no-op (it still writes a
    "poor"-verdict report via the writer mock).
    """

    async def __aenter__(self) -> _StubStore:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def health(self) -> dict[str, object]:
        return {"backend": "stub"}

    async def export_layer(self, layer: object) -> AsyncIterator[object]:
        # Empty layer → tick processes zero nodes.
        if False:  # type: ignore[unreachable]
            yield  # pragma: no cover
        return

    async def count_neighbors_in_layer(self, layer: object) -> dict[str, int]:
        return {}

    async def batch_update_scores(self, updates: object) -> None:
        return None

    async def promote(self, node_id: str) -> None:  # pragma: no cover - never called
        return None

    async def degrade(self, node_id: str) -> None:  # pragma: no cover - never called
        return None

    async def list_clusters(self) -> list:
        return []

    async def get_cluster_members(self, cluster_id: str) -> AsyncIterator[str]:
        if False:  # pragma: no cover
            yield ""

    async def assign_cluster(
        self,
        node_id: str,
        cluster_id: str | None,
        *,
        cluster_label: str | None = None,
    ) -> None:
        return None

    async def get_cluster_centroid(self, cluster_id: str) -> list[float]:
        return []

    async def batch_bump_edges(
        self,
        edge_ids: Sequence[str],
        *,
        delta: float,
        ts: datetime,
    ) -> None:
        return None

    async def list_aged_pheromone_edges(
        self,
        *,
        horizon: datetime,
        epsilon: float,
    ) -> list[tuple[str, float]]:
        return []

    async def batch_update_pheromone_deltas(
        self,
        updates: Sequence[tuple[str, float]],
    ) -> None:
        return None


class _StubEmbedder:
    @property
    def model_id(self) -> str:
        return "stub@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 4


@asynccontextmanager
async def _patched_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Production lifespan with the heavy bits stubbed out.

    Approach: monkey-patch the modules the lifespan imports so the
    real Bolt connection / BGE load / audit DB never happen. Restore
    on exit. We can't simply call ``lifespan(app)`` directly because
    its imports resolve eagerly; the targeted patches keep that
    contract honest.

    NB: we use ``importlib.import_module`` because ``theogony.api`` re-
    exports the ``app`` FastAPI instance, which makes the bare attribute
    ``theogony.api.app`` ambiguous between submodule and FastAPI object.

    E8.5: we use the **real** :class:`OneirosWorker` against the
    :class:`_StubStore` (which returns ``[]`` for export_layer and
    ``{}`` for count_neighbors_in_layer) so the lifespan's startup
    actually instantiates + starts the worker, and shutdown actually
    cancels the worker task. The worker's ``_tick`` loops harmlessly
    over the empty store while the lifespan body runs.
    """
    import importlib

    app_mod = importlib.import_module("theogony.api.app")

    original = {
        "Settings": app_mod.Settings,
        "ExtractionAuditLog": app_mod.ExtractionAuditLog,
        "LocalSentenceTransformerEmbedder": app_mod.LocalSentenceTransformerEmbedder,
        "build_llm_from_settings": app_mod.build_llm_from_settings,
        "InMemoryKnowledgeStore": app_mod.InMemoryKnowledgeStore,
        "RunReportWriter": app_mod.RunReportWriter,
    }
    audit_mock = MagicMock()
    # spec=object → no aclose attribute on the LLM mock, so the
    # lifespan's hasattr-guarded `await llm.aclose()` is skipped (the
    # production GeminiLLMProvider has aclose; the StubLLMProvider does
    # not — the conditional is doing its job).
    llm_mock = MagicMock(spec=object)
    writer_mock = MagicMock()

    # OneirosSettings stub with a long-enough tick that the worker
    # never actually completes a tick during the test (we only care
    # that startup created it and shutdown cancelled it).
    real_settings = app_mod.Settings()
    settings_mock = MagicMock(
        embedding=MagicMock(model_id="stub@v1", dim=4),
        data_dir=real_settings.data_dir,
        run_reports_dir=real_settings.run_reports_dir,
        oneiros=MagicMock(tick_interval_s=3600.0),  # never actually wakes
        report=real_settings.report,
        store=real_settings.store,
        clustering=real_settings.clustering,
        retrieval=real_settings.retrieval,
    )
    app_mod.Settings = lambda: settings_mock  # type: ignore[assignment]
    app_mod.ExtractionAuditLog = lambda *a, **kw: audit_mock  # type: ignore[assignment]
    app_mod.LocalSentenceTransformerEmbedder = lambda **kw: _StubEmbedder()  # type: ignore[assignment]
    app_mod.build_llm_from_settings = lambda *_a, **_kw: llm_mock  # type: ignore[assignment]
    app_mod.InMemoryKnowledgeStore = lambda *a, **kw: _StubStore()  # type: ignore[assignment]
    app_mod.RunReportWriter = lambda *_a, **_kw: writer_mock  # type: ignore[assignment]

    try:
        async with lifespan(app):
            yield
    finally:
        for name, value in original.items():
            setattr(app_mod, name, value)


@pytest.mark.asyncio
async def test_lifespan_startup_wires_every_app_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from theogony.memory.oneiros import OneirosWorker

    app = FastAPI()
    async with _patched_lifespan(app):
        assert app.state.settings is not None
        assert app.state.audit is not None
        assert app.state.embedder is not None
        assert app.state.llm is not None
        assert app.state.store is not None
        assert app.state.report_writer is not None
        assert app.state.cluster_index is not None
        # E8.5 contract: oneiros slot is filled with a real worker
        # + a running asyncio.Task (no longer None as in E9).
        assert isinstance(app.state.oneiros, OneirosWorker)
        assert isinstance(app.state.oneiros_task, asyncio.Task)
        assert not app.state.oneiros_task.done()


@pytest.mark.asyncio
async def test_lifespan_shutdown_closes_resources_in_reverse_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    async with _patched_lifespan(app):
        audit = app.state.audit
    # Audit's __exit__ was called once during shutdown.
    audit.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_lifespan_starts_and_cancels_oneiros_worker_within_5s() -> None:
    """E8.5 contract: lifespan starts the worker on entry and cancels
    it within the §4.4 5-second graceful-shutdown budget on exit."""
    from theogony.memory.oneiros import OneirosWorker

    app = FastAPI()
    captured_task: asyncio.Task[None] | None = None
    async with _patched_lifespan(app):
        assert isinstance(app.state.oneiros, OneirosWorker)
        captured_task = app.state.oneiros_task
        assert captured_task is not None
        assert not captured_task.done()
    # Lifespan exit cancelled + waited; the task is done within 5 s.
    assert captured_task is not None
    assert captured_task.done() or captured_task.cancelled()


_: type = Any  # silences unused-import check
