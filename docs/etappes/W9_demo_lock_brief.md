# W9 — Demo Lock + Recording (Living Demo, slice 4)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w9-demo-lock`
**Scope:** one PR (docs + scripts only; no production code changes)
**Predecessor:** W7-A, W7-B, W8 merged to `main`
**Sprint slot:** Living Demo W9 (fourth and final)

This is the closing sprint. Its only job is to make the demo reproducible. It must contain zero production code changes. If you find yourself editing `src/theogony/`, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (W7-A, W7-B, W8 must all be merged; if not, this brief is blocked).
2. `git checkout -b feat/w9-demo-lock`
3. After acceptance: `git push -u origin feat/w9-demo-lock` and open PR per template.

If any of W7-A / W7-B / W8 is not on `main`: stop. Open a draft PR `[BLOCKED] feat(demo): W9 — waiting on prerequisite slices`.

---

## Why this etappe exists

W7-A through W8 build the closed loop. W9 makes the loop demonstrable.

The Living Demo Plan §1 specifies one canonical 3-minute recording. W9 supplies the reset script that brings the chronicle into the demo's starting state, the recording script that says exactly what happens at every second, and the operator-facing doc that says what the recording proves. The recording itself is taken by the human operator with a real LLM key — Talos does not record it.

---

## Locked knobs

### Knob 1 — Reset script

`demo/reset_living_growth.sh` (new, executable). One-shot bash script. Zero arguments. Behaviour, in order:

1. Refuse to run if `THEOGONY_ALLOW_DEMO_RESET` is not set to `1`. Print "set THEOGONY_ALLOW_DEMO_RESET=1 to confirm wipe" and exit 2.
2. If `THEOGONY_NEO4J__URI` is set, run a Cypher `MATCH (n) DETACH DELETE n` against it (use `cypher-shell` if available, otherwise the Python helper below). If unset, wipe `data/run_reports/` and `data/audit.sqlite` only.
3. Re-seed by invoking `theogony seed` (existing CLI) so `pantheon_self` is back at its baseline node count.
4. Export `THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true`, `THEOGONY_CURIOSITY__ARGUS__ENABLED=true` into a generated `.demo.env` file (one line per variable, no secrets) at the repo root.
5. Print one summary block:
   ```
   Living Demo reset complete.
   Source the env: source .demo.env
   Start the cockpit: theogony cockpit serve
   Open: http://127.0.0.1:8000/cockpit/explorer?growth=on
   Recording script: demo/living_growth.md
   ```

If `cypher-shell` is unavailable and `THEOGONY_NEO4J__URI` is set, the script may shell out to a tiny Python one-liner (`python -c "import asyncio; from theogony.stores import ..."`). Keep that fallback inline; do not add a new helper module under `src/`.

`.demo.env` belongs in `.gitignore` — add the line if it is not already covered.

### Knob 2 — Recording script

`demo/living_growth.md` (new). Operator-facing, reproducible. Mandatory sections:

1. **Prerequisites** — a real LLM key in env, Neo4j running (or `THEOGONY_STORE=in_memory` for the cheaper recording variant), the env file from the reset script.
2. **Pre-flight** — three commands the operator runs and what their output should look like (`theogony seed`, `theogony cockpit serve` ready line, browser at the explorer URL with the growth panel visible).
3. **The 3-minute walk** — copy the timeline from `docs/plans/LIVING_DEMO_PLAN.md` §1 verbatim, add the literal text the operator types, the literal click target ("Lhasa" cell), and screenshot anchor markers (`[screenshot: t+00:25 — three Gutenberg candidates]`).
4. **Acceptance** — a checklist the operator ticks if and only if the recording is honest:
   - [ ] starting graph node count printed before t+00:00 matches the seed baseline
   - [ ] the cockpit shows a `trigger_emitted` event in the growth panel
   - [ ] the cockpit shows at least one `argus_phase` named `fetch` followed by `done`
   - [ ] re-asking yields a longer cited answer
   - [ ] the post-demo node count is strictly greater than the pre-demo node count
   - [ ] no manual flag flipping happened during the recording
5. **Failure modes** — if any acceptance item fails, the recording is invalid; rerun the reset script and try again. Do not edit the recording.

### Knob 3 — Operator-facing doc

`docs/LIVING_DEMO.md` (new). One page. Audience: someone who finds the project and wants to know "what does this prove". Mandatory sections:

1. **What the demo is** — one paragraph summarising the closed loop: query → gap → autonomous Argus → HestiaLite → ingest → graph grows live → better answer.
2. **What it proves** — three bullet points mapping back to Living Demo Plan §"Exit criteria":
   - the chronicle has typed intent to grow (W7-A)
   - one autonomous agent acts on that intent under deterministic governance (W7-B)
   - the growth is visible in real time (W8)
3. **What it does NOT prove** — explicit list:
   - it does not prove web acquisition (out of scope until v2)
   - it does not prove federation, time-machine queries, or negative-knowledge layers
   - it does not prove cost or latency beyond a single demo run
4. **How to reproduce** — pointer to `demo/reset_living_growth.sh` and `demo/living_growth.md`. Two commands: reset, walk.
5. **Where the recording lives** — link target only (the actual recording is published by the user, not by Talos).

### Knob 4 — Hosted smoke deploy

After the local recording is verified, deploy the same container image to a host you operate and run a remote smoke walk against the hosted MCP. Procedure goes into `demo/living_growth_hosted.md` (new):

- one **container roll** per [`hosted/README.md`](../../hosted/README.md) (build, optional registry push, restart/redeploy — or optional `fly deploy` if you use the checked-in Fly manifests)
- one `mcp` smoke call sequence (using the existing MCP test pattern under `tests/test_mcp_server.py` as reference) hitting `pantheon_ask` against a thin region
- expected: identical phase sequence to local

This file is documentation only. Talos does not deploy. The operator runs their own deploy pipeline.

### Knob 5 — Backlog hygiene tag

Append to the relevant entries in `docs/PHOENIX_BACKLOG.md`:

- PHX-0037: append `**Phase 1 closed (W7-A + W7-B + W8 + W9, see Living Demo Plan):** trigger schema + Argus + HestiaLite + cockpit live stream + reproducible demo. Phase 2 remains open for additional source types and real Hestia (PHX-0039).`
- For each frozen-for-demo phase listed in `docs/plans/LIVING_DEMO_PLAN.md` §"Backlog hygiene during W7-W9", append `**Frozen for Living Demo W7-W9, may activate post-demo.**` to the corresponding catalogue entry.

No new PHX tickets. No structural rewrite of the catalogue.

### Knob 6 — README pointer

In `README.md`, add a single short section between the existing "Quickstart" and "MCP" sections (or wherever the analogue exists) titled `Living Demo` with three lines:

- one sentence describing the demo
- a link to `docs/LIVING_DEMO.md`
- a link to `demo/living_growth.md`

Do not restructure README. Do not add screenshots in this PR — the user supplies screenshots after the recording.

### Knob 7 — No production code

Forbidden in this PR (zero exceptions):

- any change under `src/theogony/`
- any change to `pyproject.toml` other than (optionally) the addition of the `living_demo` pytest marker if W7-A did not register it
- any change to `tests/` other than possibly fixing a pre-existing test that breaks from running the reset script in CI (which it should not, because CI does not export `THEOGONY_ALLOW_DEMO_RESET`)

If you discover a real bug in W7-A / W7-B / W8 while writing the recording script, **do not fix it here**. Open a separate PR off `main` named `fix/<short-slug>` and reference it in this PR's body.

---

## Files to add / change

**New**

- `demo/reset_living_growth.sh` (executable; chmod 755)
- `demo/living_growth.md`
- `demo/living_growth_hosted.md`
- `docs/LIVING_DEMO.md`

**Edit**

- `README.md` — one short Living Demo section per Knob 6.
- `docs/PHOENIX_BACKLOG.md` — append the lines from Knob 5.
- `.gitignore` — add `.demo.env` if not already covered.

**Forbidden**

- everything else.

---

## Acceptance criteria (machine-runnable)

### A1 — Reset script behaves

```bash
bash demo/reset_living_growth.sh
# expects: prints the THEOGONY_ALLOW_DEMO_RESET refusal and exits 2

THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh
# expects: completes; prints the summary block; .demo.env exists at repo root
```

The second invocation must work in a CI-like environment where Neo4j is not running (it falls back to local data wipe).

### A2 — Markdown lints clean

```bash
# whatever lint the repo uses for markdown — at minimum:
ruff check  # rules out trailing whitespace etc. only on .py; markdown is best-effort
# eyeball headings level + link integrity
```

Validate every relative link in `docs/LIVING_DEMO.md`, `demo/living_growth.md`, `demo/living_growth_hosted.md` resolves to a real file in the repo at the time of the PR.

### A3 — Existing tests stay green

```bash
pytest -q
pytest -q -m living_demo
```

No production code changed → both must pass without modification.

### A4 — Recording script self-test

The `demo/living_growth.md` "Pre-flight" section must be runnable by Talos as a sequence of shell commands inside an isolated tmp directory and produce the expected outputs. Talos runs this once before opening the PR and pastes the recorded outputs into the PR body under "Pre-flight self-test result".

(The 3-minute walk itself is run by the human, not by Talos.)

---

## STOP-and-file rules

- The reset script cannot wipe Neo4j without introducing a new Python helper module. → file PHX, stop. Use the Python one-liner inline (Knob 1).
- The README's structure does not allow a clean Living Demo section in three lines without restructuring. → file PHX, stop. Append at end as a fallback only after escalation.
- W7-A / W7-B / W8 acceptance criteria fail when re-run on `main`. → do not paper over. File PHX, mark this PR as `[BLOCKED]`, escalate.

---

## PR description template

```
W9 — Demo Lock + Recording

Implements Living Demo W9 per docs/etappes/W9_demo_lock_brief.md.
Builds on W7-A + W7-B + W8.

What this PR does:
- adds demo/reset_living_growth.sh (gated by THEOGONY_ALLOW_DEMO_RESET=1)
- adds demo/living_growth.md (the 3-minute recording script)
- adds demo/living_growth_hosted.md (hosted smoke walk)
- adds docs/LIVING_DEMO.md (operator-facing summary)
- appends backlog-hygiene lines per Living Demo Plan §"Backlog hygiene"
- adds Living Demo pointer to README

What this PR does NOT do:
- it changes zero production code
- it does not record the video (the user records it after merge)
- it does not deploy anything (the operator runs their own container host)

Acceptance criteria run locally:
- `bash demo/reset_living_growth.sh` (refuses without env)
- `THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh` (succeeds)
- `pytest -q && pytest -q -m living_demo`
- pre-flight self-test outputs (pasted below)

Pre-flight self-test result:
<paste here>

PHX tickets filed in this PR: <list, or "none">

@hesiod-review
```
