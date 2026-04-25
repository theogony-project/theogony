# W17.5 - Demo Hardening: Make the Wave 3 Live Path Explainable and Robust

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-25
**Branch:** `feat/w17-5-demo-hardening`
**Scope:** one small PR (live-demo reliability, diagnostics, demo startup script; no new architecture)
**Predecessor:** W17 merged on `main` (PR #107). Local test surfaced the exact failures this brief addresses.
**Sprint slot:** Living Demo W17.5-A (post-Wave-3 hardening before broader demo recording)

This is a repair-and-polish sprint, not a concept sprint. The goal is to make the existing Wave 3 loop demonstrable and diagnosable.

---

## What we observed locally

The local Wave 3 test after W17 showed:

1. `cockpit serve` starts and the Explorer works.
2. The Sven Hedin query completes with `verdict=good`, 10 nodes, 8 edges, but no citations and a visible knowledge gap.
3. `Research this further` only works when the server is started with the right Curiosity flags.
4. With those flags, the button emits a trigger and opens the research stream.
5. Research planning/execution finds candidates:
   - `wikipedia_fetch - Sven Hedin`
   - `wikipedia_fetch - Trans-Himalaya (book series)`
   - `wikidata_lookup - Sven Hedin`
6. Evaluation selects 3 candidates.
7. Final UI outcome is `research_complete outcome=ingest_failed`.
8. Verification pool remains empty, so Athene/Chronos have nothing useful to process.
9. The UI does not show the concrete ingest failure reason.

This sprint fixes the operator-visible failure modes first.

---

## Doctrine constraints

- No pre-gate content filter.
- No deterministic "only perfect data enters" rule.
- No blocking ingest on Athene, Chronos, Nemesis, Eris, or Mnemosyne.
- No new LLM provider.
- No new research architecture.
- No scheduler/daemon.
- No self-modification.

Failures may still happen. The point of W17.5-A is that failures are visible, actionable, and do not unnecessarily abort the whole batch.

---

## Knob 1 - Show why `ingest_failed` happened

Today the Cockpit panel shows `research_complete outcome=ingest_failed` but hides the useful reason.

Update:

- `src/theogony/cockpit/growth_stream.py`
- `src/theogony/cockpit/static/js/explorer_growth.js`
- tests around growth stream rendering if present

Requirements:

1. `_emit_research_events_from_result(...)` must include these fields on `research_complete`:
   - `outcome`
   - `reason`
   - `decision_reason`
   - `decision_source_type`
   - `decision_identifier`
   - `decision_title`
   - `ingested_count`
   - `selected_count`
   - `rejected_count`
   - `pool_entry_ids`
2. The Cockpit "Outcome" block must render:
   - `research_complete outcome=<...>`
   - `reason=<...>` when present
   - `decision=<source_type>:<identifier> <title>` when present
   - `pool entries=<n>` when present
3. If `outcome` is any failure-like value (`ingest_failed`, `approved_ingest_failed`, `budget_exceeded`, `no_candidate_selected`, `no_planned_steps`, `no_candidates`, `unsupported_source_type`), render the line in warning style.
4. Do not expose stack traces. `reason` is capped to 500 chars in existing Argus result logic; preserve that cap.

Acceptance test:

- Fixture an `ArgusResult(outcome=INGEST_FAILED, reason="boom", decision.reason="candidate broke")`.
- Assert emitted `research_complete` data contains both reason fields.
- Assert JS renderer includes `reason=boom` or a stable text equivalent in the DOM.

---

## Knob 2 - Do not abort all selected research candidates on first ingest failure

Current W11 Argus planner path stops on the first acquisition/ingest error in a selected batch. In the local test, 3 candidates were selected but the system ended with zero pool entries.

Change `src/theogony/agents/argus.py` planner path:

- Continue through all selected candidates.
- Record per-candidate failure rows.
- Ingest every candidate that can be acquired and ingested.
- Return `APPROVED_AND_INGESTED` if at least one selected candidate succeeds.
- Return `INGEST_FAILED` only if all selected candidates fail after acquisition/ingest attempts.

Add model:

```python
class ArgusFailedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_label: str
    source_type: str | None = None
    source_identifier: str | None = None
    reason: str
```

Extend `ArgusResult`:

```python
failed_candidates: list[ArgusFailedCandidate] = Field(default_factory=list)
```

Rules:

- Budget exceed for a single selected source should skip that source and record a failed candidate, unless the **whole selected batch** exceeds `trigger.budget.max_total_bytes` before any acquisition. Keep the existing whole-batch budget guard.
- If acquisition fails for one source, record it and continue.
- If ingest fails for one source, record it and continue.
- `decision` should point to the last successful candidate if any, otherwise the first failed candidate.
- `reason` should summarize: `ingested=<n> failed=<m>`.

Acceptance tests:

- selected candidates A/B/C; A fails ingest, B succeeds, C succeeds -> outcome `approved_and_ingested`, 2 pool entries, 1 failed candidate.
- all selected candidates fail -> outcome `ingest_failed`, 0 pool entries, failed candidate count = selected count.
- one selected candidate exceeds per-source bytes -> skipped with failed candidate, others continue.

---

## Knob 3 - Persist candidate-level failure detail in reports and UI

The report and UI should let us answer "which source broke?" without reading logs.

Update:

- curiosity report models if needed
- growth stream event DTOs
- Cockpit rendering

Requirements:

- `failed_candidates` appears in the Argus result object returned to the growth stream.
- Growth stream emits `failed_candidates` on `research_complete`.
- Cockpit renders a compact list under Outcome:
  - `failed: <label> - <reason>`
  - max 5 visible rows
  - if more, render `+N more failures`
- Keep line lengths readable; no raw JSON dump.

Acceptance test:

- growth stream emits two failed candidates.
- Cockpit renderer displays both labels and reasons.

---

## Knob 4 - Demo startup script with the correct flags

Add `demo/start_wave3_cockpit.sh`.

Content requirements:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED="${THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED:-true}"
export THEOGONY_CURIOSITY__ARGUS__ENABLED="${THEOGONY_CURIOSITY__ARGUS__ENABLED:-true}"
export THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED="${THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED:-true}"
export THEOGONY_CURIOSITY__EVALUATOR__ENABLED="${THEOGONY_CURIOSITY__EVALUATOR__ENABLED:-true}"
export THEOGONY_CURIOSITY__ATHENE__ENABLED="${THEOGONY_CURIOSITY__ATHENE__ENABLED:-true}"
export THEOGONY_CURIOSITY__CHRONOS__ENABLED="${THEOGONY_CURIOSITY__CHRONOS__ENABLED:-true}"
export THEOGONY_CURIOSITY__NEMESIS__ENABLED="${THEOGONY_CURIOSITY__NEMESIS__ENABLED:-true}"
export THEOGONY_CURIOSITY__ERIS__ENABLED="${THEOGONY_CURIOSITY__ERIS__ENABLED:-true}"
export THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED="${THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED:-true}"

exec "${THEOGONY_PYTHON_BIN:-venv/bin/theogony}" cockpit serve --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
```

Make it executable.

Update `demo/wave3_local_test.md`:

- Prefer `bash demo/start_wave3_cockpit.sh`.
- Keep the raw command as an appendix for operators who want explicit flags.
- Note that without these flags `Research this further` may correctly emit no trigger.

Acceptance test:

- `bash -n demo/start_wave3_cockpit.sh`
- `rg 'GROWTH_BRIDGE__ENABLED' demo/start_wave3_cockpit.sh`
- `rg 'start_wave3_cockpit' demo/wave3_local_test.md`

---

## Knob 5 - Friendly `trigger_id=null` behavior

When `/cockpit/api/research-request` returns `{"trigger_id": null}`, the UI should not merely re-enable the button. It should explain what happened.

Update `explorer_growth.js`:

- If response is OK but `trigger_id` missing:
  - show toast: `No research trigger emitted. Is the growth bridge enabled?`
  - render a small Outcome line near the button: `No research trigger emitted (growth bridge disabled or no qualifying gap).`
  - re-enable the button.

Acceptance test:

- Mock `fetch("/cockpit/api/research-request")` response `{trigger_id:null}`.
- Assert toast text or DOM line contains `No research trigger emitted`.

---

## Knob 6 - Health endpoint for cockpit standalone

The local test tried `GET /health` against `cockpit serve` and got 404, even though the API app has a health route.

Add a minimal health route to cockpit standalone:

```json
{
  "status": "ok",
  "app": "cockpit",
  "store": "<backend>",
  "llm_model_id": "<model or stub>"
}
```

Location:

- likely `src/theogony/cockpit/standalone_app.py` or `router.py`

Rules:

- No LLM call.
- No expensive store traversal.
- Best-effort store backend name only.

Acceptance test:

- Start test client for cockpit app.
- `GET /health` returns 200 and includes `app=cockpit`.

---

## Knob 7 - Report-level smoke command

Add `demo/run_wave3_workers.sh`.

It should run:

```bash
THEOGONY_CURIOSITY__ATHENE__ENABLED=true venv/bin/theogony curiosity athene-run --once --store "${STORE:-memory}"
THEOGONY_CURIOSITY__CHRONOS__ENABLED=true venv/bin/theogony curiosity chronos-run --once --store "${STORE:-memory}"
THEOGONY_CURIOSITY__NEMESIS__ENABLED=true venv/bin/theogony curiosity nemesis-run --once --store "${STORE:-memory}"
THEOGONY_CURIOSITY__ERIS__ENABLED=true venv/bin/theogony curiosity eris-run --once --store memory --fixture
THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED=true venv/bin/theogony mnemosyne conduct --once --store "${STORE:-memory}" --metric-mode fixture
```

Then list:

```bash
venv/bin/theogony reports list --type chronos
venv/bin/theogony reports list --type nemesis
venv/bin/theogony reports list --type eris
venv/bin/theogony reports list --type mnemosyne_conductor
```

Acceptance test:

- `bash -n demo/run_wave3_workers.sh`
- docs mention it.

---

## Acceptance criteria

Run:

```bash
ruff format
ruff check
pytest -q tests/agents/test_argus.py
pytest -q tests/cockpit tests/cli/test_mnemosyne_conduct_cli.py tests/cli/test_nemesis_eris_cli.py
pytest -q
bash -n demo/start_wave3_cockpit.sh
bash -n demo/run_wave3_workers.sh
```

Manual smoke:

1. `bash demo/start_wave3_cockpit.sh`
2. Open `http://127.0.0.1:8000/cockpit/explorer?growth=on`
3. Ask `Wer war Sven Hedin und was hat er in Tibet erforscht?`
4. Click `Research this further`
5. Expected:
   - trigger emitted
   - plan/execution visible
   - candidate failures visible if any
   - if at least one candidate ingests, pool total increases
   - if all candidates fail, the exact source-level reasons are visible

---

## PR description template

```markdown
W17.5-A - Demo hardening for Wave 3 live path

What this PR does:
- surfaces Argus ingest/acquisition failure reasons in the Cockpit research panel
- lets planner-mode Argus continue after one selected candidate fails
- adds candidate-level failure details to the growth stream
- adds `demo/start_wave3_cockpit.sh` and `demo/run_wave3_workers.sh`
- adds a lightweight `/health` route for cockpit standalone
- updates `demo/wave3_local_test.md`

What this PR does NOT do:
- no new research architecture
- no content pre-gate
- no scheduler
- no self-modification

Acceptance criteria run locally:
- `ruff format && ruff check`
- targeted tests from the brief
- `pytest -q`
- `bash -n demo/start_wave3_cockpit.sh`
- `bash -n demo/run_wave3_workers.sh`

Notes / deviations:
<list or "none">

PHX tickets filed:
<list or "none">
```
