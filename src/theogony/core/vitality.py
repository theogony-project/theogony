"""
Vitality computation and lifecycle management for knowledge nodes.

The vitality score determines whether a node is promoted (Ephemera → Mneme),
retained, compressed, archived, or deleted. The threshold is dynamic —
adjusted by storage pressure, query latency, and knowledge density.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone


def compute_freshness(
    created_at: datetime,
    last_accessed: datetime | None = None,
    half_life_days: float = 365.0,
) -> float:
    """
    Compute a time-decayed freshness score.

    Freshness starts at 1.0 and decays exponentially. The half-life
    determines how quickly freshness falls to 0.5.

    Recent access resets the decay clock.
    """
    reference = last_accessed or created_at
    now = datetime.now(tz=timezone.utc)

    # Ensure timezone-aware comparison
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    age_days = (now - reference).total_seconds() / 86400
    return math.exp(-math.log(2) * age_days / half_life_days)


def dynamic_vitality_threshold(
    storage_pressure: float = 0.0,
    query_latency_p95_ms: float = 0.0,
    baseline: float = 0.25,
) -> float:
    """
    Compute the dynamic vitality threshold below which nodes become candidates
    for compression, archival, or deletion.

    The threshold rises under storage pressure or degrading query latency,
    causing more aggressive pruning. It falls when the system is healthy.

    Args:
        storage_pressure: fraction of storage capacity used (0.0 to 1.0)
        query_latency_p95_ms: 95th percentile query latency in milliseconds
        baseline: the baseline threshold under ideal conditions

    Returns:
        The effective vitality threshold (0.0 to 1.0)
    """
    pressure_adjustment = storage_pressure * 0.3
    latency_adjustment = max(0.0, (query_latency_p95_ms - 500) / 5000) * 0.2
    return min(0.8, baseline + pressure_adjustment + latency_adjustment)


def promotion_ready(
    confidence: float,
    connectivity: float,
    confidence_threshold: float = 0.65,
    connectivity_threshold: float = 0.2,
) -> bool:
    """
    Determine whether a node is ready to be promoted from Ephemera to Mneme.

    A node must be both well-verified AND well-connected. An isolated
    high-confidence fact is still suspect — it may be correct, but it
    has not been integrated into the knowledge network.
    """
    return confidence >= confidence_threshold and connectivity >= connectivity_threshold


def connectivity_score(edge_count: int, max_expected: int = 50) -> float:
    """
    Convert a raw edge count into a normalized connectivity score [0.0, 1.0].

    Uses a logarithmic scale so that the difference between 1 and 10 edges
    is large, but the difference between 100 and 200 edges is small.
    """
    if edge_count <= 0:
        return 0.0
    return min(1.0, math.log1p(edge_count) / math.log1p(max_expected))
