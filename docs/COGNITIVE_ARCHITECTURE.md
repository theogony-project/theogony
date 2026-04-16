# Cognitive Architecture

The Chronik is not only a memory store. It should also embody a model of cognition.

This document outlines the cognitive principles that guide how the system thinks, not only what it remembers.

## Fast and Slow Thinking

Following Kahneman: the Chronik should support two modes of reasoning.

### Fast Path (System 1)

- vector similarity
- graph activation
- heuristic retrieval
- quick constellation assembly
- low latency, low cost

Appropriate for: navigation, orientation, everyday queries, browsing.

### Slow Path (System 2)

- deliberate reasoning loops
- opposing evidence retrieval
- source evaluation
- uncertainty quantification
- advisory structure (Metis)

Appropriate for: politics, science, strategy, personal decisions, sensitive claims, conflict.

### The Rule

Fast thinking may never be the only voice when the situation is serious.

The system should detect when slow thinking is required and escalate automatically, or when an agent or user explicitly requests depth.

## The Opposition Principle

Humans have developed powerful strategies against their own cognitive biases. They rarely use them. The Chronik should use them by default.

### 1. Advocate

Build the strongest supporting interpretation of a claim or position.

### 2. Skeptic

Surface contradictions, gaps, biases, weak evidence, and unstated assumptions.

### 3. Counterview

Formulate the strongest honest case for the opposing position. Not a caricature. Not a token gesture. A genuine attempt to understand what the other side would say at its best.

### The Rule

For any claim that enters the Slow Path, the system should attempt all three roles before compiling a Constellation or Counsel Packet.

This is not relativism. It is epistemic hygiene.

## Knowledge Beyond Chronology

Not all knowledge is anchored to time, place, person, or event.

The Chronik must represent at least four fundamental knowledge forms:

### 1. Chronological Knowledge

History, biographies, events, political developments, timelines.

Naturally organized by time, place, and actors.

### 2. Structural Knowledge

Mathematics, logic, physics, formal systems, taxonomies, ontologies.

Organized by definitions, axioms, dependencies, and derivations. Time-independent.

### 3. Mechanistic Knowledge

How things work. Causality. Biology, engineering, medicine, chemistry.

Organized by processes, inputs, outputs, feedback loops, and models.

### 4. Normative Knowledge

Law, ethics, values, goals, rules, obligations, prohibitions.

Organized by scope, jurisdiction, hierarchy, and conflict resolution.

The Chronik must not force all knowledge into a single temporal narrative. These forms require different clustering strategies, different embedding spaces, and different retrieval modes.

## Implications for Design

- The Activation Engine should support both fast and slow propagation modes.
- Constellations should carry a marker indicating whether they were assembled via fast or slow path.
- Metis should always use the slow path.
- Chronese assertion frames should carry a `knowledge_form` field.
- The Multi-Embedding Fabric should include spaces optimized for structural and mechanistic knowledge, not only for narrative and temporal proximity.
- The Advocate/Skeptic/Counterview triad should be implementable as agent roles or as prompting strategies within existing agents.
