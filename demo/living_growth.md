# Living Demo — 3-minute recording script

Operator-facing walk for the closed loop (query → gap → Argus → HestiaLite → ingest → live growth → better answer). See [`docs/LIVING_DEMO.md`](../docs/LIVING_DEMO.md) for what this proves.

## Prerequisites

- A **real LLM API key** in the environment (for example `ANTHROPIC_API_KEY` with the default Anthropic provider). Stub synthesis alone is not valid for an honest recording.
- **Neo4j** running if you use `THEOGONY_NEO4J__URI` so the reset script can wipe the graph before re-seeding; otherwise the script clears `data/run_reports/` + `data/audit.sqlite` and runs `theogony seed --store memory` (see [`reset_living_growth.sh`](reset_living_growth.sh)).
- `theogony cockpit serve` uses the bundled in-memory chronicle; restart the cockpit after a reset so the in-memory graph matches a clean run.
- After reset: `source .demo.env` from the repo root so **GrowthBridge** and **Argus** are enabled.

## Pre-flight

Run these three commands from the **repository root** after a successful reset (`THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh`). Paste outputs into your PR under “Pre-flight self-test” when you are Talos.

**1) Baseline seed header (node count before t+00:00)**

```bash
theogony seed --info
```

Expected: a table whose `node_count` is **278** and `edge_count` is **1168** for the bundled `pantheon_self` dump (schema version 1). Embedding line should show `BAAI/bge-small-en-v1.5@v1` and `embedding_dim` 384.

**2) Cockpit ready line**

```bash
source .demo.env
theogony cockpit serve --host 127.0.0.1 --port 8000
```

Expected: a log line similar to `Theogony Cockpit → http://127.0.0.1:8000/cockpit/ (in-memory pantheon_self seed)` and Uvicorn listening without traceback.

**3) Browser**

Open `http://127.0.0.1:8000/cockpit/explorer?growth=on` in a normal browser window.

Expected: Explorer loads; the **Growth live** panel is visible (not collapsed/hidden) because `growth=on` is set.

## The 3-minute walk

Copy the timeline from [`docs/plans/LIVING_DEMO_PLAN.md`](../docs/plans/LIVING_DEMO_PLAN.md) §1 verbatim, then execute it literally:

```text
00:00  Cockpit open, chronicle close to empty (only pantheon_self seed).
00:10  User asks: "Who was Sven Hedin and what did he investigate in Tibet?"
00:15  Answer: "I only know a little. Blind spot detected in region
        [Tibet, expedition, early 20th century]. Argus is searching..."
        The growth panel opens.
00:25  Argus: Gutenberg search -> 3 candidates -> #43497 score 0.87 ->
        HestiaLite approved -> fetch starts.
00:55  Pipeline: sentences extracted, entities resolved, relations stored,
        embeddings written.
01:40  The graph grows visibly in the cockpit.
02:00  System: "Done. Ask again."
02:10  User repeats the question.
02:15  Longer cited answer with Hover-Lupe drill-down.
02:50  User clicks "Lhasa" cell -> zoom opens -> another stub appears ->
        "Younghusband expedition - Argus is searching..."
```

**Literal operator inputs**

- At **00:10**, type exactly (submit as the Explorer question):

  `Who was Sven Hedin and what did he investigate in Tibet?`

- At **02:10**, repeat the **same** question verbatim.

- At **02:50**, click the **"Lhasa"** cell (table or graph label as rendered in the Explorer answer — the literal click target is the visible **Lhasa** text).

**Screenshot anchor markers** (place markers in your recording notes; they are not UI chrome):

- `[screenshot: t+00:25 — three Gutenberg candidates]` — growth panel shows search/score/candidates with three Gutenberg rows and `#43497` visible.
- `[screenshot: t+02:15 — longer cited answer]` — second answer clearly longer / more citations than first pass.
- `[screenshot: t+02:50 — Lhasa zoom]` — zoom/detail view after clicking **Lhasa**.

## Acceptance

Tick **only** if the recording is honest:

- [ ] Starting graph node count printed before t+00:00 matches the seed baseline (**278** nodes from `theogony seed --info`, or the equivalent your reset just established).
- [ ] The cockpit shows a **`trigger_emitted`** event in the growth panel.
- [ ] The cockpit shows at least one **`argus_phase`** named **`fetch`** followed by **`done`**.
- [ ] Re-asking yields a longer cited answer than the first pass.
- [ ] Post-demo node count is **strictly greater** than pre-demo node count (measure via Explorer graph or status surface you use consistently).
- [ ] No manual flag flipping happened during the recording (all enablement came from `source .demo.env` / scripted env, not from editing live config mid-take).

## Failure modes

If any acceptance item fails, the recording is **invalid**: run `THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh` again, restart the cockpit, and redo the walk. Do not edit the timeline post hoc to match what happened.
