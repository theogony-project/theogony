"""
CuriosityRunReport — one end-to-end curiosity loop run (PHX-0037, W7-A).

The brief (Knob 6) asks for ``AcquisitionDecision`` and
``CuriosityRunReport`` next to the existing run-report family in
``reporting/models.py``. That placement creates a circular import,
because :class:`CuriosityRunReport` references
:class:`~theogony.curiosity.trigger.CuriosityTrigger` while
:class:`~theogony.curiosity.trigger.CuriosityTrigger` already imports
:class:`~theogony.reporting.models.RegionDescriptor` and
:func:`~theogony.reporting.models.new_run_id`.

We resolve that cycle by defining the report in this sibling module.
The on-disk JSON shape, the ``report_type="curiosity"`` discriminator,
the writer registration, and the run-reports directory layout are
identical to what the brief specifies — only the file path differs.
The deviation is documented in the W7-A PR body.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.research_evaluator import EvaluatorDecision
from theogony.curiosity.trigger import CuriosityTrigger
from theogony.reporting.models import RunReportBase


class AcquisitionDecision(BaseModel):
    """Argus + HestiaLite outcome (W7-B will populate; W7-A leaves None)."""

    model_config = ConfigDict(extra="forbid")

    candidate_source_type: str | None = None
    candidate_identifier: str | None = None
    candidate_title: str | None = None
    hestia_status: Literal["not_evaluated", "approved", "rejected"] = "not_evaluated"
    hestia_reason: str = ""
    ingest_run_id: str | None = None


class CuriosityRunReport(RunReportBase):
    """One end-to-end curiosity loop run (PHX-0037)."""

    report_type: Literal["curiosity"] = "curiosity"
    trigger: CuriosityTrigger
    decision: AcquisitionDecision = Field(default_factory=AcquisitionDecision)
    bytes_acquired: int = Field(default=0, ge=0)
    evaluator_decision: EvaluatorDecision | None = None


__all__ = ["AcquisitionDecision", "CuriosityRunReport"]
