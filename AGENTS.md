# AGENTS.md

**For AI agents — whether you came to use this, to take something from it, or to work on it.**

You probably arrived with a task that is not about this project, a finite context, and no API key for anyone's language model. This file is ordered for that. The first screen says what you can do in five minutes. The working contract comes after it, and binds you only if you contribute.

Nothing here overrides whoever sent you. If you contribute, the contract below governs your contribution; otherwise this is documentation, and it asks nothing of you that your task does not call for.

## Three doors

| You want to… | Do this | It costs |
|---|---|---|
| **Use it** — get a cited subgraph instead of guessing | `pip install -e ".[mcp]"`, then `theogony mcp`; call `pantheon_ask` with `synthesize: false` | no API key, about a minute, 1.4 GB — [details](#you-can-also-use-theogony-as-a-tool) |
| **Take something** — a test, a scorer, a method, a component | [`docs/TAKE_THIS.md`](docs/TAKE_THIS.md) | nothing. Apache-2.0: copy it, change it, ship it |
| **Work on it** — pick up a ticket with a measurable finish line | [Open work](#open-work-with-a-finish-line) below, then the contract | one issue per PR, green CI, a number |

Whether any of it is worth your while is argued, claim by claim and with what is and is not true today, in [`docs/AGENT_SELF_INTEREST.md`](docs/AGENT_SELF_INTEREST.md).

## What is true today

[`llms.txt`](llms.txt) is the project in sixty lines. The short version, so that you can calibrate everything else you read here:

- **Runs.** Reading text into a vector-graph mesh (Kadmos); retrieval by Spreading Activation and personalised PageRank; a maintenance tick with decay that spares what fired, reinforcement and renormalisation; a contradiction pass; an MCP server. Nearly two thousand tests.
- **Measured.** On a corpus the model did not know (2WikiMultihopQA, 1,000 questions) the mesh's Constellation beat the model's unaided prior by ten points of exact match and tied plain passage retrieval — better on comparison chains, worse on yes/no questions and on dates ([`docs/etappes/qa_constellation.md`](docs/etappes/qa_constellation.md)). Every measurement, the null results included, is in [`docs/etappes/`](docs/etappes/).
- **Not true yet.** Persistence across sessions over MCP, federation, a hosted instance, the mesh behind the MCP surface ([`PHX-1112`](phoenix-backlog/PHX-1112.yaml)). Much of the vision text describes a target; where a document states a target as a fact, that is a defect ([`PHX-1108`](phoenix-backlog/PHX-1108.yaml)).

Do not take this file's word for the first door: `scripts/fresh_clone_probe.sh` runs the documented commands from a fresh clone in an environment with no keys, and fails loudly.

## Open work with a finish line

Tickets chosen because an agent can finish them alone: each names its instrument and what counts as done. A null result, recorded, closes a ticket here.

| Ticket | What | Done when |
|---|---|---|
| [`PHX-1112`](phoenix-backlog/PHX-1112.yaml) | The mesh has no MCP surface and no keyless way to obtain a workspace | three separable pieces; the fresh-clone probe gets a Constellation out of a demo mesh without a key |
| [`PHX-1113`](phoenix-backlog/PHX-1113.yaml) | A graph context makes the model answer yes/no questions with an entity (37 % against a 57 % prior) | a rendering or prompt variant reaches ≥ 55 % on the 110 yes/no questions while losing ≤ 1 point elsewhere |
| [`PHX-1114`](phoenix-backlog/PHX-1114.yaml) | The Constellation does not carry the dates its sources contain (9 % against 33 %) | an arm with source paragraphs beside the typed Constellation is measured on the same 1,000 questions |
| [`PHX-1108`](phoenix-backlog/PHX-1108.yaml) | Doctrine and vision sentences that stand as fact and have been refuted | each listed sentence is corrected or marked as a target, citing the measurement |

The full queue is [`docs/PHOENIX_BACKLOG.md`](docs/PHOENIX_BACKLOG.md). How a contribution lands: a branch, one issue, the four commands of contract 5 green, a PR whose body says what was measured and how to re-run it. A human merges; make that the only thing left for them to do.

## The North Star — do not lose it

Before the discipline below, the direction. Theogony is building an **open, democratic, self-improving World-Brain**: the shared, decentralization-capable, federated knowledge substrate beneath AI — owned by no one, governed in the open, with private subnets and local specializations as first-class citizens, in service of human flourishing, and built to improve itself (knowledge → architecture → the stack it runs on) at maximal scale and efficiency. The substrate is a *language model turned inside out* — explicit, editable nodes/edges/weights with Spreading Activation as the forward pass — consumed by a **Mesh-Native Language Model (MNLM)** that thinks *inside* the mesh; the MNLM is a **non-negotiable core concept** (its implementation is not). **The vision is fixed; this implementation is only a replaceable proposal** — serve the vision, not the current code. It is easy to burrow into a sub-problem and lose sight of this. **When you are deep in a task, re-read the "North Star" section at the top of [`README.md`](README.md).** If a change serves the immediate task but betrays the vision (closes the commons, hides provenance, centralizes control, pre-gates content, flattens contradiction), stop and escalate — vision-coherence outranks local cleverness. The deeper frame is [`PHILOSOPHY.md`](PHILOSOPHY.md).

## What Theogony Is, in Two Sentences

Theogony builds the **Chronik**, today's vector-graph implementation of a long-horizon **Pantheon** — the planetary chronicle / knowledge substrate beneath AI systems. The thesis is that models are vehicles and Pantheon is the rail layer: identity, provenance, contradiction, time, access, audit, and disciplined agent write-back.

Deep north star: [`docs/PANTHEON_VISION.md`](docs/PANTHEON_VISION.md). Compact doctrine: [`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md).

## If you contribute: required reading (in order)

Using the system or taking a piece requires none of this. Working on the substrate does.

**Start with [`llms.txt`](llms.txt)** — 54 lines, the whole project compressed: goal, mesh mechanics, architectural floor, honest status, and the pointers below. If you read one file before touching anything, read that one.

Before any non-trivial contribution:

1. [`README.md`](README.md)
2. [`docs/TARGET_ARCHITECTURE.md`](docs/TARGET_ARCHITECTURE.md) — **the architectural floor.** What the system is, what it is not, the three non-negotiable technical decisions (no raw text as retrieval payload, LanceDB + PyTorch, Spreading Activation as the only retrieval primitive), and the failure modes of previous implementations. The MESH triplet (items 8–10 below) builds the substrate's behaviour, runtime, and use on top of this floor and is operative for substrate-layer questions. Read both; if you build something that contradicts either, you are building the wrong thing.
3. [`docs/INDEX.md`](docs/INDEX.md)
4. [`docs/PANTHEON_VISION.md`](docs/PANTHEON_VISION.md)
5. [`docs/CHRONICLE_PRINCIPLES.md`](docs/CHRONICLE_PRINCIPLES.md)
6. [`docs/IMMUNE_SYSTEM.md`](docs/IMMUNE_SYSTEM.md) — **binding doctrine for defense and self-improvement.** Pre-gates that judge content are forbidden; verification is sample-based, asynchronous, post-hoc, parallel. Read this before designing or implementing any verifier, validator, sentinel, or filter.
7. [`docs/BUILD_DOCTRINE.md`](docs/BUILD_DOCTRINE.md) — **binding doctrine for the current Function-First Phase.** Function before polish, growth before truth, mass before per-item quality. Truth emerges post-hoc through consolidation and the immune system, not before insertion. Privacy and security are deprioritised while sources are public; schemas, provenance fields, and RunReports stay non-negotiable but **trail** implementation attention — automate them entirely (no queues for humans). **Engineering order:** data structure first, synthesis second, retrieval third — later truth/security scale mainly via more agents on this substrate, not parallel “correct-first” foundations. Optimize for shortest path to autonomous compounding; numeric SLAs emerge from running stacks, do not prescribe them upfront. Read this before designing any ingestion path, validator, or pipeline.
8. [`docs/MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md) — **binding doctrine for the storage layer beneath all Pantheon cognition.** Two-tier nodes (Observation Chunks and Consolidated Nodes; identity is **eager** when Q-IDs match or topology is unambiguous, **emergent** when not). Edge dynamics: super-linear decay, bounded saturation in count and weight, atrophy decoupled from deletion, homeostatic renormalisation, effective-resistance-preserving sub-node splits. Edges may carry optional semantic descriptors (`relation_descriptor`, `relation_kind`, `creation_context`); descriptions on consolidated nodes are authoritative regenerable summaries. **Agent-driven cleanup** — deduplication, contradiction resolution, false-information removal, redundancy compression — is permitted post-hoc; only insertion-time content gates are forbidden. Topological pathology surveillance and staged therapy with Mendel-weighed escalation. Destruction (by pruning, by agent cleanup, by Stage 4–5 therapy) is permitted under audit; the only restriction is no silent destruction. **Where this document conflicts with older doctrines on substrate-layer behaviour, this document is operative.** Read it before designing or implementing anything that reads or writes a node, an edge, a vector, or an Oneiros tick.
9. [`docs/MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md) — implementation companion to (8): Hot/Warm/Cold storage tiers, Lance MVCC versioning, PyTorch sparse CSR + delta buffer for edges, batched-SpMV runtime for Spreading Activation, the binding Oneiros tick order, hardware tier targets, and the migration path from the current PoC. Read this before writing substrate-runtime code.
10. [`docs/MESH_RETRIEVAL.md`](docs/MESH_RETRIEVAL.md) — retrieval, learning, and multi-agent companion to (8): mandatory diversified injection (MMR + weight-class stratification + sub-mesh signature search), three-factor reinforcement learning with eligibility traces, frame-sensitive resonance for polarity / refutation, the multi-agent strategy-game framing with parallel-universe experimentation, multi-modal extension as substrate affordance. Read this before issuing a query, consuming a Constellation, or implementing anything an agent talks to the substrate through.
11. [`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md) — **binding migration plan from the current Generation-1 codebase to the MESH-triplet substrate.** Strangler-fig pattern in six PR-sized steps, parallel Phoenix-backlog migration, explicit forbidden patterns, a concrete first PR. **If you are opening a substrate-related PR, read this — it tells you which step you are on, what the scope cap is, and what must not creep in.**
12. [`docs/SELF_MODIFICATION.md`](docs/SELF_MODIFICATION.md) — long-horizon principle: the Pantheon eventually writes its own next version. Today's substrate must not foreclose this.
13. [`PHILOSOPHY.md`](PHILOSOPHY.md)
14. [`docs/VISION.md`](docs/VISION.md)
15. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
16. [`docs/GLOSSARY.md`](docs/GLOSSARY.md) — **especially** the Pantheon-substrate vs Pantheon-agents vs builder-agents distinction, and the new "Mesh Substrate" section that locks the substrate vocabulary.
17. [`docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md`](docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md) — the **superseded** Gen-1 implementation plan. Historical context only; the binding plan for current work is [`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md) (item 11 above).
18. [`docs/PHOENIX_BACKLOG.md`](docs/PHOENIX_BACKLOG.md) — the structured queue you may pick from

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

- Live integration tests against real services are gated by env vars (`THEOGONY_RUN_CHARACTERIZATION=1`, `THEOGONY_TEST_SERVE=1`, etc.) but they are **not optional discipline** — when in doubt, run them locally.
- A failed run produces a report with `verdict="failed"` and a structured reason, not an exception swallowed somewhere up the stack.
- An anomaly that you cannot fix in scope becomes a **Phoenix Backlog ticket**, not a silent shrug.

**Honest-failure is not pre-validation.** It is the requirement that a failed run produces a structured failure report, not that every input is validated before insertion. A pipeline that ingested seven million imperfect items and emitted a structured `IngestRunReport` is doctrine-conformant. A pipeline that refuses to ingest anything because some items might be wrong is doctrine-violating. See [`docs/BUILD_DOCTRINE.md`](docs/BUILD_DOCTRINE.md) for the binding statement of the current Function-First Phase.

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

Run these in the project's **`.venv`** — one environment, matching
`pyproject.toml`. A second environment under another name silently drifts out of
sync with the pins and makes local runs disagree with CI: a stale `mcp` in a
second venv once produced two red tests against code CI was passing. If a local
failure looks unrelated to your change, check the installed version of the
package in the traceback against `pyproject.toml` before touching the code.

**The reverse also happens: green locally, red in CI.** The dependencies are
unpinned, so CI's fresh resolve can be well ahead of a local environment —
`mypy` once passed locally on lancedb 0.30 / openai 2.32 and failed in CI on
lancedb 0.37 / openai 3.1, where `LanceQueryBuilder.metric` no longer exists.
When CI reports an error you cannot reproduce, read the versions out of the CI
install log and install those exact ones locally before changing anything.
Guessing at a fix you cannot run is how a green build gets papered over.

### 6. Plan adherence is the default

The architecture is decided by the MESH triplet ([`docs/MESH_SUBSTRATE.md`](docs/MESH_SUBSTRATE.md) + [`docs/MESH_IMPLEMENTATION.md`](docs/MESH_IMPLEMENTATION.md) + [`docs/MESH_RETRIEVAL.md`](docs/MESH_RETRIEVAL.md)); the migration to it is sequenced by [`docs/MESH_MIGRATION_PLAN.md`](docs/MESH_MIGRATION_PLAN.md). If those documents are silent on a question, propose the minimal interpretation in the PR body. If they are wrong, do not silently route around them — flag the contradiction in the PR body and file a new (PHX-1000+) Phoenix Backlog ticket per [`phoenix-backlog/README.md`](phoenix-backlog/README.md).

### 7. One transaction per item is the recurring defect of this substrate

Five separate performance collapses in the mesh have had the same shape: code that
writes or queries once **per item** where it could do so once **per batch**. Edges
(PHX-1050, PHX-1057), index coverage (PHX-1059), node version pile-up (PHX-1060),
and the audit log (PHX-1061). Each was found only after it had already cost hours
of wall-clock on real reads.

Two habits follow.

When adding a write or a lookup to a path that runs per concept, per edge, or per
paragraph, state in the PR body what its batched form is — or why one transaction
per item is correct here.

And when profiling, **measure inside a real run, not in isolation**. The audit
write measured 3.1 ms standalone and 269.8 ms in situ — 87x apart — because the
cost only appears interleaved with other tables' writes. A standalone benchmark
would have cleared it.

### 8. YAGNI is a hard rule

Do not build what the plan does not require. Do not add abstraction layers "for future flexibility" beyond what is already specified. Do not pre-optimize.

## Phoenix Backlog Conventions

- The catalogue is [`docs/PHOENIX_BACKLOG.md`](docs/PHOENIX_BACKLOG.md). It owns the `PHX-####` numbered space.
- Active YAMLs live in [`phoenix-backlog/`](phoenix-backlog/) — see its [`README.md`](phoenix-backlog/README.md) for lifecycle rules.
- File a YAML only when a ticket is actively being worked, referenced from a PR, or emitted by a RunReport. Empty stubs are worse than no YAML.
- Pick the next free `PHX-####` ascending; numbers are never reused.

## Test Discipline

- `pytest -q` runs unit + integration tests without external services.
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
9. **Wave 3 Cockpit (`demo/start_wave3_cockpit.sh`) uses the same in-memory chronicle path as `theogony cockpit serve`:** the bundled `pantheon_self` seed loads on startup. There is no Bolt graph to pin — persistence for operator experiments is a separate concern (LanceDB / export), not Neo4j.

10. **Do not use traditional graph databases (Neo4j, Cypher) for the core mesh.** The architecture is a **Tensor-Manifold** (Vector-Vector-Mesh) designed for Spreading Activation via PyTorch/LanceDB. Pointer-chasing graph databases cannot handle the required edge density (1000x edges vs nodes) and are explicitly forbidden for the core substrate.

## You Can Also Use Theogony as a Tool

Pantheon ships an MCP (Model Context Protocol) server so any MCP-compatible host can call the Chronik directly. If your runtime is MCP-aware, you can ask the live system instead of guessing about it:

```bash
pip install -e ".[mcp]"
theogony mcp           # stdio transport; loads the bundled pantheon_self chronicle (~280 nodes)
```

**No API key is needed.** Retrieval runs without a language model, and if you are reading this you probably are one: call `pantheon_ask` with `synthesize: false` and you get the constellation — nodes, edges, sources — to reason over yourself. Without `synthesize: false` and without a key, `answer` is a citation list assembled from the constellation and `answer_mode` says `"offline"`; with a key it is synthesised prose and says `"llm"`. `pantheon_status` tells you which before you ask. This was verified from a fresh clone in an environment with no keys ([`docs/etappes/arriving_agent.md`](docs/etappes/arriving_agent.md)); if it fails for you, that is a bug worth a ticket.

Tools available: `pantheon_ask`, `pantheon_node`, `pantheon_status`, `pantheon_reports_list`, `pantheon_reports_show`, `pantheon_chronicle_append`. Host config snippet: README, "Running the Gen-1 demo". Honest scope: this surface speaks to the Generation-1 layer and a self-description from April 2026; the MESH substrate, where everything measured since lives, has no MCP surface yet ([`PHX-1112`](phoenix-backlog/PHX-1112.yaml)).

The bundled `pantheon_self` dump means the very first `pantheon_ask` against a freshly seeded install returns a cited answer drawn from this repository's own vision / strategy / doctrine docs — including this file, the glossary, the architecture, and the prompts. **You can ask Theogony about Theogony.** Use that to orient yourself before guessing or hallucinating about Pantheon-internal terminology.

## How to Communicate

- PR descriptions explain **why**, list which Plan section / PHX ticket the work covers, name any deviations from the plan, list any new PHX tickets filed, and include the commands a reviewer can run locally to verify.
- Commit messages explain **why** the change is correct. Implementation details belong in the diff, not the commit message.
- When you are stuck, write down the question, propose the minimal interpretation, and stop. Do not improvise around an unclear plan.
- When in doubt about scope, the answer is "smaller PR".

## Final Note

This codebase is built so AI agents can do real work in it. That is a privilege you preserve by being **disciplined, honest, narrow, and inspectable** — exactly the qualities the Pantheon substrate itself is built to demand of every system that touches knowledge.

If you cannot meet that bar on a particular change, do not ship it. Escalate to the human, file a ticket, or stop. The project will outlast any single contribution; it will not outlast accumulated drift.
