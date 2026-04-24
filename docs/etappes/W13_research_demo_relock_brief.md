# W13 — Research demo re-lock + new SSE vocabulary + new recording (Living Demo Wave 2, slice 4)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w13-research-demo-relock`
**Scope:** one PR (cockpit + docs + scripts; minimal production code)
**Predecessor:** W10, W11, W12 merged on `main`
**Sprint slot:** Living Demo W13 (fourth and final in Wave 2)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (W10/11/12 must all be merged; if not, this brief is blocked).
2. `git checkout -b feat/w13-research-demo-relock`
3. Implement.
4. `git push -u origin feat/w13-research-demo-relock`
5. `gh pr create --base main --title "feat(cockpit): W13 — research SSE vocabulary + demo re-lock"` with the body shape at the bottom.

---

## Why this etappe exists

W10-W12 build a real research loop. This sprint makes it visible.

The W8 SSE vocabulary (`search → 0 candidates → done`) was designed for single-source lookup and reads as failure. The new flow has more interesting phases (planning, multi-source executing, evaluating) that the cockpit needs to surface honestly. The cockpit also needs the new "research this further" button wired into the live SSE stream (W10 added the button; W13 makes clicking it open a live panel).

W13 also retires HestiaLite cleanly and refreshes the demo recording so the user has something they would actually publish.

---

## Locked knobs

### Knob 1 — New SSE event vocabulary

The W8 vocabulary is **replaced**. Old event types stay valid for one release for backward compatibility with the W8 cockpit JS, but the new vocabulary is the only one the new cockpit panel listens to.

| `event:` | Payload fields | When emitted |
|---|---|---|
| `query_phase` | `phase` ∈ {`embed`, `retrieve`, `synthesize`}; `elapsed_ms` | per existing pipeline phase |
| `query_complete` | full Explorer payload | once, after synthesize |
| `trigger_emitted` | `trigger_id`, `gap_class`, `trigger_reason`, `answer_verdict` | once, only if a trigger fired |
| `planning_started` | `planner_model_id`, `expected_max_steps` | once, immediately after trigger |
| `planning_step_search` | `query: str`, `result_count: int` | once per LLM web_search tool invocation during planning |
| `planning_complete` | `step_count: int`, `cost_eur: float`, plan steps array (label only, not full schema) | once, after planner returns |
| `executing_step` | `step_index`, `step_kind`, `step_target` | once per step start |
| `step_candidates` | `step_index`, `candidate_count`, `candidate_labels: list[str]` | once per step end |
| `evaluating` | nothing | once, before evaluator call |
| `evaluation_complete` | `selected_count`, `rejected_count`, `cost_eur`, `rationale` | once, after evaluator |
| `hestia_review` | `candidate_label`, `decision`, `rule_fired`, `llm_called: bool` | one per candidate |
| `acquiring` | `candidate_label`, `bytes_target_estimate` | one per approved candidate |
| `acquired` | `candidate_label`, `bytes_acquired` | one per approved candidate |
| `ingesting` | `candidate_label` | one per ingest start |
| `ingested` | `candidate_label`, `nodes_added`, `edges_added`, `wikidata_qids_linked` | one per ingest end |
| `research_complete` | `outcome`, `total_cost_eur`, `total_nodes_added`, `total_edges_added` | once, terminal |
| `error` | `where: str`, `message: str` | terminal; stream closes after |

Phase names are exact. Adding a new event type is a brief violation; if the planner or executor produces something the vocabulary cannot represent → file PHX, stop.

The names are deliberately verbal ("planning_started", "executing_step", "ingested") so a human watching the cockpit reads work happening, not log lines.

### Knob 2 — Cockpit "Research live" panel rework

`src/theogony/cockpit/static/js/explorer_growth.js` is **rewritten** to render the new vocabulary. The growth panel becomes a "Research live" panel with three vertical sections that fill in as events arrive:

1. **Plan** — pretty-printed list of steps (kind + target + rationale tooltip) populated by `planning_complete`. Empty until then; "planning…" placeholder.
2. **Execution** — collapsible cards per step, populated incrementally by `executing_step` → `step_candidates`. Each candidate card shows label + summary + size estimate.
3. **Outcome** — populated incrementally by `evaluation_complete` → `hestia_review`* → `acquiring`/`acquired`/`ingesting`/`ingested` → `research_complete`. Per-candidate progress bars from acquire start to ingest done.

The old "list of one-line phase records" (W8 shape) is gone. The new shape is structured, scannable, and tells a story.

`src/theogony/cockpit/templates/explorer.html` — the growth panel block is rewritten with the three sections (HTML scaffolding only; JS populates).

### Knob 3 — Server-side stream rework

`src/theogony/cockpit/growth_stream.py::stream_growth_run` — the existing function is rewritten to emit the new vocabulary. The composition is the same (it composes `stream_explorer_ask_sse` for the query phases + the planner + executor + evaluator + hestia + acquire + ingest paths from W10/W11/W12). The only thing that changes is the event labels and payload shapes.

The `POST /cockpit/api/growth-stream` endpoint stays. The `POST /cockpit/api/research-request` endpoint from W10 is **rewired**: instead of just emitting a trigger and returning `{trigger_id}`, it now opens a server-sent event stream that runs the same machinery for the user-requested trigger. The cockpit button JS is updated to use `EventSource` against this endpoint.

```
GET  /cockpit/explorer?growth=on             — page (W8/W10)
POST /cockpit/api/ask-stream                  — query stream (W8)
POST /cockpit/api/growth-stream               — query + research stream (W8/W13)
GET  /cockpit/api/research-request-stream/{trigger_id}
                                              — research-only stream for the manual button
```

The new `GET /cockpit/api/research-request-stream/{trigger_id}` accepts the trigger ID returned by `POST /cockpit/api/research-request` (from W10) and opens an SSE stream for the research portion of that trigger. The cockpit button flow becomes: POST to create trigger → open EventSource for the research stream → render in the panel.

### Knob 4 — Retire HestiaLite

W12 added HestiaSentinel behind a settings flag and kept HestiaLite for one release. W13 deletes HestiaLite entirely:

- delete `src/theogony/agents/hestia_lite.py`
- delete `tests/test_hestia_lite.py`
- remove `HestiaLiteSettings` from `src/theogony/config/settings.py`
- remove the `HestiaLite | HestiaSentinel` union type in `argus.py`; constructor accepts `HestiaSentinel` only
- remove the legacy fallback path in `argus_wiring.py`
- update demo `.demo.env` to set `THEOGONY_CURIOSITY__HESTIA_SENTINEL__ENABLED=true` and remove any HestiaLite env vars

Add one test that asserts `Settings()` rejects `THEOGONY_CURIOSITY__HESTIA_LITE__*` env vars (the same pattern W10 used for `TRIGGER_THRESHOLD`).

### Knob 5 — Demo reset script + recording script update

`demo/reset_living_growth.sh`:

- enable: `THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true`
- enable: `THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED=true`
- enable: `THEOGONY_CURIOSITY__EVALUATOR__ENABLED=true`
- enable: `THEOGONY_CURIOSITY__HESTIA_SENTINEL__ENABLED=true`
- ensure: `THEOGONY_LLM__PROVIDER=anthropic`, `THEOGONY_LLM__MODEL_ID=claude-sonnet-4-6`
- check: refuse if `ANTHROPIC_API_KEY` not set (Wave 2 demo requires it; Wave 1 worked without)

`demo/living_growth.md` is **rewritten** to match the new flow. New 3-minute walk:

```
00:00  Cockpit open, chronicle close to empty (only pantheon_self).
00:10  User asks: "Wer war Sven Hedin und was hat er in Tibet erforscht?"
00:25  Answer arrives: cited 0 nodes, verdict=poor.
        "Argus sucht nach Quellen..." badge appears.
00:30  Research panel opens.
        Plan section fills: 3 steps —
          1. wikidata_lookup "Sven Hedin"
          2. wikipedia_fetch "Sven Hedin"
          3. gutenberg_search "Hedin Tibet"
00:55  Execution cards fill in:
         - Wikidata: 1 candidate (Q154759)
         - Wikipedia (de): 1 candidate (Sven Hedin, 47 KB)
         - Gutenberg: 3 candidates, top one #43497 Trans-Himalaya Vol.1
01:15  Evaluation: 3 selected, 1 rejected (duplicate of pantheon_self).
01:25  HestiaSentinel: all 3 approved (default-rule for wikipedia/wikidata/gutenberg).
01:35  Acquiring + ingesting in parallel; counters tick.
02:30  Ingest done: +312 nodes, +189 edges, 2 Wikidata Q-IDs cross-linked.
02:40  User re-asks the same question.
02:55  Long, well-cited answer with Hover-Lupe drill-down.
```

The "Lhasa zoom" finale stays as in W9 — tests another stub trigger as the final beat.

`docs/LIVING_DEMO.md` is updated to describe the research loop instead of the lookup loop.

### Knob 6 — Default cleanup

The W7-A `verdict_reasoning="curiosity trigger emitted"` text is updated everywhere it appears to `"research initiated for weak answer"` or `"research initiated by user request"`, depending on `trigger_reason`. Audit trail clarity.

The CuriosityRunReport gains a `total_cost_eur` field summing planner + evaluator + sentinel-fallback costs.

### Knob 7 — Backlog hygiene

Append to `docs/PHOENIX_BACKLOG.md`:

- PHX-0037: append `**Wave 2 closed (W10 + W11 + W12 + W13):** verdict-based trigger, LLM ResearchPlanner with Anthropic web_search tool, multi-source executor (Wikidata, Gutenberg, Wikipedia, generic web), HestiaSentinel per-candidate auditor, fully reworked cockpit research panel. Phase 3 remains open for: (a) federation-aware research (PHX-0061 dependency), (b) Mnemosyne self-reflective backlog auditor (PHX-0071 already filed), (c) human-in-the-loop review queue for HestiaSentinel "rejected" decisions.`
- PHX-0039 (Hestia full): append `**Partial coverage by W12 HestiaSentinel.** Per-candidate auditing with deterministic + LLM-fallback rules covers single-trigger acts. Still open: drift audit across many triggers over time, recursion budgets, person-as-target deep checks, regulatory dial.`

No new PHX tickets unless ones surface during implementation.

### Knob 8 — README + AGENT_SELF_INTEREST update

In `README.md` Living Demo section (added by W9): replace the link target description from "Gutenberg-only acquisition" to "Multi-source autonomous research with Wikidata, Wikipedia, Gutenberg, and open web; governed per-candidate by HestiaSentinel".

In `docs/AGENT_SELF_INTEREST.md`: add one paragraph at the end explaining that Pantheon now performs autonomous research using the agent's own LLM provider's web_search capability, so an agent calling `pantheon_ask` against a thin region triggers a real research action that fills the chronicle.

---

## Files to add / change

**New**

- (none structural; all changes are edits)

**Edit**

- `src/theogony/cockpit/growth_stream.py` — new vocabulary per Knob 1.
- `src/theogony/cockpit/static/js/explorer_growth.js` — rewrite for the three-section panel per Knob 2.
- `src/theogony/cockpit/templates/explorer.html` — three-section panel scaffolding.
- `src/theogony/cockpit/router.py` — add `GET /api/research-request-stream/{trigger_id}` endpoint.
- `src/theogony/agents/argus.py` — drop the union type per Knob 4.
- `src/theogony/curiosity/argus_wiring.py` — drop the legacy fallback per Knob 4.
- `src/theogony/config/settings.py` — drop `HestiaLiteSettings`.
- `src/theogony/curiosity/growth_bridge.py` — `verdict_reasoning` text update per Knob 6.
- `src/theogony/reporting/models.py` — `CuriosityRunReport.total_cost_eur` field.
- `demo/reset_living_growth.sh` — new env vars per Knob 5.
- `demo/living_growth.md` — rewritten 3-minute walk per Knob 5.
- `demo/living_growth_hosted.md` — same updates.
- `docs/LIVING_DEMO.md` — research-loop description.
- `README.md` — Living Demo section update.
- `docs/AGENT_SELF_INTEREST.md` — research paragraph.
- `docs/PHOENIX_BACKLOG.md` — Knob 7 appendings.
- `tests/cockpit/test_growth_stream.py` — assert new vocabulary.
- `tests/cockpit/test_research_request_stream_endpoint.py` (new file).

**Delete**

- `src/theogony/agents/hestia_lite.py`
- `tests/test_hestia_lite.py`

**Forbidden in this PR**

- Any change under `src/theogony/agents/research_*` (planner, evaluator). W11 stays stable.
- Any change under `src/theogony/acquisition/`. W11/W12 stay stable.
- Any new pytest marker.
- Any new dependency.

---

## Acceptance criteria (machine-runnable)

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/cockpit src/theogony/agents src/theogony/curiosity src/theogony/reporting/models.py src/theogony/config/settings.py
```

### A2 — Unit / integration tests

```bash
pytest -q tests/cockpit/test_growth_stream.py tests/cockpit/test_research_request_stream_endpoint.py
```

Required behaviours covered:

- `test_growth_stream_emits_planning_started_after_trigger`
- `test_growth_stream_emits_planning_step_search_per_web_search_call`
- `test_growth_stream_emits_executing_step_per_plan_step`
- `test_growth_stream_emits_step_candidates_per_step`
- `test_growth_stream_emits_evaluation_complete`
- `test_growth_stream_emits_hestia_review_per_candidate`
- `test_growth_stream_emits_acquired_then_ingested_in_order`
- `test_growth_stream_emits_research_complete_terminal`
- `test_research_request_stream_endpoint_returns_sse_with_trigger_replay`
- `test_old_w8_event_vocabulary_no_longer_emitted`

### A3 — Existing tests stay green

```bash
pytest -q
```

Including the legacy W8 cockpit tests, which must be **updated** to assert the new vocabulary (not retain assertions about the old). Old-vocabulary tests removed in this PR are listed in the PR body.

### A4 — Living-demo smoke

```bash
pytest -q -m living_demo
```

The smoke test now asserts:
- the new vocabulary appears in the SSE stream
- a CuriosityRunReport is written with `research_plan` populated
- at least one ingest_run_id appears in the report

### A5 — Manual demo dress rehearsal

After all of the above passes:

```bash
THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh
.venv/bin/theogony cockpit serve --host 127.0.0.1 --port 8000
# in browser: http://127.0.0.1:8000/cockpit/explorer?growth=on
# ask: "Wer war Sven Hedin und was hat er in Tibet erforscht?"
# observe the research panel filling in per the demo/living_growth.md script
```

Talos runs this once and pastes the observed phase sequence + final node/edge counts into the PR body. The actual recording is taken by the user after merge.

### A6 — HestiaLite gone

```bash
ls src/theogony/agents/hestia_lite.py 2>/dev/null && exit 1
ls tests/test_hestia_lite.py 2>/dev/null && exit 1
grep -r "hestia_lite" src/ tests/ && exit 1   # no references remain
```

These three commands must all return non-zero (i.e., not find the artefacts).

---

## STOP-and-file rules

- The cockpit's `EventSource` browser API does not handle `POST` requests, blocking the research-request-stream pattern → file PHX, stop. The W13 brief assumes a GET endpoint paired with the POST trigger creation; if that pattern needs different plumbing, escalate.
- The W11 planner does not actually emit `planning_step_search` events at the right granularity (Anthropic SDK does not surface per-tool-call events) → file PHX, stop. Worst case: collapse the planning_step_search events into a single aggregate count on `planning_complete` and document the degradation.
- Removing HestiaLite breaks more than 5 tests beyond `tests/test_hestia_lite.py` itself → file PHX, document the cascading dependency, stop. The deprecation should be near-clean by W12.

---

## PR description template

```
W13 — Research SSE vocabulary + cockpit panel rework + demo re-lock

Implements Living Demo Wave 2 slice 4 per docs/etappes/W13_research_demo_relock_brief.md.
Closes Wave 2. Builds on W10 + W11 + W12.

What this PR does:
- replaces the W8 SSE event vocabulary with research-shaped events
  (planning_started, executing_step, evaluation_complete, hestia_review, ...)
- rewrites the cockpit "Growth live" panel into a three-section "Research live"
  panel (Plan / Execution / Outcome)
- wires the W10 "research this further" button into a live SSE research stream
- retires HestiaLite (deletes module + tests + settings)
- updates the demo reset script + recording script + operator doc to reflect
  the multi-source research loop
- appends backlog hygiene per Knob 7

What this PR does NOT do:
- it does not change the planner / evaluator / executor / adapters
- it does not change ingest, retrieval, or extraction
- it does not record the demo (the user records after merge)

Old-vocabulary tests removed: <list>

Manual dress-rehearsal observed phase sequence:
<paste here>

Manual dress-rehearsal final counts:
<nodes_added, edges_added, wikidata_qids_linked, total_cost_eur>

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/cockpit src/theogony/agents src/theogony/curiosity
       src/theogony/reporting/models.py src/theogony/config/settings.py`
- `pytest -q`
- `pytest -q -m living_demo`
- manual dress rehearsal per A5
- HestiaLite-gone grep per A6

PHX tickets filed: <list, or "none">

Closes: Living Demo Wave 2 (W10-W13).
@hesiod-review
```
