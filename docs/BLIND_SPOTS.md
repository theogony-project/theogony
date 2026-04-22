# Blind spots — recurring thin regions

The Chronik should notice not only that a single answer was thin, but **which regions of its knowledge surface keep attracting questions that still come back thin**. That strategic signal is what Wave 1 W3 (PHX-0058 Phase 1) introduces: per-query **stub detection** plus optional **aggregation** into `BlindSpotReport` files.

This document complements [`CURIOSITY.md`](CURIOSITY.md) (motivation and the full Curiosity Loop vision) with the concrete Gen 1 mechanics.

## Principle

- **Per query:** every `QueryRunReport` carries a `StubVerdict` (six independent boolean signals plus recorded metrics and an unweighted aggregate strength in `[0, 1]`) and a `RegionDescriptor` (query embedding, dominant `cluster_id` / `node_type`, seed counts, mean confidence).
- **Over time:** an operator-opt-in Oneiros tick phase (`blind_spot_aggregation`, default **off**) scans recent query reports, keeps those with `stub_verdict.is_stub`, clusters their `region_descriptor.query_embedding` vectors with the same **HDBSCAN** machinery as W1, and writes one **`BlindSpotReport` per emergent cluster** that meets `Settings.curiosity.min_hits`.

The aggregator **does not** dispatch outward research (that remains PHX-0037). It only persists a priority signal for Prometheus / Morpheus / operators.

## The six stub signals

Aligned with [`CURIOSITY.md`](CURIOSITY.md) §Stub Detection:

1. **Low node count** — constellation smaller than `min_node_count`.
2. **Low edge density** — edges per node below `min_edge_density`.
3. **Low vitality (Phase 1 proxy)** — mean `ConstellationNode.confidence` below `min_mean_vitality` (full vitality on `KnowledgeNode` is a Phase 2 refinement).
4. **Narrow source diversity** — fewer than `min_distinct_source_types` distinct `source_ref.source_type` values among nodes.
5. **Low confidence aggregate** — mean confidence below `min_mean_confidence` (same proxy input as vitality in Phase 1).
6. **Poor named-entity coverage** — when callers supply `named_entities_in_query`, resolved ratio vs citations/labels; if the list is omitted, ratio is treated as `1.0` (neutral).

Aggregate: `stub_signal_strength = (count of fired signals) / 6`. `is_stub` is true when strength is strictly greater than zero.

## Configuration (`Settings.curiosity`)

- `stub_thresholds` — `StubThresholds` for the six cut-offs.
- `window_days` — how far back to scan `run_reports/query/*.json` (time filter on `started_at`).
- `min_hits` — minimum stub reports in the window to run aggregation, and minimum members per HDBSCAN cluster / emitted candidate.
- `aggregation_interval_s` — cadence guard against writing too often; mirrors Oneiros tick-style intervals (default one day).

## Operator surfaces

- **CLI:** `theogony curiosity blindspots [--force]` runs one pass (mirrors `theogony recluster`). `theogony reports list --type blindspot` / `reports show <run_id>` include blind-spot reports.
- **MCP:** `pantheon_reports_list` / `pantheon_reports_show` accept `blindspot` as a filter alongside ingest/query/oneiros/clustering.
- **Oneiros:** register `"blind_spot_aggregation"` in `DEFAULT_PHASE_REGISTRY`; add the name to `enabled_phases` only when you want the worker to run it.

## `BlindSpotReport` shape

Each file documents one candidate cluster: `contributing_run_ids`, `centroid_embedding`, aggregated `stub_signal_strength`, dominant `cluster_id` / `node_type`, and reserved **Hestia** fields (`requires_hestia_review`, `hestia_review_status`) — always `False` / `"not_required"` in Phase 1 (PHX-0039 will own real review).

## Privacy note

`RegionDescriptor.query_embedding` is the raw query embedding. It is persisted on every `QueryRunReport` for clustering fidelity. Sensitive deployments should plan scrubbing, hashing, or access control (future Hestia / policy work); W3 documents the trade-off explicitly so operators opt in with eyes open.

## Phase 2 / open questions

- **NER on the query** to populate `named_entities_in_query` automatically instead of neutral `None`.
- **Hestia review** (PHX-0039) before treating a blind spot as an actionable research target.
- **Curiosity dispatch** (PHX-0037) consuming `BlindSpotReport` heat maps.
- **Weighted** `stub_signal_strength` once calibration data exists.
- **Per-cluster stub statistics** (PHX-0060 Phase 2) and differential relevance / pheromone bump intensity for high-strength regions.
