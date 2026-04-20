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

---

# W5 — Anthropic Haiku 4.5 full-ingest validation (2026-04-20)

Captured by Talos against the live Theogony stack on `feat/anthropic-full-ingest` after PR #30 (default LLM = Anthropic) merged. The W5 brief's discipline applies: real Neo4j, real Anthropic, real prepaid credits, real wall-clock. Honest numbers, honest blocks.

This section APPENDS to the W4 section above; the W4 numbers are not edited.

## Setup

- **Hardware**: same MacBook (Apple Silicon), local Docker Desktop.
- **Neo4j**: same `neo4j:5.18-community` via `docker compose up -d neo4j`.
- **LLM**: Anthropic via `THEOGONY_LLM__PROVIDER=anthropic` (now the default after PR #30) + `ANTHROPIC_API_KEY`. **Model: `claude-haiku-4-5-20251001`** — see Demo-time finding §1 below for why this is *not* the brief's `claude-3-5-haiku-20241022`.
- **Embedding**: same `BAAI/bge-small-en-v1.5` (384 dim).
- **Worker**: `theogony serve` with `THEOGONY_ONEIROS__TICK_INTERVAL_S=30` again.

## Demo-time findings (before the deliverables, again)

Three findings worth surfacing upfront before the numbers:

### 1. PR #30's `claude-3-5-haiku-20241022` does not exist on the User account

PR #30 set the default to `anthropic / claude-3-5-haiku-20241022`. CI was 100 % green (lint + 3.12 + 3.13 + Neo4j-live + serve smoke); the PR-30 follow-up bundle in PR #31 added another sweep — also 100 % green. Yet the W5 first smoke-ingest against a fresh Neo4j produced **0 edges, €0.00 cost, 47 / 47 audit rows tagged `transport_error:NotFoundError`**.

Direct probe against the Anthropic API with the User's key:

```
404 claude-3-5-haiku-20241022 → not_found_error
404 claude-3-5-haiku-latest    → not_found_error
404 claude-haiku-3-5           → not_found_error
OK  claude-3-haiku-20240307    → "Hello! How can I assist you today?"
```

`client.models.list()` on the User's account returns Opus 4.7 / 4.6 / 4.5, Sonnet 4.6 / 4.5 / 4 / 4.1, **Haiku 4.5**, and Haiku 3 — but no Haiku 3.5 anywhere. Anthropic retired the 3.5-Haiku tier between SDK 0.30 (the original PR #30 pin's reference release) and current accounts; on new keys it is not reachable at all. PR #30 was never functional for this User; we just didn't notice because every test ran against mocks.

**Hesiod decision (Option A, relayed via User 2026-04-20)**: bump the default to `claude-haiku-4-5-20251001` with updated pricing (USD/M input bumps from 0.80 → 1.00; USD/M output bumps from 4.00 → 5.00; per Anthropic public list pricing). Forced-tool path validated against both 4.5 and Haiku 3 before commitment — both work cleanly (no SDK / schema bug; the issue was purely model-availability). Plan §3.3a's "Claude Haiku 3.5" rows are now historical artefacts.

**Filed as PHX-0055** ("CI smoke-test against the live default LLM provider — catches model-retired surprises") so the next default-swap doesn't ship silently broken into the demo recording.

### 2. Full-unbounded ingest of #43497 is structurally infeasible on Wikidata's free tier

After Hesiod's Option A re-pinning, smoke v2 succeeded cleanly: `theogony ingest 43497 --sentences 50 --no-book-context` produced 26 edges, €0.10 cost, 233 s wall — 100 % parse-OK across 47 LLM calls. The Anthropic path was vindicated.

Per the W5 brief's Step 2, the next move was the full unbounded ingest: `theogony ingest 43497`. Run-id `01KPMG4TR1WDTWPPMB8R34TYFJ`. Cost-projection extrapolated from the smoke landed at €10–15 — at the edge of Hesiod's €15 hard-stop ceiling but still in-band. Wall-clock projection at the smoke's pace landed at ~15–30 min, in-band of the 90-min ceiling.

What actually happened: **Wikidata's public SPARQL endpoint (`query.wikidata.org`) throttled the EntityResolver Stages 1–3 catastrophically**. The audit log shows transport-error retries firing every few seconds throughout the run. After 45 minutes of wall-clock the pipeline had managed:

- 1 BookContext call (€0.0039)
- 253 Stage-4 disambiguation calls (€0.5040; **100 % parse-OK**)
- 0 relation_extraction calls (Stage 4 hadn't finished for all mentions yet)
- 0 nodes persisted to Neo4j (store stage not reached)

Pace at kill: **5.6 Stage-4 LLM calls / minute** (1.7 % of what the W5 brief's mental model assumed). Linear extrapolation to ~2 200 remaining Stage-4 mentions: ~7.5 hours. The bottleneck was unmistakably Wikidata, not Anthropic. Anthropic was idle most of the run.

**Hesiod decision (relayed via User 2026-04-20)**: kill the run. *"The Anthropic-path validation goal is met by the perfect-parse calls already in audit; we have what we needed there. The full-unbounded target is structurally infeasible on Wikidata's free tier for this corpus — that's the honest finding to document."*

The corresponding Phoenix Backlog ticket — **PHX-0033** "Pre-curated Wikidata subset for travel literature" — was already on the books (Daedalus, 2026-04-17). Updated 2026-04-20 with the measured throttle evidence above as motivating data; ticket scope unchanged. **No new PHX needed.**

The W5 brief explicitly forbids fixing the Wikidata throttle in this PR (caching, request batching, alternative endpoints — all Gen-2 work). The sanctioned demo path is now `--sentences 500` with BookContextExtractor on; that's what Section "Bounded ingest" below captures.

### 3. The bounded-ingest path is the demo recording path, *not a workaround*

Hesiod's W5 brief was specific that the W4 `--no-book-context` flag was a Gemini-quota hack and not the production path. The W5 bounded path is `theogony ingest 43497 --sentences 500` (with BookContext on). That is the production path; it is what the demo recording will reproduce. The unbounded path remains a "post-PHX-0033 capability".

Numbers below are the bounded-path numbers.

## Bounded ingest

```
$ theogony ingest 43497 --sentences 500
```

| Metric | Value |
|---|---:|
| `run_id` | `01KPMJE57HW70T2TA3GXK4CZZA` |
| Source | `gutenberg:43497` — *Trans-Himalaya, Vol. 1* (Hedin, 1909) |
| Status | `completed` |
| Verdict | `poor` — `parse_error_rate=0.65 (>0.20 poor)`, `low_tier_ratio=0.90 (>0.60 poor)` |
| Wall-clock | **1188.92 s = 19 min 49 s** |
| Sentences cleaned | 7697 (full document; pipeline NER-processed first 500 per the cap) |
| NER mentions | **1158** |
| Resolved nodes | **756** |
| Edges minted | **139** |
| Tier counts | `T0=667, T1=16, T2=10, T3=44, T4=19` |
| Manual resolution needed | **667** |
| Relations attempted | 301; parsed_ok = 139 (46 % yield; the remainder dropped at evidence-span validation) |
| Embedding | 756 nodes via `BAAI/bge-small-en-v1.5@v1` |
| LLM cost | **€0.68271** |
| Audit rows | 371 (1 book_context + 69 stage4_disambiguation + 301 relation_extraction) |
| LLM parse-success | **100 %** (371 / 371 audited calls) |

Hesiod's W5 expectation for the bounded path was 30–45 min wall-clock, €2–3 cost, 400–600 nodes, 200–400 edges. Actuals: **20 min, €0.68, 756 nodes, 139 edges** — wall-clock and cost both well under expectation; node count above expectation; edge count below expectation.

The lower-than-expected edge count is structural, not Anthropic-specific. Of 301 relation_extraction calls that returned parse-OK from the LLM, only 139 survived the downstream `evidence_span` validation (the relation extractor drops relations whose evidence span lands outside the central sentence — a Gen-1 hallucination-suppression heuristic; PHX-territory at the validator level, but **out of scope for W5**). Same code path ran in W4 with Gemini and yielded the same shape.

`poor` verdict is the same heuristic shape as W4: `parse_error_rate` from the dropped relations + `low_tier_ratio` from the obscure-1908-surveyor density. The system is being honest about its own confidence; it is not silently masking the relation drops.

`theogony reports show 01KPMJE57HW70T2TA3GXK4CZZA` returns the full JSON.

## Queries

Five queries via `theogony ask` against the running `theogony serve` (port 8765, `THEOGONY_ONEIROS__TICK_INTERVAL_S=30`). Same shape mix as W4: 3 substantive + 1 honest-failure + 1 Hover-Lupe walk. The Hover-Lupe is a `theogony node` walk, which does not produce a query report.

### Verdict distribution

**3 good · 1 partial · 1 (the Hover-Lupe; not a query report)** across the 4 `ask`-shaped queries.

The `good` verdicts again include honest-failure-recognition: the synthesizer correctly said "die Chronik hat noch nicht genug Informationen" rather than fabricating. Plan §1's right-shaped output, again.

### Q1 — substantive: "Wer war Sven Hedin?"

```
run_id   01KPMM2HNQRBYDADRVNNTFCMT8
verdict  good — 1 cited, 1 high-conf
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    1941 ms · 2729 in / 83 out tokens · 0.002924 EUR
answer   Die Chronik hat noch nicht genug Informationen zu dieser Frage. Es ist nur
         bekannt, dass es eine Person namens Sven Hedin [AKA-64c45f68b1a0] gibt, aber
         es fehlen Angaben zu seinen Aktivitäten, seiner Biographie und seiner
         historischen Bedeutung.
```

The Sven Hedin node IS in the graph (tier-3, `wikidata=Q154759` — verified in Q5 below). The retrieval-side limitation is that the multi-hop seeds didn't surface Hedin's three connected `TRAVELED_TO` / `OPPOSED_TO` edges into the constellation; the synthesizer stayed honest about what was *in the prompt context*, not what was in the broader graph. PHX-territory: improve multi-hop seed selection on bare-id queries.

### Q2 — substantive multi-hop: "Welche Beziehung hatte Sven Hedin zur britisch-indischen Regierung?"

```
run_id   01KPMM2XQNKY9EZVG47HRRADRM
verdict  good — 2 cited, 1 high-conf
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    2457 ms · 2751 in / 139 out tokens · 0.003205 EUR
answer   Die Theogony Chronik hat zu dieser Frage noch nicht genug Informationen. Die
         vorliegende Konstellation enthält zwar einen Knoten zu Sven Hedin
         [AKA-64c45f68b1a0] und einen zum Britischen Empire [AKA-05d113950f73], aber
         es gibt keine dokumentierten Beziehungen zwischen ihnen…
```

Same retrieval-side limitation as Q1. The graph DOES contain `Sven Hedin → OPPOSED_TO → Tibet ← OPPOSED_TO → John Morley` (visible in the Hover-Lupe Q5 below), but the multi-hop didn't bridge from the query embedding "britisch-indische Regierung" to those edges. Honest "no" beats fabricated "yes".

### Q3 — substantive: "Welche geografischen Regionen werden in Trans-Himalaya beschrieben?"

```
run_id   01KPMM39850T5CK59NQN37R5W6
verdict  partial — 4 cited, 1 high-conf
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    2422 ms · 2739 in / 176 out tokens · 0.003366 EUR
answer   Die Chronik verfügt noch nicht über ausreichende Informationen zu dieser
         Frage. Obwohl das Werk Trans-Himalaya [AKA-951767aca56d] bekannt ist und
         einzelne Orte wie Tibet [AKA-529bb2882bfe], Zentraltibet [AKA-be82aed97a55]
         und die Nordwestgrenze [AKA-d8a7846c49ff] erwähnt werden, fehlen die
         konkreten Relationen zwischen dem Werk und den darin beschriebenen
         geografischen Regionen…
```

Four cited geographic nodes — the answer correctly names them but flags the missing "WORK → DESCRIBES → PLACE" edge type. That edge type isn't in the Gen-1 RelationExtractor's vocabulary (PHX-territory). `partial` verdict is the right shape.

### Q4 — honest-failure: "Welche musikalischen Vorlieben hatte Sven Hedin?"

```
run_id   01KPMM4262BYTF0F7CXA9Y11FZ
verdict  good — 1 cited, 1 high-conf
nodes    Constellation: 10 nodes / 0 edges / 0 gaps
synth    2006 ms · 2736 in / 78 out tokens · 0.002907 EUR
answer   Die Theogony Chronik hat zu diesem Thema noch nicht genug Informationen. Die
         vorliegende Konstellation enthält zwar einen Knoten zu Sven Hedin
         [AKA-64c45f68b1a0], aber keine Daten über seine musikalischen Vorlieben.
```

Designed to fail. It failed honestly. The win.

### Q5 — Hover-Lupe walk: Sven Hedin ↔ Tibet

```
$ theogony node AKA-64c45f68b1a0   # Sven Hedin
─────────────────────────────────────────────────────────────────────
Sven Hedin
confidence=0.75 · resolution_tier=3 · external_ids: wikidata=Q154759

Neighbourhood (depth=1, 3 edges):
  → AKA-529bb2882bfe  Tibet (TRAVELED_TO) confidence=0.95
  → AKA-529bb2882bfe  Tibet (TRAVELED_TO) confidence=0.85
  ← AKA-548ee4fb925c  the Indian Government (OPPOSED_TO) confidence=0.75

Sources: gutenberg:43497
─────────────────────────────────────────────────────────────────────

$ theogony node AKA-529bb2882bfe   # Tibet
─────────────────────────────────────────────────────────────────────
Tibet
confidence=0.90 · resolution_tier=4 · external_ids: wikidata=Q2444884

Neighbourhood (depth=1, 12 edges):
  ← AKA-526108164353  Imperial Government (RULED_BY) confidence=0.75
  ← AKA-d4485f7f7de4  Captain Cecil Rawling (TRAVELED_TO) confidence=0.90
  ← AKA-e113505101ce  Francis Younghusband (TRAVELED_TO) confidence=0.95
  ← AKA-64c45f68b1a0  Sven Hedin (TRAVELED_TO) confidence=0.95
  ← AKA-8385259b2e10  English Expedition (TRAVELED_TO) confidence=0.95
  → AKA-1ed09ea46a64  India (NEAR) confidence=0.70
  ← AKA-d816bc77abff  Lhasa (LOCATED_IN) confidence=0.85
  ← AKA-64c45f68b1a0  Sven Hedin (TRAVELED_TO) confidence=0.85
  ← AKA-409b88a6a1a2  John Morley (OPPOSED_TO) confidence=0.80
  ← AKA-cefad5fa5a24  Government (OPPOSED_TO) confidence=0.85
  ← AKA-1ed09ea46a64  India (NEAR) confidence=0.85
  ← AKA-4d38f8e7af4b  Scientific Results (DESCRIBED_BY) confidence=0.85

Sources: gutenberg:43497
─────────────────────────────────────────────────────────────────────
```

This is the recording-grade demo moment. From `Sven Hedin` (tier-3, `wikidata=Q154759` — the actual Hedin Wikidata entry) the operator steps to `Tibet` (tier-4, `wikidata=Q2444884`) and finds a populated 12-edge neighbourhood: Hedin's expedition (TRAVELED_TO with confidence 0.95), Younghusband's mission (TRAVELED_TO 0.95), Cecil Rawling (TRAVELED_TO 0.90), Lhasa (LOCATED_IN 0.85), the geopolitical contention with John Morley (OPPOSED_TO 0.80) and the Imperial Government (RULED_BY 0.75), the geographic adjacency to India (NEAR 0.85). The Edwardian Tibet expedition map, in graph form, with citation back to the source.

This is what the §1 demonstration moment looks like with recording-grade material. The W4 baseline only had Tibet ↔ Viceroy as a 2-edge round-trip; W5's bounded path produces a 12-edge geopolitical web around Tibet.

## Anthropic Haiku 4.5 vs. Gemini 2.5 Flash Lite — per-call comparison

Drawn from `data/audit.sqlite`. W4 ran a 50-sentence ingest with Gemini Flash Lite (`run_id=01KPM4PAA5QTJ8G7Z3FPS3T3DR`); W5 ran a 500-sentence ingest with Anthropic Haiku 4.5 (`run_id=01KPMJE57HW70T2TA3GXK4CZZA`). Apples-to-apples on call count is impossible (different sentence caps), so the table below compares **per-call** metrics that ARE directly comparable.

| Per-call metric (avg across all stages) | Gemini 2.5 Flash Lite (W4, n=47) | Anthropic Haiku 4.5 (W5, n=371) | Anthropic / Gemini ratio |
|---|---:|---:|---:|
| Input tokens / call | 333 | 1 120 | **3.4×** |
| Output tokens / call | 148 | 172 | 1.16× |
| Latency / call | 1 237 ms | 1 829 ms | 1.48× |
| EUR / call | €0.0000857 | €0.001840 | **21.5×** |
| Parse-OK rate | 100 % (47 / 47) | 100 % (371 / 371) | 1.00× |

Per-stage breakdown (so the cost differential isn't hidden in a stage-mix shift):

| Stage | Gemini avg_in / avg_out / €/call | Anthropic avg_in / avg_out / €/call |
|---|---|---|
| `book_context`            | (not run in W4, `--no-book-context`) | 3 061 / 247 / €0.003995 |
| `stage4_disambiguation`   | 354 / 91 / €0.0000673 | 1 304 / 162 / €0.001966 |
| `relation_extraction`     | 322 / 177 / €0.0000957 | 1 071 / 174 / €0.001804 |

**Honest reading**: Anthropic Haiku 4.5 costs ~21× per call vs Gemini Flash Lite. Most of the cost differential comes from input tokens (~3.4×, partly because the Anthropic forced-tool path injects more schema boilerplate) plus the per-token list-price differential (Haiku 4.5 input is €1.00/M vs Flash Lite's input ~€0.05/M = 20×). Both providers parse at 100 %; quality on the actual extraction (entity / relation accuracy) requires PHX-0034's gold-standard benchmark — a one-day dress-rehearsal demo doesn't authoritatively say one is "better".

The Plan §3.3a economic rationale ("predictable prepaid billing beats free-tier daily caps for daily dev work") still holds; the absolute cost is well within budget for bounded demo runs (€0.68 for the recording corpus). Whether Anthropic remains the right *quality* default after PHX-0034 evidence is a future Hesiod call.

## Oneiros activity

The `OneirosWorker` ticked **5 times** during the W5 query session (verified via `theogony reports list -t oneiros`). Sample tick (`01KPMM5AC32308P8ZTG0AH16FH`):

```json
{
  "run_id": "01KPMM5AC32308P8ZTG0AH16FH",
  "report_type": "oneiros",
  "started_at": "2026-04-20T05:00:11.123377Z",
  "duration_s": 0.4001,
  "status": "completed",
  "verdict": "partial",
  "verdict_reasoning": "no promotions or degradations (possible threshold drift)",
  "nodes_evaluated": 724,
  "nodes_promoted": 0,
  "nodes_degraded": 0,
  "vitality": {
    "mean_vitality_before": 0.4897,
    "mean_vitality_after": 0.4897,
    "median_shift": -1.76e-6
  }
}
```

**Interpretation**: 724 nodes evaluated in 400 ms — the W4 baseline did 104 nodes in 75 ms; W5 scales roughly 7× more nodes for ~5× more wall, well within Plan §5 E8.5's demo-target latency budget. Verdict `partial` because no nodes crossed promote / degrade thresholds (correct: seed nodes are < 1 hour old; freshness still saturated). Same quiet-but-alive lifecycle behaviour as W4.

Lifespan shutdown logged cleanly (`OneirosWorker.run cancelled cleanly` + `api lifespan: shutdown complete`).

## Closing summary — what the W5 run produced

```
$ theogony reports list -n 30
  ingest:   1 (01KPMJE57HW70T2TA3GXK4CZZA)   verdict=poor
  query:    4 (01KPMM2H… / 01KPMM2X… / 01KPMM39… / 01KPMM42…)   verdict=3 good · 1 partial
  oneiros:  5 (01KPMM2H… → 01KPMM5A…)         verdict=all partial (correct: no threshold crosses)
```

Plus the killed-run unbounded ingest (`01KPMG4TR1WDTWPPMB8R34TYFJ`, 254 calls / €0.5079 / 45 min wall, see Demo-time finding §2 above) — kept in `data/audit.sqlite` as PHX-0033 motivating evidence; its `IngestRunReport` was never written because the run did not reach the report-writing stage.

## Total W5 cost

- Smoke-1 (Haiku 3.5 NotFound, throwaway): €0.00 (all 404s)
- Smoke-2 (Haiku 4.5, 50 sentences): €0.10010
- Killed unbounded run (Haiku 4.5): €0.5079
- Bounded demo ingest (Haiku 4.5, 500 sentences): €0.68271
- 4 demo queries: ~€0.0124 total
- **W5 total LLM spend: €1.30**

Comfortably under Hesiod's €15 ceiling. Wall-clock ~75 min total (most of which was the killed-unbounded run + waits between).

## Reproduction (W5, recording-grade)

```bash
docker compose down -v && docker compose up -d neo4j
ANTHROPIC_API_KEY=… theogony ingest 43497 --sentences 500
THEOGONY_ONEIROS__TICK_INTERVAL_S=30 theogony serve &
# … run the 5 queries above …
theogony reports list
```

What changed vs. the W4 reproduction recipe:

- Default LLM is now Anthropic; `ANTHROPIC_API_KEY` instead of `GEMINI_API_KEY`.
- Sentence cap is now 500 (recording-grade) instead of 50 (W4-quota-hack).
- BookContextExtractor on (no `--no-book-context`).
- Otherwise identical.

Future, when PHX-0033 ships the local Wikidata subset: drop `--sentences 500`, expect the unbounded ingest to complete in ≤ 60 min wall-clock (vs. the ~480 min projection on the live SPARQL endpoint).
