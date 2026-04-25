# Living Demo — 3-minute recording script

Operator-facing walk for the closed loop (query → gap → Argus → verification pool → ingest → live growth → better answer). See [`docs/LIVING_DEMO.md`](../docs/LIVING_DEMO.md) for what this proves.

## Prerequisites

- A **real LLM API key** in the environment (for example `ANTHROPIC_API_KEY` with the default Anthropic provider). Stub synthesis alone is not valid for an honest recording.
- **Neo4j** running if you use `THEOGONY_NEO4J__URI` so the reset script can wipe the graph before re-seeding; otherwise the script clears `data/run_reports/` + `data/audit.sqlite` and runs `theogony seed --store memory` (see [`reset_living_growth.sh`](reset_living_growth.sh)).
- `theogony cockpit serve` uses the bundled in-memory chronicle; restart the cockpit after a reset so the in-memory graph matches a clean run.
- After reset: `source .demo.env` from the repo root so **GrowthBridge**, **Argus**, the **ResearchPlanner**, and the **Evaluator** are enabled.

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

Expected: Explorer loads; the **Research live** panel is visible (not collapsed/hidden) because `growth=on` is set.

## The 3-minute walk

Execute this Wave 3 open-flow timeline literally:

```text
00:00  Cockpit open, chronicle close to empty (only pantheon_self seed).
00:10  User asks: "Who was Sven Hedin and what did he investigate in Tibet?"
00:15  Answer arrives with weak/partial evidence. Argus starts research.
        The research panel opens.
00:25  Plan section fills with research steps (Wikidata / Wikipedia / Gutenberg or web).
00:55  Execution cards fill with candidates and evaluator selection.
01:25  Acquiring and ingesting in parallel.
       Pool entries created — verification happens asynchronously.
       Counters tick: nodes added, edges added.
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

- `[screenshot: t+00:25 — research plan]` — research panel shows typed steps and candidate rows.
- `[screenshot: t+02:15 — longer cited answer]` — second answer clearly longer / more citations than first pass.
- `[screenshot: t+02:50 — Lhasa zoom]` — zoom/detail view after clicking **Lhasa**.

## Optional: Athene pass (immune visibility)

After **`research_complete`**, you may run:

```bash
theogony curiosity athene-run --once --store neo4j
```

With `.demo.env` from the reset script, Athene is enabled and samples at rate `1.0`, so the **Immune system** panel in the Explorer should show `sampled_by_athene` increasing and one **Finding** node in the constellation. This demonstrates post-hoc sampling and Finding write-back, not factual verification of content.

## Optional: Chronos pass (pool clear)

After the Athene step (or any time pool rows are `sampled_by_athene`), you may run:

```bash
theogony curiosity chronos-run --once --store neo4j
```

The **Immune system** panel should show **cleared** increasing. If Athene only produced `no_issue_observed` findings, Chronos clears without negative edges. If a finding had targets and a factual contradiction type, Chronos may write `CONTRADICTS` edges and demote confidence. This proves immune response plumbing, not truth repair.

## Optional: Nemesis structural audit

Operator runs:

```bash
theogony curiosity nemesis-run --once --store neo4j
```

The Immune system panel/report list shows a Nemesis report. If contradictions or overconfident low-evidence nodes exist, Nemesis writes Finding nodes.

Optional fixture:

```bash
THEOGONY_CURIOSITY__ERIS__ENABLED=true theogony curiosity eris-run --once --store memory --fixture
```

Eris writes a campaign report and fixture Finding nodes without mutating live content.

## Acceptance

Tick **only** if the recording is honest:

- [ ] Starting graph node count printed before t+00:00 matches the seed baseline (**278** nodes from `theogony seed --info`, or the equivalent your reset just established).
- [ ] The cockpit shows a **`trigger_emitted`** event in the growth panel.
- [ ] The cockpit shows at least one **`acquired_into_pool`** event followed by **`ingested`** and **`research_complete`**.
- [ ] Re-asking yields a longer cited answer than the first pass.
- [ ] Post-demo node count is **strictly greater** than pre-demo node count (measure via Explorer graph or status surface you use consistently).
- [ ] No manual flag flipping happened during the recording (all enablement came from `source .demo.env` / scripted env, not from editing live config mid-take).

## Failure modes

If any acceptance item fails, the recording is **invalid**: run `THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh` again, restart the cockpit, and redo the walk. Do not edit the timeline post hoc to match what happened.
