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
| `build_retrieval_strategy(store, settings, override=…)` | Single factory used by the API, CLI, and MCP |

Reserved budget fields (`pheromone_mode`, `token_cap`, `wall_clock_ms_cap`)
exist for forward compatibility; see PHX-0057 and PHX-0056 Phase 2.

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
- **PHX-0057** — Edge pheromones; strategies will honour `pheromone_mode`.
- **PHX-0060** — Cluster narrowing as a further `RetrievalStrategy`.
- **PHX-0061** — Federation routing sits above strategies but shares the same
  extension surface.
