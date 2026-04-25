"""W13 verification pool stub tests."""

from __future__ import annotations

from pathlib import Path

from theogony.config.settings import Settings
from theogony.curiosity.verification_pool import PoolEntry, VerificationPool


def _settings(tmp_path: Path) -> Settings:
    return Settings().model_copy(update={"data_dir": tmp_path})


def test_pool_register_writes_json_entry(tmp_path: Path) -> None:
    pool = VerificationPool(_settings(tmp_path))
    entry = pool.register("Sven Hedin", ingest_run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")

    path = tmp_path / "run_reports" / "verification_pool" / f"{entry.entry_id}.json"
    assert path.is_file()
    persisted = PoolEntry.model_validate_json(path.read_text(encoding="utf-8"))
    assert persisted.candidate_label == "Sven Hedin"
    assert persisted.ingest_run_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert persisted.lifecycle == "unobserved"


def test_pool_entries_returns_all_registered(tmp_path: Path) -> None:
    pool = VerificationPool(_settings(tmp_path))
    one = pool.register("one")
    two = pool.register("two")

    entries = pool.entries()
    assert {e.entry_id for e in entries} == {one.entry_id, two.entry_id}
    assert {e.candidate_label for e in entries} == {"one", "two"}
