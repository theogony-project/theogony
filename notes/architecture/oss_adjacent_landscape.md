# Adjacent OSS and Research (Orientation Note)

**Language:** English (repo convention)  
**Status:** orientation only — not a binding plan  
**Context:** External summary (e.g. Gemini) pointed at several families of systems that share *pieces* of the Chronik direction (vector binding, LLM graph extraction, post-hoc clustering). This note maps **what is worth reading** versus **what is not a drop-in substitute** for the Tensor-Manifold + Spreading Activation core.

Canonical internal mesh concept note (German MVP draft): [`vector_native_spreading_activation.md`](vector_native_spreading_activation.md).

Reading-agent vision (how “reading” differs from one-shot parsing): [`reading_agent_vision.md`](reading_agent_vision.md).

### Web articles (May 2026)

- **[The Math You Need To Start Understanding LLMs](https://hackaday.com/2026/05/04/the-math-you-need-to-start-understanding-llms/)** (Hackaday) — Pointers to logits, embeddings, transformer/attention math; complements the vector/tensor language in `vector_native_spreading_activation.md`.

- **[The RAG era is ending for agentic AI — a new compilation-stage knowledge layer is what comes next](https://venturebeat.com/data/the-rag-era-is-ending-for-agentic-ai-a-new-compilation-stage-knowledge-layer-is-what-comes-next)** (VentureBeat) — “Compile knowledge once for agents” vs cold per-session RAG; **analogy** to our ingest/heal split, **not** a blueprint (commercial stack, declarative agent query layer ≠ CSR mesh + constellation return).

---

## 1. Holographic Reduced Representations (HRR) and Vector Symbolic Architectures (VSA)

**Idea:** Bind roles and fillers, superpose sets, and decode with clean-up memory — all in a single high-dimensional space using fixed algebraic operations (circular convolution / binding variants).

**Overlap with Theogony:** Conceptually close to “relations live in vector space, not only as symbolic triples.”

**Difference:** HRR/VSA is primarily **compositional algebra** over a small set of symbols per query step. The Chronik Gen-1 core targets **very large meshes**, **first-class edge vectors** (often codebook-compressed), and **Spreading Activation via SpMV** over CSR tensors — a different computational regime than a single HRR state vector.

**Practical use:** Spike-read if we ever want **explicit bind/unbind** operators alongside mesh edges. Until then, edge vectors + relation codebook in `tensor_engine.py` are enough.

---

## 2. Graphiti (Zep AI)

**What it is:** Open-source Python library for **LLM-driven, incrementally updated** knowledge graphs with a strong “agent memory” story (entities, episodes, temporal awareness).

**Repository:** https://github.com/getzep/graphiti

**Overlap:** Very close to **Synaptogenesis** — LLM extracts nodes/edges and the system mutates a graph for downstream agents.

**Difference:** Typical stack optimises **agent memory + retrieval**, not **extreme edge density** or **GPU-resident CSR Spreading Activation** as the primary read path. Schema, storage, and doctrine (RunReports, Immune System) will not match ours.

**Practical use:** Read for **prompting patterns**, **edge typing**, **incremental write paths**, and **test ideas** — not as the substrate for the core mesh.

---

## 3. “LLM Wiki” pattern and post-hoc graph clustering (e.g. Louvain)

**What it is:** Incremental wiki-style capture (famously illustrated by Andrej Karpathy’s gist pattern) plus optional **community detection** (Louvain, Leiden, etc.) over a similarity or co-occurrence graph to merge or surface clusters after the fact.

**Reference (LLM Wiki pattern):** https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

**Overlap:** Aligns with **Function-First** growth and **post-hoc healing**: allow fragmentation at ingest; consolidate later using graph/vector signals — the same *moral* as our Immune System, not a prescription to use Louvain specifically.

**Difference:** Louvain operates on a **graph summary** we must **derive** from the mesh (or from co-activation logs). It is not a replacement for Spreading Activation retrieval.

**Practical use:** When we implement consolidation passes, treat Louvain/Leiden as **one optional tool** among vector similarity + agent audits — wire behind reports, not in the hot ingest path.

---

## 4. Other named projects (SECOND ME, OpenChronicle, …)

**Caution:** Names and READMEs often align on **“autonomous knowledge”** marketing, but data models, scale targets, and governance differ. Treat them as **bibliography**, not blueprints: skim for UX patterns, agent loops, or delta/event logs — verify fit before any dependency or fork.

---

## Summary table

| Family              | Steal ideas from              | Do not assume                    |
|---------------------|-------------------------------|----------------------------------|
| HRR / VSA           | Binding, superposition design | Same runtime as CSR SpMV mesh   |
| Graphiti            | LLM graph extraction, updates | Core tensor retrieval substrate  |
| Wiki + Louvain      | Post-hoc clustering narrative | Up-front truth / human review   |
| Generic “AI memory” | Agent orchestration           | Edge density + latent-native I/O |

---

## When to escalate to code

- **Dependency:** Only after a Phoenix ticket + plan alignment (YAGNI; see `AGENTS.md`).
- **Doc-only:** This file may be updated as we retire or confirm adjacent systems after short spikes.
