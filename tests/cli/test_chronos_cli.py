"""CLI: ``theogony curiosity chronos-run`` (W15)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from theogony.cli import app
from theogony.config.settings import Settings
from theogony.curiosity.finding import Finding
from theogony.curiosity.verification_pool import VerificationPool
from theogony.stores.memory import InMemoryKnowledgeStore


def test_chronos_run_requires_once_flag(cli_runner, cli_data_dir) -> None:
    result = cli_runner.invoke(app, ["curiosity", "chronos-run", "--store", "memory"])
    assert result.exit_code == 2


def test_chronos_run_once_disabled_exits_zero(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__CHRONOS__ENABLED", "false")
    result = cli_runner.invoke(app, ["curiosity", "chronos-run", "--once", "--store", "memory"])
    assert result.exit_code == 0
    assert "Chronos disabled" in result.stdout


def test_chronos_run_once_enabled_no_eligible(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__CHRONOS__ENABLED", "true")
    result = cli_runner.invoke(app, ["curiosity", "chronos-run", "--once", "--store", "memory"])
    assert result.exit_code == 0
    assert "processed=0" in result.stdout


def test_chronos_run_once_writes_report_when_disabled(
    cli_runner, cli_data_dir, monkeypatch
) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__CHRONOS__ENABLED", "false")
    result = cli_runner.invoke(app, ["curiosity", "chronos-run", "--once", "--store", "memory"])
    assert result.exit_code == 0
    chronos_dir = Path(cli_data_dir) / "run_reports" / "chronos"
    assert chronos_dir.is_dir()
    assert list(chronos_dir.glob("*.json"))


def test_chronos_run_once_enabled_clears_pool(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__CHRONOS__ENABLED", "true")
    settings = Settings()
    pool = VerificationPool(settings)
    entry = pool.register("cli-chronos")
    finding_id = "FINDING-cli-1"
    f = Finding(
        finding_id=finding_id,
        finding_type="no_issue_observed",
        severity="info",
        pool_entry_id=entry.entry_id,
        sampled_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    store = InMemoryKnowledgeStore()

    async def _seed() -> None:
        await store.batch_upsert_nodes([f.to_knowledge_node()])

    asyncio.run(_seed())
    pool.mark_sampled_by_athene(entry.entry_id, finding_ids=[finding_id])

    @asynccontextmanager
    async def _fake_open(_settings, _store_kind, _embedding_dim):
        yield store

    monkeypatch.setattr("theogony.cli._open_store", _fake_open)

    result = cli_runner.invoke(app, ["curiosity", "chronos-run", "--once", "--store", "memory"])
    assert result.exit_code == 0
    assert "cleared=1" in result.stdout
