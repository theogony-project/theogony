# Phoenix Backlog

The Phoenix Backlog is the evolutionary memory of the Chronik. It captures problems, improvements, visions, and architectural decisions that should be considered in future generations — specifically regarding the Chronik's knowledge organization, not peripherals like GUI or client interfaces.

Tickets are filed by agents or humans during operation. They are evaluated when planning a Phoenix process (distillation and rebirth of the Chronik).

## Two Layers: Catalogue and Active YAMLs

The Phoenix Backlog has two layers, deliberately:

1. **The catalogue** — this document (`docs/PHOENIX_BACKLOG.md`) and the implementation plan (`docs/IMPLEMENTATION_PLAN_GEN1.md` §7). This is the authoritative list of every PHX ticket that has ever been conceived. The numbered space `PHX-####` is allocated here.
2. **Active YAMLs** — the files in [`phoenix-backlog/`](../phoenix-backlog/). These are the structured, machine-readable working copies of tickets that are currently being acted on, referenced from a PR or RunReport, or otherwise "warm".

A YAML file is created **only when a ticket becomes active**. Absent YAML files are not gaps — they are intentional lazy materialization. A ticket that lives only in the catalogue is real; it just has no active workspace yet.

This avoids the failure mode of dozens of stub YAMLs that nobody updates, while keeping the option to promote any catalogue entry into an active YAML the moment work begins on it. Conversely, a YAML may be archived back into catalogue-only form once a ticket is resolved or deferred and the structured fields no longer pay rent.

When you file a new ticket: add it to this catalogue first. Create the YAML only if you (or another agent) intend to begin work on it now, or if a PR/RunReport needs to reference its structured form. See [`phoenix-backlog/README.md`](../phoenix-backlog/README.md) for the operational details.

## Ticket Format

Each active ticket in `phoenix-backlog/` is a YAML file:

```yaml
id: PHX-0001
category: vision           # bug | improvement | vision | performance | knowledge_gap
priority: high              # critical | high | medium | low | vision
status: open                # open | accepted | in_progress | resolved | deferred
generation_target: 2        # which generation this targets (0 = any)
title: "Short descriptive title"
filed_by: hesiod            # agent name or human identifier
created_at: 2026-04-15
description: |
  Detailed description of the issue, improvement, or vision.
resolution: null            # filled when resolved
```

---

## Gen 1 Tickets

### PHX-0001: Custom Knowledge Store Engine

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2-3
- **Filed by**: hesiod

Neo4j is adequate for Gen 1 but not designed for the Chronik's specific access pattern: combined vector similarity + graph traversal as a single native operation. A custom engine that treats vector proximity and graph edges as aspects of the same navigational structure could be fundamentally more efficient at scale. This should be explored once real-world query patterns from Gen 1 provide data on what the ideal engine needs to optimize for.

### PHX-0002: Hierarchical Embedding Spaces

- **Category**: improvement
- **Priority**: high
- **Generation Target**: 2

Current embedding models produce flat vectors in a single space. The Chronik's hierarchical cluster structure suggests that embeddings at different abstraction levels (individual facts vs. topic summaries vs. domain overviews) might benefit from different embedding strategies or even different dimensionalities. Research needed: can a hierarchical embedding model be trained that produces naturally clustered representations?

### PHX-0003: Federated Chronik Instances

- **Category**: vision
- **Priority**: medium
- **Generation Target**: 3

Multiple Chronik instances (university departments, national libraries, research institutions) could federate — sharing knowledge across instance boundaries while respecting access controls. Key open questions: federation protocol, conflict resolution for contradictory facts across instances, trust propagation between instances.

### PHX-0004: Crystallized Inference

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

The Oneiros process currently connects existing knowledge. It should also perform and store *inferences* — derived knowledge that follows logically from existing facts. If A implies B and B implies C, the edge A→C should exist with computed confidence. This turns the Chronik into a distributed logic engine. Open questions: how to prevent inference chains from hallucinating, how to mark derived knowledge distinctly from observed knowledge.

### PHX-0005: Embedding Model Independence

- **Category**: improvement
- **Priority**: critical
- **Generation Target**: 1

The Chronik must not be locked to a specific embedding model. When a better model becomes available, it should be possible to re-embed incrementally (not all at once) during the Phoenix process. This requires storing the embedding model identifier with each vector and supporting mixed-model queries during transition periods.

### PHX-0006: Federated Compute (Distributed Dreaming)

- **Category**: vision
- **Priority**: medium
- **Generation Target**: 3

Allow external compute donors to run Oneiros tasks — embedding generation, association discovery, verification. Like Folding@home but for knowledge consolidation. Requires: task serialization, result verification, trust scoring for compute donors.

### PHX-0007: Scientific Workbench Agents

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

Specialized agents that use the Chronik as a research tool: cross-referencing scientific claims, identifying replication failures, suggesting experiments based on gap analysis, generating automated literature reviews. The Chronik becomes not just a knowledge store but an active research partner.

### PHX-0008: Multi-Language Knowledge Bridging

- **Category**: improvement
- **Priority**: medium
- **Generation Target**: 2

Knowledge extracted from a German source and knowledge extracted from a Japanese source about the same entity should converge on the same node. This requires cross-lingual entity resolution and potentially multi-lingual embedding models. The Argonauts (language specialists) are the natural agents for this.

### PHX-0009: Vitality Function Tuning

- **Category**: improvement
- **Priority**: medium
- **Generation Target**: 1-2

The vitality function weights (w1, w2, w3, w4) and the dynamic threshold need empirical tuning based on real usage data. Initial values will be heuristic. A feedback loop should be established where Helios adjusts these parameters based on system performance metrics.

### PHX-0010: Physical Library Acquisition

- **Category**: vision
- **Priority**: low
- **Generation Target**: 3+

Robotic systems that can visit physical libraries (e.g., Bavarian State Library), request books from stacks, scan or photograph pages, and feed the content into the acquisition pipeline. This requires hardware integration far beyond the current scope, but the acquisition adapter interface should be designed to accommodate it.

### PHX-0011: Knowledge Condensation at Scale

- **Category**: performance
- **Priority**: high
- **Generation Target**: 2

At billions of nodes, many represent highly similar or overlapping knowledge. A condensation process should identify clusters of near-duplicate nodes and merge them into single, higher-confidence nodes with combined source references. This is distinct from deduplication (removing exact copies) — it is semantic compression.

### PHX-0012: Cost Accounting and Credit System

- **Category**: improvement
- **Priority**: medium
- **Generation Target**: 1

Every operation (query, ingestion, agent task) should track its resource cost: LLM tokens consumed, embeddings generated, graph traversals performed, storage used. This enables the credit-based pricing model and provides data for cost optimization.

### PHX-0013: Chronese Canonical Semantic Layer

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

The Chronik should converge on a canonical semantic language that sits between source text and all graph/vector projections. This language, tentatively called Chronese, should be language-neutral, event-centric, provenance-bound, and epistemically explicit. Gen 1 can represent it as strict JSON/Pydantic schemas, but future generations may require a richer compiler, versioning system, and projection toolchain.

### PHX-0014: Metis Advisory Runtime

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

The Chronik should support a dedicated advisory agent, Metis, that operates across Akasha, Lethe, and an explicit Norm Space. Metis must separate facts, analogies, options, risks, and value assumptions rather than collapsing them into a single recommendation. Future work includes defining advisory packets, audit traces, norm handling, and ethical constraints for personal and institutional guidance.

### PHX-0020: Operative Knowledge — The Fifth Form

- **Category**: vision
- **Priority**: low
- **Generation Target**: 3

The Chronik must eventually represent operative knowledge: the knowledge that runs the world rather than describes it. Schedules, logistics, machine control, supply forecasts. Implies a new class of operative agents (Atlas, Hephaistos, Demeter) that act on the world. Long-horizon dimension; not part of Generation 1 or 2. The architecture should remain general enough to accommodate it. See [`OPERATIVE_KNOWLEDGE.md`](OPERATIVE_KNOWLEDGE.md).

### PHX-0037: Curiosity Loop — End-to-End Implementation

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2-3

The architectural coupling between attention and acquisition. Stub detection on every Constellation produces a structured `StubVerdict`; when the verdict crosses threshold a `CuriosityTrigger` is emitted; Helios dispatches Prometheus → Argus → Jason → Morpheus → Athene to acquire new content in exactly the focused region; the Constellation re-assembles progressively; a `CuriosityRunReport` is emitted per run. Cold regions may be slow, never silent. Generation 1 emits `StubVerdict` as a foothold (no trigger) so calibration data accumulates. See [`CURIOSITY.md`](CURIOSITY.md). Hard dependency on PHX-0039 (Hestia auditing) — neither ships without the other.

### PHX-0038: Mind-Map Response Format

- **Category**: improvement
- **Priority**: high
- **Generation Target**: 2

Constellation responses become structured for direct Mind-Map rendering: explicit zoom-targets per node (sub-query handles), node-level source-citation glyphs, vitality and confidence summaries, edge-relation typing visible to clients, and a progressive-update protocol (`research_in_progress: true` + `CuriosityRun` ID for live subscription). The Chronik provides no GUI; this ticket specifies only the server-side response contract that makes Mind-Map clients (web, mobile, terminal-graph, voice) possible. See [`CURIOSITY.md`](CURIOSITY.md) §"Mind-Map as Interface".

### PHX-0039: Hestia Curiosity Auditing

- **Category**: vision
- **Priority**: critical
- **Generation Target**: 2-3

Hestia's standing subscription to every `CuriosityTrigger`. Person-as-target check (private individuals require explicit consent or refusal); sensitive-topic rules (health, sexuality, religion, political dissent, financial distress run under tighter sourcing and confidence rules); recursion budgets (a single attention act has a bounded downstream research budget; sub-zooms inherit reduced budgets); drift audit (Hestia reviews patterns of Curiosity activation and can throttle the loop globally via the regulatory dial). Curiosity without Hestia is a profiling engine. Hard dependency partner of PHX-0037. See [`CURIOSITY.md`](CURIOSITY.md) §"Hestia and Curiosity" and [`HESTIA.md`](HESTIA.md).

---

## Open Architectural Questions

These are questions that do not yet have answers. They should be resolved through experimentation and community discussion.

1. **What is the optimal chunk granularity for knowledge atoms?** A single fact ("Harrer reached Uttar Kashi") vs. a composite claim ("Harrer and Marchese reached the temple city of Uttar Kashi around midnight after long wandering") — where is the right boundary?

2. **How should contradictory knowledge coexist?** Two sources claim different dates for the same event. Both nodes exist with edges to the event. How does the system represent the contradiction without arbitrating truth? Is a "contradiction" edge type sufficient?

3. **What embedding dimensionality is optimal?** Higher dimensions capture more nuance but cost more storage and compute. Is 768 sufficient, or does the Chronik's use case benefit from 2048 or 4096?

4. **How aggressively should Oneiros run?** More dreaming = faster consolidation but higher compute cost. Less dreaming = cheaper but slower knowledge maturation. What is the right balance?

5. **Can the Chronik replace text entirely?** The current design stores short labels and source references but not full text. Is there a class of queries where the original text is irretrievable from the knowledge network alone?

6. **What is the right governance model?** Benevolent dictator → foundation → decentralized DAO? At what scale does each transition make sense?

---

## Filing New Tickets

Anyone — human or agent — can file a Phoenix Backlog ticket by creating a YAML file in `phoenix-backlog/` following the format above. Ticket IDs are sequential: `PHX-NNNN`.

Tickets are reviewed during Phoenix process planning. Accepted tickets influence the design of the next generation. Deferred tickets remain in the backlog for future generations.
