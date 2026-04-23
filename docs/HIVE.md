# Hive

The Chronik is built by **Pantheon agents** (the mythological runtime roles — not "the Pantheon" planetary substrate; see [`GLOSSARY.md`](GLOSSARY.md)) working together like bees building a hive.

No single agent sees the whole picture. No single agent carries the full burden. Each does what it does best, and through their coordination, something emerges that no individual agent could produce alone: distilled, stable, high-energy knowledge — Honig.

## From Raw Material to Honey

The production chain is analogous to a real hive:

| Bee Role | Pantheon agent (role) | Action |
|----------|---------------|--------|
| Scout | Argus, Prometheus | find sources, identify gaps |
| Forager | Argus, Jason, Iris | acquire raw content |
| Processor | Extraction Pipeline | digest text into entities, relations, embeddings |
| Builder | Morpheus | create associations, infer new edges (Phase 1: deterministic embedding-band + co-occurrence proposals via opt-in `morpheus` tick phase; LLM dreaming is PHX-0004) |
| Inspector | Athene | verify, challenge, score confidence |
| Recycler | Chronos | remove waste, compress, archive |
| Guard | Hades | protect private stores |
| Queen | Helios | oversee strategy and colony health |
| Advisor | Metis | counsel based on what the hive knows |

### Auditors (meta-cognitive and adversarial)

| Role | Pantheon agent | PHX | Action |
|------|----------------|------|--------|
| External adversary | Eris | [PHX-0067](../phoenix-backlog/PHX-0067.yaml) | red-team probes; findings as reports |
| Internal hubris | Nemesis | [PHX-0068](../phoenix-backlog/PHX-0068.yaml) | overconfidence audits; read-only |
| Meta-cognitive memory | Mnemosyne | [PHX-0071](../phoenix-backlog/PHX-0071.yaml) | classifies self-referential queries; aggregates signals for backlog hygiene ([`MNEMOSYNE.md`](MNEMOSYNE.md)) |
| Auditor triage (planned) | Asklepios | [PHX-0073](../phoenix-backlog/PHX-0073.yaml) | routes Nemesis/Eris-style findings into actionable repair work |

The key insight: **no agent produces honey alone**. Honey is the emergent product of many **Pantheon agents** working on the same **Chronik** substrate — the living graph the project is building today toward the wider **Pantheon** chronicle vision ([`PANTHEON_VISION.md`](PANTHEON_VISION.md)).

## The Promotor Principle

In genetics, a promotor does not change the gene — it controls how strongly it is expressed.

The **Pantheon agent roster** works the same way.

Each agent class (Hestia, Chronos, Athene, Morpheus…) stays stable. What changes is its **expression**: how many instances run, how often, at what priority, with what budget, in response to which signals.

Helios manages the promotors.

Examples:
- drift risk detected → Hestia promotor raised → more audits, lower escalation threshold
- high ingest load → Jason promotor raised → more parallel ingest capacity
- contradiction density high → Athene promotor raised → more verification passes
- knowledge gaps accumulating → Prometheus promotor raised → more acquisition tasks
- resource pressure → all promotors dampened proportionally

This is how a finite resource pool becomes adaptive.

**Hestia as a dial:** When the system risks drifting in a dehumanizing direction, Helios increases Hestia's expression. This is not a veto — it is a weight. The heavier Hestia runs, the harder it is for drift to go unnoticed.

## Beyond Memory: The Chronik as Blueprint

The Chronik begins as external memory for lean reasoning models. But it can evolve further.

### Stage 1: External Memory

LLMs query the Chronik instead of relying on stale weights. This is Generation 1.

### Stage 2: Distillation Source

Agents generate training datasets from the Chronik — not from raw internet, but from verified, structured, epistemically graded knowledge. Small models trained on Chronik distillates learn specific cognitive skills:

- fact synthesis
- source evaluation
- contradiction detection
- perspective switching
- advisory behavior

### Stage 3: Modular Intelligence

Instead of one monolithic model, the system composes intelligence from many specialized modules:

- domain expert LoRAs
- reasoning micro-models
- verification circuits
- advisory modules
- each fed by different regions of the Chronik

### Stage 4: Designed Networks

Eventually, if the field advances far enough, the Chronik may inform the design of neural structures that are partially written rather than fully trained. Hybrid architectures combining symbolic graph structure, geometric embeddings, and targeted neural modules.

This is speculative. But the architecture should not prevent it.

## The Sensorium

The Chronik needs senses. Not all knowledge exists as text on the internet.

The acquisition layer must eventually support:

- PDF and document parsing
- image interpretation
- handwriting recognition (OHR)
- voice-to-text transcription
- video analysis
- forensic writing style analysis
- physical library access (future)

Each of these is an acquisition adapter. The extraction pipeline downstream does not care which sense provided the input. The key architectural point: **every sense must produce provenance-anchored output**. A transcribed audio clip, a scanned page, or a recognized face must carry source references just as strongly as a web-crawled text.

### The Surveillance Problem

Some of these capabilities border on surveillance. This is acknowledged honestly.

The three-tier digital twin model (public, consensual private, shadow) is the ethical architecture for this tension. Every inferred observation about a person must be classified:

- observed
- explicitly given
- inferred
- speculative
- forbidden to operationalize

The Right to Opacity remains a core principle.

## Argonauts

**Argonauts** (cluster-specialised sub-agents) are reserved by PHX-0060: `ClusterSummary.properties["agent_class"]` is the extension slot. No Argonaut lifecycle ships in Phase 1 — that lands in a dedicated Phase-2 sub-ticket once clusters are stable in production.

## Hardware Evolution

Current GPUs are optimized for transformer-style matrix multiplication. The Chronik's core operations are different:

- graph activation and propagation
- signed edge traversal
- temporal neighborhood search
- hyperedge evaluation
- event-based memory access
- sparse routing
- epistemic scoring

Future AI-designed hardware may be optimized for exactly these primitives. If and when that happens, the Chronik becomes dramatically more efficient — not by accident, but because its operations are fundamentally different from today's dominant compute patterns.

This is a long-term possibility, not a near-term plan. But the architecture should be designed with awareness that the hardware landscape will change.
