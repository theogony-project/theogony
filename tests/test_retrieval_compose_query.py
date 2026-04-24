"""Tests for :func:`theogony.retrieval.pipeline.compose_query_for_retrieval`."""

from __future__ import annotations

from theogony.retrieval.pipeline import compose_query_for_retrieval


def test_compose_without_expansion_returns_query() -> None:
    assert compose_query_for_retrieval("Who is he?", None) == "Who is he?"
    assert compose_query_for_retrieval("Who is he?", "") == "Who is he?"


def test_compose_merges_expansion_and_question() -> None:
    out = compose_query_for_retrieval(
        "What did he do?",
        "User:\nWe talked about Daedalus.\n\nAssistant:\nHe builds systems.",
    )
    assert "Current question:" in out
    assert "What did he do?" in out
    assert "Daedalus" in out


def test_compose_truncates_very_long_expansion() -> None:
    exp = "x" * 20_000
    out = compose_query_for_retrieval("Short?", exp, max_chars=500)
    assert "Current question:" in out
    assert "Short?" in out
    assert len(out) <= 520
