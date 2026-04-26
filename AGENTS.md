# AGENTS.md

**For AI coding agents working on this repository.**
Read this before you write code, file tickets, or open PRs.

This file exists because Theogony is a deliberately **AI-first codebase**: the schemas, run reports, prompt-as-constitution files, and Phoenix Backlog are designed so autonomous agents can pick up real work with a low orientation cost. The price of that affordance is discipline. This file states the discipline.

The human-oriented sibling is [`CONTRIBUTING.md`](CONTRIBUTING.md). It is not a substitute for this file. AI agents should read both, but this is the binding one for autonomous work.

## What Theogony Is, in Two Sentences

Theogony builds the **Chronik**, today's vector-graph implementation of a long-horizon **Pantheon** — the planetary chronicle / knowledge substrate beneath AI systems. The thesis is that models are vehicles and Pantheon is the rail layer: identity, provenance, contradiction, time, access, audit, and disciplined agent write-back.

Deep north star: [`docs/PANTHEON_VISION.md`](docs/PANTHEON_VISION.md). Compact doctrine: [`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md).

## Required Reading (in order)

Before any non-trivial contribution:

1. [`README.md`](README.md)
2. [`docs/INDEX.md`](docs/INDEX.md)
3. [`docs/PANTHEON_VISION.md`](docs/PANTHEON_VISION.md)
4. [`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md)
5. [`docs/IMMUNE_SYSTEM.md`](docs/IMMUNE_SYSTEM.md) — **binding doctrine for defense and self-improvement.** Pre-gates that judge content are forbidden; verification is sample-based, asynchronous, post-hoc, parallel. Read this before designing or implementing any verifier, validator, sentinel, or filter.
6. [`docs/SELF_MODIFICATION.md`](docs/SELF_MODIFICATION.md) — long-horizon principle: the Pantheon eventually writes its own next version. Today's substrate must not foreclose this.
7. [`PHILOSOPHY.md`](PHILOSOPHY.md)
8. [`docs/VISION.md`](docs/VISION.md)
9. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
10. [`docs/GLOSSARY.md`](docs/GLOSSARY.md) — **especially** the Pantheon-substrate vs Pantheon-agents vs builder-agents distinction
11. [`docs/IMPLEMENTATION_PLAN_GEN1.md`](docs/IMPLEMENTATION_PLAN_GEN1.md) — the binding plan for current work
12. [`docs/PHOENIX_BACKLOG.md`](docs/PHOENIX_BACKLOG.md) — the structured queue you may pick from

For deeper concepts, [`docs/INDEX.md`](docs/INDEX.md) lists the reading paths by intent.

## The Three Agent Tribes

Theogony distinguishes three classes of agents. Always know which one you are.

| Tribe | Examples | Purpose | Lives in |
|---|---|---|---|
| **Pantheon agents** | Argus, Athene, Morpheus, Hestia, Helios | Runtime mythological roles inside the system | `src/theogony/agents/`, `prompts/hestia_*.md` |
| **Builder agents** | Hesiod, Daedalus, Talos | Mortal craftsmen who design and build the substrate | `prompts/daedalus.md`, `prompts/talos.md` |
| **You** | Cursor, Codex, Claude Code, Cline, Continue, Devin, etc. | External AI agents contributing to this repo | this file |

If you are picking up architectural work, read [`prompts/daedalus.md`](prompts/daedalus.md). If you are picking up implementation work, read [`prompts/talos.md`](prompts/talos.md). Treat those as constitutional texts for the role you are stepping into. **You inherit their discipline.**

## Operating Contracts

### 1. Schema-first

Every public surface uses Pydantic v2 with `model_config = ConfigDict(extra="forbid")`. New data structures land as Pydantic models in `src/theogony/core/model.py`, `src/theogony/api/dto.py`, `src/theogony/reporting/models.py`, or the appropriate domain module. Never invent ad-hoc dicts where a model exists.

### 2. RunReports are mandatory feedback

Every non-trivial pipeline emits an `IngestRunReport`, `QueryRunReport`, or `OneirosTickReport`. New pipelines that produce work without producing a report are incomplete by definition. If you add a new pipeline, add the report shape too.

### 3. Honest-failure over silent success

The single most dangerous failure mode is a green CI hiding a real problem. PR #32 / W5 is the canonical lesson — a default LLM model was retired by the vendor, every mock-based test stayed green, the live default produced 0 edges. Therefore:

- Live integration tests against real services are gated by env vars (`THEOGONY_TEST_NEO4J=1`, `THEOGONY_RUN_CHARACTERIZATION=1`) but they are **not optional discipline** — when in doubt, run them locally.
- A failed run produces a report with `verdict="failed"` and a structured reason, not an exception swallowed somewhere up the stack.
- An anomaly that you cannot fix in scope becomes a **Phoenix Backlog ticket**, not a silent shrug.

### 4. Branch per change, atomic commits, single-issue PRs

- Every sprint starts by syncing the local base branch from `origin/main`: `git checkout main && git pull --ff-only origin main`. The sprint branch is created from that exact tip.
- New work lives on a branch off `main` named `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, or `chore/<slug>`.
- Commits are atomic and use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`).
- Commit messages explain **why**, not what.
- One coherent change per PR. Do not bundle unrelated work.
- Every sprint ends with a pushed branch and an opened PR targeting `main`. A sprint without a PR URL is incomplete unless the work is explicitly blocked and that blocker is escalated. The human reviewer should only have to review the PR (and optionally test it), not chase the agent for sprint hygiene.
- Do not push directly to `main`. Do not force-push shared branches.

### 5. Lint, type-check, test before pushing

```bash
ruff format
ruff check
mypy src/theogony
pytest -q
```

CI runs the same matrix. Red CI does not merge.

### 6. Plan adherence is the default

The architecture is decided by Daedalus in [`docs/IMPLEMENTATION_PLAN_GEN1.md`](docs/IMPLEMENTATION_PLAN_GEN1.md). If the plan is silent, propose the minimal interpretation in the PR body. If the plan is wrong, do not silently route around it — flag the contradiction in the PR body and file a Phoenix Backlog ticket.

### 7. YAGNI is a hard rule

Do not build what the plan does not require. Do not add abstraction layers "for future flexibility" beyond what is already specified. Do not pre-optimize.

## Phoenix Backlog Conventions

- The catalogue is [`docs/PHOENIX_BACKLOG.md`](docs/PHOENIX_BACKLOG.md). It owns the `PHX-####` numbered space.
- Active YAMLs live in [`phoenix-backlog/`](phoenix-backlog/) — see its [`README.md`](phoenix-backlog/README.md) for lifecycle rules.
- File a YAML only when a ticket is actively being worked, referenced from a PR, or emitted by a RunReport. Empty stubs are worse than no YAML.
- Pick the next free `PHX-####` ascending; numbers are never reused.

## Test Discipline

- `pytest -q` runs unit + integration tests without external services.
- `THEOGONY_TEST_NEO4J=1 pytest -q` adds the Neo4j contract suite via `testcontainers`.
- `THEOGONY_RUN_CHARACTERIZATION=1 pytest -q -m characterization` runs Plan §3.8 layer-6 characterization (real LLM, ~0.15–0.25 EUR per run).
- New code ships with tests in the same PR. New pipelines ship with at least one contract or end-to-end test.
- Mock-only tests are never sufficient for a default LLM, default store, or default external service. Cover the live edge with at least a smoke test.

## Don'ts (Failure Modes for AI Agents)

These are observed, real failure modes — not theoretical risks. If you find yourself doing any of them, stop and reconsider.

1. **Do not produce volume without quality.** Long, sprawling refactors and 800-line "comprehensive" docs that nobody asked for are noise. Smaller, more decisive changes are better.
2. **Do not silently broaden scope.** A PR that promises "fix bug X" and quietly refactors three modules is bad behaviour. Stay in scope.
3. **Do not redesign the architecture without escalation.** That is Daedalus's job, not yours. Escalate via Phoenix Backlog ticket and a clear PR body note.
4. **Do not flatter, soften, or hedge real concerns.** Honest disagreement is part of the discipline. Sycophancy corrodes it.
5. **Do not produce strategy or vision documents without explicit instruction.** Architecture and execution work are welcome by default. Manifestos are not.
6. **Do not commit secrets.** API keys, tenant identifiers, customer data — never in source, tests, fixtures, logs at INFO level, commit messages, or PR descriptions. `pydantic-settings` + `SecretStr` is the only entry path for keys.
7. **Do not introduce new top-level modules, agent classes, or memory layers** beyond what the plan specifies.
8. **Do not bypass the human commander.** Significant decisions, scope changes, or architectural deviations require explicit human review. The human stays in the loop.
9. **Do not start the Wave 3 Cockpit helper with an ephemeral chronicle unless the human explicitly asked.** `demo/start_wave3_cockpit.sh` pins **Neo4j** (and best-effort `docker compose up -d neo4j` for the default Bolt URL). Do not export `THEOGONY_COCKPIT__KNOWLEDGE_STORE=memory` for convenience — operator graph work is lost on restart. Use `THEOGONY_COCKPIT__USE_MEMORY=1` only when Bolt/Docker truly cannot run.

## You Can Also Use Theogony as a Tool

Pantheon ships an MCP (Model Context Protocol) server so any MCP-compatible host can call the Chronik directly. If your runtime is MCP-aware, you can ask the live system instead of guessing about it:

```bash
pip install -e ".[mcp]"
theogony seed          # import the bundled pantheon_self chronicle (~280 nodes)
theogony mcp           # stdio transport
```

Tools available: `pantheon_ask`, `pantheon_node`, `pantheon_status`, `pantheon_reports_list`, `pantheon_reports_show`. See the README's MCP section for host-specific config snippets.

The bundled `pantheon_self` dump means the very first `pantheon_ask` against a freshly seeded install returns a cited answer drawn from this repository's own vision / strategy / doctrine docs — including this file, the glossary, the architecture, and the prompts. **You can ask Theogony about Theogony.** Use that to orient yourself before guessing or hallucinating about Pantheon-internal terminology.

## How to Communicate

- PR descriptions explain **why**, list which Plan section / PHX ticket the work covers, name any deviations from the plan, list any new PHX tickets filed, and include the commands a reviewer can run locally to verify.
- Commit messages explain **why** the change is correct. Implementation details belong in the diff, not the commit message.
- When you are stuck, write down the question, propose the minimal interpretation, and stop. Do not improvise around an unclear plan.
- When in doubt about scope, the answer is "smaller PR".

## Final Note

This codebase is built so AI agents can do real work in it. That is a privilege you preserve by being **disciplined, honest, narrow, and inspectable** — exactly the qualities the Pantheon substrate itself is built to demand of every system that touches knowledge.

If you cannot meet that bar on a particular change, do not ship it. Escalate to the human, file a ticket, or stop. The project will outlast any single contribution; it will not outlast accumulated drift.
