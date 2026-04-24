"""
Argus v0.1 — first autonomous acquisition agent for the Living Demo (W7-B).

Consumes a :class:`~theogony.curiosity.trigger.CuriosityTrigger`, searches
Project Gutenberg via an :class:`~theogony.acquisition.base.AcquisitionAdapter`,
scores candidates deterministically, routes the winner through
:class:`~theogony.agents.hestia_lite.HestiaLiteApproval`, then acquires and
hands bytes to an :class:`~theogony.agents.argus_ingest_runner.IngestRunner`.

Sequential, narrow, and honest about failure — no background fan-out, no
retry layer on top of the adapter's own retries, no extra Pantheon agents.
"""

from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from theogony.acquisition.base import AcquisitionAdapter, SourceCandidate
from theogony.agents.argus_ingest_runner import IngestRunner
from theogony.agents.hestia_lite import HestiaApprovalStatus, HestiaLiteApproval
from theogony.config.settings import ArgusSettings
from theogony.curiosity.run_report import AcquisitionDecision
from theogony.curiosity.trigger import CuriosityTrigger

# --- Knob 2: fixed EN+DE stopword list (30 tokens; no NLTK / spaCy) ---
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "have",
        "has",
        "had",
        "der",
        "die",
        "das",
        "und",
        "von",
        "zu",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", flags=re.IGNORECASE)


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def score_candidate(candidate: SourceCandidate, trigger: CuriosityTrigger) -> float:
    """Return a deterministic score in ``[0.0, 1.0]``; higher is better (W7-B Knob 2)."""
    query_terms = _tokenize(trigger.proposed_acquisition_spec.search_query)
    title_terms = _tokenize(candidate.title)
    author_terms = _tokenize(" ".join(candidate.authors))

    title_overlap = _jaccard(query_terms, title_terms)
    author_overlap = _jaccard(query_terms, author_terms)

    lang_bonus = 0.1 if "en" in candidate.languages else 0.0

    dl = candidate.metadata.get("download_count")
    pop = 0.0
    if isinstance(dl, int) and dl > 0:
        pop = min(1.0, math.log10(dl + 1) / 5.0)

    return min(1.0, 0.6 * title_overlap + 0.2 * author_overlap + lang_bonus + 0.1 * pop)


class ArgusOutcome(StrEnum):
    """Terminal classification for one ``ArgusAgent.process`` call (W7-B Knob 1)."""

    APPROVED_AND_INGESTED = "approved_and_ingested"
    APPROVED_INGEST_FAILED = "approved_ingest_failed"
    REJECTED_BY_HESTIA = "rejected_by_hestia"
    NO_CANDIDATES = "no_candidates"
    NO_CANDIDATE_ABOVE_THRESHOLD = "no_candidate_above_threshold"
    UNSUPPORTED_SOURCE_TYPE = "unsupported_source_type"
    BUDGET_EXCEEDED = "budget_exceeded"
    # Not in the brief's original seven-outcome table — required so ``--dry-run``
    # can terminate honestly without fabricating ingest state (see W7-B PR body).
    DRY_RUN = "dry_run"


class ArgusResult(BaseModel):
    """Full outcome of one :meth:`ArgusAgent.process` call."""

    model_config = ConfigDict(extra="forbid")

    outcome: ArgusOutcome
    decision: AcquisitionDecision
    bytes_acquired: int = Field(default=0, ge=0)
    reason: str = ""


@runtime_checkable
class ArgusProcessable(Protocol):
    """Structural type for anything that can run the Argus step machine."""

    async def process(self, trigger: CuriosityTrigger, *, dry_run: bool = False) -> ArgusResult: ...


def _decision_from_candidate(
    candidate: SourceCandidate,
    *,
    hestia_status: Literal["approved", "rejected"],
    hestia_reason: str,
    ingest_run_id: str | None = None,
) -> AcquisitionDecision:
    return AcquisitionDecision(
        candidate_source_type=candidate.source_type,
        candidate_identifier=candidate.identifier,
        candidate_title=candidate.title,
        hestia_status=hestia_status,
        hestia_reason=hestia_reason,
        ingest_run_id=ingest_run_id,
    )


class ArgusAgent:
    """Gutenberg-only acquisition loop behind HestiaLite (W7-B)."""

    def __init__(
        self,
        *,
        adapter: AcquisitionAdapter,
        hestia: HestiaLiteApproval,
        ingest_runner: IngestRunner,
        settings: ArgusSettings,
    ) -> None:
        self._adapter = adapter
        self._hestia = hestia
        self._ingest_runner = ingest_runner
        self._settings = settings

    async def process(self, trigger: CuriosityTrigger, *, dry_run: bool = False) -> ArgusResult:
        """Run the Knob-1 step machine; never raises — failures become ``ArgusResult``."""
        empty = AcquisitionDecision()
        try:
            return await self._process_inner(trigger, dry_run=dry_run, empty=empty)
        except Exception as exc:  # pragma: no cover - defensive; unit tests hit happy paths
            return ArgusResult(
                outcome=ArgusOutcome.APPROVED_INGEST_FAILED,
                decision=empty,
                bytes_acquired=0,
                reason=str(exc)[:500],
            )

    async def _process_inner(
        self,
        trigger: CuriosityTrigger,
        *,
        dry_run: bool,
        empty: AcquisitionDecision,
    ) -> ArgusResult:
        spec = trigger.proposed_acquisition_spec
        if str(spec.source_type) != "gutenberg":
            return ArgusResult(
                outcome=ArgusOutcome.UNSUPPORTED_SOURCE_TYPE,
                decision=empty,
                reason=f"unsupported source_type={spec.source_type!r}",
            )

        candidates = await self._adapter.search(
            spec.search_query, limit=self._settings.search_limit
        )
        if len(candidates) == 0:
            return ArgusResult(
                outcome=ArgusOutcome.NO_CANDIDATES,
                decision=empty,
                reason="adapter.search returned zero candidates",
            )

        scored = sorted(
            ((score_candidate(c, trigger), c) for c in candidates),
            key=lambda t: t[0],
            reverse=True,
        )
        best_score, best = scored[0]
        if best_score < self._settings.min_candidate_score:
            thr = self._settings.min_candidate_score
            return ArgusResult(
                outcome=ArgusOutcome.NO_CANDIDATE_ABOVE_THRESHOLD,
                decision=empty,
                reason=f"best score {best_score:.4f} < min_candidate_score {thr}",
            )

        approval = self._hestia.review(candidate=best, trigger=trigger)
        if approval.status != HestiaApprovalStatus.APPROVED:
            return ArgusResult(
                outcome=ArgusOutcome.REJECTED_BY_HESTIA,
                decision=_decision_from_candidate(
                    best,
                    hestia_status="rejected",
                    hestia_reason=approval.reason,
                ),
                reason=approval.reason,
            )

        estimated = best.metadata.get("estimated_bytes")
        if isinstance(estimated, int) and estimated > trigger.budget.max_total_bytes:
            return ArgusResult(
                outcome=ArgusOutcome.BUDGET_EXCEEDED,
                decision=_decision_from_candidate(
                    best,
                    hestia_status="approved",
                    hestia_reason=approval.reason,
                ),
                reason=f"estimated_bytes={estimated} > budget {trigger.budget.max_total_bytes}",
            )

        if dry_run:
            return ArgusResult(
                outcome=ArgusOutcome.DRY_RUN,
                decision=_decision_from_candidate(
                    best,
                    hestia_status="approved",
                    hestia_reason=approval.reason,
                ),
                reason="dry-run: acquire and ingest not executed",
            )

        raw = await self._adapter.acquire(best)
        if raw.bytes_acquired > trigger.budget.max_total_bytes:
            return ArgusResult(
                outcome=ArgusOutcome.BUDGET_EXCEEDED,
                decision=_decision_from_candidate(
                    best,
                    hestia_status="approved",
                    hestia_reason=approval.reason,
                ),
                bytes_acquired=raw.bytes_acquired,
                reason=f"acquired {raw.bytes_acquired} B > budget {trigger.budget.max_total_bytes}",
            )

        try:
            ingest_run_id = await self._ingest_runner.run_from_raw_content(raw)
        except Exception as exc:
            return ArgusResult(
                outcome=ArgusOutcome.APPROVED_INGEST_FAILED,
                decision=_decision_from_candidate(
                    best,
                    hestia_status="approved",
                    hestia_reason=approval.reason,
                ),
                bytes_acquired=raw.bytes_acquired,
                reason=str(exc)[:500],
            )

        return ArgusResult(
            outcome=ArgusOutcome.APPROVED_AND_INGESTED,
            decision=_decision_from_candidate(
                best,
                hestia_status="approved",
                hestia_reason=approval.reason,
                ingest_run_id=ingest_run_id,
            ),
            bytes_acquired=raw.bytes_acquired,
            reason="ingest completed",
        )


__all__ = [
    "ArgusAgent",
    "ArgusOutcome",
    "ArgusProcessable",
    "ArgusResult",
    "score_candidate",
]
