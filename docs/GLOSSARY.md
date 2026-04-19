# Glossary

This glossary defines the canonical meaning of recurring terms used across the Theogony documents.

When a term appears in multiple documents, this file should be treated as the default reference unless a document explicitly narrows the meaning for a specific context.

## Core Terms

**Theogony**  
The overall project, architecture, and open initiative devoted to building the Chronik and the surrounding agent ecosystem.

**Chronik**  
The living knowledge system at the center of Theogony. A continuously evolving, open, verifiable knowledge network built from sources, semantic structure, graph relations, embeddings, provenance, and memory processes.

**Akasha**  
The global, shared, public knowledge space of the Chronik. This is the world-knowledge layer.

**Lethe Vault**  
A private, isolated knowledge space structurally similar to Akasha but protected by access control. Used for personal, organizational, or otherwise permission-bound knowledge.

**Pantheon**  
The ensemble of specialized agents that build, maintain, verify, and use the Chronik.

**Argonauts**  
A flexible class of specialized domain, language, media, or source experts that support the core Pantheon agents.

## Memory and Knowledge Layers

**Ephemera**  
The raw, fresh, unverified knowledge layer. New extractions land here first.

**Oneiros**  
The continuous dream process of the Chronik. Not a storage layer, but the ongoing background activity in which agents associate, verify, infer, deduplicate, and consolidate knowledge.

**Mneme**  
The permanent, trusted, highly connected memory layer of the Chronik.

**Phoenix**  
A rebirth or distillation process in which an existing Chronik is exported, reinterpreted, cleaned, and rebuilt into a new generation.

**Phoenix Backlog**  
The structured ticket system that captures problems, visions, improvements, and architectural desires for future generations of the Chronik.

## Representation and Semantics

**Knowledge Atom**  
An operational unit of knowledge inside the Chronik. In practical system terms this is often projected as nodes, edges, claims, events, or assertion frames.

**Chronese**  
The proposed canonical semantic language of the Chronik. A language-neutral, event-centric, provenance-bound, epistemically explicit form from which graph, vector, and textual projections can be derived.

**Assertion Frame**  
The core primitive proposed for Chronese. A structured representation of an event, state, claim, or inference involving participants, roles, time, place, qualifiers, epistemic state, and source grounding.

**Constellation**  
A structured, query-relevant working set returned by the Chronik to an agent. It contains the currently relevant nodes, edges, evidence, sources, gaps, and sometimes contradictions or competing hypotheses.

**Hover-Lupe**  
The idea that any entity or concept mentioned in an answer can be opened into a deeper local knowledge landscape. Not a static article, but a dynamic contextual zoom into the Chronik. The Hover-Lupe is also the entry point of the [Curiosity Loop](CURIOSITY.md): a zoom into a thin region triggers research in exactly that region.

**Curiosity Loop**  
The architectural coupling between attention and acquisition. A query, a zoom, or a contextual ask runs a structured stub check on the assembled Constellation; if the verdict crosses threshold, a `CuriosityTrigger` is emitted; Helios dispatches Prometheus → Argus → Jason → Morpheus → Athene to acquire new content in exactly the focused region; the Constellation re-assembles progressively. Hestia subscribes to every trigger to prevent attention-driven research from sliding into surveillance. See [`CURIOSITY.md`](CURIOSITY.md). Generation 2-3, with a Gen 1 stub-detection foothold.

**Mind-Map**  
A canonical human-facing rendering of a Constellation: nodes laid out spatially, sized by relevance, with provenance glyphs and zoom-into-node interaction. Not part of the Chronik core (clients render Constellations); the server-side response contract that makes Mind-Map clients possible is tracked under PHX-0038.

**Stub Verdict**  
A structured assessment recorded in the `QueryRunReport` indicating whether the assembled Constellation for a query is too thin to be considered a satisfying answer. Combines node count, edge density, vitality, source diversity, confidence aggregate, and named-entity coverage. Crossing the threshold emits a `CuriosityTrigger` (in Gen 2-3); in Gen 1 the verdict is recorded for calibration only.

## Deep Technical Terms

**Source Lake**  
The raw source layer where original materials live: books, webpages, PDFs, OCR scans, transcripts, private documents, and other unprocessed inputs.

**Chronicle Ledger**  
The append-only record of extracted observations, claims, and semantic outputs. It preserves what the system believed, when, from which source, and by which extraction process.

**Event Hypergraph**  
A deeper relational structure in which events and claims can connect more than two elements at once. Useful when simple triples are too weak to capture real-world structure.

**Multi-Embedding Fabric**  
A family of embedding spaces rather than a single vector space. For example: conceptual, temporal, geographic, social-role, causal, scientific-claim, or method spaces.

**Activation Engine**  
The proposed future runtime that spreads query energy through semantic, temporal, spatial, causal, analogical, and epistemic paths to produce an activation field rather than a flat search result list.

**Constellation Compiler**  
The layer that turns raw activation and deep substrate state into an agent-usable Constellation.

## Twins and Personal Context

**Digital Twin**  
A structured model of a person within the Chronik. Depending on the source base, this may be public, private, or inferred.

**Public Twin**  
The model of a person reconstructed from public sources.

**Consensual Private Twin**  
A private, permission-based model of a person inside a Lethe Vault, built from explicitly provided personal data, conversations, context, and memory.

**Shadow Twin**  
An inferred model of a person assembled from incomplete public data. Technically possible, ethically sensitive, and therefore subject to strict limitations.

**Right to Opacity**  
The principle that not everything that can be inferred about a person should be operationalized or exposed.

## Agent and Advisory Terms

**Metis**  
The proposed advisory agent of the Chronik. Metis is a situational wisdom agent that organizes facts, analogies, options, risks, and value assumptions across Akasha, Lethe, and Norm Space.

**Norm Space**  
The explicit layer of goals, rules, prohibitions, obligations, values, preferences, and risk tolerances used in advisory reasoning.

**Counsel Packet**  
A structured advisory output proposed for Metis. It separates framing, facts, analogies, options, risks, unresolved questions, value assumptions, and recommendation.

## Agent Architecture Terms

**Agent Class**
The stable identity of a Pantheon agent: its purpose, boundaries, rights, tools, and escalation rules. Equivalent to the functional core of a gene.

**Prompt Genome**
A family of prompt profiles for different sub-roles within an agent class. Not one prompt per agent, but a coordinated set of variants for different tasks and contexts.

**Promotor**
The regulatory layer that controls an agent class's expression: when it is activated, how many instances run, at what priority, with what budget, and in response to which signals. The class stays constant; the promotor governs how strongly it is expressed. Managed by Helios.

**Agent Instance**
The running unit assembled at task time from a class, a prompt profile, a task packet, a context, and a resource budget.

**Task Ledger**
The structured record of pending, active, and completed agent tasks. Combined with a priority queue and event bus to route work across the Pantheon.

**Hestia**
The human flourishing guardian. Monitors the Chronik's development for dehumanizing drift, files Phoenix Backlog tickets, triggers escalations, and serves as a regulatory dial: when raised by Helios, more Hestia expression means stronger protection of human-centric values.

## Core Pantheon Agents

**Zeus**  
The orchestrator. Routes queries, coordinates agents, and manages system-level execution.

**Argus**  
The world crawler. Searches for and acquires new public knowledge sources.

**Jason**  
The bulk ingestor. Handles large corpora, uploads, and structured source acquisition at scale.

**Iris**  
The contact agent. Accepts and mediates human-provided information and feedback.

**Prometheus**  
The gap explorer. Identifies missing, weak, stale, or underconnected knowledge.

**Morpheus**  
The dreamer. Associates, infers, and weaves new connections inside Oneiros.

**Athene**  
The verifier. Evaluates claims, evidence, contradictions, and confidence.

**Chronos**  
The recycler. Manages decay, compression, archival logic, and graceful forgetting.

**Hades**  
The privacy guardian. Enforces isolation and access control around Lethe Vaults and sensitive knowledge.

**Helios**  
The architect. Optimizes strategy, tunes system behavior, and guides long-range evolution.

## Future or Specialized Agents

**Kalypso**  
A future agent role focused on capturing especially interesting discoveries or emergent insights.

**Poseidon**  
A future agent role focused on synthesizing larger narrative or article-like outputs from crystallized knowledge.

**Hermes**  
A future bridging role for translation, mediation, and cross-domain or cross-language movement of knowledge.

## Builder Agents

Builder agents are not part of the Pantheon. They are mortal craftsmen — they build the substrate the gods inhabit, but do not live within it. Their prompts live in [`prompts/`](../prompts/) and are versioned like constitutional text.

**Hesiod**  
The first builder. Helps articulate vision, write documentation, and shape the conceptual foundation of Theogony. Named after the Greek poet who composed the original Theogony — the one who put the birth of the gods into words.

**Daedalus**  
The architect. Designs the concrete implementation of the system from the existing vision. Operates under strict YAGNI and Advocate/Skeptic/Counterview discipline. Prompt: [`prompts/daedalus.md`](../prompts/daedalus.md).

**Talos**  
The implementer. Daedalus's apprentice and successor — the craftsman who turns the architect's plan into running code, with green tests and honest RunReports. Does not redesign the architecture; escalates contradictions instead. Works on feature branches, commits atomically, and reports failures with the same candor as successes. Prompt: [`prompts/talos.md`](../prompts/talos.md).

## Domain Directions

**World Knowledge**  
The Chronik's role as a distilled, navigable memory of global public knowledge.

**Scientific Workbench**  
The Chronik's role as an active meta-research substrate: comparing claims, exposing contradictions, identifying gaps, and supporting the production of new scientific knowledge.

**Operative Knowledge**  
The fifth knowledge form: knowledge that runs the world rather than describes it. Schedules, logistics, machine control, supply forecasts, maintenance protocols. Unlike descriptive knowledge, operative knowledge is enacted in continuous plan-execute-document-learn cycles. Long-horizon dimension; not part of Generation 1 or 2. See [`OPERATIVE_KNOWLEDGE.md`](OPERATIVE_KNOWLEDGE.md).

**Operative Agents**  
A future class of agents (e.g. Atlas, Hephaistos, Demeter) that act on the world rather than only on knowledge. Subject to the same provenance, audit, and Hestia oversight as knowledge agents.
