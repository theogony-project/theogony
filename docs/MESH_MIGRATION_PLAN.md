# MESH Migration Plan

**Status:** binding migration plan for the strangler-fig replacement of the Generation-1 codebase with the substrate specified by the MESH triplet.
**Author:** Daedalus (architect role).
**Audience:** every agent — Pantheon, builder, or external — that picks up substrate-related implementation work from this point forward.
**Date filed:** 2026-05-13.

This document specifies *how* the current Generation-1 codebase walks to the substrate described in [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md), [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), and [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) — without a blackout, without throwing away functioning surface code, and without leaving the codebase in a permanent half-migrated state.

It supersedes [`IMPLEMENTATION_PLAN_GEN1_LEGACY.md`](IMPLEMENTATION_PLAN_GEN1_LEGACY.md) as the active implementation plan. That document has been renamed and is kept as historical context only; it is no longer operative.

---

## Required reading (in order, before touching code)

A new agent picking up this work must read the following, in this order, before opening a branch:

1. [`../AGENTS.md`](../AGENTS.md) — the binding working contract for AI coding agents in this repository.
2. [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) — the binding substrate doctrine. Two-tier nodes, eager identity, edge anatomy, dynamics, agent-driven cleanup, pathology and staged therapy.
3. [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) — the binding runtime spec. Hot / Warm / Cold tiering, LanceDB columnar nodes, PyTorch sparse CSR edges, delta buffer, MVCC, batched-SpMV, Oneiros tick order.
4. [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) — the binding retrieval spec. Diversified injection (MMR + weight-class stratification + sub-mesh signature), three-factor reinforcement learning, frame routing, multi-agent strategy game, multi-modal extension.
5. [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) — the architectural floor (no raw text as retrieval payload, LanceDB + PyTorch, Spreading Activation as the only retrieval primitive).
6. [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md) — the Function-First Phase doctrine. Run-it-then-heal-it, no pre-gates, honest failure reports, engineering order **data structure → synthesis → retrieval**.
7. [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) — the claim-level immune system. The substrate-level continuation lives in `MESH_SUBSTRATE.md` §"Agent-driven cleanup" + §"Pathology and therapy".
8. This document — the migration plan itself.
9. [`../ROADMAP.md`](../ROADMAP.md) — where this migration fits in the five-phase sequence.

Skipping any of items 2–4 will result in implementing the wrong substrate. Skipping item 1 will result in an unmergeable PR. Skipping items 5–7 will produce a substrate that contradicts existing doctrine in ways that are not visible from the MESH triplet alone.

---

## The architectural situation

### What the codebase looks like today

- `src/theogony/` — ~38,500 LOC across ~20 subsystems (acquisition, agents, api, chronicle, clustering, cockpit, config, core, curiosity, docs_ingest, extraction, kadmos, mcp, memory, phoenix, reporting, retrieval, seeds, stores, viz)
- `tests/` — ~30,000 LOC across ~173 test files
- `phoenix-backlog/` — 52 active PHX YAMLs (PHX-0001 to PHX-0074, with gaps)
- `docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md` — 2,168 lines with reconciliation blocks up to the "Neural Vector Mesh Pivot" of 2026-05-01; superseded by this plan
- `docs/PHOENIX_BACKLOG.md` — 516-line catalogue

### Where the code is in the right direction

The following components are conceptually correct under the MESH triplet and stay through the strangler-fig migration:

- **Surfaces:** CLI (`src/theogony/cli.py`), MCP server (`src/theogony/mcp/`), Cockpit (`src/theogony/cockpit/`), API (`src/theogony/api/`).
- **Acquisition layer:** the `AcquisitionAdapter` protocol and its implementations (Gutenberg, web, Wikidata).
- **Reporting layer:** `src/theogony/reporting/` — the `IngestRunReport` / `QueryRunReport` / `OneirosTickReport` shapes are doctrine-conformant and used by the immune system.
- **Configuration:** `pydantic-settings` with `SecretStr` for secrets; the settings tree is sound.
- **LanceDB and PyTorch CSR foundations:** `src/theogony/stores/lancedb_store.py` and `src/theogony/core/tensor_engine.py` exist; they are partial but in the right direction.

### Where the code is structurally incompatible with the MESH triplet

The central problem lives in **`src/theogony/core/model.py`**:

- `KnowledgeNode` carries a *single* `embedding` field. The MESH doctrine requires multiple per-node vectors (`semantic_vector`, `frame_vector`, optional `structural_vector`, optional `temporal_vector`, optional `description_vector`).
- `Layer = "ephemera" | "mneme"` is the binary memory-tier model. The MESH doctrine uses `consolidation_tier: int` (Tier 0 chunks, Tier 1+ consolidated, higher tiers earned).
- `NodeType` is a closed enum (`PERSON | PLACE | CONCEPT | …`). MESH §"Field discipline" point 6 forbids a stored `node_type` enum; only four discrete flags exist (`consolidation_tier`, `is_candidate`, `is_anchor`, `is_source_anchor`).
- `EpistemicStatus` (`observed | inferred | hypothesized | disputed | deprecated`) lives on the node. In the MESH doctrine, epistemic framing lives in `frame_vector` (and, for claims, in reified claim nodes / `relation_kind` on edges), not as a single enum on a node.
- `EdgeType` is a closed string enum (`extraction | inference | wikidata | …`). In the MESH doctrine, edge dynamics are quantitative (`weight`, `decay_tier`, `frame_consistency`, `eligibility`), and the optional `relation_descriptor` / `relation_kind` / `description` / `pids` / `creation_context` fields are **free-form strings**, not enums. The substrate's automatic dynamics ignore them entirely.
- Edges live in the same storage path as their quantitative weights. MESH §"Edges — PyTorch sparse + delta buffer + Lance metadata table" mandates a *split*: quantitative core in PyTorch sparse CSR (hot path) + optional descriptors in a parallel Lance metadata table (off the hot path).

This is not a mismatch of field names — it is a different shape of the substrate. No incremental field-by-field renaming reaches the MESH doctrine. A new schema has to come in alongside the old one.

The `OneirosWorker` and `TickPhase` infrastructure (`src/theogony/memory/`) is also affected: the MESH-Implementation §"Oneiros — implementation order" specifies a 17-step phase sequence that differs from what is currently implemented. Phases like `morpheus_phase`, `pheromone_decay_phase`, `depth_band_phase` will not survive the migration in their current form (some absorb into MESH-doctrine equivalents, some become obsolete).

The legacy Neo4j store (`src/theogony/stores/`, if present alongside `lancedb_store.py` and `memory.py`) is explicitly deprecated by [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) §"Three Non-Negotiable Technical Decisions" §2 and falls away as part of this migration.

---

## Why the strangler-fig pattern (and not the alternatives)

Three options were considered. This plan chooses option C. The reasoning is recorded here so future agents do not relitigate it.

**Option A — Greenfield (delete and rewrite).** Rejected. Half of the existing code (CLI, MCP, Cockpit, acquisition adapters, run-report shapes) is doctrine-conformant. Discarding ~70,000 LOC of code + tests for a problem that lives in `model.py` and the stores is wasteful and produces a multi-week blackout in which nothing runs.

**Option B — In-place schema mutation.** Rejected. The schema mismatch is structural, not cosmetic. Field-by-field incremental rewriting of `KnowledgeNode` and friends would touch every store, every pipeline, every test, every report consumer in lockstep. The realistic outcome is a multi-year half-pivot where two schemas coexist permanently and nothing works cleanly. Software-engineering history records this failure mode reliably; it is not a hypothetical.

**Option C — Strangler-fig.** Chosen. New substrate layer is built in parallel under a fresh path (`src/theogony/mesh/`). The old code continues to function while the new layer matures. Surfaces (CLI, MCP, Cockpit) learn to address both, defaulting to whichever is appropriate per command. Sub-systems are migrated one at a time, each as its own PR with its own Definition of Done. When the new layer covers the old layer's surface, the old code is deprecated and then removed in a final cleanup PR.

The strangler pattern is named for the strangler fig (*Ficus aurea*), which germinates on a host tree, slowly grows around it, and eventually replaces it without the host tree ever being cut down. The host stays alive until the strangler is itself a complete tree. That is the contract this migration commits to.

---

## The six migration steps (plus one interpolated bootstrap)

Each step is a PR-sized unit of work. Each has:

- **Goal** — what the step delivers in one sentence.
- **Pre-conditions** — what must be true before starting.
- **Deliverables** — concrete files, schemas, tests.
- **Definition of Done** — observable criteria for acceptance.
- **Scope cap** — what the step explicitly does *not* include.

The steps are ordered. Step N+1 must not be started until step N is merged. Within a step, smaller PRs are encouraged as long as each smaller PR is itself green and reviewable.

**Interpolated step S2.5** was added on 2026-05-15 between S2 and S3 — a one-shot bulk seed of the substrate from Wikidata5m to give the mesh an identity backbone before retrieval (S3) is built. S2.5 complements S2 (does not replace it) and respects the same step-ordering invariant: it must not start before S2 is merged, and S3 must not start before S2.5 is merged.

### Step S1 — New substrate skeleton

**Goal:** introduce the MESH-doctrine schemas, the dual node Lance tables, the PyTorch sparse CSR edge tensor, the COO delta buffer, and a minimal Oneiros loop (decay + Hebb + saturation only). The new layer is reachable from a single new CLI subcommand `theogony mesh status`; the old code is untouched.

**Pre-conditions:**
- The MESH triplet, AGENTS.md, BUILD_DOCTRINE.md, IMMUNE_SYSTEM.md, and this migration plan have been read.
- The old code path (`theogony seed`, `theogony ask`, `theogony ingest`) still works on `main` at the start of this PR.

**Deliverables:**
- New package: `src/theogony/mesh/` with the following structure:
  - `src/theogony/mesh/__init__.py`
  - `src/theogony/mesh/schemas.py` — Pydantic v2 models for `ChunkNode`, `ConsolidatedNode`, `Edge`, `EdgeMetadata`, `SourceProvenance`, `QIDTag`, `PIDTag`. Models follow [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Node anatomy" and §"Edge anatomy" verbatim. `ConfigDict(extra="forbid")`.
  - `src/theogony/mesh/storage/` — LanceDB storage layer.
    - `nodes.py` — two Lance tables (`chunk_nodes`, `consolidated_nodes`) with per-vector HNSW indices on `semantic_vector` (default) and on populated `frame_vector` / `structural_vector` / `description_vector` columns. Versioned snapshots.
    - `edges.py` — PyTorch sparse CSR tensor builder + COO delta buffer + parallel Lance `edge_metadata` table (per [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Edges — PyTorch sparse + delta buffer + Lance metadata table").
    - `audit.py` — append-only Lance audit ledger.
  - `src/theogony/mesh/runtime/` — minimal Oneiros loop and Spreading Activation.
    - `spreading.py` — single-query Spreading Activation as batched SpMV (no diversified injection yet — that is step S3).
    - `oneiros_tick.py` — drain delta buffer → apply decay (`k = 2`, tier-modulated; tier-1+ left at gentler default in this step) → apply Hebbian merges → enforce saturation caps → rebuild CSR → commit new Lance version. Steps for consolidation, splits, pathology, therapy are stubbed (raise `NotImplementedError`) and called out as part of S5.
  - `src/theogony/mesh/cli.py` — minimal CLI: `theogony mesh status` (prints node/edge counts, current Lance version, last tick timestamp).
- Wire the new subcommand into `src/theogony/cli.py` as `mesh` (without touching any existing subcommand).
- Tests in `tests/mesh/`:
  - `test_schemas_roundtrip.py` — every schema round-trips JSON, `extra="forbid"` is enforced.
  - `test_storage_lance.py` — append a chunk node, fetch it; append an edge, retrieve it via CSR; commit a new version, read the prior version.
  - `test_spreading_activation.py` — toy mesh of 20 nodes; one seed; activation propagates through three hops with the expected damping.
  - `test_oneiros_tick_minimal.py` — toy mesh; one tick; verify decay applied, saturation cap enforced, audit ledger written.

**Definition of Done:**
- `pytest -q tests/mesh/` is fully green.
- `theogony mesh status` runs on a freshly-initialised mesh and prints a structured summary.
- The old `theogony ask "What is the Chronik?"` still works exactly as before (no regression in the legacy path).
- The new mesh has no Python imports of `src/theogony/core/model.py`. The mesh package is self-contained.
- All new files pass `ruff check`, `ruff format`, `mypy src/theogony/mesh`, and `pytest -q`.

**Scope cap (does NOT include):**
- Kadmos v2. The new substrate is exercised by unit-test fixtures only; no ingestion from external sources happens yet.
- Diversified injection or sub-mesh signature search.
- Three-factor reinforcement learning. Hebbian update in this step uses `β = 0` (plain Hebb).
- Consolidation, splits, pathology surveillance, or therapy. Those are stubbed.
- Any change to the Cockpit, MCP server, or any agent.
- Any deletion of legacy code.

**PR title convention:** `feat(mesh): substrate skeleton — schemas + Lance tables + minimal Oneiros tick (S1)`

### Step S2 — Kadmos v2 writes into the new substrate

**Goal:** Kadmos v2 (the cognitive reading layer per [`etappes/kadmos_v2_brief.md`](etappes/kadmos_v2_brief.md)) emits Tier-0 chunks and eager Tier-1 entity / concept / source-anchor candidates directly into the new substrate via the MESH eager-linking rules ([`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Why two tiers — and how identity actually gets committed").

**Pre-conditions:**
- S1 merged on `main` and the new mesh layer is green.
- Kadmos v2 brief read and understood.

**Deliverables:**
- `src/theogony/mesh/ingestion/kadmos_v2.py` — the new reading pipeline. Takes raw text + provenance metadata, emits `ChunkNode`s and reference `Edge`s into the new substrate.
- `src/theogony/mesh/ingestion/linker.py` — the eager-linking pass with the three-signal hierarchy:
  - Signal 1: Q-ID match against existing Tier-1 nodes (uniqueness invariant enforced per `MESH_SUBSTRATE.md` §"Field discipline" point 3).
  - Signal 2: description-based linking via `description_vector` cosine similarity, weighted by structural proximity to entities being co-ingested.
  - Signal 3: tag overlap + structural context as fast disambiguation fallback.
  - Path 2: entity-candidate creation with `is_candidate = True` when no signal fires confidently.
- `src/theogony/mesh/ingestion/source_anchor.py` — source-anchor entity creation per `MESH_SUBSTRATE.md` §"Source-anchor entities", with the structured description convention `"{type}: {title} ({anchor})"`.
- New CLI subcommand `theogony mesh ingest <source>` (e.g., a Gutenberg book ID, a Wikipedia article URL) that drives the full pipeline end-to-end into the new substrate.
- Tests:
  - `tests/mesh/test_ingestion_kadmos.py` — small Wikipedia paragraph in, expected number of Tier-0 chunks + eager Tier-1 entities out; eager-linking signals fire as predicted.
  - `tests/mesh/test_ingestion_linker_qid_uniqueness.py` — two chunks reference the same Q-ID; one Tier-1 node is created; second chunk's reference attaches to the existing node.
  - `tests/mesh/test_ingestion_source_anchor.py` — ingesting from a URL creates the source-anchor entity with correct description format.
- Integration test against the existing `docs/research/mnlm/poc/mesh_inputs/` corpus — run `theogony mesh ingest` over a small subset and verify the substrate ends up with the expected shape.

**Definition of Done:**
- `theogony mesh ingest 43497 --sentences 100` (Sven Hedin's Trans-Himalaya) produces a substrate with > 100 Tier-0 chunks, > 20 Tier-1 entity / concept / source-anchor nodes, and a clean audit ledger of every insertion and eager-linking decision.
- `theogony mesh status` afterwards shows the expected sizes.
- All new tests green.
- The old `theogony ingest 43497 --sentences 100` still works against the legacy path (no regression).
- An `IngestRunReport` is emitted by the new pipeline using the existing reporting schema (the surface is shared; only the substrate it writes to is new).

**Scope cap:**
- No retrieval against the new substrate yet beyond what S1's `theogony mesh status` shows. The retrieval path is S3.
- No Cockpit / MCP integration. Those are S4.
- No consolidation. Eager-Tier-1 nodes accumulate evidence but Oneiros does not yet promote candidates or merge duplicates beyond Q-ID-driven eager linkage.

**PR title:** `feat(mesh): Kadmos v2 ingestion with eager linking + source-anchor entities (S2)`

### Step S2.5 — Wikidata5m bulk seed (interpolated bootstrap step)

**Status:** interpolated between S2 and S3 in 2026-05-15 to give the substrate an identity backbone before S3 retrieval is built. Does **not** replace S2 (Kadmos v2 cognitive reading); it complements it. Filed under the post-MESH backlog as **PHX-1030**.

**Why this step exists.** Kadmos v2 (S2) is the right shape for *cognitive reading* of new external texts — it produces Tier-0 chunks, identity decisions, and audited mentions per paragraph at LLM cost. It is the wrong shape for *bootstrapping the identity backbone*: at €0.0001–€0.001 per paragraph and 5–15 s of latency, building a 1M-node substrate via Kadmos v2 alone is months of LLM time and three-figure euro cost. The substrate needs Q-ID-anchored Tier-1 nodes *before* it has cognitive load, so that every later Kadmos v2 reference fires signal 1 (Q-ID match) of the eager-linker hierarchy ([`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Why two tiers — and how identity actually gets committed") instead of creating candidates that never converge. S2.5 supplies that backbone in one structured bulk pass, with no LLM call and no NER pass.

**Goal:** populate the new substrate with ~4.81M Q-ID-anchored Tier-1 `ConsolidatedNode`s and ~21.35M relational `Edge`s from the [Wikidata5m](https://deepgraphlearning.github.io/project/wikidata5m) KEPLER dataset (transductive split, 2019/2020 snapshot). For each Q-ID, embed the Wikipedia first-paragraph **off-substrate** into `semantic_vector` and `description_vector`; keep `description = None` (or the entity name only) — **never store the paragraph body**. Triplets become typed `Edge`s with `creation_context = "wikidata5m_seed"`. The end state is a substrate that Kadmos v2 ingestion (S2 path) and S3 retrieval can both attach to via Q-ID.

**Pre-conditions:**
- S2 merged. The new substrate is operational with the dense paragraph topology + IngestRunReport path.
- The doctrine clarification PR (`docs(mesh): clarify "no raw text in substrate" and bound description size`) merged so that "no paragraph body in `description`" is unambiguous.
- The four Wikidata5m files staged at `data/raw/wikidata5m/` (gitignored under `data/`):
  - `wikidata5m_entity.txt` — 4.81M Q-ID + alias rows
  - `wikidata5m_text.txt` — 4.81M Q-ID + Wikipedia first-paragraph rows (input to off-substrate embedding; **not** loaded into the mesh as text)
  - `wikidata5m_relation.txt` — 825 P-ID + alias rows
  - `wikidata5m_all_triplet.txt` — 21.35M `(subject_qid, predicate_pid, object_qid)` rows
- The operator decides on the embedding model for the seed run (recommended: BGE-M3 class, 1024-d, doctrine default per [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Node anatomy"). Cost band: workstation-feasible (~19 GB embeddings + ~few hundred MB CSR for the full dataset).

**Deliverables:**
- New package: `src/theogony/mesh/seeds/` (sibling to `mesh/ingestion/`, `mesh/runtime/`, `mesh/storage/`).
  - `src/theogony/mesh/seeds/__init__.py`
  - `src/theogony/mesh/seeds/wikidata5m/__init__.py`
  - `src/theogony/mesh/seeds/wikidata5m/loader.py` — streaming readers for the four files. Pure iteration — no batch buffering of millions of lines in RAM. Yield typed records.
  - `src/theogony/mesh/seeds/wikidata5m/relations.py` — small registry mapping P-IDs to default `(relation_kind, relation_descriptor)`. P-IDs unmapped at run time fall through with `relation_kind = "semantic"`, `relation_descriptor = first_alias`, and the P-ID is added to `pids` on the edge for later registry expansion. Counters track unmapped P-IDs in the seed report.
  - `src/theogony/mesh/seeds/wikidata5m/embedder.py` — batched description embedding using `MeshTextVectorizer` (or a leaner local-only equivalent if vectorizer overhead dominates). Embedding stream is decoupled from the loader stream so embedding can be parallelised.
  - `src/theogony/mesh/seeds/wikidata5m/importer.py` — orchestrator. Streams entities → embeddings → `ConsolidatedNode` upserts (idempotent on Q-ID); then triplets → `Edge` upserts. Writes one audit record per entity creation and per edge creation. Emits a `MeshSeedRunReport` at the end.
- Extend `src/theogony/reporting/models.py` with a `MeshSeedRunReport` Pydantic v2 model (`extra="forbid"`) — counters: `entities_streamed`, `entities_upserted`, `entities_skipped_duplicate_qid`, `edges_streamed`, `edges_upserted`, `edges_skipped_duplicate`, `pids_unmapped`, `embedding_model_id`, `embedding_duration_s`, `import_duration_s`, `audit_run_id`, `verdict`.
- New CLI command `theogony mesh seed wikidata5m` with flags:
  - `--max-entities N` (default 0 = all)
  - `--max-triplets N` (default 0 = all)
  - `--batch-size N` (embedding batch)
  - `--dry-run` (parse + report without writing)
  - `--root <path>` (mesh workspace)
  - `--data-root <path>` (defaults to `data/raw/wikidata5m/`)
- Tests in `tests/mesh/seeds/`:
  - `test_wikidata5m_loader.py` — stream parsers handle real-format lines from a small fixture (~50 entities, ~10 triplets, ~5 P-IDs); aliases parsed correctly, malformed lines yield structured error records, no whole-file buffering.
  - `test_wikidata5m_relations.py` — known P-IDs map to defaults, unknown P-IDs fall through cleanly with `pids` populated.
  - `test_wikidata5m_importer.py` — small fixture run produces expected node + edge counts, Q-ID uniqueness invariant holds, audit ledger written, `MeshSeedRunReport` emitted with sensible counters.
  - `test_wikidata5m_no_raw_text.py` — assert via direct LanceDB inspection that the `description` column on every imported `ConsolidatedNode` is either `None` or ≤ 100 chars (entity name only). **No Wikipedia paragraph body anywhere in the mesh.**
  - `test_wikidata5m_idempotent.py` — second run on the same fixture is a no-op (matches by Q-ID), counters reflect this.
  - `test_wikidata5m_eager_linking_handoff.py` — after the seed, run a small Kadmos v2 paragraph that mentions a seeded Q-ID; assert that the IngestRunReport's `resolution.tier_counts` shows a signal-1 (Q-ID match) link to the seeded node, not a new candidate.

**Definition of Done:**
- `theogony mesh seed wikidata5m --max-entities 1000 --max-triplets 5000` produces a substrate with 1000 Q-ID-anchored Tier-1 nodes and ≤ 5000 edges (some triplets may reference Q-IDs outside the 1000-entity slice and are skipped with audit). Audit ledger has one entry per insertion. `MeshSeedRunReport` written. `description` column spot-check is empty or entity-name-only on every node.
- `theogony mesh status` after the seed shows the expected counts.
- A subsequent `theogony mesh ingest --text-file <fixture-with-seeded-qid>` (Kadmos v2) eager-links via signal 1 to the seeded Tier-1 node — no candidate created. Verifiable in the IngestRunReport.
- `pytest -q tests/mesh` is green (S2 tests still pass, S2.5 tests pass).
- `pytest -q` is green (no regression elsewhere).
- All new files pass `ruff format --check`, `ruff check`, `mypy src/theogony/mesh`.
- Q-ID uniqueness invariant holds: no two Tier-1 nodes carry the same Q-ID after import.

**Scope cap (does NOT include):**
- No retrieval beyond `theogony mesh status`. The retrieval path is S3.
- No description regeneration or re-embedding. A future "Wikidata freshening pass" PHX ticket pulls fresh Wikipedia first-paragraphs via Q-ID and re-embeds; that is a separate step, not S2.5.
- No coupling to Kadmos v2 internals beyond using the same `MeshTextVectorizer` (or a leaner equivalent) for embedding consistency.
- No Cockpit / MCP integration. Those remain S4.
- No consolidation, splits, pathology, therapy. Those remain S5.
- No deletion of the legacy path. That remains S6.
- The seed dataset (`data/raw/wikidata5m/`, ~3.4 GB) stays in `data/raw/` (gitignored). Operators are responsible for their own copy. The README pointer to the project page is enough.
- **No raw text storage anywhere.** The `wikidata5m_text.txt` paragraphs are read off-substrate, embedded, and discarded from the import path; they remain on disk in `data/raw/wikidata5m/` for later refresh runs but never enter the mesh's stored fields. This invariant is asserted by `test_wikidata5m_no_raw_text.py`.

**PR title convention:** `feat(mesh): wikidata5m bulk seed — Q-ID-anchored Tier-1 backbone (S2.5)`

### Step S3 — Diversified-injection retrieval over the new substrate

**Goal:** the new substrate is queryable via the MESH-retrieval discipline: Maximum Marginal Relevance + weight-class stratification + (optional) sub-mesh signature search, with frame routing.

**Pre-conditions:**
- S2 merged. The new substrate contains real ingested data.

**Deliverables:**
- `src/theogony/mesh/retrieval/diversified.py` — MMR seed selection per `MESH_RETRIEVAL.md` §"Maximum Marginal Relevance".
- `src/theogony/mesh/retrieval/stratification.py` — weight-class stratification per `MESH_RETRIEVAL.md` §"Weight-class stratification".
- `src/theogony/mesh/retrieval/submesh.py` — sub-mesh signature matching via Weisfeiler-Lehman hashing per `MESH_RETRIEVAL.md` §"Sub-mesh injection".
- `src/theogony/mesh/retrieval/frame_routing.py` — masked-SpMV frame routing per `MESH_RETRIEVAL.md` §"Frame routing during Spreading Activation".
- `src/theogony/mesh/retrieval/constellation.py` — Constellation assembly: nodes (with `description`), edges (with descriptors when populated), source-anchors, gaps. Returns the structured working set that downstream consumers ingest.
- New CLI subcommand `theogony mesh ask "<question>"` that drives the full retrieval path against the new substrate and prints the Constellation.
- Tests:
  - `tests/mesh/test_retrieval_mmr.py` — MMR returns diverse seeds.
  - `tests/mesh/test_retrieval_stratification.py` — seeds drawn from all four weight classes.
  - `tests/mesh/test_retrieval_submesh_wl.py` — sub-mesh injection with structural similarity > point-only similarity on a designed test case.
  - `tests/mesh/test_retrieval_frame_routing.py` — the Kendall / Thyroxine worked example from `MESH_SUBSTRATE.md` §"Worked example": same substrate, two different queries with different frame profiles return different Constellations.

**Definition of Done:**
- `theogony mesh ask "Who was Sven Hedin and where did he travel?"` against the S2-ingested corpus returns a coherent Constellation with proper Tier-1 entity nodes for Hedin and travelled places.
- The frame-routing test passes on the Kendall / Thyroxine example.
- A `QueryRunReport` is emitted in the existing reporting schema.

**Scope cap:**
- No three-factor reinforcement learning yet. Feedback modulation is hard-coded to `β = 0` in this step. The full RL implementation is part of S5.
- No multi-agent activation routing. Single-query path only.
- No Cockpit / MCP integration. Those are S4.

**PR title:** `feat(mesh): diversified injection + frame routing retrieval (S3)`

### Step S4 — Cockpit / CLI / MCP learn to read the new substrate

**Goal:** the operator-facing surfaces become substrate-aware. They can address either the legacy store or the new mesh, defaulting to the new mesh once it carries the bulk of ingested data.

**Pre-conditions:**
- S3 merged. The new substrate is fully readable.

**Deliverables:**
- A unified `KnowledgeBackend` abstraction in `src/theogony/api/backends.py` with two implementations: `LegacyBackend` (reads from `src/theogony/stores/`) and `MeshBackend` (reads from `src/theogony/mesh/`). The CLI / MCP / Cockpit talk to a `KnowledgeBackend`.
- A configuration switch (`theogony.backend = "legacy" | "mesh"`, defaulting to `mesh` if any mesh data exists, else `legacy`).
- MCP tool implementations (`pantheon_ask`, `pantheon_node`, `pantheon_status`, etc.) wire through the selected backend.
- Cockpit (`src/theogony/cockpit/`) reads node and edge counts, source-anchor hierarchies, and audit-ledger entries from the selected backend. Display additions: tier of each node, eager-linking signal that created it (Q-ID / description / tag / emergent), source-anchor source-of-extraction.
- Tests:
  - `tests/mesh/test_api_backends.py` — both backends implement the protocol; `MeshBackend` returns the expected shapes.
  - `tests/mesh/test_mcp_mesh.py` — `pantheon_ask` against the mesh backend returns a citation-rich answer.
  - `tests/cockpit/test_cockpit_mesh.py` — Cockpit pages render against the mesh backend.

**Definition of Done:**
- `theogony ask "<question>"` (without the `mesh` infix) routes to the mesh backend when mesh data exists; falls back to legacy otherwise.
- `theogony mcp` exposes the unified surface.
- `theogony cockpit serve` shows both legacy and mesh views and defaults to mesh once any mesh data exists.
- All existing surface tests still pass against the legacy backend (no regressions).
- All new surface tests pass against the mesh backend.

**Scope cap:**
- No removal of the legacy code. The legacy backend is still selectable.
- No new MCP tools. Existing tools route through the backend abstraction.
- No new Cockpit panels. Existing panels gain mesh-aware rendering.

**PR title:** `feat(api+cockpit+mcp): backend abstraction; mesh as new default when present (S4)`

### Step S5 — Full Oneiros tick: consolidation, splits, pathology surveillance, therapy, three-factor RL

**Goal:** the new substrate gets the full Oneiros tick — every phase from `MESH_IMPLEMENTATION.md` §"Oneiros — implementation order" steps 1–17 is implemented and exercised. Three-factor reinforcement learning is wired through retrieval feedback. Argus's substrate-level pathology surveillance produces findings; staged therapy applies them.

**Pre-conditions:**
- S4 merged. The full retrieval and surface stack is mesh-aware.

**Deliverables:**
- `src/theogony/mesh/runtime/consolidation.py` — Oneiros consolidation: Tier-0 chunk clusters promote to Tier-1; entity-candidate merging when convergent evidence accumulates; description regeneration via LLM call with audit.
- `src/theogony/mesh/runtime/splits.py` — sub-node splits with effective-resistance preservation (`w_HS = Σ w_i`, `w_i' = w_i / (1 - p_i)`), `n ≥ 8` minimum cluster size.
- `src/theogony/mesh/runtime/renormalisation.py` — global homeostatic renormalisation per `MESH_SUBSTRATE.md` §"Global homeostatic renormalisation".
- `src/theogony/mesh/runtime/pruner.py` — resource-pressure-triggered pruner per `MESH_SUBSTRATE.md` §"Pruning".
- `src/theogony/mesh/runtime/pathology.py` — Argus's five topological symptom detectors per `MESH_SUBSTRATE.md` §"The five topological symptoms of a thought-spiral".
- `src/theogony/mesh/runtime/therapy.py` — five staged therapies per `MESH_SUBSTRATE.md` §"Five staged therapies", with Mendel-risk weighing logged before invasive stages.
- `src/theogony/mesh/runtime/feedback.py` — three-factor reinforcement learning per `MESH_RETRIEVAL.md` §"Three-factor reinforcement learning" with eligibility traces.
- `src/theogony/mesh/agents/argus.py`, `athene.py`, `chronos.py`, etc. — the agent-driven cleanup roles per `MESH_SUBSTRATE.md` §"Agent-driven cleanup". These can be small wrappers if their existing implementations under `src/theogony/agents/` are already sound; otherwise rewrites.
- The full 17-step Oneiros tick implemented in `src/theogony/mesh/runtime/oneiros_tick.py`, replacing the minimal version from S1.
- Tests for every new phase. Pathology surveillance tested against the worked-example pathology cases.

**Definition of Done:**
- `pytest -q tests/mesh/` is fully green including the new phases.
- A long-running ingestion (`theogony mesh ingest 43497 --sentences 1000`) followed by 20 retrieval passes and 5 Oneiros ticks produces a substrate with: at least one consolidation event, at least one Hebbian-strengthened edge above its initial weight, at least one renormalisation correction logged, and no spurious pathology findings against a non-pathological corpus.
- The three-factor RL feedback path produces visible edge-weight differentials between LLM-rated-positive and LLM-rated-negative activations after sufficient sampling.

**Scope cap:**
- No federation. Federation-aware dynamics remain Gen-3+ work per the substrate doctrine.
- No multi-modal extension. The substrate is text + Q-IDs only. Multi-modal entry remains an open path per `MESH_RETRIEVAL.md` §"Multi-modal extension".
- No parallel-universe / Lance-branch experimentation. That capability is preserved by the design but not exercised in S5.

**PR title:** `feat(mesh): full Oneiros tick — consolidation, splits, pathology, therapy, three-factor RL (S5)`

### Step S6 — Deprecation and removal of the legacy path

**Goal:** the legacy code is removed from the repository. `src/theogony/core/model.py` is gone or completely rewritten against the MESH schemas. The repository contains only the mesh-doctrine substrate.

**No legacy data migration.** The data currently held in the legacy LanceDB store was produced by the stateless Kadmos v1 extractor — single embedding per node, no frame vector, no eager-linking discipline, no source-anchor entities, no descriptions on the doctrine's terms. It is structurally and qualitatively below what the MESH substrate expects. Migrating it would propagate the failure mode it was built to escape. The legacy data is therefore **discarded** at S6, not migrated. The new substrate is populated fresh through Kadmos v2 ingestion runs (S2 onward), starting from the same source corpora.

**Pre-conditions:**
- S5 merged. The new substrate has been running in production-like usage for an operator-defined cooldown period (recommended: 30 days). No critical functionality lives only on the legacy path.
- The mesh has been seeded with the corpora the operator needs (e.g., Wikipedia article subset, Project Gutenberg books) via `theogony mesh ingest` runs. The substrate is queryably useful before deletion of the legacy path.
- The PHX backlog migration (parallel etappe, see below) is complete — all carry-forward tickets either resolved or properly translated to the new backlog.

**Deliverables:**
- Deletion of:
  - `src/theogony/core/model.py` (the old `KnowledgeNode`, `KnowledgeEdge`, `NodeType` enum, `EpistemicStatus` enum, etc.). Anything in `core/` that the mesh layer needs gets moved into `src/theogony/mesh/`. `src/theogony/core/` may then go away entirely or shrink to genuine cross-cutting utilities.
  - `src/theogony/stores/memory.py` and any legacy Neo4j store remnants.
  - `src/theogony/memory/oneiros.py`, `morpheus.py`, `pheromone_decay_phase.py`, `depth_band_phase.py`, etc. — these are absorbed into the new mesh runtime. Any genuine functionality they carried (pheromone trails, depth bands) either moves into the mesh runtime as a tier-modulated dynamic or is filed as obsolete.
  - The `LegacyBackend` from S4. Only `MeshBackend` remains.
  - All `tests/` files that test the legacy schema. They die with their code.
  - The legacy LanceDB data directory (if any operator state persists from Gen-1 runs). The operator is responsible for deleting their own data directories; the repository deletes the *code* that wrote them.
- Rename `src/theogony/mesh/` → `src/theogony/` (if appropriate at this point; the strangler-fig's host has been replaced).
- Drop the `theogony mesh ...` subcommand prefix everywhere; the unprefixed commands address the mesh because there is nothing else.
- `docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md` adds a final banner: "this plan is fully superseded; the migration is complete as of <date>".

**Definition of Done:**
- `git grep "KnowledgeNode\|NodeType\|EpistemicStatus\|EdgeType\|Layer.*ephemera\|class .*KnowledgeEdge"` returns no matches in `src/` and `tests/`.
- The entire test suite is green and consists exclusively of tests against the MESH schemas.
- `theogony ask "What is the Chronik?"` runs correctly with no legacy code in the call chain.
- The repository contains zero references to Neo4j outside of historical-context blocks in docs.
- This document gets a final banner: "S6 complete; migration done as of <date>". The plan is then archival.

**Scope cap:**
- No new features in S6. It is a removal PR (likely many small removal PRs, but no feature additions).

**PR title:** `chore(mesh): remove legacy substrate; mesh is the substrate (S6)`

---

## Parallel etappe — PHX backlog migration

The Phoenix Backlog migration runs in parallel with the strangler-fig steps above. It should be started between S1 and S2, and completed before S5 (because S5's full Oneiros tick relies on the substrate's doctrine being uncluttered by stale tickets).

### The plan

1. **Create `phoenix-backlog/archive/`.** Move all 52 existing YAMLs there. The catalogue file `docs/PHOENIX_BACKLOG.md` stays in place for now with a banner: "this catalogue reflects the pre-MESH state; for the new backlog see [link]."
2. **Walk each archived ticket, label exactly one of three:**
   - **carry-forward** — the ticket addresses a real concern that survives the migration. A new ticket in the new backlog is filed with a `migrated_from: PHX-XXXX` link. The new ticket is reframed against the MESH triplet's vocabulary.
   - **obsolete** — the ticket addresses a concern that no longer applies (e.g., tickets about the Neo4j store, about the codebook edge compression that the MESH doctrine does not use, about old retrieval strategies that diversified injection has absorbed). The archived YAML gets a `status: obsolete_since_mesh_pivot` field and a one-line reason; no new ticket is filed.
   - **absorbed** — the ticket's concern is now part of the MESH triplet itself (e.g., the "Activation Engine v1" ticket is absorbed by `MESH_RETRIEVAL.md`'s diversified-injection spec). The archived YAML gets `status: absorbed_into_mesh_doctrine` with a pointer to the relevant section.
3. **New backlog starts at PHX-1000.** The gap between PHX-0074 and PHX-1000 is deliberate — it signals the doctrine boundary to anyone reading. The first new ticket (PHX-1001 or similar) is the meta-ticket "MESH migration in progress" with this plan as its description.
4. **Rename or replace `docs/PHOENIX_BACKLOG.md`.** The new catalogue is `docs/PHOENIX_BACKLOG.md` (same name, fresh content). The legacy catalogue moves to `docs/PHOENIX_BACKLOG_LEGACY.md` for historical reference.
5. **Update `phoenix-backlog/README.md`** with the new numbering convention and the "every ticket post-migration must be doctrine-conformant to the MESH triplet" rule.

### Concrete deliverables

- `phoenix-backlog/archive/` populated with all 52 legacy YAMLs.
- A migration audit CSV at `phoenix-backlog/archive/MIGRATION_AUDIT.csv` with one row per legacy ticket: `id, title, decision, new_ticket_id_or_null, reason`.
- New backlog catalogue at `docs/PHOENIX_BACKLOG.md`.
- Legacy catalogue at `docs/PHOENIX_BACKLOG_LEGACY.md`.
- Updated `phoenix-backlog/README.md`.

### Definition of Done

- Every one of the 52 archived tickets has a `decision` row in the audit CSV.
- The new catalogue contains zero references to legacy schema concepts (`KnowledgeNode`, `EpistemicStatus`, etc.) except where the ticket is explicitly about the legacy-to-mesh migration.
- No new ticket is filed under the legacy numbering space.

---

## `IMPLEMENTATION_PLAN_GEN1.md` retirement (done)

Completed alongside the landing of this plan (2026-05-13):

1. ✅ Renamed to [`IMPLEMENTATION_PLAN_GEN1_LEGACY.md`](IMPLEMENTATION_PLAN_GEN1_LEGACY.md). Git history follows the rename via `git mv`.
2. ✅ A "superseded" banner has been added at the top pointing every reader at this migration plan.
3. ✅ Nothing below the banner has been edited. The reconciliation blocks are the audit trail of how the project got here.

Every reference to `IMPLEMENTATION_PLAN_GEN1.md` from operative documents (AGENTS, ROADMAP, prompts) has been updated to point either at this plan (for active guidance) or at the legacy file (for historical reference). References from already-archived contexts — `docs/etappes/*_brief.md`, `docs/HISTORICAL_MD_INTENTIONALLY_UNTOUCHED.md`, `phoenix-backlog/archive/*.yaml` — have been left intact, because they document the project at a moment when the old name was correct.

---

## What this plan deliberately does NOT do

- **No sprint plan.** This plan defines PR-sized steps, not weeks. Each step takes as long as it takes to land it correctly. A new agent can pick up step Sn knowing exactly what to deliver.
- **No hyperparameter prescription.** Saturation cap exact numbers, decay exponent exact value, MMR `λ` value — these live in the MESH triplet or are emergent from tuning. The plan binds the *shape*, not the *numbers*.
- **No agent-role redesign.** Argus, Athene, Morpheus, Iris, Mnemosyne stay. Their substrate-side roles are specified by the MESH triplet. The current `src/theogony/agents/` directory will be partially absorbed into `src/theogony/mesh/agents/` during S5; what survives is the role and its prompt.
- **No surface redesign.** The CLI, MCP, and Cockpit keep their existing operator-facing shapes. Only their backends change, transparently.
- **No federation or multi-modal work.** Both are preserved as substrate affordances by the doctrine. Both are explicitly out of scope for this migration. They become tractable only after S6.

---

## Forbidden patterns during the migration

Five patterns that will break the migration if a contributor falls into them. Each is forbidden:

1. **Do not partially migrate the schema.** Either a node lives fully in the new `ChunkNode` / `ConsolidatedNode` shape or it stays in the legacy `KnowledgeNode`. There is no halfway. The strangler pattern works because the two trees are *separate*, not because they share fields.

2. **Do not skip the audit ledger.** Every node creation, edge creation, eager-linking decision, consolidation, split, removal, therapy action, and prune must write a structured audit record. The ledger is the only way the substrate can honestly answer "what did you forget and why?" — and the only way the migration itself can be unwound if a step turns out wrong.

3. **Do not store raw source text on nodes.** `raw_text_ref` is a pointer only — an opaque identifier like `"gutenberg_43497#p17"` or `"wikipedia:Q336997"`, **never the text it points at**. The prohibition is broad: *raw source text* includes extracted paragraph bodies, multi-sentence source passages, Wikipedia article bodies, Gutenberg paragraph contents, and any other multi-line text that originated outside the substrate. `description`, `relation_descriptor`, `tags`, `source_url` are summary metadata and are permitted — but `description` stays bounded (typically ~200–500 chars, **never a paragraph body**). Source-anchor entities reference URLs / DOIs / ISBNs; they do not embed the source body. When a regeneration of `description` requires the original source text, the look-up happens **off-substrate** via `raw_text_ref` (e.g. an external Wikipedia dump, a Gutenberg file, or an HTTP fetch) and only the resulting bounded `description` lands in the mesh — never the source body itself.

4. **Do not break the legacy path before the new path covers its function.** S1–S5 must each preserve the legacy CLI / MCP / Cockpit behaviour against the legacy backend. Only S6 deletes legacy code, and only after the mesh has covered everything the legacy path delivered.

5. **Do not "while we're at it" scope-expand.** A PR for step S2 does not introduce changes to retrieval. A PR for step S4 does not add new MCP tools. Every PR's scope cap is binding. Out-of-scope ideas become new tickets in the new PHX backlog; they do not piggyback on the migration step.

---

## The first concrete PR

A new agent picking up this work should open the first PR as follows.

**Branch name:** `feat/mesh-s1-substrate-skeleton`

**Branch source:** `main`, freshly synced from `origin/main` per `AGENTS.md` §"Branch per change".

**Files to create:**

```
src/theogony/mesh/__init__.py
src/theogony/mesh/schemas.py
src/theogony/mesh/storage/__init__.py
src/theogony/mesh/storage/nodes.py
src/theogony/mesh/storage/edges.py
src/theogony/mesh/storage/audit.py
src/theogony/mesh/runtime/__init__.py
src/theogony/mesh/runtime/spreading.py
src/theogony/mesh/runtime/oneiros_tick.py
src/theogony/mesh/cli.py

tests/mesh/__init__.py
tests/mesh/test_schemas_roundtrip.py
tests/mesh/test_storage_lance.py
tests/mesh/test_spreading_activation.py
tests/mesh/test_oneiros_tick_minimal.py
tests/mesh/conftest.py
```

**Files to modify (minimal touch):**

```
src/theogony/cli.py                        # add `mesh` subcommand group, route to mesh.cli
pyproject.toml                              # add any new test-only or runtime deps if needed
```

**Files NOT to touch in this PR:**

```
src/theogony/core/                          # legacy schema stays
src/theogony/stores/                        # legacy stores stay
src/theogony/memory/                        # legacy Oneiros stays
src/theogony/agents/                        # legacy agents stay
src/theogony/api/, mcp/, cockpit/           # surfaces unchanged
tests/<everything-not-tests/mesh/>          # legacy tests stay green untouched
```

**Schemas in `schemas.py` follow `MESH_SUBSTRATE.md` §"Node anatomy" and §"Edge anatomy" verbatim.** Names must match: `ChunkNode`, `ConsolidatedNode`, `Edge`, `EdgeMetadata`, `SourceProvenance`, `QIDTag`, `PIDTag`. `model_config = ConfigDict(extra="forbid")`. ULID for IDs. No additional fields beyond what the substrate doctrine lists.

**Required green CI:**

- `ruff format --check`
- `ruff check`
- `mypy src/theogony/mesh`
- `pytest -q tests/mesh`
- `pytest -q` (the full suite, including legacy — proves no regression)

**PR body (template the new agent should fill):**

```
## Summary
- Introduces the MESH substrate skeleton under `src/theogony/mesh/` per
  `MESH_MIGRATION_PLAN.md` §"Step S1 — New substrate skeleton".
- New schemas (`ChunkNode`, `ConsolidatedNode`, `Edge`, `EdgeMetadata`) follow
  `MESH_SUBSTRATE.md` §"Node anatomy" and §"Edge anatomy" verbatim.
- LanceDB storage layer, PyTorch sparse CSR edge tensor + COO delta buffer,
  minimal Oneiros tick (decay + Hebb + saturation only), single-query Spreading
  Activation.
- New CLI subcommand `theogony mesh status`. Legacy CLI subcommands unchanged.

## Doctrine alignment
- `MESH_SUBSTRATE.md` — schemas, ID discipline (`ULID`), `extra="forbid"`.
- `MESH_IMPLEMENTATION.md` — Hot/Warm/Cold tiering deferred to step Sn; this
  PR uses Warm-only LanceDB + in-RAM CSR.
- `MESH_RETRIEVAL.md` — diversified injection deferred to S3; this PR's
  Spreading Activation uses simple top-K seeding for the smoke test only.

## Scope cap (per the migration plan)
- No Kadmos v2. (S2)
- No diversified injection or sub-mesh signature. (S3)
- No Cockpit / MCP integration. (S4)
- No consolidation / splits / pathology / therapy / RL. (S5)
- No deletion of legacy code. (S6)

## Test plan
- `pytest -q tests/mesh` — green
- `pytest -q` — green (no legacy regression)
- `theogony mesh status` — runs against a fresh mesh, prints structured summary
- `theogony ask "What is the Chronik?"` — still works against the legacy path
```

**Reviewer-facing local verification commands:**

```bash
ruff format && ruff check && mypy src/theogony/mesh
pytest -q
theogony mesh status
theogony ask "What is the Chronik?"
```

---

## How we know we are done

The migration is complete when **all** of the following hold:

1. `git grep -E "KnowledgeNode|NodeType|EpistemicStatus|EdgeType|Layer.*(ephemera|mneme)|KnowledgeEdge"` returns zero matches in `src/` and `tests/`.
2. The test suite is green and consists exclusively of tests against the MESH schemas.
3. `theogony ask "What is the Chronik?"` runs correctly with no legacy code in the call chain.
4. The CLI, MCP server, and Cockpit have no `--backend legacy` switch, no `theogony mesh ...` subcommand prefix, no `LegacyBackend` class.
5. `docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md` is the only reference to the legacy plan; the canonical plan is the MESH triplet plus this migration plan.
6. All 52 legacy PHX tickets have a final disposition in `phoenix-backlog/archive/MIGRATION_AUDIT.csv`.
7. The new Phoenix backlog has no `migrated_from: PHX-XXXX` tickets in `status: open` that would block deletion.
8. This document is updated with a final banner: `## Status: complete — migration finished on <date>`. From that point on, this document is archival like `IMPLEMENTATION_PLAN_GEN1_LEGACY.md` is now.

When all eight hold, the strangler-fig has fully replaced the host. The Chronik runs on the MESH triplet alone.

---

## One-line summary

> **Build the new substrate next to the old one; migrate surfaces step by step; let the host die only after the strangler is a complete tree.**
