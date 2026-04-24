"""
Argus v0.1 — first autonomous acquisition agent for the Living Demo (W7-B, W11).

Consumes a :class:`~theogony.curiosity.trigger.CuriosityTrigger`, optionally
runs the W11 planner → executor → evaluator pipeline, then acquires and
ingests approved sources. When ``use_research_planner`` is false, falls back
to the W7-B single-source Gutenberg path.
"""

from __future__ import annotations

import math
import re
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from theogony.acquisition.base import AcquisitionAdapter, SourceCandidate
from theogony.acquisition.web_fetch import ContentExtractionFailedError, RobotsDisallowedError
from theogony.agents.argus_ingest_runner import IngestRunner
from theogony.agents.hestia_lite import (
    HestiaApproval,
    HestiaApprovalStatus,
    HestiaLiteApproval,
)
from theogony.agents.hestia_sentinel import HestiaReview, HestiaSentinel
from theogony.agents.research_evaluator import Evaluator, EvaluatorCandidate, EvaluatorDecision
from theogony.agents.research_planner import PlannerContext, ResearchPlanner
from theogony.config.settings import ArgusSettings
from theogony.curiosity.research_executor import ResearchExecutor
from theogony.curiosity.run_report import AcquisitionDecision
from theogony.curiosity.trigger import CuriosityTrigger, ResearchStep, ResearchStepKind
from theogony.reporting.models import QueryRunReport

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
    """Terminal classification for one ``ArgusAgent.process`` call (W7-B Knob 1 + W11)."""

    APPROVED_AND_INGESTED = "approved_and_ingested"
    APPROVED_INGEST_FAILED = "approved_ingest_failed"
    REJECTED_BY_HESTIA = "rejected_by_hestia"
    NO_CANDIDATES = "no_candidates"
    NO_CANDIDATE_ABOVE_THRESHOLD = "no_candidate_above_threshold"
    UNSUPPORTED_SOURCE_TYPE = "unsupported_source_type"
    BUDGET_EXCEEDED = "budget_exceeded"
    DRY_RUN = "dry_run"
    NO_PLANNED_STEPS = "no_planned_steps"
    NO_CANDIDATE_SELECTED = "no_candidate_selected"
    ALL_REJECTED_BY_HESTIA = "all_rejected_by_hestia"
    INGEST_FAILED = "ingest_failed"


class ArgusResult(BaseModel):
    """Full outcome of one :meth:`ArgusAgent.process` call."""

    model_config = ConfigDict(extra="forbid")

    outcome: ArgusOutcome
    decision: AcquisitionDecision
    bytes_acquired: int = Field(default=0, ge=0)
    reason: str = ""
    updated_trigger: CuriosityTrigger | None = None
    evaluator_decision: EvaluatorDecision | None = None


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


def _planner_context_from_trigger(
    trigger: CuriosityTrigger,
    query_report: QueryRunReport | None,
) -> PlannerContext:
    answer_text: str | None = None
    if query_report is not None:
        parts = [f"query_verdict={query_report.verdict}", query_report.verdict_reasoning.strip()]
        answer_text = "\n".join(p for p in parts if p) or None
    return PlannerContext(
        origin_query=trigger.origin_query,
        answer_text_or_none=answer_text,
        answer_verdict=trigger.answer_verdict,
        cited_node_count=trigger.cited_node_count,
        gap_class=trigger.gap_class,
        region_descriptor=trigger.region_descriptor,
    )


def _source_from_evaluator_row(ec: EvaluatorCandidate) -> SourceCandidate:
    raw = ec.metadata.get("_source_candidate")
    if not isinstance(raw, dict):
        raise ValueError("evaluator candidate missing _source_candidate metadata")
    return SourceCandidate.model_validate(raw)


def _hestia_review_to_approval(hr: HestiaReview) -> HestiaApproval:
    return HestiaApproval(
        status=HestiaApprovalStatus.APPROVED
        if hr.decision == "approved"
        else HestiaApprovalStatus.REJECTED,
        reason=hr.reason,
        rule_fired=hr.rule_fired,
    )


class ArgusAgent:
    """Acquisition loop: W11 planner path or W7-B legacy Gutenberg path."""

    def __init__(
        self,
        *,
        adapter: AcquisitionAdapter | None,
        hestia: HestiaLiteApproval | HestiaSentinel,
        ingest_runner: IngestRunner,
        settings: ArgusSettings,
        use_research_planner: bool = False,
        planner: ResearchPlanner | None = None,
        executor: ResearchExecutor | None = None,
        evaluator: Evaluator | None = None,
        run_reports_dir: Path | None = None,
    ) -> None:
        if use_research_planner:
            if planner is None or executor is None or evaluator is None or run_reports_dir is None:
                raise ValueError(
                    "use_research_planner requires planner, executor, evaluator, run_reports_dir"
                )
        elif adapter is None:
            raise ValueError("legacy Argus path requires adapter")
        self._adapter = adapter
        self._hestia = hestia
        self._ingest_runner = ingest_runner
        self._settings = settings
        self._use_research_planner = use_research_planner
        self._planner = planner
        self._executor = executor
        self._evaluator = evaluator
        self._run_reports_dir = run_reports_dir

    async def _hestia_planner_review(
        self,
        sel: EvaluatorCandidate,
        *,
        ctx: PlannerContext,
        trigger: CuriosityTrigger,
    ) -> HestiaApproval:
        if isinstance(self._hestia, HestiaSentinel):
            hr = await self._hestia.review(candidate=sel, context=ctx)
            return _hestia_review_to_approval(hr)
        source = _source_from_evaluator_row(sel)
        return self._hestia.review(candidate=source, trigger=trigger)

    async def _hestia_legacy_review(
        self,
        *,
        candidate: SourceCandidate,
        trigger: CuriosityTrigger,
    ) -> HestiaApproval:
        if isinstance(self._hestia, HestiaSentinel):
            ctx = _planner_context_from_trigger(trigger, None)
            step = ResearchStep(
                kind=ResearchStepKind.GUTENBERG_SEARCH,
                target=candidate.identifier,
                rationale="legacy_argus_path",
            )
            ec = EvaluatorCandidate(
                source_step=step,
                candidate_label=candidate.title,
                summary="; ".join(candidate.authors) if candidate.authors else "",
                estimated_bytes=int(candidate.metadata.get("estimated_bytes", 0) or 0),
                metadata={"_source_candidate": candidate.model_dump()},
            )
            hr = await self._hestia.review(candidate=ec, context=ctx)
            return _hestia_review_to_approval(hr)
        return self._hestia.review(candidate=candidate, trigger=trigger)

    async def process(self, trigger: CuriosityTrigger, *, dry_run: bool = False) -> ArgusResult:
        """Run the step machine; never raises — failures become ``ArgusResult``."""
        empty = AcquisitionDecision()
        try:
            if self._use_research_planner:
                return await self._process_planner(trigger, dry_run=dry_run, empty=empty)
            return await self._process_legacy(trigger, dry_run=dry_run, empty=empty)
        except Exception as exc:  # pragma: no cover - defensive; unit tests hit happy paths
            return ArgusResult(
                outcome=ArgusOutcome.APPROVED_INGEST_FAILED,
                decision=empty,
                bytes_acquired=0,
                reason=str(exc)[:500],
            )

    async def _process_planner(
        self,
        trigger: CuriosityTrigger,
        *,
        dry_run: bool,
        empty: AcquisitionDecision,
    ) -> ArgusResult:
        assert self._planner is not None
        assert self._executor is not None
        assert self._evaluator is not None
        assert self._run_reports_dir is not None

        qr: QueryRunReport | None = None
        qpath = self._run_reports_dir / "query" / f"{trigger.origin_query_run_id}.json"
        if qpath.is_file():
            qr = QueryRunReport.model_validate_json(qpath.read_text(encoding="utf-8"))

        ctx = _planner_context_from_trigger(trigger, qr)
        plan = await self._planner.plan(ctx)
        trig_after_plan = trigger.model_copy(update={"research_plan": plan})

        if not plan.steps:
            return ArgusResult(
                outcome=ArgusOutcome.NO_PLANNED_STEPS,
                decision=empty,
                reason="planner returned zero steps",
                updated_trigger=trig_after_plan,
            )

        candidates: list[EvaluatorCandidate] = []
        for step in plan.steps:
            candidates.extend(await self._executor.execute_step(step))

        decision = await self._evaluator.evaluate(context=ctx, candidates=candidates)

        if not decision.selected:
            return ArgusResult(
                outcome=ArgusOutcome.NO_CANDIDATE_SELECTED,
                decision=empty,
                reason="evaluator selected zero candidates",
                updated_trigger=trig_after_plan,
                evaluator_decision=decision,
            )

        total_bytes = sum(s.estimated_bytes for s in decision.selected)
        if total_bytes > trigger.budget.max_total_bytes:
            return ArgusResult(
                outcome=ArgusOutcome.BUDGET_EXCEEDED,
                decision=empty,
                reason=f"evaluator selection estimated_bytes={total_bytes} > budget",
                updated_trigger=trig_after_plan,
                evaluator_decision=decision,
            )

        if dry_run:
            return ArgusResult(
                outcome=ArgusOutcome.DRY_RUN,
                decision=empty,
                reason="dry-run: acquire and ingest not executed",
                updated_trigger=trig_after_plan,
                evaluator_decision=decision,
            )

        bytes_total = 0
        last_decision = empty
        any_ingested = False
        any_hestia_rejection = False
        ingest_error: str | None = None

        for sel in decision.selected:
            try:
                source = _source_from_evaluator_row(sel)
            except (TypeError, ValueError) as exc:
                ingest_error = str(exc)[:500]
                break

            approval = await self._hestia_planner_review(sel, ctx=ctx, trigger=trig_after_plan)
            if approval.status != HestiaApprovalStatus.APPROVED:
                any_hestia_rejection = True
                last_decision = _decision_from_candidate(
                    source,
                    hestia_status="rejected",
                    hestia_reason=approval.reason,
                )
                continue

            estimated = source.metadata.get("estimated_bytes")
            if isinstance(estimated, int) and estimated > trigger.budget.max_total_bytes:
                return ArgusResult(
                    outcome=ArgusOutcome.BUDGET_EXCEEDED,
                    decision=_decision_from_candidate(
                        source,
                        hestia_status="approved",
                        hestia_reason=approval.reason,
                    ),
                    reason=f"estimated_bytes={estimated} > budget {trigger.budget.max_total_bytes}",
                    updated_trigger=trig_after_plan,
                    evaluator_decision=decision,
                )

            try:
                raw = await self._executor.acquire_source(source)
            except (RobotsDisallowedError, ContentExtractionFailedError) as exc:
                any_hestia_rejection = True
                last_decision = _decision_from_candidate(
                    source,
                    hestia_status="rejected",
                    hestia_reason=str(exc)[:500],
                )
                continue
            if raw.bytes_acquired > trigger.budget.max_total_bytes:
                return ArgusResult(
                    outcome=ArgusOutcome.BUDGET_EXCEEDED,
                    decision=_decision_from_candidate(
                        source,
                        hestia_status="approved",
                        hestia_reason=approval.reason,
                    ),
                    bytes_acquired=bytes_total + raw.bytes_acquired,
                    reason=(
                        f"acquired {raw.bytes_acquired} B > budget {trigger.budget.max_total_bytes}"
                    ),
                    updated_trigger=trig_after_plan,
                    evaluator_decision=decision,
                )

            try:
                ingest_run_id = await self._ingest_runner.run_from_raw_content(raw)
            except Exception as exc:
                ingest_error = str(exc)[:500]
                last_decision = _decision_from_candidate(
                    source,
                    hestia_status="approved",
                    hestia_reason=approval.reason,
                )
                break

            bytes_total += raw.bytes_acquired
            any_ingested = True
            last_decision = _decision_from_candidate(
                source,
                hestia_status="approved",
                hestia_reason=approval.reason,
                ingest_run_id=ingest_run_id,
            )

        if ingest_error is not None:
            return ArgusResult(
                outcome=ArgusOutcome.INGEST_FAILED,
                decision=last_decision,
                bytes_acquired=bytes_total,
                reason=ingest_error,
                updated_trigger=trig_after_plan,
                evaluator_decision=decision,
            )

        if any_ingested:
            return ArgusResult(
                outcome=ArgusOutcome.APPROVED_AND_INGESTED,
                decision=last_decision,
                bytes_acquired=bytes_total,
                reason="ingest completed",
                updated_trigger=trig_after_plan,
                evaluator_decision=decision,
            )

        if any_hestia_rejection:
            return ArgusResult(
                outcome=ArgusOutcome.ALL_REJECTED_BY_HESTIA,
                decision=last_decision,
                bytes_acquired=0,
                reason="all selected candidates rejected by Hestia",
                updated_trigger=trig_after_plan,
                evaluator_decision=decision,
            )

        return ArgusResult(
            outcome=ArgusOutcome.NO_CANDIDATE_SELECTED,
            decision=empty,
            reason="no successful acquisition",
            updated_trigger=trig_after_plan,
            evaluator_decision=decision,
        )

    async def _process_legacy(
        self,
        trigger: CuriosityTrigger,
        *,
        dry_run: bool,
        empty: AcquisitionDecision,
    ) -> ArgusResult:
        assert self._adapter is not None
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

        approval = await self._hestia_legacy_review(candidate=best, trigger=trigger)
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
