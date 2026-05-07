"""Tests for :mod:`theogony.extraction.gutenberg_ingest_log`."""

from __future__ import annotations

from pathlib import Path

from theogony.extraction.gutenberg_ingest_log import (
    append_ingest_log,
    chunk_content_sha256,
    ingest_log_path,
    load_completed_chunk_hashes,
)


def test_chunk_hash_stable(tmp_path: Path) -> None:
    assert chunk_content_sha256("αβγ") == chunk_content_sha256("αβγ")
    assert chunk_content_sha256("a") != chunk_content_sha256("b")


def test_load_completed_hashes_filters_params(tmp_path: Path) -> None:
    log = tmp_path / "gutenberg_ingest_log.jsonl"
    append_ingest_log(
        log,
        {
            "kind": "chunk_ok",
            "gutenberg_id": 43497,
            "chunk_chars": 32000,
            "chunk_overlap": 1500,
            "content_sha256": "aa" * 32,
            "nodes_written": 10,
        },
    )
    append_ingest_log(
        log,
        {
            "kind": "chunk_ok",
            "gutenberg_id": 43497,
            "chunk_chars": 16000,
            "chunk_overlap": 750,
            "content_sha256": "bb" * 32,
            "nodes_written": 5,
        },
    )
    h32 = load_completed_chunk_hashes(
        log, gutenberg_id=43497, chunk_chars=32000, chunk_overlap=1500
    )
    assert h32 == {"aa" * 32}
    h16 = load_completed_chunk_hashes(log, gutenberg_id=43497, chunk_chars=16000, chunk_overlap=750)
    assert h16 == {"bb" * 32}


def test_ingest_log_path() -> None:
    p = ingest_log_path(Path("data/foo_lancedb"))
    assert p.name == "gutenberg_ingest_log.jsonl"
    assert p.parent == Path("data/foo_lancedb")
