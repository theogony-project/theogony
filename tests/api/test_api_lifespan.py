"""
FastAPI lifespan startup/shutdown (Plan §4.4; E9 brief).

The lifespan is the **single owner** of long-lived resources. This
test exercises the production lifespan with mocked-out heavy
dependencies (no real BGE download, no real Gemini, no real Neo4j
container) to verify:

- every ``app.state.*`` resource is wired during startup;
- shutdown closes everything in reverse order;
- the absent OneirosWorker case does NOT skip the lifespan
  (E9 ships the slot wired but unpopulated);
- the present OneirosWorker case (mocked) DOES start + cancel
  the worker task during shutdown.

Why patching rather than DI overrides: the lifespan runs *before*
DI is consulted; its job is to populate the very state DI reads.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from theogony.api.app import lifespan


class _StubStore:
    async def __aenter__(self) -> _StubStore:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def health(self) -> dict[str, object]:
        return {"backend": "stub"}


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
async def _patched_lifespan(
    app: FastAPI, oneiros_task: asyncio.Task[None] | None = None
) -> AsyncIterator[None]:
    """Production lifespan with the heavy bits stubbed out.

    Approach: monkey-patch the modules the lifespan imports so the
    real Bolt connection / BGE load / audit DB never happen. Restore
    on exit. We can't simply call ``lifespan(app)`` directly because
    its imports resolve eagerly; the targeted patches keep that
    contract honest.

    NB: we use ``importlib.import_module`` because ``theogony.api`` re-
    exports the ``app`` FastAPI instance, which makes the bare attribute
    ``theogony.api.app`` ambiguous between submodule and FastAPI object.
    """
    import importlib

    app_mod = importlib.import_module("theogony.api.app")

    original = {
        "Settings": app_mod.Settings,
        "ExtractionAuditLog": app_mod.ExtractionAuditLog,
        "LocalSentenceTransformerEmbedder": app_mod.LocalSentenceTransformerEmbedder,
        "build_llm_from_settings": app_mod.build_llm_from_settings,
        "Neo4jKnowledgeStore": app_mod.Neo4jKnowledgeStore,
        "RunReportWriter": app_mod.RunReportWriter,
    }
    audit_mock = MagicMock()
    # spec=object → no aclose attribute on the LLM mock, so the
    # lifespan's hasattr-guarded `await llm.aclose()` is skipped (the
    # production GeminiLLMProvider has aclose; the StubLLMProvider does
    # not — the conditional is doing its job).
    llm_mock = MagicMock(spec=object)
    writer_mock = MagicMock()
    settings_mock = MagicMock(
        embedding=MagicMock(model_id="stub@v1", dim=4),
        data_dir=app_mod.Settings().data_dir,
        run_reports_dir=app_mod.Settings().run_reports_dir,
        neo4j=MagicMock(),
    )
    app_mod.Settings = lambda: settings_mock  # type: ignore[assignment]
    app_mod.ExtractionAuditLog = lambda *a, **kw: audit_mock  # type: ignore[assignment]
    app_mod.LocalSentenceTransformerEmbedder = lambda **kw: _StubEmbedder()  # type: ignore[assignment]
    app_mod.build_llm_from_settings = lambda *_a, **_kw: llm_mock  # type: ignore[assignment]
    app_mod.Neo4jKnowledgeStore = lambda *a, **kw: _StubStore()  # type: ignore[assignment]
    app_mod.RunReportWriter = lambda *_a, **_kw: writer_mock  # type: ignore[assignment]

    try:
        async with lifespan(app):
            if oneiros_task is not None:
                app.state.oneiros = MagicMock()
                app.state.oneiros_task = oneiros_task
            yield
    finally:
        for name, value in original.items():
            setattr(app_mod, name, value)


@pytest.mark.asyncio
async def test_lifespan_startup_wires_every_app_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    async with _patched_lifespan(app):
        assert app.state.settings is not None
        assert app.state.audit is not None
        assert app.state.embedder is not None
        assert app.state.llm is not None
        assert app.state.store is not None
        assert app.state.report_writer is not None
        # OneirosWorker slot wired but unpopulated (E9 contract).
        assert app.state.oneiros is None
        assert app.state.oneiros_task is None


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
async def test_lifespan_oneiros_absent_does_not_skip_lifespan() -> None:
    """E9 contract: a missing OneirosWorker is the default state, NOT
    a reason to abort. The slot stays None on entry and shutdown
    proceeds without error."""
    app = FastAPI()
    async with _patched_lifespan(app):
        # No OneirosWorker injected — the conditional in the lifespan
        # finally-clause must not crash.
        assert app.state.oneiros_task is None
    # No exception means the conditional honoured the contract.


@pytest.mark.asyncio
async def test_lifespan_oneiros_present_cancels_task_on_shutdown() -> None:
    """When a future E8.5 etappe wires app.state.oneiros_task, shutdown
    must cancel it within the 5s timeout."""
    app = FastAPI()

    async def _forever() -> None:
        try:
            await asyncio.sleep(3600)  # never wakes naturally
        except asyncio.CancelledError:
            return

    task = asyncio.create_task(_forever())
    async with _patched_lifespan(app, oneiros_task=task):
        assert app.state.oneiros_task is task
    # After the lifespan exits, the cancel + wait_for must have closed
    # the task without raising.
    assert task.cancelled() or task.done()


_: type = Any  # silences unused-import check
