"""Verification pool: sampling reservoir for post-hoc immune verification (W13–W14)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.settings import Settings

PoolLifecycle = Literal["unobserved", "sampled_by_athene", "cleared", "archived"]


class PoolEntry(BaseModel):
    """One acquired candidate awaiting asynchronous post-hoc verification."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_label: str
    ingest_run_id: str | None = None
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lifecycle: PoolLifecycle = "unobserved"

    source_type: str | None = None
    source_identifier: str | None = None
    target_node_ids: list[str] = Field(default_factory=list)
    sampled_by: list[str] = Field(default_factory=list)
    sampled_at: datetime | None = None
    cleared_at: datetime | None = None
    finding_ids: list[str] = Field(default_factory=list)


class VerificationPoolStats(BaseModel):
    """Aggregate counts over on-disk pool entries."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    unobserved: int = 0
    sampled_by_athene: int = 0
    cleared: int = 0
    archived: int = 0
    findings_total: int = 0


class VerificationPoolStatusDTO(BaseModel):
    """Cockpit read model for verification pool visibility (W14)."""

    model_config = ConfigDict(extra="forbid")

    stats: VerificationPoolStats
    recent_entries: list[PoolEntry]


class VerificationPool:
    """Disk-backed pool; W14 adds sampling and Athene lifecycle updates."""

    def __init__(self, settings: Settings) -> None:
        self._pool_dir = Path(settings.run_reports_dir) / "verification_pool"
        self._pool_dir.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        candidate_label: str,
        ingest_run_id: str | None = None,
        *,
        source_type: str | None = None,
        source_identifier: str | None = None,
        target_node_ids: list[str] | None = None,
    ) -> PoolEntry:
        entry = PoolEntry(
            candidate_label=candidate_label,
            ingest_run_id=ingest_run_id,
            source_type=source_type,
            source_identifier=source_identifier,
            target_node_ids=list(target_node_ids or ()),
        )
        self._persist(entry)
        return entry

    def get(self, entry_id: str) -> PoolEntry | None:
        path = self._pool_dir / f"{entry_id}.json"
        if not path.is_file():
            return None
        return PoolEntry.model_validate_json(path.read_text(encoding="utf-8"))

    def stats(self) -> VerificationPoolStats:
        entries = self.entries()
        counts = {
            "unobserved": 0,
            "sampled_by_athene": 0,
            "cleared": 0,
            "archived": 0,
        }
        findings_total = 0
        for e in entries:
            if e.lifecycle in counts:
                counts[e.lifecycle] += 1
            findings_total += len(e.finding_ids)
        return VerificationPoolStats(
            total=len(entries),
            unobserved=counts["unobserved"],
            sampled_by_athene=counts["sampled_by_athene"],
            cleared=counts["cleared"],
            archived=counts["archived"],
            findings_total=findings_total,
        )

    def sample_for_athene(
        self,
        *,
        sample_rate: float,
        max_entries: int,
        min_entries: int,
        seed: int | None = None,
    ) -> list[PoolEntry]:
        eligible = [e for e in self.entries() if e.lifecycle == "unobserved"]
        if not eligible:
            return []
        rng: random.Random = random.Random(seed) if seed is not None else random.SystemRandom()

        selected: list[PoolEntry] = []
        selected_ids: set[str] = set()
        for entry in eligible:
            if rng.random() < sample_rate:
                selected.append(entry)
                selected_ids.add(entry.entry_id)

        if len(selected) < min_entries:
            rest = [e for e in eligible if e.entry_id not in selected_ids]
            rng.shuffle(rest)
            for entry in rest:
                if len(selected) >= min_entries:
                    break
                selected.append(entry)
                selected_ids.add(entry.entry_id)

        return selected[:max_entries]

    def mark_sampled_by_athene(self, entry_id: str, *, finding_ids: list[str]) -> PoolEntry:
        entry = self.get(entry_id)
        if entry is None:
            msg = f"pool entry not found: {entry_id}"
            raise ValueError(msg)
        now = datetime.now(UTC)
        sampled_by = list(entry.sampled_by)
        if "athene" not in sampled_by:
            sampled_by.append("athene")
        merged_findings = list(entry.finding_ids)
        for fid in finding_ids:
            if fid not in merged_findings:
                merged_findings.append(fid)
        updated = entry.model_copy(
            update={
                "lifecycle": "sampled_by_athene",
                "sampled_by": sampled_by,
                "sampled_at": now,
                "finding_ids": merged_findings,
            }
        )
        self._persist(updated)
        return updated

    def entries(self) -> list[PoolEntry]:
        parsed = [
            PoolEntry.model_validate_json(p.read_text(encoding="utf-8"))
            for p in self._pool_dir.glob("*.json")
        ]
        return sorted(parsed, key=lambda e: e.acquired_at)

    def _persist(self, entry: PoolEntry) -> None:
        (self._pool_dir / f"{entry.entry_id}.json").write_text(
            entry.model_dump_json(indent=2),
            encoding="utf-8",
        )


__all__ = [
    "PoolEntry",
    "PoolLifecycle",
    "VerificationPool",
    "VerificationPoolStats",
    "VerificationPoolStatusDTO",
]
