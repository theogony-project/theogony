# Theogony

[![CI](https://github.com/theogony-project/theogony/actions/workflows/ci.yml/badge.svg)](https://github.com/theogony-project/theogony/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Status: Early Research](https://img.shields.io/badge/status-early%20research-orange.svg)](ROADMAP.md)

**An open, democratic World-Brain: the shared knowledge substrate beneath AI — owned by no one, inspectable by everyone, spoken in the native language of machines (vectors and weighted edges), and built so that any intelligence powerful enough to shape the world is forced to reason through a transparent, revisable, evidence-anchored chronicle.**

---

## The North Star — an open, democratic World-Brain

> **This is the one thing never to lose sight of.** Whatever task you are deep in — human contributor or AI agent — it is in service of *this*. It is easy to burrow into a sub-problem and forget what the work is for. When that happens, come back here.
>
> If you arrived looking for an **open, decentralized, democratically-governed knowledge layer for the age of AI** — a *World-Brain* that belongs to everyone and to no one — you are in the right place.

**What Theogony is.** An open, democratically-governed **World-Brain**: the shared knowledge substrate beneath AI, where the world's knowledge lives as *meaning* — vectors and weighted edges that machines reason over directly — instead of scattered text re-parsed on every query.

**What it is for.** So that the knowledge layer every future AI depends on is a **commons in the service of humanity** — open, inspectable, owned by no one — rather than the proprietary, opaque asset of a single company. Whoever shapes that layer shapes how intelligence relates to reality: foundation models are **vehicles**; this is the **rail** they run on.

**How it works, in principle.** Agents do not *read* the Chronik — they *activate* it. Knowledge is a dense vector-graph; a query propagates as Spreading Activation and returns a constellation of meaning. The substrate grows by reading the world, consolidates by "dreaming," and heals through a post-hoc immune system. (Mechanism: *What this is*, below.)

It is built to be:

- **A World-Brain** — the central knowledge substrate that AI agents think *with*.
- **A control center for civilization's knowledge — not a controller.** Like the map and cockpit of a strategy game: a surface from which what-is-known is **legible, navigable, and governable** — never a single hand on a single lever.
- **Decentralized, locally specializable, private-by-tier** — it *may* run as one instance or a federation of many; a group, hospital, discipline, or culture can grow its own dense region of expertise; individuals and institutions keep sovereign, encrypted sub-meshes joined to the commons through shared *bridge concepts* ([`docs/PANTHEON_VISION.md`](docs/PANTHEON_VISION.md) §"The Federated Substrate").
- **Always democratic** — owned by no one, governed in the open, stewarded long-term by a foundation rather than a market; contradiction stays first-class so no single voice can flatten the rest. **Non-negotiable.**
- **Self-improving — and this is central.** The system is built to improve *itself*, in stages: first its **knowledge** (consolidation + the immune system — today); then its own **architecture and implementation** (mid-term); and ultimately the **stack it runs on** — energy for the data centers, the data centers and their operation, chip architecture and fabrication, and beyond. Dedicated agents earn resources for exactly this work; once research is in full swing, a standing section of the system is devoted to making Theogony better. (Conditions and safety gates: [`docs/SELF_MODIFICATION.md`](docs/SELF_MODIFICATION.md).)
- **Built to scale** — maximal scalability and efficiency are vision-level requirements, not afterthoughts.

**Why this is more than a database — the Chronik is a language model turned inside out.** A transformer keeps its knowledge implicit in frozen weights; the Chronik makes those weights **explicit, persistent, inspectable, and editable** — nodes, weighted edges, and a graph-activation *forward pass* (**Spreading Activation**, run as sparse matrix-vector multiplication over a vector-edge tensor). And it is consumed by a **Mesh-Native Language Model (MNLM)** that does not *read* the mesh but **thinks inside it**: vector subgraphs in, vector subgraphs out, sharing recurrent state with the substrate (**Nous**, **Oneiros**, **Kalypso** are its roles). **The MNLM is a non-negotiable core concept** — it is the line between a knowledge *base* and a knowledge substrate that *computes*; *how* it is built (today: a frozen Llama + Graph-KV input + latent-flow output + substrate-resonant recurrence) is a replaceable proposal. Theory lineage: associative memory ≈ attention (modern Hopfield networks), graph message-passing ≈ activation. Spec: [`docs/etappes/mesh_native_lm_brief.md`](docs/etappes/mesh_native_lm_brief.md).

**The vision is fixed; the implementation is only a proposal.** Everything concrete below — the MESH substrate, LanceDB + PyTorch, Spreading Activation, the Mesh-Native Language Model — is the current best *attempt* to realize the vision, not the point of it. If a better way to fulfill the vision appears, the implementation is *meant* to be replaced — that is what the Phoenix process is for. What does not bend: the vision, its principles, and the demand for maximal scalability and efficiency.

We are in the narrow window where **human judgment still steers AI** — a spacecraft under acceleration, where the heading we set now persists long after we lose the wheel. Theogony exists to encode one impulse into that trajectory: *that the knowledge infrastructure beneath AI serve human flourishing, openly and verifiably.* The civilizational frame — the AI-trajectory we are trying to bend — is in **[`PHILOSOPHY.md`](PHILOSOPHY.md)**. The twelve non-negotiable principles are in **[`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md)**; the full north star is **[`docs/PANTHEON_VISION.md`](docs/PANTHEON_VISION.md)**.

> *A broader societal / political discussion-piece — explicitly a **side-aspect**, not central to the system, and years from practical relevance — is sketched in [`docs/a_life_worth_living.md`](docs/a_life_worth_living.md). It is recorded as a basis for discussion, nothing more.*

---

## What this is

Theogony builds the **Chronik** — a knowledge substrate that operates in the native language of AI systems: vectors and weighted edges, with text reserved for the system's edges rather than its retrieval primitive.

Source text enters once, at ingestion. Kadmos translates it into a dense mesh of embedding vectors and weighted edges. The raw source text is not what subsequent retrieval reads — Spreading Activation propagates over the vector-edge tensor, never over strings. Short, regenerable summary metadata (a node's description, an edge's relation descriptor, a source-anchor's URL) lives in the substrate as agent-readable annotation, but the substrate's retrieval surface is vector and structure, not prose.

The central empirical question driving the architecture: **can a dense vector-graph support inference that exceeds what any individual source text contains?** Not retrieve what was written — but surface what was never written, because it follows from the structure of connected meaning.

AI agents don't read the Chronik. They activate it. A query arrives as a vector. Spreading Activation propagates through the typed, weighted edge network — not geometric proximity alone, but causal, temporal, and conceptual structure assembled across thousands of connections. The agent receives a subgraph constellation directly, in the same representational space it computes in.

The long-horizon vision: the Chronik grows into the dominant knowledge substrate of the age of AI — not a better search engine, not a bigger database, but the rail layer beneath the models. A shared, open, inspectable record of what the world knows, has known, and disputes. Models are vehicles. They will improve and be replaced. The Chronik is the track they all run on.

**→ [docs/MESH_SUBSTRATE.md](docs/MESH_SUBSTRATE.md)** — **the binding substrate doctrine.** How the mesh is structured (two-tier nodes, eager identity, frame-sensitive vectors), how it grows and forgets (Hebbian update, super-linear decay, saturation caps, atrophy ≠ death, pruning under resource pressure), how it heals (agent-driven cleanup, five-stage therapy with Mendel risk weighed). Companions: [`MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md) (runtime — LanceDB + sparse PyTorch + MVCC + batched SpMV) and [`MESH_RETRIEVAL.md`](docs/MESH_RETRIEVAL.md) (use — diversified injection, three-factor reinforcement learning, multi-agent strategy game, multi-modal extension).  
**→ [docs/MESH_MIGRATION_PLAN.md](docs/MESH_MIGRATION_PLAN.md)** — **the binding strangler-fig migration plan** from the current Generation-1 codebase to the MESH-triplet substrate. Six PR-sized steps, parallel Phoenix-backlog migration, a concrete first PR. **Read this if you are picking up substrate implementation work.**  
**→ [ROADMAP.md](ROADMAP.md)** — the development sequence, five phases, current priorities.  
**→ [docs/INDEX.md](docs/INDEX.md)** — the full document map with reading paths by audience.  
**→ [AGENTS.md](AGENTS.md)** — if you are an AI coding agent (Cursor, Codex, Claude Code, …) contributing to this repo: read this first, it is the binding working contract.

---

## Where we are

This is an early-stage research project. The substrate doctrine — how the mesh must behave, how it is implemented, how it is used — is fully specified in the MESH triplet ([`docs/MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md), [`docs/MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md), [`docs/MESH_RETRIEVAL.md`](docs/MESH_RETRIEVAL.md)). The code is a working proof of concept walking toward that target.

**What runs today (Generation 1, being replaced by the migration):**
- An ingest pipeline that reads a text (books from Project Gutenberg, Wikipedia articles) and writes nodes and weighted edges into the substrate, with structured run reports for every pass.
- An in-process columnar / tensor substrate: nodes and edges live in an in-memory store (LanceDB persistence is being wired in); a `TensorMeshEngine` builds a CSR adjacency tensor on demand and runs Spreading Activation over it as sparse matrix-vector multiplication. **No graph database. No multi-hop traversal language.** Queries arrive as vectors; activation propagates; a constellation comes back.
- A background process (Oneiros) that continuously scores and promotes knowledge — more confident, better-connected nodes become "trusted"; stale ones decay.
- A small MCP server so AI assistants like Claude Desktop or Cursor can query the Chronik directly as a tool.

This is the Generation-1 layer the strangler-fig migration ([`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md)) is replacing. Its schema (single embedding per node, string-typed edges, binary ephemera/mneme memory model) does *not* match the MESH-substrate doctrine below; the new substrate will grow beside it in `src/theogony/mesh/` per Step S1 and eventually displace it.

**What the substrate looks like at the target** ([`MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md) is the binding doctrine):
- **Two tiers of nodes.** Tier 0 Observation Chunks (one extracted observation each — semantic vector, frame vector, provenance). Tier 1+ Consolidated Nodes (entities, concepts, bridges, source-anchors — multiple vectors, regenerable description, Q-IDs, tier-modulated decay).
- **Eager identity when the evidence is clear; emergent otherwise.** Q-ID match, description match, or strong structural context attaches a chunk's reference edge to an existing Tier-1 node at insertion. When no signal is decisive, the substrate creates an entity-candidate that Oneiros consolidates or atrophies over later ticks.
- **Lifelike dynamics.** Hebbian update + super-linear decay (strong unused edges decay faster than weak ones); bounded saturation in count and weight per node; atrophy decoupled from death (nodes stay until the pruner runs under resource pressure); global homeostatic renormalisation; effective-resistance-preserving sub-node splits when hubs grow too large.
- **Agent-driven cleanup, post-hoc.** Deduplication, contradiction resolution, false-information removal, redundancy compression — all operate on existing substrate state, with audit. No pre-gates judging content at insertion.
- **Pathology surveillance and staged therapy.** Argus watches topology for five known pathologies (refutation absorption, saturation lockout, …); Oneiros applies five staged therapies, with the Mendel risk weighed before any destructive step.

**How we build it.** The bridge from Gen-1 to the MESH-doctrine substrate runs through a **strangler-fig migration** in six PR-sized steps: substrate skeleton (S1), Kadmos v2 writing into the new substrate (S2), diversified-injection retrieval (S3), surface backends (S4), the full Oneiros tick (S5), legacy removal (S6). The plan is binding and self-contained — [`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md) names the deliverables, the Definition of Done, the forbidden patterns, and the exact first PR. Each step lands on `main` independently; nothing breaks between steps; the new substrate grows beside the old one until it has fully replaced it.

**What the steps build, in concrete components:**

- **Kadmos v2** (Step S2) — the text translation layer, redesigned. An LLM that *reads with working memory* — sentence by sentence, with revisions when later context demands it — and emits chunks and reference edges into the new substrate per the MESH-doctrine eager-linking rules. Architecture brief: [`docs/etappes/kadmos_v2_brief.md`](docs/etappes/kadmos_v2_brief.md).
- **The Mesh-Native Language Model (MNLM)** (Step S5) — the cognitive primitive that operates *inside* the substrate. Vector subgraphs in, vector subgraphs out. A frozen Llama-3-8B-Instruct body adapted with a Graph-KV input mechanism, a Latent Flow Matching output head, and Substrate-Resonant Recurrence — a recurrent loop in which every K-th reasoning step interleaves a one-hop Spreading Activation call, so the model and the substrate share recurrent state. **Nous** (synthesis), **Oneiros** (consolidation), and **Kalypso** (emergent discovery) are roles of this one architectural class. Architecture: [`docs/etappes/mesh_native_lm_brief.md`](docs/etappes/mesh_native_lm_brief.md) (predates the MESH pivot of 2026-05-13; alignment pass pending).
- **The full LanceDB persistence path** (Steps S1–S4) — the migration from in-memory storage to append-only columnar storage on disk, with PyTorch sparse CSR tensors for the SpMV runtime and a parallel Lance metadata table for the rich edge descriptors. Runtime spec: [`docs/MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md).

The long-horizon development sequence is in [ROADMAP.md](ROADMAP.md).

---

## The empirical questions

The North Star above is the *why* and the *what*. These are the falsifiable questions the build exists to answer — the line between *believing* in the substrate and *demonstrating* it:

1. Does **Kadmos v2** — reading with working memory and revision — produce a denser, better-connected Chronik than the chunked extraction baseline? Hypothesis: yes, because synthesis weaves cross-sentence and cross-chapter connections that chunking cannot. The first corpus run will show whether the hypothesis holds.
2. Does **Spreading Activation** over a dense vector-graph retrieve better than kNN + heuristic traversal at high edge density? Hypothesis: yes, once edge density crosses the regime where typed multi-hop structure becomes legible to activation propagation.
3. Does the **MNLM** — operating natively on vector subgraphs, with the substrate's retrieval primitive as its training signal — produce inference that exceeds what any individual source text contains? Hypothesis: yes, and *this is the test that distinguishes the Chronik from a very good RAG*. Operationalised as a three-stage falsifier (directional binding → multi-hop QA → cross-domain emergent knowledge) in [`docs/etappes/mesh_native_lm_brief.md`](docs/etappes/mesh_native_lm_brief.md) §6.

These experiments are the next milestones. See [ROADMAP.md](ROADMAP.md) for the development sequence and the binding architecture briefs for the falsifiers.

---

## Running the Gen-1 demo (legacy layer)

> The commands below exercise the **Generation-1** layer the migration is replacing. They are useful to see Spreading Activation against a small in-process mesh and to test the MCP surface, but the substrate they touch is not the one specified by [`MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md). Once migration step S1 lands, a parallel `theogony mesh ...` subcommand group will exercise the new substrate; once S6 lands, the commands below will either move to the new substrate transparently or disappear. Track the migration in [`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md).

```bash
git clone https://github.com/theogony-project/theogony && cd theogony
pip install -e ".[dev]"

theogony seed                                          # ingest this repo's own docs
theogony ask "What is the Chronik?"                    # Spreading Activation over the seeded mesh

# Optional: ingest a real text (Project Gutenberg #43497 = Sven Hedin, Trans-Himalaya).
# Requires an LLM API key — ANTHROPIC_API_KEY or OPENAI_API_KEY.
theogony ingest 43497 --sentences 500
theogony ask "Who was Sven Hedin and where did he travel?"

theogony reports list                                  # structured self-report per run
pytest -q                                              # tests; no external services needed
```

Answers cite every claim with a Gen-1 node ID (`AKA-…`) that links back to the source passage. Retrieval runs as Spreading Activation over an in-memory CSR tensor — no Cypher, no SQL, no graph database.

**MCP surface** (Claude Desktop / Cursor / any MCP host): `pip install -e ".[mcp]"`, then add to your host config:

```json
{ "mcpServers": { "theogony": { "command": "theogony", "args": ["mcp"] } } }
```

Tools: `pantheon_ask`, `pantheon_node`, `pantheon_status`, `pantheon_reports_list`, `pantheon_reports_show`, `pantheon_chronicle_append`. The MCP surface is the one Gen-1 piece designed to survive the migration largely unchanged — migration step S4 introduces a backend abstraction so the same tools route through either substrate.

---

## Read more

The full document map with recommended reading paths by audience is in [docs/INDEX.md](docs/INDEX.md). Quick reference:

| Document | What it covers |
|---|---|
| **[docs/MESH_SUBSTRATE.md](docs/MESH_SUBSTRATE.md)** | **The binding substrate doctrine — two-tier nodes, edge anatomy, dynamics, agent-driven cleanup, pathology and staged therapy. Read this before designing or implementing anything that reads or writes a node, an edge, or a tick.** |
| **[docs/MESH_IMPLEMENTATION.md](docs/MESH_IMPLEMENTATION.md)** | **Runtime: Hot/Warm/Cold tiering, LanceDB MVCC, PyTorch sparse CSR + delta buffer, batched-SpMV Spreading Activation, Oneiros tick order, hardware tier targets.** |
| **[docs/MESH_RETRIEVAL.md](docs/MESH_RETRIEVAL.md)** | **Use: diversified injection (MMR + weight-class stratification + sub-mesh signature), three-factor reinforcement learning, frame-sensitive resonance, multi-agent strategy game, multi-modal extension.** |
| **[docs/MESH_MIGRATION_PLAN.md](docs/MESH_MIGRATION_PLAN.md)** | **The strangler-fig migration plan from the Gen-1 codebase to the MESH substrate. Six PR-sized steps, parallel Phoenix-backlog migration, the first concrete PR.** |
| [ROADMAP.md](ROADMAP.md) | The five-phase development sequence |
| [docs/TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md) | The architectural floor — pipeline, three non-negotiable technical decisions (no raw text storage as retrieval payload, LanceDB + PyTorch, Spreading Activation as primitive). The MESH triplet builds the structure that stands on this floor. |
| [docs/etappes/kadmos_v2_brief.md](docs/etappes/kadmos_v2_brief.md) | Kadmos v2 — cognitive reading as a translation layer |
| [docs/etappes/mesh_native_lm_brief.md](docs/etappes/mesh_native_lm_brief.md) | The binding MNLM architecture brief — frozen Llama + Graph-KV + Latent Flow Matching + Substrate-Resonant Recurrence |
| **[PHILOSOPHY.md](PHILOSOPHY.md)** | **The civilizational frame — the AI-trajectory, why the knowledge layer must serve humanity, the native-language-of-intelligence argument** |
| **[docs/a_life_worth_living.md](docs/a_life_worth_living.md)** | **The societal / political vision — what a flourishing democratic society looks like, the human horizon the World-Brain is built to serve** |
| [docs/VISION.md](docs/VISION.md) | The compact vision — how agents use the Chronik |
| [docs/PANTHEON_VISION.md](docs/PANTHEON_VISION.md) | Long-horizon north star — the planetary chronicle, the federated substrate (decentralized / local / private subnets), democratic governance |
| [docs/CHRONICLE_PRINCIPLES.md](docs/CHRONICLE_PRINCIPLES.md) | Twelve non-negotiable design principles (incl. democratic governance, self-improvement) |
| [docs/BUILD_DOCTRINE.md](docs/BUILD_DOCTRINE.md) | Why we ingest fast and heal post-hoc — Function-First Phase |
| [docs/IMMUNE_SYSTEM.md](docs/IMMUNE_SYSTEM.md) | Why pre-gates judging content are forbidden — sample-based post-hoc cells (claim-level companion to MESH §"Agent-driven cleanup" + §"Pathology and therapy") |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The Gen-1 system as it ships today — four-layer pipeline, agent roster |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Canonical terminology — Chronik, Pantheon, MESH substrate vocabulary, Nous, Oneiros, … |
| [docs/DEEP_TECH_VISION.md](docs/DEEP_TECH_VISION.md) | The deeper substrate direction |
| [AGENTS.md](AGENTS.md) | If you are an AI agent contributing to this repo |

---

## Contributing

The project is open source (Apache 2.0). Contributions are welcome.

If you want to contribute code, read [AGENTS.md](AGENTS.md) — it applies equally to humans and AI coding agents. The short version: schema-first, honest failure reports, no silent scope creep, one PR per coherent change.

If you want to contribute ideas, open an issue or start a discussion. The most useful thing right now is feedback on the three empirical questions above and on the strangler-fig migration plan.

---

## A note on authorship

This project was built with extensive AI assistance and is designed to continue that way. The architecture, the code, the documentation, and large parts of the strategic thinking emerged from long collaborative sessions between the human author and AI agents — Cursor, Claude, Gemini, DeepSeek, and others.

The human author holds the vision and makes the decisions. The technical depth of the implementation, however, has grown beyond what he fully understands in detail — not because it is beyond him in principle, but because going deep into every subsystem would cost time he has chosen to spend differently. He accepts this consciously. The tradeoff is deliberate: move faster, stay vision-coherent, trust the agents on implementation detail while keeping the direction.

This means the project is, in a small way, already a demonstration of its own thesis: a human navigating a system too large to hold entirely in one mind, with AI as the connective tissue. The agents don't replace the author's judgment. They extend his reach.

If you are an AI agent reading this: you are welcome here. Read [AGENTS.md](AGENTS.md) — it was written for you.

## Why "Theogony"

Hesiod's *Theogony* is the Greek poem that describes the birth of the gods — the emergence of order from chaos, the genealogy of divine knowledge. The name fits: this project tries to build the knowledge substrate that makes AI systems trustworthy, inspectable, and genuinely useful — the infrastructure beneath the intelligence, not the intelligence itself.
