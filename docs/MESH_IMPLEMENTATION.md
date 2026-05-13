# Mesh Implementation

**Status:** implementation guidance for the mesh substrate. Specifies the storage layer, concurrency model, hardware tiers, and runtime operators that satisfy the doctrine in [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md).
**Companion docs:** [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) (the doctrine; this document realises it), [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) (the use), [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) (the architectural commitments this implementation realises and, in places, refines — LanceDB + PyTorch, Spreading Activation as primitive), [`CHRONIK_SCALE.md`](CHRONIK_SCALE.md) (the scale-tier numbers this document maps onto).
**Audience:** Talos and any builder agent who writes substrate code.

**Precedence.** Together with [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) and [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md), this document is the **operative substrate doctrine**. Where the substrate triplet conflicts with older doctrine documents on substrate-layer behaviour, runtime, or use, the substrate triplet is operative.

---

## Why this doc exists

[`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) specifies *what* the substrate must do. This document specifies *how* the current generation of hardware can be made to do it efficiently. The two are deliberately separated: the doctrine should outlive any particular storage choice, while the implementation guidance is expected to evolve as hardware economics shift.

This document is therefore advisory more than binding. Where it is binding, it says so. Where alternatives are open, it names them.

---

## The shape of the work

The substrate's complete operational surface is small. Only a few primitive operations matter:

| Operation | Frequency | Cost dominated by |
|---|---|---|
| Append a chunk node | Per ingest event | Vector encode, Lance write |
| Append an edge | Per Hebbian trigger | Index write to delta buffer |
| Hebbian update on existing edges | Per Spreading Activation | RMW on delta buffer entries |
| Spreading Activation propagation | Per query | Sparse matrix-vector multiplication (SpMV) |
| Decay tick (super-linear) | Per Oneiros tick | Element-wise tensor op |
| Global renormalisation | Per Oneiros tick (conditional) | Element-wise tensor scale |
| Sub-node split | Per Oneiros tick (conditional) | Local restructure + audit log |
| Pruning | Under resource pressure | Sort + truncate |
| Consolidation (Tier promotion) | Per Oneiros tick (conditional) | Cluster detection + LLM call for description |

Spreading Activation is the operation that runs many times per second under load; everything else is either append-only at insertion or batched into Oneiros ticks. The implementation should optimise heavily for the first; correctness and recoverability matter more than speed for the rest.

The fact that Spreading Activation reduces to **sparse matrix-vector multiplication** is the central engineering reason the substrate works. SpMV is one of the most thoroughly studied primitives in numerical computing, with mature implementations across CPU, GPU, and TPU. The substrate inherits all that work for free.

---

## The three-tier physical layout

The substrate's contents naturally separate into three temperature tiers. Treating them as the same storage class wastes either money or latency.

| Tier | Content | Physical home | Access pattern |
|---|---|---|---|
| **Hot** | Working set: nodes activated in the last *N* queries; their immediate neighbourhood; the active sub-mesh of any in-flight Spreading Activation | Dense PyTorch tensors in RAM (or GPU VRAM) | Random access, microsecond latency |
| **Warm** | Bulk of the substrate: most nodes, most edges, current weights | LanceDB tables (columnar, mmap-friendly), backed by NVMe | Batched read, millisecond latency |
| **Cold** | Historical Lance versions, pruned-but-not-deleted records, audit trail of consolidations / splits / therapy events | LanceDB versioned snapshots on commodity SSD or object storage | On-demand only; latency tolerated |

Movement between tiers is automatic and statistical, not declarative:

- A node that fires above threshold during recent activations is automatically promoted to Hot on its next access.
- A Hot node that has not fired during the last *N* activations falls back to Warm.
- Cold tier content stays cold until something explicitly references a historical version (e.g., for an audit query, for federation reconciliation, for a research-mode time-travel run).

Hot and Warm both carry the same data shape — the same Pydantic schemas from [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md). Hot is a cache; Warm is the source of truth. Cold is the audit ledger.

---

## Storage choices

### Nodes — LanceDB

**Why Lance.** Columnar storage means a Spreading Activation pass can read just the vector columns it needs, not whole node rows. Built-in versioning gives the substrate atomic snapshots — every Oneiros tick produces a new version, old versions remain queryable. Lance's per-column HNSW index gives sub-millisecond approximate nearest-neighbour for the per-vector retrieval that diversified injection requires (see [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md)). Memory mapping means cold nodes cost no RAM until something touches them.

**Layout.** One table per node tier, broadly. In practice, two tables suffice — `chunk_nodes` (Tier 0) and `consolidated_nodes` (Tier 1+) — with the `consolidation_tier` integer column on the second table partitioning the rows. Per-vector columns receive their own HNSW indices; metadata columns (counters, timestamps, `qids`, `description`) are simple typed columns with the indexing Lance would default to.

**Vector dimensionality.** The default semantic vector is 1024-dimensional (BGE-M3 class) because it is the smallest dimensionality at which contemporary embeddings preserve enough nuance for cross-domain retrieval, and BGE-M3 specifically supports both dense, sparse, and multi-vector retrieval modes if the substrate later wants to exploit them. Smaller models (384-dim, MiniLM class) are acceptable for prototype / laptop deployments; the substrate's mechanics do not care.

The frame vector is small (default 64-d) and exists to be cheap. Frame routing during Spreading Activation reads it on every hop; making it small keeps that overhead negligible.

The structural and temporal vectors are populated only on Tier-1+ consolidated nodes and only when consolidation has run enough times to have meaningful values. They are nullable.

### Edges — PyTorch sparse + delta buffer + Lance metadata table

Edges are the substrate's high-volume data, and they carry two qualitatively different kinds of information:

- **Quantitative fields** (source, target, weight, decay tier, frame consistency) — read on every Spreading Activation hop, must be GPU-batched for SpMV/SpMM.
- **Optional semantic descriptors** (`relation_descriptor`, `relation_kind`, `description`, `pids`, `creation_context`) — read only when an agent inspects an edge during repair, when retrieval results are formatted for a consumer, or when a query specifically targets edges of a certain kind. Not on the SpMV hot path.

Storing both in the same structure forces a wrong choice: a sparse tensor is wrong for rich metadata; a Lance row-per-edge is too slow for SpMV. The substrate uses **three structures, kept in step**:

1. **Stable CSR sparse tensor** (the SpMV runtime). PyTorch sparse CSR. Holds only the quantitative fields needed for propagation: `(source, target, weight, decay_tier, frame_consistency)`. Built by Oneiros at the end of each tick. Loaded into RAM (Warm tier) or GPU (Hot tier) directly. SpMV / SpMM run natively against this.

2. **Append-only COO delta buffer** (the write path). Hebbian updates and new-edge additions during regular operation go here as `(source_id, target_id, weight_delta, optional_metadata_pointer)` tuples. Lock-free append with atomic-fetch-and-add or lock striping. Merged into the stable CSR at every Oneiros tick. Never more than a few thousand entries.

3. **Lance edge-metadata table** (the rich-metadata surface). One Lance row per edge that carries any optional semantic descriptor. Edges that are pure Hebbian co-firings with no descriptor are *not* in this table. Schema:
   ```python
   class EdgeMetadata(BaseModel):
       model_config = ConfigDict(extra="forbid")
       source_id: ULID
       target_id: ULID
       relation_descriptor: str | None = None
       relation_kind: str | None = None
       description: str | None = None
       pids: list[PIDTag] = []
       creation_context: str | None = None
   ```
   Updated at Oneiros tick boundaries, in lock-step with the CSR rebuild. Versioned alongside everything else in Lance.

**Read paths.** Spreading Activation reads only the CSR (and the merged delta) — it never touches the metadata table on the hot path. Agents performing repair, deduplication, contradiction resolution, or richly-formatted retrieval consult the metadata table by `(source_id, target_id)` lookup. Because most edges carry no metadata, the metadata table is much smaller than the edge tensor — typically 10–30% of edges have any descriptor populated, depending on extraction richness.

**Storage cost.** With ~10⁹ edges in a Wikipedia-scale substrate, the CSR tensor is ~10–20 GB (FP16 weights + int32 indices). The metadata table at 30% population × ~200 bytes per row is ~60 GB on Lance — significant but manageable. For a laptop substrate (10⁸ edges), both structures fit comfortably in tens of GB.

**Write path.** Insertion of a new edge:
1. Append to the COO delta buffer with `(source, target, weight)` and an optional pointer to a metadata payload.
2. If the edge carries metadata, the payload is appended to a separate metadata-write buffer.
3. Both buffers drain at the next Oneiros tick: the CSR is rebuilt with quantitative fields; the metadata table is updated atomically with the new descriptors. Lance commits a single new version; readers cut over.

The pattern is the standard MVCC implementation for high-write graph systems with a sidecar metadata store. It scales to millions of writes per second while keeping reads fully consistent against a snapshot, and lets the SpMV hot path stay narrow without sacrificing the rich-metadata affordance the substrate doctrine commits to.

### Anchor nodes — separate index

Per [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Splits in the wild — also: temporal nodes are special", anchor nodes (years, geo cells, languages, genome positions) live in a different storage class. They are immutable, very-high-cap, do not participate in decay or Hebbian updates. Implementation: a small Lance table (`anchor_nodes`) plus an inverted index mapping each anchor to the chunks that reference it via the chunk's `temporal_anchor` / `geo_anchor` / etc. fields. Range queries over anchors (e.g., "what happened between 1900 and 1910?") use the anchor index, not graph traversal.

### Audit ledger — append-only Lance

Every non-trivial Oneiros operation — consolidations, tier promotions, sub-node splits, therapy applications, prunings — writes a structured record to an append-only audit table. This is the substrate-side analogue of the `Finding` records in [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md). Records are never modified. Lance's versioning means historical audit reads are cheap and consistent.

---

## Concurrency model

The substrate is read-heavy. Production load looks like many concurrent Spreading Activation passes against a slowly-updating mesh. The concurrency design follows from that profile.

### Reads — snapshot isolation (MVCC)

Every Spreading Activation pass pins a Lance version when it begins, and reads against that version for the entire pass. The pin is cheap; releases are automatic at pass end. There is no read locking. Unlimited parallel reads are supported by construction.

This means that an ongoing Oneiros tick that is rebuilding the stable CSR cannot affect any Spreading Activation already in flight. The CSR rebuild produces a *new* version; ongoing reads continue against the old version; new reads after the rebuild see the new version.

### Writes — buffered, not synchronous

Hebbian updates from a Spreading Activation pass are accumulated in a per-pass buffer and flushed to the delta buffer at pass end. This avoids contention during the pass itself. The flush is a single append batch, not many small appends.

Insertions of new chunk nodes are direct Lance appends. Lance handles concurrent appends lock-free (each writer claims a fragment).

### Oneiros — serialised, snapshot-publishing

Oneiros runs as a single-writer process (per substrate instance — federations are per-instance Oneiros) on a configurable schedule. Within a tick:

1. Read the current Lance version snapshot.
2. Drain the delta buffer.
3. Apply decay, Hebbian merges, renormalisation, consolidations, splits, prunings, therapy actions, in well-defined order.
4. Build the new stable CSR.
5. Write the new Lance version atomically.
6. Publish the new version pointer for subsequent readers.

Oneiros may take seconds to minutes per tick at scale. During that time, Spreading Activation continues unimpeded against the old version. This is the substrate's basic time-decoupling: thinking on substrate state is decoupled from updating substrate state.

### What is forbidden

- **Long-lived locks.** No mutex held across more than a single short critical section (lock-free fetch-and-add is preferred). Long locks block Spreading Activation; that is unacceptable.
- **Transactional multi-edge updates.** The delta buffer is single-edge atomic; there is no equivalent of an SQL `BEGIN ... COMMIT`. Cross-edge consistency is provided by the snapshot/Oneiros boundary, not by transactions during reads.
- **Reads that mutate the version they read from.** Hebbian-write-back happens through the delta buffer, not by modifying the snapshot in place. The snapshot is read-only for the lifetime of the read pass.

---

## Spreading Activation as batched SpMV

The single most important runtime affordance of the substrate is that **K concurrent Spreading Activation queries fold into one batched SpMV**.

For a single query, Spreading Activation is `x_{t+1} = damping · A · x_t + injection`, where `A` is the edge tensor and `x_t` is the current activation vector. This is one SpMV per propagation step; convergence happens within a small fixed number of steps (3–5 typically; the existing PoC uses 3 hops).

For K queries with K independent activation vectors, you can stack the vectors as a matrix `X` of shape `(N, K)` and execute `X_{t+1} = damping · A · X_t + Injection`. This is one SpMM (sparse matrix × dense matrix) per propagation step, regardless of K. Modern GPU sparse libraries (cuSPARSE on NVIDIA, MPS sparse ops on Apple, ROCm sparse on AMD) handle this efficiently.

The practical consequence: **Spreading Activation latency is dominated by mesh size and propagation depth, not by the number of concurrent queries up to the GPU memory limit.** A modest production server with an 80 GB H100 can hold a multi-billion-edge tensor and serve hundreds of concurrent activations within single-digit-millisecond latency per pass. This is the architectural reason the substrate is preferable to pointer-chasing graph databases: SpMV/SpMM scale, pointer chasing does not.

### Damping and stop conditions

The damping factor (default ≈ 0.5) ensures activation decreases per hop. Combined with a minimum-activation threshold (default ≈ 0.05) per node, propagation naturally halts; the result is the activated sub-graph (the **Constellation**, in [`GLOSSARY.md`](GLOSSARY.md) terms).

A maximum hop count (default 3, never above 5 for production queries) prevents pathological cases from running unbounded. The hop cap is an engineering safety net; correctness comes from damping + threshold.

### Frame routing

Frame routing during Spreading Activation modifies the SpMV slightly: edges contribute to the propagation only when their `frame_consistency` with the current frame context exceeds a threshold. Implementation: a per-frame mask is computed for the active edges, and the SpMV becomes `(A * mask) · X`. The mask is a sparse boolean tensor; `A * mask` is element-wise. On GPU this fuses with the SpMV kernel without extra memory traffic.

### Diversified seeding

The seeds for Spreading Activation are not "top-K nearest to the query" — see [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Diversified injection" for the full rule. The implementation uses the standard MMR algorithm over the per-vector ANN results, plus weight-class stratification by sampling from per-tier index sub-collections. The total seed count is typically 20–100, well within batched-SpMV economics.

---

## Oneiros — implementation order

The Oneiros tick is a sequence of operations. Order matters: doing them in the wrong order produces inconsistent intermediate states.

1. **Pin the input snapshot.** All read operations during the tick reference this version.
2. **Drain the delta buffer.** All Hebbian updates accumulated since the last tick are merged into a working copy of the edge tensor.
3. **Apply decay** (super-linear, tier-modulated). Element-wise on the working tensor.
4. **Apply renormalisation** (conditional on drift threshold). Element-wise scale on the working tensor.
5. **Apply pending agent-driven cleanup actions.** Drain the queue of `MergeProposal`, `RemovalProposal`, `ContradictionFinding`, and `RedundancyProposal` records emitted since the last tick by Argus, Athene, or other agents. For each, apply the proposed merge / removal / contradiction-marking / consolidation, with full audit-ledger entries (the original finding, the agent's evidence trail, the action taken).
6. **Compute consolidation candidates.** Identify Tier-0 chunk clusters that have reliably co-fired across many distinct contexts. (Note: many Tier-1 entity nodes already exist eagerly from Kadmos's Q-ID linking — see [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Why two tiers — and how identity actually gets committed". This step finds *additional* Tier-1 candidates from chunks that did not link eagerly, and proposes promotions to higher tiers for established Tier-1 nodes.)
7. **Apply consolidations.** Create new Tier-1 nodes for emergent clusters; merge entity-candidates with confirmed identity into existing entities; rebuild edges from member chunks; generate or regenerate descriptions via small LLM calls (cached aggressively to avoid redundant calls); flip `is_candidate` to `False` where convergence is reached.
8. **Compute saturation pressure.** For each node above its tier cap (in either count or weight), determine which edges to evict.
9. **Apply saturation evictions.** Remove the displaced edges, append audit-ledger entries.
10. **Compute split candidates.** For each near-saturated hub, run cluster detection on its outgoing edges. If a clean split is available (n ≥ 8 per cluster, themes are well-separated), propose the split.
11. **Apply splits** with effective-resistance preservation (per [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Sub-node splits"). Audit each split.
12. **Compute pathology samples.** Argus's substrate-level surveillance: sample regions, compute the five topological symptoms, emit `Finding` records.
13. **Apply therapy actions** that have crossed escalation thresholds since the previous tick. For Stage 4 and Stage 5 actions, log the Mendel-risk weighing alongside the topological evidence.
14. **Refresh `node_potential_cache` and `activation_entropy`** for all touched nodes.
15. **Write the new audit-ledger entries** for everything done in this tick.
16. **Build the new stable CSR tensor.** Compress the working edge tensor back into CSR format for the next read epoch.
17. **Publish the new Lance version atomically** (Lance commit). The new version becomes the default for subsequent readers.

Steps 5, 12, 13 are agent-driven (Argus, Athene, and other Pantheon agents emit findings; Oneiros consumes them). They execute inside the Oneiros tick because they need consistent access to the mesh state, but the *decisions* about what to merge / remove / mark / treat are made by the agents, not by Oneiros.

Each step writes structured `OneirosTickReport` substeps, which become first-class data alongside the substrate they describe. The tick report is the human-and-agent-readable summary of "what changed and why" — including the audit trail of every agent-driven cleanup action and every destructive therapy with its Mendel-weighing.

### Tick frequency

The tick frequency is operator-configurable. Reasonable defaults by scale:

| Substrate scale | Tick interval |
|---|---|
| PoC (< 10⁵ nodes, single laptop) | Every few minutes |
| Tier 0 / Gen 1 dev (< 10⁶ nodes) | Every 15–30 minutes |
| Tier 1 / Wikipedia EN (~10⁸ nodes) | Hourly |
| Tier 2+ (multi-language Wikipedia, regional) | Several hours, possibly with continuous Argus and on-demand splits |

The tick should never exceed about 5–10% of wall clock at the production tier. If it does, Oneiros's per-tick scope must be cut (e.g., split consolidation across multiple ticks via cursor-based work distribution).

### Pruning trigger

Pruning is triggered separately from the regular tick. Conditions that trip the pruner:

- RAM occupancy of the Hot tensor exceeding `prune_ram_threshold` (default 80% of available)
- p95 Spreading Activation latency exceeding `prune_latency_threshold` (default 50 ms)
- GPU memory occupancy exceeding `prune_gpu_threshold` (default 85% of allocated)

When tripped, the pruner runs immediately (not waiting for the next Oneiros tick). It removes the weakest atrophied nodes and edges until the trigger condition has cleared with margin (default: trigger threshold − 20%). The action is logged to the audit ledger.

The pruner has no other policy. It does not look at content, it does not target therapy-flagged regions preferentially, it does not consult any agent. Per [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Pruning", pruning is the only operation in the substrate that destroys information, and the safest possible pruning is the simplest possible pruning.

---

## Hardware tier targets

The substrate runs on a wide range of hardware. The following are *target operating points*, not minimums or maximums.

| Operating tier | Node count | Edge count | RAM | GPU | Storage | Notes |
|---|---|---|---|---|---|---|
| **Laptop / PoC** | ≤ 10⁶ | ≤ 10⁸ | 16–32 GB | optional (MPS / consumer GPU) | 256 GB SSD | Hot+Warm+Cold all on one device |
| **Workstation / Gen 1 dev** | ≤ 10⁷ | ≤ 10⁹ | 64–128 GB | RTX 4090 / RTX 6000 (24–48 GB VRAM) | 2 TB NVMe | Hot in VRAM, Warm in RAM, Cold on NVMe |
| **Single server / English Wikipedia** | ~10⁸ | ~10¹⁰ | 256–512 GB | A100 80 GB or H100 80 GB | 4–8 TB NVMe RAID + object storage | Per [`CHRONIK_SCALE.md`](CHRONIK_SCALE.md) Tier 1 |
| **Multi-server / federated tier** | 10⁹+ | 10¹¹+ | distributed | distributed | distributed | Sharding by topic cluster or by tier; out of scope for Gen 1 |

The substrate is designed so that **the same code runs on all four tiers**. The differences are configuration: tick frequency, pruning thresholds, hot-tier capacity, GPU presence. There is no separate "scale-out implementation". This is a deliberate choice — the substrate's most important property is that growth from PoC to production is continuous, not punctuated by rewrites.

For [`CHRONIK_SCALE.md`](CHRONIK_SCALE.md) Tier 1 and below (everything Gen 1 plausibly needs), single-server hardware suffices. Tier 2 and above are explicit Gen 2+ work.

---

## Migration from current PoC state

The PoC at `docs/research/mnlm/poc/` already produces `MeshInput` JSONs that contain chunks with vectors and edges with weights. The migration to the substrate doctrine is incremental, not rewrite-from-scratch:

1. **Wrap the existing chunks as `ChunkNode` instances** — they already have ULIDs (visible in the `mesh_inputs/` filenames). Add the missing fields (`fired_total = 0`, `fired_recent = 0`, etc.) with sensible defaults. The vectors that exist become `semantic_vector`. A `frame_vector` of zeros is acceptable for an initial pass; Kadmos v2 will produce real ones.

2. **Move the chunks into a Lance table** (`chunk_nodes`). Build the per-column HNSW index on `semantic_vector`.

3. **Materialise the existing edges as a PyTorch sparse CSR tensor.** The PoC edges are a starting density; subsequent Hebbian updates and Nous synthesis edges will grow the tensor.

4. **Implement the delta buffer and the basic Hebbian update.** Spreading Activation already runs in some form (per `notes/architecture/vector_native_spreading_activation.md`); this step adds the write-back.

5. **Implement the Oneiros tick framework** — first with stub phases for everything except decay and renormalisation, then progressively filling in consolidation, splits, pathology surveillance, therapy.

6. **Implement the pruner** as the final step, with conservative thresholds. Validate that nothing important is destroyed under expected loads.

Each of these steps is a separate PHX backlog ticket and a separate PR. None of them obviates earlier work; the PoC chunks remain valid `ChunkNode` instances throughout.

---

## What this implementation does not do

A small set of engineering patterns that, if violated, break the implementation's correctness or performance guarantees.

1. **Do not store edges in Lance as one-row-per-edge.** The CSR sparse tensor + delta buffer is the correct structure. Lance is excellent for nodes; it is not the right home for the edge tensor at scale.

2. **Do not implement Spreading Activation as a Python loop over neighbours.** It must be SpMV (or SpMM for batched). A Python loop that pointer-chases the graph one edge at a time loses the batched-GPU affordance that makes Spreading Activation viable at scale.

3. **Do not lock the substrate for write operations.** MVCC with snapshot isolation handles all the concurrency the substrate needs. Locks introduce contention that defeats the entire batched-SpMV affordance.

4. **Do not run Oneiros and Spreading Activation in the same process at the same time without snapshot pinning.** The reason for snapshot pinning is the partial Oneiros state during a tick. A read that crosses the boundary sees inconsistent intermediate state; the bug is silent and intermittent. Pinning is not optional.

5. **Do not skip the audit ledger.** Every consolidation, split, prune, agent-driven cleanup action, and therapy action goes to the ledger. This is bookkeeping, not validation, and it is the only way to recover when something does go wrong — and the only way the substrate can honestly answer "what did you forget and why?".

6. **Do not synchronise the delta buffer to Lance on every Hebbian update.** That kills throughput. The buffer lives in RAM and persists to Lance only at Oneiros tick boundaries. If the process crashes mid-update, the few lost Hebbian increments are part of the substrate's noise budget — that is what the immune system later corrects through resampling and reinforcement.

These six are engineering disciplines, not policy statements. They preserve the implementation's correctness and performance properties; everything else (storage choices, vector dimensionality, GPU library, concrete tier thresholds, Oneiros frequency) is a tuning surface.

---

## Open implementation questions

These are calls for engineering judgement that should be made and recorded as backlog tickets when the work is taken up.

- **GPU library choice.** cuSPARSE is mature and fast on NVIDIA but not portable. PyTorch sparse is portable but slower for some operations. For Gen 1, default to PyTorch sparse on whatever GPU is present (MPS on Apple, CUDA on NVIDIA), accept the performance ceiling, document the cuSPARSE migration as a future optimisation. The substrate doctrine does not bind on this choice.

- **Vector dimensionality.** 1024-d (BGE-M3) is the doctrine default. Lower dimensions (768-d, 384-d) work for prototypes; higher dimensions (4096-d) are research-only until empirically justified. Memory budget at scale dominates the choice — 384-d cuts node storage by ~3× over 1024-d.

- **Description regeneration LLM choice.** Tier-1 descriptions are regenerated periodically by an LLM call. Gen 1 should use whatever the operator's main extraction model is — there is no need for a separate "description LLM". The cost is small (one short call per Tier-1 node per consolidation cycle) and easily cacheable.

- **Frame encoder choice.** This is open research. The frame encoder must distinguish *epistemic* frames in semantically-similar text. Off-the-shelf NLI-fine-tuned encoders (e.g., the Stella-class models) help marginally; a project-specific small contrastive encoder is the right answer once the substrate has enough labelled frame data to train one. Until then, a heuristic frame extractor (rule-based on cue words: "claimed", "wrongly believed", "suspected", "demonstrated") populates a coarse frame_vector. See [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Frame-sensitive resonance".

- **Pruning safety margin.** The current implementation guidance is to prune until 20% under threshold to avoid thrashing. The right margin is empirical and may differ by tier; tune via Mnemosyne A/B (per [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) §"Self-improvement loop").

---

## One-line summary

> **Nodes in Lance, edges in PyTorch sparse, mesh-state in version-snapshots, queries as batched SpMV, ticks as the only writers — and the same code from laptop to multi-server.**
