# F2 — TickPhase pipeline refactoring in OneirosWorker

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-21  
**Branch:** new branch off `main`, e.g. `chore/f2-tickphase-pipeline`  
**Scope:** one PR, tightly scoped  
**Predecessor:** F1 (PR #46) merged. Vitality math now lives in `core/vitality.py`. F2 is the **second sprint of the architecture-audit Phase 0**. F3 (RetrievalStrategy Protocol) follows as a separate brief.

Direct brief, no Daedalus. This is a refactoring etappe, not an architectural decision round. The pipeline shape and the phase responsibilities are spec'd here verbatim — your job is execution discipline, not redesign.

---

## Why this etappe exists

`OneirosWorker._tick` is one method that does six structurally distinct things in sequence:

1. Snapshot Ephemera (one `export_layer` round-trip)
2. Bulk neighbour count (one `count_neighbors_in_layer` round-trip)
3. Recompute scores (the linear-formula loop now in `core/vitality.py`)
4. Bulk write score updates (one `batch_update_scores` round-trip)
5. Promote nodes that crossed the promotion threshold
6. Degrade idle low-vitality Mneme nodes (the hysteresis pass)

Plus the `try / finally` builds and writes the `OneirosTickReport` regardless.

Today this is acceptable. Looking forward, four open PHX tickets each want to add their own phase to the same tick:

- **PHX-0057** Edge-Pheromone — needs a "decay edge weights" phase + a "consume citation traversals to bump edge weights" phase
- **PHX-0058** Aggregated Stub Detection — needs a "scan recent QueryRunReports for blind-spot clusters" phase  
- **PHX-0059** Morpheus-as-Associator — needs a "propose new edges via deterministic signals" phase
- **PHX-0060** Domain Clusters — needs a periodic "re-cluster Ephemera + Mneme via HDBSCAN" phase

Without F2, every one of those tickets becomes either a god-method extension (compounding complexity inside `_tick`) or a parallel worker (multiplying lifecycle ownership). Both are the wrong direction.

**F2 makes `_tick` a pipeline of `TickPhase` objects.** Each existing piece becomes one phase. Each future piece registers as one more phase. Phase ordering, opt-in / opt-out, per-phase metrics, per-phase failure isolation — all become composable.

This is the foundation refactoring PHX-0057 / 0058 / 0059 / 0060 build on top of. Land it before any of them are picked up.

---

## Goal

After this PR:

- `src/theogony/memory/tick_phase.py` (new) defines the `TickPhase` Protocol and the `TickContext` dataclass.
- `src/theogony/memory/oneiros.py` `_tick` becomes a thin loop over a configured list of `TickPhase` instances.
- The current six steps live as six `TickPhase` implementations: `SnapshotEphemeraPhase`, `CountNeighborsPhase`, `RecomputeScoresPhase`, `WriteScoresPhase`, `PromotePhase`, `DegradeMnemePhase`.
- `Settings.oneiros.enabled_phases: list[str]` lets the operator opt phases out (default: all six enabled).
- The `OneirosTickReport` finalisation (steps 7) stays intact and preserves today's exact field semantics.
- `tests/test_oneiros.py` stays green byte-for-byte (no behaviour change).
- New `tests/test_tick_phase.py` covers the Protocol mechanics and one fake phase to demonstrate the extension surface.
- A new short module docstring at the top of `tick_phase.py` explains the pattern and points future phase-authors at PHX-0057/0058/0059/0060 as the consumers.

---

## Scope decisions (read first)

### 1. The `TickPhase` Protocol

Pure async protocol, single method:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class TickPhase(Protocol):
    """One phase of an OneirosWorker tick.

    Phases are executed in registered order. Each receives the
    shared mutable :class:`TickContext` for cross-phase state and
    metrics. A phase may raise; the worker catches at the tick
    boundary, marks the report as failed, and proceeds to the
    next tick (lifecycle keeps moving).
    """

    name: str  # short stable identifier; used in metrics + opt-out

    async def run(self, ctx: TickContext) -> None: ...
```

`name` is a class attribute, not a property — gives reliable `enabled_phases` filtering without instantiating.

### 2. The `TickContext` dataclass

```python
from dataclasses import dataclass, field

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

    # Populated by SnapshotEphemeraPhase:
    nodes_ephemera: list[KnowledgeNode] = field(default_factory=list)

    # Populated by CountNeighborsPhase:
    edge_counts: dict[str, int] = field(default_factory=dict)

    # Populated by RecomputeScoresPhase:
    updates: list[ScoreUpdate] = field(default_factory=list)
    pre_vitality: list[float] = field(default_factory=list)
    post_vitality: list[float] = field(default_factory=list)
    promote_targets: list[str] = field(default_factory=list)

    # Populated by PromotePhase:
    nodes_promoted: int = 0

    # Populated by DegradeMnemePhase:
    nodes_degraded: int = 0

    # Optional bag for future phases (PHX-0057 etc.) without
    # re-spec'ing the dataclass every time. Use sparingly — proper
    # dataclass fields are preferred when a value is read by report
    # finalisation.
    extras: dict[str, object] = field(default_factory=dict)
```

`extras` is the deliberate escape hatch for new phases that want to write something the worker does not yet know about. PHX-0057 will likely promote some `extras` fields to proper dataclass fields when it lands.

### 3. The six existing-step phases

Spec is mechanical translation. Each phase reads from `ctx` and writes to `ctx`; nothing else changes.

```python
class SnapshotEphemeraPhase:
    name = "snapshot_ephemera"

    async def run(self, ctx: TickContext) -> None:
        ctx.nodes_ephemera = [
            n async for n in ctx.store.export_layer(Layer.EPHEMERA)
        ]


class CountNeighborsPhase:
    name = "count_neighbors"

    async def run(self, ctx: TickContext) -> None:
        ctx.edge_counts = await ctx.store.count_neighbors_in_layer(Layer.EPHEMERA)


class RecomputeScoresPhase:
    name = "recompute_scores"

    async def run(self, ctx: TickContext) -> None:
        for node in ctx.nodes_ephemera:
            before = node.scores.vitality()
            ctx.pre_vitality.append(before)

            degree = ctx.edge_counts.get(node.id, 0)
            new_conn = compute_connectivity_linear(
                degree=degree,
                full_credit_edges=ctx.cfg.connectivity_full_credit_edges,
            )
            new_fresh = compute_freshness_linear(
                node.last_accessed,
                horizon_days=ctx.cfg.freshness_horizon_days,
                now=ctx.started_at,
            )

            new_scores = node.scores.model_copy(
                update={"connectivity": new_conn, "freshness": new_fresh}
            )
            new_vitality = new_scores.vitality()
            ctx.post_vitality.append(new_vitality)

            ctx.updates.append(
                ScoreUpdate(
                    node_id=node.id,
                    connectivity=new_conn,
                    freshness=new_fresh,
                    vitality=new_vitality,
                )
            )
            if new_vitality >= ctx.cfg.promote_threshold:
                ctx.promote_targets.append(node.id)


class WriteScoresPhase:
    name = "write_scores"

    async def run(self, ctx: TickContext) -> None:
        await ctx.store.batch_update_scores(ctx.updates)


class PromotePhase:
    name = "promote"

    async def run(self, ctx: TickContext) -> None:
        for node_id in ctx.promote_targets:
            await ctx.store.promote(node_id)
            ctx.nodes_promoted += 1


class DegradeMnemePhase:
    name = "degrade_mneme"

    async def run(self, ctx: TickContext) -> None:
        min_idle_s = ctx.cfg.degrade_min_idle_days * 86400.0
        async for mnode in ctx.store.export_layer(Layer.MNEME):
            idle_s = (ctx.started_at - _aware(mnode.last_accessed)).total_seconds()
            if (
                mnode.scores.vitality() <= ctx.cfg.degrade_threshold
                and idle_s >= min_idle_s
            ):
                await ctx.store.degrade(mnode.id)
                ctx.nodes_degraded += 1
```

These six phases live in `src/theogony/memory/tick_phases.py` (note the plural — distinct from the Protocol module `tick_phase.py`).

### 4. The new `_tick` body in OneirosWorker

```python
async def _tick(self) -> None:
    """One pass over EPHEMERA + MNEME. Pipeline of TickPhase instances.

    Phase ordering is fixed at construction-time from
    ``Settings.oneiros.enabled_phases``. Per-phase failures are
    caught at the tick boundary; the lifecycle keeps moving
    regardless.
    """
    started = datetime.now(UTC)
    perf_started = time.perf_counter()
    cfg = self._settings.oneiros
    raised = False

    ctx = TickContext(
        started_at=started,
        perf_started=perf_started,
        cfg=cfg,
        store=self._store,
    )

    try:
        for phase in self._phases:
            await phase.run(ctx)
    except asyncio.CancelledError:
        raise
    except Exception:
        raised = True
        raise
    finally:
        duration_s = time.perf_counter() - perf_started
        try:
            report = self._finalize_report(
                started_at=started,
                duration_s=duration_s,
                nodes_evaluated=len(ctx.nodes_ephemera) if not raised else 0,
                nodes_promoted=ctx.nodes_promoted if not raised else 0,
                nodes_degraded=ctx.nodes_degraded if not raised else 0,
                pre_vitality=ctx.pre_vitality if not raised else [],
                post_vitality=ctx.post_vitality if not raised else [],
                raised=raised,
            )
            self._writer.write(report)
        except Exception:  # pragma: no cover - defensive
            log.exception("oneiros tick report write failed")
```

`self._phases` is constructed in `__init__` from `cfg.enabled_phases`. The construction is straightforward — see Scope decision 5.

### 5. `OneirosWorker.__init__` constructs the phase list from settings

```python
DEFAULT_PHASE_REGISTRY: dict[str, type[TickPhase]] = {
    "snapshot_ephemera": SnapshotEphemeraPhase,
    "count_neighbors": CountNeighborsPhase,
    "recompute_scores": RecomputeScoresPhase,
    "write_scores": WriteScoresPhase,
    "promote": PromotePhase,
    "degrade_mneme": DegradeMnemePhase,
}

class OneirosWorker:
    def __init__(
        self,
        store: KnowledgeStore,
        settings: Settings,
        report_writer: RunReportWriter,
        *,
        tick_interval_s: float | None = None,
        phase_registry: dict[str, type[TickPhase]] | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._writer = report_writer
        self._tick_interval_s = (
            tick_interval_s if tick_interval_s is not None else settings.oneiros.tick_interval_s
        )

        registry = phase_registry or DEFAULT_PHASE_REGISTRY
        self._phases: list[TickPhase] = [
            registry[name]() for name in settings.oneiros.enabled_phases
            if name in registry
        ]
```

The `phase_registry` keyword is the **test seam**: tests can inject fake phases or partial registries without touching settings.

### 6. New `Settings.oneiros.enabled_phases`

Add to `OneirosSettings`:

```python
enabled_phases: list[str] = Field(
    default_factory=lambda: [
        "snapshot_ephemera",
        "count_neighbors",
        "recompute_scores",
        "write_scores",
        "promote",
        "degrade_mneme",
    ],
    description=(
        "Ordered list of TickPhase names to run per tick. Default = "
        "all six built-in phases in their canonical order. Operators "
        "can disable phases (e.g. omit 'promote' for read-only test "
        "deployments) or reorder. Future phases from PHX-0057/0058/"
        "0059/0060 are added via custom phase_registry injection."
    ),
)
```

Operators override via env: `THEOGONY_ONEIROS__ENABLED_PHASES='["snapshot_ephemera","count_neighbors","recompute_scores","write_scores"]'` (JSON list in env per the existing pydantic-settings convention).

### 7. Per-phase failure isolation (Phase-1 keep simple)

For F2, **a phase exception fails the whole tick** — same behaviour as today's `_tick`. The outer `except Exception: raised = True; raise` block is unchanged.

PHX-0057's pheromone-decay phase will likely want **per-phase isolation** (one phase failing should not abort the others). That extension lives in the future PR, not here. Document the deferred-feature in a TODO comment in `_tick`:

```python
# TODO(F2-followup): per-phase failure isolation. Today a phase
# exception fails the whole tick. Future phases (pheromone-decay,
# morpheus-associator) may benefit from per-phase try/except that
# logs and continues. Land that when the first phase that wants
# isolation arrives.
```

### 8. The `_finalize_report` method stays exactly as it is

Same signature, same body. The only difference: it is now called with values that came from `ctx` instead of from local variables in the same function. Behaviour preserved.

---

## Implementation plan (file-by-file)

### `src/theogony/memory/tick_phase.py` (new)

The Protocol + the TickContext dataclass + the module docstring. Imports kept tight (only `typing`, `dataclasses`, `datetime`, `theogony.config.settings.OneirosSettings`, `theogony.core.model`, `theogony.core.store`).

### `src/theogony/memory/tick_phases.py` (new)

The six phase implementations. Each is its own small class. The module docstring explains the pattern and points at the registry in `oneiros.py`.

### `src/theogony/memory/oneiros.py`

1. Replace the inline `_tick` body with the pipeline-loop body from Scope decision 4.
2. Add `phase_registry` constructor keyword (Scope decision 5).
3. Add the `DEFAULT_PHASE_REGISTRY` constant at module level.
4. Move the `_aware` helper to `tick_phase.py` (it is used by `DegradeMnemePhase`); re-export from `oneiros.py` for backward compatibility if any test imports it.
5. The `_finalize_report` method stays (Scope decision 8).

### `src/theogony/config/settings.py`

1. Add `enabled_phases` to `OneirosSettings` per Scope decision 6.
2. No other settings change.

### `tests/test_oneiros.py`

Should stay green without modification. **This is the regression contract.** If any test fails, you have introduced behaviour drift; investigate before claiming F2 done.

### `tests/test_tick_phase.py` (new)

Add at minimum:

- `test_tick_phase_protocol_runtime_checkable` — assert `isinstance(SnapshotEphemeraPhase(), TickPhase)`.
- `test_tick_context_default_field_initialisation` — assert that newly-constructed `TickContext` has empty lists/dicts and zero counts.
- `test_phase_pipeline_runs_in_registered_order` — define two fake phases that each append to `ctx.extras["call_order"]`, run them through a fake worker, assert order.
- `test_phase_can_be_disabled_via_settings` — construct OneirosWorker with `enabled_phases=["snapshot_ephemera", "count_neighbors"]` and a fake registry; assert only those two run; the rest do not.
- `test_unknown_phase_name_in_settings_silently_skipped` — `enabled_phases=["nonexistent"]` does not raise; the phase list is just empty.
- `test_phase_exception_propagates_and_marks_tick_failed` — define a fake phase that raises; assert the worker's report has `status="failed"`.

### Documentation touches

1. `docs/PHOENIX_BACKLOG.md` PHX-0057 / 0058 / 0059 / 0060 catalogue entries each get a one-line update at the end: `"Implementation will plug into the TickPhase pipeline introduced by F2 (PR #...)."`
2. `docs/ARCHITECTURE.md` Memory Architecture section: short paragraph announcing the TickPhase pipeline as the lifecycle extension surface.
3. `prompts/talos.md` — no change.

---

## Cost-benefit considerations

**Token cost**: small-to-medium. Composer needs to translate one big function into seven small classes mechanically. The brief is detailed; the diff should be ≤ 350 lines of net change. Estimate ≤ €0.30 of Composer execution.

**Runtime cost**: zero net. Same number of `await` points, same number of round-trips, same memory profile. The pipeline-loop overhead is one Python `for` iteration of 6 small async calls per tick — orders of magnitude below the network cost of the round-trips themselves.

**Test cost**: marginal. ~6 new tiny tests; total wall-clock added to the suite is negligible.

**Failure modes worth watching**:

- **Behaviour drift**: if `tests/test_oneiros.py` fails, you have introduced an arithmetic or ordering difference. Investigate. The contract is byte-identical reports for any given input.
- **Settings serialisation**: pydantic-settings reading `enabled_phases` from a JSON env var has a known footgun if the JSON is malformed. The default-factory handles the missing-env case; for malformed-env, pydantic raises a clear validation error — let it.
- **Import cycle**: `tick_phase.py` → `oneiros.py` → `tick_phase.py` is fine because `oneiros.py` only imports the Protocol + dataclass at module-level (no class-body cycle). But if you accidentally import phases from `tick_phases.py` inside `tick_phase.py`, the cycle reverses. Keep `tick_phase.py` Protocol-and-dataclass-only.

---

## Out of scope (do not do)

- **Do not** add per-phase failure isolation. Document the TODO; the first ticket that needs it (likely PHX-0057) will add it.
- **Do not** add per-phase metrics. The TickContext carries the data the existing `OneirosTickReport` needs; per-phase latency / cost metrics are PHX-0057-territory.
- **Do not** add a new RunReport type. The existing `OneirosTickReport` stays. Future phases that emit their own reports add their own RunReport types alongside.
- **Do not** change the OneirosTickReport schema. Field semantics, JSON shape, persistence path — all untouched.
- **Do not** add a CLI flag for phase configuration in this PR. Operators configure via `THEOGONY_ONEIROS__ENABLED_PHASES` env var; CLI flag is a future ergonomics ticket.
- **Do not** touch the `RelevanceTracker` or any other lifecycle code outside `oneiros.py`. F2 is OneirosWorker-only.
- **Do not** add new abstractions (factories, builders, dependency injection containers). The `phase_registry` keyword + the simple list-of-instances is the entire abstraction surface.

---

## Done when

- [ ] `src/theogony/memory/tick_phase.py` exists with the Protocol + TickContext + module docstring.
- [ ] `src/theogony/memory/tick_phases.py` exists with the six phase classes.
- [ ] `OneirosWorker._tick` is the thin pipeline loop from Scope decision 4. The `_finalize_report` method is unchanged.
- [ ] `OneirosWorker.__init__` accepts `phase_registry` keyword and constructs `self._phases` from `settings.oneiros.enabled_phases`.
- [ ] `Settings.oneiros.enabled_phases` exists with the canonical-six default.
- [ ] `tests/test_oneiros.py` stays green without modification.
- [ ] `tests/test_tick_phase.py` covers all six new tests listed in the implementation plan; all green.
- [ ] Full test suite (`pytest -q`) green.
- [ ] `ruff check` clean. `ruff format --check` clean.
- [ ] `mypy src/theogony/memory/` clean (strict).
- [ ] `docs/PHOENIX_BACKLOG.md` PHX-0057 / 0058 / 0059 / 0060 entries get the one-line TickPhase-pipeline update.
- [ ] `docs/ARCHITECTURE.md` Memory Architecture section gets the TickPhase paragraph.
- [ ] PR title: `chore(memory): F2 — TickPhase pipeline refactoring in OneirosWorker`. PR body lists which Plan / PHX ticket the work covers (foundation for PHX-0057/0058/0059/0060) and confirms zero behaviour change against `test_oneiros.py`.

---

## After this PR

F2 closes. Phase 0's last brief is **F3 — RetrievalStrategy Protocol skeleton** (separate brief, separate PR; this is PHX-0056 Phase 1). When F1 + F2 + F3 all land, Phase 0 is complete and Phase 1 (Cluster v1, PHX-0060) becomes a clean implementation against a clean foundation.

The future tickets that build on F2:

- PHX-0057 will add a `BumpEdgePheromonePhase` (called by `RelevanceTracker`-equivalent on cited paths, runs as part of the citation write-back rather than the periodic tick) plus a `DecayEdgePheromonePhase` (added to the periodic OneirosWorker tick).
- PHX-0058 will add a `BlindSpotAggregationPhase` (typically infrequent — perhaps via `enabled_phases` opt-in only on dedicated audit ticks).
- PHX-0059 will add a `MorpheusAssociatorPhase`.
- PHX-0060 will add a `ReclusterPhase` (also infrequent — monthly default).

Each of those is one more entry in `DEFAULT_PHASE_REGISTRY` and one more class in `tick_phases.py` (or its own module if the phase is large enough). The pipeline scales without `_tick` ever growing again.
