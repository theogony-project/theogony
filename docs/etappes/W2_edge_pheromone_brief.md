# W2 — Edge-Pheromone trails + Slow-Path emancipation (PHX-0057 Phase 1)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-22  
**Branch:** new branch off `main`, e.g. `feat/w2-edge-pheromone`  
**Scope:** one PR  
**Predecessor:** Phase 0 closed by F1 (PR #46) + F2 (PR #49) + F3 (PR #50). W1 closed by PR #52. W2 is the **second sprint of Wave 1**.

Direct brief, no Daedalus. Five design knobs are pre-locked below — your job is execution discipline.

---

## Why this etappe exists

Today's pheromone signal is **node-level only**: `RelevanceTracker.bump_all` raises `relevance` and `last_accessed` on every cited *node* by δ=0.05 per retrieval. Three structural gaps relative to the user's "Ameisenstraße" framing (PHX-0057):

1. **Edges are not strengthened.** When an answer travels through path A → B → C, today only nodes A, B, C receive a bump. The edges (A,B) and (B,C) — the actual conduit the next query will follow — keep their original weight. The trail is invisible to the graph itself.
2. **No symmetric edge decay.** Nodes have `freshness` that decays with idle days. Edges have no analogous erosion. Without it, the first successes become permanent autobahns — concept lock-in by attention bias.
3. **No Slow-Path emancipation.** `pheromone_mode` is reserved on `RetrievalBudget` (F3) but no strategy honours it. Without resistance, "deliberate reasoning" reduces to "the same well-trodden path with more LLM tokens" — exactly what cognitive bias-correction should prevent.

W2 ships Phase 1 of all three:

- A `pheromone_delta: float` + `last_traversed: datetime | None` on every `KnowledgeEdge`. The original `weight` stays sacred ("baseline"); the delta is what mutates.
- A new `EdgePheromoneTracker` (mirrors `RelevanceTracker`): bumps each cited path edge's delta by a small amount and stamps `last_traversed`.
- A new default-off `PheromoneDecayPhase` for `OneirosWorker` that pulls aged deltas back toward 0.
- The three existing `RetrievalStrategy` implementations honour `pheromone_mode`: `follow` reads `weight + delta`, `ignore` reads `weight`, `invert` reads `weight - delta`.
- The `QueryPipeline` calls `EdgePheromoneTracker.bump_all` in parallel with the existing `RelevanceTracker.bump_all`, **but only when the query ran in `follow` mode** — Slow-Path queries are read-only on the pheromone signal.

---

## Pre-decided design knobs (locked 2026-04-22)

The PHX-0057 YAML left several decisions open. They are closed here:

### Knob 1 — Schema: `pheromone_delta` (NOT `weight_baseline`)

Add two fields to `KnowledgeEdge`:

- `pheromone_delta: float = Field(default=0.0, ge=-1.0, le=1.0)` — signed delta on top of the baseline weight. Mutated by `EdgePheromoneTracker.bump` and `PheromoneDecayPhase.run`.
- `last_traversed: datetime | None = Field(default=None)` — last time this edge was on a cited path. Read by `PheromoneDecayPhase`.

Rationale (vs. the YAML's alternative `weight_baseline` companion):

- No data migration: the existing `weight` stays the baseline. Old edges automatically have `pheromone_delta = 0.0` (default), `last_traversed = None`.
- One mutation surface: `pheromone_delta` is the only field that pheromone code writes. `weight` is treated as immutable post-extraction (matches its current semantics — extraction sets it once).
- `pheromone_mode` semantics are crisp:
  - `follow`: `effective_weight = clamp(weight + pheromone_delta, 0, 1)`
  - `ignore`: `effective_weight = weight` (the pre-pheromone baseline)
  - `invert`: `effective_weight = clamp(weight - pheromone_delta, 0, 1)`
- Decay equilibrium is `0` (delta returns to neutral), not `0.5`. This is mathematically simpler than the YAML's "pull weight toward 0.5" framing and avoids the edge case where a baseline-weak edge (`weight=0.2`) gets *strengthened* by decay pulling it up to 0.5.

### Knob 2 — Cited-edge derivation: from `cited_node_ids` ∩ constellation edges

The PHX-0057 YAML says "the literal sequence of edges that the constellation traversed to ground a citation". Phase 1 derives this without changing the synthesizer:

```python
def derive_cited_edge_ids(
    constellation: Constellation,
    cited_node_ids: Sequence[str],
) -> list[str]:
    """Edges in the constellation whose BOTH endpoints were cited.

    Approximation of "the path the answer travelled". Misses edges
    that were traversed but whose endpoints did not survive citation
    selection (the LLM dropped one endpoint). Phase 2 may extend the
    synthesizer to cite edges directly; Phase 1 ships the
    derivation.
    """
    cited = set(cited_node_ids)
    return [
        edge_id_for(e)
        for e in constellation.edges
        if e.source_id in cited and e.target_id in cited
    ]
```

`Constellation` already exposes `ConstellationEdge.source_id` / `target_id` but not `edge_id`. `ConstellationEdge` is a slim projection — we need the full edge id to bump. Add `edge_id: str` to `ConstellationEdge` (mirroring `id` on `KnowledgeEdge`); `from_knowledge_edge` populates it. Downstream consumers ignore the new field.

### Knob 3 — Bump skip on non-`follow` queries

Slow-Path queries (`pheromone_mode != "follow"`) **must not** strengthen the pheromone they were trying to escape. The `QueryPipeline` reads the per-call `pheromone_mode` and skips the edge bump (and arguably the node bump too — see below).

Concretely: extend `QueryPipeline.ask` with `pheromone_mode: Literal["follow","ignore","invert"] = "follow"`. Pass through to the strategy via `RetrievalBudget`. Skip both pheromone tracking AND relevance tracking when the mode is not `"follow"`. (Relevance bumping is also a form of attention reinforcement; Slow-Path is a read-only audit, not a write-back.)

This is a deliberate choice — there is a defensible counter-position ("relevance is about node-level usefulness, not pheromone, so it should always bump"). Phase 2 may split the two switches if measured behaviour calls for it. Phase 1 keeps them together for simplicity and a clean "Slow-Path = pure audit" mental model.

### Knob 4 — Decay mechanics: aged-only, multiplicative toward 0

`PheromoneDecayPhase` runs once per OneirosWorker tick (when enabled). Algorithm:

```python
async def run(self, ctx: TickContext) -> None:
    cfg = ctx.cfg.edge_pheromone  # NEW: see Settings section
    horizon = ctx.started_at - timedelta(days=cfg.decay_horizon_days)

    # Single store call: yields edges where last_traversed < horizon
    # AND |pheromone_delta| > epsilon. The store skips zero-delta edges
    # so we don't pay write amplification on the cold majority.
    aged = await ctx.store.list_aged_pheromone_edges(
        horizon=horizon, epsilon=cfg.decay_epsilon
    )

    updates: list[tuple[str, float]] = []
    for edge_id, current_delta in aged:
        new_delta = current_delta * (1.0 - cfg.decay_rate)
        # Snap to 0 once below epsilon — avoids infinite asymptotic
        # tail and lets the store skip the same edge next tick.
        if abs(new_delta) < cfg.decay_epsilon:
            new_delta = 0.0
        updates.append((edge_id, new_delta))

    if updates:
        await ctx.store.batch_update_pheromone_deltas(updates)

    ctx.extras["pheromone_decay"] = {
        "edges_decayed": len(updates),
        "horizon_days": cfg.decay_horizon_days,
        "decay_rate": cfg.decay_rate,
    }
```

- `decay_rate = 0.05` (5 % per tick, multiplicative). With default tick interval 60 s, an edge with delta = 0.20 reaches the epsilon floor in ~ (log(epsilon/0.20) / log(0.95)) ticks. For epsilon = 0.001, that is ~103 ticks ≈ 100 minutes once decay kicks in.
- `decay_horizon_days = 30` — only edges idle for >30 days decay. Active edges keep their full delta.
- `decay_epsilon = 0.001` — write-amplification floor. Below this, snap to 0 and stop writing.
- `equilibrium = 0` is implicit (delta returns to neutral).

### Knob 5 — Default-off + opt-in path

`PheromoneDecayPhase` is **not** in `OneirosSettings.enabled_phases` default — operators opt in. `EdgePheromoneTracker.bump_all` IS called by default on every successful `follow`-mode query (matching the existing `RelevanceTracker.bump_all` pattern; users who want zero pheromone can set `Settings.relevance.edge_pheromone_delta = 0.0`).

This asymmetry is intentional: the bump is **local** (one query, a handful of edges, sub-millisecond) and tightly bounded; the decay is **global** (a sweep over the whole edge table) and benefits from operator awareness before being turned on.

---

## Goal

After this PR:

- `KnowledgeEdge` carries `pheromone_delta: float` + `last_traversed: datetime | None`. Both backends round-trip them.
- `ConstellationEdge` exposes `edge_id: str` (so `QueryPipeline` can derive cited edges from the assembled constellation without a second store round-trip).
- `KnowledgeStore` Protocol gains:
  - `batch_bump_edges(edge_ids: Sequence[str], *, delta: float, ts: datetime) -> None` — atomic delta bump + `last_traversed` stamp on a batch of edges.
  - `list_aged_pheromone_edges(*, horizon: datetime, epsilon: float) -> list[tuple[str, float]]` — async iterator of `(edge_id, current_delta)` for decay-eligible edges.
  - `batch_update_pheromone_deltas(updates: Sequence[tuple[str, float]]) -> None` — write back the decayed deltas.
- New module `src/theogony/memory/edge_pheromone.py` defines `EdgePheromoneTracker`.
- New module `src/theogony/memory/pheromone_decay_phase.py` defines `PheromoneDecayPhase`.
- `OneirosWorker.DEFAULT_PHASE_REGISTRY` registers `pheromone_decay` (off by default).
- `Settings.relevance.edge_pheromone_delta: float = 0.015` (the new bump δ for edges).
- `Settings.oneiros.edge_pheromone` group: `decay_horizon_days`, `decay_rate`, `decay_epsilon`.
- The three existing `RetrievalStrategy` implementations (`FixedDepthStrategy`, `EdgeProductBreadthFirstStrategy`, `ClusterNarrowingRetrievalStrategy`) honour `RetrievalBudget.pheromone_mode`. `cluster_narrow` simply forwards the mode to its inner strategy.
- `QueryPipeline.ask` accepts `pheromone_mode`, plumbs it through to the strategy via the budget, and skips the post-answer bump (both edge and node) when the mode is not `"follow"`.
- The CLI `theogony ask` and the API `POST /query` accept the new `--pheromone-mode` / `pheromone_mode` field.
- New `tests/test_edge_pheromone_tracker.py`, `tests/test_pheromone_decay_phase.py`, and `tests/test_pheromone_modes.py` cover the contracts. The "follow vs invert returns different constellations after 100 bumps" Slow-Path test from PHX-0057 lives in `tests/test_pheromone_modes.py`.
- New short `docs/PHEROMONE.md` documents the principle (trails strengthen the graph; Slow-Path is allowed to walk against them).

---

## Scope decisions (read first)

### 1. The `EdgePheromoneTracker`

Mirror of `RelevanceTracker` for edges. Lives at `src/theogony/memory/edge_pheromone.py`.

```python
DEFAULT_EDGE_PHEROMONE_DELTA = 0.015


class EdgePheromoneTracker:
    """Apply the pheromone bump for cited edges (PHX-0057 Phase 1)."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        delta: float = DEFAULT_EDGE_PHEROMONE_DELTA,
    ) -> None:
        if not 0.0 <= delta <= 1.0:
            raise ValueError(f"delta must be in [0,1]; got {delta}")
        self._store = store
        self._delta = delta

    async def bump_all(self, edge_ids: Iterable[str]) -> None:
        """Bump every distinct edge id once (preserving first-seen order).

        Dedupe matches RelevanceTracker.bump_all semantics: an answer
        that traverses the same edge twice (cycle) bumps it once.
        """
        seen: set[str] = set()
        ordered: list[str] = []
        for eid in edge_ids:
            if eid in seen:
                continue
            seen.add(eid)
            ordered.append(eid)
        if not ordered:
            return
        await self._store.batch_bump_edges(
            ordered, delta=self._delta, ts=datetime.now(UTC)
        )
```

`batch_bump_edges` is a single store call (vs. `RelevanceTracker.bump_all`'s per-id round-trip). Edge count per query is small (≤ ~50 with default budget); a batch-aware tracker is the cleaner shape from day one because the decay phase needs the same kind of bulk-write discipline.

### 2. The `PheromoneDecayPhase`

Per Knob 4 above. Lives at `src/theogony/memory/pheromone_decay_phase.py`.

```python
class PheromoneDecayPhase:
    name = "pheromone_decay"

    async def run(self, ctx: TickContext) -> None:
        # Implementation per Knob 4. Honour ctx.cfg.edge_pheromone.
        # Stash a small dict in ctx.extras["pheromone_decay"] for
        # observability (mirrors W1's ctx.extras["clustering_run"]
        # pattern). The OneirosTickReport does not get a new field
        # in W2 — the extras dict is enough for inspection via the
        # OneirosWorker's debug logging in W2.
        ...
```

The phase is small (~50 lines including helpers). Keep it private to the module.

### 3. `KnowledgeStore` Protocol additions

Three new methods. Both backends implement.

```python
async def batch_bump_edges(
    self,
    edge_ids: Sequence[str],
    *,
    delta: float,
    ts: datetime,
) -> None:
    """Add `delta` to each edge's pheromone_delta and set last_traversed=ts.

    Per-edge clamp to [-1.0, 1.0]. Nonexistent edge ids are silent
    no-ops (matches the existing batch_update_scores semantics for
    nodes). Single round-trip on Neo4j (UNWIND); single dict pass
    on the in-memory store.
    """
    ...


async def list_aged_pheromone_edges(
    self,
    *,
    horizon: datetime,
    epsilon: float,
) -> list[tuple[str, float]]:
    """Edges where last_traversed < horizon AND |pheromone_delta| > epsilon.

    Returns (edge_id, current_pheromone_delta) tuples. Caller (the
    PheromoneDecayPhase) computes the new delta and writes back via
    batch_update_pheromone_deltas. Two-step pattern (read aged →
    compute → write) keeps the math out of Cypher.
    """
    ...


async def batch_update_pheromone_deltas(
    self,
    updates: Sequence[tuple[str, float]],
) -> None:
    """Set pheromone_delta to the supplied value for each (edge_id, delta).

    Does NOT touch last_traversed (decay is not a traversal). Single
    round-trip on Neo4j (UNWIND); per-id dict update on the in-memory
    store.
    """
    ...
```

Neo4j Cypher sketch (verified shapes; the executor agent writes the precise queries):

```cypher
// batch_bump_edges
UNWIND $rows AS row
MATCH ()-[r:RELATES {id: row.edge_id}]->()
SET r.pheromone_delta = CASE
        WHEN r.pheromone_delta + $delta > 1.0 THEN 1.0
        WHEN r.pheromone_delta + $delta < -1.0 THEN -1.0
        ELSE r.pheromone_delta + $delta
      END,
    r.last_traversed = $ts

// list_aged_pheromone_edges
MATCH ()-[r:RELATES]->()
WHERE r.last_traversed IS NOT NULL
  AND r.last_traversed < $horizon
  AND abs(r.pheromone_delta) > $epsilon
RETURN r.id AS id, r.pheromone_delta AS delta

// batch_update_pheromone_deltas
UNWIND $rows AS row
MATCH ()-[r:RELATES {id: row.edge_id}]->()
SET r.pheromone_delta = row.new_delta
```

Add a Neo4j BTREE index on `r.last_traversed` in `_schema.py` — without it the decay query is a full edge scan.

### 4. `pheromone_mode` honoring in retrieval strategies

Each strategy reads `budget.pheromone_mode` and computes the `effective_weight` from the edge:

```python
def effective_weight(edge: KnowledgeEdge | ConstellationEdge, mode: str) -> float:
    """Compute the pheromone-mode-aware weight."""
    delta = getattr(edge, "pheromone_delta", 0.0)  # Constellation slim form has no delta
    base = edge.weight
    if mode == "follow":
        return max(0.0, min(1.0, base + delta))
    if mode == "ignore":
        return base
    if mode == "invert":
        return max(0.0, min(1.0, base - delta))
    raise ValueError(f"unknown pheromone_mode: {mode}")
```

Live this helper in `src/theogony/retrieval/strategies/pheromone.py` — shared by all three strategies.

The strategies' weight checks change as follows:

- `FixedDepthStrategy`: pre-W2 delegates to `store.multi_hop_search`, which reads `weight` directly. The store's `multi_hop_search` does not currently know about pheromone_delta. The cheapest path: extend `multi_hop_search` with a `pheromone_mode: str = "follow"` keyword and have the store apply the effective_weight inside its own filter. The Cypher equivalent of the helper above is one CASE expression.
- `EdgeProductBreadthFirstStrategy`: walks via `store.get_neighborhood` and computes path products in Python. Apply `effective_weight(edge, mode)` instead of `edge.weight` when computing the product and when checking against `budget.min_edge_weight`.
- `ClusterNarrowingRetrievalStrategy`: pure facade — inner strategy receives the budget unchanged.

The store-level `pheromone_mode` parameter is the only way to keep `FixedDepthStrategy` byte-identical in the `follow` path. With `delta = 0.0` everywhere on a cold-start corpus, all three modes return identical results. The regression tests stay green.

### 5. `QueryPipeline` plumbing

Extend `QueryPipeline.ask`:

```python
async def ask(
    self,
    query: str,
    *,
    layer: Layer | None = None,
    k: int = 10,
    hops: int = 2,
    strategy: Literal["fixed_depth", "edge_product", "cluster_narrow"] | None = None,
    pheromone_mode: Literal["follow", "ignore", "invert"] = "follow",
) -> QueryResult:
    ...
```

Two integration points:

1. After step 2 (retrieve), construct the budget with `pheromone_mode` and pass it to the strategy. Today the budget is constructed inside `MultiHopRetriever.retrieve` from the legacy `(k, hops, min_weight)` triple — extend that signature with a fourth keyword `pheromone_mode` so the caller can override.
2. After step 7 (relevance bump), only run the bumps when `pheromone_mode == "follow"`. Concretely:

```python
# ---- 7. write-back (only on follow-mode queries)
if pheromone_mode == "follow":
    cited_edge_ids = derive_cited_edge_ids(constellation, answer.cited_node_ids)
    await asyncio.gather(
        self._relevance.bump_all(answer.cited_node_ids),
        self._edge_pheromone.bump_all(cited_edge_ids),
    )
```

Add `edge_pheromone: EdgePheromoneTracker` to `QueryPipeline.__init__`. Wire it in `api/app.py` lifespan.

### 6. CLI + API

- `theogony ask` gains `--pheromone-mode` (Literal). Default `follow`.
- `POST /query` request body gains optional `pheromone_mode`. Default `follow`. The DTO Literal mirrors the budget Literal.
- `pantheon_ask` MCP tool gains the same field with the same default.

### 7. Settings

```python
class EdgePheromoneSettings(BaseModel):
    """OneirosWorker tunables for the PheromoneDecayPhase (PHX-0057 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    decay_horizon_days: float = Field(default=30.0, ge=0.0)
    decay_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    decay_epsilon: float = Field(default=0.001, ge=0.0, le=1.0)
```

Wire into `OneirosSettings` as `edge_pheromone: EdgePheromoneSettings = Field(default_factory=EdgePheromoneSettings)`.

Extend `RelevanceSettings` (or wherever the existing `RelevanceTracker.delta` lives) with `edge_pheromone_delta: float = Field(default=0.015, ge=0.0, le=1.0)`. If a dedicated `RelevanceSettings` group does not exist yet, create one — keep it small.

The `OneirosSettings.enabled_phases` default is **unchanged** (does not include `"pheromone_decay"`).

---

## Implementation plan (file-by-file)

### `src/theogony/memory/edge_pheromone.py` (new)

`EdgePheromoneTracker` per Scope decision 1. ~60 lines including docstring.

### `src/theogony/memory/pheromone_decay_phase.py` (new)

`PheromoneDecayPhase` per Scope decision 2 + Knob 4. ~80 lines including helpers and docstring.

### `src/theogony/retrieval/strategies/pheromone.py` (new)

`effective_weight` helper per Scope decision 4. ~30 lines.

### `src/theogony/core/model.py`

Add `pheromone_delta: float = Field(default=0.0, ge=-1.0, le=1.0, description="...")` and `last_traversed: datetime | None = Field(default=None, description="...")` to `KnowledgeEdge`. Add `edge_id: str` to `ConstellationEdge`; update `from_knowledge_edge` to populate it.

### `src/theogony/core/store.py`

Add the three new methods (`batch_bump_edges`, `list_aged_pheromone_edges`, `batch_update_pheromone_deltas`) per Scope decision 3. Extend `multi_hop_search` signature with `pheromone_mode: str = "follow"`.

### `src/theogony/stores/memory.py`

Implement the three new methods. Update `multi_hop_search` to honour `pheromone_mode` via the helper. Update `_edges` round-tripping to include `pheromone_delta` and `last_traversed`.

### `src/theogony/stores/neo4j_store.py`

Implement the three new methods per the Cypher sketches in Scope decision 3. Update `_edge_to_props` and `_edge_from_props` to include the two new fields. Update `multi_hop_search` Cypher with the `pheromone_mode` CASE expression on the weight check.

### `src/theogony/stores/_schema.py`

Add `BTREE INDEX FOR ()-[r:RELATES]-() ON (r.last_traversed)` in the Neo4j init path. Without it, the decay query is a full edge scan.

### `src/theogony/config/settings.py`

Add `EdgePheromoneSettings` per Scope decision 7. Wire into `OneirosSettings`. Add `edge_pheromone_delta` to `RelevanceSettings` (creating it if needed).

### `src/theogony/memory/oneiros.py`

Register `"pheromone_decay": PheromoneDecayPhase` in `DEFAULT_PHASE_REGISTRY`. The `enabled_phases` default does NOT include it.

### `src/theogony/retrieval/strategies/fixed_depth.py`

Add `pheromone_mode` to `RetrievalBudget` consumption — pass through to `store.multi_hop_search`.

### `src/theogony/retrieval/strategies/edge_product.py`

Use `effective_weight(edge, budget.pheromone_mode)` in the path-product computation and the `min_edge_weight` filter.

### `src/theogony/retrieval/strategies/cluster_narrowing.py`

No code change to weight handling (pure facade). Confirm the budget is passed through unchanged.

### `src/theogony/retrieval/multi_hop.py`

Extend `MultiHopRetriever.retrieve` with `pheromone_mode` keyword. Default `"follow"` for backward compatibility. Plumb into the budget.

### `src/theogony/retrieval/pipeline.py`

Per Scope decision 5: add `pheromone_mode` to `ask`, construct the strategy with it, gather the two bumps when `follow`, skip both when not.

Add `edge_pheromone: EdgePheromoneTracker` to `__init__`.

### `src/theogony/api/dependencies.py`

Construct `EdgePheromoneTracker(store, delta=settings.relevance.edge_pheromone_delta)` and pass to `QueryPipeline`.

### `src/theogony/api/app.py`

Lifespan: instantiate the tracker, pass into the pipeline.

### `src/theogony/api/dto.py`

Add `pheromone_mode: Literal["follow", "ignore", "invert"] = "follow"` to `QueryRequest`.

### `src/theogony/api/routes/query.py`

Forward the new field.

### `src/theogony/cli.py`

Add `--pheromone-mode` to `theogony ask`.

### `src/theogony/mcp/server.py`

Add `pheromone_mode` to the `pantheon_ask` input schema; default `"follow"`. Plumb to the pipeline.

### `tests/test_edge_pheromone_tracker.py` (new)

- `test_bump_all_dedupes_within_call` (cycle-cited edge bumps once).
- `test_bump_all_clamps_to_one`.
- `test_bump_all_silent_no_op_on_unknown_edge_id`.
- `test_bump_all_stamps_last_traversed_to_now` (frozen time fixture).
- `test_default_delta_matches_settings`.

### `tests/test_pheromone_decay_phase.py` (new)

- `test_decay_phase_skips_edges_within_horizon`.
- `test_decay_phase_pulls_aged_delta_toward_zero`.
- `test_decay_phase_snaps_to_zero_below_epsilon`.
- `test_decay_phase_does_not_touch_zero_delta_edges` (write-amplification floor).
- `test_decay_phase_respects_clamp_on_negative_deltas`.
- `test_decay_phase_writes_observability_to_ctx_extras`.

### `tests/test_pheromone_modes.py` (new — the high-value Slow-Path gate)

- `test_follow_uses_observed_weight`.
- `test_ignore_uses_baseline_weight`.
- `test_invert_uses_baseline_minus_delta`.
- `test_invert_returns_different_constellation_after_100_bumps` — the PHX-0057 acceptance criterion. Setup: a 5-node line graph with one path bumped 100 times. Assert `follow` returns the bumped path; `invert` surfaces a previously-neglected sibling.
- `test_query_pipeline_skips_bumps_when_mode_is_not_follow` (assert via spy on the trackers).

### `tests/test_pheromone_pipeline_integration.py` (new — small integration)

- `test_ask_with_follow_mode_bumps_cited_edges` — issue one ask against the in-memory store, assert the cited edges' pheromone_delta moved by exactly the configured δ.
- `test_ask_with_ignore_mode_does_not_bump_anything`.

### Documentation touches

1. `docs/PHEROMONE.md` (new, ~120 lines): documents the principle, the three modes, the schema (`pheromone_delta`, `last_traversed`), the bump path (`EdgePheromoneTracker`), the decay path (`PheromoneDecayPhase`), the Slow-Path emancipation contract, and a short "Phase 2 / open questions" section listing: per-cluster pheromone spaces (PHX-0060 Phase 2), LLM-cited edges (synthesizer extension), differential bump for high-confidence vs low-confidence edges, anomaly detection on pheromone autobahns (Nemesis territory).

2. `docs/CHRONICLE_PRINCIPLES.md` — add a one-liner to the existing principles list: "Trails strengthen the graph; Slow-Path is allowed to walk against them."

3. `docs/PHOENIX_BACKLOG.md` PHX-0057 catalogue entry: append `"Phase 1 closed by W2 (PR #...): pheromone_delta + last_traversed schema, EdgePheromoneTracker, PheromoneDecayPhase (default-off), pheromone_mode honoring in fixed_depth/edge_product/cluster_narrow, QueryPipeline plumbing. Phase 2 sub-tickets: per-cluster pheromone spaces, LLM-cited edges, differential bump."`

4. `docs/ARCHITECTURE.md` — short paragraph in the Memory section announcing the pheromone bump-and-decay loop. Cross-reference `docs/PHEROMONE.md`.

5. `docs/RETRIEVAL_STRATEGIES.md` — short section on `pheromone_mode`, the three values, and the "Slow-Path = read-only" contract.

---

## Cost-benefit considerations

**Token cost**: smaller than W1. Composer adds two new memory modules, three store methods (with both backends), schema/property fields, plumbing through three strategies + pipeline + CLI + API + MCP, and ~22 new tests. Estimate ≤ €0.80 of Composer execution.

**Runtime cost**:

- Default `follow` path adds **one extra batch store call per query** (`batch_bump_edges`). Expected ~50 µs in-memory, ~5 ms on Neo4j (UNWIND on a few-element list). Both well below the 2 s p95 budget.
- `PheromoneDecayPhase` is **default-off**. When enabled, the cost is one indexed Cypher query per tick (with the new `last_traversed` BTREE index, this is sub-100 ms even at 100 k edges) plus an UNWIND write of the aged set. Operators turn it on with eyes open.
- `pheromone_mode != "follow"` queries skip both write-backs — they are **cheaper** than `follow` queries, not more expensive. Slow-Path is therefore a free observability mode for "what would the system have answered without the accumulated bias?"

**Test cost**: ~22 new tests; estimated ~1 s wall-clock added.

**Failure modes worth watching**:

- **Schema-missing field on round-trip**: old in-memory dumps and old Neo4j data have neither `pheromone_delta` nor `last_traversed`. Pydantic defaults handle the read; the Neo4j `_edge_from_props` must use `.get(..., default)` rather than direct dict access.
- **`last_traversed` index missing on Neo4j**: the decay query becomes a full edge scan and is the whole tick budget. The `_schema.py` change is non-optional.
- **Bump amplification on cycles**: the dedupe in `EdgePheromoneTracker.bump_all` is the only line preventing a cycle-cited edge from being bumped twice. Test it explicitly.
- **Invert clamp**: `weight - delta` can underflow to negative; clamp to 0. The unit test `test_invert_uses_baseline_minus_delta` covers this.
- **`pheromone_mode` plumbing leak**: if the QueryPipeline forgets to pass `pheromone_mode` into the budget, the default `"follow"` always wins — tests pass but the `--pheromone-mode invert` flag does nothing user-visible. The integration test `test_invert_returns_different_constellation_after_100_bumps` is the canary.

---

## Out of scope (do not do)

- **Do not** change the synthesizer to cite edges directly. Phase 1 derives cited edges from `cited_node_ids` ∩ constellation. A future ticket may extend the synthesis contract.
- **Do not** make the pheromone bump per-cluster (one delta per cluster). That is a PHX-0060 Phase 2 follow-up.
- **Do not** add a `bridge_score` for cross-cluster edges. That is a PHX-0060 Phase 2 follow-up paired with PHX-0059.
- **Do not** add anomaly detection on pheromone autobahns. That is Nemesis territory (PHX-0068).
- **Do not** add a separate `node_pheromone_mode` switch. Phase 1 ties the node and edge bumps together (skip both when `pheromone_mode != "follow"`). Splitting them is a Phase 2 sub-ticket if measured behaviour calls for it.
- **Do not** add a `pheromone_decay` field to `OneirosTickReport`. The `ctx.extras["pheromone_decay"]` payload + worker debug logging is the Phase 1 observability surface.
- **Do not** change the `MultiHopResult` shape. The pheromone signal lives on the edges themselves; the result type stays as it is.

---

## Done when

- [ ] `KnowledgeEdge.pheromone_delta` and `KnowledgeEdge.last_traversed` exist; both backends round-trip them.
- [ ] `ConstellationEdge.edge_id` exists; `from_knowledge_edge` populates it.
- [ ] `KnowledgeStore` Protocol gains `batch_bump_edges`, `list_aged_pheromone_edges`, `batch_update_pheromone_deltas`; both backends implement them.
- [ ] `multi_hop_search` accepts `pheromone_mode`; both backends honour it.
- [ ] `src/theogony/memory/edge_pheromone.py` and `src/theogony/memory/pheromone_decay_phase.py` exist.
- [ ] `src/theogony/retrieval/strategies/pheromone.py` (the `effective_weight` helper) exists.
- [ ] `OneirosWorker.DEFAULT_PHASE_REGISTRY` includes `"pheromone_decay"`. `OneirosSettings.enabled_phases` default does **not** include it.
- [ ] `Settings.oneiros.edge_pheromone` group exists with the three knobs.
- [ ] `Settings.relevance.edge_pheromone_delta` exists.
- [ ] `QueryPipeline.ask` accepts `pheromone_mode`; the bump runs only on `follow`.
- [ ] `QueryPipeline.__init__` accepts `edge_pheromone: EdgePheromoneTracker`; `api/app.py` lifespan wires it.
- [ ] `theogony ask --pheromone-mode invert "<question>"` works.
- [ ] `POST /query` accepts `pheromone_mode`.
- [ ] `pantheon_ask` MCP tool accepts `pheromone_mode`.
- [ ] All existing tests stay green without modification (full `pytest -q`).
- [ ] New tests cover the four new test files; all green.
- [ ] `tests/test_pheromone_modes.py::test_invert_returns_different_constellation_after_100_bumps` is the high-value Slow-Path gate; it must pass.
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy` clean (strict) on the new modules.
- [ ] `docs/PHEROMONE.md` exists.
- [ ] `docs/CHRONICLE_PRINCIPLES.md`, `docs/ARCHITECTURE.md`, `docs/RETRIEVAL_STRATEGIES.md`, `docs/PHOENIX_BACKLOG.md` updated.
- [ ] PR title: `feat(memory): W2 — Edge-Pheromone trails + Slow-Path emancipation (PHX-0057 Phase 1)`. PR body lists the five resolved knobs, confirms zero default-path behaviour change on cold-start corpora (delta=0 everywhere → all three modes return identical results), and includes the result of the 100-bump Slow-Path test.

---

## After this PR

W2 closes PHX-0057 Phase 1 and unlocks the rest of Wave 1:

- **W3 — PHX-0058 Aggregated Stub Detection**: per-cluster blind-spot statistics. Now that pheromone trails exist, a heat-map of "queries hit dead-ends here" composes naturally with the pheromone heat-map.
- **W4 — PHX-0059 Morpheus-as-Associator**: the dreamer needs to know which edges are "fresh discovery candidates" vs "well-trodden trails". The `pheromone_delta` field gives that signal directly.

Wave 1 finishes when W4 lands. After Wave 1, the substrate has: clusters (W1), pheromones (W2), stubs (W3), an active dreamer (W4) — the operational shape PHX-0061 (federation), PHX-0062 (negative knowledge), and PHX-0063+ build on top of.
