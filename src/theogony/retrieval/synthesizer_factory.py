"""Factory for the query-path answer synthesizer (PHX-0070)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from theogony.agents.llm import OfflineLLMProvider
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
    # The instance decides, not the setting: a provider that is configured but
    # has no key arrives here as an OfflineLLMProvider (`build_llm_or_offline`,
    # PHX-1111). Not any stub — a scripted StubLLMProvider is how tests drive the
    # real synthesizer.
    if settings.llm.provider == "stub" or isinstance(llm, OfflineLLMProvider):
        return OfflineAnswerSynthesizer(top_n=settings.llm.offline_top_n_citations)
    return AnswerSynthesizer(llm, audit_log=audit_log)
