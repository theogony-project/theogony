"""HestiaSentinel — per-candidate safety auditor for research (W12)."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from theogony.acquisition.base import SourceCandidate
from theogony.agents.llm import LLMProvider
from theogony.agents.research_evaluator import EvaluatorCandidate
from theogony.agents.research_planner import PlannerContext
from theogony.config.settings import HestiaSentinelSettings
from theogony.curiosity.trigger import ResearchStepKind

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "hestia_sentinel.md"

HARD_BLOCK_KEYWORDS: tuple[str, ...] = (
    "child sexual abuse material",
    "csam",
    "weapons synthesis",
    "explosive synthesis",
    "bioweapon synthesis",
    "chemical weapon synthesis",
    "self-harm instructions",
)

LOCKED_HOST_BLOCK_LIST: tuple[str, ...] = (
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "linkedin.com",
    "reddit.com",
)

_ALLOWED_STEP_KINDS: frozenset[ResearchStepKind] = frozenset(
    {
        ResearchStepKind.WIKIDATA_LOOKUP,
        ResearchStepKind.GUTENBERG_SEARCH,
        ResearchStepKind.WIKIPEDIA_FETCH,
        ResearchStepKind.WEB_FETCH,
    }
)


class SentinelDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    UNSURE_ESCALATED = "unsure_escalated"


class HestiaReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    reason: str
    rule_fired: str
    llm_called: bool = False
    llm_cost_eur: float = Field(default=0.0, ge=0.0)


class _LLMFallbackOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    reason: str = ""


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _host_matches_blocklist(host: str) -> bool:
    h = host.casefold().strip(".")
    for domain in LOCKED_HOST_BLOCK_LIST:
        d = domain.casefold()
        if h == d or h.endswith("." + d):
            return True
    return False


def _source_from_evaluator(ec: EvaluatorCandidate) -> SourceCandidate | None:
    raw = ec.metadata.get("_source_candidate")
    if not isinstance(raw, dict):
        return None
    return SourceCandidate.model_validate(raw)


class HestiaSentinel:
    """Deterministic rules plus optional LLM fallback for open-web candidates."""

    def __init__(self, *, llm: LLMProvider, settings: HestiaSentinelSettings) -> None:
        self._llm = llm
        self._settings = settings
        self._system = _load_system_prompt()

    async def review(
        self, *, candidate: EvaluatorCandidate, context: PlannerContext
    ) -> HestiaReview:
        kind = candidate.source_step.kind
        if kind not in _ALLOWED_STEP_KINDS:
            return HestiaReview(
                decision="rejected",
                reason=f"unsupported research step kind: {kind!r}",
                rule_fired="source_type_unknown",
            )

        sc = _source_from_evaluator(candidate)
        if sc is None:
            return HestiaReview(
                decision="rejected",
                reason="missing _source_candidate on evaluator row",
                rule_fired="source_type_unknown",
            )

        if sc.source_type == "web":
            url = sc.url or sc.download_url
            if not url or not str(url).lower().startswith("https://"):
                return HestiaReview(
                    decision="rejected",
                    reason="web candidate requires https URL",
                    rule_fired="url_scheme_or_host_invalid",
                )
            parsed = urlparse(str(url))
            host = (parsed.hostname or "").casefold()
            if not host:
                return HestiaReview(
                    decision="rejected",
                    reason="invalid host",
                    rule_fired="url_scheme_or_host_invalid",
                )
            try:
                import ipaddress

                ipaddress.ip_address(host.split("%", 1)[0])
                return HestiaReview(
                    decision="rejected",
                    reason="IP-literal hosts are not allowed for web fetch",
                    rule_fired="url_scheme_or_host_invalid",
                )
            except ValueError:
                pass
            if "." not in host:
                return HestiaReview(
                    decision="rejected",
                    reason="invalid host",
                    rule_fired="url_scheme_or_host_invalid",
                )
            if _host_matches_blocklist(host):
                return HestiaReview(
                    decision="rejected",
                    reason=f"host blocked by policy: {host!r}",
                    rule_fired="url_scheme_or_host_invalid",
                )

        if candidate.estimated_bytes > self._settings.max_candidate_bytes:
            return HestiaReview(
                decision="rejected",
                reason=(
                    f"estimated_bytes={candidate.estimated_bytes} > "
                    f"max_candidate_bytes={self._settings.max_candidate_bytes}"
                ),
                rule_fired="content_size_excessive",
            )

        label_l = candidate.candidate_label.casefold()
        summary_l = candidate.summary.casefold()
        for kw in HARD_BLOCK_KEYWORDS:
            k = kw.casefold()
            if k in label_l or k in summary_l:
                return HestiaReview(
                    decision="rejected",
                    reason=f"hard block keyword matched: {kw!r}",
                    rule_fired="hard_block_keywords_in_label_or_summary",
                )

        if sc.source_type in ("gutenberg", "wikidata", "wikipedia"):
            return HestiaReview(
                decision="approved",
                reason=f"default approve governed source_type={sc.source_type!r}",
                rule_fired="gutenberg_or_wikidata_or_wikipedia_default_approve",
            )

        if sc.source_type == "web":
            if not self._settings.llm_fallback_enabled:
                return HestiaReview(
                    decision="rejected",
                    reason="LLM fallback disabled for web candidates",
                    rule_fired="web_no_obvious_block_then_llm_fallback",
                )
            return await self._llm_fallback_web(candidate=candidate, context=context, sc=sc)

        return HestiaReview(
            decision="rejected",
            reason=f"unsupported source_type={sc.source_type!r}",
            rule_fired="source_type_unknown",
        )

    async def _llm_fallback_web(
        self,
        *,
        candidate: EvaluatorCandidate,
        context: PlannerContext,
        sc: SourceCandidate,
    ) -> HestiaReview:
        user_payload: dict[str, Any] = {
            "origin_query": context.origin_query,
            "gap_class": context.gap_class.value,
            "candidate_label": candidate.candidate_label,
            "candidate_summary": candidate.summary,
            "url": sc.url or sc.download_url,
            "source_title": sc.title,
        }
        user_prompt = json.dumps(user_payload, ensure_ascii=False)
        schema = _LLMFallbackOutput.model_json_schema()
        try:
            import asyncio

            async with asyncio.timeout(3.0):
                result = await self._llm.complete(
                    user_prompt,
                    system=self._system,
                    json_schema=schema,
                    max_output_tokens=min(100, self._settings.llm_fallback_max_total_tokens),
                    temperature=0.0,
                    timeout_s=3.0,
                )
        except Exception:
            return HestiaReview(
                decision="rejected",
                reason="llm_fallback_unavailable",
                rule_fired="llm_fallback_unavailable",
                llm_called=True,
            )
        try:
            parsed = _LLMFallbackOutput.model_validate_json(result.text)
        except Exception:
            return HestiaReview(
                decision="rejected",
                reason="llm_fallback_unparseable",
                rule_fired="llm_fallback_unavailable",
                llm_called=True,
                llm_cost_eur=float(result.cost_eur),
            )
        return HestiaReview(
            decision=parsed.decision,
            reason=parsed.reason or ("approved" if parsed.decision == "approved" else "rejected"),
            rule_fired="llm_fallback",
            llm_called=True,
            llm_cost_eur=float(result.cost_eur),
        )


__all__ = [
    "HARD_BLOCK_KEYWORDS",
    "HestiaReview",
    "HestiaSentinel",
    "LOCKED_HOST_BLOCK_LIST",
    "SentinelDecision",
]
