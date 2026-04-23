"""Read-only contract: cockpit traffic must not mutate the chronicle."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.cockpit.async_util import run_async
from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer
from theogony.docs_ingest import read_dump
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


async def _all_nodes(store: InMemoryKnowledgeStore) -> list[KnowledgeNode]:
    out: list[KnowledgeNode] = []
    for layer in (Layer.EPHEMERA, Layer.MNEME):
        async for n in store.export_layer(layer):
            out.append(n)
    out.sort(key=lambda n: n.id)
    return out


def _edge_dump(store: InMemoryKnowledgeStore) -> list[dict[str, object]]:
    edges = sorted(store._edges.values(), key=lambda e: e.id)
    return [e.model_dump(mode="python") for e in edges]


def _digest_tree(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(root))
            out[rel] = p.read_bytes()
    return out


def test_cockpit_does_not_mutate_chronicle_or_guarded_dirs(
    cockpit_client: TestClient,
    api_store: InMemoryKnowledgeStore,
    api_settings: Settings,
) -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    run_async(api_store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)]))
    run_async(api_store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)]))

    before_nodes = [n.model_dump(mode="python") for n in run_async(_all_nodes(api_store))]
    before_edges = _edge_dump(api_store)

    repo_root = Path(__file__).resolve().parents[2]
    phx_before = _digest_tree(repo_root / "phoenix-backlog")
    prompts_before = _digest_tree(repo_root / "prompts")
    reports_before = _digest_tree(api_settings.run_reports_dir)

    urls = (
        "/cockpit/",
        "/cockpit/browser",
        "/cockpit/browser/search?q=Pantheon",
        "/cockpit/browser/node/AKA-b435daf2df24",
        "/cockpit/clusters",
        "/cockpit/reports",
        "/cockpit/reports/query",
        "/cockpit/manifest",
    )
    for u in urls:
        cockpit_client.get(u)

    after_nodes = [n.model_dump(mode="python") for n in run_async(_all_nodes(api_store))]
    after_edges = _edge_dump(api_store)
    assert after_nodes == before_nodes
    assert after_edges == before_edges

    assert _digest_tree(repo_root / "phoenix-backlog") == phx_before
    assert _digest_tree(repo_root / "prompts") == prompts_before
    assert _digest_tree(api_settings.run_reports_dir) == reports_before
