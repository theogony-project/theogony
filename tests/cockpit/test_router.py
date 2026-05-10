"""Routing + HTML smoke tests for the Iris cockpit."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.cockpit.async_util import run_async
from tests.cockpit.conftest import load_truncated_pantheon_seed
from theogony.agents.llm import StubLLMProvider
from theogony.clustering.runner import run_one_recluster_pass
from theogony.config.settings import ClusteringSettings, Settings
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore


async def _load_pantheon(store: InMemoryKnowledgeStore) -> None:
    await load_truncated_pantheon_seed(store)


@pytest.fixture
def seeded_client(cockpit_client: TestClient, api_store: InMemoryKnowledgeStore) -> TestClient:
    run_async(_load_pantheon(api_store))
    return cockpit_client


def test_status_panel_renders_against_pantheon_self_seed(
    seeded_client: TestClient,
    api_store: InMemoryKnowledgeStore,
) -> None:
    h = run_async(api_store.health())
    r = seeded_client.get("/cockpit/")
    assert r.status_code == 200
    assert str(h.get("nodes", 0)) in r.text
    assert str(h.get("edges", 0)) in r.text


def test_browser_search_returns_html_fragment_for_pantheon_query(
    seeded_client: TestClient,
) -> None:
    r = seeded_client.get("/cockpit/browser/search", params={"q": "Pantheon"})
    assert r.status_code == 200
    assert "<a " in r.text


def test_browser_node_detail_renders_hover_lupe_data(
    seeded_client: TestClient,
) -> None:
    r = seeded_client.get("/cockpit/browser/node/AKA-b435daf2df24")
    assert r.status_code == 200
    assert "data-graph=" in r.text
    assert '"nodes"' in r.text


def test_clusters_panel_lists_clusters_after_recluster(
    cockpit_client: TestClient,
    api_store: InMemoryKnowledgeStore,
    api_settings: Settings,
    api_llm: StubLLMProvider,
) -> None:
    run_async(_load_pantheon(api_store))
    settings = api_settings.model_copy(
        update={
            "clustering": ClusteringSettings(
                algorithm="hdbscan",
                min_cluster_size=4,
                min_corpus_size=20,
            ),
        },
    )
    writer = RunReportWriter(settings.run_reports_dir)
    run_async(run_one_recluster_pass(api_store, settings, writer, force=True))
    r = cockpit_client.get("/cockpit/clusters")
    assert r.status_code == 200
    assert "cluster" in r.text.lower()


def test_reports_panel_default_tab_is_query(cockpit_client: TestClient) -> None:
    r = cockpit_client.get("/cockpit/reports")
    assert r.status_code == 200
    assert 'hx-get="/cockpit/reports/query"' in r.text
    assert "Immune system" in r.text


def test_reports_table_empty_state_for_mnemosyne_conductor(cockpit_client: TestClient) -> None:
    r = cockpit_client.get("/cockpit/reports/mnemosyne_conductor")
    assert r.status_code == 200
    assert "Mnemosyne conductor has not run yet" in r.text


def test_reports_show_returns_full_json_for_known_run_id(
    cockpit_client: TestClient,
    api_settings: Settings,
) -> None:
    d = api_settings.run_reports_dir / "query"
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "01TESTCOCKPITRUN",
        "report_type": "query",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:01+00:00",
        "duration_s": 1.0,
        "status": "completed",
        "verdict": "good",
        "query": "hello",
        "query_length_chars": 5,
        "multi_hop": {
            "seed_count": 1,
            "nodes_per_hop": None,
            "final_node_count": 1,
            "duplicates_removed": 0,
            "duration_ms": 0,
        },
        "constellation_node_count": 0,
        "constellation_edge_count": 0,
        "suggested_source_count": 0,
        "gaps_identified": 0,
        "synthesis": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_eur": 0.0,
            "latency_ms": 0,
        },
        "citation_quality": {
            "cited_node_count": 0,
            "citations_with_high_confidence_source": 0,
            "citations_aka_only": 0,
        },
        "cited_node_ids": [],
    }
    (d / "01TESTCOCKPITRUN.json").write_text(json.dumps(payload), encoding="utf-8")
    r = cockpit_client.get("/cockpit/reports/query/01TESTCOCKPITRUN")
    assert r.status_code == 200
    assert "01TESTCOCKPITRUN" in r.text
