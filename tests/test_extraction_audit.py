"""Unit tests for :class:`ExtractionAuditLog` (Plan §2.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from theogony.extraction.audit import AuditRecord, ExtractionAuditLog


def _now() -> datetime:
    return datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------- write


class TestRecord:
    def test_record_inserts_and_returns_rowid(self) -> None:
        with ExtractionAuditLog() as audit:
            row_id = audit.record(
                run_id="run-A",
                stage="relation_extraction",
                prompt="Extract from: ...",
                response='{"relations": []}',
                ts=_now(),
            )
        assert row_id == 1

    def test_consecutive_records_get_increasing_rowids(self) -> None:
        with ExtractionAuditLog() as audit:
            ids = [
                audit.record(
                    run_id="run-A",
                    stage="s",
                    prompt="p",
                    response="r",
                    ts=_now(),
                )
                for _ in range(5)
            ]
        assert ids == [1, 2, 3, 4, 5]

    def test_record_persists_all_optional_fields(self) -> None:
        with ExtractionAuditLog() as audit:
            audit.record(
                run_id="run-A",
                stage="stage4_disambiguation",
                prompt="Mention: Aufschnaiter ...",
                response='{"chosen": "Q123"}',
                sentence_index=42,
                input_tokens=1234,
                output_tokens=56,
                cost_eur=0.0007,
                latency_ms=890,
                model_id="gemini-2.5-flash-lite",
                parse_error=None,
                ts=_now(),
            )
            rows = audit.query_all()
        assert len(rows) == 1
        rec = rows[0]
        assert rec.run_id == "run-A"
        assert rec.stage == "stage4_disambiguation"
        assert rec.sentence_index == 42
        assert rec.input_tokens == 1234
        assert rec.output_tokens == 56
        assert rec.cost_eur == pytest.approx(0.0007)
        assert rec.latency_ms == 890
        assert rec.model_id == "gemini-2.5-flash-lite"
        assert rec.parse_error is None
        assert rec.ts == _now()

    def test_record_persists_parse_error_tag(self) -> None:
        with ExtractionAuditLog() as audit:
            audit.record(
                run_id="run-A",
                stage="relation_extraction",
                prompt="...",
                response="(non-JSON garbage)",
                parse_error="json_decode",
                ts=_now(),
            )
            rec = audit.query_all()[0]
        # Reviewer agent buckets failure modes by parse_error tag —
        # must round-trip exactly.
        assert rec.parse_error == "json_decode"

    def test_record_requires_run_id(self) -> None:
        with ExtractionAuditLog() as audit, pytest.raises(ValueError, match="run_id"):
            audit.record(run_id="", stage="s", prompt="p", response="r")

    def test_record_requires_stage(self) -> None:
        with ExtractionAuditLog() as audit, pytest.raises(ValueError, match="stage"):
            audit.record(run_id="r", stage="", prompt="p", response="r")

    def test_default_timestamp_is_recent(self) -> None:
        # When ts kwarg omitted, the record stamps itself with now(UTC).
        before = datetime.now(UTC)
        with ExtractionAuditLog() as audit:
            audit.record(run_id="r", stage="s", prompt="p", response="r")
            rec = audit.query_all()[0]
        after = datetime.now(UTC)
        assert before <= rec.ts <= after


# ---------------------------------------------------------------- queries


class TestQueries:
    def test_query_for_run_returns_only_matching_rows(self) -> None:
        with ExtractionAuditLog() as audit:
            audit.record(run_id="run-A", stage="s1", prompt="p1", response="r1", ts=_now())
            audit.record(run_id="run-B", stage="s2", prompt="p2", response="r2", ts=_now())
            audit.record(run_id="run-A", stage="s3", prompt="p3", response="r3", ts=_now())
            rows_a = audit.query_for_run("run-A")
            rows_b = audit.query_for_run("run-B")
            rows_c = audit.query_for_run("run-NONEXISTENT")
        assert {r.stage for r in rows_a} == {"s1", "s3"}
        assert {r.stage for r in rows_b} == {"s2"}
        assert rows_c == []

    def test_query_all_returns_insertion_order(self) -> None:
        with ExtractionAuditLog() as audit:
            for i in range(5):
                audit.record(run_id=f"r{i}", stage="s", prompt="p", response="r", ts=_now())
            rows = audit.query_all()
        assert [r.run_id for r in rows] == ["r0", "r1", "r2", "r3", "r4"]

    def test_count_and_count_for_run(self) -> None:
        with ExtractionAuditLog() as audit:
            for _ in range(3):
                audit.record(run_id="A", stage="s", prompt="p", response="r", ts=_now())
            for _ in range(2):
                audit.record(run_id="B", stage="s", prompt="p", response="r", ts=_now())
            assert audit.count() == 5
            assert audit.count_for_run("A") == 3
            assert audit.count_for_run("B") == 2
            assert audit.count_for_run("nope") == 0

    def test_total_cost_for_run(self) -> None:
        with ExtractionAuditLog() as audit:
            audit.record(
                run_id="A",
                stage="s",
                prompt="p",
                response="r",
                cost_eur=0.001,
                ts=_now(),
            )
            audit.record(
                run_id="A",
                stage="s",
                prompt="p",
                response="r",
                cost_eur=0.002,
                ts=_now(),
            )
            audit.record(
                run_id="B",
                stage="s",
                prompt="p",
                response="r",
                cost_eur=0.005,
                ts=_now(),
            )
            assert audit.total_cost_for_run("A") == pytest.approx(0.003)
            assert audit.total_cost_for_run("B") == pytest.approx(0.005)
            assert audit.total_cost_for_run("nope") == 0.0


# ---------------------------------------------------------------- persistence


class TestFilePersistence:
    def test_writes_persist_across_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.sqlite"
        with ExtractionAuditLog(db) as audit:
            audit.record(run_id="A", stage="s", prompt="p1", response="r1", ts=_now())
            audit.record(run_id="A", stage="s", prompt="p2", response="r2", ts=_now())
        # Reopen — rows must still be there.
        with ExtractionAuditLog(db) as audit:
            rows = audit.query_for_run("A")
        assert len(rows) == 2
        assert rows[0].prompt == "p1"
        assert rows[1].prompt == "p2"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        deep = tmp_path / "deeply" / "nested" / "audit.sqlite"
        with ExtractionAuditLog(deep) as audit:
            audit.record(run_id="A", stage="s", prompt="p", response="r", ts=_now())
        assert deep.exists()


# ---------------------------------------------------------------- DTO


class TestAuditRecord:
    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            AuditRecord(  # type: ignore[call-arg]
                id=1,
                ts=_now(),
                run_id="r",
                stage="s",
                prompt="p",
                response="r",
                input_tokens=0,
                output_tokens=0,
                cost_eur=0.0,
                latency_ms=0,
                bogus="x",
            )

    def test_negative_token_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            AuditRecord(
                id=1,
                ts=_now(),
                run_id="r",
                stage="s",
                prompt="p",
                response="r",
                input_tokens=-1,
                output_tokens=0,
                cost_eur=0.0,
                latency_ms=0,
            )


# ---------------------------------------------------------------- concurrency


class TestConcurrency:
    async def test_concurrent_records_serialise_via_lock(self) -> None:
        # Hammer the audit log from many asyncio tasks. Even though
        # sqlite3 + check_same_thread=False is single-threaded for
        # our purposes, the RLock prevents the rare race where two
        # tasks interleave INSERT + SELECT.
        import asyncio

        with ExtractionAuditLog() as audit:

            async def write_one(i: int) -> None:
                # Yield control so other tasks get a chance.
                await asyncio.sleep(0)
                audit.record(
                    run_id="run-A",
                    stage=f"s{i}",
                    prompt=f"p{i}",
                    response=f"r{i}",
                    ts=_now(),
                )

            await asyncio.gather(*[write_one(i) for i in range(50)])
            count = audit.count_for_run("run-A")
        assert count == 50
