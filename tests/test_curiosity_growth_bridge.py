"""
GrowthBridge decision logic (W7-A, PHX-0037 slice 1).

These tests pin every Knob 2 / Knob 3 / Knob 5 rule. They also serve
as the audit specification: an operator reading these tests learns
exactly when a trigger fires, which ``GapClass`` it picks, and what
the rationale string looks like. Drift here = drift in the demo
contract.
"""

from __future__ import annotations

from theogony.config.settings import GrowthBridgeSettings
from theogony.core.model import NodeType
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.trigger import GapClass
from theogony.reporting.models import RegionDescriptor, StubVerdict


def _enabled_settings(threshold: float = 0.5) -> GrowthBridgeSettings:
    return GrowthBridgeSettings(enabled=True, trigger_threshold=threshold)


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
    strength: float = 0.7,
) -> StubVerdict:
    return StubVerdict(
        poor_named_entity_coverage=poor_named_entity_coverage,
        low_node_count=low_node_count,
        stub_signal_strength=strength,
        is_stub=strength > 0.0,
    )


class TestGate:
    def test_disabled_returns_none(self) -> None:
        bridge = GrowthBridge(GrowthBridgeSettings(enabled=False, trigger_threshold=0.0))
        result = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(strength=1.0),
            region_descriptor=_region(),
        )
        assert result is None

    def test_below_threshold_returns_none(self) -> None:
        bridge = GrowthBridge(_enabled_settings(threshold=0.6))
        result = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(strength=0.59),
            region_descriptor=_region(),
        )
        assert result is None

    def test_at_threshold_emits(self) -> None:
        bridge = GrowthBridge(_enabled_settings(threshold=0.5))
        result = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(strength=0.5),
            region_descriptor=_region(),
        )
        assert result is not None


class TestGapClassPriority:
    def test_entity_unknown_wins_over_region_thin(self) -> None:
        # Both flags raised; ENTITY_UNKNOWN has priority 1.
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(
                poor_named_entity_coverage=True,
                low_node_count=True,
                strength=0.9,
            ),
            region_descriptor=_region(),
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.ENTITY_UNKNOWN

    def test_region_thin_when_only_low_node_count(self) -> None:
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(low_node_count=True, strength=0.7),
            region_descriptor=_region(seed_node_count=1),
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.REGION_THIN

    def test_edge_density_low_default(self) -> None:
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(strength=0.6),
            region_descriptor=_region(),
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.EDGE_DENSITY_LOW


class TestAcquisitionSpec:
    def test_search_query_uses_original_query(self) -> None:
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="Wer war Sven Hedin?",
            origin_query_run_id="r",
            stub_verdict=_stub(low_node_count=True, strength=0.8),
            region_descriptor=_region(seed_node_count=1),
        )
        assert trigger is not None
        assert trigger.proposed_acquisition_spec.search_query == "Wer war Sven Hedin?"

    def test_rationale_includes_gap_class_strength_seed_count(self) -> None:
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(low_node_count=True, strength=0.83),
            region_descriptor=_region(seed_node_count=2),
        )
        assert trigger is not None
        rationale = trigger.proposed_acquisition_spec.rationale
        assert "gap_class=region_thin" in rationale
        assert "stub_signal_strength=0.83" in rationale
        assert "seed_node_count=2" in rationale

    def test_entity_unknown_branch_with_dominant_type(self) -> None:
        # Branch exists for a future Phase-2 sharpening; for now both
        # paths still use the original query. The branching alone
        # must not crash with a populated ``dominant_node_type``.
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="Sven Hedin",
            origin_query_run_id="r",
            stub_verdict=_stub(poor_named_entity_coverage=True, strength=0.75),
            region_descriptor=_region(dominant_node_type=NodeType.PERSON),
        )
        assert trigger is not None
        assert trigger.gap_class == GapClass.ENTITY_UNKNOWN
        assert trigger.proposed_acquisition_spec.search_query == "Sven Hedin"


class TestTriggerShape:
    def test_origin_fields_propagate(self) -> None:
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="origin q",
            origin_query_run_id="origin-run-id",
            stub_verdict=_stub(strength=0.6),
            region_descriptor=_region(),
        )
        assert trigger is not None
        assert trigger.origin_query == "origin q"
        assert trigger.origin_query_run_id == "origin-run-id"
        assert trigger.stub_signal_strength == 0.6

    def test_default_budget_has_locked_caps(self) -> None:
        bridge = GrowthBridge(_enabled_settings())
        trigger = bridge.maybe_emit(
            origin_query="q",
            origin_query_run_id="r",
            stub_verdict=_stub(strength=0.6),
            region_descriptor=_region(),
        )
        assert trigger is not None
        assert trigger.budget.max_sources_to_fetch == 1
        assert trigger.budget.max_total_bytes == 2 * 1024 * 1024
        assert trigger.budget.max_llm_eur == 0.50
