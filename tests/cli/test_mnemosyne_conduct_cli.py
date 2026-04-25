"""CLI: ``theogony mnemosyne conduct`` (W17)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from theogony.cli import app
from theogony.cockpit.router import REPORT_TABS
from theogony.stores.memory import InMemoryKnowledgeStore


def test_mnemosyne_conduct_requires_once_flag(cli_runner, cli_data_dir) -> None:
    result = cli_runner.invoke(app, ["mnemosyne", "conduct", "--store", "memory"])
    assert result.exit_code == 2


def test_mnemosyne_conduct_disabled_exits_zero_and_writes_report(
    cli_runner, cli_data_dir, monkeypatch
) -> None:
    monkeypatch.setenv("THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED", "false")
    store = InMemoryKnowledgeStore()

    @asynccontextmanager
    async def _fake_open(_settings, _store_kind, _embedding_dim):
        yield store

    monkeypatch.setattr("theogony.cli._open_store", _fake_open)

    result = cli_runner.invoke(app, ["mnemosyne", "conduct", "--once", "--store", "memory"])
    assert result.exit_code == 0
    assert "Mnemosyne conductor disabled" in result.stdout
    mdir = Path(cli_data_dir) / "run_reports" / "mnemosyne_conductor"
    assert mdir.is_dir()
    assert list(mdir.glob("*.json"))


def test_mnemosyne_conduct_fixture_mode_prints_counts(
    cli_runner, cli_data_dir, monkeypatch
) -> None:
    monkeypatch.setenv("THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED", "true")
    store = InMemoryKnowledgeStore()

    @asynccontextmanager
    async def _fake_open(_settings, _store_kind, _embedding_dim):
        yield store

    monkeypatch.setattr("theogony.cli._open_store", _fake_open)

    result = cli_runner.invoke(
        app,
        [
            "mnemosyne",
            "conduct",
            "--once",
            "--store",
            "memory",
            "--metric-mode",
            "fixture",
        ],
    )
    assert result.exit_code == 0
    assert "metrics=3" in result.stdout
    assert "experiments=3" in result.stdout


def test_reports_list_accepts_mnemosyne_conductor_type(cli_runner, cli_data_dir) -> None:
    result = cli_runner.invoke(
        app, ["reports", "list", "--type", "mnemosyne_conductor", "--last", "5"]
    )
    assert result.exit_code == 0


def test_cockpit_report_tabs_include_mnemosyne_conductor() -> None:
    types = [t[0] for t in REPORT_TABS]
    assert "mnemosyne_conductor" in types
