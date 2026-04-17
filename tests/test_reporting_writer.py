"""Tests for the atomic RunReportWriter (Plan §2.11.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from theogony.reporting.models import (
    EmbeddingSummary,
    IngestRunReport,
    NerSummary,
    OneirosTickReport,
    QualityFlags,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
    VitalityShift,
    new_run_id,
)
from theogony.reporting.writer import RunReportWriter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ingest_report(run_id: str | None = None) -> IngestRunReport:
    started = datetime.now(UTC)
    return IngestRunReport.model_validate(
        {
            "run_id": run_id or new_run_id(),
            "started_at": started,
            "finished_at": started + timedelta(seconds=1),
            "duration_s": 1.0,
            "status": "completed",
            "verdict": "good",
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


def _oneiros_report(run_id: str | None = None) -> OneirosTickReport:
    started = datetime.now(UTC)
    return OneirosTickReport.model_validate(
        {
            "run_id": run_id or new_run_id(),
            "started_at": started,
            "finished_at": started + timedelta(milliseconds=50),
            "duration_s": 0.05,
            "status": "completed",
            "verdict": "good",
            "nodes_evaluated": 10,
            "nodes_promoted": 1,
            "nodes_degraded": 0,
            "vitality": VitalityShift(),
        }
    )


@pytest.fixture
def writer(tmp_path: Path) -> RunReportWriter:
    return RunReportWriter(base_dir=tmp_path / "run_reports")


# ---------------------------------------------------------------------------
# Basic write
# ---------------------------------------------------------------------------


class TestWrite:
    def test_creates_per_type_subdirectory(self, writer: RunReportWriter, tmp_path: Path) -> None:
        report = _ingest_report()
        path = writer.write(report)
        assert path == tmp_path / "run_reports" / "ingest" / f"{report.run_id}.json"
        assert path.exists()

    def test_pretty_indented_json(self, writer: RunReportWriter) -> None:
        report = _ingest_report()
        path = writer.write(report)
        contents = path.read_text(encoding="utf-8")
        assert "\n  " in contents  # indented
        # Round-trip parses
        parsed = json.loads(contents)
        assert parsed["run_id"] == report.run_id

    def test_overwrites_existing_file(self, writer: RunReportWriter) -> None:
        rid = new_run_id()
        first = _ingest_report(run_id=rid)
        first.verdict = "good"
        path = writer.write(first)
        original_size = path.stat().st_size

        second = _ingest_report(run_id=rid)
        second.verdict = "poor"
        path2 = writer.write(second)
        assert path2 == path
        # File contents now reflect the overwrite, not the original.
        contents = json.loads(path.read_text(encoding="utf-8"))
        assert contents["verdict"] == "poor"
        # Size may differ (different verdict string) — at minimum it
        # isn't the original empty/uninitialised state.
        assert path.stat().st_size > 0
        del original_size

    def test_separate_subdirs_for_different_report_types(
        self, writer: RunReportWriter, tmp_path: Path
    ) -> None:
        ingest = _ingest_report()
        oneiros = _oneiros_report()
        writer.write(ingest)
        writer.write(oneiros)
        assert (tmp_path / "run_reports" / "ingest" / f"{ingest.run_id}.json").exists()
        assert (tmp_path / "run_reports" / "oneiros" / f"{oneiros.run_id}.json").exists()


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


class TestAtomicity:
    def test_no_partial_file_at_final_path_when_serialisation_crashes(
        self, writer: RunReportWriter
    ) -> None:
        """A crash *during model_dump_json* must leave the final path absent.

        We force model_dump_json to raise before any disk write happens;
        the writer must propagate the exception and the final path must
        not exist (no half-written .json file at the citation address).
        """
        report = _ingest_report()
        final_path = writer.path_for(report)
        assert not final_path.exists()
        with (
            patch.object(
                IngestRunReport,
                "model_dump_json",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            writer.write(report)
        assert not final_path.exists()

    def test_no_partial_file_at_final_path_when_replace_crashes(
        self, writer: RunReportWriter
    ) -> None:
        """A crash *during os.replace* must leave the final path absent.

        The .tmp file may still be on disk (clean up on next run), but
        readers querying the final path see "no report yet", never a
        half-written one.
        """
        report = _ingest_report()
        final_path = writer.path_for(report)
        with (
            patch("theogony.reporting.writer.os.replace", side_effect=OSError("boom")),
            pytest.raises(OSError, match="boom"),
        ):
            writer.write(report)
        assert not final_path.exists()

    def test_tmp_file_never_remains_at_final_address(
        self, writer: RunReportWriter, tmp_path: Path
    ) -> None:
        """After a successful write, only the .json exists — no .tmp left over."""
        report = _ingest_report()
        writer.write(report)
        ingest_dir = tmp_path / "run_reports" / "ingest"
        files = list(ingest_dir.iterdir())
        assert all(f.suffix == ".json" for f in files)


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


class TestPrune:
    def test_keeps_most_recent_n(self, writer: RunReportWriter) -> None:
        # Insert 10 oneiros reports with explicit ULID-shaped run_ids
        # that sort in known order.
        run_ids = [f"01HK0000000000000000000{i:03d}" for i in range(10)]
        for rid in run_ids:
            writer.write(_oneiros_report(run_id=rid))
        removed = writer.prune_to("oneiros", keep=4)
        assert removed == 6
        remaining = sorted(f.stem for f in writer.directory_for("oneiros").iterdir() if f.is_file())
        assert remaining == sorted(run_ids[-4:])  # six oldest gone

    def test_keep_more_than_present_is_noop(self, writer: RunReportWriter) -> None:
        for _ in range(3):
            writer.write(_oneiros_report())
        removed = writer.prune_to("oneiros", keep=10)
        assert removed == 0

    def test_ignores_non_json_files(self, writer: RunReportWriter, tmp_path: Path) -> None:
        ingest_dir = writer.directory_for("oneiros")
        (ingest_dir / "stale.tmp").write_text("garbage")
        (ingest_dir / "README.md").write_text("notes")
        for _ in range(3):
            writer.write(_oneiros_report())
        removed = writer.prune_to("oneiros", keep=1)
        assert removed == 2  # only .json files counted
        # Non-json files survived
        assert (ingest_dir / "stale.tmp").exists()
        assert (ingest_dir / "README.md").exists()
