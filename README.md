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

```bash
# 1. Set up Python (3.12+).
pip install -e ".[dev,gemini]"
python -m spacy download en_core_web_sm

# 2. Start the Neo4j 5.18-community store backend (Plan §3.1a).
#    Auth is disabled for local dev (see docker-compose.yml header);
#    production deployments override THEOGONY_NEO4J__PASSWORD.
docker compose up -d neo4j

# 3. Verify the toolchain.
theogony status                           # config + report counts
pytest -q                                 # unit + integration suite (no Neo4j)

# 4. Run the Neo4j-store contract suite + live tests.
THEOGONY_TEST_NEO4J=1 pytest \
  tests/test_store_contract.py \
  tests/test_neo4j_store_live.py \
  tests/test_retrieval_pipeline_neo4j_live.py -v

# 5. Ingest one Project Gutenberg book end-to-end into Neo4j
#    (~1-3 min, ~0.1 EUR Gemini). Requires GEMINI_API_KEY or
#    GOOGLE_API_KEY in env.
theogony ingest 43497 --sentences 50 --relations 10
theogony reports show <run_id>

# 6. Ask the Chronik a question (E9):
theogony ask "Wer war Sven Hedin?"

# 7. Hover-Lupe one shot (E9):
theogony node AKA-3432a578cfb0

# 8. Manual-resolution surface (E9, Plan §3.4):
theogony resolve --list
theogony resolve <node-id> --non-interactive --pick=Q1234

# 9. FastAPI surface (E9):
theogony serve                            # http://127.0.0.1:8000
curl localhost:8000/health
curl -X POST localhost:8000/query -H 'content-type: application/json' \
  -d '{"q": "Wer war Sven Hedin?"}'
```

Stop everything: `docker compose down`. Wipe Neo4j data: `docker compose down -v`.

