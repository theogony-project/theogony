"""
GrowthBridge decision logic (W7-A, PHX-0037 slice 1; W10 verdict gate).

These tests pin gap-class priority and acquisition-spec shape. Gate
ordering lives in ``tests/test_w10_trigger_semantics.py``.
"""

from __future__ import annotations

from theogony.config.settings import GrowthBridgeSettings
from theogony.core.model import NodeType
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.trigger import GapClass, TriggerReason
from theogony.reporting.models import RegionDescriptor, StubVerdict


def _enabled() -> GrowthBridgeSettings:
    return GrowthBridgeSettings(enabled=True)


def _region(
    seed_node_count: int = 0, dominant_node_type: NodeType | None = None
) -> RegionDescriptor:
    return RegionDescriptor(
        query_embedding=[0.1, 0.2, 0.3],
        seed_node_count=seed_node_count,
        dominant_node_type=dominant_node_type,
    )


def _stub(
    *,
    poor_named_entity_coverage: bool = False,
    low_node_count: bool = False,
    low_edge_density: bool = False,
    strength: float = 0.7,
) -> StubVerdict:
    return StubVerdict(
        poor_named_entity_coverage=poor_named_entity_coverage,
        low_node_count=low_node_count,
        low_edge_density=low_edge_density,
        stub_signal_strength=strength,
        is_stub=strength > 0.0,
    )


def _emit(
    bridge: GrowthBridge,
    *,
    verdict: str = "partial",
    cited: int = 0,
    explicit: bool = False,
    stub: StubVerdict | None = None,
    region: RegionDescriptor | None = None,
):
    return bridge.maybe_emit(
        origin_query="q",
        origin_query_run_id="r",
        answer_verdict=verdict,  # type: ignore[arg-type]
        cited_node_count=cited,
        stub_verdict=stub or _stub(strength=0.7),
        region_descriptor=region or _region(),
        explicit_user_request=explicit,
    )


class TestGapClassPriority:
    def test_entity_unknown_wins_over_region_thin(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = _emit(
            bridge,
            stub=_stub(
                poor_named_entity_coverage=True,
                low_node_count=True,
                strength=0.9,
            ),
            cited=0,
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.ENTITY_UNKNOWN

    def test_region_thin_when_only_low_citations(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = _emit(
            bridge,
            stub=_stub(low_node_count=True, strength=0.7),
            cited=1,
            region=_region(seed_node_count=1),
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.REGION_THIN

    def test_edge_density_low_when_cited_above_one(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = _emit(
            bridge,
            stub=_stub(low_edge_density=True, strength=0.6),
            cited=2,
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.EDGE_DENSITY_LOW


class TestAcquisitionSpec:
    def test_search_query_uses_original_query(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = bridge.maybe_emit(
            origin_query="Wer war Sven Hedin?",
            origin_query_run_id="r",
            answer_verdict="partial",
            cited_node_count=0,
            stub_verdict=_stub(low_node_count=True, strength=0.8),
            region_descriptor=_region(seed_node_count=1),
        )
        assert trigger is not None
        assert trigger.proposed_acquisition_spec.search_query == "Wer war Sven Hedin?"

    def test_rationale_includes_gap_class_strength_seed_count(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            answer_verdict="partial",
            cited_node_count=0,
            stub_verdict=_stub(low_node_count=True, strength=0.83),
            region_descriptor=_region(seed_node_count=2),
        )
        assert trigger is not None
        rationale = trigger.proposed_acquisition_spec.rationale
        assert "gap_class=region_thin" in rationale
        assert "stub_signal_strength=0.83" in rationale
        assert "seed_node_count=2" in rationale

    def test_entity_unknown_branch_with_dominant_type(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = bridge.maybe_emit(
            origin_query="Sven Hedin",
            origin_query_run_id="r",
            answer_verdict="partial",
            cited_node_count=0,
            stub_verdict=_stub(poor_named_entity_coverage=True, strength=0.75),
            region_descriptor=_region(dominant_node_type=NodeType.PERSON),
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.ENTITY_UNKNOWN
        assert trigger.proposed_acquisition_spec.search_query == "Sven Hedin"


class TestTriggerShape:
    def test_origin_fields_propagate(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = bridge.maybe_emit(
            origin_query="origin q",
            origin_query_run_id="origin-run-id",
            answer_verdict="failed",
            cited_node_count=0,
            stub_verdict=_stub(strength=0.6),
            region_descriptor=_region(),
        )
        assert trigger is not None
        assert trigger.origin_query == "origin q"
        assert trigger.origin_query_run_id == "origin-run-id"
        assert trigger.stub_signal_strength == 0.6
        assert trigger.trigger_reason == TriggerReason.WEAK_ANSWER

    def test_default_budget_has_locked_caps(self) -> None:
        bridge = GrowthBridge(_enabled())
        trigger = _emit(bridge, stub=_stub(strength=0.6))
        assert trigger is not None
        assert trigger.budget.max_sources_to_fetch == 1
        assert trigger.budget.max_total_bytes == 2 * 1024 * 1024
        assert trigger.budget.max_llm_eur == 0.50
