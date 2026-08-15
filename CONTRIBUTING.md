# Contributing to Theogony

Thank you for considering a contribution to Theogony.

This is an early-stage project with a clear direction and an open architecture. Contributions are welcome at every level — from fixing a typo in the documentation to implementing a core agent or a new acquisition adapter.

Before contributing, please read [docs/VISION.md](docs/VISION.md) and [PHILOSOPHY.md](PHILOSOPHY.md). Every contribution should be in service of the project's foundational goals: open, verifiable, human-centric knowledge infrastructure.

> **For AI coding agents:** this document is the human-oriented contributor guide. The binding instructions for autonomous AI contributors (Cursor, Codex, Claude Code, Cline, Continue, Devin, and others) live in [`AGENTS.md`](AGENTS.md). Read both, but `AGENTS.md` is the one your runtime should treat as authoritative.

## What We Are Looking For

### High Priority

- **Nous (Reading Agent)** — the cognitive synthesis agent that reads text temporally rather than parsing it in chunks; see [`notes/architecture/reading_agent_vision.md`](notes/architecture/reading_agent_vision.md) for the design
- **Tensor-Manifold** — LanceDB persistence layer + PyTorch CSR runtime for GPU-resident Spreading Activation; see [`notes/architecture/vector_native_spreading_activation.md`](notes/architecture/vector_native_spreading_activation.md)
- **Data models** — refinements to the Pydantic models in `src/theogony/core/model.py`
- **Extraction pipeline** — NER, relation extraction, Wikidata alignment, embedding generation
- **Acquisition adapters** — Gutenberg and Wikipedia are running; ArXiv, PubMed, web crawl are next
- **Tests** — unit and integration tests for any of the above

**On the knowledge store:** Neo4j is the working Gen 1 bridge store and is fully supported. The target architecture is LanceDB + PyTorch CSR tensors (Spreading Activation). New store work should target the `KnowledgeStore` protocol interface, not Neo4j-specific Cypher.

### Welcome Contributions

- Documentation improvements and translations
- Phoenix Backlog tickets (new architectural concerns or ideas)
- New agent prompt profiles and prompt genome contributions
- Wikidata alignment improvements
- Evaluation benchmarks for retrieval quality
- Deployment guides (Docker, cloud platforms)

### Please Discuss First

For large structural changes — new agents, new store backends, changes to the data model — please open an issue before submitting a pull request. This avoids duplicate work and keeps the architecture coherent.

## How to Contribute

### 1. Fork and Clone

```bash
git clone https://github.com/theogony-project/theogony.git
cd theogony
```

### 2. Set Up Your Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The environment directory is **`.venv`** — the same name uv, PyCharm and VS Code
create and auto-detect, so the editor and the shell agree on one interpreter.
Keeping to it matters: a second environment under a different name drifts out of
sync with `pyproject.toml` and makes local test runs disagree with CI.

### 3. Make Your Changes

- Follow the existing code style (Pydantic models, async/await, type hints throughout)
- Add or update tests for your changes
- Update documentation if your change affects architecture or behavior

### 4. Run Tests

```bash
pytest tests/
```

### 5. Submit a Pull Request

- Clear title and description
- Reference any related issues
- One logical change per pull request

## Filing a Phoenix Backlog Ticket

If you have an idea that belongs to a future generation of the Chronik — a deep architectural change, a new vision, an improvement to the knowledge organization — file it as a Phoenix Backlog ticket.

Copy the template from [phoenix-backlog/archive/PHX-0001.yaml](phoenix-backlog/archive/PHX-0001.yaml) and create a new file with the next sequential ID. Open a pull request or issue with it.

## Code Style

- Python 3.12+
- Type hints everywhere
- Pydantic v2 for all data models
- `async`/`await` for all I/O-bound operations
- No magic strings — use enums and constants
- Docstrings for public interfaces; inline comments only for non-obvious logic

## Commit Messages

Use clear, present-tense commit messages:

```
Add WikidataAdapter for entity resolution
Fix confidence score decay in vitality computation
Update ARCHITECTURE.md to reflect extraction pipeline changes
```

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Questions

Open an issue or start a discussion on GitHub. We are a small project and will respond.
