"""W10 — verdict-based growth gate, gap_class, ResearchPlan schema, stale env guard."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from theogony.config.settings import GrowthBridgeSettings, Settings
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.trigger import (
    GapClass,
    ResearchPlan,
    ResearchStep,
    ResearchStepKind,
    TriggerReason,
)
from theogony.reporting.models import RegionDescriptor, StubVerdict


def _region(**kwargs: object) -> RegionDescriptor:
    return RegionDescriptor(
        query_embedding=[0.1, 0.2, 0.3],
        seed_node_count=int(kwargs.get("seed_node_count", 0)),
        dominant_node_type=kwargs.get("dominant_node_type"),
    )


def _stub(**kwargs: object) -> StubVerdict:
    return StubVerdict(
        poor_named_entity_coverage=bool(kwargs.get("poor_named_entity_coverage", False)),
        low_node_count=bool(kwargs.get("low_node_count", False)),
        low_edge_density=bool(kwargs.get("low_edge_density", False)),
        stub_signal_strength=float(kwargs.get("strength", 0.7)),
        is_stub=True,
    )


def _bridge(**kwargs: object) -> GrowthBridge:
    s = GrowthBridgeSettings(enabled=True, **kwargs)
    return GrowthBridge(s)


def test_gate_returns_none_when_disabled() -> None:
    bridge = GrowthBridge(GrowthBridgeSettings(enabled=False))
    r = bridge.maybe_emit(
        origin_query="q",
        origin_query_run_id="r",
        answer_verdict="partial",
        cited_node_count=0,
        stub_verdict=_stub(strength=1.0),
        region_descriptor=_region(),
    )
    assert r is None


def test_gate_returns_none_on_good_verdict_even_if_constellation_thin() -> None:
    bridge = _bridge(min_cited_for_no_research=3)
    r = bridge.maybe_emit(
        origin_query="q",
        origin_query_run_id="r",
        answer_verdict="good",
        cited_node_count=0,
        stub_verdict=_stub(low_node_count=True, strength=0.99),
        region_descriptor=_region(),
    )
    assert r is None


def test_gate_emits_on_partial_verdict_with_low_citations() -> None:
    bridge = _bridge(min_cited_for_no_research=3)
    t = bridge.maybe_emit(
        origin_query="q",
        origin_query_run_id="r",
        answer_verdict="partial",
        cited_node_count=1,
        stub_verdict=_stub(low_edge_density=True, strength=0.5),
        region_descriptor=_region(),
    )
    assert t is not None
    assert t.trigger_reason == TriggerReason.WEAK_ANSWER
    assert t.answer_verdict == "partial"
    assert t.cited_node_count == 1


def test_gate_emits_on_explicit_user_request_regardless_of_verdict() -> None:
    bridge = _bridge(min_cited_for_no_research=3)
    t = bridge.maybe_emit(
        origin_query="q",
        origin_query_run_id="r",
        answer_verdict="good",
        cited_node_count=10,
        stub_verdict=_stub(strength=0.1),
        region_descriptor=_region(),
        explicit_user_request=True,
    )
    assert t is not None
    assert t.trigger_reason == TriggerReason.USER_REQUEST
    assert t.answer_verdict == "good"
    assert t.cited_node_count == 10


def test_gap_class_priority_entity_unknown_first() -> None:
    bridge = _bridge()
    t = bridge.maybe_emit(
        origin_query="q",
        origin_query_run_id="r",
        answer_verdict="partial",
        cited_node_count=0,
        stub_verdict=_stub(poor_named_entity_coverage=True, low_node_count=True, strength=0.9),
        region_descriptor=_region(),
    )
    assert t is not None
    assert t.gap_class == GapClass.ENTITY_UNKNOWN


def test_research_plan_schema_round_trip() -> None:
    plan = ResearchPlan(
        steps=[
            ResearchStep(
                kind=ResearchStepKind.GUTENBERG_SEARCH,
                target="Sven Hedin",
                rationale="seed",
            )
        ],
        planner_model_id="stub",
        planner_cost_eur=0.01,
    )
    restored = ResearchPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan


def test_research_plan_max_5_steps_enforced() -> None:
    steps = [
        ResearchStep(kind=ResearchStepKind.WEB_FETCH, target=f"https://example.com/{i}")
        for i in range(6)
    ]
    with pytest.raises(ValidationError):
        ResearchPlan(steps=steps)


def test_old_trigger_threshold_setting_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__GROWTH_BRIDGE__TRIGGER_THRESHOLD", "0.5")
    with pytest.raises(ValidationError):
        Settings()
