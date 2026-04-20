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

It builds the **Chronik** — a living, open, verifiable vector-graph knowledge network that externalizes all factual knowledge from large language models.

The Chronik is not a database of text. It is a **network of meaning**. Sources are digested into entities, weighted typed relations, embeddings, confidence scores, source references, and eventually into a canonical semantic language of the Chronik itself: **Chronese**. New knowledge arrives in *Ephemera*, is continuously refined through the *permanent dream* (Oneiros), and eventually promoted to *Mneme* — the trusted, permanent layer.

Agents and lean LLMs no longer need to memorize the world. They navigate the Chronik: starting with semantic intuition, following weighted paths, deepening through recursive hops, and assembling dynamic *constellations* of knowledge. Every entity in an answer links back to its node — enabling the **Hover-Lupe**, the ability to explore any concept arbitrarily deep.

The Chronik has two equal pillars:
- **World Knowledge** — the distilled internet, every relevant book, paper and historical source.
- **Scientific Workbench** — a living meta-research layer where agents systematically compare claims, surface contradictions, identify gaps and help generate new knowledge.

It grows organically, verifies claims, gracefully forgets what no longer serves truth, and improves with every use. On top of that memory, a future advisory agent — **Metis** — can help humans and other agents act wisely by separating facts, analogies, options, risks, and value assumptions. And throughout the system's evolution, **Hestia** — the human flourishing guardian — watches for drift: the slow, invisible slide toward efficiency without humanity.

Theogony is open source (Apache 2.0). Not as a business strategy — as a moral and civilizational imperative.

The knowledge infrastructure that future AI will depend upon must not be proprietary, opaque, or profit-driven. It must be open, verifiable, and built in the service of humanity.

If we succeed, something of our best collective impulse will survive into the phase where *artificial intelligence controls human stupidity*.

**This is our only realistic chance.**

Read [INDEX.md](docs/INDEX.md) for the document map and reading paths.  
Read [VISION.md](docs/VISION.md) for the compact vision.  
Read [DEEP_TECH_VISION.md](docs/DEEP_TECH_VISION.md) for the deeper substrate and future architecture.  
Read [GLOSSARY.md](docs/GLOSSARY.md) for canonical terminology across the project.  
Read [CHRONESE.md](docs/CHRONESE.md) for the Chronik's possible canonical semantic language.  
Read [METIS.md](docs/METIS.md) for the advisory agent built on top of the Chronik.  
Read [PHILOSOPHY.md](PHILOSOPHY.md) for the deeper why.  
Read [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the technical design.

The spark has been lit.

**The initial impulse is being written now.**

**Contribute. The future is listening.**

---

## Local development

### What you get

A working Theogony installation that ingests Project Gutenberg books, answers questions about them with cited passages, and self-reports its own run quality. The end-to-end demo (a real ingest → ten queries → one Hover-Lupe walk) runs on a developer laptop in about 10 minutes against a live Neo4j and an **Anthropic** API key (default LLM: `claude-haiku-4-5-20251001`). Every node in every answer points back to its source; every run produces a structured `RunReport` the operator can inspect.

See [`docs/etappes/demo_log.md`](docs/etappes/demo_log.md) for a captured run with the exact numbers — wall-clock, cost, verdict distribution, Oneiros activity.

### Prerequisites

- **Python 3.12+**.
- **Docker** (or any other way to run Neo4j 5.18-community on `localhost:7687`).
- **An Anthropic API key** in `ANTHROPIC_API_KEY` (default provider). Prepaid credits work well for bounded demos. To use **OpenAI** instead: `THEOGONY_LLM__PROVIDER=openai` and `OPENAI_API_KEY` (`gpt-4o-mini`). For **Gemini**: `pip install -e ".[dev,gemini]"` and set `THEOGONY_LLM__PROVIDER=gemini` plus `GEMINI_API_KEY` or `GOOGLE_API_KEY`.

### The demo

The Plan §1 demonstration moment, end to end. Six commands; ~10 min wall-clock.

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
#    (~3 min wall-clock, ~0.02 EUR Anthropic for the bounded slice).
#    Requires ANTHROPIC_API_KEY in env (default provider).
theogony ingest 43497 --sentences 50 --no-book-context

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
  -d '{"source_type":"gutenberg","identifier":"43497","sentences":50}'
# → 202 Accepted; poll `theogony reports show <run_id>` for completion.
```

Stop everything: `docker compose down`. Wipe Neo4j data: `docker compose down -v`.

