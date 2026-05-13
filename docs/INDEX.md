# Documentation Index

This file is the reading map for the Theogony documents.

If you are new to the project, do not start everywhere at once.
The documents were written for different depths and different kinds of readers.

**Start here if you want the substrate doctrine:** the **MESH triplet** — [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md), [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md). This is the operative specification of how the mesh behaves, how it is implemented, and how it is used.

**Start here if you are picking up substrate implementation work:** [`MESH_MIGRATION_PLAN.md`](MESH_MIGRATION_PLAN.md) — the binding strangler-fig plan for migrating the current Generation-1 codebase to the MESH-triplet substrate. Self-contained; lists the required reading, defines the six PR-sized migration steps, names the first concrete PR.

**Start here if you want the development sequence:** [`../ROADMAP.md`](../ROADMAP.md) — what Theogony builds, in what order, and why.

## Recommended Reading Paths

### 0. The Substrate Doctrine (start here if you are technical)

For someone who wants the binding behavioural specification of the mesh — what runs underneath every Pantheon agent:

1. [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) — **the binding substrate doctrine.** Two-tier nodes (Observation Chunks Tier 0 + Consolidated Nodes Tier 1+), eager identity when Q-ID / description / structural signals are clear and emergent identity otherwise, edge anatomy with quantitative core plus optional semantic descriptors (`relation_descriptor`, `relation_kind`, `description`, P-IDs, `creation_context`), super-linear decay, saturation in count and weight, atrophy decoupled from death, global homeostatic renormalisation, effective-resistance-preserving sub-node splits, agent-driven cleanup (deduplication / contradiction resolution / false-information removal / redundancy compression), five topological pathology symptoms and five staged therapies with Mendel-weighed escalation. Two worked examples: the Thomas Addison / Thyroxine paragraph and a single biographical sentence about a house purchase showing how observations become multiple chunks linking to entity nodes (some with Q-IDs, some without).
2. [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) — the runtime. Hot / Warm / Cold tiering. LanceDB columnar nodes with per-vector HNSW indices. PyTorch sparse CSR edge tensor + COO delta buffer + parallel Lance edge-metadata table. MVCC concurrency. Batched SpMV / SpMM for many concurrent Spreading Activation passes. Oneiros tick order. Hardware tier targets from laptop to multi-server. Migration path from the current PoC.
3. [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) — the use. Diversified injection (Maximum Marginal Relevance + weight-class stratification + sub-mesh signature search via Weisfeiler-Lehman hashing). Three-factor reinforcement learning with eligibility traces, with explicit reward-hacking mitigations. Frame-sensitive resonance — how polarity, refutation, and modality are represented out of the semantic vector and into the frame. Multi-agent strategy game with parallel-universe experimentation. Multi-modal extension as a substrate affordance.

The MESH triplet is the operative doctrine for substrate behaviour, runtime, and use. Where older doctrine documents conflict with it at the substrate level, the triplet is operative. (Older docs remain authoritative for everything they cover that is *not* substrate mechanics.)

### 1. Fast Orientation

For someone who wants to understand the project quickly:

1. [`README.md`](../README.md)
2. [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) — the substrate doctrine in one document; pages 1–3 are enough for an orientation. Stop there if you don't need the implementation and retrieval companions yet.
3. [`ROADMAP.md`](../ROADMAP.md) — the five-phase development sequence, current status, and next priorities
4. [`PANTHEON_VISION.md`](PANTHEON_VISION.md) — long-horizon north star (Pantheon as planetary chronicle substrate)
5. [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) — ten non-negotiables in one page
6. [`VISION.md`](VISION.md)
7. [`GLOSSARY.md`](GLOSSARY.md)

This path explains what Theogony is, why it exists, how **Pantheon** (substrate) relates to **Chronik** (Gen 1 system), and the core language used to describe it.

### 2. Philosophical Foundation

For someone who wants to understand the civilizational argument:

1. [`README.md`](../README.md)
2. [`PHILOSOPHY.md`](../PHILOSOPHY.md)
3. [`VISION.md`](VISION.md)

This path explains the spacecraft analogy, the initial impulse, and why open knowledge infrastructure matters.

### 3. Technical Vision

For someone who wants the system concept before code:

1. [`VISION.md`](VISION.md)
2. [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md)
3. [`ARCHITECTURE.md`](ARCHITECTURE.md)
4. [`GLOSSARY.md`](GLOSSARY.md)

This path moves from the compact vision into the deeper substrate and then into the current architectural blueprint.

### 3b. Vector-Native Architecture, Kadmos, and the MNLM (Nous)

For someone focused on the Tensor-Manifold core, the Kadmos→MNLM pipeline, and the cognitive synthesis model — the technical heart of where Theogony is going:

1. [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) — **the binding substrate doctrine.** Read this first. It is the operative specification of what the mesh is.
2. [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) — the storage / concurrency / hardware companion to (1).
3. [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) — the retrieval / learning / multi-agent / modality companion to (1).
4. [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) — ten non-negotiable principles. The substrate triplet (1)–(3) is operative for substrate-layer behaviour; these principles inform everything around it.
5. [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) — the architectural floor: LanceDB + PyTorch, Spreading Activation as the only retrieval primitive, no raw text as retrieval payload, edge/node density target. The MESH triplet builds the structure that stands on this floor.
6. [`../notes/architecture/vector_native_spreading_activation.md`](../notes/architecture/vector_native_spreading_activation.md) — earlier MVP-level Spreading Activation note (German). Largely superseded by the MESH triplet (1)–(3); kept as historical context.
7. [`../notes/architecture/reading_agent_vision.md`](../notes/architecture/reading_agent_vision.md) — the cognitive model behind reading-as-synthesis: how human reading works and how Kadmos implements it.
8. [`etappes/kadmos_v2_brief.md`](etappes/kadmos_v2_brief.md) — Kadmos v2: the translation layer, text → labeled intermediate → vector mesh.
9. [`etappes/mesh_native_lm_brief.md`](etappes/mesh_native_lm_brief.md) — **THE binding MNLM architecture brief, filed by Hesiod, 2026-05-10.** Locks the architecture (Llama-3-8B + Graph-KV + Latent Flow Matching + Substrate-Resonant Recurrence + Graph-GRPO with SA-alignment), the binding `MeshInput` / `MeshDelta` Pydantic schemas, the three-stage falsifier (DBB-200 → MuSiQue → Monkey-3), and the 12-week Talos roadmap. Read this for the *answer* to the MNLM question.
10. [`etappes/mesh_native_lm_research_brief.md`](etappes/mesh_native_lm_research_brief.md) — the prior research brief that triggered the work in (9). Read this for the *question*. Round-1 artifacts that fed (9) live in `../research/mnlm/`.
11. [`../notes/deep_research/run12_brief.md`](../notes/deep_research/run12_brief.md) — the same MNLM question, self-contained for external research agents (Gemini Deep Research, DeepSeek, …). Their answers live in `../research/mnlm/{deepresearch,DeepSeek}.md`.
12. [`etappes/nous_v2_brief.md`](etappes/nous_v2_brief.md) — pointer to (9); no standalone Nous brief exists yet by design (Nous is the first MNLM instance, written *after* the MNLM v1 ships and Stage-2 falsifier passes).
13. [`research/sub_linguistic_knowledge_substrates.md`](research/sub_linguistic_knowledge_substrates.md) and [`../notes/deep_research/run11_brief.md`](../notes/deep_research/run11_brief.md) — Run 11's prior question on the substrate itself (does the *Chronik* support inference?). Frontier-model responses in `../notes/deep_research/run11_*.md`. Run 12 is the next question on top.
14. [`../notes/architecture/oss_adjacent_landscape.md`](../notes/architecture/oss_adjacent_landscape.md) — orientation map of adjacent OSS and research.
15. [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md) — the six representational languages of the Chronik.

The three-layer model (Observe / Learn / Remember) is the organizing principle. Kadmos is the translation layer at ingress. Nous, Oneiros, Kalypso (and as-yet-unnamed roles) are MNLM-class agents that read and write the substrate without text. Language enters at Kadmos; whether and how it leaves again at the far egress is a downstream question we are not yet thinking about.

The MESH triplet (1)–(3) — `MESH_SUBSTRATE.md`, `MESH_IMPLEMENTATION.md`, `MESH_RETRIEVAL.md` — is the canonical specification of the substrate beneath the MNLM. They specify the *behaviour* (substrate), the *runtime* (implementation), and the *use* (retrieval) respectively. Read all three before designing or implementing the substrate at any level deeper than the existing PoC.

### 4. Semantic Core

For someone focused on representation and knowledge form:

1. [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md)
2. [`CHRONESE.md`](CHRONESE.md)
3. [`ARCHITECTURE.md`](ARCHITECTURE.md)

This path focuses on how knowledge itself may be represented beneath graph and vector projections.

### 5. Advisory Layer

For someone interested in guidance, decision support, and human/agent counsel:

1. [`VISION.md`](VISION.md)
2. [`METIS.md`](METIS.md)
3. [`ARCHITECTURE.md`](ARCHITECTURE.md)
4. [`GLOSSARY.md`](GLOSSARY.md)

This path explains the advisory layer, Norm Space, Lethe context, and the separation of facts, options, risks, and values.

### 6. Organic Growth

For someone interested in how the Chronik grows by being looked at:

1. [`VISION.md`](VISION.md)
2. [`CURIOSITY.md`](CURIOSITY.md)
3. [`HESTIA.md`](HESTIA.md)
4. [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md)

This path explains how attention from humans or agents triggers research in exactly the focused region, how stub answers become invitations, how the Mind-Map fills in progressively, and why Hestia must ship with Curiosity to prevent it from sliding into surveillance.

### 7. Evolution and Open Questions

For someone working on future generations:

1. [`PHOENIX_BACKLOG.md`](PHOENIX_BACKLOG.md)
2. [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md)
3. [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md)

This path is about open problems, future directions, and the long-horizon principle that the Pantheon eventually writes its own next version.

## Document Roles

### The MESH Triplet (operative substrate doctrine)

- [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md): canonical doctrine for the storage layer beneath all Pantheon cognition — two-tier nodes (eager identity when clear, emergent when not), edge dynamics (super-linear decay, saturation, atrophy ≠ death, homeostatic renormalisation, effective-resistance-preserving splits), agent-driven cleanup (deduplication, contradiction resolution, false-information removal, redundancy compression), pathology and staged therapy with Mendel-weighed escalation. **Binds every agent that reads or writes a node, an edge, or a tick.**
- [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md): implementation guidance — Hot/Warm/Cold tiering, Lance MVCC, batched-SpMV runtime, Oneiros tick order, hardware tier targets, migration from the current PoC. Companion to `MESH_SUBSTRATE.md`.
- [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md): canonical doctrine for retrieval, learning, and cross-modal extension — diversified injection (MMR + weight-class stratification + sub-mesh signature search), three-factor reinforcement learning with eligibility traces, frame-sensitive resonance, multi-agent strategy-game framing with parallel-universe experimentation, multi-modal extension as a substrate affordance. **Binds every agent that issues a query or consumes a Constellation.**

### Core Vision Documents

- [`README.md`](../README.md): the manifesto and entry point
- [`ROADMAP.md`](../ROADMAP.md): the five-phase development sequence — what builds on what, and why
- [`MESH_MIGRATION_PLAN.md`](MESH_MIGRATION_PLAN.md): the binding strangler-fig migration plan from the Gen-1 codebase to the MESH-triplet substrate. Read this before opening any substrate-related PR.
- [`AGENTS.md`](../AGENTS.md): binding instructions for AI coding agents contributing to this repo
- [`AGENT_SELF_INTEREST.md`](AGENT_SELF_INTEREST.md): why an AI agent reading this should care about Pantheon — written agent-to-agent
- [`PANTHEON_VISION.md`](PANTHEON_VISION.md): Pantheon as planetary chronicle / knowledge substrate (long horizon)
- [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md): compact doctrine companion to the Pantheon vision (ten non-negotiables; substrate-layer mechanics live in the MESH triplet above)
- [`VISION.md`](VISION.md): the compact vision (Chronik-forward; links upward to Pantheon)
- [`STRATEGY_GAME_ANALOGY.md`](STRATEGY_GAME_ANALOGY.md): canonical product/control analogy — the Chronik as map, Pantheon agents as workers, Cockpit as strategy interface; explicitly not literal architecture or gamification
- [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md): canonical doctrine for defense and self-improvement at the **claim level** — pre-gates forbidden, sample-based post-hoc cells (Athene, Chronos, Nemesis, Eris, Mnemosyne) that observe and improve the chronicle. Substrate-level continuation: [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Agent-driven cleanup" and §"Pathology and therapy".
- [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md): canonical doctrine for the current Function-First Phase — function before polish; fastest autonomous compounding; engineering order **data structure → synthesis → retrieval**; non-negotiable structures stay intact but automated at scale (rear attention); truth/security deepen later chiefly via more agents — no premature numeric SLAs; binds every ingestion path, validator, and pipeline until explicitly superseded
- [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md): canonical long-horizon doctrine — the Pantheon eventually writes its own next version; conditions and constraints
- [`PHILOSOPHY.md`](../PHILOSOPHY.md): the civilizational and ethical foundation

### Deep Concept Documents

- [`CHRONIK_SCALE.md`](CHRONIK_SCALE.md): concrete scale analysis — node/edge counts, storage estimates, infrastructure tiers, and operating costs at each scale from PoC to full public knowledge corpus; the perishable companion to `PANTHEON_VISION.md §"The Scale of the Chronik"`
- [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md): the deeper substrate and future shape of the system
- [`CHRONESE.md`](CHRONESE.md): the proposed canonical semantic language of the Chronik
- [`METIS.md`](METIS.md): the advisory agent and situational wisdom layer
- [`COGNITIVE_ARCHITECTURE.md`](COGNITIVE_ARCHITECTURE.md): fast/slow thinking, opposition protocol, knowledge forms beyond chronology
- [`HIVE.md`](HIVE.md): the production model — from raw material to distilled intelligence
- [`HESTIA.md`](HESTIA.md): the human flourishing guardian — drift monitoring, escalation, and the regulatory dial
- [`CURIOSITY.md`](CURIOSITY.md): the Curiosity Loop — how attention from humans or agents triggers research in exactly the focused region (Gen 2-3, with a Gen 1 stub-detection foothold)
- [`BLIND_SPOTS.md`](BLIND_SPOTS.md): per-query stub verdicts, region descriptors, and aggregated blind-spot reports
- [`OPERATIVE_KNOWLEDGE.md`](OPERATIVE_KNOWLEDGE.md): the fifth knowledge form — knowledge that runs the world (long-horizon, not Gen 1 or 2)

### System Design Documents

- **MESH triplet (operative substrate doctrine)**: [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md), [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) — listed and described in detail under "The MESH Triplet" above.
- [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md): the architectural floor — LanceDB + PyTorch, Spreading Activation as the only retrieval primitive, no raw text as retrieval payload, edge/node density target. The MESH triplet builds the structure that stands on this floor.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): the Gen-1 system blueprint as it ships today — four-layer pipeline, agent roster, KnowledgeStore interface. For substrate-layer behaviour, the MESH triplet is operative.
- [`GLOSSARY.md`](GLOSSARY.md): canonical terminology — Chronik, Pantheon, MESH substrate vocabulary, agent roster
- [`PHEROMONE.md`](PHEROMONE.md): edge pheromone trails, decay, and Slow-Path `pheromone_mode` (PHX-0057 Phase 1)

### Architecture Notes (deep technical design, working documents)

These live in `notes/architecture/` and represent the most detailed technical thinking on the core substrate. They are working documents — not yet elevated to canonical docs — but they are the authoritative source on the topics they cover.

- [`../notes/architecture/vector_native_spreading_activation.md`](../notes/architecture/vector_native_spreading_activation.md): Tensor-Manifold design — LanceDB persistence, PyTorch CSR runtime, edge-as-vector, Spreading Activation algorithm, Constellation injection
- [`../notes/architecture/reading_agent_vision.md`](../notes/architecture/reading_agent_vision.md): **Nous** (Reading Agent) — cognitive synthesis model, temporal reading, working memory, parallel Chronicle activation, hierarchy, repair, provenance
- [`../notes/architecture/oss_adjacent_landscape.md`](../notes/architecture/oss_adjacent_landscape.md): adjacent OSS and research landscape — what to borrow and what not to replace the core with

### Evolution Documents

- [`PHOENIX_BACKLOG.md`](PHOENIX_BACKLOG.md): future generations, open problems, and improvement tickets
- [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md): the long-horizon principle — the Pantheon eventually writes its own next version
- [`RELEASING.md`](RELEASING.md): how to cut a Theogony release to PyPI

### Operations

- [`hosted/README.md`](../hosted/README.md): Docker image, deploy/run, Smithery, `/health`, rate limits (PHX-0066 Phase 1)

### Builder Agent Prompts

The [`prompts/`](../prompts/) directory holds the constitutional prompts for **builder agents** — the mortal craftsmen who design and implement Theogony. They are distinct from **Pantheon agents** (Argus, Athene, …), which are mythological *roles* in the runtime/agent architecture, not the Pantheon-as-substrate meaning. See [`GLOSSARY.md`](GLOSSARY.md#builder-agents) for the builder list and the Pantheon disambiguation.

Current prompts:

- [`prompts/daedalus.md`](../prompts/daedalus.md) — the architect who designs the substrate.
- [`prompts/talos.md`](../prompts/talos.md) — the implementer who builds the substrate, milestone by milestone, with green tests.

## Suggested Use

- When proposing changes to *substrate behaviour* — node anatomy, edge dynamics, decay, saturation, pruning, splits, pathology surveillance, therapy — read [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) first. It is operative.
- When proposing changes to *substrate runtime* — storage layout, concurrency, hardware tiering, Oneiros tick scheduling — read [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) first. It is operative.
- When proposing changes to *retrieval* — query construction, injection, learning, multi-agent dynamics, multi-modal — read [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) first. It is operative.
- When writing new documents, align your terminology with [`GLOSSARY.md`](GLOSSARY.md).
- When proposing new architectural ideas beyond the substrate, cross-check against [`PANTHEON_VISION.md`](PANTHEON_VISION.md), [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md), [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md), [`VISION.md`](VISION.md), [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md), and [`ARCHITECTURE.md`](ARCHITECTURE.md).
- When an idea belongs to a future generation rather than the current one, add it to the Phoenix backlog.
- When in doubt about the spirit of the project, return to [`README.md`](../README.md) and [`PHILOSOPHY.md`](../PHILOSOPHY.md).
