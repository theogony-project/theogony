"""Unit tests for Explorer chat compaction (cockpit-only)."""

from __future__ import annotations

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.cockpit.explorer_chat import (
    CHAT_COMPACT_TRIGGER_TOKENS,
    CHAT_MAX_MESSAGE_CHARS,
    ExplorerChatTurn,
    estimate_chat_block_tokens,
    parse_explorer_chat_messages,
    parse_explorer_rolling_summary,
    prepare_explorer_chat_for_synthesis,
    rough_token_estimate,
    update_explorer_chat_history_summary,
)


def test_rough_token_estimate_positive() -> None:
    assert rough_token_estimate("") == 0
    assert rough_token_estimate("abc") >= 1


def test_parse_explorer_chat_messages_empty() -> None:
    assert parse_explorer_chat_messages(None) == []
    assert parse_explorer_chat_messages([]) == []


def test_parse_explorer_chat_messages_rejects_non_list() -> None:
    with pytest.raises(ValueError, match="array"):
        parse_explorer_chat_messages({})


def test_parse_explorer_rolling_summary() -> None:
    assert parse_explorer_rolling_summary(None) == ""
    assert parse_explorer_rolling_summary("  hello  ") == "hello"


@pytest.mark.asyncio
async def test_prepare_stub_drops_oversized_single_turn() -> None:
    # Several max-sized turns so total rough tokens exceed the compaction trigger.
    prior: list[ExplorerChatTurn] = []
    for _ in range(6):
        prior.append(
            ExplorerChatTurn(role="user", content="w" * CHAT_MAX_MESSAGE_CHARS),
        )
        prior.append(ExplorerChatTurn(role="assistant", content="ack"))
    assert estimate_chat_block_tokens("", prior) > CHAT_COMPACT_TRIGGER_TOKENS
    block, summary, kept, meta = await prepare_explorer_chat_for_synthesis(
        rolling_summary="",
        prior_messages=prior,
        llm=StubLLMProvider(),
    )
    assert meta["compacted"] is True
    assert len(kept) < len(prior)
    assert estimate_chat_block_tokens(summary, kept) <= CHAT_COMPACT_TRIGGER_TOKENS


@pytest.mark.asyncio
async def test_prepare_noop_when_small() -> None:
    prior = [
        ExplorerChatTurn(role="user", content="What is X?"),
        ExplorerChatTurn(role="assistant", content="X is a letter."),
    ]
    block, summary, kept, meta = await prepare_explorer_chat_for_synthesis(
        rolling_summary="",
        prior_messages=prior,
        llm=StubLLMProvider(),
    )
    assert meta["compacted"] is False
    assert kept == prior
    assert summary == ""
    assert "User:" in block or "User" in block


@pytest.mark.asyncio
async def test_update_history_summary_runs_after_each_answer_with_stub() -> None:
    summary, meta = await update_explorer_chat_history_summary(
        rolling_summary="Earlier: user asked about explorers.",
        question="Welche genau?",
        context_questions=["Sven Hedin Tibet Forschung", "geografische Entdeckungen"],
        answer="Sven Hedin erforschte Transhimalaya-Routen und Kartenmaterial.",
        llm=StubLLMProvider(),
    )
    assert "Earlier" in summary
    assert "Welche genau? (Sven Hedin Tibet Forschung - geografische Entdeckungen)" in summary
    assert "Transhimalaya" in summary
    assert meta["post_answer_summary_used_llm"] is False
