"""
GrowthBridge — turn a stub signal into a typed CuriosityTrigger (W7-A, PHX-0037).

The bridge is the single place where the system decides "this query
revealed a real gap; emit a trigger". It is **pure**: no I/O, no store
access, no async. The decision logic is fully deterministic so the
auditor can replay it from a recorded ``StubVerdict`` + ``RegionDescriptor``
pair.

Persistence is the caller's job: ``QueryPipeline._finalize_report``
writes a :class:`~theogony.reporting.models.CuriosityRunReport` to the
run-reports directory whenever :meth:`GrowthBridge.maybe_emit` returns
a non-``None`` trigger.

Knob fidelity: the W7-A brief locks every behaviour here. Do not add
backoff, retries, batching, or multi-trigger emission without a fresh
brief amendment — those are by-design out of scope for slice 1.
"""

from __future__ import annotations

from typing import Literal

from theogony.config.settings import GrowthBridgeSettings
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
    TriggerReason,
)
from theogony.reporting.models import RegionDescriptor, StubVerdict


def _pick_gap_class(*, stub_verdict: StubVerdict, cited_node_count: int) -> GapClass:
    """Deterministic GapClass selection (W10 Knob 2)."""
    if cited_node_count == 0 and stub_verdict.poor_named_entity_coverage:
        return GapClass.ENTITY_UNKNOWN
    if cited_node_count <= 1:
        return GapClass.REGION_THIN
    if stub_verdict.low_edge_density:
        return GapClass.EDGE_DENSITY_LOW
    return GapClass.REGION_THIN


def _build_acquisition_spec(
    *,
    origin_query: str,
    gap_class: GapClass,
    region_descriptor: RegionDescriptor,
    stub_signal_strength: float,
) -> AcquisitionSpec:
    """Deterministic search-spec derivation (W7-A Knob 3).

    Both branches currently use the user's original query verbatim; the
    branching is here so a Phase-2 ticket can sharpen the
    ``ENTITY_UNKNOWN`` path (e.g. extract the unresolved entity name)
    without reshaping the schema. Do not implement that sharpening
    in W7-A — the contract is "user query goes through; the auditor
    can read the rationale and see why".
    """
    if gap_class == GapClass.ENTITY_UNKNOWN and region_descriptor.dominant_node_type is not None:
        search_query = origin_query
    else:
        search_query = origin_query
    rationale = (
        f"gap_class={gap_class.value} "
        f"stub_signal_strength={stub_signal_strength:.2f} "
        f"seed_node_count={region_descriptor.seed_node_count}"
    )
    return AcquisitionSpec(search_query=search_query, rationale=rationale)


class GrowthBridge:
    """Emit at most one CuriosityTrigger per query when the stub signal warrants it."""

    def __init__(self, settings: GrowthBridgeSettings) -> None:
        self._settings = settings

    def maybe_emit(
        self,
        *,
        origin_query: str,
        origin_query_run_id: str,
        answer_verdict: Literal["good", "partial", "poor", "failed"],
        cited_node_count: int,
        stub_verdict: StubVerdict,
        region_descriptor: RegionDescriptor,
        explicit_user_request: bool = False,
    ) -> CuriosityTrigger | None:
        """Return a :class:`CuriosityTrigger` if a trigger should fire, else ``None``.

        Decision rules (W10 Knob 1):

        - bridge disabled → ``None``;
        - ``explicit_user_request`` → emit (skip other checks);
        - ``answer_verdict in ("partial", "poor", "failed")`` and
          ``cited_node_count < min_cited_for_no_research`` → emit;
        - otherwise → ``None``.

        ``max_triggers_per_query`` is enforced by the caller because
        this method is, by contract, called at most once per query in
        W7-A. The setting is recorded in the schema so a future
        multi-trigger producer reads the same shape.
        """
        if not self._settings.enabled:
            return None

        trigger_reason: TriggerReason
        if explicit_user_request:
            trigger_reason = TriggerReason.USER_REQUEST
        elif answer_verdict in ("partial", "poor", "failed") and cited_node_count < int(
            self._settings.min_cited_for_no_research
        ):
            trigger_reason = TriggerReason.WEAK_ANSWER
        else:
            return None

        gap_class = _pick_gap_class(stub_verdict=stub_verdict, cited_node_count=cited_node_count)
        acquisition_spec = _build_acquisition_spec(
            origin_query=origin_query,
            gap_class=gap_class,
            region_descriptor=region_descriptor,
            stub_signal_strength=stub_verdict.stub_signal_strength,
        )
        return CuriosityTrigger(
            origin_query=origin_query,
            origin_query_run_id=origin_query_run_id,
            gap_class=gap_class,
            region_descriptor=region_descriptor,
            stub_signal_strength=stub_verdict.stub_signal_strength,
            proposed_acquisition_spec=acquisition_spec,
            budget=TriggerBudget(),
            trigger_reason=trigger_reason,
            answer_verdict=answer_verdict,
            cited_node_count=cited_node_count,
            research_plan=None,
        )


__all__ = ["GrowthBridge"]
