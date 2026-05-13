"""Append-only audit ledger for mesh operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import lancedb
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
    """Lance-backed append-only audit table."""

    def __init__(self, db: lancedb.DBConnection) -> None:
        self._db = db
        if "mesh_audit" not in db.list_tables():
            self._table = db.create_table("mesh_audit", schema=_AUDIT_SCHEMA)
        else:
            self._table = db.open_table("mesh_audit")

    def append(self, *, action: str, detail: dict[str, Any]) -> str:
        """Write one audit row; returns the row id (ULID)."""
        row_id = str(ULID())
        now = datetime.now(UTC)
        self._table.add(
            [
                {
                    "id": row_id,
                    "recorded_at": now,
                    "action": action,
                    "payload_json": json.dumps(detail, default=str),
                }
            ]
        )
        return row_id
