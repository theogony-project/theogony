# Theogony

[![CI](https://github.com/theogony-project/theogony/actions/workflows/ci.yml/badge.svg)](https://github.com/theogony-project/theogony/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Status: Early Research](https://img.shields.io/badge/status-early%20research-orange.svg)](ROADMAP.md)

**Transforming the world's knowledge into a vast, living network of vectors and edges — navigated by AI agents without ever translating into text.**

---

## What this is

Reading a sentence, the brain doesn't store words. It stores concepts — massively interconnected, firing across prior knowledge, condensing into synthesis. Theogony builds the machine equivalent: the **Chronik**, a planetary knowledge substrate where every piece of knowledge exists as a node in a dense vector-graph, connected to thousands of other nodes by typed, weighted edges.

AI agents don't read the Chronik. They activate it. A thought arrives as a vector. Spreading activation propagates through the network — concepts lighting up, energy decaying along weak edges, a constellation of relevant structure assembling itself. The agent receives that constellation directly, in the same vector space it thinks in. No text. No chunking. No translation.

A large ecosystem of agents — with distinct roles, expertise, and memory — lives inside and around this network. They read the world into it. They dream connections across it. They heal it, verify it, prune it. They are permanently wired to it: their working memory, their biographical history, their task queues are all subgraphs in the Chronik itself.

The long-horizon vision: the Chronik grows into the dominant knowledge substrate of the age of AI — not a better search engine, not a bigger database, but the rail layer beneath the models. A shared, open, inspectable record of what the world knows, has known, and disputes. Models are vehicles. They will improve and be replaced. The Chronik is the track they all run on. The **Pantheon** — the full agent ecosystem that weaves, heals, and navigates it — is what makes it live.

Today we are building the foundations toward that.

---

## Where we are

This is an early-stage research project. The architecture is well-thought-out and documented. The code is a working proof of concept, not a production system.

**What runs today:**
- A pipeline that reads a text (currently: books from Project Gutenberg, Wikipedia articles), extracts concepts and relations using an LLM, and writes them as nodes and edges into a knowledge graph
- A retrieval layer that does multi-hop vector + graph search and returns cited answers
- A background process (Oneiros) that continuously scores and promotes knowledge — more confident, better-connected nodes become "trusted"; stale ones decay
- A small MCP server so AI assistants like Claude Desktop or Cursor can query the Chronik directly as a tool

**What we build next:**
- **Nous** — a cognitive synthesis agent that reads text the way a person does: sentence by sentence, with working memory, spreading activation against the existing Chronik in parallel, and synthesis that builds up from sentences to paragraphs to chapters. This produces a far denser, better-connected Chronik than the current chunk-by-chunk pipeline.
- **Tensor-Manifold** — replacing the current graph database (Neo4j) with a GPU-resident sparse tensor structure (LanceDB + PyTorch CSR). Spreading activation runs as matrix multiplication. Edges are vectors, not string labels. The Chronik becomes queryable in milliseconds regardless of size.
- **Chronik-as-Cross-Attention** — a proof of concept: a small open language model (1–3B parameters) that attends directly to the Chronik during inference, without a separate retrieval step. This is the technical demonstration that knowledge doesn't belong in model weights.

The full development sequence is in [ROADMAP.md](ROADMAP.md).

---

## The thesis

Models are vehicles. They will improve, split, age out, and be replaced. What matters more is what they run on.

The Pantheon thesis: the most consequential AI infrastructure of the next decades will not be the models themselves. It will be the **knowledge layer** — the substrate that tells a model what exists, what happened, what is contested, what matters, and what should be reconsidered. Whoever shapes that layer shapes how intelligence relates to reality.

That layer should be open, provenance-first, inspectable, and structured for machines — not for human readers. It should carry contradictions, not flatten them. It should grow autonomously, verify asynchronously, and never require a human in the loop to decide what counts as knowledge before it enters.

The Chronik is the first concrete step toward that. It is a **living vector-graph**: concepts as high-dimensional embeddings, relationships as weighted typed edges, clusters as navigational regions, queries as activation fields that propagate and return constellations. It grows by reading the world. It consolidates by dreaming. It defends itself through a background immune system of agents.

This is early. The two open empirical questions we build toward:

1. Does **Nous** — the cognitive synthesis reading agent — produce a denser, better-connected Chronik than chunked extraction? (We believe yes, because synthesis weaves cross-sentence and cross-chapter connections that chunking cannot. Needs to be shown.)
2. Does **Spreading Activation** over a dense vector-graph retrieve better than ANN search + graph traversal at high edge density? (We believe yes. Needs to be shown.)

These experiments are the next milestones. See [ROADMAP.md](ROADMAP.md).

---

## Try it

The quickest way to see the system is to seed it with the project's own documentation and ask it a question — no external data needed.

```bash
git clone https://github.com/theogony-project/theogony && cd theogony
pip install -e ".[dev]"

# Import the project's own docs as a queryable knowledge network
# (requires a running Neo4j — see below — and a local embedding model)
theogony seed
theogony ask "What is the Chronik?"
```

To run Neo4j locally:

```bash
docker compose up -d neo4j
```

To ingest a real text (Sven Hedin's *Trans-Himalaya*, a public-domain book on Tibet):

```bash
# Requires an API key — set ANTHROPIC_API_KEY or OPENAI_API_KEY
theogony ingest 43497 --sentences 500
theogony ask "Who was Sven Hedin and where did he travel?"
```

Answers cite every claim with a node ID (`AKA-…`) that links back to the source passage. The system also produces a structured self-report for every run: what it found, how confident it was, where it failed.

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

Tools: `pantheon_ask`, `pantheon_node`, `pantheon_status`, `pantheon_reports_list`, `pantheon_reports_show`.

---

## Read more

The full document map with recommended reading paths by audience is in [docs/INDEX.md](docs/INDEX.md). Quick reference:

| Document | What it covers |
|---|---|
| [ROADMAP.md](ROADMAP.md) | The five-phase development sequence |
| [docs/VISION.md](docs/VISION.md) | The compact vision — how agents use the Chronik |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design — layers, data model, retrieval |
| [docs/DEEP_TECH_VISION.md](docs/DEEP_TECH_VISION.md) | The deeper substrate direction |
| [notes/architecture/vector_native_spreading_activation.md](notes/architecture/vector_native_spreading_activation.md) | Tensor-Manifold and Spreading Activation design |
| [notes/architecture/reading_agent_vision.md](notes/architecture/reading_agent_vision.md) | Nous — the cognitive reading model |
| [docs/CHRONICLE_PRINCIPLES.md](docs/CHRONICLE_PRINCIPLES.md) | Nine non-negotiable design principles |
| [docs/BUILD_DOCTRINE.md](docs/BUILD_DOCTRINE.md) | Why we ingest fast and heal post-hoc |
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
