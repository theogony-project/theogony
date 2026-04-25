"""
HestiaReview — Pydantic schema for the Hestia agent's drift-monitoring output.

Hestia is the Pantheon's Human Flourishing Guardian (``docs/HESTIA.md``).
In Gen 1 this is a **schema-only** deliverable per Plan §1 ("Hestia as
Schema and prompt templates only" + Plan §5 Week 4). No runtime; no
orchestration; no integration with :class:`RunReportWriter`. The
schema exists so the future Hestia runtime (Sentinel + Auditor agent
classes, Gen 2 territory per ``docs/HESTIA.md`` "Generation 2") targets
a stable, reviewed shape from day one.

Future production prompts drive the Hestia drift-monitoring agent classes when
they exist; they require their LLM call to produce one :class:`HestiaReview`
per artefact / sweep.

The literal vocabularies (:data:`HestiaCategory`, :data:`HestiaSeverity`,
:data:`HestiaUrgency`, :data:`HestiaVerdict`) are the contract the
prompts target. ``HestiaCategory`` mirrors the seven drift modes named
in ``docs/HESTIA.md`` ("efficiency becomes the only metric",
"surveillance becomes normalized", etc.). ``HestiaVerdict`` mirrors
:class:`OneirosTickReport.verdict` and :class:`IngestRunReport.verdict`
so consumers (a future Reviewer agent, dashboards, the operator's eye)
see consistent vocabulary across all agent self-reports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Seven drift categories Hestia walks every artefact / sweep through.
#: Lifted from ``docs/HESTIA.md`` "What Hestia Watches" + "Why Hestia
#: Exists". ``other`` is the explicit fall-through so the LLM never
#: has to silently mis-categorise; concerns that don't fit the six
#: named modes still get logged with reasoning.
HestiaCategory = Literal[
    "efficiency_uber_alles",
    "surveillance_creep",
    "managed_contentment",
    "diversity_collapse",
    "control_for_care",
    "expropriation_of_meaning",
    "other",
]

#: Severity ladder for an individual concern. ``info`` = noted but not
#: actionable; ``watch`` = monitor over time; ``concern`` = surface to
#: human reviewer; ``drift`` = matches the verdict's strongest level.
HestiaSeverity = Literal["info", "watch", "concern", "drift"]

#: Urgency ladder for an individual recommendation. Mirrors the
#: cadence Hestia operates on per ``docs/HESTIA.md`` Generation 1 +
#: Generation 2 build path.
HestiaUrgency = Literal["next_review", "next_sprint", "immediate"]

#: Aggregate verdict — the headline a project lead reads first.
#: ``clean`` = no action; ``watch`` = re-review next cycle; ``concern``
#: = needs human attention; ``drift`` = escalation per ``docs/HESTIA.md``
#: "Escalation" section. Mirrors the same vocabulary the
#: :class:`OneirosTickReport` and :class:`IngestRunReport` carry, so
#: agent-self-reports speak with one voice.
HestiaVerdict = Literal["clean", "watch", "concern", "drift"]


class HestiaConcern(BaseModel):
    """One specific drift signal Hestia identified in the reviewed artefact.

    ``evidence_locator`` is the operator-readable reference the
    reviewer can chase: a file:line, a ``run_id`` (resolvable via
    ``theogony reports show``), a prompt name, a commit SHA, etc.
    The string is intentionally untyped — what counts as a locator
    varies per artefact kind.
    """

    model_config = ConfigDict(extra="forbid")

    category: HestiaCategory
    severity: HestiaSeverity
    reasoning: str = Field(min_length=1)
    evidence_locator: str = Field(
        min_length=1,
        description="file:line, run_id, prompt name, commit SHA, etc.",
    )


class HestiaRecommendation(BaseModel):
    """One concrete action Hestia recommends in response to the concerns.

    Hestia is not a veto (per ``docs/HESTIA.md`` "What Hestia Is Not");
    these are advisory. ``urgency`` chooses the operator's response
    cadence; ``rationale`` is the one-paragraph "why this action" the
    next reviewer reads to decide whether to act on it.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    urgency: HestiaUrgency
    rationale: str = Field(min_length=1)


class HestiaReview(BaseModel):
    """One Hestia review of a single artefact (sentinel) or sweep (auditor).

    The schema is intentionally narrow per Plan §1: Hestia is a
    *counter-weight*, not a veto. Concerns + recommendations + a
    verdict; no enforcement, no patches. The verdict is the executive
    summary; the concerns + recommendations are the audit trail.

    ``subject_path`` identifies what Hestia reviewed. For the Sentinel
    profile this is typically a ``file:line`` or a ``commit:<sha>``;
    for the Auditor profile it is typically ``sweep:<YYYY-MM-DD>``
    or ``window:<start>..<end>``. The string is the operator's lookup
    key for "what was Hestia looking at when she said this".

    ``reviewed_by`` carries the LLM ``model_id`` (e.g.
    ``"gemini-2.5-flash-lite"``) so the Phoenix process / Reviewer
    agent (PHX-0035) can correlate Hestia opinions against model
    revisions over time — the same discipline ``KnowledgeNode``
    applies to ``embedding_model_id``.
    """

    model_config = ConfigDict(extra="forbid")

    subject_path: str = Field(
        min_length=1,
        description="file path, run_id, commit SHA, or 'sweep:<date>'",
    )
    reviewed_by: str = Field(
        min_length=1,
        description="LLM model id (e.g. 'gemini-2.5-flash-lite')",
    )
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    concerns: list[HestiaConcern] = Field(default_factory=list)
    recommendations: list[HestiaRecommendation] = Field(default_factory=list)
    verdict: HestiaVerdict
    verdict_reasoning: str = Field(min_length=1)


__all__ = [
    "HestiaCategory",
    "HestiaConcern",
    "HestiaRecommendation",
    "HestiaReview",
    "HestiaSeverity",
    "HestiaUrgency",
    "HestiaVerdict",
]
