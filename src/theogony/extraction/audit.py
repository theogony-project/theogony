"""
ExtractionAuditLog — append-only SQLite log of every LLM call (Plan §2.5).

One row per LLM call across the extraction pipeline (BookContextExtractor,
EntityResolver Stage 4, RelationExtractor; future stages plug in the
same way). The log is the audit trail Athene / the Reviewer agent
(PHX-0035) consume to detect drift, evaluate provider quality, and
trace any minted node / edge back to the exact prompt that produced it.

Design points (Plan §2.5 spec: "append-only SQLite, write-only from
pipeline, read by debug tooling"):

- **Append-only.** ``record`` always inserts; the schema does not
  expose UPDATE or DELETE. Tests can read via ``query_all`` /
  ``query_for_run`` for assertions.
- **Local SQLite.** No daemon, no network. Runs alongside the
  ``theogony`` process; one file per data directory. Concurrent
  ingest tasks share the connection via a write lock — SQLite's
  WAL mode handles this comfortably for the volumes Plan §4.1
  predicts (~3 000 LLM calls per book ingest).
- **Schema is forward-compatible.** New columns can be added via
  ``ALTER TABLE`` migrations without invalidating prior rows.
  Initial schema covers the 11 fields Plan §2.5 calls for.
- **No async needed.** SQLite writes are sub-millisecond; we run
  ``record`` synchronously and let the caller decide whether to
  wrap in ``asyncio.to_thread`` if they have a hot loop.

What this module deliberately does NOT do:

- It does not enforce any retention policy. The audit log grows
  monotonically; rotation is a Gen 2 / PHX deferral.
- It does not encrypt or redact prompts. Plan §3.6 keeps secrets
  out of prompts at the boundary; the audit log assumes the data
  it sees is already safe to store.
- It does not interpret rows — that's the Reviewer agent's job.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.logging import get_logger

log = get_logger("extraction.audit")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    run_id          TEXT    NOT NULL,
    stage           TEXT    NOT NULL,
    sentence_index  INTEGER,
    prompt          TEXT    NOT NULL,
    response        TEXT    NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_eur        REAL    NOT NULL DEFAULT 0.0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    model_id        TEXT    NOT NULL DEFAULT '',
    parse_error     TEXT
);

CREATE INDEX IF NOT EXISTS llm_calls_run_id_idx ON llm_calls (run_id);
CREATE INDEX IF NOT EXISTS llm_calls_stage_idx ON llm_calls (stage);
"""


class AuditRecord(BaseModel):
    """Read-only projection of one ``llm_calls`` row.

    Returned by the query helpers; callers (tests, Reviewer agent)
    consume this rather than raw tuples for type discipline.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    ts: datetime
    run_id: str
    stage: str
    sentence_index: int | None = None
    prompt: str
    response: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_eur: float = Field(ge=0.0)
    latency_ms: int = Field(ge=0)
    model_id: str = ""
    parse_error: str | None = None


class ExtractionAuditLog:
    """Append-only audit log backed by a local SQLite database.

    Use as a context manager so the connection is closed on exit::

        with ExtractionAuditLog(path="data/audit.sqlite") as audit:
            audit.record(run_id=..., stage="relation_extraction", ...)

    Or pass the path-only constructor and call :meth:`close` manually
    (lifecycle managed elsewhere — typical for a long-running
    ``theogony serve``).

    Concurrency: every method that touches the database acquires an
    internal RLock so ingest tasks running at concurrency 8 (Plan
    §4.1) serialise their writes. SQLite WAL mode keeps reads from
    blocking writes; for Gen 1 ingest volumes (~3 000 LLM calls per
    book), the lock contention is negligible.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path: Path | None = Path(path) if path != ":memory:" else None
        self._conn: sqlite3.Connection | None = None
        self._lock = RLock()
        # ":memory:" passed verbatim to sqlite3.connect when no path.
        self._memory_path: str = str(path) if path == ":memory:" else ":memory:"

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            target = str(self._path)
        else:
            target = self._memory_path  # ":memory:"
        # check_same_thread=False so the lock-protected connection
        # can be shared by asyncio tasks that run on the same thread
        # (default) and the rare pool-thread call that wraps a sync
        # operation in asyncio.to_thread.
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL mode: many readers, one writer at a time, no full-DB
        # lock during writes. Best fit for our pattern.
        if self._path is not None:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        self._conn = conn
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._ensure_conn().cursor()
            try:
                yield cur
            finally:
                cur.close()

    # ------------------------------------------------------------- write

    def record(
        self,
        *,
        run_id: str,
        stage: str,
        prompt: str,
        response: str,
        sentence_index: int | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_eur: float = 0.0,
        latency_ms: int = 0,
        model_id: str = "",
        parse_error: str | None = None,
        ts: datetime | None = None,
    ) -> int:
        """Insert one row, return its rowid.

        ``ts`` defaults to ``datetime.now(UTC)`` when omitted; tests
        pass it explicitly for deterministic assertions.

        ``parse_error`` is a short tag string ("evidence_span_outside_central",
        "json_decode", "stage4_llm_refused") used by the Reviewer
        agent to bucket failure modes. None means "call succeeded".
        """
        if not run_id:
            raise ValueError("run_id is required")
        if not stage:
            raise ValueError("stage is required")
        timestamp = (ts or datetime.now(UTC)).isoformat()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO llm_calls "
                "(ts, run_id, stage, sentence_index, prompt, response, "
                "input_tokens, output_tokens, cost_eur, latency_ms, model_id, parse_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    run_id,
                    stage,
                    sentence_index,
                    prompt,
                    response,
                    int(input_tokens),
                    int(output_tokens),
                    float(cost_eur),
                    int(latency_ms),
                    model_id,
                    parse_error,
                ),
            )
            self._ensure_conn().commit()
            row_id = cur.lastrowid
            assert row_id is not None  # sqlite3 returns int after INSERT
            return row_id

    # ------------------------------------------------------------- read

    def query_for_run(self, run_id: str) -> list[AuditRecord]:
        """Return all rows for a run, in insertion order. For tests + tooling."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM llm_calls WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            )
            return [_record_from_row(row) for row in cur.fetchall()]

    def query_all(self) -> list[AuditRecord]:
        """Return every row, in insertion order. For tests + tooling."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM llm_calls ORDER BY id ASC")
            return [_record_from_row(row) for row in cur.fetchall()]

    def count(self) -> int:
        """Return the total row count. Cheap; used by report aggregation."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM llm_calls")
            return int(cur.fetchone()[0])

    def count_for_run(self, run_id: str) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM llm_calls WHERE run_id = ?", (run_id,))
            return int(cur.fetchone()[0])

    def total_cost_for_run(self, run_id: str) -> float:
        """Sum of ``cost_eur`` across every row for the given run.

        Used by IngestRunReport.relations.llm_cost_eur and similar
        aggregates. Returns 0.0 when there are no rows.
        """
        with self._cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(cost_eur), 0.0) FROM llm_calls WHERE run_id = ?",
                (run_id,),
            )
            return float(cur.fetchone()[0])

    # ------------------------------------------------------------- lifecycle

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> ExtractionAuditLog:
        self._ensure_conn()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _record_from_row(row: sqlite3.Row) -> AuditRecord:
    """Build an AuditRecord from a sqlite3.Row.

    The ``ts`` column is stored as ISO-format string; we parse it
    back to ``datetime`` here so consumers don't have to.
    """
    raw: dict[str, Any] = dict(row)
    ts_raw = raw["ts"]
    raw["ts"] = datetime.fromisoformat(ts_raw)
    return AuditRecord(**raw)


__all__ = ["AuditRecord", "ExtractionAuditLog"]
