"""
Shared CLI test fixtures (Plan §3.8 layer 4).

Provides a :class:`typer.testing.CliRunner` plus an isolated
``Settings`` rooted at a tmp_path so audit / reports stay
test-local. CLI tests run against the in-memory store backend
(``--store memory``) and the StubLLMProvider so no network /
Neo4j is required.

Pattern note: CLI tests do not use the FastAPI fixtures (those
go through ``app.dependency_overrides``); CLI commands construct
their own pipelines from ``settings`` + ``--store`` flags. We
isolate by setting the env-var ``THEOGONY_DATA_DIR`` so
``Settings()`` resolves to tmp_path during the call.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Force Settings() to resolve under tmp_path for the duration of the test.

    ``THEOGONY_DATA_DIR`` is the canonical env override for
    ``Settings.data_dir`` (pydantic-settings prefix-mapped).
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("THEOGONY_DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture
def cli_runner() -> Iterator[CliRunner]:
    """Wider terminal so Rich panels do not wrap in a way that breaks asserts.

    The 200-column env mirrors the existing ``test_cli.py`` discipline.
    """
    runner = CliRunner(env={"COLUMNS": "200"})
    yield runner
