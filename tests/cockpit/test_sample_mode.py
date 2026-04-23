"""Sample-only mode behaviour (PHX-0074)."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.cockpit.async_util import run_async
from theogony.cockpit.dependencies import get_settings as cockpit_get_settings
from theogony.config.settings import CockpitSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest import read_dump
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


async def _load_pantheon(store: InMemoryKnowledgeStore) -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])


def test_sample_mode_caps_search_results_to_top_n(
    api_app: FastAPI,
    api_settings: Settings,
    api_store: InMemoryKnowledgeStore,
) -> None:
    run_async(_load_pantheon(api_store))
    s = api_settings.model_copy(
        update={"cockpit": CockpitSettings(sample_only=True, sample_top_n_nodes=2)},
    )
    api_app.dependency_overrides[cockpit_get_settings] = lambda: s
    with TestClient(api_app) as sample_client:
        r = sample_client.get("/cockpit/browser/search", params={"q": "the"})
        assert r.status_code == 200
        assert r.text.count('hx-get="/cockpit/browser/node/') <= 2


def test_sample_mode_caps_recent_reports_to_n(
    api_app: FastAPI,
    api_settings: Settings,
) -> None:
    d = api_settings.run_reports_dir / "query"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(30):
        (d / f"01ZZZZZZZZZZZZZZZZZZZZZZ{i:02d}.json").write_text(
            json.dumps(
                {
                    "run_id": f"01ZZZZZZZZZZZZZZZZZZZZZZ{i:02d}",
                    "report_type": "query",
                    "verdict": "good",
                    "status": "completed",
                    "duration_s": 0.1,
                    "finished_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
    s = api_settings.model_copy(
        update={
            "cockpit": CockpitSettings(sample_only=True, sample_recent_n_reports=3),
        },
    )
    api_app.dependency_overrides[cockpit_get_settings] = lambda: s
    with TestClient(api_app) as sample_client:
        r = sample_client.get("/cockpit/reports/query")
        assert r.status_code == 200
        assert r.text.count('hx-get="/cockpit/reports/query/') <= 3


def test_sample_mode_blocks_manifest_save_with_403(
    api_app: FastAPI,
    api_settings: Settings,
) -> None:
    s = api_settings.model_copy(
        update={"cockpit": CockpitSettings(sample_only=True)},
    )
    api_app.dependency_overrides[cockpit_get_settings] = lambda: s
    with TestClient(api_app) as sample_client:
        r = sample_client.post("/cockpit/manifest", data={"content": "x"})
        assert r.status_code == 403


def test_sample_mode_status_panel_still_shows_real_counts(
    api_app: FastAPI,
    api_settings: Settings,
    api_store: InMemoryKnowledgeStore,
) -> None:
    run_async(_load_pantheon(api_store))
    h = run_async(api_store.health())
    s = api_settings.model_copy(
        update={"cockpit": CockpitSettings(sample_only=True)},
    )
    api_app.dependency_overrides[cockpit_get_settings] = lambda: s
    with TestClient(api_app) as sample_client:
        r = sample_client.get("/cockpit/")
        assert r.status_code == 200
        assert str(h.get("nodes", 0)) in r.text
