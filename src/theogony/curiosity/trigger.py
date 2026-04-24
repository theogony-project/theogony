"""
CuriosityTrigger — typed intent to grow the chronicle (PHX-0037 slice 1, W7-A).

A trigger is the **decision-shaped object** that turns a passive
``StubVerdict`` + ``RegionDescriptor`` observation into an auditable
intent for downstream acquisition agents (W7-B). The bridge that emits
triggers lives in :mod:`theogony.curiosity.growth_bridge`; this module
owns only the schema.

Schema discipline (W7-A brief, Knob 1):

- Every model uses ``model_config = ConfigDict(extra="forbid")`` so a
  silent typo in a producer (or a future schema drift) becomes a loud
  validation error rather than a discarded field.
- ``AcquisitionSpec.source_type`` is a ``Literal["gutenberg"]`` in v1.
  The web is structurally out of scope; widening the Literal is a
  future PHX, not an early-binding flexibility hook.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.reporting.models import RegionDescriptor, new_run_id


class GapClass(StrEnum):
    """The shape of the gap that motivated the trigger (W7-A Knob 2)."""

    ENTITY_UNKNOWN = "entity_unknown"
    REGION_THIN = "region_thin"
    EDGE_DENSITY_LOW = "edge_density_low"


class TriggerBudget(BaseModel):
    """Hard ceilings the downstream acquisition agent must honour."""

    model_config = ConfigDict(extra="forbid")

    max_sources_to_fetch: int = Field(default=1, ge=1, le=5)
    max_total_bytes: int = Field(default=2 * 1024 * 1024, ge=1)  # 2 MiB
    max_llm_eur: float = Field(default=0.50, ge=0.0)


class AcquisitionSpec(BaseModel):
    """Hint to the acquisition agent about where to look."""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["gutenberg"] = "gutenberg"
    search_query: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=500)


class CuriosityTrigger(BaseModel):
    """Typed intent to grow the chronicle in a focused region (PHX-0037 slice 1)."""

    model_config = ConfigDict(extra="forbid")

    trigger_id: str = Field(default_factory=new_run_id)
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    origin_query: str
    origin_query_run_id: str

    gap_class: GapClass
    region_descriptor: RegionDescriptor
    stub_signal_strength: float = Field(ge=0.0, le=1.0)

    proposed_acquisition_spec: AcquisitionSpec
    budget: TriggerBudget


__all__ = [
    "AcquisitionSpec",
    "CuriosityTrigger",
    "GapClass",
    "TriggerBudget",
]
