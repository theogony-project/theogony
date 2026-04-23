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

from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.stub_detector import StubDetector
from theogony.memory.edge_pheromone import EdgePheromoneTracker
from theogony.memory.relevance import RelevanceTracker
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesizer_factory import build_synthesizer


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
    stub_detector = getattr(state, "stub_detector", None)
    if stub_detector is None:
        stub_detector = StubDetector(state.settings.curiosity.stub_thresholds)
    mnemosyne = getattr(state, "mnemosyne_classifier", None)
    if mnemosyne is None:
        mnemosyne = build_mnemosyne_classifier(state.settings, state.llm)
    return QueryPipeline(
        embedder=state.embedder,
        retriever=MultiHopRetriever(
            state.store,
            strategy=build_retrieval_strategy(state.store, state.settings),
        ),
        assembler=ConstellationAssembler(state.store),
        synthesizer=build_synthesizer(state.settings, state.llm, audit_log=state.audit),
        relevance=RelevanceTracker(
            state.store,
            relevance_delta=state.settings.relevance.relevance_delta,
        ),
        settings=state.settings,
        report_writer=state.report_writer,
        edge_pheromone=EdgePheromoneTracker(
            state.store,
            delta=state.settings.relevance.edge_pheromone_delta,
        ),
        stub_detector=stub_detector,
        mnemosyne=mnemosyne,
        entry_planner_llm=state.llm,
    )


__all__ = ["get_query_pipeline", "get_settings", "get_store"]
