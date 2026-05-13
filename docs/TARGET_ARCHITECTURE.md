# Target Architecture — The Chronik as a Sub-Linguistic Knowledge Substrate

**Status:** Binding technical target. All implementation work is measured against this.  
**Date:** 2026-05-08  
**Audience:** Implementers (Talos, Daedalus), contributors, anyone who wants to understand what this project is building.

---

## What this is

The Chronik is not a better search engine. It is not a smarter database. It is not RAG with graph features.

It is a **knowledge substrate that operates in the native language of AI systems** — vectors and weighted edges — without text as an internal medium.

The central architectural bet: a dense vector-graph can support inference that exceeds what any individual source text contains. Not by retrieving what was written. By surfacing what was never written but follows from the structure of what was.

This is the question the architecture is designed to answer empirically:

> **At what point does a vector knowledge graph become a genuine knowledge representation, capable of supporting inference that exceeds what any individual source text contains?**

Everything below is in service of answering that question.

---

## The Pipeline — What Actually Happens

```
World (text, Wikipedia, books, web)
    ↓
ARGUS — finds sources
    ↓
KADMOS — translates text into a primitive vector mesh
    Input:  raw text
    Output: nodes (embedding vectors) + typed local edges
            NEXT_SENTENCE, SAME_PARAGRAPH, SAME_SECTION, WIKI_LINK
    No LLM labels stored. No text stored. Only vectors and edges.
    Fast. No deep reasoning. Structurally faithful to the source.
    ↓
NOUS — weaves the primitive mesh into a denser knowledge network
    Input:  Kadmos vector mesh (no text)
    Output: denser mesh
            — diagonal edges (sentence concept → article theme)
            — cross-paragraph connections
            — synthesis nodes at higher abstraction levels
            — revision of earlier nodes when later context demands it
    Operates via GNN encoder + synthesis loop.
    Text is never an intermediate medium.
    ↓
CHRONIK — the persistent semantic space
    Storage:  LanceDB (columnar, append-only, versioned)
    Runtime:  PyTorch CSR tensor (Spreading Activation as SpMV)
    Nodes:    multiple embedding vectors (semantic, frame, structural, temporal,
              description) + optional regenerable description text + Q-ID tags +
              tier counters. Two tiers: Observation Chunks (Tier 0) and
              Consolidated Nodes (Tier 1+). Raw source text is NOT stored.
    Edges:    quantitative core (source, target, weight, decay_tier,
              frame_consistency) + optional semantic descriptors
              (relation_descriptor, relation_kind, description, P-IDs,
              creation_context). The quantitative core drives SpMV; the
              descriptors travel for agent / repair / debugging use.
    Provenance: source-anchor entities at Tier 1+ (URLs, DOIs, ISBNs) plus
              per-chunk raw_text_ref pointer (not retrieval payload).
    ↓
ONEIROS — thinks continuously
    Not a batch consolidation job.
    Simulates Observe and Remember internally:
    runs activation patterns over existing knowledge,
    treats results as new observations,
    writes back denser connections.
    The Chronik grows wiser without reading new texts.
    ↓
KALYPSO — discovers emergent connections
    Finds what nobody queried.
    Not retrieval. Emergence.
    ↓
IRIS — translates vector constellations into language
    Input:  activated subgraph (vectors + edges)
    Output: natural language for humans
    Does not retrieve stored text.
    Formulates from structure.
    THE ONLY POINT WHERE LANGUAGE IS GENERATED.
```

Language enters at Kadmos. Language exits at Iris. Everything in between is vector space.

The pipeline above describes a single mesh tier. The Chronik is designed to host **multiple federated tiers** — a global public layer, institutional sub-meshes, and personal sub-meshes — all connected via bridge nodes (shared concept vectors). Spreading Activation respects permission boundaries: it propagates into a sub-mesh only if the querying agent holds the access context for that tier. See [`PANTHEON_VISION.md`](PANTHEON_VISION.md) §"The Federated Substrate" for the full architectural description. Gen 1 implements the global public layer only; the data model is designed not to foreclose federation.

---

## The Three Non-Negotiable Technical Decisions

These are decided. They are not under discussion.

**1. No raw text storage after Kadmos.**  
Once Kadmos has translated a source, the raw source text is not stored in the Chronik as retrieval payload. SpMV reads vectors, not strings. A minimal `raw_text_ref` pointer exists per chunk so the immune system can re-derive from the source when needed; source-anchor entities (Tier-1+ nodes flagged with `is_source_anchor`) carry URLs, DOIs, ISBNs as structured anchors. Short text fields — `description` on nodes and edges, `relation_descriptor`, `tags`, `source_url` — are summary metadata, *not* raw source text, and they are explicitly permitted; they are how agents and humans read the mesh. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Field discipline" and §"Source-anchor entities".

**2. LanceDB + PyTorch, not Neo4j.**  
Neo4j is deprecated for the core mesh. It cannot execute Spreading Activation. It cannot handle 1000:1 edge/node density. It uses pointer-chasing, not tensor operations. The target store is LanceDB (append-only columnar vector store) with PyTorch CSR tensors for runtime Spreading Activation.

**3. Spreading Activation as the retrieval primitive.**  
Queries are not SQL or Cypher. A query arrives as a vector. Spreading Activation propagates energy through the typed, weighted edge network. The result is a subgraph — a Constellation — that reflects not just geometric proximity but causal, temporal, and conceptual structure that kNN alone cannot find.

---

## The Edge/Node Density Target

The current topology_parser produces ~0.5 edges per node. This is a parse, not a knowledge network.

A human cortical neuron has on average ~7,000 synaptic connections. That is the biological reference point for what a genuine knowledge substrate looks like. We are not trying to match biology — we are trying to reach the density at which Spreading Activation becomes a meaningful retrieval primitive and emergent inference becomes possible.

**Minimum viable density: 20:1.** Below this, the graph is too sparse for Spreading Activation to outperform kNN. Above this, multi-hop structural reasoning begins to work.

**Near-term target: 100–500:1.** Achievable with Kadmos structural edges + Nous synthesis edges + post-read kNN pass.

**Long-horizon: 1000:1+.** The density at which the Chronik approaches the connectivity of a genuine semantic substrate — where Oneiros dreaming and Kalypso discovery become meaningful.

How we get there:
- Kadmos: structural edges (sequential, hierarchical, wiki-links) — ~5:1
- Nous: semantic synthesis edges (diagonal, cross-level, causal) — ~15–50:1
- Post-read kNN pass: implicit similarity edges, top-k neighbors per node — ~100–200:1
- Oneiros: Hebbian reinforcement of traversed paths over time — cumulative

---

## What the Chronik Is Not

**Not RAG.** RAG stores text chunks and retrieves them. The Chronik stores meaning and generates language from it. If text is being stored as payload — in nodes, edges, or agent communications — it is RAG thinking, and it violates the architecture.

**Not a knowledge graph in the traditional sense.** Traditional knowledge graphs (Wikidata, DBpedia) store facts as subject-predicate-object triples whose retrieval primitive is graph traversal over string-labeled edges. The Chronik stores meaning as vectors and retrieves via Spreading Activation. Edges may carry optional semantic descriptors (`relation_descriptor`, `relation_kind`, P-IDs) for agent and human consumption — but the substrate's *retrieval primitive* is SpMV over the weighted edge tensor, not Cypher-style label matching. The descriptors travel with the edge; they are not the way the substrate finds things.

**Not a vector database.** A vector database does kNN search over embeddings. The Chronik does Spreading Activation over a dense typed graph. The difference is multi-hop, causal, temporal, structural reasoning — not just geometric proximity.

**Not a current-generation system.** The current codebase (Neo4j, JSON extraction, LLM-per-paragraph) is a proof of concept that demonstrated what does not work. It is Kadmos v1 — the translation layer — not the target system. Do not mistake the current implementation for the target architecture.

---

## The Open Empirical Questions

Three questions must be answered by running the system, not by design:

**Monkey 1:** Does cognitive synthesis (Nous) produce a denser, better-connected graph than extraction (Kadmos) on the same article?  
*Status: Kadmos v1 baseline established (0.49 ratio). True Nous not yet implemented.*

**Monkey 2:** Does Spreading Activation over a dense Chronik retrieve better than kNN + graph traversal?  
*Status: Not yet run. Requires Monkey 1 first.*

**Monkey 3:** Can the system answer questions whose answers are not present in any single source text — questions that require the system to have genuinely synthesized new knowledge from the structure of the graph?  
*Status: This is the ultimate test. It determines whether the Chronik is a very good RAG or something new.*

---

## What Implementers Must Not Build

These are failure modes observed in previous implementation rounds. Do not repeat them.

**Do not build stateless LLM-per-paragraph extraction into Kadmos.**  
Kadmos v1's failure was context-free extraction: one LLM call per paragraph, no memory of what came before, no revision. That pattern is forbidden. What is allowed — and what Kadmos v2 implements — is an LLM that reads with working memory, carries forward a running synthesis, and revises earlier concepts when later context demands it. This is not "extraction per paragraph". It is reading. The distinction matters: extraction treats each paragraph as an isolated data source; reading treats the text as a temporal experience that builds cumulative understanding.

Labels on concepts are a **transitional representation** inside Kadmos. They are produced by the LLM during the reading pass, used to build the rich intermediate structure (ReadingState, synthesis nodes, typed edges), and then translated into embedding vectors by Kadmos's internal embedding pass. The vectors are the substrate's retrieval primitives.

**Do not use text labels as the retrieval primitive.** A node's primary retrieval representation is its embedding vectors (semantic, frame, structural, temporal, description); its edges are the substrate's structural truth. *In addition*, Tier-1+ consolidated nodes carry an authoritative regenerable `description` (a short discriminating text summary) and edges may carry `relation_descriptor` / `description` / `pids` — these are agent-readable metadata for repair, disambiguation, LLM injection, and human inspection per [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Field discipline" point 4 and §"Edge anatomy". They are not retrieval primitives, but they are not "debugging only" either.

**Do not write through the Neo4j KnowledgeStore Protocol for Kadmos or Nous.** The KnowledgeStore Protocol is a legacy interface for the current codebase. Kadmos and Nous write directly to LanceDB. The migration is the architecture, not a future concern.

**Do not build Nous as an LLM that reads text.** Nous receives a vector mesh. Its input is not text. Its output is not JSON. It is a GNN encoder + synthesis loop that operates in vector space.

**Do not mistake the current codebase for the target.** The current system works. It is not the goal.

---

## For People Reading This Repository

If you are looking at this repository for the first time:

This project is building a knowledge system for AI agents that operates entirely in vector space — the same representational medium in which AI systems actually compute. Text enters at one end (via Kadmos) and exits at the other end (via Iris). Everything in between — storage, reasoning, synthesis, retrieval — happens in vectors and weighted edges.

The central claim is that this substrate can support a form of inference that text-based retrieval cannot: the emergence of knowledge that was never explicitly written, but that follows from the dense structure of connected meaning.

Whether this claim is true is an empirical question. The architecture is designed to answer it.

---

## Substrate-Level Doctrine (the operative companions)

This document specifies *what* the substrate must be. Three companion documents specify *how it behaves*, *how it is implemented*, and *how it is used*:

- [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) — canonical doctrine for the storage layer beneath all Pantheon cognition. Two-tier nodes (eager identity when clear, emergent when not), edge dynamics (super-linear decay, saturation, atrophy ≠ death, homeostatic renormalisation, effective-resistance-preserving sub-node splits), agent-driven cleanup (deduplication, contradiction resolution, false-information removal, redundancy compression), pathology surveillance and staged therapy with Mendel-weighed escalation. **Binds every agent that reads or writes a node, an edge, or a tick.** Where its substrate-layer doctrine differs from this document, that document is operative.
- [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) — implementation guidance: Hot/Warm/Cold tiering, Lance MVCC, batched-SpMV runtime, Oneiros tick order, hardware tier targets, migration from the current PoC.
- [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) — retrieval doctrine: diversified injection (MMR + weight-class stratification + sub-mesh signature search), three-factor reinforcement learning with eligibility traces, frame-sensitive resonance, multi-agent strategy-game framing with parallel-universe experimentation, multi-modal extension as substrate affordance.

The Three Non-Negotiable Technical Decisions in this document — no text storage, LanceDB + PyTorch, Spreading Activation as primitive — set the architectural floor. The MESH_* triplet builds the structure that stands on that floor.

---

*This document is binding. When in doubt about the direction of implementation, return here. When the question is about substrate behaviour, runtime, or use, continue into [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md), [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), and [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md).*
