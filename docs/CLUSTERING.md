# Clustering (PHX-0060 Phase 1)

This document is the operator-facing companion to [`docs/etappes/W1_cluster_v1_brief.md`](etappes/W1_cluster_v1_brief.md) and [`phoenix-backlog/PHX-0060.yaml`](../phoenix-backlog/PHX-0060.yaml). Phase 1 ships **flat** semantic clusters over the Chronik: emergent “cognitive centers” (Sprachzentrum / Sehzentrum / code vs places vs fiction style regions) without claiming neuroscience fidelity — the metaphor guides product direction.

## Locked Phase-1 decisions (four YAML knobs, resolved 2026-04-21)

1. **Hierarchy depth:** one level only. `cluster_id` points to a leaf cluster; centroids-of-centroids are Phase 2.
2. **Identity stability:** `cluster_id` is volatile; when a new pass disagrees strongly with the old partition, ids are re-minted. **`cluster_label`** survives when Jaccard overlap between old and new membership is ≥ **0.7** (default); otherwise the new cluster starts with `cluster_label=None` (LLM naming is Phase 2).
3. **Argonauts (per-cluster sub-agents):** deferred. `ClusterSummary.properties` reserves `agent_class: str | None` for a follow-up ticket.
4. **Cross-cluster edges:** `KnowledgeEdge.properties["cross_cluster"]` is a bool, set on ingest and refreshed after each recluster. **`bridge_score`** waits for Morpheus (PHX-0059) + Phase 2.

Pre-locked knobs from the YAML remain: **hard** clustering, **hybrid** trigger (periodic recluster + insert-time nearest centroid), **HDBSCAN** default with **k-means** above `corpus_size_kmeans_threshold`.

## Runtime shape

- **`ClusteringStrategy`:** sync `cluster(node_ids, embeddings) -> ClusteringResult` (CPU work wrapped in `asyncio.to_thread` inside `ReclusterPhase`).
- **`ReclusterPhase`:** Oneiros tick phase `name="recluster"` — **off** by default (`Settings.oneiros.enabled_phases` does not include it). When enabled, cadence is governed by `Settings.clustering.recluster_interval_days` and the latest `ClusteringRunReport` on disk.
- **`ClusterIndex`:** held by API lifespan / CLI ingest; `rebuild_from_store` after each recluster extras publish; `assign(embedding)` returns nearest centroid’s `cluster_id` or `None` on cold start.
- **`ClusterNarrowingRetrievalStrategy`:** optional retrieval; ranks clusters by centroid cosine, unions members of top-N, then **post-filters** the inner strategy’s scored nodes. Falls back to the inner strategy alone when there are no clusters or when `|candidates| < max(budget.max_nodes, 20)` (anti over-narrowing).

## Operator knobs (`Settings.clustering`)

| Field | Role |
|--------|------|
| `algorithm` | `auto` chooses HDBSCAN vs k-means from corpus size |
| `recluster_interval_days` | Minimum spacing between automatic passes |
| `min_cluster_size` | HDBSCAN parameter floor |
| `min_corpus_size` | Skip recluster if fewer embedded nodes |
| `corpus_size_kmeans_threshold` | Switch to k-means at or above this count |
| `identity_jaccard_threshold` | Jaccard gate for inheriting `cluster_id` / `cluster_label` |
| `new_node_assignment` | `nearest_centroid` vs `skip` at ingest |

## Phase 2 (explicit non-goals for Phase 1)

Hierarchical meta-centroids, LLM cluster naming, Argonaut lifecycles, soft multi-membership clustering, `bridge_score`, per-cluster pheromones (PHX-0057), Morpheus scoped to clusters (PHX-0059), federation (PHX-0061).

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) §"The Knowledge Network as Its Own Index"
- [`RETRIEVAL_STRATEGIES.md`](RETRIEVAL_STRATEGIES.md) — `cluster_narrow` composition and fallbacks
- `theogony recluster [--force]` — one-shot operator command
