# F3 — RetrievalStrategy Protocol skeleton (PHX-0056 Phase 1)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-21  
**Branch:** new branch off `main`, e.g. `feat/f3-retrieval-strategy`  
**Scope:** one PR, tightly scoped  
**Predecessor:** F1 (PR #46) and F2 (the TickPhase brief) merged. F3 is the **third and final sprint of the architecture-audit Phase 0**.

Direct brief, no Daedalus. The Protocol shape, the budget shape, and the second concrete strategy are spec'd here verbatim — your job is execution discipline.

---

## Why this etappe exists

`MultiHopRetriever.retrieve` is a single method with a single way to navigate the chronicle:

```python
async def retrieve(
    self,
    query_embedding: list[float],
    *,
    k: int = 10,
    hops: int = 2,
    min_weight: float = 0.3,
    layer: Layer | None = None,
) -> MultiHopResult: ...
```

Vector seed → fixed-depth hop expansion → min-weight filter → dedupe → top-k. Plan §4.2 defaults.

Looking forward, four already-filed tickets need different retrieval strategies:

- **PHX-0056 Phase 2+** — three concrete strategies named in the YAML: `EdgeProductBreadthFirst` (path-product threshold + top-N best paths), `VectorSimilarityBreadthFirst` (continuous vector-steered walk), `LLMHeuristicGuided` (Slow-Path with token budget).
- **PHX-0057** — Slow-Path emancipation needs `RetrievalBudget.pheromone_mode = follow|ignore|invert`. Cannot land without a `RetrievalBudget` shape that strategies consult.
- **PHX-0060** — `ClusterNarrowingRetrievalStrategy` needs to be a first-class plug-in strategy.
- **PHX-0061** — Federation routing operates one tier above the retrieval strategy and depends on the same Strategy Protocol existing.

Without F3, every one of those tickets either reinvents the dispatch shape or quietly forks `MultiHopRetriever` into a parallel implementation. Both compound complexity.

**F3 introduces the `RetrievalStrategy` Protocol and the `RetrievalBudget` model.** Today's behaviour becomes the default `FixedDepthStrategy`. One second concrete strategy (`EdgeProductBreadthFirstStrategy`) ships alongside to prove the abstraction holds. The remaining strategies named in PHX-0056 are deferred to Phase 2.

This is the foundation refactoring PHX-0056 / 0057 / 0060 / 0061 build on top of. Land it before any of them are picked up.

---

## Goal

After this PR:

- `src/theogony/retrieval/strategies/` (new subpackage) defines the `RetrievalStrategy` Protocol and the `RetrievalBudget` Pydantic model.
- `FixedDepthStrategy` lives in `src/theogony/retrieval/strategies/fixed_depth.py` and preserves today's `MultiHopRetriever` behaviour byte-for-byte.
- `EdgeProductBreadthFirstStrategy` lives in `src/theogony/retrieval/strategies/edge_product.py` and proves the abstraction with a meaningfully different traversal pattern.
- `MultiHopRetriever` becomes a thin facade that holds a default `RetrievalStrategy` and dispatches to it.
- `QueryPipeline` accepts a `RetrievalStrategy` injection (default = `FixedDepthStrategy()`).
- `Settings.retrieval` group exists with `strategy: Literal["fixed_depth", "edge_product"]` (default `"fixed_depth"`).
- The CLI `theogony ask` and the API `POST /query` both accept an optional `--strategy` / `strategy` field.
- `tests/test_retrieval_pipeline.py` and `tests/test_retrieval_pipeline_neo4j_live.py` stay green without modification.
- New `tests/test_retrieval_strategies.py` covers the Protocol mechanics, the `FixedDepthStrategy` contract, and the `EdgeProductBreadthFirstStrategy` contract.
- Module docstrings + a new short `docs/RETRIEVAL_STRATEGIES.md` companion document explain the pattern and point at PHX-0056/0057/0060/0061 as the consumers.

---

## Scope decisions (read first)

### 1. The `RetrievalStrategy` Protocol

Pure async protocol, single method:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class RetrievalStrategy(Protocol):
    """One concrete retrieval strategy.

    Strategies receive a query embedding and a RetrievalBudget; they
    return a MultiHopResult. The store + the budget are the only
    dependencies — no LLM, no settings, no per-query state on the
    strategy itself. Implementations may carry construction-time
    configuration (e.g. an EdgeProductBreadthFirst's threshold);
    keep it on the instance, not on the call.
    """

    name: str  # short stable identifier; matches Settings.retrieval.strategy literal

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult: ...
```

`name` is a class attribute (parallel to `TickPhase.name` from F2).

### 2. The `RetrievalBudget` Pydantic model

This is the ticket on which all current and future strategies coordinate. Spec it once, well:

```python
class RetrievalBudget(BaseModel):
    """Per-call resource and parameter envelope for a RetrievalStrategy.

    A strategy MUST honour ``max_nodes`` and ``min_edge_weight`` —
    these are the universal floors. Other fields are optional hints
    that specific strategies may consult. Strategies SHOULD ignore
    fields they do not understand; they MUST NOT silently produce
    results that exceed an explicit cap.
    """

    model_config = ConfigDict(extra="forbid")

    # Universal: every strategy honours these.
    max_nodes: int = Field(default=10, ge=1, le=200)
    min_edge_weight: float = Field(default=0.3, ge=0.0, le=1.0)

    # FixedDepthStrategy honours these:
    hops: int = Field(default=2, ge=0, le=4)

    # EdgeProductBreadthFirstStrategy honours these:
    min_path_product: float | None = Field(default=None, ge=0.0, le=1.0)
    top_n_paths: int | None = Field(default=None, ge=1, le=200)

    # Reserved for PHX-0057 (Slow-Path emancipation) — strategy
    # implementations may already accept the field but the canonical
    # behaviour ships when PHX-0057 lands.
    pheromone_mode: Literal["follow", "ignore", "invert"] = "follow"

    # Reserved for PHX-0056 LLMHeuristicGuided strategy.
    token_cap: int | None = Field(default=None, ge=1)
    wall_clock_ms_cap: int | None = Field(default=None, ge=1)
```

The reserved fields (`pheromone_mode`, `token_cap`, `wall_clock_ms_cap`) ship in F3 even though no current strategy honours them — establishes the schema once so PHX-0057 etc. do not need to change `RetrievalBudget` again.

### 3. The default `FixedDepthStrategy`

Mechanical translation of today's `MultiHopRetriever.retrieve` behaviour. Same call to `store.multi_hop_search`, same defaults, same `MultiHopResult` shape:

```python
class FixedDepthStrategy:
    name = "fixed_depth"

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        started = time.perf_counter()
        scored = await self._store.multi_hop_search(
            embedding=embedding,
            k=budget.max_nodes,
            hops=budget.hops,
            min_weight=budget.min_edge_weight,
            layer=layer,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        seed_count = min(budget.max_nodes, len(scored))
        return MultiHopResult(
            scored_nodes=scored,
            seed_count=seed_count,
            nodes_per_hop=None,  # PHX-0051: store does not expose per-hop visibility
            final_node_count=len(scored),
            duplicates_removed=0,
            duration_ms=duration_ms,
        )
```

**The crucial regression contract**: when `MultiHopRetriever` (the facade — see Scope decision 5) is called with the legacy parameters, it produces a `MultiHopResult` byte-identical to today's. Run the existing `tests/test_retrieval_pipeline.py` and `tests/test_retrieval_pipeline_neo4j_live.py` as your gate.

### 4. The new `EdgeProductBreadthFirstStrategy`

Proves the abstraction is real, not just a one-strategy facade. The strategy does:

1. Vector-seed: `store.vector_search(embedding, k=budget.max_nodes, layer=layer)` — gets initial scored nodes.
2. Breadth-first walk from each seed: at each step, expand to neighbours via `store.get_neighborhood(node_id, depth=1, min_weight=budget.min_edge_weight)`. Track the running **path product** (multiply edge weights along the path).
3. Prune any path whose product falls below `budget.min_path_product` (when set).
4. After expansion, sort all discovered paths by accumulated weight, keep the top `budget.top_n_paths` (when set).
5. Deduplicate nodes across paths.
6. Return as `MultiHopResult` with `nodes_per_hop` populated (now we have hop-by-hop visibility, unlike `FixedDepthStrategy`).

```python
class EdgeProductBreadthFirstStrategy:
    name = "edge_product"

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        # Implementation per the six-step algorithm above.
        # Honour budget.min_path_product and budget.top_n_paths.
        # Return MultiHopResult with nodes_per_hop populated.
        ...
```

**Implementation notes**:

- `budget.hops` acts as the maximum depth (still capped at 4).
- When `budget.min_path_product` is `None`, no path-product pruning happens — the walk still completes, just without that filter.
- When `budget.top_n_paths` is `None`, all paths are returned (no top-N pruning).
- When **both** are `None`, the strategy degrades to a pure breadth-first walk capped by `budget.hops` and `budget.max_nodes` — a useful diagnostic mode.
- `nodes_per_hop` is the list `[count_at_hop_0, count_at_hop_1, ..., count_at_hop_n]` where hop 0 is the seed set.

### 5. `MultiHopRetriever` becomes a thin facade

The existing class stays for backward compatibility. It now holds a default strategy:

```python
class MultiHopRetriever:
    """Thin async facade over a RetrievalStrategy.

    Preserved for callers that constructed the original
    MultiHopRetriever shape directly. New code should construct
    a strategy and pass it to QueryPipeline.

    The default strategy is FixedDepthStrategy, which preserves
    Plan §4.2 behaviour byte-for-byte.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        strategy: RetrievalStrategy | None = None,
    ) -> None:
        self._store = store
        self._strategy = strategy if strategy is not None else FixedDepthStrategy(store)

    async def retrieve(
        self,
        query_embedding: list[float],
        *,
        k: int = 10,
        hops: int = 2,
        min_weight: float = 0.3,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        # Validate legacy args (preserves today's ValueError semantics).
        if k <= 0:
            raise ValueError(f"k must be positive; got {k}")
        if hops < 0:
            raise ValueError(f"hops must be non-negative; got {hops}")
        if not 0.0 <= min_weight <= 1.0:
            raise ValueError(f"min_weight must be in [0,1]; got {min_weight}")

        budget = RetrievalBudget(
            max_nodes=k,
            hops=hops,
            min_edge_weight=min_weight,
        )
        return await self._strategy.retrieve(query_embedding, budget=budget, layer=layer)
```

### 6. `QueryPipeline` accepts a `RetrievalStrategy` injection

Update `QueryPipeline.__init__` to take an optional `strategy: RetrievalStrategy | None`:

```python
def __init__(
    self,
    *,
    embedder: EmbeddingProvider,
    retriever: MultiHopRetriever,  # legacy keyword stays
    strategy: RetrievalStrategy | None = None,
    assembler: ConstellationAssembler,
    synthesizer: AnswerSynthesizer,
    relevance: RelevanceTracker,
    settings: Settings,
    report_writer: RunReportWriter,
) -> None:
    ...
    if strategy is not None:
        # New code path: caller injected an explicit strategy.
        self._retriever = MultiHopRetriever(retriever._store, strategy=strategy)
    else:
        self._retriever = retriever
```

Existing callers that pass only `retriever` keep working unchanged. New callers can pass `strategy=...`.

### 7. New `Settings.retrieval` group

```python
class RetrievalSettings(BaseModel):
    """Tunables for the retrieval stack (PHX-0056 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    strategy: Literal["fixed_depth", "edge_product"] = "fixed_depth"
    # Per-strategy defaults; strategies read these on construction.
    edge_product_min_path_product: float | None = Field(default=None, ge=0.0, le=1.0)
    edge_product_top_n_paths: int | None = Field(default=None, ge=1, le=200)
```

Wire `retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)` into the top-level `Settings` class.

### 8. CLI + API strategy selection

`theogony ask` gains an optional `--strategy` flag (Literal of strategy names; defaults to settings value).

`POST /query` request body gains an optional `strategy` field:

```python
class QueryRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=2000)
    layer: Layer | None = None
    k: int = Field(default=10, ge=1, le=50)
    hops: int = Field(default=2, ge=0, le=4)
    strategy: Literal["fixed_depth", "edge_product"] | None = None  # NEW
```

When the field is set, `get_query_pipeline` constructs the matching strategy and passes it. When unset, the settings default applies.

### 9. The `MultiHopResult` shape stays

Same fields, same JSON serialisation. The only change: `EdgeProductBreadthFirstStrategy` populates `nodes_per_hop` (which `FixedDepthStrategy` leaves as `None` per PHX-0051). Downstream consumers (the slim Constellation, the report writer) already handle `None`-or-list correctly.

---

## Implementation plan (file-by-file)

### `src/theogony/retrieval/strategies/__init__.py` (new)

Re-exports: `RetrievalStrategy`, `RetrievalBudget`, `FixedDepthStrategy`, `EdgeProductBreadthFirstStrategy`. Keep the public surface tight.

### `src/theogony/retrieval/strategies/protocol.py` (new)

The `RetrievalStrategy` Protocol + module docstring. Imports kept tight.

### `src/theogony/retrieval/strategies/budget.py` (new)

The `RetrievalBudget` Pydantic model + module docstring explaining which strategy honours which field.

### `src/theogony/retrieval/strategies/fixed_depth.py` (new)

The `FixedDepthStrategy` class. Roughly 50 lines. Mechanical extraction from today's `MultiHopRetriever.retrieve`.

### `src/theogony/retrieval/strategies/edge_product.py` (new)

The `EdgeProductBreadthFirstStrategy` class. Roughly 100–150 lines depending on how the breadth-first walk is structured. The implementation must:

- Use `asyncio.gather` for the parallel `get_neighborhood` calls per hop step (consistent with the project's async discipline).
- Cap at `budget.max_nodes` overall.
- Honour `budget.min_path_product` and `budget.top_n_paths` per Scope decision 4.
- Populate `nodes_per_hop` correctly.

### `src/theogony/retrieval/multi_hop.py`

Refactor `MultiHopRetriever` into the thin facade per Scope decision 5. The legacy validation checks (`k <= 0` etc.) stay on the facade. The actual retrieval delegates to the strategy. `MultiHopResult` stays in this module (it is the strategy output type; not an internal of any one strategy).

### `src/theogony/retrieval/pipeline.py`

Update `QueryPipeline.__init__` per Scope decision 6.

### `src/theogony/api/dependencies.py`

`get_query_pipeline` reads `request_state.settings.retrieval.strategy` and constructs the strategy:

```python
def _build_strategy(store: KnowledgeStore, settings: Settings) -> RetrievalStrategy:
    name = settings.retrieval.strategy
    if name == "fixed_depth":
        return FixedDepthStrategy(store)
    if name == "edge_product":
        return EdgeProductBreadthFirstStrategy(store)
    raise ValueError(f"unknown retrieval.strategy: {name}")
```

When the per-request `QueryRequest.strategy` field is set, override.

### `src/theogony/api/dto.py`

Add the `strategy` field to `QueryRequest` per Scope decision 8. `QueryResponse` is unchanged.

### `src/theogony/api/routes/query.py`

Pass the request's optional `strategy` field into `get_query_pipeline` (or override after construction). The simplest path is to extract a small helper that builds the strategy from the request + settings.

### `src/theogony/cli.py`

Add `--strategy` option to the `ask` command. Pass through to `_run_ask`. The async function constructs the matching strategy and injects it.

### `src/theogony/config/settings.py`

Add `RetrievalSettings` per Scope decision 7. Wire into top-level `Settings`.

### `tests/test_retrieval_pipeline.py` and `tests/test_retrieval_pipeline_neo4j_live.py`

Should stay green without modification. **This is the regression contract.**

### `tests/test_retrieval_strategies.py` (new)

Add at minimum:

- `test_retrieval_strategy_protocol_runtime_checkable` — assert `isinstance(FixedDepthStrategy(store), RetrievalStrategy)`.
- `test_retrieval_budget_default_values` — assert the documented defaults.
- `test_retrieval_budget_rejects_unknown_field` — assert `extra="forbid"` works.
- `test_fixed_depth_strategy_byte_identical_to_legacy_multi_hop_retriever` — given a fixture in-memory store, run the legacy path and the new strategy path, assert results equal.
- `test_edge_product_strategy_prunes_below_min_path_product` — given a fixture store with known edge weights, assert paths whose product falls below the threshold are excluded.
- `test_edge_product_strategy_returns_top_n_when_set` — given a fixture with N+5 valid paths, assert exactly N are returned.
- `test_edge_product_strategy_populates_nodes_per_hop` — assert the field is a list of correct length.
- `test_query_pipeline_uses_injected_strategy` — construct a pipeline with `strategy=EdgeProductBreadthFirstStrategy(...)`, run `ask`, assert the strategy was actually used (e.g., via a sentinel attribute on the result).
- `test_query_pipeline_falls_back_to_settings_strategy_when_no_injection` — settings says `edge_product`; pipeline constructed without explicit strategy uses it.

### Documentation touches

1. `docs/PHOENIX_BACKLOG.md` PHX-0056 catalogue entry: append `"Phase 1 closed by F3 (PR #...): Protocol + RetrievalBudget + FixedDepthStrategy + EdgeProductBreadthFirstStrategy. Phase 2 ships VectorSimilarityBreadthFirst and LLMHeuristicGuided when measured signals justify them."`
2. `docs/PHOENIX_BACKLOG.md` PHX-0057 / 0060 / 0061 entries: append `"Implementation will register a new RetrievalStrategy alongside the F3 Protocol."`
3. New short `docs/RETRIEVAL_STRATEGIES.md` (~80 lines): explains the Protocol pattern, the RetrievalBudget contract, when to add a new strategy, and the relationship to PHX-0056 / 0057 / 0060 / 0061.
4. `docs/ARCHITECTURE.md` — short paragraph in the Retrieval section announcing the Strategy pattern as the extension surface.

---

## Cost-benefit considerations

**Token cost**: medium. Composer needs to introduce a new subpackage, refactor one existing module into a facade, add a second concrete strategy with non-trivial logic (the breadth-first walk), update the CLI / API / settings, and write 9 new tests. Estimate ≤ €0.60 of Composer execution. Bigger than F1 but smaller than the hosted v1 brief.

**Runtime cost**: zero net for the default path. `FixedDepthStrategy` does the same `store.multi_hop_search` call as today's `MultiHopRetriever`. The new `EdgeProductBreadthFirstStrategy` is opt-in via settings or per-request flag — its cost only applies when a caller explicitly chooses it.

**Test cost**: marginal. ~9 new tests; total wall-clock added is < 0.2 s.

**Failure modes worth watching**:

- **Behaviour drift in the default path**: the existing retrieval tests are the regression contract. If they fail, the `FixedDepthStrategy` is not byte-identical to the legacy code. Investigate before claiming F3 done.
- **`get_neighborhood` semantics in the EdgeProductBreadthFirst walk**: `KnowledgeStore.get_neighborhood` returns a `Constellation` with nodes + edges. The strategy walks the edges and tracks the path product. Make sure you do not double-count edges (an `A → B → A` cycle is a single visit, not two).
- **Async parallelism**: per-hop expansion uses `asyncio.gather`. Make sure you do not flood the store with thousands of concurrent calls — bound concurrency to `budget.max_nodes` per hop step.
- **`extra="forbid"` on `RetrievalBudget`**: pydantic-settings can pass through unknown keys silently if `extra="allow"` is the default. We explicitly forbid; verify the test catches the regression.

---

## Out of scope (do not do)

- **Do not** implement `VectorSimilarityBreadthFirstStrategy` or `LLMHeuristicGuidedStrategy`. Those are PHX-0056 Phase 2.
- **Do not** wire `pheromone_mode` into either strategy's actual behaviour. The field exists in `RetrievalBudget` for forward compatibility; PHX-0057 ships the behaviour.
- **Do not** add `ClusterNarrowingRetrievalStrategy`. That is PHX-0060.
- **Do not** add federation routing. That is PHX-0061.
- **Do not** change the `Constellation` / `ConstellationNode` / `ConstellationEdge` shapes. Strategies operate on `MultiHopResult`; assembly into a Constellation happens downstream.
- **Do not** add token-counting for the `token_cap` field. The field is reserved; no strategy currently honours it. PHX-0056 Phase 2 implements LLMHeuristicGuided which will.
- **Do not** add a strategy registry beyond the explicit if/elif in `_build_strategy`. A registry pattern is overkill for two strategies; PHX-0056 Phase 2 introduces it when there are five.
- **Do not** add per-strategy metrics to `MultiHopResult`. The `duration_ms` field already exists; per-strategy diagnostics belong in `QueryRunReport.multi_hop` extension when a future ticket needs them.

---

## Done when

- [ ] `src/theogony/retrieval/strategies/` exists with five files: `__init__.py`, `protocol.py`, `budget.py`, `fixed_depth.py`, `edge_product.py`.
- [ ] `MultiHopRetriever` is the thin facade from Scope decision 5; legacy callers keep working.
- [ ] `QueryPipeline` accepts a `strategy` keyword.
- [ ] `Settings.retrieval.strategy` exists with `"fixed_depth"` default.
- [ ] CLI `theogony ask --strategy edge_product "<question>"` works; API `POST /query` accepts `strategy` field.
- [ ] `tests/test_retrieval_pipeline.py` and `tests/test_retrieval_pipeline_neo4j_live.py` stay green without modification.
- [ ] `tests/test_retrieval_strategies.py` covers all nine new tests; all green.
- [ ] Full test suite (`pytest -q`) green.
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy src/theogony/retrieval/` clean (strict).
- [ ] `docs/PHOENIX_BACKLOG.md` PHX-0056 / 0057 / 0060 / 0061 entries get the one-line F3 update.
- [ ] `docs/RETRIEVAL_STRATEGIES.md` exists.
- [ ] `docs/ARCHITECTURE.md` Retrieval section gets the Strategy paragraph.
- [ ] PR title: `feat(retrieval): F3 — RetrievalStrategy Protocol + EdgeProductBreadthFirst`. PR body lists which Plan / PHX ticket the work covers (PHX-0056 Phase 1) and confirms zero behaviour change against existing retrieval tests.

---

## After this PR

F3 closes Phase 0. F1 + F2 + F3 together form the architecture foundation:

- Vitality math is consolidated under `core/vitality.py` (F1).
- The OneirosWorker tick is a composable pipeline of `TickPhase`s (F2).
- The retrieval stack is a composable family of `RetrievalStrategy`s (F3).

Phase 1 begins with **PHX-0060 Phase 1 — Cluster v1**: populate `cluster_id` via the hybrid trigger (periodic OneirosWorker re-pass via a new `ReclusterPhase` + nearest-centroid assignment on insert), expose centroids, ship the second concrete strategy `ClusterNarrowingRetrievalStrategy` that narrows retrieval via centroid similarity before graph traversal.

After PHX-0060 Phase 1, the parallel Wave-1 sprints (PHX-0057 Edge-Pheromone, PHX-0058 Aggregated Stub Detection, PHX-0059 Morpheus Associator) become small, focused PRs because each one drops a single new `TickPhase` (and PHX-0057 also adds `pheromone_mode` behaviour to each existing strategy) into the foundation F2 + F3 just laid.
