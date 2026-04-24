# Living Demo

## What the demo is

The Living Demo is a short, operator-run walk through the Cockpit Explorer where you ask a question, the system detects a knowledge gap, **Argus** autonomously selects a governed Gutenberg acquisition, **HestiaLite** approves it, the existing ingest pipeline runs, the chronicle graph grows while you watch the growth stream, and a second question in the same region returns a richer cited answer than the first.

## What it proves

These points map to the exit criteria in [`docs/plans/LIVING_DEMO_PLAN.md`](plans/LIVING_DEMO_PLAN.md) §"Exit criteria":

- The chronicle has typed intent to grow: a **CuriosityTrigger** is emitted from stub signals when the growth bridge is enabled (W7-A).
- One autonomous agent acts on that intent under deterministic governance: **Argus** proposes sources, **HestiaLite** approves or rejects without an LLM (W7-B).
- Growth is visible in real time: the Cockpit **Growth live** panel streams phases over SSE (W8).

## What it does NOT prove

- It does **not** prove open-web acquisition; that remains out of scope until a later version.
- It does **not** prove federation, time-machine queries, or a negative-knowledge layer.
- It does **not** prove production cost, latency, or scale beyond what you observe in a single honest run.

## How to reproduce

1. Run the reset script (gated — see script output if you forget the confirmation env var): [`demo/reset_living_growth.sh`](../demo/reset_living_growth.sh).
2. Follow the operator recording script: [`demo/living_growth.md`](../demo/living_growth.md).

Two conceptual steps: **reset**, then **walk** the timeline.

## Where the recording lives

The canonical ~3 minute screen recording is produced and published by the project operator (not by automation in this repository). After you have a valid recording, link it from your release notes or project page as you prefer.

For a hosted smoke walk after local verification, see [`demo/living_growth_hosted.md`](../demo/living_growth_hosted.md).
