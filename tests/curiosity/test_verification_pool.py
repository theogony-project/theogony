"""Verification pool (W13 stub + W14 sampling reservoir)."""

from __future__ import annotations

import json
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


def test_pool_entry_backwards_compatible_with_w13_shape(tmp_path: Path) -> None:
    pool_dir = tmp_path / "run_reports" / "verification_pool"
    pool_dir.mkdir(parents=True)
    legacy = {
        "entry_id": "legacy-id",
        "candidate_label": "old",
        "ingest_run_id": None,
        "acquired_at": "2026-04-25T00:00:00+00:00",
        "lifecycle": "unobserved",
    }
    (pool_dir / "legacy-id.json").write_text(json.dumps(legacy), encoding="utf-8")
    pool = VerificationPool(_settings(tmp_path))
    e = pool.get("legacy-id")
    assert e is not None
    assert e.source_type is None
    assert e.finding_ids == []


def test_pool_stats_counts_lifecycle_and_findings(tmp_path: Path) -> None:
    pool = VerificationPool(_settings(tmp_path))
    pool.register("a", ingest_run_id="x")
    e2 = pool.register("b")
    pool.mark_sampled_by_athene(e2.entry_id, finding_ids=["FINDING-1", "FINDING-2"])
    st = pool.stats()
    assert st.total == 2
    assert st.unobserved == 1
    assert st.sampled_by_athene == 1
    assert st.findings_total == 2


def test_sample_for_athene_samples_at_least_min_when_enabled(tmp_path: Path) -> None:
    pool = VerificationPool(_settings(tmp_path))
    for i in range(5):
        pool.register(f"c{i}", ingest_run_id=f"id{i}")
    out = pool.sample_for_athene(sample_rate=0.0, max_entries=50, min_entries=1, seed=42)
    assert len(out) == 1


def test_sample_for_athene_respects_max_entries(tmp_path: Path) -> None:
    pool = VerificationPool(_settings(tmp_path))
    for i in range(20):
        pool.register(f"c{i}", ingest_run_id=f"id{i}")
    out = pool.sample_for_athene(sample_rate=1.0, max_entries=3, min_entries=1, seed=1)
    assert len(out) == 3


def test_mark_sampled_by_athene_persists_finding_ids(tmp_path: Path) -> None:
    pool = VerificationPool(_settings(tmp_path))
    e = pool.register("x", ingest_run_id="ing")
    updated = pool.mark_sampled_by_athene(e.entry_id, finding_ids=["FINDING-abc"])
    assert updated.lifecycle == "sampled_by_athene"
    assert "FINDING-abc" in updated.finding_ids
    again = pool.get(e.entry_id)
    assert again is not None
    assert again.finding_ids == ["FINDING-abc"]


def test_get_returns_none_for_missing(tmp_path: Path) -> None:
    pool = VerificationPool(_settings(tmp_path))
    assert pool.get("does-not-exist") is None
