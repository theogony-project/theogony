"""Memory-safe defaults for the wikidata5m bulk seed path."""

from __future__ import annotations

DEFAULT_SEED_EMBEDDING_MAX_CHARS = 2_048
DEFAULT_SEED_EMBEDDING_BATCH_SIZE = 8
MAX_SEED_WRITE_BATCH_SIZE = 128


def truncate_seed_embedding_text(text: str, *, max_chars: int) -> tuple[str, bool]:
    """Return text clipped for embedding; second value is True when truncated."""
    if max_chars <= 0:
        raise ValueError(f"max_chars must be > 0; got {max_chars}")
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped, False
    clipped = stripped[: max_chars - 1].rstrip() + "…"
    return clipped, True


def seed_write_batch_size(embedding_batch_size: int) -> int:
    if embedding_batch_size <= 0:
        raise ValueError(f"embedding_batch_size must be > 0; got {embedding_batch_size}")
    return min(max(embedding_batch_size * 4, embedding_batch_size), MAX_SEED_WRITE_BATCH_SIZE)
