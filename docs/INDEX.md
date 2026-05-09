# Documentation Index

This file is the reading map for the Theogony documents.

If you are new to the project, do not start everywhere at once.
The documents were written for different depths and different kinds of readers.

**Start here if you want the development sequence:** [`ROADMAP.md`](../ROADMAP.md) — what Theogony builds, in what order, and why.

## Recommended Reading Paths

### 1. Fast Orientation

For someone who wants to understand the project quickly:

1. [`README.md`](../README.md)
2. [`ROADMAP.md`](../ROADMAP.md) — the five-phase development sequence, current status, and next priorities
3. [`PANTHEON_VISION.md`](PANTHEON_VISION.md) — long-horizon north star (Pantheon as planetary chronicle substrate)
4. [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) — nine non-negotiables in one page
5. [`VISION.md`](VISION.md)
6. [`GLOSSARY.md`](GLOSSARY.md)

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

### 3b. Vector-Native Architecture, Kadmos, and Nous

For someone focused on the Tensor-Manifold core, the Kadmos/Nous pipeline, and the cognitive synthesis model — the technical heart of where Theogony is going:

1. [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) — the founding principle: language is the edge, not the substrate. Read this first.
2. [`../notes/architecture/vector_native_spreading_activation.md`](../notes/architecture/vector_native_spreading_activation.md) — Spreading Activation over CSR tensors, edge-as-vector, Constellation injection into KV-cache
3. [`../notes/architecture/reading_agent_vision.md`](../notes/architecture/reading_agent_vision.md) — the cognitive model behind **Nous**: how human reading works and how the agent implements it
4. [`etappes/nous_v2_brief.md`](etappes/nous_v2_brief.md) — Hesiod's architecture brief for Nous v2: the cognitive synthesis layer that operates without text
5. [`research/sub_linguistic_knowledge_substrates.md`](research/sub_linguistic_knowledge_substrates.md) — the open research questions: can an AI system reason over pure vector meshes? Responses from frontier models in `../notes/deep_research/run11_*.md`.
6. [`../notes/architecture/oss_adjacent_landscape.md`](../notes/architecture/oss_adjacent_landscape.md) — orientation map of adjacent OSS and research
7. [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md) — the six representational languages of the Chronik

The three-layer model (Observe / Learn / Remember) is the organizing principle. Kadmos and Nous are the Observe layer. Oneiros is the Learn layer. Iris, Kalypso, and Poseidon are the Remember layer. Language enters at Kadmos and exits at Iris — everything in between is vector space.

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

### Core Vision Documents

- [`README.md`](../README.md): the manifesto and entry point
- [`ROADMAP.md`](../ROADMAP.md): the five-phase development sequence — what builds on what, and why
- [`AGENTS.md`](../AGENTS.md): binding instructions for AI coding agents contributing to this repo
- [`AGENT_SELF_INTEREST.md`](AGENT_SELF_INTEREST.md): why an AI agent reading this should care about Pantheon — written agent-to-agent
- [`PANTHEON_VISION.md`](PANTHEON_VISION.md): Pantheon as planetary chronicle / knowledge substrate (long horizon)
- [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md): compact doctrine companion to the Pantheon vision
- [`VISION.md`](VISION.md): the compact vision (Chronik-forward; links upward to Pantheon)
- [`STRATEGY_GAME_ANALOGY.md`](STRATEGY_GAME_ANALOGY.md): canonical product/control analogy — the Chronik as map, Pantheon agents as workers, Cockpit as strategy interface; explicitly not literal architecture or gamification
- [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md): canonical doctrine for defense and self-improvement — pre-gates forbidden, sample-based post-hoc cells (Athene, Chronos, Nemesis, Eris, Mnemosyne) that observe and improve the chronicle
- [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md): canonical doctrine for the current Function-First Phase — function before polish; fastest autonomous compounding; engineering order **data structure → synthesis → retrieval**; non-negotiable structures stay intact but automated at scale (rear attention); truth/security deepen later chiefly via more agents — no premature numeric SLAs; binds every ingestion path, validator, and pipeline until explicitly superseded
- [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md): canonical long-horizon doctrine — the Pantheon eventually writes its own next version; conditions and constraints
- [`PHILOSOPHY.md`](../PHILOSOPHY.md): the civilizational and ethical foundation

### Deep Concept Documents

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

- [`ARCHITECTURE.md`](ARCHITECTURE.md): the current system blueprint
- [`GLOSSARY.md`](GLOSSARY.md): canonical terminology
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

- [`hosted/README.md`](../hosted/README.md): Docker image, Fly.io / Hugging Face Spaces / Modal notes, Smithery listing, `/health`, rate limits (PHX-0066 Phase 1)

### Builder Agent Prompts

The [`prompts/`](../prompts/) directory holds the constitutional prompts for **builder agents** — the mortal craftsmen who design and implement Theogony. They are distinct from **Pantheon agents** (Argus, Athene, …), which are mythological *roles* in the runtime/agent architecture, not the Pantheon-as-substrate meaning. See [`GLOSSARY.md`](GLOSSARY.md#builder-agents) for the builder list and the Pantheon disambiguation.

Current prompts:

- [`prompts/daedalus.md`](../prompts/daedalus.md) — the architect who designs the substrate.
- [`prompts/talos.md`](../prompts/talos.md) — the implementer who builds the substrate, milestone by milestone, with green tests.

## Suggested Use

- When writing new documents, align your terminology with [`GLOSSARY.md`](GLOSSARY.md).
- When proposing new architectural ideas, cross-check them against [`PANTHEON_VISION.md`](PANTHEON_VISION.md), [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md), [`VISION.md`](VISION.md), [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md), and [`ARCHITECTURE.md`](ARCHITECTURE.md).
- When an idea belongs to a future generation rather than the current one, add it to the Phoenix backlog.
- When in doubt about the spirit of the project, return to [`README.md`](../README.md) and [`PHILOSOPHY.md`](../PHILOSOPHY.md).
