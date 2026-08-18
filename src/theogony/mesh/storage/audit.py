"""Append-only Lance audit ledger for mesh operations.

Records are never modified. Lance versioning means historical reads are cheap.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import lancedb
import lancedb.table
import pyarrow as pa
from ulid import ULID

_AUDIT_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("recorded_at", pa.timestamp("us", tz="UTC")),
        ("action", pa.string()),
        ("payload_json", pa.string()),
    ]
)


# Staged rows are lost if the process dies before a flush, so the bound is low
# enough that little is at risk and high enough that the write cost amortises.
_STAGE_FLUSH_LIMIT = 256


class MeshAuditLog:
    """Append-only audit table for Oneiros operations and agent-driven actions."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        resp = db.list_tables()
        if "mesh_audit" not in (resp.tables or []):
            # lancedb >= 0.37 returns the general `Table` from create/open; the
            # concrete LanceTable is an implementation detail we never rely on.
            self._table: lancedb.table.Table = db.create_table("mesh_audit", schema=_AUDIT_SCHEMA)
        else:
            self._table = db.open_table("mesh_audit")
        self._staged: list[dict[str, Any]] = []

    @staticmethod
    def _row(action: str, detail: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        row_id = str(ULID())
        now = datetime.now(UTC)
        return row_id, {
            "id": row_id,
            "recorded_at": now,
            "action": action,
            "payload_json": json.dumps(detail, default=str),
        }

    def append(self, *, action: str, detail: dict[str, Any]) -> str:
        """Write one audit row; returns the row id (ULID string)."""
        row_id, row = self._row(action, detail)
        self._table.add([row])
        return row_id

    def append_many(self, entries: list[tuple[str, dict[str, Any]]]) -> list[str]:
        """Write many audit rows and return their ids."""
        if not entries:
            return []
        built = [self._row(action, detail) for action, detail in entries]
        self._table.add([row for _, row in built])
        return [row_id for row_id, _ in built]

    def stage(self, *, action: str, detail: dict[str, Any]) -> str:
        """Stamp an audit row now, write it with the next :meth:`flush`.

        One Lance transaction per row is affordable for the handful of run-level
        entries; it is not affordable for the per-item ones. Measured inside a
        real ingest, `append` cost **269.8 ms** per call and was the single
        largest term in the whole resolution stage — 22.1 s of 26.5 s for six
        paragraphs (PHX-1061). In isolation the same call measures 3.1 ms, which
        is why this never showed up outside a full run.

        The row is built here, not at flush time, so `id` and `recorded_at`
        record when the event happened rather than when it was written. Reads on
        this log flush first, so a staged row is never invisible to a caller.
        """
        row_id, row = self._row(action, detail)
        self._staged.append(row)
        if len(self._staged) >= _STAGE_FLUSH_LIMIT:
            self.flush()
        return row_id

    def flush(self) -> int:
        """Write staged rows as one transaction; returns how many were written."""
        if not self._staged:
            return 0
        rows, self._staged = self._staged, []
        self._table.add(rows)
        return len(rows)

    def pending(self) -> int:
        """Rows stamped but not yet written."""
        return len(self._staged)

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent audit rows (newest first)."""
        self.flush()
        rows = self._table.to_arrow().to_pylist()
        rows.sort(key=lambda r: r["recorded_at"], reverse=True)
        return cast("list[dict[str, Any]]", rows[:limit])

    def count(self) -> int:
        self.flush()
        return int(self._table.count_rows())
