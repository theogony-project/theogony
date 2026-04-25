# Strategy-Game Analogy

**Status:** canonical product/interaction analogy, not a literal architecture.
**Companion docs:** [`VISION.md`](VISION.md), [`PANTHEON_VISION.md`](PANTHEON_VISION.md), [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md).
**Audience:** anyone designing Cockpit, worker orchestration, agent autonomy, resource controls, or demos.

## The Analogy

Theogony should feel, at the operator layer, a little like an Aufbau-strategy game:

- **The Chronik is the map.** It is the world, the terrain, the resource landscape, the contested territory, and the memory of what happened there.
- **Pantheon agents are workers.** They are autonomous units with roles, costs, capacities, and work preferences. The operator does not micromanage every action; they allocate attention and resources.
- **The Cockpit is the strategy interface.** It should show what exists, what is missing, which regions are active, which agents are idle or busy, and what the operator can start with the current budget.
- **Markers are job signals.** Gaps, weak regions, unresolved findings, stale pool entries, contradictions, failed ingests, high-value query regions, and Mnemosyne proposals are the "things on the map" that workers can discover and act on.

This is an analogy for comprehension and control. It is **not** a mandate to implement game mechanics, a simulation engine, or artificial UI flavor.

## Useful Role Metaphors

The metaphor is useful because many Pantheon roles already behave like strategy-game unit classes:

- **Miners** gather raw material: Argus searches, fetches, and acquires source material where attention revealed a gap.
- **Factories** transform raw material: ingestion, extraction, relation-building, clustering, and Oneiros phases turn sources into structured knowledge.
- **Scouts** explore unknown territory: curiosity and research planning probe thin regions of the graph.
- **Towers** watch and defend: Athene, Nemesis, and Eris observe, sample, audit, and red-team.
- **Recyclers** clear and repair: Chronos resolves or demotes damaged knowledge without pretending it never existed.
- **Planners** improve the base: Mnemosyne observes system-wide signals, defines metrics, proposes experiments, and drafts Phoenix work.

These names are mental handles. The canonical agent names remain mythological unless a future product layer deliberately adds game-style labels.

## Resource Allocation

A good Cockpit should eventually make resource tradeoffs visible:

- How many workers of each type are running?
- What are they spending: tokens, wall-clock time, API calls, memory, graph writes, operator attention?
- Which map regions are underserved?
- Which jobs are queued, stale, blocked, risky, or complete?
- Which worker type would be most useful next?

The operator should be able to say, in effect:

> I have limited resources. Start two research workers, one verifier, and one recycler. Let them find appropriate work from the map.

Behind that simple gesture, actual agents use structured markers and reports, not hidden magic.

## Markers Before Micromanagement

The system should prefer **marker-driven autonomy** over command-by-command control.

Workers need surfaces they can independently scan:

- verification-pool entries
- `Finding` nodes
- failed or partial run reports
- blind-spot clusters
- weak query regions
- contradiction edges
- stale high-vitality nodes
- backlog proposal drafts
- cost or latency anomalies

The operator starts or budgets worker classes. The workers find work by reading the map.

This preserves the immune-system doctrine: agent work is asynchronous, parallel, post-hoc, and sampled. New knowledge should not synchronously summon every worker.

## Cockpit Direction

The Cockpit should evolve toward a strategy-map overview:

- a map/status view of the Chronik's active regions
- worker cards showing idle/running/blocked states
- resource budgets and spend
- launch controls for worker classes
- queues and markers grouped by meaning
- clear "what happens next" affordances

The goal is not gamification for its own sake. The goal is operator legibility: a complex autonomous organism becomes understandable when it is shown as a living map with workers, resources, signals, and consequences.

## Relationship to Classical Databases

The Chronik is not meant to swallow every kind of data.

For example, a hotel-booking application may keep booking records, availability, payments, and transactional constraints in a relational database. The Chronik may hold semantic memory: hotel concepts, room styles, preferences, past satisfaction, similarity embeddings, provenance of reviews, and taste patterns.

Pantheon agents can combine both:

- query relational data for availability and price
- query the Chronik for semantic fit and preference similarity
- explain the recommendation through provenance and remembered taste

The hotel example is not strategically important. It simply clarifies the boundary: the Chronik is the semantic world model; other databases may remain the right home for transactional facts.

## Non-Goals

- Do not turn Theogony into a literal game.
- Do not rename core architecture around miners/towers/factories.
- Do not hide real agent complexity behind cute labels.
- Do not add fake resource scarcity where real budgets already exist.
- Do not make worker launch synchronous with ingest.

The analogy should make the system easier to operate, not less honest.
