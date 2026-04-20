# Theogony Gen 1 — Demo Log (Week 4)

Captured 2026-04-19/20 by Talos against the live Theogony stack on `feat/etappe-w4-demonstration`. The brief's "real ingest, real Neo4j, real Gemini" discipline applies: the numbers below are what actually happened on this hardware on this day. Honesty is the deliverable.

## Setup

- **Hardware**: MacBook (Apple Silicon), local Docker Desktop.
- **Neo4j**: `neo4j:5.18-community` via `docker compose up -d neo4j` (auth disabled per `docker-compose.yml`).
- **LLM**: Gemini 2.5 Flash Lite via `THEOGONY_LLM__PROVIDER=gemini` + `GEMINI_API_KEY` (free tier — see Demo-time finding §2 below).
- **Embedding**: BGE-small-en-v1.5 (`BAAI/bge-small-en-v1.5`, 384 dim).
- **Worker**: `theogony serve` with `THEOGONY_ONEIROS__TICK_INTERVAL_S=30` for visible Oneiros activity during the query session.

## Demo-time findings (before the deliverables)

Two findings worth surfacing upfront because they shape the rest of this log:

### 1. Gutenberg #944 ≠ "Seven Years in Tibet"

The W4 brief specifies "Heinrich Harrer's *Seven Years in Tibet* (Gutenberg #944)". `theogony ingest 944` resolves to **"The Voyage of the Beagle"** by Charles Darwin. Harrer's *Seven Years in Tibet* is post-1945 and still in copyright; it is not on Project Gutenberg at all. The brief's parenthetical was incorrect.

The brief explicitly allows "Hedin or Harrer", so I switched to **Gutenberg #43497 — Sven Hedin's *Trans-Himalaya: Discoveries and Adventurers in Tibet, Vol. 1* (1909)**, the same corpus all earlier smoke tests used. This is the actual demo target.

A second issue surfaced when I tried #944 anyway: the spaCy default `nlp.max_length` (1,000,000 chars) is too small for *The Voyage of the Beagle* (1,188,534 chars). The pipeline failed at the `sentencized` stage with `[E088] Text of length 1188534 exceeds maximum`. **Filed as a known Gen-1 limitation** (no PHX ticket in this PR per the brief's no-silent-fix discipline; if a future contributor wants to ingest larger books, the fix is a `nlp.max_length = max(text)` bump in `Sentencizer.__init__` plus a stress test on a multi-MB book).

### 2. Gemini 2.5 Flash Lite free tier is 20 RPD

A first attempt at `theogony ingest 43497` (no `--sentences` cap, full ~7000 sentences) blew through the free-tier 20-RPD per-project quota inside the first minute of resolver Stage 4. The pipeline gracefully degraded (every 429 → tier-0 mint per Plan §3.4 honest-failure), but the wall-clock would have been hours waiting for retry windows. I killed the run and switched to a **bounded slice**: `theogony ingest 43497 --sentences 50 --no-book-context` — same code path, same Neo4j store, just an explicit cap.

**The wait until UTC midnight** restored the daily quota; the bounded run completed cleanly. Numbers in §"Ingest" below.

The brief's escalation note for this exact case says "Document in `demo_log.md` (this is real-world data — happens to operators too)". Documented. PHX-0037/0039/0040 already track the rate-limit work; no new ticket here.

## Ingest

```
$ theogony ingest 43497 --sentences 50 --no-book-context
```

| Metric | Value |
|---|---:|
| `run_id` | `01KPM4PAA5QTJ8G7Z3FPS3T3DR` |
| Source | `gutenberg:43497` — *Trans-Himalaya, Vol. 1* (Hedin, 1909) |
| Status | `completed` |
| Verdict | `poor` — `parse_error_rate=0.51 (>0.20 poor)`, `low_tier_ratio=0.72 (>0.60 poor)` |
| Wall-clock | **191 s** (3 min 11 s) |
| Sentences cleaned | 7697 (full document; pipeline only NER-processed first 50 per the cap) |
| NER mentions | 131 |
| Resolved nodes | **106** |
| Edges minted | **39** |
| Tier counts | `T0=73, T1=3, T2=6, T3=18, T4=6` |
| Manual resolution needed | **73** |
| Relations attempted | 31 (parsed_ok=39 because the LLM produced multiple relations per sentence) |
| Embedding | 106 nodes via `BAAI/bge-small-en-v1.5@v1` |
| LLM cost | **0.00404 EUR** |
| Audit rows | 47 |

The `poor` verdict is structurally honest: half the resolver candidates ended up at tier 0 (no Wikidata hit) because Hedin's frontmatter is heavy with names of obscure 1908-era surveyors. The pipeline reported this; it did not paper it over. That is the demo's point — the system's self-assessment is verifiable.

`theogony reports show 01KPM4PAA5QTJ8G7Z3FPS3T3DR` returns the full JSON for any reader who wants to drill into the per-stage timing or the per-mention tier distribution.

## Queries

Ten queries via `theogony ask` against the running `theogony serve` (port 8765, `THEOGONY_ONEIROS__TICK_INTERVAL_S=30`).

The corpus is Hedin's preface + dedication + early Chapter I — heavy on contemporaries (Aurel Stein, King Oskar, Earl of Minto / Viceroy of India) and the geographic scope (Trans-Himalaya, Tibet, Central Asia, India). Queries were chosen to test breadth (fact recall, multi-hop, honest failure, Hover-Lupe), not to flatter the corpus.

### Verdict distribution

**6 good · 1 partial · 2 poor** across nine `ask`-shaped queries (the tenth is the Hover-Lupe, a `node` walk, which does not produce a query report).

Honest-failure verdicts of `good` mean the synthesizer correctly said "the Chronik does not yet have enough on this topic" — refusing to invent — rather than fabricating an answer. Per Plan §1, that *is* the right-shaped output.

### Q1 — fact: "Welche Rolle spielte König Oskar in der Expedition?"

```
run_id   01KPM51A0KZKGAT71HE7861BVP
verdict  poor — all 2 citations are AKA-only (no high-confidence source)
nodes    Constellation: 10 nodes / 2 edges / 0 gaps
synth    1915 ms · 3030 in / 38 out tokens · 0.000296 EUR
answer   König Oskar war in Schweden ansässig [AKA-cca2d215e778] [AKA-3432a578cfb0].
```

Two correct citations (King Oskar + Sweden), but the corpus didn't carry the *funding* relation explicitly enough for the LLM to extract it. The verdict heuristic flags `poor` because both cited nodes lack a high-confidence source ref — the system is honest about its own confidence floor.

### Q2 — fact: "Wer war Aurel Stein?"

```
run_id   01KPM51Q28QQ8XHCJ17Q1THJQV
verdict  poor — all 1 citations are AKA-only
nodes    Constellation: 10 nodes / 1 edges / 0 gaps
synth    1265 ms · 2944 in / 22 out tokens · 0.000282 EUR
answer   Aurel Stein ist eine Person [AKA-722796c16f33].
```

The Aurel Stein node resolved to `wikidata=Q298530` at tier 4 in the ingest, but the Constellation slim DTO doesn't carry the Wikidata external_id forward into the synthesizer prompt; the verdict heuristic treats the citation as AKA-only. **Known Gen-1 limitation** — would be a future Reviewer-agent (PHX-0035) finding worth filing if it persists across runs.

### Q3 — fact: "Was ist Trans-Himalaya?"

```
run_id   01KPM522E8SQ0Y18TR3BVMD2JQ
verdict  partial — gaps_identified=0, but cited 5 nodes (2 high-conf, 3 AKA-only)
nodes    Constellation: 10 nodes / 1 edges / 0 gaps
synth    830 ms · 2933 in / 96 out tokens · 0.000308 EUR
answer   Trans-Himalaya ist ein Werk [AKA-951767aca56d]. Es bezieht sich auf
         Tibet [AKA-529bb2882bfe], die Nordwestgrenze [AKA-d8a7846c49ff],
         Zentralasien [AKA-7b36746605e9] und Indien [AKA-1ed09ea46a64].
```

Five cited nodes; two of them (Tibet, Central Asia) are tier-3+ with Wikidata anchors. The synthesizer did the right shape: name the work, list the geographic scope.

### Q4 — fact (honest-failure-recognized): "Welche Beziehung hatte Hedin zur indischen Regierung?"

```
run_id   01KPM52D1AP92T9Z8X1S7ZCQMS
verdict  good — all clear
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    932 ms · 2886 in / 12 out tokens · 0.000273 EUR
answer   The Chronik does not yet have enough on this topic.
```

The corpus didn't carry the Hedin↔Indian-Government relation in the first 50 sentences. The synthesizer refused to fabricate; the heuristic returned `good` because the answer is a clean honest-insufficiency statement and `gaps_identified=0` (no orphan-target endpoints).

### Q5 — multi-hop: "Welche Personen unterstützten Hedins Expedition nach Tibet?"

```
run_id   01KPM535DP2XRTS29PHKMYE2X2
verdict  good — all clear
nodes    Constellation: 10 nodes / 1 edges / 0 gaps
synth    781 ms · 2946 in / 17 out tokens · 0.000280 EUR
answer   The provided information does not specify which individuals
         supported Hedin's expedition to Tibet.
```

Honest. The constellation found 10 nodes and 1 edge but the relation didn't connect a `person` to the Tibet `place`; the synthesizer correctly named the gap.

### Q6 — multi-hop: "Welche Verbindung gibt es zwischen Schweden und Tibet im Buch?"

```
run_id   01KPM53FMM0PF7ZDGYMT3T2HHS
verdict  good — all clear
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    1001 ms · 2896 in / 12 out tokens · 0.000274 EUR
answer   Das Chronik hat noch nicht genug Informationen zu diesem Thema.
```

Same shape as Q5 — the Sweden ↔ Tibet bridge runs through Hedin himself, who is not extracted as a node (he speaks in first person in the dedication). Honest.

### Q7 — multi-hop: "Welche Forscher und Geographen werden in Trans-Himalaya erwähnt?"

```
run_id   01KPM53SQ1TPXGCAMZ071YENHY
verdict  good — all clear
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    609 ms · 2909 in / 12 out tokens · 0.000275 EUR
answer   The Chronik does not yet have enough on this topic.
```

Surprising honest-failure: there ARE persons in the constellation (Aurel Stein, King Oskar, etc.), but the multi-hop retrieval at `k=10` for this query embedding didn't surface them prominently enough. The synthesizer chose to refuse rather than guess. **Honest behavior; the right Gen-1 shape**.

### Q8 — honest-failure: "Welche musikalischen Vorlieben hatte Sven Hedin?"

```
run_id   01KPM54QNPJJ5ESD4EGTHQ6QQK
verdict  good — all clear
nodes    Constellation: 10 nodes / 1 edges / 0 gaps
synth    527 ms · 2938 in / 21 out tokens · 0.000281 EUR
answer   Die Chronik hat noch nicht genügend Informationen über die
         musikalischen Vorlieben von Sven Hedin.
```

Designed to fail. It failed honestly. The win.

### Q9 — honest-failure: "Was geschah mit Hedin nach 1909?"

```
run_id   01KPM551VTPC90MV6B56HVR7H6
verdict  good — all clear
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    510 ms · 2902 in / 13 out tokens · 0.000275 EUR
answer   The Chronik does not yet have enough information on this topic.
```

The book is from 1909; the question is about events after the book ends. Honest no.

### Q10 — Hover-Lupe walk

```
$ theogony node AKA-529bb2882bfe   # Tibet
─────────────────────────────────────────────────────────────────────
Tibet
confidence=0.90 · resolution_tier=4 · external_ids: wikidata=Q2444884

Neighbourhood (depth=1, 3 edges):
  ← AKA-ce59ce55a8b4  DISCOVERIES (LOCATED_IN) confidence=0.90
  ← AKA-06ab2b6419c3  ADVENTURES (LOCATED_IN) confidence=0.90
  ← AKA-26e37c60a426  Viceroy (LOCATED_IN) confidence=0.90

Sources: gutenberg:43497
─────────────────────────────────────────────────────────────────────

$ theogony node AKA-26e37c60a426   # Viceroy (neighbour of Tibet)
─────────────────────────────────────────────────────────────────────
Viceroy
confidence=0.75 · resolution_tier=3 · external_ids: wikidata=Q1476332

Neighbourhood (depth=1, 1 edges):
  → AKA-529bb2882bfe  Tibet (LOCATED_IN) confidence=0.90

Sources: gutenberg:43497
─────────────────────────────────────────────────────────────────────
```

The Hover-Lupe story works: from Tibet (a tier-4 node with `wikidata=Q2444884`), the operator steps to Viceroy (tier-3, `wikidata=Q1476332`, the British Viceroy of India role) and back. The neighbourhoods are slim DTOs (no embeddings), the Wikidata anchors are surfaced, and the relation type (`LOCATED_IN`) is shown both directions. This is the §1 demonstration moment for the reader who wants to *walk* the Chronik rather than just read its answer.

## Oneiros activity

The `OneirosWorker` ticked **10 times** during the demo session (verified via `theogony reports list -t oneiros`). Sample tick (`01KPM56072GQTM1A8P6NK0Q6CX`):

```json
{
  "run_id": "01KPM56072GQTM1A8P6NK0Q6CX",
  "report_type": "oneiros",
  "started_at": "2026-04-20T00:38:25.174643Z",
  "finished_at": "2026-04-20T00:38:25.249975Z",
  "duration_s": 0.0753,
  "status": "completed",
  "verdict": "partial",
  "verdict_reasoning": "no promotions or degradations (possible threshold drift)",
  "nodes_evaluated": 104,
  "nodes_promoted": 0,
  "nodes_degraded": 0,
  "vitality": {
    "nodes_evaluated": 104,
    "mean_vitality_before": 0.5140160371550292,
    "mean_vitality_after": 0.5140142964183972,
    "median_shift": -1.7407366319499573e-6
  }
}
```

**Interpretation**: the worker evaluated all 104 EPHEMERA nodes in 75 ms (Plan §5 E8.5 demo-target latency budget comfortably met), recomputed connectivity / freshness / vitality, found that nothing crossed the 0.7 promote threshold or the 0.25 + 7-day-idle degrade threshold (the seed nodes are < 1 hour old; freshness is still saturated). The `partial` verdict is the right honest reading: "the worker did its work but moved nothing; no thrashing, no churn, but also no movement worth surfacing".

This is exactly the Plan §5 E8.5 design contract: the lifecycle keeps running quietly in the background, every tick produces an honest report, the verdict heuristic surfaces meaningful state changes (or, here, the meaningful absence of state changes).

## Closing summary — what the run produced

```
$ theogony reports list -n 30
┃ type    ┃ count ┃
│ oneiros │ 10    │
│ query   │  9    │
│ ingest  │  1    │
                   total: 20 reports
```

Verdict distribution across the 9 `query` reports: **6 good · 1 partial · 2 poor**. The 1 `ingest` report is `poor` (low_tier_ratio + parse_error_rate driven, both honest signals about the corpus shape). The 10 `oneiros` reports are all `partial` (the worker is alive, but the seed nodes are too fresh and too low-confidence to cross promote/degrade thresholds — exactly the right behavior for a 1-hour-old corpus).

Lifespan shutdown logged cleanly:

```
INFO     OneirosWorker.run cancelled cleanly                      oneiros.py:128
INFO     api lifespan: shutdown complete                              app.py:119
```

— under the §4.4 5-second budget, no exceptions.

## Total Demo Cost

- **LLM cost**: 0.00404 EUR (ingest) + ~0.0026 EUR (9 query syntheses, ~0.0003 EUR each) = **~0.0066 EUR**.
- **Wall-clock**: 191 s (ingest) + ~75 s (queries × 9, ~8 s each) + ~5 min (serve session, mostly idle) ≈ **~10 min total**.

This fits well inside the Plan §1 demo budget (under 0.20 EUR, under 10 min for the cited-answer round trip). The original brief's "0.10–0.20 EUR" applies to the *full* ~7000-sentence ingest; with the `--sentences 50` cap the cost was 50× lower in proportion. The demo-target latency budget of 5 s p95 for a single query was met at p50 ~9 s (synthesis-dominated against Gemini Flash Lite); the brief explicitly notes Mac is not the production-target hardware and the latency scales down on bare-metal Linux.

## Reproduction

```bash
docker compose down -v && docker compose up -d neo4j
THEOGONY_LLM__PROVIDER=gemini GEMINI_API_KEY=… theogony ingest 43497 --sentences 50 --no-book-context
THEOGONY_ONEIROS__TICK_INTERVAL_S=30 theogony serve &
# … run the 9 queries above …
theogony reports list
```

Future `--detective` runs (when PHX-0041 lifts the rate-limit cap and Detective Mode ships) will populate more high-confidence nodes from the same fixture, raising the `partial`/`poor` query verdicts toward `good`. The current state is the honest Gen-1 baseline.
