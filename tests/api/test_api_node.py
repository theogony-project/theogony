"""
GET /node/{id} contract (Plan §3.7; E9 brief).

Asserts:
- existing id → 200 + node + slim neighbourhood;
- missing id → 404 with "no node with id" detail;
- the response payload never carries an embedding (Plan §9.1
  defence-in-depth at the API boundary).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.stores import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", location=loc, language="en")


def _node(label: str, *, node_type: NodeType = NodeType.PERSON) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=node_type,
        source_ref=_src(f"loc:{label}"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="test-embedder@v1",
    )


@pytest.mark.asyncio
async def test_node_existing_returns_200_with_neighborhood(
    api_client: TestClient, api_store: InMemoryKnowledgeStore
) -> None:
    hedin = _node("Sven Hedin")
    tibet = _node("Tibet", node_type=NodeType.PLACE)
    edge = KnowledgeEdge(
        source_id=hedin.id,
        target_id=tibet.id,
        relation_type="EXPLORED",
        weight=0.8,
        evidence_span="Hedin explored Tibet.",
    )
    await api_store.upsert_node(hedin)
    await api_store.upsert_node(tibet)
    await api_store.upsert_edge(edge)

    response = api_client.get(f"/node/{hedin.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["node"]["id"] == hedin.id
    assert body["node"]["label"] == "Sven Hedin"
    # Neighbourhood is a Constellation-shaped DTO with the slim node
    # that participates in the depth-1 edge.
    assert body["neighborhood"]["query"] == "Sven Hedin"
    assert body["neighborhood"]["path"] == "fast"
    assert any(n["id"] == tibet.id for n in body["neighborhood"]["nodes"])
    assert any(
        e["source_id"] == hedin.id and e["target_id"] == tibet.id
        for e in body["neighborhood"]["edges"]
    )


def test_node_missing_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/node/AKA-deadbeefdead")
    assert response.status_code == 404
    assert "no node with id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_node_response_excludes_embeddings(
    api_client: TestClient, api_store: InMemoryKnowledgeStore
) -> None:
    """API boundary is the second filter (slim DTO is the first).

    A regression that re-attaches embedding to the wire shape would
    surface as the canary 0.0 sequence appearing in the JSON.
    """
    hedin = _node("Sven Hedin")
    await api_store.upsert_node(hedin)
    body = api_client.get(f"/node/{hedin.id}").json()
    payload = str(body)
    assert "embedding" not in payload.lower()
    # The fixture embedding is [1.0, 0.0, 0.0, 0.0]; its concatenated
    # presence is the canary.
    assert "0.0, 0.0, 0.0" not in payload
