# Theogony — Roadmap

**Status:** Living document. Updated as phases complete.  
**Author:** Chaos (vision role), May 2026.  
**Audience:** Anyone who wants to understand where this is going and why.

This document is the single authoritative sequence of what Theogony builds,
in what order, and why each phase is a prerequisite for the next.
It is not a sprint plan. It is the horizon.

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
*parses* text into extractions.

### The Cognitive Synthesis Agent — **Nous**

A human does not extract concepts from a text. She synthesises them
continuously, sentence by sentence, carrying a working memory forward:
5–10 new concepts per sentence, plus ~50 activations from prior knowledge,
condensed into a synthesis that pre-warms the next sentence. Paragraphs
condense into chapter-syntheses. Repair fires when a new sentence
contradicts an earlier synthesis.

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

**Why this comes first:** Without Nous, the Chronik is filled by a
stateless parser. The Chronik's value is proportional to the quality
of synthesis at ingest. Better synthesis = richer structure = better
retrieval = better agents downstream.

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
Tensor-Manifold that supports Spreading Activation natively.

### Core architecture

| Layer | Technology | Role |
|---|---|---|
| **Persistent store** | LanceDB (Parquet/Arrow) | Append-only columnar vector storage for nodes and edges |
| **Runtime manifold** | PyTorch CSR tensors | Spreading Activation via SpMV, GPU-resident |
| **Edge representation** | First-class vectors + Codebook compression | Relation types as embeddings, not string labels |
| **Query interface** | Activation injection → Constellation return | No Cypher, no SQL |
| **Write interface** | Append-only ledger, supersedes-edges for corrections | Immutable provenance |

### Potential Escalation (Spreading Activation)

Activation injected at a query point spreads through the manifold:

```
E_target = (E_source × W_edge) - D_decay
```

Where edge weight `W_edge` is the cosine similarity between the stimulus
vector and the edge vector, modulated by Hebbian reactivation frequency
(pheromones). Propagation halts when energy drops below threshold `T_min`.

The result is a **Constellation** — a subgraph of nodes and edges above
the activation threshold, returned as a tensor matrix directly injectable
into a model's KV-cache or as soft prompts.

### Scale targets

| Phase | Nodes | Edges | Storage | Deployment |
|---|---|---|---|---|
| Gen 1 (current) | millions | tens of millions | gigabytes | single machine |
| Gen 2 | billions | trillions | terabytes | clustered |
| Gen 3 | trillions | — | petabytes | globally distributed |

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

The long-horizon goal: Mnemosyne observes enough to propose the next
version of the system — new thresholds, new agent configurations, new
Phoenix process parameters. These proposals land in the Phoenix Backlog
as first-class tickets. The Pantheon writes its own next incarnation.

This is documented in [`docs/SELF_MODIFICATION.md`](docs/SELF_MODIFICATION.md).
It is not a goal for current phases. It is the horizon that current
architecture must not accidentally block.

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
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture and layer definitions |
| [`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md) | Nine non-negotiable doctrines |
| [`docs/BUILD_DOCTRINE.md`](docs/BUILD_DOCTRINE.md) | Function-First Phase binding doctrine |
| [`docs/DEEP_TECH_VISION.md`](docs/DEEP_TECH_VISION.md) | Deeper substrate vision (six languages of the Chronik) |
| [`docs/COGNITIVE_ARCHITECTURE.md`](docs/COGNITIVE_ARCHITECTURE.md) | Cognitive model underlying the system |
| [`notes/architecture/reading_agent_vision.md`](notes/architecture/reading_agent_vision.md) | Reading Agent vision (detailed) |
| [`notes/architecture/vector_native_spreading_activation.md`](notes/architecture/vector_native_spreading_activation.md) | Tensor-Manifold and Spreading Activation design |
| [`docs/IMMUNE_SYSTEM.md`](docs/IMMUNE_SYSTEM.md) | Defense and self-improvement architecture |
| [`docs/SELF_MODIFICATION.md`](docs/SELF_MODIFICATION.md) | Long-horizon self-modification principle |
| [`docs/IMPLEMENTATION_PLAN_GEN1.md`](docs/IMPLEMENTATION_PLAN_GEN1.md) | Current generation implementation plan |
| [`docs/PHOENIX_BACKLOG.md`](docs/PHOENIX_BACKLOG.md) | Evolutionary ticket queue |
