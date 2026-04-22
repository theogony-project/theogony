# Edge pheromones and Slow-Path modes (PHX-0057 Phase 1)

**Purpose:** explain how the Chronik strengthens **edges** that repeatedly ground citations, how idle trails **decay**, and how **Slow-Path** retrieval may deliberately walk *against* accumulated bias.

**Scope:** Gen 1 Phase 1 only. Node-level relevance bumps (`RelevanceTracker`) remain; edge pheromones are additive.

---

## Principle

Successful answers leave a **trail on the graph**, not only on nodes. Each cited retrieval path bumps the `pheromone_delta` overlay on the edges whose endpoints were both cited, so the next traversal can treat those conduits as slightly stronger (under the default `follow` mode). Trails that go unused for a long horizon can be **decayed** back toward zero by Oneiros.

**Doctrine line:** trails strengthen the graph; Slow-Path is allowed to walk against them (see [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md)).

---

## Schema

| Field | Where | Role |
|--------|--------|------|
| `pheromone_delta` | `KnowledgeEdge`, mirrored on `ConstellationEdge` | Signed overlay in \([-1, 1]\) applied on top of baseline `weight`. |
| `last_traversed` | `KnowledgeEdge` | UTC timestamp of the last bump (decay phase selects “aged” edges by this index). |
| `edge_id` | `ConstellationEdge` | Same id as `KnowledgeEdge.id` so the query pipeline can derive cited edges from citations + constellation. |

Cold corpora start with `pheromone_delta = 0` everywhere: **all three traversal modes behave identically** until bumps accumulate.

---

## Traversal modes (`pheromone_mode`)

Passed through `RetrievalBudget` into `KnowledgeStore.multi_hop_search` / `traverse` / `get_neighborhood`. Effective edge weight uses `effective_weight` in `src/theogony/core/pheromone.py` (also re-exported from `src/theogony/retrieval/strategies/pheromone.py` for strategies):

| Mode | Effective weight |
|------|------------------|
| `follow` | `clamp01(weight + pheromone_delta)` — default; honours trails. |
| `ignore` | `weight` — exploratory read; ignores overlay. |
| `invert` | `clamp01(weight - pheromone_delta)` — Slow-Path; penalises well-trodden edges. |

**Slow-Path write contract:** when `pheromone_mode != "follow"`, `QueryPipeline.ask` skips **both** node relevance bumps and edge pheromone bumps for that call. Slow-Path is cheaper and leaves no write-back footprint.

---

## Bump path

`EdgePheromoneTracker` (`src/theogony/memory/edge_pheromone.py`) calls `KnowledgeStore.batch_bump_edges` with the configured δ (`Settings.relevance.edge_pheromone_delta`, default `0.015`). Cited edge ids are derived in `derive_cited_edge_ids` from the constellation plus `Answer.cited_node_ids`. Duplicate ids in one answer are deduped.

---

## Decay path

`PheromoneDecayPhase` (`src/theogony/memory/pheromone_decay_phase.py`) runs as an optional Oneiros tick phase (`name = "pheromone_decay"`). It is **registered** on the worker but **not** in the default `enabled_phases` list. Operators opt in explicitly.

Knobs live under `Settings.oneiros.edge_pheromone` (`decay_horizon_days`, `decay_rate`, `decay_epsilon`). The phase lists aged edges via `list_aged_pheromone_edges`, applies multiplicative decay toward zero, snaps tiny values to `0.0`, and records counts in `TickContext.extras["pheromone_decay"]`.

---

## Phase 2 / open questions

- **Per-cluster pheromone spaces** (PHX-0060 Phase 2): one overlay per cluster instead of a single global δ.
- **LLM-cited edges:** extend the synthesizer contract so citations can name edges directly, not only nodes.
- **Differential bump:** stronger δ for high-confidence citations, weaker for uncertain ones.
- **Anomaly / autobahn detection** (Nemesis / PHX-0068): guardrails when a few edges absorb all traffic.

---

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Memory architecture and Oneiros tick pipeline.
- [`RETRIEVAL_STRATEGIES.md`](RETRIEVAL_STRATEGIES.md) — Strategy stack and `pheromone_mode` wiring.
- [`docs/etappes/W2_edge_pheromone_brief.md`](etappes/W2_edge_pheromone_brief.md) — full design brief.
