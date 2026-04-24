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

from theogony.config.settings import GrowthBridgeSettings
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
)
from theogony.reporting.models import RegionDescriptor, StubVerdict


def _pick_gap_class(stub_verdict: StubVerdict) -> GapClass:
    """Deterministic GapClass selection (W7-A Knob 2).

    Priority order is fixed:

    1. ``poor_named_entity_coverage`` → ``ENTITY_UNKNOWN``
    2. ``low_node_count`` → ``REGION_THIN``
    3. otherwise → ``EDGE_DENSITY_LOW``

    Every ``StubVerdict`` lands in exactly one class. Adding more
    vocabulary requires a fresh PHX ticket and a brief amendment.
    """
    if stub_verdict.poor_named_entity_coverage:
        return GapClass.ENTITY_UNKNOWN
    if stub_verdict.low_node_count:
        return GapClass.REGION_THIN
    return GapClass.EDGE_DENSITY_LOW


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
        stub_verdict: StubVerdict,
        region_descriptor: RegionDescriptor,
    ) -> CuriosityTrigger | None:
        """Return a :class:`CuriosityTrigger` if a trigger should fire, else ``None``.

        Decision rules (W7-A Knob 5):

        - bridge disabled → ``None``;
        - stub_signal_strength below threshold → ``None``;
        - otherwise build the trigger from the deterministic Knob 2 + 3
          derivations and return it.

        ``max_triggers_per_query`` is enforced by the caller because
        this method is, by contract, called at most once per query in
        W7-A. The setting is recorded in the schema so a future
        multi-trigger producer reads the same shape.
        """
        if not self._settings.enabled:
            return None
        if stub_verdict.stub_signal_strength < self._settings.trigger_threshold:
            return None
        gap_class = _pick_gap_class(stub_verdict)
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
        )


__all__ = ["GrowthBridge"]
