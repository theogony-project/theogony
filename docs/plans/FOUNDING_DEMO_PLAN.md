# Founding Demo Plan — "Theogony reads the Theogony"

**Status:** binding execution plan, approved by the operator 2026-07-14.
**Purpose:** produce the first demo of the MESH substrate that *feels* like the vision — a small, dense, fully Kadmos-read mesh instead of a large seeded skeleton — for less than 100 EUR.
**Ticket:** [PHX-1045](../../phoenix-backlog/PHX-1045.yaml). Prerequisite: [PHX-1042](../../phoenix-backlog/PHX-1042.yaml).
**Relation to [`LIVING_DEMO_PLAN.md`](LIVING_DEMO_PLAN.md):** that plan proved the Gen-1 growth loop. This plan is its MESH-substrate successor: it demonstrates the *substrate* doctrine (activation, contradiction, dream), not the acquisition loop.

## Why this plan exists

Live 100k testing (PHX-1042/1043/1044) established that the current showcase mesh is structurally hollow: `mesh-wiki-100k` was **seeded** from Wikidata5m, not **read** by Kadmos. Its labels are `aliases[0]` noise, its topology is hub-poisoned, and it contains no observations, no descriptions, no contradictions — none of what [`MESH_SUBSTRATE.md`](../MESH_SUBSTRATE.md) specifies. The mesh the doctrine describes exists in code ([`kadmos_v2.py`](../../src/theogony/mesh/ingestion/kadmos_v2.py)) but has only ever run at smoke scale.

Scaling the seed further makes the problem worse. The founding demo therefore inverts the priority: **small, dense, real** — a corpus read end-to-end by Kadmos v2, retrieved by Spreading Activation, consolidated by Oneiros, shown honestly.

## The corpus

Greek mythology from its primary sources — all public domain on Project Gutenberg (~400–500k words total):

| Work | Why it is in the corpus |
|---|---|
| Hesiod, *Theogony* (Evelyn-White tr.) | The project's namesake. The founding act: the chronicle's first read is its own name. |
| Apollodorus, *The Library* (Frazer tr.) | Systematic mythography — dense entity overlap with Hesiod, independent lineages. |
| Ovid, *Metamorphoses* (More tr.) | Third independent tradition; narrative (not systematic) framing of the same entities. |
| Homeric Hymns (Evelyn-White tr.) — optional | Fourth source for bridge-density if budget allows. |

Gutenberg IDs are resolved and pinned by the corpus script (step F2) and **verified against Gutendex metadata at fetch time** — a title mismatch is a structured failure, not a silent ingest.

Why this corpus: (1) the same gods appear across sources that never cite each other, so consolidation and bridge nodes arise naturally; (2) it contains famous *genuine* contradictions (Aphrodite's parentage: sea-foam of Uranus in Hesiod vs. daughter of Zeus and Dione in the Homeric tradition), so contradiction-as-first-class can be shown, not asserted; (3) Zeus is a natural hub, which forces the PHX-1042 fix to be validated on honest data.

## The demonstration moment

One ~3-minute recording, three beats. Every beat maps to a run report — no staged magic.

```text
BEAT 1 — Activation, not retrieval (~60s)
00:00  Cockpit Mesh Explorer open on the founding mesh.
00:05  Query about a mythological figure.
00:10  The constellation lights up hop by hop (animated SpMV iterations,
       streamed over the existing SSE channel). Every node shows a real
       name, a Kadmos description, and source anchors from up to three
       independent books.

BEAT 2 — Contradiction is first-class (~60s)
01:00  Query: "Who are Aphrodite's parents?"
01:10  TWO activated subgraphs appear, joined by a `contradicts` edge.
       Each is anchored to its source (Hesiod vs. the Homeric tradition).
       Neither is flattened. The provenance panel shows both anchors.

BEAT 3 — The permanent dream (~60s)
02:00  Operator triggers an Oneiros tick live.
02:20  Edge count before/after; one concrete new connection that stood in
       no single source text; the OneirosTickReport on screen.
02:50  "The chronicle grew wiser without reading new text."
```

## What it proves / what it does NOT prove

Proves: Kadmos v2 produces a dense, real mesh from primary sources at full-book scale; Spreading Activation over that mesh returns provenance-anchored constellations; contradictions survive as first-class structure; Oneiros densifies without new input.

Does **not** prove: the MNLM bet (emergent inference exceeding source texts — PHX-1035, blocked on compute, deliberately out of scope); federation; retrieval quality at 100k+ scale; factual correctness of extracted claims beyond source-anchoring.

## Build sequence

| Step | Scope | Exit criterion | Est. cost |
|---|---|---|---|
| **F1** | PHX-1042 minimal fix: degree-aware PPR damping + optional global hub mask, default-off, exposed through `retrieve()` and `theogony mesh ask` | Unit tests show hub demotion on a synthetic scale-free graph; behavior with defaults unchanged; A/B via emergent judge runs on the founding mesh in F4 | 0 EUR |
| **F2** | Corpus script: manifest (pinned Gutenberg IDs), fetch via existing `mesh ingest` path, pilot mode (~50 paragraphs) and full mode, dedicated mesh root `data/mesh-founding/` | Pilot mesh exists; per-source `IngestRunReport`s emitted; title-verification failure path tested | ~2 EUR (pilot) |
| **F3** | Model decision: pilot with Haiku 4.5 vs. Sonnet 5, compared on run-report metrics (edges/node, tier distribution, Q-ID rate, relation density) | Written decision in the PR body of the full-read run; operator confirms spend | — |
| **F4** | Full read of the corpus with the chosen model; Oneiros ticks to consolidation saturation; PHX-1042 A/B on the founding mesh | Full mesh built; Beat-2 contradiction reachable by query; judge A/B result recorded | ~15–30 EUR |
| **F5** | Cockpit polish: activation animation (SpMV iterations as frames over SSE), provenance panel, contradiction highlighting | The three beats reproducible by an operator following a script in `demo/` | 0 EUR |
| **F6** | Produce: 3-minute recording, read-only hosted instance, animated GIF for the README head | Recording published; GIF in README | ~10 EUR (hosting) |

Budget ceiling: **100 EUR**. Estimated total: ~65 EUR including one full re-read as iteration buffer. LLM reads go through the Batch API (50% discount) where the pipeline supports it; embeddings are local (sentence-transformers); no GPU required.

## Non-goals (explicitly out of scope)

- Scaling `mesh-wiki-100k` or cosmetic fixes to its labels (PHX-1044 stays open, unaffected).
- Anything requiring H100-class compute (PHX-1035). The demo must not depend on the unproven central bet.
- New top-level modules or agent classes. Every step lands inside existing module boundaries.
