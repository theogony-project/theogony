"""TickPhase protocol and shared tick context for :class:`~theogony.memory.oneiros.OneirosWorker`.

Each tick is a **pipeline** of :class:`TickPhase` callables (see
``tick_phases.py`` for the six built-in Gen-1 steps). Future lifecycle
extensions register additional phases instead of growing a single
``_tick`` method — see PHX-0057 (edge pheromone), PHX-0058 (blind-spot
aggregation), PHX-0059 (Morpheus associator), PHX-0060 (re-clustering).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from theogony.config.settings import OneirosSettings, Settings
from theogony.core.model import KnowledgeNode, ScoreUpdate
from theogony.core.store import KnowledgeStore
from theogony.reporting.writer import RunReportWriter


def _aware(dt: datetime) -> datetime:
    """Coerce a naive datetime to UTC; pass aware datetimes through.

    Older :class:`KnowledgeNode` records on disk may have stored
    ``last_accessed`` as a naive datetime (UTC implicit). Subtraction
    against an aware ``datetime.now(UTC)`` raises; this helper
    normalises both sides to aware-UTC.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@runtime_checkable
class TickPhase(Protocol):
    """One phase of an OneirosWorker tick.

    Phases are executed in registered order. Each receives the
    shared mutable :class:`TickContext` for cross-phase state and
    metrics. A phase may raise; the worker catches at the tick
    boundary, marks the report as failed, and proceeds to the
    next tick (lifecycle keeps moving).
    """

    name: str

    async def run(self, ctx: TickContext) -> None: ...


@dataclass
class TickContext:
    """Mutable state shared across all phases of one tick.

    Phases mutate this. The worker reads it after all phases run
    to finalise the OneirosTickReport. Field types match what the
    OneirosTickReport ultimately needs.
    """

    started_at: datetime
    perf_started: float
    cfg: OneirosSettings
    store: KnowledgeStore
    app_settings: Settings = field(default_factory=Settings)
    writer: RunReportWriter | None = None

    nodes_ephemera: list[KnowledgeNode] = field(default_factory=list)
    edge_counts: dict[str, int] = field(default_factory=dict)
    updates: list[ScoreUpdate] = field(default_factory=list)
    pre_vitality: list[float] = field(default_factory=list)
    post_vitality: list[float] = field(default_factory=list)
    promote_targets: list[str] = field(default_factory=list)
    nodes_promoted: int = 0
    nodes_degraded: int = 0
    extras: dict[str, object] = field(default_factory=dict)
