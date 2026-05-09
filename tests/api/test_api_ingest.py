"""
POST /ingest contract (Plan §3.7; E9 brief).

Asserts:
- 202 + run_id + report_url in the accept response;
- payload validation (extra='forbid' on IngestRequest);
- an unsupported source_type yields 422 (only "gutenberg" is allowed
  in Gen 1).

Starlette's ``TestClient`` runs ``BackgroundTasks`` to completion before
returning from ``.post()`` (unlike a real HTTP client that would detach
after the 202 body). Without intervention, this contract test would pull
Gutenberg + Wikidata + the full ingest pipeline and take many minutes.

We therefore monkeypatch ``_run_background_ingest`` to a no-op so this
module only asserts the **202 accept boundary** + validation. Full
pipeline coverage lives in ingest unit tests and smoke tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _noop_background_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not run real Gutenberg/Wikidata ingest during TestClient requests."""

    async def _noop(**_: object) -> None:
        return None

    monkeypatch.setattr(
        "theogony.api.routes.ingest._run_background_ingest",
        _noop,
    )


def test_ingest_returns_202_with_run_id(api_client: TestClient) -> None:
    response = api_client.post(
        "/ingest",
        json={
            "source_type": "gutenberg",
            "identifier": "43497",
            "sentences": 30,
            "no_relations": True,
            "no_embed": True,
            "no_book_context": True,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["run_id"]
    assert body["report_url"] == f"/reports/{body['run_id']}"
    assert "status_message" in body


def test_ingest_rejects_extra_fields_with_422(api_client: TestClient) -> None:
    response = api_client.post(
        "/ingest",
        json={
            "source_type": "gutenberg",
            "identifier": "43497",
            "unknown_extra_field": "boom",
        },
    )
    assert response.status_code == 422


def test_ingest_rejects_unsupported_source_type_with_422(api_client: TestClient) -> None:
    response = api_client.post(
        "/ingest",
        json={"source_type": "wikipedia", "identifier": "X"},
    )
    assert response.status_code == 422


def test_ingest_rejects_empty_identifier_with_422(api_client: TestClient) -> None:
    response = api_client.post("/ingest", json={"source_type": "gutenberg", "identifier": ""})
    assert response.status_code == 422
