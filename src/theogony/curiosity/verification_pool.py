"""Verification pool stub for W13 pre-gate removal."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.settings import Settings


class PoolEntry(BaseModel):
    """One acquired candidate awaiting asynchronous post-hoc verification."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_label: str
    ingest_run_id: str | None = None
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lifecycle: str = "unobserved"


class VerificationPool:
    """Stub pool. W14 replaces this with the full sampling reservoir."""

    def __init__(self, settings: Settings) -> None:
        self._pool_dir = Path(settings.run_reports_dir) / "verification_pool"
        self._pool_dir.mkdir(parents=True, exist_ok=True)

    def register(self, candidate_label: str, ingest_run_id: str | None = None) -> PoolEntry:
        entry = PoolEntry(candidate_label=candidate_label, ingest_run_id=ingest_run_id)
        (self._pool_dir / f"{entry.entry_id}.json").write_text(
            entry.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return entry

    def entries(self) -> list[PoolEntry]:
        return [
            PoolEntry.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self._pool_dir.glob("*.json"))
        ]


__all__ = ["PoolEntry", "VerificationPool"]
