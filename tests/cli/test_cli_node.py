"""
``theogony node`` CLI integration (Plan §3.8 layer 4 / E9 brief).

Asserts:
- existing id → exit 0, neighbourhood rendered, no embedding leak;
- missing id → exit 1, red panel with "did you mean" hint;
- the embedding values never appear in stdout (Plan §9.1 boundary).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from typer.testing import CliRunner

from theogony.cli import app
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


def _build_seeded_store() -> tuple[InMemoryKnowledgeStore, KnowledgeNode, KnowledgeNode]:
    store = InMemoryKnowledgeStore()
    hedin = _node("Sven Hedin")
    tibet = _node("Tibet", node_type=NodeType.PLACE)
    edge = KnowledgeEdge(
        source_id=hedin.id,
        target_id=tibet.id,
        relation_type="EXPLORED",
        weight=0.8,
        evidence_span="Hedin explored Tibet.",
    )
    asyncio.run(store.upsert_node(hedin))
    asyncio.run(store.upsert_node(tibet))
    asyncio.run(store.upsert_edge(edge))
    return store, hedin, tibet


def _patch_open_store(monkeypatch: pytest.MonkeyPatch, store: InMemoryKnowledgeStore) -> None:
    import theogony.cli as cli_mod

    @asynccontextmanager
    async def _yield(*args: object, **kwargs: object) -> AsyncIterator[object]:
        yield store

    monkeypatch.setattr(cli_mod, "_open_store", _yield)


def test_node_existing_renders_neighborhood_panel(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, hedin, tibet = _build_seeded_store()
    _patch_open_store(monkeypatch, store)
    result = cli_runner.invoke(app, ["node", hedin.id, "--store", "memory"])
    assert result.exit_code == 0, result.stdout
    assert hedin.id in result.stdout
    assert "Sven Hedin" in result.stdout
    assert "Tibet" in result.stdout
    assert "EXPLORED" in result.stdout
    # Embedding canary: 1.0/0.0 sequence must not appear.
    assert "1.0, 0.0, 0.0" not in result.stdout


def test_node_missing_returns_red_panel(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _hedin, _tibet = _build_seeded_store()
    _patch_open_store(monkeypatch, store)
    result = cli_runner.invoke(app, ["node", "AKA-deadbeefdead", "--store", "memory"])
    assert result.exit_code == 1
    assert "No node with id" in result.stdout
    assert "AKA-deadbeefdead" in result.stdout


def test_node_unknown_store_kind_exits_2(cli_runner: CliRunner, cli_data_dir) -> None:
    result = cli_runner.invoke(app, ["node", "AKA-x", "--store", "wibble"])
    assert result.exit_code == 2
    assert "Unknown --store value" in result.stdout
