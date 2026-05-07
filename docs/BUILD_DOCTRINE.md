# Build Doctrine — Function before Polish

**Status:** canonical doctrine for the current build phase ("Function-First Phase").
**Audience:** every agent — Pantheon, builder, or external — that touches ingestion, extraction, schemas, or the chronicle itself.
**Companion docs:** [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md), [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md), [`PANTHEON_VISION.md`](PANTHEON_VISION.md).

## Why this doc exists

The Pantheon doctrine has always rejected the clinic model: pre-gates that judge content before it enters the chronicle are forbidden. [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) spells out why — total coverage is unattainable, synchronous gates make the system slow and brittle, pre-filtering hides the system's actual epistemic state.

Despite this, agents (including AI agents working on this repo) repeatedly slide back into clinic-style reasoning: *"first we should validate every Wikipedia article, then we should ingest only the clean ones, then we should add provenance afterward."* That pattern is wrong by doctrine and wrong for the current phase.

This document exists so that no agent can credibly claim the doctrine was unclear.

## The headline rule

> **Function before polish. Run it, then heal it.**

Imperfection at ingest time is **the design**, not a defect. The substrate is meant to grow first, consolidate second, validate third. Truth is not a property to be **secured before insertion** — it is a property that **emerges from mass and consolidation post-hoc**, supervised by the immune system.

## Function-First Phase — explicit declaration

We are currently in the **Function-First Phase**. In this phase:

1. **Growth is the highest priority.** Mass and velocity of ingestion outweigh per-item polish.
2. **Truth is not yet a priority.** Truth becomes a priority once enough data has accumulated for consolidation to be meaningful. Until then, the system contains contradictions, errors, gaps, low-confidence assertions — by design.
3. **Privacy is not yet a priority.** All current sources (Wikipedia, Wikidata) are public. Privacy enforcement returns to priority only when private sources (Lethe Vaults) enter scope.
4. **Security is not yet a priority** beyond operational self-defense (rate limits, robots.txt, response-size caps). Adversarial robustness, access control, and authority modelling return to priority once the system has external users.
5. **Zero human work on the substrate path.** Nothing in ingestion, bookkeeping, enrichment, segmentation, reconciliation, DLQ drainage, or run reporting may assume a human reader, reviewer, labeler, or approver — now or implied as “eventually.” Doctrine-level intervention by an operator stays outside this definition. Prefer designs that degrade to **queued agent workloads** rather than halted humans.
6. **Massive language-model and agent leverage.** Anything that can be done by an agent should be done by an agent. Anything that cannot be done by an agent yet should be queued, not blocked.

This phase ends when the substrate has enough mass that consolidation produces useful signal, and when an operator decides — explicitly, in a documented decision — that the next phase begins. **Until that decision, every agent operates under this doctrine.**

## Build mandate — priority order and fastest start

**What comes first.** Maximize **time-to-live compounding**: a thin vertical slice must write real assertions into real storage quickly, then widen. Fancy retrieval and deep consolidation are worthless if the ingest path does not breathe on day one — but do not paper over schemas with ad-hoc dicts while doing so.

**Ordering of engineering concern** (explicit; use this when trade-offs collide):

1. **Data structure first.** Shapes worth compounding — Chronese-level assertions, identities, provenance fields, projections (graph + vectors), append-only semantics. Prefer a clean substrate with noisy rows over noisy shapes with pretty rows.
2. **Knowledge synthesis second.** Automated extraction and write-back — high-throughput ingestion of assertions into that structure, including contradictory or low-confidence material as typed facts, dead-letter queues for machines to re-drive — still with **no** pre-validation gates.
3. **Retrieval third.** Responsive read paths — planners, embeddings, constellations — deepened once (1) and (2) are moving, without blocking them with latency budgets or perfectionism.

Solid architecture means **schemas, provenance records, and run reports remain machine-generated artefacts**, not human proof-reading.

**Non-negotiable disciplines are not waived — they stay *behind* speed in *attention*.** Implement them so they **scale like infrastructure**: codegen, validators, exporters, immutable append paths, bots that fill provenance automatically. They **must not** reintroduce the clinic pattern (blocking reviews, spreadsheets, cron mail for humans). If bookkeeping constrains throughput, **add automation or agents** — never human work queues.

Do **not** fix this doctrine to numeric targets (edges per euro, percentile latency budgets, etc.). Those will emerge from running stacks; prescribing them prematurely optimizes spreadsheets over shipping.

**Later truth and security** should land mainly through **additional agent throughput on this substrate**, not parallel “correct-first” foundational stacks — extend in place.

**Universal text intake (starting with Wikipedia)** is assumed to evolve toward **richer in-text markup** — pre-structuring raw text with tags for hierarchical chunks of different orders, keywords, index links, and topological connections. The text becomes a blueprint for the future vector nodes and edges **before** it hits the database. This is prep for synthesis, still without humans in that pipeline.

## What stays non-negotiable, even now

The Function-First Phase **does not** waive the structural disciplines below. They cost nothing at build time and make later hardening trivial:

- **Schemas remain Pydantic v2 with `extra="forbid"`.** Every node, every edge, every assertion still has a fixed shape. Schema enforcement is a *write-time* property, not a *truth-time* gate.
- **Provenance fields remain populated.** Every node still carries `source_anchor`, `revision_id`, `extracted_at`, `extractor_id`. The pipeline writes them automatically; no human has to verify them. This is not validation, it is bookkeeping.
- **AKA-IDs remain primary.** External IDs (Wikidata QIDs) attach as `external_ids`. The identity model does not bend.
- **RunReports remain mandatory.** Every pipeline still emits an `IngestRunReport` / `QueryRunReport` / `OneirosTickReport`. Honest failure is a *report verdict*, not a pre-validation step.
- **Pre-gates on content remain forbidden.** No "validate before insert" anywhere. Find a pre-gate, delete it.
- **The Chronicle Ledger remains append-only.** Mistakes get superseded, not overwritten.

These are *structural* properties, not *quality* properties. They exist so that the immune system has something to work on later. Without them, the substrate is unrecoverable; with them, growth-with-imperfection is recoverable by design.

## What the immune system does about the imperfection

The immune system already exists in [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md). In the Function-First Phase its load profile is:

- **Athene-Light** runs at low sampling rate (well below 2 %) — the goal is calibration data, not coverage.
- **Chronos-Light** demotes only the most accumulated cases — slow recycling, not aggressive cleanup.
- **Nemesis-Light** is a periodic structural scan, not a real-time auditor.
- **Eris** is paused. Red-team campaigns belong to a later phase.
- **Mnemosyne** observes growth metrics, not yet immune-system tuning.

These cells do not gate ingest. They observe and annotate post-hoc. They are allowed to lag the ingest by orders of magnitude in throughput, because **the chronicle is allowed to be wrong while it grows**.

## Translation for common situations

When in doubt during the Function-First Phase, ask the version of the question that prefers growth:

| Bad question (clinic-mode) | Right question (function-first) |
|---|---|
| *"Is this article clean enough to ingest?"* | *"Will the pipeline emit a structured failure report if it can't process it?"* |
| *"How do I validate every claim against Wikidata?"* | *"How do I record the assertion with its source anchor and let Athene sample later?"* |
| *"How do I prevent contradictions from entering?"* | *"How do I ensure contradictions get typed `CONTRADICTS` edges so Nemesis can find them?"* |
| *"How do I make the extractor 100 % accurate?"* | *"How do I make the extractor handle 95 % of cases and emit `verdict=failed` on the rest?"* |
| *"Should I ask the human to review this batch?"* | *"Which agent backlog consumes failed rows — and how does each run emit a verdict without implying a reader?"* |
| *"How do I add access control before ingesting Wikipedia?"* | *"Wikipedia is public. There is nothing to access-control. Move on."* |

## Honest-failure, sharpened

The "Honest-failure over silent success" rule in [`AGENTS.md`](../AGENTS.md) §3 is not a license for pre-validation. It is the requirement that a *failed run produces a structured failure report*. Honest-failure means:

- **A pipeline that crashed silently** is the failure mode to prevent.
- **A pipeline that ingested 7 million Wikipedia articles, of which 50 000 are flagged as suspect by Athene three weeks later, is doctrine-conformant.**
- **A pipeline that refuses to run because 50 000 articles might be wrong is doctrine-violating.**

## When this phase ends

This phase ends when an operator (currently a human; eventually possibly Mnemosyne under [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md)) writes a successor doctrine and supersedes this document. Future doctrines may reorder priorities — privacy, truth, security, governance may rise to the top in a later phase. **That is allowed and expected.** This document is binding *now*; it is not binding *forever*.

## One-line summary

**Run it. Let it grow. Let it be wrong. Heal it later.**
