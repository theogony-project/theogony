# W17.5 - Cockpit Usability: Make the Living Demo Legible

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-25
**Branch:** `feat/w17-5-cockpit-usability`
**Scope:** one small PR (Cockpit usability and explanation polish; no backend architecture change)
**Predecessor:** W17.5-A should land first if possible. If not, this brief may still proceed but must not duplicate W17.5-A failure-detail work.
**Sprint slot:** Living Demo W17.5-B (operator/demo UX before recording or showing externally)

This sprint makes the Cockpit understandable to a human watching the living system for the first time. It does not make the system smarter. It makes the system explain itself.

---

## Why this etappe exists

The current Cockpit proves that pieces exist, but it does not yet narrate the organism:

- A new observer sees buttons and raw terms (`growth`, `stub`, `verdict`, `pool`) without a clear story.
- The answer and research panel are visually present, but the state transitions are not explained.
- The immune-system area shows numbers, but not what they mean or what to do next.
- Reports exist, but the path from "ask a question" to "immune system learned something" is not legible.

The Living Demo must be showable. That means the Cockpit needs a guided, honest narrative layer.

---

## Doctrine constraints

- No fake success states.
- No hiding failures.
- No pre-gates.
- No synchronous immune workers.
- No new data model unless explicitly listed below.
- No large frontend framework migration.
- No new CSS system.
- No charts requiring a plotting library. Use existing HTML/CSS.

The Cockpit should stay a thin, server-rendered demo surface with small vanilla JS helpers.

---

## Usability principle

Every screen should answer three questions:

1. **What is happening now?**
2. **Why did the system do that?**
3. **What can the operator do next?**

Apply this principle only to the Explorer/Growth/Reports surfaces touched below. Do not redesign the whole app.

---

## Knob 1 - Demo mode banner and readiness checklist

Add a compact "Wave 3 Demo Readiness" card to the Explorer page when `?growth=on`.

Location:

- `src/theogony/cockpit/templates/explorer.html`
- supporting data from router/app state if needed
- small JS in `explorer_growth.js` if dynamic

Card content:

- `Growth: on/off`
- `Research planner: on/off`
- `Evaluator: on/off`
- `Argus: on/off`
- `Verification pool: <total> entries`
- `Immune workers: manual`
- `Mnemosyne conductor: on/off`

Each row should be:

- green if enabled/healthy
- amber if disabled but optional
- red if required for the demo path and disabled

Rules:

- Do not call LLM.
- Do not block page load on store traversal.
- Use settings and existing `/cockpit/api/verification-pool`.

Acceptance test:

- With growth bridge disabled, rendered page includes `Growth: off` or equivalent.
- With growth bridge enabled, rendered page includes `Growth: on`.
- Verification pool count updates from the existing API.

---

## Knob 2 - Guided query examples

Replace or augment the current quick buttons with demo-aware examples grouped by purpose.

Required groups:

1. **Show known internal knowledge**
   - `What does Daedalus do?`
   - `How does Mnemosyne classify queries?`
2. **Trigger a knowledge gap**
   - `Wer war Sven Hedin und was hat er in Tibet erforscht?`
   - `What did Hypatia write about astronomy?`
3. **Explain the organism**
   - `How does the immune system repair misinformation?`
   - `What happens after content enters the verification pool?`

UI requirement:

- Each button has a one-line tooltip/help text below or in `title`, e.g. `Good demo gap: should offer Research this further.`
- Clicking still fills/sends the query as current quick buttons do.

Acceptance test:

- Page contains all three group labels.
- Buttons fill/send as before.

---

## Knob 3 - Stepper for the growth lifecycle

Add a visible lifecycle stepper near the Growth panel.

Steps:

1. `Ask`
2. `Detect gap`
3. `Plan research`
4. `Fetch candidates`
5. `Evaluate`
6. `Acquire`
7. `Ingest`
8. `Pool`
9. `Immune workers`
10. `Mnemosyne`

Behavior:

- Before query: all neutral.
- During ask: `Ask` active.
- When answer is weak/stub/gap and `Research this further` is shown: `Detect gap` active/done.
- On SSE events:
  - `planning_started` / `planning_complete` -> `Plan research`
  - `executing_step` / `step_candidates` -> `Fetch candidates`
  - `evaluating` / `evaluation_complete` -> `Evaluate`
  - `acquiring` / `acquired` -> `Acquire`
  - `ingesting` / `ingested` -> `Ingest`
  - `acquired_into_pool` -> `Pool`
  - `research_complete` -> mark completed or failed based on outcome
- Manual worker script is not run by Cockpit, so `Immune workers` should show `manual next step`.
- `Mnemosyne` should show `run conductor after workers`.

Failure behavior:

- If `research_complete outcome=ingest_failed`, mark `Ingest` failed and keep `Pool` neutral.
- If `trigger_id=null`, mark `Plan research` blocked with explanation.

Acceptance test:

- Unit/DOM test for event sequence updates expected step classes.
- Failure event marks the right step failed.

---

## Knob 4 - Plain-language explanation cards

Add collapsible "What does this mean?" cards for three areas:

1. **Verdict**
   - `good` does not mean "true"; it means the query pipeline completed and produced an answer under current scoring.
2. **Research**
   - Research is asynchronous acquisition. It may fail. Failure is part of the immune-system design if visible and repairable.
3. **Verification pool**
   - The pool is not a queue. It is a sampling reservoir; immune cells draw from it independently.

Requirements:

- Default collapsed.
- No long prose wall; 2-4 sentences each.
- Use exact doctrine language where useful: "post-hoc", "sampling reservoir", "not a pre-gate".

Acceptance test:

- Cards exist.
- Text contains `not a pre-gate` and `sampling reservoir`.

---

## Knob 5 - Better empty states

Replace generic blank/zero states with actionable empty states.

Required empty states:

- Verification pool total `0`:
  - `No acquired content in the pool yet. Ask a gap question, click Research this further, then wait for acquired_into_pool.`
- No reports for `athene`:
  - `Athene has not run yet. Run demo/run_wave3_workers.sh after research has produced pool entries.`
- No reports for `mnemosyne_conductor`:
  - `Mnemosyne conductor has not run yet. Run demo/run_wave3_workers.sh or the mnemosyne conduct command.`
- Research request produces no trigger:
  - `No trigger emitted. Growth bridge may be disabled or this answer did not qualify as a gap.`

Acceptance test:

- Mock empty pool API -> expected empty state text rendered.
- Reports page with no `mnemosyne_conductor` reports -> expected empty state text.

---

## Knob 6 - Reports page grouping by organism role

Improve Reports page navigation without changing report storage.

Group report type filters into sections:

- **Query and ingestion**
  - `query`
  - `ingest`
  - `curiosity`
- **Dream and structure**
  - `oneiros`
  - `clustering`
  - `blindspot`
  - `mnemosyne`
- **Immune system**
  - `chronos`
  - `nemesis`
  - `eris`
  - `mnemosyne_conductor`

If Athene does not currently write a report type, do not invent one in this PR. Show Athene through findings/pool state only.

Acceptance test:

- Reports page includes `Immune system`.
- `mnemosyne_conductor` filter remains functional.

---

## Knob 7 - Operator command drawer

Add a small copyable command drawer on the Explorer page.

Commands:

```bash
bash demo/start_wave3_cockpit.sh
bash demo/run_wave3_workers.sh
venv/bin/theogony reports list --type mnemosyne_conductor
```

Requirements:

- Display only; do not execute commands from the browser.
- Include one sentence: `Cockpit does not run immune workers automatically; they are independent post-hoc cells.`
- If browser copy helper is easy and already patterned, add copy buttons. Otherwise simple `<code>` blocks are enough.

Acceptance test:

- Page contains `demo/run_wave3_workers.sh`.
- Page contains `independent post-hoc cells`.

---

## Knob 8 - Visual polish within existing style

Small CSS-only polish:

- Make active/failure lifecycle steps visually obvious.
- Use consistent colors:
  - green: completed/success
  - amber: active/warning/manual
  - red: failed/blocker
  - purple/blue: immune-system informational
- Keep dark theme.
- Do not introduce a dependency.

Acceptance test:

- CSS file contains lifecycle classes:
  - `.growth-step`
  - `.growth-step-active`
  - `.growth-step-done`
  - `.growth-step-failed`

---

## Knob 9 - Honest demo footer

Add a compact footer/note on Explorer with:

```text
This demo shows growth mechanics, not guaranteed truth. False or partial information may enter; the immune system samples, flags, repairs, and learns over time.
```

This matters because the user wants to show the living mechanism honestly, without pretending the first answer is authoritative.

Acceptance test:

- Explorer page includes `growth mechanics, not guaranteed truth`.

---

## Files likely touched

- `src/theogony/cockpit/templates/explorer.html`
- `src/theogony/cockpit/templates/reports.html` or equivalent reports template
- `src/theogony/cockpit/static/js/explorer_growth.js`
- `src/theogony/cockpit/static/css/cockpit.css`
- `src/theogony/cockpit/router.py`
- `tests/cockpit/...`
- `docs/LIVING_DEMO.md`

Do not touch:

- `src/theogony/agents/argus.py` (belongs to W17.5-A)
- ingestion pipeline
- LLM provider wiring
- store implementations

---

## Acceptance criteria

Run:

```bash
ruff format
ruff check
pytest -q tests/cockpit
pytest -q
```

Manual UI smoke:

1. `bash demo/start_wave3_cockpit.sh`
2. Open `http://127.0.0.1:8000/cockpit/explorer?growth=on`
3. Confirm readiness card is visible.
4. Click the Sven Hedin gap example.
5. Confirm lifecycle stepper advances through Ask/Detect gap.
6. Click `Research this further`.
7. Confirm research lifecycle is visible and failures are understandable.
8. Open Reports.
9. Confirm report types are grouped and `mnemosyne_conductor` is discoverable.

---

## PR description template

```markdown
W17.5-B - Cockpit usability for the living demo

What this PR does:
- adds Wave 3 demo readiness card
- groups guided demo queries by purpose
- adds growth lifecycle stepper
- adds plain-language explanation cards
- improves empty states for pool/reports/research trigger
- groups Reports page by organism role
- adds operator command drawer and honest demo footer

What this PR does NOT do:
- no backend architecture changes
- no new research logic
- no immune worker scheduling
- no pre-gates

Acceptance criteria run locally:
- `ruff format && ruff check`
- `pytest -q tests/cockpit`
- `pytest -q`
- manual UI smoke from the brief

Notes / deviations:
<list or "none">

PHX tickets filed:
<list or "none">
```
