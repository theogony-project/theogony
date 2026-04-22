# Retrieval strategies (F3)

Theogony’s multi-hop retrieval is **pluggable**: each query embedding plus a
`RetrievalBudget` is handled by a `RetrievalStrategy` implementation that
returns a `MultiHopResult`. The façade `MultiHopRetriever` keeps the legacy
`retrieve(..., k=, hops=, min_weight=)` API and maps those arguments into a
budget for the active strategy.

## Components

| Piece | Role |
|--------|------|
| `RetrievalStrategy` | Protocol: `name: str` and `async retrieve(embedding, *, budget, layer)` |
| `RetrievalBudget` | Pydantic envelope: universal caps (`max_nodes`, `min_edge_weight`) plus strategy-specific hints (`hops`, `min_path_product`, `top_n_paths`, …) |
| `FixedDepthStrategy` | Default: delegates to `KnowledgeStore.multi_hop_search` (Plan §4.2) |
| `EdgeProductBreadthFirstStrategy` | Vector seed + BFS with path-product pruning and optional top-N paths |
| `ClusterNarrowingRetrievalStrategy` (`cluster_narrow`) | Ranks `ClusterSummary` centroids by cosine to the query, unions top-N cluster members, runs an inner strategy, then **post-filters** scored nodes to that union |
| `build_retrieval_strategy(store, settings, override=…)` | Single factory used by the API, CLI, and MCP |

## `pheromone_mode` (PHX-0057 Phase 1)

`RetrievalBudget.pheromone_mode` is forwarded into the store’s multi-hop traversal and neighbourhood reads:

| Value | Meaning |
|--------|---------|
| `follow` (default) | Effective edge weight = `clamp01(weight + pheromone_delta)` — honours accumulated trails. |
| `ignore` | Uses baseline `weight` only. |
| `invert` | `clamp01(weight - pheromone_delta)` — Slow-Path prefers edges that were *not* heavily bumped. |

When `QueryPipeline.ask(..., pheromone_mode=...)` is not `follow`, **no** post-answer relevance or edge-pheromone write-back runs for that call — Slow-Path stays read-only with respect to those signals.

API / CLI / MCP expose the same literal (`POST /query`, `theogony ask --pheromone-mode`, `pantheon_ask`). Details: [`PHEROMONE.md`](PHEROMONE.md).

Reserved budget fields (`token_cap`, `wall_clock_ms_cap`) remain for forward compatibility (PHX-0056 Phase 2).

## `cluster_narrow` (PHX-0060 Phase 1)

`cluster_narrow` is a **wrapper** strategy: it always delegates to an **inner**
strategy (`Settings.retrieval.cluster_narrow_inner_strategy`, default
`fixed_depth`). Before the inner call it:

1. Loads `await store.list_clusters()`. If empty, it returns the inner result unchanged (same as `fixed_depth` default path).
2. Sorts clusters by centroid cosine to the query embedding, keeps the top `Settings.retrieval.cluster_narrow_top_n_clusters` (default **3**), and unions their member node ids.
3. If that union is smaller than `max(budget.max_nodes, 20)`, it **falls back** to the inner strategy without narrowing — avoids starving retrieval on small or sparse cluster assignments.
4. Otherwise it runs the inner `retrieve`, then drops any scored node whose id is not in the union (post-filter; Phase 2 may push a hard candidate scope into `RetrievalBudget`).

Default deployment behaviour remains **`strategy=fixed_depth`** until the operator opts in.

## Selecting a strategy

- **Settings:** `THEOGONY_RETRIEVAL__STRATEGY=edge_product` (nested env for
  `Settings.retrieval.strategy`).
- **HTTP:** optional `strategy` on `POST /query` overrides settings for that
  request only.
- **CLI:** `theogony ask --strategy edge_product "…"`.
- **Code:** pass `strategy=` into `QueryPipeline`, or construct
  `MultiHopRetriever(store, strategy=…)`.

## Adding a strategy

1. Implement the protocol (async `retrieve`, stable `name`).
2. Honour `max_nodes` and `min_edge_weight`; ignore unknown budget fields rather
   than violating caps silently.
3. Wire the name into `build_retrieval_strategy` (explicit `if`/`elif` until a
   registry is justified — PHX-0056 Phase 2).
4. Extend `RetrievalSettings` / API / CLI literals if the strategy is
   user-selectable.

## Tickets

- **PHX-0056** — Activation engine; Phase 1 (F3) ships the protocol, budget, and
  two strategies; Phase 2 adds vector-steered and LLM-guided strategies.
- **PHX-0057** — Edge pheromones shipped Phase 1 (`pheromone_mode` + bump/decay); Phase 2 items are listed in [`PHEROMONE.md`](PHEROMONE.md).
- **PHX-0060** — Cluster narrowing (`cluster_narrow`) shipped in Phase 1; hierarchical / soft variants remain future work.
- **PHX-0061** — Federation routing sits above strategies but shares the same
  extension surface.
