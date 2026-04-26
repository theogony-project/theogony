"""Explorer multi-turn chat: token budget (~100k) and optional LLM compaction.

Cockpit-only helpers — keep the main retrieval pipeline free of UI concepts
except the optional ``synthesis_conversation_context`` string passed into
:class:`~theogony.retrieval.pipeline.QueryPipeline.ask`.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from theogony.agents.llm import LLMProvider, StubLLMProvider

# Rough context budget (Explorer); constellation JSON is separate in synthesis.
CHAT_MAX_CONTEXT_TOKENS = 100_000
CHAT_COMPACT_TRIGGER_TOKENS = 85_000
CHAT_MAX_MESSAGES = 400
CHAT_MAX_MESSAGE_CHARS = 48_000
CHAT_MAX_SUMMARY_CHARS = 120_000

_SUMMARY_SYSTEM = (
    "You compress dialogue for a retrieval-grounded assistant. "
    "Reply with plain prose only (no JSON, no markdown headings). "
    "Preserve names, technical terms, and unresolved follow-up questions. "
    "Be dense; aim under ~3000 words."
)

_HISTORY_SUMMARY_SYSTEM = (
    "You maintain a compact chat-history summary for a retrieval planning step. "
    "Reply with plain prose only. Preserve named entities, user intent, concrete "
    "answers, and unresolved follow-up targets. Do not add facts."
)


class ExplorerChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=CHAT_MAX_MESSAGE_CHARS)


def rough_token_estimate(text: str) -> int:
    """Liberal byte/3 heuristic (OK for budget gating, not billing)."""
    if not text:
        return 0
    return max(1, len(text.encode("utf-8"))) // 3


def _format_turns(summary: str, messages: list[ExplorerChatTurn]) -> str:
    parts: list[str] = []
    s = summary.strip()
    if s:
        parts.append("Rolling summary of earlier exchanges:\n" + s)
    for m in messages:
        lab = "User" if m.role == "user" else "Assistant"
        parts.append(f"\n{lab}:\n{m.content.strip()}\n")
    return "\n".join(parts).strip()


def estimate_chat_block_tokens(summary: str, messages: list[ExplorerChatTurn]) -> int:
    return rough_token_estimate(_format_turns(summary, messages))


def hard_truncate_chat_block(block: str) -> str:
    """Last resort wall at ~100k tokens of *chat* context (UTF-8 bytes / 3)."""
    max_chars = CHAT_MAX_CONTEXT_TOKENS * 3
    if len(block) <= max_chars:
        return block
    return (
        block[: max_chars - 220].rstrip()
        + "\n\n[Explorer: prior chat context truncated at 100k-token budget]\n"
    )


def parse_explorer_chat_messages(raw: Any) -> list[ExplorerChatTurn]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("conversation_messages must be a JSON array or omitted")
    if len(raw) > CHAT_MAX_MESSAGES:
        raise ValueError(f"conversation_messages exceeds {CHAT_MAX_MESSAGES} items")
    return TypeAdapter(list[ExplorerChatTurn]).validate_python(raw)


def parse_explorer_rolling_summary(raw: Any) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ValueError("conversation_summary must be a string or null")
    s = raw.strip()
    if len(s) > CHAT_MAX_SUMMARY_CHARS:
        s = s[-CHAT_MAX_SUMMARY_CHARS:]
    return s


async def prepare_explorer_chat_for_synthesis(
    *,
    rolling_summary: str,
    prior_messages: list[ExplorerChatTurn],
    llm: LLMProvider,
) -> tuple[str, str, list[ExplorerChatTurn], dict[str, Any]]:
    """Trim or LLM-summarise chat so the synthesis prefix stays under budget.

    Returns ``(synthesis_conversation_context, rolling_summary_out, prior_messages_out, meta)``.
    ``prior_messages_out`` is the canonical suffix the client should send next time
    (after compaction); on a no-op pass it equals ``prior_messages``.
    """
    t0 = time.perf_counter()
    meta: dict[str, Any] = {
        "compacted": False,
        "summarization_ms": 0,
        "llm_summary_rounds": 0,
        "stub_dropped_turns": 0,
        "tokens_estimated_before": 0,
        "tokens_estimated_after": 0,
    }
    summary = rolling_summary.strip()
    msgs: list[ExplorerChatTurn] = list(prior_messages)
    meta["tokens_estimated_before"] = estimate_chat_block_tokens(summary, msgs)
    use_stub = isinstance(llm, StubLLMProvider)
    summarize_ms = 0

    while estimate_chat_block_tokens(summary, msgs) > CHAT_COMPACT_TRIGGER_TOKENS:
        meta["compacted"] = True
        if use_stub:
            if len(msgs) >= 2:
                msgs = msgs[2:]
                meta["stub_dropped_turns"] = int(meta["stub_dropped_turns"]) + 2
            elif len(msgs) == 1:
                msgs = []
                meta["stub_dropped_turns"] = int(meta["stub_dropped_turns"]) + 1
            elif summary:
                drop = max(len(summary) // 3, 8000)
                summary = summary[drop:].strip()
                if not summary:
                    summary = (
                        "[Earlier dialogue omitted: Explorer chat hit token budget "
                        "with stub LLM — no summariser available.]"
                    )
            else:
                break
        else:
            prompt = (
                "Existing rolling summary (may be empty):\n\n"
                f"{summary if summary else '(none)'}\n\n"
                "Conversation lines to fold in:\n\n"
                f"{_format_turns('', msgs)}\n\n"
                "Write one updated rolling summary that merges the old summary and "
                "the conversation. Prefer bullet clusters over long prose."
            )
            t_llm = time.perf_counter()
            try:
                res = await llm.complete(
                    prompt,
                    system=_SUMMARY_SYSTEM,
                    max_output_tokens=4096,
                    temperature=0.0,
                )
                summary = res.text.strip()
                if not summary:
                    summary = "[Chat compaction returned empty text.]"
            except Exception:
                msgs = msgs[4:] if len(msgs) >= 4 else []
                if not summary and not msgs:
                    summary = "[Chat compaction failed; context dropped.]"
            summarize_ms += int((time.perf_counter() - t_llm) * 1000)
            meta["llm_summary_rounds"] = int(meta["llm_summary_rounds"]) + 1
            msgs = []
            if int(meta["llm_summary_rounds"]) >= 4:
                break

    block = hard_truncate_chat_block(_format_turns(summary, msgs))
    meta["tokens_estimated_after"] = rough_token_estimate(block)
    meta["summarization_ms"] = summarize_ms
    meta["chat_prep_total_ms"] = int((time.perf_counter() - t0) * 1000)
    return block, summary, msgs, meta


async def update_explorer_chat_history_summary(
    *,
    rolling_summary: str,
    question: str,
    context_questions: list[str],
    answer: str,
    llm: LLMProvider,
) -> tuple[str, dict[str, Any]]:
    """Gutenberg-style post-answer summary update.

    Mirrors ``gutenbergApp.get_chat_history_summary``: after answering, fold the
    current question, vector-search strings, answer, and previous summary into one
    rolling summary that the next retrieval-planning request can always use.
    """
    t0 = time.perf_counter()
    previous = rolling_summary.strip()
    q = question.strip()
    ans = answer.strip()
    cq = " - ".join(s.strip() for s in context_questions if s.strip())
    augmented_question = f"{q} ({cq})" if cq else q
    meta: dict[str, Any] = {
        "post_answer_summary_ms": 0,
        "post_answer_summary_used_llm": False,
        "post_answer_summary_model_id": "",
    }

    if isinstance(llm, StubLLMProvider):
        parts = []
        if previous:
            parts.append(previous)
        if augmented_question:
            parts.append(f"Q: {augmented_question}")
        if ans:
            parts.append(f"A: {ans}")
        out = "\n".join(parts).strip()
        if len(out) > CHAT_MAX_SUMMARY_CHARS:
            out = out[-CHAT_MAX_SUMMARY_CHARS:]
        meta["post_answer_summary_ms"] = int((time.perf_counter() - t0) * 1000)
        return out, meta

    prompt = (
        "Bitte fasse den bisherigen Chatverlauf mit Anfragen und Antworten "
        "stichpunktartig als Protokoll zusammen, damit diese Zusammenfassung bei "
        "Folgefragen als Kontext für die Vektorsuche verwendet werden kann. Die "
        "neue Zusammenfassung soll sowohl die bisherige Zusammenfassung als auch "
        "die neu hinzugekommene Anfrage und Antwort enthalten. Maximal 1500 "
        "Zeichen.\n\n"
        "Es wurde zuletzt folgende Anfrage gestellt:\n"
        f"{augmented_question}\n\n"
        "Du hast auf diese Anfrage folgende Antwort geliefert:\n"
        f"{ans if ans else '(empty)'}\n\n"
        "Die bisherige Zusammenfassung des Chatverlaufs lautet:\n"
        f"{previous if previous else '(none)'}"
    )
    try:
        res = await llm.complete(
            prompt,
            system=_HISTORY_SUMMARY_SYSTEM,
            max_output_tokens=800,
            temperature=0.0,
        )
        out = res.text.strip()
        if not out:
            out = previous
        meta["post_answer_summary_used_llm"] = True
        meta["post_answer_summary_model_id"] = (res.model_id or "").strip() or llm.model_id
    except Exception:
        parts = [p for p in (previous, f"Q: {augmented_question}", f"A: {ans}") if p]
        out = "\n".join(parts).strip()
    if len(out) > CHAT_MAX_SUMMARY_CHARS:
        out = out[-CHAT_MAX_SUMMARY_CHARS:]
    meta["post_answer_summary_ms"] = int((time.perf_counter() - t0) * 1000)
    return out, meta
