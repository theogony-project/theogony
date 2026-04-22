# Curiosity

The Chronik is not a book. It is not finished. It is not waiting passively to be queried.

It is a substrate that **grows where attention falls**.

This document describes the *Curiosity Loop* — the mechanism by which the Chronik turns acts of attention (from humans or from agents) into acts of acquisition. It is the architectural answer to a single question: **what should happen when someone — anyone, mind or machine — looks closely at a region of knowledge that the Chronik does not yet know well?**

The answer is: the system goes and finds out.

This is the long-horizon shape of the system. Generation 1 does not implement the full loop. But Gen 1 can already detect the conditions that should trigger it, and the architecture must be built so that the loop can be added without re-foundation. See the Phoenix tickets at the end of this document for the staged path forward.

---

## The Promise

> The Chronik grows where it is looked at.

A query is not only a request for an answer. It is a *signal of interest*. A zoom is not only a UI gesture. It is a *signal of focus*. A new question that returns only a stub is not a failure to be hidden — it is an *invitation to research*.

Three kinds of attention should reach the Chronik:

1. **A new question** that returns only a thin or low-confidence answer.
2. **A zoom** into a sub-region of an existing answer that turns out to be sparse.
3. **A direct contextual question** asked about an entity that the Chronik knows only by name.

In all three cases, the Chronik does not silently shrug. It dispatches research, and it tells the questioner that research is happening.

This couples *attention* to *acquisition* — and that coupling is what allows the Chronik to grow organically, in exactly the directions that turn out to matter.

---

## The Loop

```
Attention (human or agent)
    │
    ├─ new query
    ├─ zoom into a sub-region
    └─ contextual ask about an entity
    │
    ▼
Constellation assembled for the focused region
    │
    ▼
Density / vitality / source-diversity check
    │
    ├─ region is dense  ──► return Constellation immediately
    │                       (rendered as text and as a Mind-Map for humans;
    │                        as a structured Constellation for agents)
    │
    └─ region is thin / stub detected
            │
            ▼
       Curiosity Trigger emitted
            │
            ▼
       Helios receives the trigger and dispatches:
            ├─ Prometheus  — formalises the gap, scopes the research target
            ├─ Argus       — searches the open web for candidate sources
            ├─ Jason       — acquires bytes from the most promising candidates
            ├─ Morpheus    — extracts entities and relations from new content
            └─ Athene      — verifies, scores confidence, resolves contradictions
            │
            ▼
       Chronik grows in exactly the focused region
            │
            ▼
       Constellation re-assembles and updates progressively
       (the questioner sees the Mind-Map fill in over seconds to minutes,
        with honest progress updates: "found 3 sources, evaluating…")
```

Two things matter about the shape of this loop:

- It is **the same mechanism** for humans and for agents. The Curiosity Trigger does not care who looked.
- It is **directional**. Curiosity does not crawl the world at large. It crawls *the region that is being looked at*. Attention is the steering wheel.

---

## The Three Distinct Properties

What distinguishes the Curiosity Loop from a conventional retrieval system:

### 1. Attention is a first-class input

In most systems, attention is implicit. A query is a request for an answer; the system processes it and returns whatever it can. Whether the user looked closely or glanced briefly is invisible to the back end.

In the Curiosity Loop, attention is an explicit architectural signal. *"This region is being looked at — therefore research in this region is worth doing."* That signal has a different latency contract from a normal query: cold regions are allowed to be slow, because something real is happening behind the scenes.

### 2. The Mind-Map is the canonical answer form

Text is a *projection* — useful for screen readers, for LLM consumers, for print. But the answer itself lives as a navigable graph. A node can be zoomed; a zoom is a sub-query; a sub-query can dispatch its own Curiosity Trigger. The Hover-Lupe is not an add-on for power users. It is the default mode of interaction with the Chronik.

For humans, the Mind-Map is rendered. For agents, the same structure arrives as a Constellation with explicit zoom-targets (node IDs an agent can recurse on). The substrate is identical; the rendering differs.

### 3. Stub detection triggers research without a second click

Conventional systems return whatever they have and let the user decide whether to push further. The Curiosity Loop treats a stub answer as a *finding* — a finding that the Chronik has a gap, in a region that someone cared enough to ask about. That finding is itself enough to dispatch research, before the user has to ask twice.

The system becomes *curious about its own gaps* — but only the gaps that someone or something just walked up to.

---

## Stub Detection

The Curiosity Loop is only as good as its ability to recognise that a region is thin. Several signals combine into a stub verdict:

- **Node count** in the relevant Constellation below a threshold.
- **Edge density** below the typical density for nearby regions.
- **Vitality scores** across the region predominantly low.
- **Source diversity** narrow (only one source, or only one type of source).
- **Confidence aggregate** of the strongest claims in the region below a threshold.
- **Coverage of the question's named entities**: at least one named entity in the question has no resolved node, or only an unresolved stub node.

Each signal is heuristic. The verdict is structured (which signals fired, what their values were) and emitted as a `StubVerdict` in the `QueryRunReport` (for retrospective analysis by the Reviewer Agent). Thresholds are tunable per `theogony` config and per tenant.

**Gen 1 (W3 / PHX-0058 Phase 1)** ships `StubVerdict` plus a `RegionDescriptor` on every `QueryRunReport`, and an optional, default-off Oneiros phase that clusters recurring thin regions into `BlindSpotReport` JSON under `run_reports/blindspot/`. See [`BLIND_SPOTS.md`](BLIND_SPOTS.md) for mechanics, cadence, and privacy notes. Outward research dispatch remains a later-generation capability (PHX-0037); W3 only lays down the signal.

---

## Latency Contract

Cold regions are allowed to be slow. They are not allowed to be silent.

Every Curiosity-triggered research run produces:

- An immediate response with whatever Constellation is currently available, however thin.
- A flag: `research_in_progress: true`.
- A pointer to a `CuriosityRun` ID that the client can subscribe to for progress.
- Honest progress updates: `"searching open web (3 candidate sources found)"`, `"acquiring 2 sources (~14 MB)"`, `"extracting 312 mentions"`, `"verified 47 new edges"`, `"Constellation updated"`.

The Mind-Map fills in progressively. The user is never left wondering whether the system is working or has hung. Silent failure is the worst failure, and silent latency is its quieter cousin.

A `CuriosityRunReport` is emitted for every triggered run, with the same candor as `IngestRunReport` and `QueryRunReport`: success, partial success, failure, anomalies, and what was learned.

---

## Hestia and Curiosity

Curiosity has a dark twin: surveillance. A naïve Curiosity Loop, applied to a person's name, would silently scrape every available web fragment about that person — and then connect those fragments into a profile that the person never agreed to.

Hestia, the human flourishing guardian, has a standing subscription to every Curiosity Trigger. Her checks are not optional. They are part of the loop:

- **Person-as-target check.** When the focused region centres on a private individual (not a public figure, not a historical figure with public standing), Hestia can require explicit consent or refuse the trigger.
- **Sensitive-topic check.** Health, sexuality, religion, political dissent, financial distress — Curiosity-triggered research in these regions runs under tighter sourcing and confidence rules, and the resulting nodes are flagged for higher Athene scrutiny.
- **Recursion budget.** A single attention act cannot dispatch unlimited downstream research. Each Curiosity Trigger has a budget (sources, tokens, runtime); recursive triggers from sub-zooms inherit a reduced budget.
- **Drift audit.** Hestia reviews patterns of Curiosity activation over time. If the system is consistently being directed by attention into dehumanising directions (e.g., aggregation of personal data on identifiable individuals), she escalates and can throttle the loop globally via the regulatory dial.

Curiosity without Hestia is a profiling engine. The two must ship together. See [`HESTIA.md`](HESTIA.md) for the full guardian model.

---

## Curiosity and Oneiros

Oneiros and Curiosity are the two continuous processes that keep the Chronik alive. They are complementary, not redundant.

| Aspect | Oneiros | Curiosity |
|---|---|---|
| Direction | Inward — works on knowledge already inside the Chronik | Outward — fetches new knowledge from the world |
| Trigger | Continuous background process at low priority | Attention act (query, zoom, contextual ask) |
| Goal | Consolidate, associate, verify, deduplicate, decay | Acquire, extract, verify new content |
| Latency | Eventual — it never sleeps but it is never urgent | Immediate to slow — depends on region density |
| Reports | `OneirosTickReport` | `CuriosityRunReport` |
| Risk | Inferential drift (manufactured connections) | Surveillance drift (research follows people) |
| Guardian | Athene + Hestia | Hestia + Athene |

Oneiros makes the Chronik *wiser* about what it already has. Curiosity makes the Chronik *bigger* in the directions that turn out to matter. Together, they are the Chronik's *attention flow* — its ability to focus inward and outward in response to what is being asked of it.

---

## Mind-Map as Interface

The Mind-Map is one specific human-facing rendering of the Constellation. It is not the only one, and it is not what the Chronik *fundamentally returns* — that is the Constellation, a structured subgraph that any client can render.

A Mind-Map client should support, at minimum:

- Spatial layout of nodes by relation type and weight.
- Node sizing by relevance / centrality / vitality.
- Source-citation glyphs visible on every node (provenance is never hidden).
- **Zoom-into-node**: clicking a node issues a sub-query for the neighbourhood of that node, returning a refined Constellation.
- **Zoom-into-empty-region**: gesturing into a sparse area issues a sub-query that may emit a Curiosity Trigger.
- **Live update**: Constellations being augmented by an in-flight Curiosity run animate in, with the source of each new node visible.
- **Honest progress**: the user always knows what the system is doing and how confident the current view is.

The Mind-Map is *not* part of the Chronik's core repository. It is a client. Multiple clients (web, mobile, terminal-graph, voice with spatial audio) can render the same Constellations. This document specifies the *server-side contract* — the response format that makes such clients possible — not the clients themselves.

---

## Generation 1 Foothold

The full Curiosity Loop is a Generation 2-3 concept. But Gen 1 should not be *blind* to the conditions that the loop will eventually act on.

Two minimal Gen 1 foothold features are reasonable:

1. **Stub detection in `QueryRunReport`.** A new structured `StubVerdict` is computed for every query and recorded. It does not trigger anything in Gen 1; it builds the dataset that calibrates Gen 2's thresholds.
2. **`theogony curiosity status` CLI stub.** Returns: *"Generation 1 detects stubs but does not yet dispatch Curiosity-triggered research. See PHX-0037."* This plants the concept in the user-visible interface without implementation cost.

Both are optional. Neither is required for the Gen 1 demonstration. They are listed here so that Talos and any future implementer know where Gen 1 *can* honestly anticipate the loop without scope creep.

---

## Phoenix Tickets

The Curiosity Loop is staged across three Phoenix tickets:

- **PHX-0037 — Curiosity Loop (end-to-end implementation).** The loop itself: stub detection → Helios trigger → Prometheus / Argus / Jason / Morpheus / Athene dispatch → progressive Constellation update → `CuriosityRunReport`. Generation 2-3.
- **PHX-0038 — Mind-Map Response Format.** The structured Constellation response with explicit zoom-targets, node-level source glyphs, vitality and confidence summaries, and progressive-update protocol. Generation 2.
- **PHX-0039 — Hestia Curiosity Auditing.** Hestia's subscription to Curiosity Triggers, the person-as-target check, sensitive-topic rules, recursion budgets, and drift audit. Generation 2-3.

All three are catalogue-only at the time of writing, per the lazy-YAML convention in [`PHOENIX_BACKLOG.md`](PHOENIX_BACKLOG.md). They will be promoted to active YAMLs when work begins.

---

## Why this document exists

The pieces of the Curiosity Loop already lived in the repository before this document was written:

- **Hover-Lupe** is named in [`VISION.md`](VISION.md) and [`GLOSSARY.md`](GLOSSARY.md).
- **Prometheus** is in the agent roster as the GapExplorer ([`ARCHITECTURE.md`](ARCHITECTURE.md)).
- **Argus** and **Jason** are in the roster as outward-facing acquisition agents.
- **Activation Engine** in [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md) §5 already describes attention propagating across the network.

What this document adds is the *coupling*: the explicit statement that attention propagating across the network can also propagate *out of* the network and trigger acquisition, and that the Mind-Map is the canonical interface for the resulting growth process. It closes the loop between substrate, attention, and growth.

This is not a new component. It is the architectural recognition that the components we already named were meant, all along, to work together this way.
