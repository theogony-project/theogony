"""Tests for POST /cockpit/api/growth-stream (W8)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.cockpit.async_util import run_async
from tests.test_extraction_pipeline import FakeWikidataClient, _hedin_responses
from tests.test_living_demo_w7b_smoke import _StubGutenbergAdapter
from theogony.agents.argus import ArgusAgent, ArgusSettings
from theogony.agents.llm import StubLLMProvider
from theogony.clustering.cluster_index import ClusterIndex
from theogony.cockpit.growth_stream import _PersistingIngestRunner
from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.curiosity.verification_pool import VerificationPool
from theogony.docs_ingest import read_dump
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.resolve import EntityResolver
from theogony.reporting.writer import RunReportWriter
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


def _parse_sse_blocks(raw: str) -> list[tuple[str | None, dict]]:
    out: list[tuple[str | None, dict]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        ev: str | None = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data: "):
                out.append((ev, json.loads(line[6:])))
    return out


async def _load_pantheon(store: InMemoryKnowledgeStore) -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])


@pytest.fixture
def seeded_explorer_client(
    cockpit_client: TestClient,
    api_store: InMemoryKnowledgeStore,
) -> TestClient:
    run_async(_load_pantheon(api_store))
    return cockpit_client


def test_growth_stream_rejects_when_growth_flag_missing(cockpit_client: TestClient) -> None:
    r = cockpit_client.post("/cockpit/api/growth-stream", json={"q": "hello"})
    assert r.status_code == 400
    assert "ask-stream" in r.json()["detail"]


def test_growth_stream_rejects_when_growth_false(cockpit_client: TestClient) -> None:
    r = cockpit_client.post("/cockpit/api/growth-stream", json={"q": "hello", "growth": False})
    assert r.status_code == 400


def test_growth_stream_emits_query_phases_then_complete(
    cockpit_client: TestClient,
) -> None:
    with cockpit_client.stream(
        "POST",
        "/cockpit/api/growth-stream",
        json={"q": "Who was Sven Hedin and what did he do?", "growth": True, "k": 5, "hops": 1},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    typed = [(e, d) for e, d in _parse_sse_blocks(raw) if e]
    ev_names = [e for e, _ in typed]
    assert "query_phase" in ev_names
    assert "query_complete" in ev_names
    qc = next(d for e, d in typed if e == "query_complete")
    assert qc.get("query")
    assert "constellation" in qc


def test_growth_stream_emits_trigger_when_thin(
    cockpit_client: TestClient,
    api_app: FastAPI,
) -> None:
    api_app.state.llm = StubLLMProvider(default="")
    with cockpit_client.stream(
        "POST",
        "/cockpit/api/growth-stream",
        json={"q": "Who was Sven Hedin and what did he investigate in Tibet?", "growth": True},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    typed = [(e, d) for e, d in _parse_sse_blocks(raw) if e]
    names = [e for e, _ in typed]
    assert "trigger_emitted" in names


@asynccontextmanager
async def _stub_gutenberg_cm() -> AsyncIterator[_StubGutenbergAdapter]:
    yield _StubGutenbergAdapter()


@asynccontextmanager
async def _stub_argus_session(
    settings: Settings,
    store: InMemoryKnowledgeStore,
    adapter: object,
    report_writer: RunReportWriter,
) -> AsyncIterator[ArgusAgent]:
    client = FakeWikidataClient(_hedin_responses())
    resolver = EntityResolver(client=client)  # type: ignore[arg-type]
    cluster_index = ClusterIndex()
    await cluster_index.rebuild_from_store(store)
    pipeline = IngestionPipeline(
        entity_resolver=resolver,
        store=store,
        settings=settings,
        cluster_index=cluster_index,
        ner_sentence_limit=80,
    )
    runner = _PersistingIngestRunner(pipeline, report_writer)
    verification_pool = VerificationPool(settings)
    yield ArgusAgent(
        adapter=adapter,  # type: ignore[arg-type]
        ingest_runner=runner,
        verification_pool=verification_pool,
        settings=ArgusSettings(enabled=True, min_candidate_score=0.0, search_limit=5),
    )


def test_growth_stream_emits_acquired_into_pool_not_legacy_gate_event(
    cockpit_client: TestClient,
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_app.state.llm = StubLLMProvider(default="")
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._gutenberg_adapter",
        _stub_gutenberg_cm,
    )
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._cockpit_argus_dispatch_session",
        _stub_argus_session,
    )
    with cockpit_client.stream(
        "POST",
        "/cockpit/api/growth-stream",
        json={"q": "Who was Sven Hedin and what did he investigate in Tibet?", "growth": True},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    typed = [(e, d) for e, d in _parse_sse_blocks(raw) if e]
    names = [e for e, _ in typed]
    assert "acquired_into_pool" in names
    legacy = "hestia" + "_review"
    assert legacy not in names
    assert names.index("acquired") < names.index("acquired_into_pool")


def test_acquired_into_pool_payload_contains_pool_entry_id(
    cockpit_client: TestClient,
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_app.state.llm = StubLLMProvider(default="")
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._gutenberg_adapter",
        _stub_gutenberg_cm,
    )
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._cockpit_argus_dispatch_session",
        _stub_argus_session,
    )
    with cockpit_client.stream(
        "POST",
        "/cockpit/api/growth-stream",
        json={"q": "Who was Sven Hedin and what did he investigate in Tibet?", "growth": True},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    pool_events = [d for e, d in _parse_sse_blocks(raw) if e == "acquired_into_pool"]
    assert len(pool_events) >= 1
    assert pool_events[0].get("pool_entry_id")
    assert pool_events[0].get("candidate_label")


def test_growth_stream_emits_research_complete_with_outcome(
    cockpit_client: TestClient,
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_app.state.llm = StubLLMProvider(default="")
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._gutenberg_adapter",
        _stub_gutenberg_cm,
    )
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._cockpit_argus_dispatch_session",
        _stub_argus_session,
    )
    with cockpit_client.stream(
        "POST",
        "/cockpit/api/growth-stream",
        json={"q": "Who was Sven Hedin and what did he investigate in Tibet?", "growth": True},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    completes = [d for e, d in _parse_sse_blocks(raw) if e == "research_complete"]
    assert len(completes) == 1
    body = completes[0]
    assert body.get("outcome") == "approved_and_ingested"
    assert body.get("total_nodes_added", 0) >= 0
    assert body.get("outcome") == "approved_and_ingested"


def test_existing_explorer_ask_stream_byte_for_byte_unchanged_for_default_request(
    seeded_explorer_client: TestClient,
) -> None:
    """Regression guard: default ask-stream body shape is unchanged by W8 wiring."""
    with seeded_explorer_client.stream(
        "POST",
        "/cockpit/api/ask-stream",
        json={"q": "Pantheon", "k": 5, "hops": 1},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    events = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert [e["type"] for e in events[:4]] == ["phase", "phase", "phase", "phase"]
    assert events[-1]["type"] == "complete"
    assert events[-1]["payload"]["query"] == "Pantheon"
