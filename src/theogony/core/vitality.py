"""Vitality-related math for knowledge nodes (single canonical module).

Two **formula families** live here on purpose:

* **Log / exponential** — ``compute_freshness`` (half-life decay),
  ``connectivity_score`` (``log1p``), ``dynamic_vitality_threshold``, and
  ``promotion_ready``. Used by :meth:`KnowledgeNode.can_be_promoted` and
  related threshold logic where the natural scale is multiplicative.

* **Linear** — ``compute_freshness_linear`` and ``compute_connectivity_linear``.
  Used by :class:`~theogony.memory.oneiros.OneirosWorker` per-tick lifecycle
  math (Plan §5 E8.5): predictable, operator-tunable, easy to audit.

PHX-0009 (Vitality Function Tuning) may eventually unify or retune these;
when that happens, the changes land **here**, not scattered across callers.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime


def compute_freshness_linear(
    last_accessed: datetime | None,
    horizon_days: float,
    *,
    now: datetime | None = None,
) -> float:
    """Linear freshness in ``[0.0, 1.0]`` for Oneiros lifecycle ticks.

    Returns ``1.0`` at zero idle time, ``0.0`` when idle time is at or above
    ``horizon_days``. Values in between decay linearly.

    ``now`` must be timezone-aware UTC (caller's responsibility). When
    ``last_accessed`` is naive, it is interpreted as UTC wall time for the
    idle interval (same rule Oneiros applies before subtracting from ``now``).
    When ``last_accessed`` is ``None``, the node is treated as never
    accessed and **fully fresh** (``1.0``).

    When ``now`` is omitted, :func:`datetime.now` in UTC is used (same pattern
    as :func:`compute_freshness`).
    """
    if last_accessed is None:
        return 1.0
    effective_now = now if now is not None else datetime.now(tz=UTC)
    ref = last_accessed if last_accessed.tzinfo is not None else last_accessed.replace(tzinfo=UTC)
    idle_days = (effective_now - ref).total_seconds() / 86400.0
    return max(0.0, 1.0 - idle_days / horizon_days)


def compute_connectivity_linear(degree: int, full_credit_edges: int) -> float:
    """Linear connectivity cap in ``[0.0, 1.0]`` for Oneiros lifecycle ticks.

    Returns ``min(1.0, degree / full_credit_edges)``. When
    ``full_credit_edges == 0``, returns ``1.0`` if ``degree > 0`` else ``0.0``
    to avoid division by zero.
    """
    if full_credit_edges == 0:
        return 1.0 if degree > 0 else 0.0
    return min(1.0, degree / full_credit_edges)


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
    now = datetime.now(tz=UTC)

    # Ensure timezone-aware comparison
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)

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
