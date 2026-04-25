"""CLI: Nemesis + Eris (W16)."""

from __future__ import annotations

from theogony.cli import app


def test_nemesis_run_requires_once_flag(cli_runner, cli_data_dir) -> None:
    result = cli_runner.invoke(app, ["curiosity", "nemesis-run", "--store", "memory"])
    assert result.exit_code == 2


def test_nemesis_run_once_disabled_exits_zero(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__NEMESIS__ENABLED", "false")
    result = cli_runner.invoke(app, ["curiosity", "nemesis-run", "--once", "--store", "memory"])
    assert result.exit_code == 0
    assert "Nemesis disabled" in result.stdout


def test_nemesis_run_once_prints_counts(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__NEMESIS__ENABLED", "true")
    result = cli_runner.invoke(app, ["curiosity", "nemesis-run", "--once", "--store", "memory"])
    assert result.exit_code == 0
    assert "findings=" in result.stdout
    assert "confidence=" in result.stdout


def test_eris_run_requires_once_flag(cli_runner, cli_data_dir) -> None:
    result = cli_runner.invoke(app, ["curiosity", "eris-run", "--store", "memory", "--fixture"])
    assert result.exit_code == 2


def test_eris_run_requires_fixture_flag(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__ERIS__ENABLED", "true")
    result = cli_runner.invoke(app, ["curiosity", "eris-run", "--once", "--store", "memory"])
    assert result.exit_code == 2
    assert "--fixture" in result.stdout


def test_eris_run_once_disabled_exits_zero(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__ERIS__ENABLED", "false")
    result = cli_runner.invoke(
        app, ["curiosity", "eris-run", "--once", "--store", "memory", "--fixture"]
    )
    assert result.exit_code == 0
    assert "Eris disabled" in result.stdout
