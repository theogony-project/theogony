"""
Append-only JSONL audit log for :mod:`ingest_gutenberg_mesh` (root script).

Each successfully persisted chunk yields one ``chunk_ok`` line with a SHA-256 of the exact
chunk text plus chunking parameters, so a later run can ``--resume`` without re-calling the LLM
for identical segments. This is deterministic and avoids embedding-threshold false skips
(overlapping windows, label-level vectors vs chunk text).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

LOG_FILENAME = "gutenberg_ingest_log.jsonl"


def ingest_log_path(db_path: Path | str) -> Path:
    """Path to the JSONL file stored alongside the LanceDB directory."""
    return Path(db_path) / LOG_FILENAME


def chunk_content_sha256(text: str) -> str:
    """SHA-256 of UTF-8 chunk bytes — identity for resume/skip decisions."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plaintext_sha256(text: str) -> str:
    """Fingerprint of the full cleaned plaintext (edition drift detection)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_completed_chunk_hashes(
    log_path: Path,
    *,
    gutenberg_id: int,
    chunk_chars: int,
    chunk_overlap: int,
) -> set[str]:
    """SHA-256 set for chunks already stored under the same chunking parameters."""
    if not log_path.exists():
        return set()
    out: set[str] = set()
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") != "chunk_ok":
                continue
            if rec.get("gutenberg_id") != gutenberg_id:
                continue
            if rec.get("chunk_chars") != chunk_chars or rec.get("chunk_overlap") != chunk_overlap:
                continue
            h = rec.get("content_sha256")
            if isinstance(h, str) and len(h) == 64:
                out.add(h)
    return out


def append_ingest_log(log_path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object as a single line (crash-safe enough for append-only audit)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = [
    "LOG_FILENAME",
    "append_ingest_log",
    "chunk_content_sha256",
    "ingest_log_path",
    "load_completed_chunk_hashes",
    "plaintext_sha256",
]
