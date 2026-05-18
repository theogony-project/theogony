from __future__ import annotations

import pytest

from theogony.mesh.seeds.wikidata5m.limits import (
    seed_write_batch_size,
    truncate_seed_embedding_text,
)


def test_truncate_seed_embedding_text_keeps_short_text() -> None:
    text, truncated = truncate_seed_embedding_text("short paragraph", max_chars=100)
    assert text == "short paragraph"
    assert truncated is False


def test_truncate_seed_embedding_text_clips_long_text() -> None:
    long_text = "x" * 50
    text, truncated = truncate_seed_embedding_text(long_text, max_chars=20)
    assert truncated is True
    assert len(text) == 20
    assert text.endswith("…")


def test_seed_write_batch_size_caps_peak_flush() -> None:
    assert seed_write_batch_size(8) == 32
    assert seed_write_batch_size(64) == 128


def test_truncate_seed_embedding_text_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        truncate_seed_embedding_text("text", max_chars=0)
