"""
Schema discipline for the W7-A CuriosityTrigger family (PHX-0037 slice 1).

The trigger is the spine of every downstream agent (Argus, HestiaLite,
the cockpit growth panel). If a typo can silently land in a producer
and disappear from the report, the audit trail is worse than useless —
hence the ``extra="forbid"`` enforcement and the round-trip checks.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
    TriggerReason,
)
from theogony.reporting.models import RegionDescriptor


def _region() -> RegionDescriptor:
    return RegionDescriptor(
        query_embedding=[0.1, 0.2, 0.3],
        seed_node_count=2,
    )


def _trigger() -> CuriosityTrigger:
    return CuriosityTrigger(
        origin_query="Wer war Sven Hedin?",
        origin_query_run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=_region(),
        stub_signal_strength=0.83,
        proposed_acquisition_spec=AcquisitionSpec(
            search_query="Sven Hedin Tibet",
            rationale="seed_node_count=2",
        ),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.WEAK_ANSWER,
        answer_verdict="partial",
        cited_node_count=0,
    )


class TestSchemaShape:
    def test_trigger_round_trip_json(self) -> None:
        original = _trigger()
        payload = original.model_dump_json()
        restored = CuriosityTrigger.model_validate_json(payload)
        assert restored == original
        assert restored.gap_class == GapClass.REGION_THIN
        assert restored.proposed_acquisition_spec.source_type == "gutenberg"

    def test_trigger_rejects_unknown_field(self) -> None:
        payload = json.loads(_trigger().model_dump_json())
        payload["unexpected"] = "noise"
        with pytest.raises(ValidationError):
            CuriosityTrigger.model_validate(payload)

    def test_acquisition_spec_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            AcquisitionSpec(search_query="ok", rationale="ok", unexpected="x")  # type: ignore[call-arg]

    def test_acquisition_spec_source_type_locked_to_gutenberg(self) -> None:
        # The Literal["gutenberg"] is the W7-A allowlist; widening is a
        # future PHX, not an early-binding flexibility hook.
        with pytest.raises(ValidationError):
            AcquisitionSpec.model_validate({"source_type": "web", "search_query": "x"})

    def test_acquisition_spec_search_query_min_length(self) -> None:
        with pytest.raises(ValidationError):
            AcquisitionSpec(search_query="")

    def test_budget_caps_enforced(self) -> None:
        # max_sources_to_fetch must be >= 1 and <= 5
        with pytest.raises(ValidationError):
            TriggerBudget(max_sources_to_fetch=0)
        with pytest.raises(ValidationError):
            TriggerBudget(max_sources_to_fetch=99)

    def test_stub_signal_strength_range(self) -> None:
        with pytest.raises(ValidationError):
            CuriosityTrigger(
                origin_query="q",
                origin_query_run_id="r",
                gap_class=GapClass.REGION_THIN,
                region_descriptor=_region(),
                stub_signal_strength=1.5,
                proposed_acquisition_spec=AcquisitionSpec(search_query="q"),
                budget=TriggerBudget(),
                trigger_reason=TriggerReason.WEAK_ANSWER,
                answer_verdict="partial",
                cited_node_count=0,
            )

    def test_trigger_default_factories_unique(self) -> None:
        a = _trigger()
        b = _trigger()
        assert a.trigger_id != b.trigger_id
        assert a.emitted_at <= b.emitted_at
