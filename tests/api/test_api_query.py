"""
POST /query integration (Plan §3.7; E9 brief).

Happy path against InMemory + StubLLM, plus the 422 / 503 edge cases.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from theogony.agents.llm import StubLLMProvider
from theogony.api.dependencies import get_query_pipeline
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.stores import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", location=loc, language="en")


async def _populate_two_nodes(
    store: InMemoryKnowledgeStore,
) -> tuple[KnowledgeNode, KnowledgeNode]:
    hedin = KnowledgeNode(
        label="Sven Hedin",
        node_type=NodeType.PERSON,
        source_ref=_src("loc:hedin"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="test-embedder@v1",
        external_ids={"wikidata": "Q154759"},
    )
    hedin.scores.confidence = 0.9
    tibet = KnowledgeNode(
        label="Tibet",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:tibet"),
        embedding=[0.9, 0.1, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="test-embedder@v1",
        external_ids={"wikidata": "Q17269"},
    )
    tibet.scores.confidence = 0.8
    edge = KnowledgeEdge(
        source_id=hedin.id,
        target_id=tibet.id,
        relation_type="EXPLORED",
        evidence_span="Sven Hedin explored Tibet.",
    )
    await store.upsert_node(hedin)
    await store.upsert_node(tibet)
    await store.upsert_edge(edge)
    return hedin, tibet


@pytest.mark.asyncio
async def test_query_happy_path_returns_answer_constellation_run_id(
    api_app: FastAPI,
    api_client: TestClient,
    api_store: InMemoryKnowledgeStore,
    api_llm: StubLLMProvider,
) -> None:
    hedin, tibet = await _populate_two_nodes(api_store)
    # Override the StubLLM's default so the synthesizer cites real ids.
    api_llm._default = f"Sven Hedin explored Tibet [{hedin.id}] [{tibet.id}]."
    response = api_client.post("/query", json={"q": "Wer war Sven Hedin?", "k": 10, "hops": 1})
    assert response.status_code == 200
    body = response.json()
    assert "Sven Hedin" in body["answer"]
    assert hedin.id in body["cited_node_ids"]
    assert tibet.id in body["cited_node_ids"]
    assert body["run_id"]
    assert body["verdict"] in ("good", "partial", "poor", "failed", "inconclusive")
    assert body["constellation"]["query"] == "Wer war Sven Hedin?"
    assert body["constellation"]["path"] == "fast"
    assert body["report_url"] == f"/reports/{body['run_id']}"


def test_query_rejects_empty_string_with_422(api_client: TestClient) -> None:
    response = api_client.post("/query", json={"q": ""})
    assert response.status_code == 422
    detail = response.json()["detail"]
    # Some validation rule must mention the q field; surface it for diagnostics.
    assert any("q" in str(err.get("loc", "")) for err in detail)


def test_query_rejects_oversized_string_with_422(api_client: TestClient) -> None:
    response = api_client.post("/query", json={"q": "x" * 2001})
    assert response.status_code == 422


def test_query_rejects_invalid_k_with_422(api_client: TestClient) -> None:
    response = api_client.post("/query", json={"q": "ok", "k": 0})
    assert response.status_code == 422


def test_query_returns_503_when_pipeline_raises(
    api_app: FastAPI,
    api_client: TestClient,
) -> None:
    """A genuine pipeline exception (e.g. Neo4j down) becomes 503 +
    structured ErrorResponse rather than a default 500."""

    class _BoomPipeline:
        async def ask(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("simulated retrieval failure")

    api_app.dependency_overrides[get_query_pipeline] = lambda: _BoomPipeline()
    response = api_client.post("/query", json={"q": "ok"})
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "retrieval pipeline raised"
    assert body["verdict"] == "failed"
    assert "RuntimeError" in (body.get("detail") or "")


def test_query_response_does_not_leak_embeddings(
    api_app: FastAPI,
    api_client: TestClient,
    api_store: InMemoryKnowledgeStore,
    api_llm: StubLLMProvider,
) -> None:
    """Plan §9.1 invariant: embeddings stay out of the wire DTO."""
    import asyncio

    hedin, _ = asyncio.run(_populate_two_nodes(api_store))
    api_llm._default = f"Hedin [{hedin.id}]."
    body = api_client.post("/query", json={"q": "Hedin"}).json()
    payload_str = response_text = str(body)
    # No floating-point arrays of the embedding kind should appear.
    # The fixture embedding is [1.0, 0.0, 0.0, 0.0]; if it leaks, all
    # four would be present in the JSON.
    assert "0.0, 0.0, 0.0" not in payload_str
    assert "embedding" not in response_text.lower() or "embedding_model" in response_text.lower()
