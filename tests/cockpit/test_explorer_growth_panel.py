"""Explorer HTML growth panel (W8)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.cockpit.async_util import run_async
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest import read_dump
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


async def _load_pantheon(store: InMemoryKnowledgeStore) -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])


def test_explorer_page_default_does_not_include_growth_panel(
    cockpit_client: TestClient,
    api_store: InMemoryKnowledgeStore,
) -> None:
    run_async(_load_pantheon(api_store))
    r = cockpit_client.get("/cockpit/explorer")
    assert r.status_code == 200
    assert "Growth live" not in r.text
    assert "explorer_growth.js" not in r.text
    assert 'data-growth="on"' not in r.text


def test_explorer_page_with_growth_on_includes_panel_and_script(
    cockpit_client: TestClient,
    api_store: InMemoryKnowledgeStore,
) -> None:
    run_async(_load_pantheon(api_store))
    r = cockpit_client.get("/cockpit/explorer?growth=on")
    assert r.status_code == 200
    assert "Growth live" in r.text
    assert "explorer_growth.js" in r.text
    assert 'data-growth="on"' in r.text
    assert "explorer-growth-log" in r.text
