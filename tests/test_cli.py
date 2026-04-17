"""Tests for the Typer CLI (Plan §2.8)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from theogony.cli import app
from theogony.reporting.models import (
    EmbeddingSummary,
    IngestRunReport,
    NerSummary,
    QualityFlags,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
    new_run_id,
)
from theogony.reporting.writer import RunReportWriter


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Per-test cwd + clean Theogony env so the CLI never sees the user's shell."""
    monkeypatch.chdir(tmp_path)
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    for name in [n for n in os.environ if n.startswith("THEOGONY_")]:
        monkeypatch.delenv(name, raising=False)


def _write_ingest(tmp_path: Path, run_id: str, verdict: str = "good") -> Path:
    settings_dir = tmp_path / "data" / "run_reports"
    writer = RunReportWriter(base_dir=settings_dir)
    started = datetime.now(UTC)
    rep = IngestRunReport.model_validate(
        {
            "run_id": run_id,
            "started_at": started,
            "finished_at": started + timedelta(seconds=1),
            "duration_s": 1.0,
            "status": "completed",
            "verdict": verdict,
            "source_type": "gutenberg",
            "source_identifier": "Gutenberg:944",
            "word_count": 100,
            "sentence_count": 10,
            "stages": [],
            "ner": NerSummary(total_mentions=0),
            "resolution": ResolutionSummary(),
            "relations": RelationSummary(),
            "embedding": EmbeddingSummary(
                nodes_embedded=0, embedding_model_id="x@v1", duration_s=0.0
            ),
            "store": StoreSummary(nodes_upserted=0, edges_upserted=0),
            "quality_flags": QualityFlags(),
        }
    )
    return writer.write(rep)


# ---------------------------------------------------------------------------
# `--help` smoke
# ---------------------------------------------------------------------------


class TestHelp:
    def test_root_help(self) -> None:
        result = CliRunner().invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Theogony" in result.stdout
        assert "status" in result.stdout
        assert "reports" in result.stdout

    def test_status_help(self) -> None:
        result = CliRunner().invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "configuration" in result.stdout

    def test_reports_help(self) -> None:
        result = CliRunner().invoke(app, ["reports", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "show" in result.stdout


# ---------------------------------------------------------------------------
# `theogony status`
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_runs_without_external_services(self) -> None:
        # No env vars, no network — must still print a coherent summary.
        result = CliRunner().invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Theogony" in result.stdout
        assert "gemini" in result.stdout
        assert "BAAI/bge-small-en-v1.5" in result.stdout

    def test_status_reports_missing_api_key(self) -> None:
        result = CliRunner().invoke(app, ["status"])
        assert result.exit_code == 0
        assert "missing" in result.stdout.lower()

    def test_status_reports_present_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "g-fake")
        result = CliRunner().invoke(app, ["status"])
        assert result.exit_code == 0
        assert "set" in result.stdout
        # The actual key must NOT appear (Plan §3.6 secret discipline).
        assert "g-fake" not in result.stdout

    def test_status_counts_existing_reports(self, tmp_path: Path) -> None:
        for _ in range(3):
            _write_ingest(tmp_path, run_id=new_run_id())
        result = CliRunner().invoke(app, ["status"])
        assert result.exit_code == 0
        # The "ingest" row in the run-reports table should show 3
        assert "ingest" in result.stdout
        assert "│     3 │" in result.stdout or " 3 " in result.stdout


# ---------------------------------------------------------------------------
# `theogony reports list`
# ---------------------------------------------------------------------------


class TestReportsList:
    def test_empty_when_no_reports(self) -> None:
        result = CliRunner().invoke(app, ["reports", "list"])
        assert result.exit_code == 0
        assert "No reports" in result.stdout

    def test_lists_existing_reports_newest_first(self, tmp_path: Path) -> None:
        # Use ULID-shaped run_ids that sort in known order (lower stem → older).
        run_ids = [f"01HK0000000000000000000{i:03d}" for i in range(5)]
        for rid in run_ids:
            _write_ingest(tmp_path, run_id=rid)
        result = CliRunner().invoke(app, ["reports", "list"])
        assert result.exit_code == 0
        # All five ids present
        for rid in run_ids:
            assert rid in result.stdout
        # Newest first: index of the last id < index of the first id
        idx_newest = result.stdout.index(run_ids[-1])
        idx_oldest = result.stdout.index(run_ids[0])
        assert idx_newest < idx_oldest

    def test_last_caps_results(self, tmp_path: Path) -> None:
        for i in range(5):
            _write_ingest(tmp_path, run_id=f"01HK0000000000000000000{i:03d}")
        result = CliRunner().invoke(app, ["reports", "list", "--last", "2"])
        assert result.exit_code == 0
        # Only two of the five ids should be present
        present = sum(1 for i in range(5) if f"01HK0000000000000000000{i:03d}" in result.stdout)
        assert present == 2

    def test_type_filter(self, tmp_path: Path) -> None:
        # Only ingest reports written; --type ingest finds them, --type oneiros does not.
        _write_ingest(tmp_path, run_id="01HK00000000000000000000AA")
        ingest_only = CliRunner().invoke(app, ["reports", "list", "--type", "ingest"])
        assert ingest_only.exit_code == 0
        assert "01HK00000000000000000000AA" in ingest_only.stdout
        oneiros_only = CliRunner().invoke(app, ["reports", "list", "--type", "oneiros"])
        assert oneiros_only.exit_code == 0
        assert "No reports" in oneiros_only.stdout


# ---------------------------------------------------------------------------
# `theogony reports show`
# ---------------------------------------------------------------------------


class TestReportsShow:
    def test_show_unknown_returns_nonzero(self) -> None:
        result = CliRunner().invoke(app, ["reports", "show", "01HXNOTHERE"])
        assert result.exit_code != 0
        assert "No report" in result.stdout

    def test_show_exact_match(self, tmp_path: Path) -> None:
        rid = "01HK00000000000000000000AA"
        _write_ingest(tmp_path, run_id=rid, verdict="poor")
        result = CliRunner().invoke(app, ["reports", "show", rid])
        assert result.exit_code == 0
        assert rid in result.stdout
        assert "poor" in result.stdout

    def test_show_prefix_match(self, tmp_path: Path) -> None:
        rid = "01HK00000000000000000000AA"
        _write_ingest(tmp_path, run_id=rid)
        result = CliRunner().invoke(app, ["reports", "show", "01HK0000"])
        assert result.exit_code == 0
        assert rid in result.stdout

    def test_show_ambiguous_prefix_returns_nonzero(self, tmp_path: Path) -> None:
        _write_ingest(tmp_path, run_id="01HK0000000000000000000001")
        _write_ingest(tmp_path, run_id="01HK0000000000000000000002")
        result = CliRunner().invoke(app, ["reports", "show", "01HK"])
        assert result.exit_code != 0
        assert "Multiple reports" in result.stdout

    def test_show_renders_full_json(self, tmp_path: Path) -> None:
        rid = "01HK00000000000000000000AA"
        path = _write_ingest(tmp_path, run_id=rid)
        # Sanity: the file on disk parses as a dict with run_id.
        on_disk = json.loads(path.read_text())
        assert on_disk["run_id"] == rid
        result = CliRunner().invoke(app, ["reports", "show", rid])
        assert result.exit_code == 0
        # The JSON pretty-print should include the source_type field.
        assert "gutenberg" in result.stdout
