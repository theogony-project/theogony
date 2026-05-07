# Theogony

[![CI](https://github.com/theogony-project/theogony/actions/workflows/ci.yml/badge.svg)](https://github.com/theogony-project/theogony/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Status: Early Research](https://img.shields.io/badge/status-early%20research-orange.svg)](ROADMAP.md)

**A knowledge substrate for AI systems — built so they stop needing to memorise the world.**

---

## What this is

AI models carry their knowledge inside their weights. That means every fact they know was baked in during training, goes stale after the cutoff date, and cannot be inspected, corrected, or cited. When you ask a model something, it draws on memory it cannot show you.

Theogony builds an alternative: a living, open knowledge network — the **Chronik** — that AI systems can navigate instead of memorise.

The idea is simple: instead of storing knowledge *inside* a model, you store it *beside* it, in a dense graph of concepts, relations, and sources. The model doesn't need to know facts. It needs to know how to find them. Every claim it makes can be traced back to a node in the network, which traces back to a source.

At the technical core: the Chronik is a **vector-graph** — concepts as embeddings, relations as weighted typed edges. Queries don't retrieve documents; they propagate activation through the network and return a constellation of relevant nodes and connections. The model reads the constellation, not a pile of text chunks.

This is different from RAG. RAG retrieves documents and hands them to a model. The Chronik returns *structured relationships* — and the long-term direction is to inject those directly into a model's attention mechanism, bypassing text entirely.

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

## The core bet

Current AI systems are built so that knowledge and reasoning live in the same place — the model weights. That conflates two very different things. Reasoning is a process. Knowledge is a substrate. Separating them makes both better: you can update knowledge without retraining, inspect it, correct it, cite it, and share it across models.

The Chronik is that substrate. It grows by reading. It heals itself through an immune system of background agents. It never pre-validates — it ingests fast and corrects post-hoc. And it is designed so that, eventually, AI agents can communicate by exchanging activation fields rather than text — the knowledge network becomes the shared language.

This is early. The bets haven't been proven yet. The two open questions:

1. Does cognitive synthesis (Nous) produce a denser, more useful Chronik than chunked extraction? (We believe yes — but it needs to be shown.)
2. Does Spreading Activation over a dense vector-graph retrieve better than ANN search + graph traversal? (We believe yes at high edge density — but it needs to be shown.)

These are the experiments we build toward.

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

| Document | What it covers |
|---|---|
| [ROADMAP.md](ROADMAP.md) | The five-phase development sequence |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design — layers, data model, retrieval |
| [docs/DEEP_TECH_VISION.md](docs/DEEP_TECH_VISION.md) | The deeper substrate direction |
| [notes/architecture/vector_native_spreading_activation.md](notes/architecture/vector_native_spreading_activation.md) | Tensor-Manifold and Spreading Activation design |
| [notes/architecture/reading_agent_vision.md](notes/architecture/reading_agent_vision.md) | Nous — the cognitive reading model |
| [docs/CHRONICLE_PRINCIPLES.md](docs/CHRONICLE_PRINCIPLES.md) | Nine non-negotiable design principles |
| [docs/BUILD_DOCTRINE.md](docs/BUILD_DOCTRINE.md) | Why we ingest fast and heal post-hoc |
| [docs/INDEX.md](docs/INDEX.md) | Full document map and reading paths |
| [AGENTS.md](AGENTS.md) | If you are an AI agent contributing to this repo |

---

## Contributing

The project is open source (Apache 2.0). Contributions are welcome.

If you want to contribute code, read [AGENTS.md](AGENTS.md) — it applies equally to humans and AI coding agents. The short version: schema-first, honest failure reports, no silent scope creep, one PR per coherent change.

If you want to contribute ideas, open an issue or start a discussion. The most useful thing right now is feedback on the two core bets above.

---

## Why "Theogony"

Hesiod's *Theogony* is the Greek poem that describes the birth of the gods — the emergence of order from chaos, the genealogy of divine knowledge. The name fits: this project tries to build the knowledge substrate that makes AI systems trustworthy, inspectable, and genuinely useful — the infrastructure beneath the intelligence, not the intelligence itself.
