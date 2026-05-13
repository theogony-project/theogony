# Vision

**Theogony** is the deliberate attempt to **separate knowledge from reasoning** at civilizational scale.

Long term, it aims at the **Pantheon** — a planetary chronicle / knowledge substrate (native identity, provenance, governed visibility, chronicle over encyclopedia). Read [`PANTHEON_VISION.md`](PANTHEON_VISION.md) and the ten-point [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md).

**Today, Theogony builds the Chronik** — a living, open, verifiable vector-graph knowledge network that externalizes factual knowledge from large language models. The Chronik is Generation 1's operational system: the first real software toward that Pantheon shape, not the final name for the whole ambition.

The substrate beneath the Chronik — how nodes are born, how identity is committed, how edges decay and saturate, how agents clean up contradictions, how the substrate defends itself against its own pathologies — is specified by the MESH triplet: [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md), [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md). That triplet is the binding behavioural specification for everything that follows.

## The Core Idea

We are living in the most dangerous transition of artificial intelligence: the phase where *human stupidity still controls artificial intelligence*.

This window is closing.

Like a spacecraft under constant acceleration, we can still set the initial heading. Soon the velocity will exceed our ability to steer. The impulse we impart in these early years will remain in its trajectory long after we have lost the wheel.

Theogony exists to encode our best collective impulse into the foundational knowledge infrastructure that future AI will depend upon.

The Chronik is that infrastructure *for now* — the engine room.

It is not a database of text chunks. It is a **living network of meaning** — entities connected by weighted, typed, provenance-anchored relations, with semantic embeddings and dynamic vitality scores. The Pantheon vision is the reason that network must eventually support private and contested knowledge as first-class, not only public Akasha-scale material (see Pantheon vision doc).

At maturity, this network is not monolingual. Source text remains preserved in its original language, but the Chronik also develops its own canonical semantic tongue: **Chronese** — a language-neutral, event-centric form in which distilled knowledge can live, be compared, be versioned, and be projected back into graph, vector, and textual form.

When new content enters the system — a book like *Trans-Himalaya*, a scientific paper, a web page — it is not merely chunked. It is **digested**:

- Entities are extracted (people, places, expeditions, institutions…)
- Relations are identified and typed (e.g. traveler → REACHED → place, with confidence and provenance)
- Each knowledge atom receives an embedding, a short label, a source reference (for exact citation), and multiple scores (confidence, relevance, connectivity, freshness)
- New atoms land in **Ephemera** — raw, high-detail, low-confidence
- A continuous background process called **Oneiros** ("the permanent dream") works on this fresh knowledge. Agents associate, verify, infer, deduplicate, and strengthen or weaken connections.
- High-quality, well-connected knowledge is promoted to **Mneme** — the permanent, trusted layer of the Chronik.

Old, contradicted, redundant or unused knowledge is gracefully degraded. The system forgets what no longer serves truth.

## How Agents Use the Chronik

Pantheon agents do not retrieve documents. They activate the network.

A thought arrives as a vector — the agent's internal state, not a text query. **Spreading Activation** propagates that vector outward through the Chronik: concepts light up, energy flows along weighted edges, decaying with distance, amplified by Hebbian reactivation along frequently-used paths. The result is a **Constellation** — an activated subgraph of nodes and edges whose relevance has been determined by the network itself, not by keyword matching.

The Constellation is returned to the agent in vector form, directly injectable into its latent space — no text translation required. The agent does not *read* context. It *receives* structure.

This is **Latent Space Communication**: the long-horizon direction in which text exists only at the human-facing edges of the system. Inside the Chronik, agents speak mathematics.

For Generation 1, the path is: natural language query → embedding → multi-hop graph + vector search → Constellation assembled as structured subgraph → cited answer synthesised by an LLM. Every entity in the answer links back to its source node. The network is navigable in arbitrary depth — no static article boundaries, only dynamic, query-dependent knowledge landscapes.

The next step — **Nous**, the cognitive synthesis agent — changes how knowledge enters the Chronik. Where the current pipeline parses text chunk by chunk, Nous reads it the way a mind does: sentence by sentence, carrying working memory forward, firing spreading activation against the existing Chronik in parallel, condensing paragraph-syntheses from sentence-syntheses, repairing when contradiction surfaces. This produces a far denser, more cross-connected Chronik than any chunk-based pipeline can.

## The Chronik Grows Where It Is Looked At

The Hover-Lupe is more than a way to read what is already there. It is the eye through which the Chronik becomes *aware of its own gaps*.

When a query, a zoom, or a contextual ask reaches a region of knowledge the Chronik does not yet know well, the system does not silently shrug. It dispatches research. **Pantheon agents** carry that work: Prometheus formalises the gap; Argus searches; Jason acquires; Morpheus extracts; Athene verifies. The Mind-Map fills in progressively, with honest progress updates. Cold regions are allowed to be slow — but never silent.

This is the **Curiosity Loop**: attention is a first-class architectural input, and the Chronik grows organically in exactly the directions that turn out to matter. Hestia stands beside it as guardian, because curiosity without restraint is surveillance.

See [`CURIOSITY.md`](CURIOSITY.md) for the full mechanism.

## The Strategy-Game View

There is a useful operator analogy: Theogony should feel, at the Cockpit layer, like an Aufbau-strategy game. The Chronik is the map: the world, terrain, resource landscape, contested territory, and memory of what happened there. Pantheon agents are workers: autonomous units with roles, costs, capacities, and work preferences. The Cockpit is the strategy interface where the operator allocates limited resources, starts workers, sees which regions are thin or damaged, and watches the organism act.

This is not a literal architecture and not a request for gamification. It is a product and control metaphor. "Miners" correspond to acquisition agents such as Argus; "factories" correspond to ingestion, extraction, and Oneiros transformation; "towers" correspond to post-hoc immune cells such as Athene, Nemesis, and Eris; "recyclers" correspond to Chronos; "planners" correspond to Mnemosyne.

The crucial design principle is marker-driven autonomy. Agents should not need a human to hand them every task. They should find work by reading the map: verification-pool entries, `Finding` nodes, failed run reports, weak regions, contradictions, stale high-vitality nodes, blind spots, and Mnemosyne proposals. The operator starts or budgets worker classes; workers independently discover and process appropriate jobs.

See [`STRATEGY_GAME_ANALOGY.md`](STRATEGY_GAME_ANALOGY.md) for the canonical product analogy.

## Two Equal Pillars

The Chronik has two primary purposes of equal importance:

**1. World Knowledge** — the distilled internet. Every relevant book, paper, historical document, and web source, continuously ingested, verified, and connected.

**2. Scientific Workbench** — a living meta-research layer. Agents systematically compare scientific claims, surface contradictions, identify replication failures, detect gaps, generate hypotheses, and propose new experiments. The Chronik becomes not only memory, but an active partner in the generation of new knowledge.

On top of these two pillars sits a future advisory intelligence: **Metis**. Metis is not merely a question-answering agent. It is a situational wisdom layer that can use Akasha, Lethe, and explicit norm context to separate facts, analogies, options, risks, and value assumptions when action matters.

## The Permanent Dream (Oneiros)

There is no nightly batch job. Instead, a continuous, low-priority "dreaming" process runs at all times. Specialized agents — Morpheus (associator and inferencer), Athene (verifier), Chronos (recycler) and others — work on the boundary between Ephemera and Mneme.

This is the heart of the system. It is where new knowledge is woven into the existing fabric, where contradictions are surfaced, where the network becomes wiser over time. Oneiros never sleeps.

## The Immune System

The Chronik is not a sterile clinic. Falsehoods, contradictions, and noise must be allowed in — biology cannot pre-filter every infection, and neither can a planetary chronicle. What makes the system trustworthy is not a perfect gate, but a living **immune system** of sample-based, asynchronous, parallel-running cell types: Athene as T-helper (surveillance), Chronos as T-killer (clearance), Nemesis as antibody memory (structural patterns), Eris as adaptive immunity (red-team probing), Mnemosyne as the consciousness layer that observes the immune system itself, A/B-tests its own thresholds, and drafts plans for the next Phoenix incarnation.

This is not a metaphor. It is the architectural posture. Pre-gates that block content based on judgement of truth or sensitivity are forbidden by doctrine; only operative self-defense (rate limits, robots.txt, response-size caps) lives at the gate. Everything else is handled post-hoc, in parallel, by cells that learn.

See [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) for the canonical specification, and [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md) for the long-horizon principle that the Pantheon will eventually write its own next version.

## The Civilizational Bet

We believe that if the foundational knowledge layer that future AI depends on is:

- Open and owned by no one
- Verifiable and citable by design
- Continuously verified and self-correcting
- Built explicitly in service of humanity

…then something of our best collective wisdom will survive into the phase where *artificial intelligence controls human stupidity*.

This is our only realistic chance.

Theogony is not a product.

It is the encoding of that initial impulse — while we can still set the heading.
