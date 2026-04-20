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


class TestIngestCommand:
    def test_ingest_help_lists_all_options(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Force wide terminal so Typer/Rich's columns don't wrap option
        # names with ANSI escapes mid-token (CI's default 80-col TERM
        # turned "--sentences" into a multi-segment Rich render that
        # `in result.stdout` couldn't find).
        monkeypatch.setenv("COLUMNS", "200")
        result = CliRunner().invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "BOOK_ID" in result.stdout
        # Match each option's help description body — those words live
        # in the description column and are not split by Rich even at
        # narrow widths. More robust than asserting on the option
        # token itself, which Rich may colour-segment.
        for description_token in (
            "Limit NER",  # --sentences
            "Cap relation extraction",  # --relations
            "Skip BookContextExtractor",  # --no-book-context
            "Skip RelationExtractor",  # --no-relations
            "Skip the embedder",  # --no-embed
        ):
            assert description_token in result.stdout, (
                f"missing help description for option: {description_token!r}"
            )

    def test_ingest_without_book_id_errors(self) -> None:
        # Typer should refuse the call with a usage error when the
        # required positional argument is missing.
        result = CliRunner().invoke(app, ["ingest"])
        assert result.exit_code != 0

    def test_ingest_reports_acquisition_failure_cleanly(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # No GEMINI/GOOGLE keys in env (autouse fixture clears them)
        # AND no network access in CI sandbox. The acquisition stage
        # is the first thing that touches the network — it must fail
        # with a clean Rich panel + non-zero exit, not a stack trace.
        # We force-fail acquisition by monkeypatching get_by_id to
        # raise — keeps the test offline and deterministic.
        from theogony.acquisition import gutenberg as gb

        async def boom(self: gb.GutenbergAdapter, book_id: object) -> None:
            raise gb.httpx.HTTPStatusError(
                "404 Not Found",
                request=gb.httpx.Request("GET", "https://gutendex.com/books/x"),
                response=gb.httpx.Response(404),
            )

        monkeypatch.setattr(gb.GutenbergAdapter, "get_by_id", boom)
        result = CliRunner().invoke(app, ["ingest", "999999999"])
        assert result.exit_code == 1
        assert "Acquisition failed" in result.stdout

    def test_ingest_reports_missing_llm_key_cleanly(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Force acquisition to succeed via a stub that returns a
        # minimal RawContent — then the missing Gemini key must be
        # what fails next, with a clean panel.
        from datetime import UTC
        from datetime import datetime as _dt

        from theogony.acquisition import gutenberg as gb
        from theogony.acquisition.base import RawContent, SourceCandidate

        async def fake_get(self: gb.GutenbergAdapter, book_id: object) -> SourceCandidate:
            return SourceCandidate(
                source_type="gutenberg",
                identifier=str(book_id),
                title="Test",
                download_url="https://example.invalid/x",
            )

        async def fake_acquire(
            self: gb.GutenbergAdapter,
            cand: SourceCandidate,
        ) -> RawContent:
            return RawContent(
                source_type="gutenberg",
                identifier=cand.identifier,
                title=cand.title,
                language="en",
                content="hello world",
                content_format="text/plain; charset=utf-8",
                bytes_acquired=11,
                acquired_at=_dt.now(UTC),
            )

        monkeypatch.setattr(gb.GutenbergAdapter, "get_by_id", fake_get)
        monkeypatch.setattr(gb.GutenbergAdapter, "acquire", fake_acquire)
        # Default provider is "openai" but no key in env → factory raises.
        result = CliRunner().invoke(app, ["ingest", "1"])
        assert result.exit_code == 1
        assert "LLM provider unavailable" in result.stdout
        assert "OPENAI_API_KEY" in result.stdout


class TestStatus:
    def test_status_runs_without_external_services(self) -> None:
        # No env vars, no network — must still print a coherent summary.
        result = CliRunner().invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Theogony" in result.stdout
        assert "openai" in result.stdout
        assert "BAAI/bge-small-en-v1.5" in result.stdout

    def test_status_reports_missing_api_key(self) -> None:
        result = CliRunner().invoke(app, ["status"])
        assert result.exit_code == 0
        assert "missing" in result.stdout.lower()

    def test_status_reports_present_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-openai")
        result = CliRunner().invoke(app, ["status"])
        assert result.exit_code == 0
        assert "set" in result.stdout
        # The actual key must NOT appear (Plan §3.6 secret discipline).
        assert "sk-fake-openai" not in result.stdout

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
