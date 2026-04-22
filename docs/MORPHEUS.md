# Morpheus — deterministic associator (PHX-0059 Phase 1)

**Morpheus** is the Pantheon dreamer role: it proposes *new* graph edges the extractor never saw. In Gen 1 Phase 1 this is implemented as an **opt-in Oneiros tick phase** (`morpheus` on `Settings.oneiros.enabled_phases`), not a separate worker.

## What runs today

- **`MorpheusAssociator`** (`src/theogony/memory/morpheus.py`) — pure async logic over `KnowledgeStore`.
- **`MorpheusPhase`** (`src/theogony/memory/morpheus_phase.py`) — calls the associator and `batch_upsert_edges`.

Each tick considers up to `Settings.morpheus.batch_size` **lonely Ephemera** nodes (degree `< candidate_isolation_max_edges`), **oldest `created_at` first** so fresh ingest gets the next tick.

## Signals (Phase 1)

Two deterministic signals ship; temporal proximity and glossary overlap are deferred to Phase 2 (see [`PHOENIX_BACKLOG.md`](PHOENIX_BACKLOG.md) PHX-0059).

1. **Embedding band** — cosine similarity in `[embedding_band_low, embedding_band_high]` (default `[0.6, 0.9]`). This is deliberately *not* “top‑k nearest”: very tight neighbours (>0.9) are condensation territory (PHX-0011); far pairs are noise.
2. **Source co-occurrence** — same `source_ref.identifier`, not yet directly connected.

## Proposed edge shape

- `relation_type="ASSOCIATED_WITH"` (generic; Athene may sharpen later).
- `epistemic_type=INFERENCE`, `confidence=0.4`, `weight=0.5`.
- `properties`: `proposed_by=morpheus`, `signal`, `signal_value`, `tick_run_id`, optional `cross_cluster` (W1 convention).

## Cluster scope

`Settings.morpheus.cluster_scope`:

- `within_and_cross` (default) — emits cross-cluster bridges with `cross_cluster=True`.
- `within_only` — suppresses cross-cluster proposals.

`bridge_score` on cross-cluster edges is Phase 2 (paired with PHX-0060 Phase 2).

## Observability

- `OneirosTickReport.morpheus` (`MorpheusBreakdown`) when the phase ran.
- MCP `pantheon_status.morpheus_proposals_recent` reads the latest tick report.

## Phase 2 (explicit non-goals here)

- LLM-driven dreaming — PHX-0004.
- Athene verification — PHX-0007.
- Temporal / glossary signals — sub-tickets from PHX-0059.
- Blind-spot-aware targeting (W3 composition) — deferred.

See also [`DEPTH_BANDS.md`](DEPTH_BANDS.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md) §Memory Architecture.
