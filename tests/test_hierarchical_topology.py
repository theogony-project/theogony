"""Unit tests for hierarchical span normalization (no LLM)."""

from theogony.extraction.hierarchical_topology import normalize_span_within_text


def test_normalize_full_text_when_offsets_missing() -> None:
    assert normalize_span_within_text(None, None, 47) == (0, 47)


def test_normalize_invalid_negative_offsets_use_full_text() -> None:
    assert normalize_span_within_text(-1, 10, 100) == (0, 100)


def test_normalize_clamps_order_and_bounds() -> None:
    assert normalize_span_within_text(5, 15, 100) == (5, 15)
    assert normalize_span_within_text(200, 300, 100) == (0, 100)
    assert normalize_span_within_text(30, 20, 100) == (0, 100)
