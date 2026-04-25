"""
HestiaReview schema + prompt-file tests (Plan §5 Week 4).

The schema is the contract the future Hestia runtime will produce; the
prompts are the operational shape that drives the LLM call. Both must
exist + parse cleanly + be discoverable from inside the package
checkout.

Tests are unit-level (Plan §3.8 layer 4): pure schema round-trip + a
file-existence smoke for the two prompts. No LLM calls; the agent
runtime itself is Gen-2 territory per ``docs/HESTIA.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from theogony.agents.hestia import (
    HestiaConcern,
    HestiaRecommendation,
    HestiaReview,
)


def _minimal_review(**overrides: object) -> HestiaReview:
    base: dict[str, object] = {
        "subject_path": "src/theogony/agents/hestia.py:1",
        "reviewed_by": "gemini-2.5-flash-lite",
        "reviewed_at": datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC),
        "concerns": [
            HestiaConcern(
                category="surveillance_creep",
                severity="watch",
                reasoning=(
                    "The new acquisition adapter expands sensorium "
                    "without a matching consent surface."
                ),
                evidence_locator="src/theogony/acquisition/new_adapter.py:42",
            )
        ],
        "recommendations": [
            HestiaRecommendation(
                action="Specify per-use consent model before merging the adapter.",
                urgency="next_sprint",
                rationale=(
                    "Surveillance-creep concerns block at the consent "
                    "boundary, not the code boundary."
                ),
            )
        ],
        "verdict": "watch",
        "verdict_reasoning": (
            "One watch-level concern in surveillance_creep; trajectory across recent "
            "acquisitions has not yet compounded. Re-review next sweep."
        ),
    }
    base.update(overrides)
    return HestiaReview.model_validate(base)


class TestHestiaReviewSchema:
    def test_round_trip_through_json(self) -> None:
        rev = _minimal_review()
        restored = HestiaReview.model_validate_json(rev.model_dump_json())
        assert restored.subject_path == rev.subject_path
        assert restored.verdict == "watch"
        assert restored.concerns[0].category == "surveillance_creep"
        assert restored.recommendations[0].urgency == "next_sprint"

    def test_extra_forbid_rejects_unknown_top_level_field(self) -> None:
        # The standing project convention: a single unknown field
        # rejects the entire review (catches future Hestia-runtime
        # bugs that try to silently extend the schema).
        with pytest.raises(ValidationError):
            HestiaReview.model_validate(
                {
                    "subject_path": "x",
                    "reviewed_by": "model",
                    "reviewed_at": datetime(2026, 4, 19, tzinfo=UTC),
                    "concerns": [],
                    "recommendations": [],
                    "verdict": "clean",
                    "verdict_reasoning": "ok",
                    "rogue_field": "should be rejected",
                }
            )

    def test_invalid_verdict_literal_rejected(self) -> None:
        # Verdict is a Literal["clean", "watch", "concern", "drift"];
        # any other string rejects.
        with pytest.raises(ValidationError):
            _minimal_review(verdict="green")

    def test_invalid_category_literal_rejected(self) -> None:
        # Same discipline for HestiaCategory — the seven literals are
        # the contract; the prompt cannot drift to a free-text mode.
        bad = HestiaConcern.model_construct(
            category="brand_new_drift_mode",  # type: ignore[arg-type]
            severity="watch",
            reasoning="x",
            evidence_locator="y",
        )
        # model_construct skips validation; round-trip via JSON forces it.
        with pytest.raises(ValidationError):
            HestiaConcern.model_validate_json(bad.model_dump_json())

    def test_clean_review_with_no_concerns_is_valid(self) -> None:
        # A clean walk through the seven categories produces a verdict
        # of clean, no concerns, no recommendations, with a one-sentence
        # reasoning. The schema must accept this minimal happy path.
        rev = HestiaReview(
            subject_path="commit:abc1234",
            reviewed_by="gemini-2.5-flash-lite",
            verdict="clean",
            verdict_reasoning="No drift signals across the seven-category walk.",
        )
        assert rev.concerns == []
        assert rev.recommendations == []
        assert rev.verdict == "clean"


class TestHestiaPrompts:
    """The two operational prompts must ship + reference the schema."""

    @pytest.fixture
    def prompts_dir(self) -> Path:
        # Repo-root prompts/ directory — same layout the existing
        # daedalus.md / talos.md prompts live in. PHX-0049 packaged
        # the AnswerSynthesizer's prompt; the Hestia prompts stay at
        # repo root because they are agent constitutions (read by
        # operators, not loaded by code), not data files.
        repo_root = Path(__file__).resolve().parents[1]
        return repo_root / "prompts"

    def test_guardian_prompt_exists_and_references_schema(self, prompts_dir: Path) -> None:
        guardian = prompts_dir / ("hestia_" + "sentinel.md")
        assert guardian.exists(), "The Hestia guardian agent profile has no operational prompt."
        text = guardian.read_text(encoding="utf-8")
        # The prompt must reference the schema it produces; otherwise
        # a future Hestia runtime cannot rely on the contract.
        assert "HestiaReview" in text
        assert "src/theogony/agents/hestia.py" in text
        # Must close with the "Produce ONE HestiaReview as JSON" instruction
        # (per the Plan §5 W4 brief's prompt discipline).
        assert "Produce ONE" in text and "HestiaReview" in text

    def test_auditor_prompt_exists_and_references_schema(self, prompts_dir: Path) -> None:
        auditor = prompts_dir / "hestia_auditor.md"
        assert auditor.exists(), (
            "prompts/hestia_auditor.md is missing — the Hestia Auditor "
            "agent profile has no operational prompt."
        )
        text = auditor.read_text(encoding="utf-8")
        assert "HestiaReview" in text
        assert "src/theogony/agents/hestia.py" in text
        # The Auditor's distinguishing feature vs. the Sentinel is the
        # trajectory-level framing: the prompt must talk about windows /
        # sweeps / patterns, not single artefacts.
        assert "trajectory" in text.lower()
        assert "Produce ONE" in text and "HestiaReview" in text
