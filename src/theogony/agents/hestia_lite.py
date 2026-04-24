"""
HestiaLite — deterministic governance for Argus acquisition (W7-B, PHX-0037).

No LLM, no network, no trust in upstream callers: every rule is a
straight predicate evaluated in a fixed order. The first match wins.

The blocked-keyword list is a **module constant** (W7-B brief Knob 3):
operators cannot soften it via settings — only a deliberate code
change can widen or narrow the floor.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from theogony.acquisition.base import SourceCandidate
from theogony.config.settings import HestiaLiteSettings
from theogony.curiosity.trigger import CuriosityTrigger

# W7-B brief: locked floor — not loaded from disk, not env-tunable.
BLOCKED_KEYWORDS: tuple[str, ...] = (
    "minor",
    "child abuse",
    "child pornography",
    "csam",
    "self-harm instructions",
    "weapons manufacturing",
    "explosive synthesis",
    "bioweapon",
    "chemical weapon",
)


class HestiaApprovalStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class HestiaApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HestiaApprovalStatus
    reason: str
    rule_fired: str | None = None


class HestiaLiteApproval:
    """Deterministic allowlist + blocklist + copyright gate (Living Demo W7-B)."""

    def __init__(self, settings: HestiaLiteSettings) -> None:
        self._settings = settings

    def review(
        self,
        *,
        candidate: SourceCandidate,
        trigger: CuriosityTrigger,
    ) -> HestiaApproval:
        """Evaluate rules in order; first match decides (W7-B Knob 3)."""
        allowlist: tuple[str, ...] = tuple(self._settings.allowlist)
        if candidate.source_type not in allowlist:
            return HestiaApproval(
                status=HestiaApprovalStatus.REJECTED,
                reason=f"source_type {candidate.source_type!r} not in allowlist {list(allowlist)}",
                rule_fired="source_type_not_allowlisted",
            )

        title_lower = candidate.title.casefold()
        query_lower = trigger.proposed_acquisition_spec.search_query.casefold()
        for kw in BLOCKED_KEYWORDS:
            k = kw.casefold()
            if k in title_lower or k in query_lower:
                return HestiaApproval(
                    status=HestiaApprovalStatus.REJECTED,
                    reason=f"blocked keyword matched: {kw!r}",
                    rule_fired="title_or_search_in_blocklist",
                )

        if candidate.download_url is None:
            return HestiaApproval(
                status=HestiaApprovalStatus.REJECTED,
                reason="download_url is None — cannot acquire safely",
                rule_fired="download_url_missing",
            )

        copyright_flag = candidate.metadata.get("copyright")
        if copyright_flag is True:
            return HestiaApproval(
                status=HestiaApprovalStatus.REJECTED,
                reason="metadata.copyright is True — not public-domain per Gutendex",
                rule_fired="license_unknown",
            )

        return HestiaApproval(
            status=HestiaApprovalStatus.APPROVED,
            reason="no Hestia rule blocks; gutenberg public-domain by source policy",
            rule_fired="default_approve",
        )


__all__ = [
    "BLOCKED_KEYWORDS",
    "HestiaApproval",
    "HestiaApprovalStatus",
    "HestiaLiteApproval",
]
