"""Factory for the query-path answer synthesizer (PHX-0070)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from theogony.config.settings import Settings
from theogony.retrieval.synthesize import (
    AnswerSynthesizer,
    AnswerSynthesizerLike,
    OfflineAnswerSynthesizer,
)

if TYPE_CHECKING:
    from theogony.agents.llm import LLMProvider
    from theogony.extraction.audit import ExtractionAuditLog


def build_synthesizer(
    settings: Settings,
    llm: LLMProvider,
    *,
    audit_log: ExtractionAuditLog | None = None,
) -> AnswerSynthesizerLike:
    """Pick the right synthesizer for the active LLM provider.

    Stub provider → :class:`~theogony.retrieval.synthesize.OfflineAnswerSynthesizer`
    (deterministic, no LLM call). Real providers →
    :class:`~theogony.retrieval.synthesize.AnswerSynthesizer` (LLM prose + citations).
    """
    if settings.llm.provider == "stub":
        return OfflineAnswerSynthesizer(top_n=settings.llm.offline_top_n_citations)
    return AnswerSynthesizer(llm, audit_log=audit_log)
