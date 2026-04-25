"""CLI: ``theogony curiosity athene-run`` (W14)."""

from __future__ import annotations

from theogony.cli import app


def test_athene_run_requires_once_flag(cli_runner, cli_data_dir) -> None:
    result = cli_runner.invoke(app, ["curiosity", "athene-run", "--store", "memory"])
    assert result.exit_code == 2


def test_athene_run_once_disabled_exits_zero(cli_runner, cli_data_dir, monkeypatch) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__ATHENE__ENABLED", "false")
    result = cli_runner.invoke(app, ["curiosity", "athene-run", "--once", "--store", "memory"])
    assert result.exit_code == 0
    assert "Athene disabled" in result.stdout


def test_athene_run_once_prints_sampled_and_findings_counts(
    cli_runner, cli_data_dir, monkeypatch
) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__ATHENE__ENABLED", "true")
    monkeypatch.setenv("THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE", "1.0")
    from theogony.config.settings import Settings
    from theogony.curiosity.verification_pool import VerificationPool

    settings = Settings()
    VerificationPool(settings).register("x", ingest_run_id=None)
    result = cli_runner.invoke(
        app,
        ["curiosity", "athene-run", "--once", "--store", "memory", "--seed", "0"],
    )
    assert result.exit_code == 0
    assert "sampled=1" in result.stdout
    assert "findings=1" in result.stdout
    assert "pool_marked=1" in result.stdout
