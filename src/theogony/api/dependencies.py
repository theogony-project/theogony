"""
Per-request dependency factories for the FastAPI surface (E9).

One function per pipeline component the routes need. Each pulls the
long-lived resources from ``app.state`` (set up in
:func:`theogony.api.app.lifespan`) and constructs a fresh per-request
pipeline / tracker. Routes consume these via ``Depends(...)`` so
tests can override the dependency surgically without monkeypatching
module-level globals.

Why per-request rather than per-app pipelines: ``QueryPipeline``
owns small ephemeral state (the run_id flow + the synthesizer's
audit_run_id is per-call); building one per request is < 1 µs and
keeps the contract testable.
"""

from __future__ import annotations

from fastapi import Request

from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.memory.relevance import RelevanceTracker
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.synthesize import AnswerSynthesizer


def get_settings(request: Request) -> Settings:
    """Resolve :class:`Settings` from app state."""
    settings: Settings = request.app.state.settings
    return settings


def get_store(request: Request) -> KnowledgeStore:
    """Resolve the active :class:`KnowledgeStore` from app state."""
    store: KnowledgeStore = request.app.state.store
    return store


def get_query_pipeline(request: Request) -> QueryPipeline:
    """Construct a fresh :class:`QueryPipeline` per request.

    The expensive long-lived components (``embedder``, ``llm``,
    ``store``, ``audit``, ``report_writer``) come from
    ``app.state``; the cheap glue (retriever, assembler,
    synthesizer, relevance) is constructed here per call so each
    request gets isolated synthesizer audit-run-id flow.
    """
    state = request.app.state
    return QueryPipeline(
        embedder=state.embedder,
        retriever=MultiHopRetriever(state.store),
        assembler=ConstellationAssembler(state.store),
        synthesizer=AnswerSynthesizer(state.llm, audit_log=state.audit),
        relevance=RelevanceTracker(state.store),
        settings=state.settings,
        report_writer=state.report_writer,
    )


__all__ = ["get_query_pipeline", "get_settings", "get_store"]
