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


class MeshAuditLog:
    """Append-only audit table for Oneiros operations and agent-driven actions."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        resp = db.list_tables()
        if "mesh_audit" not in (resp.tables or []):
            self._table: lancedb.table.LanceTable = db.create_table(
                "mesh_audit", schema=_AUDIT_SCHEMA
            )
        else:
            self._table = db.open_table("mesh_audit")

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

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent audit rows (newest first)."""
        rows = self._table.to_arrow().to_pylist()
        rows.sort(key=lambda r: r["recorded_at"], reverse=True)
        return cast("list[dict[str, Any]]", rows[:limit])

    def count(self) -> int:
        return int(self._table.count_rows())
