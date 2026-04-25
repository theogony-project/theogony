"""GET /cockpit/api/verification-pool (W14)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from theogony.curiosity.verification_pool import VerificationPool


def test_verification_pool_status_returns_stats(
    cockpit_client: TestClient, api_app: FastAPI
) -> None:
    settings = api_app.state.settings
    pool = VerificationPool(settings)
    pool.register("a", ingest_run_id="i1")
    pool.register("b", ingest_run_id="i2")

    r = cockpit_client.get("/cockpit/api/verification-pool")
    assert r.status_code == 200
    body = r.json()
    assert body["stats"]["total"] >= 2
    assert body["stats"]["unobserved"] >= 2


def test_verification_pool_status_includes_cleared_count(
    cockpit_client: TestClient, api_app: FastAPI
) -> None:
    settings = api_app.state.settings
    pool = VerificationPool(settings)
    e = pool.register("cleared-candidate")
    pool.mark_cleared(e.entry_id)

    r = cockpit_client.get("/cockpit/api/verification-pool")
    assert r.status_code == 200
    assert r.json()["stats"]["cleared"] >= 1


def test_verification_pool_status_limits_recent_entries_to_ten(
    cockpit_client: TestClient,
    api_app: FastAPI,
) -> None:
    settings = api_app.state.settings
    pool = VerificationPool(settings)
    for i in range(15):
        pool.register(f"c{i}", ingest_run_id=f"id{i}")

    r = cockpit_client.get("/cockpit/api/verification-pool")
    assert r.status_code == 200
    assert len(r.json()["recent_entries"]) == 10
