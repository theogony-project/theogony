"""Explorer HTML growth panel (W8)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.cockpit.async_util import run_async
from theogony.cockpit.router import _explorer_growth_enabled_from_query
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest import read_dump
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


def test_explorer_growth_query_defaults_on_and_off_tokens() -> None:
    assert _explorer_growth_enabled_from_query("") is True
    assert _explorer_growth_enabled_from_query("on") is True
    assert _explorer_growth_enabled_from_query("OFF") is False
    assert _explorer_growth_enabled_from_query("false") is False


async def _load_pantheon(store: InMemoryKnowledgeStore) -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])


def test_explorer_page_growth_off_hides_panel(
    cockpit_client: TestClient,
    api_store: InMemoryKnowledgeStore,
) -> None:
    run_async(_load_pantheon(api_store))
    r = cockpit_client.get("/cockpit/explorer?growth=off")
    assert r.status_code == 200
    assert "Research live" not in r.text
    assert "explorer_growth.js" not in r.text
    assert 'data-growth="on"' not in r.text


def test_explorer_page_default_includes_growth_panel_and_script(
    cockpit_client: TestClient,
    api_store: InMemoryKnowledgeStore,
) -> None:
    run_async(_load_pantheon(api_store))
    r = cockpit_client.get("/cockpit/explorer")
    assert r.status_code == 200
    assert "Research live" in r.text
    assert "explorer_growth.js" in r.text
    assert 'data-growth="on"' in r.text
    assert "explorer-growth-log" in r.text
    assert "Wave 3 Demo Readiness" in r.text
    assert "growth mechanics, not guaranteed truth" in r.text
    assert "Show known internal knowledge" in r.text
    assert "Trigger a knowledge gap" in r.text
    assert "Explain the organism" in r.text


def test_growth_js_contains_failure_reason_and_no_trigger_messages() -> None:
    js_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "theogony"
        / "cockpit"
        / "static"
        / "js"
        / "explorer_growth.js"
    )
    text = js_path.read_text(encoding="utf-8")
    assert "reason=" in text
    assert "failed:" in text
    assert "No research trigger emitted" in text
