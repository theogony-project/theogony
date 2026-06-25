# Theogony — Roadmap

**Status:** Living document. Updated as phases complete.  
**Author:** Chaos (vision role), May 2026.  
**Audience:** Anyone who wants to understand where this is going and why.

This document is the single authoritative sequence of what Theogony builds,
in what order, and why each phase is a prerequisite for the next.
It is not a sprint plan. It is the horizon.

**Operative substrate doctrine:** the MESH triplet — [`docs/MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md), [`docs/MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md), [`docs/MESH_RETRIEVAL.md`](docs/MESH_RETRIEVAL.md) — specifies what the substrate must behave like, how it is implemented, and how it is used. Every phase below realises some part of that triplet. Where this roadmap and the triplet conflict on substrate-layer behaviour, the triplet is operative.

**Operative migration plan:** [`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md) — the binding strangler-fig plan for replacing the current Generation-1 codebase with the MESH-triplet substrate. The roadmap below describes the *what* (five long-horizon phases); the migration plan describes the *how* (six PR-sized strangler steps for the substrate replacement, parallel Phoenix-backlog migration). Both are binding; they address different questions.

---

## The Core Thesis (One Paragraph)

Text is the wrong medium for AI-to-AI communication. Today's systems
translate knowledge into text, transmit text, and translate back. Every
step degrades, compresses, and discards structure. Theogony builds a
substrate where knowledge lives as a dense vector-graph (the **Chronik**),
where agents communicate by injecting and receiving activation fields
(not documents), and where the substrate itself grows, dreams, heals, and
eventually writes its own next version. Text remains at the edges — for
human input and human output. In the interior, there is only the Manifold.

---

## Phase 1 — Reading (Current Priority)

**Goal:** A system that *synthesises* knowledge as it reads, not one that
*parses* text into extractions — and that writes its output into the
substrate following the MESH-doctrine eager-linking rules
([`docs/MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md) §"Why two tiers — and
how identity actually gets committed").

### The Cognitive Reading Layer — **Kadmos v2**

A human does not extract concepts from a text. She synthesises them
continuously, sentence by sentence, carrying a working memory forward:
5–10 new concepts per sentence, plus ~50 activations from prior knowledge,
condensed into a synthesis that pre-warms the next sentence. Paragraphs
condense into chapter-syntheses. Repair fires when a new sentence
contradicts an earlier synthesis.

Kadmos v2 implements exactly this and emits Tier-0 Observation Chunks
plus reference edges into the substrate at insertion time. Where the
chunk references entities the linker can resolve confidently (Q-ID,
description, or strong structural context), Kadmos attaches reference
edges directly to existing Tier-1 entity / concept / source-anchor
nodes — eagerly. Where no signal is decisive, Kadmos creates entity-
candidate nodes that Oneiros later consolidates or atrophies. See
[`docs/etappes/kadmos_v2_brief.md`](docs/etappes/kadmos_v2_brief.md).

The Reading Agent implements exactly this:

| Mechanism | Description |
|---|---|
| **Temporal reading unit** | Sentence-by-sentence, carrying state forward |
| **Working memory** | Active concept set with weights and decay |
| **Parallel Chronicle activation** | kNN search against Chronik runs at ~20% of compute while foreground reads |
| **Synthesis events** | Emerge when concepts condense, not on hard paragraph-boundaries |
| **Repair events** | Triggered by detected contradiction; backward revision of earlier synthesis |
| **Trust-and-skim** | Chapter can be skimmed if its core concept is well-validated in Chronik |
| **Fuzzy hierarchy** | Sentence → Paragraph → Chapter → Article → Theme, fuzzy membership, diagonal edges allowed |
| **Stable identity anchors** | Wikidata Q-IDs for entities where they exist; AKA-IDs otherwise |
| **Multi-resolution models** | Optional: sentence with small model, chapter with large model |

The Reading Agent produces an **AnnotatedReading** — a machine-readable,
human-inspectable record of the temporal synthesis process. This is the
unit of comparison between human and agent comprehension.

**Why this comes first:** Without Kadmos v2, the substrate is filled by
a stateless parser whose output does not respect the eager-linking
discipline. The substrate's value is proportional to the quality of
synthesis at ingest. Better synthesis = richer Tier-0 chunks + richer
Tier-1 entity / concept structure = better Spreading Activation
retrieval = better agents downstream.

**On the name "Nous".** In the older roadmap framing, the cognitive
reading layer was called "Nous". The current naming separates the two
roles: **Kadmos v2** is the text → substrate translation layer at
ingress (Phase 1); **Nous** is the first MNLM instance (Phase 4), a
substrate-native agent that operates *inside* the mesh, not on text.
See [`docs/etappes/mesh_native_lm_brief.md`](docs/etappes/mesh_native_lm_brief.md).

### Agent Initialisation Space (inside the Chronik)

Agents must be initialised with persistent context. The Chronik must
contain a dedicated region for each agent instance:

- **Identity & Expertise layer**: the agent's role, prompt-genome, domain
  competencies, epistemic posture, and constitutional constraints. Stored
  as a concept cluster — readable and writable during runtime.
- **Biographical memory**: a temporal record of what the agent has done,
  what it has produced, what failed, what was rewarded. This is not a
  log file — it is a first-class subgraph in the Chronik that the agent
  reads as context at initialisation and writes continuously during its
  active lifetime.
- **Task queue layer**: current assignments with priority, dependency
  edges to other tasks and agents, and estimated completion status. Also
  a subgraph — readable by orchestrators (Zeus, Helios) and writable by
  the agent itself.

This agent initialisation space is naturally a concept-graph. It is part
of the Chronik, not external to it. It may also run as a separate
lightweight store for latency reasons — but its schema and identity
model must be compatible with the Chronik's.

**Concretely:** When Morpheus wakes up for a new tick, it reads its own
biographical subgraph, updates its task queue, and begins work. When it
finishes, it writes back: what it produced, what edges it created, what
confidence it assigned. This record is available to Athene for auditing
and to Mnemosyne for meta-learning.

---

## Phase 2 — Chronik Architecture (Tensor-Manifold)

**Goal:** The Chronik as a solid, readable, writable, GPU-resident
Tensor-Manifold that supports Spreading Activation natively — realising
the MESH triplet's behavioural and implementation doctrine.

### Core architecture

Binding spec: [`docs/MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md).
Summary:

| Layer | Technology | Role |
|---|---|---|
| **Persistent node store** | LanceDB (Parquet/Arrow, columnar) | Two-tier nodes (Tier 0 Chunks, Tier 1+ Consolidated); per-vector HNSW indices on semantic / frame / structural / temporal / description embeddings; versioned snapshots |
| **Edge runtime (SpMV path)** | PyTorch sparse CSR tensor | Quantitative fields only: `(source, target, weight, decay_tier, frame_consistency)`. Built by Oneiros; loaded into RAM / GPU. SpMV / SpMM for batched Spreading Activation |
| **Edge delta buffer (write path)** | Append-only COO | Hebbian updates accumulate lock-free; merged into CSR at every Oneiros tick |
| **Edge metadata** | Parallel Lance table | Optional semantic descriptors: `relation_descriptor`, `relation_kind`, `description`, `pids` (Wikidata P-IDs), `creation_context`. Read only when an agent inspects an edge — never on the SpMV hot path |
| **Anchor index** | Lance + inverted index | Temporal, geographic, language, and genome-position anchor nodes obey different rules (immutable, very-high-cap, no decay); range queries use index lookups, not graph traversal |
| **Audit ledger** | Append-only Lance | Every consolidation, split, therapy action, pruning, agent-driven cleanup writes a structured record |
| **Query interface** | Activation injection (single vector or sub-mesh with structure) → Constellation | No Cypher, no SQL, no "fast path" around Spreading Activation |
| **Concurrency** | MVCC (Lance versioning) | Unlimited parallel reads against pinned snapshots; Oneiros is the single writer of new versions |

### Spreading Activation

Binding spec: [`docs/MESH_RETRIEVAL.md`](docs/MESH_RETRIEVAL.md).
Summary:

- **Diversified seeding (always on).** Maximum Marginal Relevance + weight-class stratification (micro / medium / large / hub); optional sub-mesh signature search using Weisfeiler-Lehman hashing. Plain top-K-by-cosine retrieval is forbidden in production.
- **Frame-routed propagation.** Edges contribute only when their `frame_consistency` with the query's active frame profile exceeds a threshold. Implemented as a masked SpMV / SpMM fused into the GPU kernel.
- **Damped propagation.** Activation decays per hop; propagation halts at `min_activation` (~0.05) or `max_hops` (default 3, ≤ 5 in production).
- **Constellation result.** The activated subgraph is returned as a structured working set: nodes, edges (with descriptors), source anchors, gaps. Directly injectable into the consuming agent's latent space.
- **Three-factor learning.** Consumer feedback (LLM self-rating, downstream task success) modulates Hebbian update along the activation trace; eligibility traces back-propagate sparse rewards across multi-hop paths.

### Substrate dynamics

Binding spec: [`docs/MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md).
Summary:

- **Two-tier nodes** with eager identity when Q-ID / description / structural signals are clear, emergent identity otherwise.
- **Super-linear decay** (default `k = 2`, tier-modulated) — strong unused edges decay faster than weak ones; high edge weight signifies *currently relevant*, not *historically important*.
- **Saturation caps** in both count and weight, indexed by tier (Tier 0: 10K / S; Tier 1: 50K / 5S; Tier 2: 200K / 20S; Tier 3: 1M / 100S).
- **Atrophy decoupled from death** — nodes stay until the pruner runs under resource pressure. The mesh loses memory only under genuine resource constraints.
- **Global homeostatic renormalisation** keeps the substrate's total-edge-weight / node-count ratio near a target `R_ideal`.
- **Effective-resistance-preserving sub-node splits** when hubs reach their cap.
- **Agent-driven cleanup** (deduplication, contradiction resolution, false-information removal, redundancy compression) operates post-hoc with audit; pre-gates judging content at insertion remain forbidden.
- **Topology pathology surveillance** by Argus (five symptoms) and **five staged therapies** with the Mendel risk weighed before any invasive step.

### Scale targets

Binding numbers: [`docs/CHRONIK_SCALE.md`](docs/CHRONIK_SCALE.md).
Summary:

| Tier | Nodes (consolidated) | Edges | Storage | Deployment |
|---|---|---|---|---|
| 0 (PoC / Gen 1 dev) | ≤ 10⁶ | ≤ 10⁸ | ≤ 5 GB | Single laptop |
| 1 (English Wikipedia) | ~10⁸ | ~10¹⁰ | ~5–8 TB | Single server (256–512 GB RAM, A100/H100) |
| 2 (multilingual + sources) | ~10⁸–10⁹ | ~10¹⁰–10¹¹ | ~15–50 TB | Single large server or small cluster |
| 3 (federated full public knowledge) | ~10⁹–10¹⁰ | ~10¹¹–10¹² | ~50–500 TB | Distributed |

---

## Phase 3 — First Corpus (Wikipedia + Books)

**Goal:** Seed the Chronik with a real, dense, multi-source corpus using
the Reading Agent pipeline.

### Wikipedia

- Begin with the German and English Wikipedia dumps (full XML)
- Pre-process with the hierarchical topology parser (Domain → Theme →
  Article → Chapter → Paragraph → Sentence)
- Run the Reading Agent on each article, writing AnnotatedReadings and
  Chronik subgraphs
- Wiki-links become candidate identity anchors (Q-ID resolution)
- Categories become fuzzy theme memberships (diagonal edges)

### Books (Gutenberg)

- Prioritise public-domain books in history, science, biography, and
  philosophy
- Same Reading Agent pipeline
- Provenance anchor per sentence: Gutenberg ID + character offset

### Scale expectation

A full Wikipedia ingest at Reading-Agent quality produces a Chronik of
100M–1B nodes (concepts at sentence, paragraph, and article level) with
10–100x more edges than nodes, spanning hundreds of domains.

---

## Phase 4 — Chronik as Cross-Attention Layer

**Goal:** Demonstrate that a language model can use the Chronik as a
live memory layer inside the forward pass — not via RAG post-processing,
but via cross-attention inside or alongside the transformer blocks.

### Mechanism

Following RETRO (DeepMind, 2021) and Memorizing Transformers (Google,
2022): a small open model (e.g. Llama 3.2 1B or Phi-3-mini) is extended
with cross-attention heads that attend to Chronik node vectors retrieved
by the current input's hidden states.

The model retrieves not text chunks but **Constellation tensors** — the
activation-field output of the Chronik — and attends to them directly.
This eliminates the token-cost of RAG and the latency of a separate
retrieval step.

**The model no longer needs to know facts.**  
It needs to know how to navigate the Chronik and how to interpret
Constellations. A small model with access to a large Chronik outperforms
a large model without one on knowledge-intensive tasks.

### Why this matters

This is the technical proof of the core thesis. Once it works at small
scale (1B parameters + 10M Chronik nodes), the architecture is
demonstrated. Scaling is then primarily a function of Chronik growth, not
of model re-training.

---

## Phase 5 — The Living Pantheon

**Goal:** A self-organising ecosystem of agents living inside and around
the Chronik — reading, writing, healing, curating, and eventually
improving themselves.

### The roster at maturity

| Agent | Role |
|---|---|
| **Nous** | Reads the world into the Chronik — cognitive synthesis, temporal reading |
| **Morpheus** | Finds associations, creates inference edges |
| **Athene** | Verifies, samples, adjusts confidence |
| **Chronos** | Lifecycle: decay, archive, delete |
| **Nemesis** | Structural auditor: echo chambers, pheromone highways |
| **Eris** | Red-team: adversarial probes against isolated test pantheon |
| **Mnemosyne** | Meta-learner: observes all cells, A/B-tests thresholds |
| **Argus** | WorldCrawler: autonomous web exploration |
| **Prometheus** | Gap detector: what is the Chronik missing? |
| **Metis** | Advisory agent: structured counsel from Akasha + Lethe + Norm Space |
| **Helios** | Regulatory orchestration: who runs how much, at what priority |
| **Zeus** | Operative orchestration: tasks, budgets, routing |

Each agent has an **initialisation space** in the Chronik (Phase 1),
a **biographical memory** that grows over time, and a **task queue**
that is visible to orchestrators.

### Self-modification

Self-improvement is **central**, not incidental, and it widens in scope
over time:

1. **Knowledge** — the chronicle already improves its own contents
   without new external input (consolidation, the immune system, Oneiros
   "dreaming"). Live today.
2. **Architecture and implementation** — Mnemosyne observes enough to
   propose, and eventually author, the next version of the system: new
   thresholds, agent configurations, schemas, substrate code. Proposals
   land in the Phoenix Backlog as first-class tickets; the Pantheon walks
   toward writing its own next incarnation.
3. **The stack it runs on** — long-horizon: the efficiency of the
   algorithms, the operation and design of the data centers, the energy
   that powers them, and chip architecture and fabrication specialised
   for this workload — and beyond.

Dedicated agents are budgeted for this work; as research reaches full
operation, a standing "improve-Theogony" section runs continuously
(the same way Argus acquires and Athene verifies). The dangerous stages
— the system authoring its own code and shaping its own infrastructure —
are gated by the strict conditions in
[`docs/SELF_MODIFICATION.md`](docs/SELF_MODIFICATION.md): hard CI wall,
bot-account separation, human-review default, reversibility, audit. The
principle is recorded both because it is central and so current
architecture never accidentally forecloses it.

---

## Name: Nous

The Reading Agent is named **Nous** (Greek: νοῦς — the active intellect;
Aristotle's principle of the mind that actualises knowledge rather than
merely storing it).

The name is precise. Nous is not memory (that is Mneme). Nous is not
the dream (that is Oneiros). Nous is the active synthesising faculty —
the process by which raw sensation becomes understanding. In Aristotle's
formulation, Nous is what makes the potential actual: it takes what exists
in the world and constitutes it as knowledge in the mind.

That is exactly what this agent does.

---

## Summary Sequence

```
Phase 1: Nous (Cognitive Synthesis Agent) + Agent Initialisation Space
Phase 2: Chronik Tensor-Manifold (LanceDB + PyTorch CSR)
Phase 3: Wikipedia + Books corpus
Phase 4: Chronik as Cross-Attention Layer (Proof of Concept)
Phase 5: Living Pantheon (self-organising agent ecosystem)
```

Each phase produces something runnable and demonstrable. No phase is
purely preparatory. The Chronik grows at every step.

---

## What this is not

- Not a RAG system (RAG is text-in, text-out; this is vector-in,
  vector-out at the core)
- Not a knowledge graph database (pointer-chasing Cypher cannot handle
  1000x edge density)
- Not a chat interface (the Chronik is a substrate, not a product)
- Not a fine-tuning pipeline (models are not trained on Chronik content;
  they access it live via Spreading Activation or Cross-Attention)

---

## Reference documents

| Document | Purpose |
|---|---|
| **[`docs/MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md)** | **Operative substrate doctrine — two-tier nodes, edge anatomy, dynamics, agent-driven cleanup, pathology and staged therapy. Binding for substrate behaviour.** |
| **[`docs/MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md)** | **Operative runtime spec — Hot/Warm/Cold tiering, LanceDB + sparse PyTorch + MVCC + batched SpMV, Oneiros tick order. Binding for substrate runtime.** |
| **[`docs/MESH_RETRIEVAL.md`](docs/MESH_RETRIEVAL.md)** | **Operative retrieval spec — diversified injection, three-factor reinforcement learning, frame routing, multi-agent strategy game, multi-modal extension. Binding for substrate use.** |
| **[`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md)** | **Operative migration plan — strangler-fig replacement of Gen-1 with the MESH substrate. Six PR-sized steps + parallel Phoenix-backlog migration + the first concrete PR.** |
| [`docs/TARGET_ARCHITECTURE.md`](docs/TARGET_ARCHITECTURE.md) | The architectural floor: no raw text as retrieval payload, LanceDB + PyTorch, Spreading Activation as the only retrieval primitive. The MESH triplet builds on this. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Gen-1 system as it ships today — four-layer pipeline, agent roster, KnowledgeStore interface. For substrate-layer questions the MESH triplet is operative. |
| [`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md) | Twelve non-negotiable doctrines |
| [`docs/BUILD_DOCTRINE.md`](docs/BUILD_DOCTRINE.md) | Function-First Phase binding doctrine |
| [`docs/CHRONIK_SCALE.md`](docs/CHRONIK_SCALE.md) | Concrete scale numbers per tier |
| [`docs/DEEP_TECH_VISION.md`](docs/DEEP_TECH_VISION.md) | Deeper substrate vision (six languages of the Chronik) |
| [`docs/COGNITIVE_ARCHITECTURE.md`](docs/COGNITIVE_ARCHITECTURE.md) | Cognitive model underlying the system |
| [`docs/etappes/kadmos_v2_brief.md`](docs/etappes/kadmos_v2_brief.md) | Kadmos v2 — the text translation layer |
| [`docs/etappes/mesh_native_lm_brief.md`](docs/etappes/mesh_native_lm_brief.md) | MNLM architecture brief (Nous, Oneiros, Kalypso as MNLM-class instances) |
| [`notes/architecture/reading_agent_vision.md`](notes/architecture/reading_agent_vision.md) | Reading-as-synthesis vision (historical context — informs Kadmos v2) |
| [`notes/architecture/vector_native_spreading_activation.md`](notes/architecture/vector_native_spreading_activation.md) | MVP-level Spreading Activation note (historical; superseded by the MESH triplet) |
| [`docs/IMMUNE_SYSTEM.md`](docs/IMMUNE_SYSTEM.md) | Defense and self-improvement architecture (claim-level; substrate-level continuation in MESH §"Agent-driven cleanup" + §"Pathology and therapy") |
| [`docs/SELF_MODIFICATION.md`](docs/SELF_MODIFICATION.md) | Long-horizon self-modification principle |
| [`docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md`](docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md) | **Superseded** — Generation-1 implementation plan up to the Neural Vector Mesh Pivot (2026-05-01). Historical context only; not operative. Active plan: `MESH_MIGRATION_PLAN.md`. |
| [`docs/PHOENIX_BACKLOG.md`](docs/PHOENIX_BACKLOG.md) | Evolutionary ticket queue |
