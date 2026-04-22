"""Curiosity-layer signals: stub detection and blind-spot aggregation (PHX-0058 / W3)."""

from __future__ import annotations

from theogony.curiosity.stub_detector import StubDetector
from theogony.reporting.models import RegionDescriptor, StubVerdict

__all__ = [
    "BlindSpotAggregationPhase",
    "StubDetector",
    "StubVerdict",
    "RegionDescriptor",
    "compute_region_descriptor",
    "run_one_aggregation_pass",
]


def __getattr__(name: str) -> object:
    """Break import cycles with ``retrieval.pipeline`` (which needs region helpers)."""

    if name == "BlindSpotAggregationPhase":
        from theogony.curiosity.blind_spot_aggregation_phase import BlindSpotAggregationPhase

        return BlindSpotAggregationPhase
    if name == "compute_region_descriptor":
        from theogony.curiosity.region_descriptor import compute_region_descriptor

        return compute_region_descriptor
    if name == "run_one_aggregation_pass":
        from theogony.curiosity.runner import run_one_aggregation_pass

        return run_one_aggregation_pass
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
