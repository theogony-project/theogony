"""Smoke tests for the cockpit Explorer (`/cockpit/explorer` + ask APIs)."""

from __future__ import annotations

import json
import math

import pytest
from fastapi.testclient import TestClient

from tests.cockpit.async_util import run_async
from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest import read_dump
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


def test_scrub_json_floats_replaces_non_finite() -> None:
    from theogony.cockpit.explorer import scrub_json_floats

    raw = {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2.5}}
    clean = scrub_json_floats(raw)
    json.dumps(clean, allow_nan=False)
    assert clean["a"] is None
    assert clean["b"] == [1.0, None]
    assert clean["c"]["d"] == 2.5
    assert math.isfinite(clean["c"]["d"])


def _parse_sse_data_lines(raw: str) -> list[dict]:
    out: list[dict] = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
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


def test_explorer_page_renders_chat_input_and_d3_chart(
    seeded_explorer_client: TestClient,
) -> None:
    r = seeded_explorer_client.get("/cockpit/explorer")
    assert r.status_code == 200
    assert "explorer-llm-ribbon" in r.text
    assert "Antwortmodus" in r.text
    assert "explorer-root" in r.text
    assert "explorer-q" in r.text
    assert "phase-embed" in r.text
    assert "explorer-save" in r.text
    assert "explorer-graph" in r.text
    assert "explorer-thinking-max" in r.text
    assert "explorer-chat-log" in r.text
    assert "explorer-new-chat" in r.text
    assert "phase-chat" in r.text
    assert "d3@7" in r.text


def test_explorer_api_ask_returns_rich_payload(
    seeded_explorer_client: TestClient,
) -> None:
    r = seeded_explorer_client.post(
        "/cockpit/api/ask",
        json={"q": "Pantheon", "k": 5, "hops": 1},
    )
    assert r.status_code == 200
    payload = r.json()
    assert "error" not in payload, payload
    assert payload["query"] == "Pantheon"
    assert "answer" in payload and "text" in payload["answer"]
    assert "constellation" in payload
    assert "nodes" in payload["constellation"]
    assert "edges" in payload["constellation"]
    assert "timing_ms" in payload
    assert "retrieval" in payload
    assert payload["retrieval"]["k"] == 5
    assert payload["retrieval"]["hops"] == 1
    assert payload["retrieval"]["thinking_max"] == 2
    assert "nodes_per_hop" in payload["retrieval"]
    assert "synthesis_meta" in payload
    assert payload["synthesis_meta"]["stub_llm"] is True
    assert "entry_plan" in payload
    assert payload["entry_plan"]["sub_queries"]
    assert isinstance(payload["query_embedding_preview"], list)
    assert "chat" in payload
    assert payload["chat"]["prior_messages_kept"] == []
    assert payload["chat"]["tokens_estimated_after"] >= 0


def test_explorer_api_ask_rejects_invalid_conversation_summary_type(
    seeded_explorer_client: TestClient,
) -> None:
    r = seeded_explorer_client.post(
        "/cockpit/api/ask",
        json={"q": "Hi", "conversation_summary": ["not", "a", "string"]},
    )
    assert r.status_code == 400
    assert "conversation_summary" in r.json()["detail"].lower()


def test_explorer_api_ask_rejects_empty_query(
    seeded_explorer_client: TestClient,
) -> None:
    r = seeded_explorer_client.post(
        "/cockpit/api/ask",
        json={"q": "   "},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("error") == "query must be non-empty"


def test_explorer_api_ask_clamps_k_and_hops(
    seeded_explorer_client: TestClient,
) -> None:
    r = seeded_explorer_client.post(
        "/cockpit/api/ask",
        json={"q": "Hestia", "k": 999, "hops": 99, "thinking_max": 99},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["retrieval"]["k"] <= 25
    assert payload["retrieval"]["hops"] <= 3
    assert payload["retrieval"]["thinking_max"] <= 8


def test_explorer_api_ask_stream_returns_phases_and_complete(
    seeded_explorer_client: TestClient,
) -> None:
    with seeded_explorer_client.stream(
        "POST",
        "/cockpit/api/ask-stream",
        json={"q": "Pantheon", "k": 5, "hops": 1},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    events = _parse_sse_data_lines(raw)
    types = [e["type"] for e in events]
    assert types[:4] == ["phase", "phase", "phase", "phase"]
    assert types[-1] == "complete"
    payload = events[-1]["payload"]
    assert payload["query"] == "Pantheon"
    assert "constellation" in payload
    phase_events = [e for e in events if e["type"] == "phase"]
    assert [e["phase"] for e in phase_events] == [
        "chat_compact",
        "embed",
        "retrieve",
        "synthesize",
    ]


def test_explorer_api_ask_stream_empty_query_emits_error_event(
    seeded_explorer_client: TestClient,
) -> None:
    with seeded_explorer_client.stream(
        "POST",
        "/cockpit/api/ask-stream",
        json={"q": "   "},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    events = _parse_sse_data_lines(raw)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "non-empty" in events[0]["message"]


def test_explorer_api_chronicle_append_upserts(
    seeded_explorer_client: TestClient,
) -> None:
    r = seeded_explorer_client.post(
        "/cockpit/api/chronicle-append",
        json={
            "fragments": [
                {
                    "title": "Test hypothesis from Explorer pytest",
                    "body": "A short hypothesized claim for CI append smoke.",
                }
            ],
            "context_note": "pytest explorer chronicle-append",
        },
    )
    assert r.status_code == 200
    out = r.json()
    assert "error" not in out, out
    assert out["fragment_count"] == 1
    assert len(out["upserted_node_ids"]) == 1
    assert out["origin"] == "cockpit_explorer"


def test_explorer_api_chronicle_append_forbidden_when_sample_only(
    seeded_explorer_client: TestClient,
    api_settings: Settings,
) -> None:
    api_settings.cockpit.sample_only = True
    try:
        r = seeded_explorer_client.post(
            "/cockpit/api/chronicle-append",
            json={
                "fragments": [{"title": "Should not land", "body": "Body text long enough." * 5}],
            },
        )
    finally:
        api_settings.cockpit.sample_only = False
    assert r.status_code == 403
    assert "sample-only" in r.json()["detail"]


def test_explorer_api_chronicle_append_disabled_returns_error_payload(
    seeded_explorer_client: TestClient,
    api_settings: Settings,
) -> None:
    api_settings.mcp_append.enabled = False
    try:
        r = seeded_explorer_client.post(
            "/cockpit/api/chronicle-append",
            json={
                "fragments": [{"title": "Disabled append", "body": "Some hypothesized body here."}],
            },
        )
    finally:
        api_settings.mcp_append.enabled = True
    assert r.status_code == 200
    out = r.json()
    assert "error" in out
    assert "disabled" in out["error"].lower()
