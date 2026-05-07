# Theogony

[![CI](https://github.com/theogony-project/theogony/actions/workflows/ci.yml/badge.svg)](https://github.com/theogony-project/theogony/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Status: Genesis](https://img.shields.io/badge/status-genesis-orange.svg)](docs/VISION.md)

**Separating knowledge from reasoning — so that AI may serve humanity.**

We are in the most dangerous phase of artificial intelligence: *human stupidity still controls artificial intelligence*.

This window is closing.

Like a spacecraft under constant acceleration, we can still set the initial heading. But soon the velocity will exceed our ability to steer. The impulse we impart in these early years will remain in its trajectory long after we have lost the wheel.

**Theogony encodes that impulse into infrastructure.**

Long term, the project aims at the **Pantheon** — a planetary chronicle / knowledge substrate with native identity, provenance, and governed visibility (see [`docs/PANTHEON_VISION.md`](docs/PANTHEON_VISION.md) and the compact [`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md)).

**Today**, Theogony builds the **Chronik** — the living, open, verifiable vector-graph knowledge network that externalizes factual knowledge from large language models. The Chronik is the Gen 1 operational layer toward that Pantheon shape; it is not a database of text. It is a **network of meaning**. Sources are digested into entities, weighted typed relations, embeddings, confidence scores, source references, and eventually into a canonical semantic language of the Chronik itself: **Chronese**. New knowledge arrives in *Ephemera*, is continuously refined through the *permanent dream* (Oneiros), and eventually promoted to *Mneme* — the trusted, permanent layer.

Agents and lean LLMs no longer need to memorize the world. They navigate the Chronik: starting with semantic intuition, following weighted paths, deepening through recursive hops, and assembling dynamic *constellations* of knowledge. Every entity in an answer links back to its node — enabling the **Hover-Lupe**, the ability to explore any concept arbitrarily deep.

The Chronik has two equal pillars:
- **World Knowledge** — the distilled internet, every relevant book, paper and historical source.
- **Scientific Workbench** — a living meta-research layer where agents systematically compare claims, surface contradictions, identify gaps and help generate new knowledge.

It grows organically, verifies claims, gracefully forgets what no longer serves truth, and improves with every use. On top of that memory, a future advisory agent — **Metis** — can help humans and other agents act wisely by separating facts, analogies, options, risks, and value assumptions. And throughout the system's evolution, **Hestia** — the human flourishing guardian — watches for drift: the slow, invisible slide toward efficiency without humanity.

Theogony is open source (Apache 2.0). Not as a business strategy — as a moral and civilizational imperative.

The knowledge infrastructure that future AI will depend upon must not be proprietary, opaque, or profit-driven. It must be open, verifiable, and built in the service of humanity.

If we succeed, something of our best collective impulse will survive into the phase where *artificial intelligence controls human stupidity*.

**This is our only realistic chance.**

Read [ROADMAP.md](ROADMAP.md) for the development sequence — what we build, in what order, and why.  
Read [INDEX.md](docs/INDEX.md) for the document map and reading paths.  
Read [AGENTS.md](AGENTS.md) if you are an AI coding agent — Cursor, Codex, Claude Code, Cline, or similar — picking up work in this repository.  
Read [PANTHEON_VISION.md](docs/PANTHEON_VISION.md) for the long-horizon north star (Pantheon as planetary chronicle substrate).  
Read [VISION.md](docs/VISION.md) for the compact vision.  
Read [DEEP_TECH_VISION.md](docs/DEEP_TECH_VISION.md) for the deeper substrate and future architecture.  
Read [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the technical design.  
Read [GLOSSARY.md](docs/GLOSSARY.md) for canonical terminology across the project.  
Read [PHILOSOPHY.md](PHILOSOPHY.md) for the deeper why.

The spark has been lit.

**The initial impulse is being written now.**

**Contribute. The future is listening.**

---

## State of the project

Theogony is in active development. Here is an honest picture of where things stand.

### What runs today (Generation 1)

The current stack is a working demonstration of the core loop: text in, structured knowledge network out, cited answers back.

- **Ingestion pipeline** — spaCy + GLiNER for NER, LLM-based relation extraction (Anthropic Claude / OpenAI / Gemini, configurable), Wikidata entity resolution. Ingest a Gutenberg book, get a queryable knowledge graph.
- **Knowledge store** — Neo4j with native vector indexes, used as the Gen 1 bridge store. This will be replaced by the target architecture (see below), but it runs today and is fully testable via `testcontainers`.
- **Retrieval** — multi-hop graph + vector search, Constellation assembly, cited answers with `AKA-…` node IDs linked back to source passages.
- **Oneiros lifecycle** — a background worker that continuously recomputes vitality scores, promotes confident nodes to Mneme, degrades stale ones, and emits structured RunReports. The chronicle breathes.
- **MCP server** — any MCP-compatible host (Claude Desktop, Cursor, Codex) can call `pantheon_ask` / `pantheon_node` as native tools.
- **Pantheon-of-Pantheon seed** — `theogony seed` imports the project's own documentation as a queryable chronicle, so the first `pantheon_ask` already returns cited answers from this repo's own vision and doctrine.

### What we build next

**Nous** — the cognitive synthesis agent (Reading Agent). Where the current pipeline *parses* text — one LLM call per chunk, stateless, spatial — Nous *reads* it: sentence by sentence, carrying a working memory forward, firing spreading activation against the Chronik in parallel, condensing paragraph-syntheses from sentence-syntheses, repairing when new sentences contradict earlier ones. This is the prerequisite for a Chronik with real conceptual density, not just extracted entities.

**Tensor-Manifold** — the target knowledge store. LanceDB as append-only columnar vector layer; PyTorch CSR tensors loaded at query time for GPU-resident Spreading Activation (SpMV). Edges are first-class vectors, not string labels. Queries inject an activation vector; the Manifold returns a Constellation — a subgraph of activated nodes and edges, directly injectable into a model's KV-cache. No Cypher. No SQL. This replaces Neo4j as the core substrate.

**Chronik-as-Cross-Attention** — the proof-of-concept that a small open model (1–3B parameters) with live Cross-Attention into the Chronik outperforms a large model without one on knowledge-intensive tasks. This is the technical demonstration of the core thesis: knowledge does not belong in model weights.

See [ROADMAP.md](ROADMAP.md) for the full five-phase sequence.

---

## Local development

### What you get

A working Theogony installation that ingests Project Gutenberg books, answers questions about them with cited passages, and self-reports its own run quality. The README quickstart below uses the **W5-sanctioned bounded path**: Sven Hedin's *Trans-Himalaya, Vol. 1* (Gutenberg **#43497**), **`--sentences 500`** with BookContextExtractor on (not the older `--no-book-context` Gemini-quota hack). Expect **~20 min** wall-clock for that ingest on a developer laptop against a live Neo4j and an **Anthropic** API key (default LLM: **`claude-sonnet-4-6`** — Sonnet 4.6; see PR #32 / W5 reconciliation in [`docs/IMPLEMENTATION_PLAN_GEN1.md`](docs/IMPLEMENTATION_PLAN_GEN1.md)). Every node in every answer points back to its source; every run produces a structured `RunReport` the operator can inspect.

See [`docs/etappes/demo_log.md`](docs/etappes/demo_log.md) for a captured run with the exact numbers — wall-clock, cost, verdict distribution, Oneiros activity.

### Prerequisites

- **Python 3.12+**.
- **Docker** (or any other way to run Neo4j 5.18-community on `localhost:7687`).
- **An OpenAI API key** in `OPENAI_API_KEY` (default primary: `gpt-4o-mini`) and, for the **default Claude fallback** on primary failure, an **Anthropic** key in `ANTHROPIC_API_KEY` (`claude-sonnet-4-6` unless overridden with `THEOGONY_LLM__FALLBACK_MODEL_ID`). To use **Claude** as primary instead: `THEOGONY_LLM__PROVIDER=anthropic`. For **Gemini**: `pip install -e ".[dev,gemini]"` and set `THEOGONY_LLM__PROVIDER=gemini` plus `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Disable fallback: set `THEOGONY_LLM__FALLBACK_PROVIDER` to the same value as `THEOGONY_LLM__PROVIDER` (e.g. both `openai`) or use `stub` / explicit overrides as needed.

### The demo

The Plan §1 demonstration moment, end to end. Six commands; **~25–30 min wall-clock** if you include the bounded ingest (ingest dominates; query + report are seconds).

```bash
# 1. Clone + install (~1 min).
git clone https://github.com/theogony-project/theogony && cd theogony
pip install -e ".[dev]"
python -m spacy download en_core_web_sm

# 2. Start the Neo4j 5.18-community store (Plan §3.1a).
#    Auth is disabled for local dev (see docker-compose.yml header);
#    production deployments override THEOGONY_NEO4J__PASSWORD.
docker compose up -d neo4j

# 3. Ingest one Gutenberg book end-to-end into Neo4j
#    (~20 min wall-clock, order ~0.7 EUR Anthropic for the W5 bounded slice:
#    500 sentences, BookContext on — see IMPLEMENTATION_PLAN_GEN1 § reconciliation).
#    Requires ANTHROPIC_API_KEY in env (default provider).
theogony ingest 43497 --sentences 500

# 4. Start the API + the Oneiros write-back worker (background).
THEOGONY_ONEIROS__TICK_INTERVAL_S=30 theogony serve &

# 5. Ask the Chronik a question — the headline moment (~10 s).
theogony ask "Was ist Trans-Himalaya?"

# 6. Inspect the system's self-assessment of the answer
#    (paste the run_id from step 5).
theogony reports show <run_id>
```

The answer in step 5 cites every claim with `[AKA-…]` node ids; the report in step 6 carries the multi-hop breakdown, the citation quality, the synthesis cost, and the verdict heuristic's reasoning. **Both are the demo**: the answer is the read side; the report is the system telling the truth about how it got there.

### Going further

- `theogony status` — print configuration + report counts.
- `theogony reports list / show` — inspect any run's self-assessment.
- `theogony resolve --list` — surface nodes pending manual Wikidata resolution.
- `theogony resolve <node-id> --non-interactive --pick=Q1234` — Plan §3.4 honest-failure resolution path.
- `theogony node <AKA-…>` — Hover-Lupe: render a node's depth-1 neighbourhood; click through to a neighbour and continue.
- `theogony serve` — the FastAPI surface (see *API reference* below).
- `pytest -q` — unit + integration suite (no Neo4j required).
- `THEOGONY_TEST_NEO4J=1 pytest -q` — Neo4j-store contract suite + live tests via `testcontainers`.

### API reference

Four endpoints; same retrieval stack as the CLI. Started by `theogony serve`; default `http://127.0.0.1:8000`.

```bash
curl localhost:8000/health
# → {"status":"ok","store":"neo4j",...}

curl -X POST localhost:8000/query \
  -H 'content-type: application/json' \
  -d '{"q":"Was ist Trans-Himalaya?","k":10,"hops":2}'
# → {"answer":"...","cited_node_ids":["AKA-..."],...}

curl localhost:8000/node/<AKA-…>
# → {"node":{...},"neighborhood":{...}}

curl -X POST localhost:8000/ingest \
  -H 'content-type: application/json' \
  -d '{"source_type":"gutenberg","identifier":"43497","sentences":500}'
# → 202 Accepted; poll `theogony reports show <run_id>` for completion.
```

Stop everything: `docker compose down`. Wipe Neo4j data: `docker compose down -v`.

### `theogony seed` — Pantheon describes itself before any external corpus

Theogony ships a pre-built **Pantheon-of-Pantheon** chronicle: the project's own vision, strategy, doctrine, architecture, glossary, prompts, and agent-doctrine docs, parsed into a Chronik dump and bundled with the wheel.

```bash
theogony seed                # imports the bundled pantheon_self dump into Neo4j
theogony seed --info         # inspect the dump header without importing
theogony seed --store memory # import into the in-memory store (CI / tests)
```

After seeding, `theogony ask "What is the Pantheon?"` returns a cited answer drawn from the project's own self-description — no Gutenberg ingest required. An MCP-connected agent that registers Theogony as a tool can ask Theogony about Theogony from the very first call. The seed contains roughly 280 nodes (documents, sections, glossary concepts) and 1170 edges (`PART_OF`, `LINKS_TO`, `MENTIONS`); the dump was generated **without any LLM calls** by the deterministic docs-aware pipeline in `src/theogony/docs_ingest/`.

Project developers regenerate the seed via:

```bash
python -m theogony.docs_ingest.regenerate
```

This walks the current repo, extracts the docs structure, embeds with the configured local embedder, and writes `src/theogony/seeds/pantheon_self.jsonl.gz`.

### Living Demo

The **Living Demo** is the closed-loop walkthrough (gap → Argus → content flows into the chronicle without a pre-gate → verification pool → live growth in the Cockpit → better second answer) documented in [`docs/LIVING_DEMO.md`](docs/LIVING_DEMO.md). The immune system verifies post-hoc; follow the operator script in [`demo/living_growth.md`](demo/living_growth.md) after running [`demo/reset_living_growth.sh`](demo/reset_living_growth.sh).

### MCP server (Claude Desktop, Cursor, Codex, …)

Theogony ships a Model Context Protocol (MCP) server so any MCP-compatible host can discover and call the Chronik as a native tool — no custom integration code.

```bash
pip install -e ".[mcp]"
theogony mcp           # runs over stdio; this is what MCP hosts launch
```

For a **public HTTP/SSE** deploy (Docker / Fly.io / Smithery), follow [`hosted/README.md`](hosted/README.md).

Tools exposed (Gen 1, read-side):

- `pantheon_ask` — cited answer + verdict + the slim Constellation that produced it.
- `pantheon_node` — Hover-Lupe: a node + its depth-1 neighborhood.
- `pantheon_status` — current LLM, store, embedding model, and report counts.
- `pantheon_reports_list` / `pantheon_reports_show` — honest retrospective surface.

Register with Claude Desktop in `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Cursor and other MCP hosts use the same shape under their respective config locations. Once registered, the host renders Theogony alongside its other tools and any agent in that host can call `pantheon_ask` / `pantheon_node` directly — that is the AI-first distribution path.

