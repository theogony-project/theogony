"""
GET /health smoke (Plan §3.7; E9 brief).

Asserts:
- 200 + payload shape;
- the LLM is NOT invoked (a health endpoint that pings Gemini is wrong);
- the store backend name is reflected (``in_memory`` in the default API
  test fixture; ``lancedb`` when that backend is wired);
- report counts come from the per-test settings.run_reports_dir.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from theogony import __version__
from theogony.agents.llm import StubLLMProvider


def test_health_returns_200_with_payload(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["store"] == "in_memory"
    assert body["embedding_dim"] >= 1
    assert body["embedding_model"]
    assert "report_counts" in body
    assert set(body["report_counts"].keys()) >= {"ingest", "query", "oneiros"}


def test_health_does_not_invoke_llm(api_client: TestClient, api_llm: StubLLMProvider) -> None:
    """A /health response must not hit the LLM (cost + latency).

    The StubLLM records every call; if the route reaches it, this
    assertion fails loudly.
    """
    api_client.get("/health")
    assert api_llm.calls == []


def test_health_payload_is_extra_forbid(api_client: TestClient) -> None:
    """The response Pydantic model has extra='forbid'; a server-side
    typo (extra field) would surface as a serialisation error before
    it reaches the client. Guard the contract by listing the allowed
    keys explicitly."""
    body = api_client.get("/health").json()
    expected = {
        "status",
        "version",
        "store",
        "embedding_model",
        "embedding_dim",
        "report_counts",
    }
    assert set(body.keys()) == expected
