"""
``theogony resolve`` CLI integration (Plan §3.4 / §3.8 layer 4 / E9 brief).

Asserts:
- ``resolve --list`` prints the queue (table + count);
- ``resolve --list`` returns "queue empty" when no nodes pending;
- ``resolve <id> --non-interactive --pick=Q1234`` mints the wikidata id,
  bumps tier to 1, clears manual_resolution_needed;
- ``resolve <id> --non-interactive --pick=none`` clears the flag only;
- ``resolve --non-interactive`` without ``--pick`` exits 2 with a clear
  error;
- ``resolve <id>`` for unknown id returns red panel + exit 1;
- ``resolve`` without args + without --list exits 2.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from typer.testing import CliRunner

from theogony.cli import app
from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.stores import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", location=loc, language="en")


def _pending_node(label: str) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=NodeType.PERSON,
        source_ref=_src(f"loc:{label}"),
        manual_resolution_needed=True,
        resolution_tier=0,
    )


def _patch_open_store(monkeypatch: pytest.MonkeyPatch, store: InMemoryKnowledgeStore) -> None:
    import theogony.cli as cli_mod

    @asynccontextmanager
    async def _yield(*args: object, **kwargs: object) -> AsyncIterator[object]:
        yield store

    monkeypatch.setattr(cli_mod, "_open_store", _yield)


def test_list_with_pending_renders_table(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryKnowledgeStore()
    a = _pending_node("Aufschnaiter")
    b = _pending_node("Stein")
    asyncio.run(store.upsert_node(a))
    asyncio.run(store.upsert_node(b))
    _patch_open_store(monkeypatch, store)
    result = cli_runner.invoke(app, ["resolve", "--list", "--store", "memory"])
    assert result.exit_code == 0
    assert "Aufschnaiter" in result.stdout
    assert "Stein" in result.stdout
    assert "Pending manual resolution" in result.stdout


def test_list_empty_queue_renders_green_panel(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_open_store(monkeypatch, InMemoryKnowledgeStore())
    result = cli_runner.invoke(app, ["resolve", "--list", "--store", "memory"])
    assert result.exit_code == 0
    assert "Queue is empty" in result.stdout


def test_pick_qid_resolves_node(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryKnowledgeStore()
    pending = _pending_node("Aufschnaiter")
    asyncio.run(store.upsert_node(pending))
    _patch_open_store(monkeypatch, store)
    result = cli_runner.invoke(
        app,
        [
            "resolve",
            pending.id,
            "--non-interactive",
            "--pick",
            "Q123456",
            "--store",
            "memory",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Resolved" in result.stdout
    assert "Q123456" in result.stdout
    # Verify store mutation.
    fetched = asyncio.run(store.get_node(pending.id))
    assert fetched is not None
    assert fetched.external_ids.get("wikidata") == "Q123456"
    assert fetched.resolution_tier == 1
    assert fetched.manual_resolution_needed is False


def test_pick_none_clears_flag_only(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryKnowledgeStore()
    pending = _pending_node("Aufschnaiter")
    asyncio.run(store.upsert_node(pending))
    _patch_open_store(monkeypatch, store)
    result = cli_runner.invoke(
        app,
        [
            "resolve",
            pending.id,
            "--non-interactive",
            "--pick",
            "none",
            "--store",
            "memory",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Confirmed no candidate fits" in result.stdout
    fetched = asyncio.run(store.get_node(pending.id))
    assert fetched is not None
    assert "wikidata" not in fetched.external_ids
    assert fetched.resolution_tier == 0
    assert fetched.manual_resolution_needed is False


def test_non_interactive_without_pick_exits_2(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryKnowledgeStore()
    pending = _pending_node("Aufschnaiter")
    asyncio.run(store.upsert_node(pending))
    _patch_open_store(monkeypatch, store)
    result = cli_runner.invoke(
        app,
        ["resolve", pending.id, "--non-interactive", "--store", "memory"],
    )
    assert result.exit_code == 2
    assert "--non-interactive requires --pick" in result.stdout


def test_unknown_node_id_exits_1(
    cli_runner: CliRunner, cli_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_open_store(monkeypatch, InMemoryKnowledgeStore())
    result = cli_runner.invoke(
        app,
        [
            "resolve",
            "AKA-deadbeefdead",
            "--non-interactive",
            "--pick",
            "Q1",
            "--store",
            "memory",
        ],
    )
    assert result.exit_code == 1
    assert "No node with id" in result.stdout


def test_no_args_no_list_exits_2(cli_runner: CliRunner, cli_data_dir) -> None:
    result = cli_runner.invoke(app, ["resolve", "--store", "memory"])
    assert result.exit_code == 2
    assert "Pass either a node id or --list" in result.stdout
