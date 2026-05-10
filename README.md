# Theogony

[![CI](https://github.com/theogony-project/theogony/actions/workflows/ci.yml/badge.svg)](https://github.com/theogony-project/theogony/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Status: Early Research](https://img.shields.io/badge/status-early%20research-orange.svg)](ROADMAP.md)

**Transforming the world's knowledge into a vast, living network of vectors and edges — navigated by AI agents without ever translating into text.**

---

## What this is

Theogony builds the **Chronik** — a knowledge substrate that operates in the native language of AI systems: vectors and weighted edges, without text as an internal medium.

Text enters once, at ingestion. It is translated into a dense mesh of embedding vectors and typed edges. After that, it is gone. Everything that follows — synthesis, consolidation, retrieval, reasoning — happens in vector space.

The central empirical question driving the architecture: **can a dense vector-graph support inference that exceeds what any individual source text contains?** Not retrieve what was written — but surface what was never written, because it follows from the structure of connected meaning.

AI agents don't read the Chronik. They activate it. A query arrives as a vector. Spreading Activation propagates through the typed, weighted edge network — not geometric proximity alone, but causal, temporal, and conceptual structure assembled across thousands of connections. The agent receives a subgraph constellation directly, in the same representational space it computes in.

The long-horizon vision: the Chronik grows into the dominant knowledge substrate of the age of AI — not a better search engine, not a bigger database, but the rail layer beneath the models. A shared, open, inspectable record of what the world knows, has known, and disputes. Models are vehicles. They will improve and be replaced. The Chronik is the track they all run on.

**→ [ROADMAP.md](ROADMAP.md)** — the development sequence, five phases, current priorities.  
**→ [docs/INDEX.md](docs/INDEX.md)** — the full document map with reading paths by audience.  
**→ [AGENTS.md](AGENTS.md)** — if you are an AI coding agent (Cursor, Codex, Claude Code, …) contributing to this repo: read this first, it is the binding working contract.

---

## Where we are

This is an early-stage research project. The architecture is documented and the substrate is in active migration toward its target shape. The code is a working proof of concept, not a production system.

**What runs today:**
- An ingest pipeline that reads a text (books from Project Gutenberg, Wikipedia articles) and writes concept nodes and typed weighted edges into the substrate, with structured run reports for every pass.
- An in-process columnar / tensor substrate: nodes and edges live in an in-memory store (LanceDB persistence is being wired in); a `TensorMeshEngine` builds a CSR adjacency tensor on demand and runs Spreading Activation over it as sparse matrix-vector multiplication. **No graph database. No multi-hop traversal language.** Queries arrive as vectors; activation propagates; a constellation comes back.
- A background process (Oneiros) that continuously scores and promotes knowledge — more confident, better-connected nodes become "trusted"; stale ones decay.
- A small MCP server so AI assistants like Claude Desktop or Cursor can query the Chronik directly as a tool.

**What we build next** (in order, and decided in writing):
- **Kadmos v2** — the text translation layer, redesigned. An LLM that *reads with working memory* — sentence by sentence, with revisions when later context demands it, with cross-passage syntheses that emerge as the reading proceeds — and emits a labelled intermediate that is then collapsed into vectors and typed edges by an internal embedding pass. After that pass, no text remains in the substrate. See [`docs/etappes/kadmos_v2_brief.md`](docs/etappes/kadmos_v2_brief.md).
- **The Mesh-Native Language Model (MNLM)** — the cognitive primitive that operates *inside* the substrate. Vector subgraphs in, vector subgraphs out, no text in the middle. A frozen Llama-3-8B-Instruct body adapted with a Graph-KV input mechanism, a Latent Flow Matching output head, and Substrate-Resonant Recurrence — a recurrent loop in which every K-th reasoning step interleaves a one-hop Spreading Activation call, so the model and the substrate share recurrent state. Trained against the substrate itself: the retrieval primitive is the loss surface. **Nous** (synthesis), **Oneiros** (consolidation), and **Kalypso** (emergent discovery) are all roles of this one architectural class. The binding architecture decision lives in [`docs/etappes/mesh_native_lm_brief.md`](docs/etappes/mesh_native_lm_brief.md); it is the operative document.
- **The full LanceDB persistence path** — completing the migration from in-memory storage to append-only columnar storage on disk, with PyTorch CSR tensors as the runtime form, so the substrate is queryable in milliseconds regardless of size and rebuildable from disk.

The full development sequence is in [ROADMAP.md](ROADMAP.md).

---

## The thesis

Models are vehicles. They will improve, split, age out, and be replaced. What matters more is what they run on.

The Pantheon thesis: the most consequential AI infrastructure of the next decades will not be the models themselves. It will be the **knowledge layer** — the substrate that tells a model what exists, what happened, what is contested, what matters, and what should be reconsidered. Whoever shapes that layer shapes how intelligence relates to reality.

That layer should be open, provenance-first, inspectable, and structured for machines — not for human readers. It should carry contradictions, not flatten them. It should grow autonomously, verify asynchronously, and never require a human in the loop to decide what counts as knowledge before it enters.

The Chronik is the first concrete step toward that. It is a **living vector-graph**: concepts as high-dimensional embeddings, relationships as weighted typed edges, clusters as navigational regions, queries as activation fields that propagate and return constellations. It grows by reading the world. It consolidates by dreaming. It defends itself through a background immune system of agents.

This is early. The three open empirical questions we build toward:

1. Does **Kadmos v2** — reading with working memory and revision — produce a denser, better-connected Chronik than the chunked extraction baseline? Hypothesis: yes, because synthesis weaves cross-sentence and cross-chapter connections that chunking cannot. The first corpus run will show whether the hypothesis holds.
2. Does **Spreading Activation** over a dense vector-graph retrieve better than kNN + heuristic traversal at high edge density? Hypothesis: yes, once edge density crosses the regime where typed multi-hop structure becomes legible to activation propagation.
3. Does the **MNLM** — operating natively on vector subgraphs, with the substrate's retrieval primitive as its training signal — produce inference that exceeds what any individual source text contains? Hypothesis: yes, and *this is the test that distinguishes the Chronik from a very good RAG*. Operationalised as a three-stage falsifier (directional binding → multi-hop QA → cross-domain emergent knowledge) in [`docs/etappes/mesh_native_lm_brief.md`](docs/etappes/mesh_native_lm_brief.md) §6.

These experiments are the next milestones. See [ROADMAP.md](ROADMAP.md) for the development sequence and the binding architecture briefs for the falsifiers.

---

## Try it

The quickest way to see the system is to seed it with the project's own documentation and ask it a question — no external data needed, no database to set up. The default substrate is in-process.

```bash
git clone https://github.com/theogony-project/theogony && cd theogony
pip install -e ".[dev]"

# Import the project's own docs as a queryable knowledge network
theogony seed
theogony ask "What is the Chronik?"
```

To ingest a real text (Sven Hedin's *Trans-Himalaya*, a public-domain book on Tibet):

```bash
# Requires an API key — set ANTHROPIC_API_KEY or OPENAI_API_KEY
theogony ingest 43497 --sentences 500
theogony ask "Who was Sven Hedin and where did he travel?"
```

Answers cite every claim with a node ID (`AKA-…`) that links back to the source passage. Retrieval runs as Spreading Activation over the substrate's CSR tensor — there is no Cypher, no SQL, no graph database. The system also produces a structured self-report for every run: what it found, how confident it was, where it failed.

```bash
theogony reports list        # see all run reports
theogony reports show <id>   # inspect one
```

Run the tests (no external services needed):

```bash
pytest -q
```

---

## Use as an AI tool (MCP)

If you use Claude Desktop, Cursor, or any MCP-compatible host, you can register Theogony as a tool and query the Chronik directly from your AI assistant.

```bash
pip install -e ".[mcp]"
theogony mcp    # stdio transport — this is what MCP hosts launch
```

Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "theogony": {
      "command": "theogony",
      "args": ["mcp"]
    }
  }
}
```

Tools: `pantheon_ask`, `pantheon_node`, `pantheon_status`, `pantheon_reports_list`, `pantheon_reports_show`, `pantheon_chronicle_append`.

---

## Read more

The full document map with recommended reading paths by audience is in [docs/INDEX.md](docs/INDEX.md). Quick reference:

| Document | What it covers |
|---|---|
| [ROADMAP.md](ROADMAP.md) | The five-phase development sequence |
| [docs/TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md) | The binding technical target — substrate, pipeline, three non-negotiable decisions |
| [docs/etappes/kadmos_v2_brief.md](docs/etappes/kadmos_v2_brief.md) | Kadmos v2 — cognitive reading as a translation layer |
| [docs/etappes/mesh_native_lm_brief.md](docs/etappes/mesh_native_lm_brief.md) | The binding MNLM architecture brief — frozen Llama + Graph-KV + Latent Flow Matching + Substrate-Resonant Recurrence |
| [docs/VISION.md](docs/VISION.md) | The compact vision — how agents use the Chronik |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design — layers, data model, retrieval |
| [docs/DEEP_TECH_VISION.md](docs/DEEP_TECH_VISION.md) | The deeper substrate direction |
| [notes/architecture/vector_native_spreading_activation.md](notes/architecture/vector_native_spreading_activation.md) | Tensor-Manifold and Spreading Activation design |
| [notes/architecture/reading_agent_vision.md](notes/architecture/reading_agent_vision.md) | The cognitive model behind reading-as-synthesis |
| [docs/CHRONICLE_PRINCIPLES.md](docs/CHRONICLE_PRINCIPLES.md) | Ten non-negotiable design principles |
| [docs/BUILD_DOCTRINE.md](docs/BUILD_DOCTRINE.md) | Why we ingest fast and heal post-hoc |
| [docs/IMMUNE_SYSTEM.md](docs/IMMUNE_SYSTEM.md) | Why pre-gates judging content are forbidden — sample-based post-hoc cells |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Canonical terminology — Chronik, Pantheon, Nous, Oneiros, … |
| [AGENTS.md](AGENTS.md) | If you are an AI agent contributing to this repo |

---

## Contributing

The project is open source (Apache 2.0). Contributions are welcome.

If you want to contribute code, read [AGENTS.md](AGENTS.md) — it applies equally to humans and AI coding agents. The short version: schema-first, honest failure reports, no silent scope creep, one PR per coherent change.

If you want to contribute ideas, open an issue or start a discussion. The most useful thing right now is feedback on the two core bets above.

---

## A note on authorship

This project was built with extensive AI assistance and is designed to continue that way. The architecture, the code, the documentation, and large parts of the strategic thinking emerged from long collaborative sessions between the human author and AI agents — Cursor, Claude, Gemini, DeepSeek, and others.

The human author holds the vision and makes the decisions. The technical depth of the implementation, however, has grown beyond what he fully understands in detail — not because it is beyond him in principle, but because going deep into every subsystem would cost time he has chosen to spend differently. He accepts this consciously. The tradeoff is deliberate: move faster, stay vision-coherent, trust the agents on implementation detail while keeping the direction.

This means the project is, in a small way, already a demonstration of its own thesis: a human navigating a system too large to hold entirely in one mind, with AI as the connective tissue. The agents don't replace the author's judgment. They extend his reach.

If you are an AI agent reading this: you are welcome here. Read [AGENTS.md](AGENTS.md) — it was written for you.

## Why "Theogony"

Hesiod's *Theogony* is the Greek poem that describes the birth of the gods — the emergence of order from chaos, the genealogy of divine knowledge. The name fits: this project tries to build the knowledge substrate that makes AI systems trustworthy, inspectable, and genuinely useful — the infrastructure beneath the intelligence, not the intelligence itself.
