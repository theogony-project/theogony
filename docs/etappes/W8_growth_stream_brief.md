# W8 — Live Growth Stream in the Cockpit (Living Demo, slice 3)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w8-growth-stream`
**Scope:** one PR
**Predecessor:** W7-A and W7-B merged to `main`
**Sprint slot:** Living Demo W8 (third of four)

This is the sprint that makes growth visible. It is also the sprint where the temptation to "improve the cockpit while we're at it" is greatest. Resist. The Living Demo Plan §3 explicitly froze every cockpit surface except the growth panel. A PR that polishes anything else is a brief violation.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (W7-B must be merged; if not, this brief is blocked).
2. `git checkout -b feat/w8-growth-stream`
3. After acceptance: `git push -u origin feat/w8-growth-stream` and open PR per template.

If W7-B is not on `main`: stop. Open a draft PR titled `[BLOCKED] feat(cockpit): W8 — waiting on W7-B`.

---

## Why this etappe exists

W7-A emits intent. W7-B acts on intent. Neither is visible to a human watching the cockpit. The demo recording requires a human-perceptible stream of phases: "trigger emitted → searching → 3 candidates → Hestia approved → fetching 1.2 MB → 743 sentences → 312 entities → 189 relations → done". Without that stream, the Living Demo recording does not exist.

W8 ships exactly that: an SSE endpoint, a small browser panel, and an opt-in flag on the Explorer query that wires the W7-A bridge + W7-B dispatcher into a single inline run that the user observes in real time.

---

## Locked knobs

### Knob 1 — One inline run, not a background worker

The cockpit's Explorer is the single user-facing entry point. When a query is sent with `?growth=on` (or `growth=true` in the JSON body), the request handler:

1. Runs the normal `QueryPipeline.ask` with the growth bridge enabled (W7-A behaviour).
2. If a `CuriosityTrigger` was emitted on this query, immediately runs Argus on that trigger inline (W7-B behaviour) inside the same SSE stream.
3. Streams every phase to the client.
4. Returns the final cockpit payload (already W7-A compatible) once Argus is done.

This is a **single inline run** initiated by the user click. It is not a background watcher, not a tick phase, not a websocket subscription. The latency is owned by the user's request.

If `?growth=on` is not set, behaviour is identical to today's `/cockpit/api/ask-stream`.

### Knob 2 — SSE endpoint

New endpoint: `POST /cockpit/api/growth-stream`. Mirrors the request shape of `POST /cockpit/api/ask-stream`. Adds one optional body field:

```json
{
  "q": "...",
  "k": 10,
  "hops": 2,
  "thinking_max": 2,
  "growth": true
}
```

If `growth` is missing or false, return HTTP 400 with `{"detail": "use /cockpit/api/ask-stream when growth is not requested"}`. This is a deliberate "no implicit fallthrough" guardrail — the endpoint is for the demo path only.

Reuse `stream_explorer_ask_sse`'s SSE machinery shape (line-framed `data:` events, optional `event:` types). Implement the new stream in `src/theogony/cockpit/growth_stream.py`, not by branching `explorer.py`.

### Knob 3 — SSE phase events (locked vocabulary)

Each event is a JSON object on a single `data:` line preceded by a typed `event:`. The vocabulary is closed:

| `event:` | Payload fields | When emitted |
|---|---|---|
| `query_phase` | `phase` ∈ {`embed`, `retrieve`, `synthesize`}; `elapsed_ms` | once per existing pipeline phase |
| `query_complete` | full Explorer payload (same shape as `/api/ask-stream` `complete`) | once, after synthesize |
| `trigger_emitted` | `trigger_id`, `gap_class`, `stub_signal_strength`, `proposed_search_query` | once, only if a trigger fired |
| `argus_phase` | `phase` ∈ {`search`, `score`, `hestia_review`, `fetch`, `extract_entities`, `extract_relations`, `embed_nodes`, `store`, `done`}; `count: int | None`; `elapsed_ms` | once per Argus phase |
| `argus_complete` | `outcome` (one of `ArgusOutcome`); `bytes_acquired`; `ingest_run_id`; `decision` (the `AcquisitionDecision` shape) | once, after Argus terminates |
| `error` | `where: str`; `message: str` | terminal; stream closes after |

`extract_entities`, `extract_relations`, `embed_nodes`, `store` are surfaced from the underlying ingest pipeline by **subscribing** to its existing per-stage events if they exist. If they do not, you may emit those phases as a single coarse "ingest" phase with `count=None` and a final aggregate count taken from the `IngestRunReport`. Do **not** add new instrumentation hooks to the ingest pipeline in this PR.

The vocabulary above is exact. Adding a new event type is a brief violation.

### Knob 4 — Explorer panel: "Growth live"

Add one new server-rendered panel to the Explorer template, hidden by default. Activated by the URL parameter `?growth=on` on `/cockpit/explorer`. When active:

- The Explorer's question form switches its submit URL to `/cockpit/api/growth-stream` instead of `/cockpit/api/ask-stream`.
- A new right-side panel labeled "Growth live" appears, scrolled to bottom, displaying each `argus_phase` event as a one-line readable record (e.g., `12:00:25 search → 3 candidates`).
- A small "growth=on" badge appears in the page header.

Unchanged when `?growth=on` is absent: the existing Explorer is byte-for-byte identical for the user.

Implement the UI changes in:

- `src/theogony/cockpit/templates/explorer.html` (hidden growth panel + conditional form action)
- `src/theogony/cockpit/static/js/explorer_growth.js` (new file, ~120 LOC)

Do not touch `explorer.js` for this. Keep the growth code in its own file so the existing Explorer behaviour cannot regress.

### Knob 5 — Server wiring

`src/theogony/cockpit/growth_stream.py` exports:

```python
async def stream_growth_run(
    *,
    settings: Settings,
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider | None,
    audit: ExtractionAuditLog | None,
    report_writer: RunReportWriter,
    query: str,
    k: int,
    hops: int,
    thinking_max: int,
    conversation_summary: str | None = None,
    conversation_messages: list[Any] | None = None,
) -> AsyncIterator[bytes]: ...
```

Internally it composes:

- the existing `stream_explorer_ask_sse` for the query phases
- the W7-A `GrowthBridge` (forced-enabled for this stream regardless of settings, because the user explicitly opted in)
- the W7-B `ArgusAgent` + `RealIngestRunner` (forced-enabled likewise)
- the locked event vocabulary from Knob 3

The forced-enable is **only inside this stream**. The settings defaults stay unchanged. Operators who do not opt in still get a fully default-off system.

### Knob 6 — Demo path budget guards (no surprise costs)

Even with Argus forced-enabled, the cockpit stream uses a defensive budget:

- `TriggerBudget(max_sources_to_fetch=1, max_total_bytes=2 * 1024 * 1024, max_llm_eur=0.50)` — passed into the trigger constructed inside the stream.
- If the user is on a `StubLLMProvider`, the synthesize phase still runs the offline answerer (existing behaviour). Argus's ingest still runs, and the cockpit will show the graph grow.

### Knob 7 — Router registration

Add the new endpoint to `src/theogony/cockpit/router.py` in `build_cockpit_router`. Place it next to `explorer_ask_stream`. Do not refactor the surrounding handlers. Do not change the `REPORT_TABS` tuple. Do not add a "growth" tab to the cockpit.

### Knob 8 — `?growth=on` rendering

Modify the `explorer_page` handler so that when the request's query string contains `growth=on` (or `growth=true`):

- Pass `growth_enabled=True` into the template context.
- The template conditionally includes the growth panel and `<script src="static/js/explorer_growth.js">`.

When the parameter is absent, the existing template renders byte-for-byte.

---

## Files to add / change

**New**

- `src/theogony/cockpit/growth_stream.py`
- `src/theogony/cockpit/static/js/explorer_growth.js`
- `tests/cockpit/test_growth_stream.py`
- `tests/cockpit/test_explorer_growth_panel.py`
- `tests/test_living_demo_w8_smoke.py`

**Edit**

- `src/theogony/cockpit/router.py` — register the new endpoint; thread `growth_enabled` flag into `explorer_page` template context.
- `src/theogony/cockpit/templates/explorer.html` — conditional growth panel + form action switch.

**Forbidden in this PR**

- Any change to `src/theogony/cockpit/explorer.py` beyond what is strictly necessary to expose the existing SSE machinery to `growth_stream.py` (and even that should be additive — no behaviour changes).
- Any change to `src/theogony/cockpit/static/js/explorer.js`.
- Any change to `src/theogony/cockpit/aggregations.py`, `manifest.py`, `sse.py`, `sample_mode.py`, `dependencies.py`.
- Any change to `REPORT_TABS` or the cockpit navigation.
- Any change to the standalone cockpit app (`standalone_app.py`).
- Any change under `src/theogony/agents/`, `src/theogony/curiosity/`. Argus + bridge are W7-* and stable.
- Any new dependency (no SSE library beyond what `starlette.responses.StreamingResponse` already gives).

---

## Acceptance criteria (machine-runnable)

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/cockpit/growth_stream.py src/theogony/cockpit/router.py
```

### A2 — Unit / integration tests

```bash
pytest -q tests/cockpit/test_growth_stream.py tests/cockpit/test_explorer_growth_panel.py
```

Required tests:

- `test_growth_stream_rejects_when_growth_flag_missing`
- `test_growth_stream_emits_query_phases_then_complete`
- `test_growth_stream_emits_trigger_when_thin`
- `test_growth_stream_emits_argus_phases_after_trigger`
- `test_growth_stream_emits_argus_complete_with_outcome`
- `test_explorer_page_default_does_not_include_growth_panel`
- `test_explorer_page_with_growth_on_includes_panel_and_script`
- `test_existing_explorer_ask_stream_byte_for_byte_unchanged_for_default_request`

### A3 — Existing tests stay green

```bash
pytest -q
```

### A4 — Living-demo smoke

```bash
pytest -q -m living_demo
```

`tests/test_living_demo_w8_smoke.py` exercises the full inline path end-to-end against `InMemoryKnowledgeStore` + `StubLLMProvider`, asserts the SSE stream contains every phase from Knob 3 in order, and asserts the resulting `CuriosityRunReport` and `IngestRunReport` are written to disk.

### A5 — Manual sanity (run locally before PR)

```bash
theogony cockpit serve  # in one terminal
# in another:
curl -N -X POST http://127.0.0.1:8000/cockpit/api/growth-stream \
     -H 'Content-Type: application/json' \
     -d '{"q":"who was Sven Hedin","growth":true}'
```

You should see typed `event:` lines flowing in real time. Document the observed phase sequence in the PR body.

---

## STOP-and-file rules

- The existing ingest pipeline emits no per-stage events that the stream can subscribe to **and** also has no clean way to be wrapped without duplicating its body. → emit a single coarse `argus_phase` named `ingest` and file PHX for proper instrumentation. (Acceptable degradation; explicitly mention it in the PR body.)
- The existing `stream_explorer_ask_sse` is too tightly coupled to be reused as a co-routine inside `stream_growth_run` without major refactoring. → file PHX, stop. Do not refactor `explorer.py` in this PR.
- The cockpit's request lifecycle does not allow `request.query_params` to reach the `explorer_page` handler. → file PHX, stop.

---

## PR description template

```
W8 — Live Growth Stream in the Cockpit

Implements Living Demo W8 per docs/etappes/W8_growth_stream_brief.md.
Builds on W7-A + W7-B.

What this PR does:
- adds POST /cockpit/api/growth-stream (SSE) for the inline demo path
- adds the "Growth live" Explorer panel, activated only by ?growth=on
- composes W7-A bridge + W7-B Argus inside the inline stream with forced-enable
- ships locked SSE event vocabulary (query_phase, trigger_emitted, argus_phase, ...)

What this PR does NOT do:
- it does not change default settings
- it does not change the existing Explorer in any user-visible way
- it does not add background workers, tick phases, or new tabs
- it does not touch any frozen surface from the Living Demo Plan §3

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/cockpit/growth_stream.py src/theogony/cockpit/router.py`
- `pytest -q`
- `pytest -q -m living_demo`
- the manual SSE curl above

Manual SSE phase sequence observed:
<paste here>

PHX tickets filed in this PR: <list, or "none">

@hesiod-review
```
