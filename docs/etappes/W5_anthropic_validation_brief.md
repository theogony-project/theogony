# W5 — Full ingest on Anthropic + demo-recording prep

**From:** Hesiod
**To:** Talos
**Date:** 2026-04-20
**Branch:** new branch off main, e.g. `feat/anthropic-full-ingest`
**Scope:** one PR, bundled
**Predecessor:** PR #30 merged → default LLM is now `claude-3-5-haiku-20241022`

Direct brief, no Daedalus. Execution etappe: validate the new default end-to-end against a real corpus, generate the actual material the §1 demo recording will showcase, close the two remaining 🟡 in §5 Week 4, and reconcile PR #30 in the Plan.

---

## Why this etappe

Three problems collapse into one PR:

1. **PR #30 changed the default LLM but never ran live against the pipeline.** Unit + integration tests with mocks pass; the forced-tool path on Anthropic's Messages API has not been exercised end-to-end against our Pydantic schemas with a real book. That is the User's original request ("Können wir das einfach umstellen und dann nochmal einen Testlauf machen?") still open.

2. **The W4 demo log is bounded (50 sentences, 106 nodes).** Honest at the time — Gemini's free tier was exhausted — but not enough material for a 5-min screen recording: the answer-quality is too thin, the Hover-Lupe walk has too few nodes to traverse interestingly, the Oneiros activity is too small to read.

3. **Plan §5 Week 4 still carries two 🟡** for cardinality + latency. Both can be closed against the actual numbers from a full Anthropic-Haiku ingest.

**One run, three problems closed.**

---

## What this etappe ships

Bundled scope, one PR (sibling pattern to PR #24 / PR #27 / PR #29):

1. **Full unbounded ingest of #43497** on the new default stack (Anthropic Claude 3.5 Haiku). Real Neo4j, real prepaid Anthropic credits, real wall-clock. Capture the `IngestRunReport` and the actual numbers. The User has prepaid Anthropic credits; cost is bounded by credit balance, not a free-tier RPD cap.

2. **Five demo queries** via `theogony ask` against the running `theogony serve`. Three "good-shape" queries (the answer should land), one honest-failure query, one Hover-Lupe walk via `theogony node`. Capture verdicts + cited node IDs + per-query cost, write into `demo_log.md`.

3. **Anthropic-vs-Gemini comparison table** appended to `demo_log.md`. Apples-to-apples is impossible (the W4 baseline ran a 50-sentence slice; this run is full-book), but you can compare the *per-LLM-call* metrics that *are* directly comparable: avg tokens-in, avg tokens-out, avg latency, EUR-per-call. Write a small table; honesty discipline as in W4 (no cherry-picking).

4. **Plan §5 Week 4 reconciliation**: flip the two 🟡 (cardinality + latency) to ✅ if the real numbers meet the brief targets, or to a refined explanation if they don't. Update the §1 demo block's commands if anything in the demo path changed (it shouldn't have).

5. **Top-of-doc reconciliation block** for **PR #30 + this run** combined. PR #30 was a small provider-swap that didn't get its own recon at merge time (intentionally deferred per User: "weniger PRs"). This block writes both at once: (a) PR #30 — provider expansion + default switch to Anthropic Haiku, with one-paragraph rationale; (b) this run — full-corpus validation of the new default, demo-recording material now in place.

6. **Demo-recording prerequisites confirmed**. After this PR merges, a `theogony reports list` should show the new full-ingest run; `theogony node <Q-id>` against any high-confidence resolved node should show a populated edge list (not the 39-edge sparse graph from the W4 bounded run). Confirm both work before declaring success.

---

## Out of bundle

Explicitly **not** in this PR (file as PHX or punt to a future brief if surfaced):

- **5-min screen recording** (User-action; Hesiod's next brief is the demo script for the User to read while recording).
- **Reviewer agent PHX-0035** (Gen-2; this run merely produces fresh corpus for it).
- **Detective Mode** etappe (still conditional on PHX-0041 re-measurement).
- **HNSW + filter pushdown** (PHX-0052, Gen-2).
- **Anthropic SDK upgrade to Haiku 4.5** (separate decision; current pin `>=0.30.0` is fine for 3.5 Haiku).
- **`max_tokens` → `max_completion_tokens`** in the OpenAI provider (irrelevant for the Anthropic-default path).
- **Any restructuring of the demo_log.md format** beyond appending the new run — keep the W4 sections intact, add new sections after them.

---

## Scope discipline (read before starting)

### Honesty is the deliverable, again

Same rule as W4: **write the truth, including unflattering numbers**. If the full ingest costs €12 instead of the €3–8 Hesiod estimated, write €12. If wall-clock is 45 min instead of the projected 15–20 min, write 45 min. If the Anthropic forced-tool path produces lower-quality relations than Gemini did on the bounded slice, write that — and pin it with a sample.

If anything blocks the run (rate limit, SDK bug, Cypher constraint surprise, wallet exhaustion at credit balance), document the block + the workaround in `demo_log.md`. Do **not** silently fall back to stub-LLM or to Gemini just to produce a green-looking PR.

### Cost ceiling — escalate, don't push through

The User's prepaid Anthropic balance is finite. Estimate per ingest call:

- ~3000 sentences with mentions × 1 LLM call (relation extraction)
- + ~2000 entity-resolution Stage-4 disambiguation calls
- + ~1 BookContextExtractor call

Rough total: **~5000 LLM calls** at Haiku 3.5 prices (€0.0007/M in, €0.0035/M out, ~3000 in / ~50 out tokens average for our prompts) → estimated **€2–4 per full ingest**.

**Hard escalation triggers** (stop, ping Hesiod, do *not* keep running):

- Cumulative cost crosses **€15** mid-ingest.
- Wall-clock exceeds **90 min** (something is wrong with concurrency or rate-limiting).
- Anthropic returns 429s in clusters (similar to the Gemini W4 finding).
- The forced-tool response shape doesn't match our Pydantic schemas in >5 % of calls (would indicate a schema-mismatch bug in `llm_anthropic.py` we'd want to investigate before a 30-min run).

If you hit any of these: kill the ingest, write what you saw into `demo_log.md`, file a PHX if it's structural, and ping Hesiod before retrying.

### Real Anthropic, real Neo4j — not stubs

Same as W4. The whole point is to validate the live path. `THEOGONY_LLM__PROVIDER=anthropic` (which is now the default), `ANTHROPIC_API_KEY` set, `docker compose up -d neo4j` running, `theogony serve` up. No `--stub-llm`, no provider override mid-run.

### One PR, no scope creep

If you find a real bug in `llm_anthropic.py` or `factory.py` while running — fix it in this PR (it's blocking the etappe). If you find anything else (a failing test on an unrelated path, a Cypher plan regression, a typo in the README) — note it in the PR body and file a PHX, do not fix it here.

---

## Concrete steps

(Order matters; each step gates the next.)

### Step 1 — Smoke test on a small slice (~5 min)

Before the full run, sanity-check the Anthropic path with the same flag pattern as the W4 baseline:

```bash
theogony ingest 43497 --sentences 50 --no-book-context
```

Watch for: forced-tool calls succeed, Pydantic validation passes, no spike of `parse_error` rows, cost is in-band (~€0.05). If anything looks off — stop and investigate. This is the cheap dress rehearsal.

### Step 2 — Full unbounded ingest

```bash
theogony ingest 43497
```

(no `--sentences`, no `--no-book-context` — full path, including BookContextExtractor.)

Monitor periodically. Capture wall-clock. The audit log + `IngestRunReport` will carry the full numbers.

### Step 3 — Five queries + Hover-Lupe

Pick the same five-shape mix as W4 (3 substantive, 1 honest-failure, 1 Hover-Lupe). You can reuse W4 queries verbatim if you want direct comparability — note in `demo_log.md` which W4 query each new query mirrors.

### Step 4 — Capture and write

Append a new section to `demo_log.md`: `## Anthropic full-ingest run (2026-04-DD)` with subsections matching the W4 structure (Setup → Ingest → Queries → Hover-Lupe → Oneiros activity → Closing summary → Total cost). Keep the W4 sections untouched above it.

Add the comparison subsection: `### Anthropic Haiku 3.5 vs. Gemini 2.5 Flash Lite — per-call`. Three columns (Anthropic, Gemini, ratio); rows: avg tokens in / out, avg latency ms, EUR per call, parse_error rate. Pull Gemini numbers from the W4 audit log (`data/extraction_audit.sqlite`, filter on `llm_provider='gemini'` from W4 run_id).

### Step 5 — Plan reconciliation

`docs/IMPLEMENTATION_PLAN_GEN1.md`:

- New top reconciliation block (place at the top, above the existing W4 block):
  ```
  **Changes since post-W4-demonstration reconciliation (2026-04-DD, post-PR-#30 + Anthropic full-ingest validation).**
  ```
  - One bullet: PR #30 — provider expansion (OpenAI + Anthropic) + default switch to Claude 3.5 Haiku. Rationale (prepaid credits, predictable billing, qualitatively cleaner extraction on literary text).
  - One bullet: this run — full unbounded ingest on the new default. Numbers: nodes, edges, cost, wall-clock, verdict. One sentence on quality vs. W4 baseline.
  - One bullet: §5 Week 4 reconciled — cardinality + latency 🟡 → ✅ (or refined).
  - One bullet: any PHX tickets filed (likely none; flag if any).

- §5 Week 4 deliverables list: flip the two 🟡 (cardinality + latency at success criteria #3 + #4) to ✅ with the new numbers, or to a refined explanation. Reference the new demo_log.md section.

### Step 6 — Verify, push, open PR

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy src/
pytest -q
```

All green. Commit, push, open the PR. PR title: `feat(demo): full-ingest validation on Anthropic Haiku 3.5 + W4 reconciliation`. PR body: short summary + numbers table + link to the new `demo_log.md` section.

---

## What success looks like

After this PR merges:

- `data/extraction_audit.sqlite` carries an Anthropic full-ingest run with ~5000 audit rows.
- `demo_log.md` carries a second run section with real numbers comparable to W4 in shape.
- The Plan §5 Week 4 block is **fully ✅** (or honestly explains why a 🟡 remains).
- A reader who follows the README quickstart on the new default stack reproduces what the demo recording will show.
- Hesiod can write the demo-recording script (next etappe) against a known-working corpus.

If the run produces unflattering numbers — that's still success. The demo recording will show whatever the system actually does; if Anthropic Haiku is *worse* than Gemini Flash Lite on literary extraction, that is a finding worth surfacing and a Gen-2 measurement worth running. The honest log is the artefact.

---

## Escalation

Ping Hesiod (don't decide silently) for:

1. Any of the four hard-stop triggers above.
2. The Anthropic forced-tool response shape not matching our schemas (suggests a real bug in `llm_anthropic.py`).
3. Anthropic's pricing turning out materially different from Hesiod's estimate (e.g. cost > 3× projection — Hesiod will recompute and decide whether to switch back to OpenAI or to a different Anthropic tier).
4. The W4 baseline numbers being unrecoverable from `data/extraction_audit.sqlite` (we'd need a different comparison strategy).
5. Anything else that looks structural, not mechanical.

Otherwise: proceed, push, ping when CI is green and `demo_log.md` is in.
