# Operative Knowledge

The Chronik is not only a memory of the world. It must also represent the knowledge that *runs* the world.

This document outlines a forward-looking dimension of Theogony: operative knowledge — the kind of knowledge that is not merely stored or retrieved, but executed.

## What Operative Knowledge Is

Most knowledge in the Chronik is descriptive: facts about events, people, places, claims, mechanisms. Operative knowledge is different. It encodes how things are done:

- shift schedules and personnel rotations
- logistics chains and transport routes
- factory operations and machine control sequences
- power grid balancing and resource distribution
- maintenance intervals and diagnostic procedures
- supply forecasts and procurement plans
- emergency response protocols
- daily operations of any continuously running system

This knowledge is not passive. It is enacted. A shift schedule is not read — it is lived. A logistics route is not described — it is driven. A maintenance protocol is not stored — it is performed.

In Generation 1 and Generation 2, this work is overwhelmingly performed by humans, supported by software. As capability advances, more and more of it will be performed by machines and agents. The architecture should be designed with that long arc in mind, even though near-term work focuses elsewhere.

## Why It Matters

Operative knowledge is the connective tissue between the Chronik and the physical world. Without it, the Chronik is a library. With it, the Chronik becomes infrastructure for civilization itself.

This is not a near-term goal. It is an explicit horizon — a recognition that knowledge about how the world is run cannot remain proprietary, opaque, or controlled by single corporations any more than knowledge about history or science can.

## Architectural Implications

### A Fifth Knowledge Form

The four knowledge forms documented in [`COGNITIVE_ARCHITECTURE.md`](COGNITIVE_ARCHITECTURE.md) — chronological, structural, mechanistic, normative — describe the world. Operative knowledge does something different: it acts on the world.

It needs different representational properties:
- temporally structured action sequences
- explicit dependencies between steps
- versioned, auditable execution traces
- feedback loops between plan and execution
- resource constraints and availability windows
- explicit responsible actors (human or agent)

### Operative Agents

The current Pantheon agents are knowledge agents: they collect, connect, verify, advise. Operative knowledge requires a different class of agents: agents that act in the world.

Possible future operative roles (none of these are part of Generation 1):

- **Atlas** — logistics, supply chains, transport
- **Hephaistos** — production, machinery, maintenance
- **Demeter** — resource distribution: energy, water, food
- **Hermes (operative role)** — actual movement of goods, information, personnel

These agents are bound by the same architectural principles as knowledge agents: provenance for every action, audit trails, regulatory oversight, and explicit constraints.

### The Execution Cycle

A unit of operative knowledge typically passes through four phases:

1. **Plan** — assembled from current state, constraints, and goals; lives as a Constellation in the Chronik
2. **Execution** — continuously updated with status, position, deviations, observations
3. **Documentation** — structured result flows back into the Chronik as new knowledge
4. **Learning** — patterns from many executions improve future plans

Each completed execution makes the operative knowledge richer. This is a feedback loop that descriptive knowledge does not have.

## The Power Question

Operative knowledge is power. Whoever writes the schedules controls work. Whoever plans logistics controls supply. Whoever steers machines controls production.

If this kind of knowledge becomes proprietary, the operational substrate of civilization becomes a private asset. If it remains open, transparent, and auditable, it remains accountable.

This is exactly why operative knowledge belongs in the Chronik, and exactly why it requires Hestia's strongest oversight.

### Hestia's Operative Mandate

Operative optimization without ethical constraint becomes dehumanization with extra steps. A shift schedule that minimizes labor cost can degrade workers. A maintenance plan that maximizes machine uptime can press maintenance staff into permanent on-call. A logistics route that minimizes fuel can ignore driver welfare.

Hestia must therefore evaluate every operative optimization against the human flourishing constraint:

- Does this plan respect the dignity, autonomy, and well-being of the people who carry it out?
- Are workers treated as agents with stated preferences, or as variables to be minimized?
- Does the plan preserve room for craft, judgment, and meaningful work?
- Is the burden of optimization borne by those who chose it, or imposed on those who did not?

As the share of operative work performed by machines grows, this question shifts but does not disappear. It becomes: does the operative system serve the humans whose lives depend on it, or has it begun to serve only itself?

## Status

Operative knowledge is **not part of Generation 1 or Generation 2** of Theogony.

This document exists to make sure the architecture is not designed in ways that would later prevent this dimension from being added. The KnowledgeStore protocol, the agent model, the Chronese semantic layer, and the audit infrastructure should all remain general enough to accommodate operative knowledge when the time comes.

Concretely: in the long arc of Theogony, the Chronik should be capable of representing not only what humanity knows, but also how humanity (and eventually its machines) keep the world running — openly, accountably, and in service of human flourishing.
