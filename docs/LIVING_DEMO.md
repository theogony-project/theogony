# Living Demo

## What the demo is

The Living Demo is a short, operator-run walk through the Cockpit Explorer where you ask a question, the system detects a knowledge gap, **Argus** autonomously researches sources, acquired content enters the verification pool without a synchronous content judge, the existing ingest pipeline runs, the chronicle graph grows while you watch the research stream, and a second question in the same region returns a richer cited answer than the first.

## What it proves

These points map to the exit criteria in [`docs/plans/LIVING_DEMO_PLAN.md`](plans/LIVING_DEMO_PLAN.md) §"Exit criteria":

- The chronicle has typed intent to grow: a **CuriosityTrigger** is emitted from stub signals when the growth bridge is enabled (W7-A).
- One autonomous agent acts on that intent: **Argus** proposes, evaluates, acquires, registers pool entries, and ingests sources.
- Growth is visible in real time: the Cockpit **Research live** panel streams phases over SSE.

## What it does NOT prove

- It does **not** prove factual correctness of ingested claims; post-hoc checks observe structure in run reports, not ground truth.
- Optional Wave 3 beat (after research): run `theogony curiosity athene-run --once --store neo4j` so the Cockpit **Immune system** panel shows `sampled_by_athene` increasing and a Finding node appears in the graph. This proves sampling and first-class Findings, not a full worker pool.
- Optional next beat: run `theogony curiosity chronos-run --once --store neo4j` so **cleared** increases on the Immune system panel. Chronos consumes persisted Findings and records actions; it does not prove factual repair.
- Operator runs: `theogony curiosity nemesis-run --once --store neo4j`. The Immune system panel/report list shows a Nemesis report. If contradictions or overconfident low-evidence nodes exist, Nemesis writes Finding nodes.
- Optional fixture: `THEOGONY_CURIOSITY__ERIS__ENABLED=true theogony curiosity eris-run --once --store memory --fixture`. Eris writes a campaign report and fixture Finding nodes without mutating live content.
- It does **not** prove federation, time-machine queries, or a negative-knowledge layer.
- It does **not** prove production cost, latency, or scale beyond what you observe in a single honest run.

## How to reproduce

1. Run the reset script (gated — see script output if you forget the confirmation env var): [`demo/reset_living_growth.sh`](../demo/reset_living_growth.sh).
2. Follow the operator recording script: [`demo/living_growth.md`](../demo/living_growth.md).
3. For Wave 3 local operators, prefer the helper scripts:
   - [`demo/start_wave3_cockpit.sh`](../demo/start_wave3_cockpit.sh)
   - [`demo/run_wave3_workers.sh`](../demo/run_wave3_workers.sh)

Two conceptual steps: **reset**, then **walk** the timeline.

## Where the recording lives

The canonical ~3 minute screen recording is produced and published by the project operator (not by automation in this repository). After you have a valid recording, link it from your release notes or project page as you prefer.

For a hosted smoke walk after local verification, see [`demo/living_growth_hosted.md`](../demo/living_growth_hosted.md).

For a single operator script that walks the full Wave 3 immune loop (Athene, Chronos, Nemesis, Eris fixture, Mnemosyne conductor) and lists the new report types, see [`demo/wave3_local_test.md`](../demo/wave3_local_test.md).
