# W10 — Research trigger semantics + ResearchPlan schema (Living Demo Wave 2, slice 1)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w10-research-trigger-semantics`
**Scope:** one PR
**Predecessor:** Wave 1 (W7-A, W7-B, W8, W9) merged on `main`. Wave 2 plan amendment in `docs/plans/LIVING_DEMO_PLAN.md`.
**Sprint slot:** Living Demo W10 (first of four in Wave 2)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main`
2. `git checkout -b feat/w10-research-trigger-semantics`
3. Implement.
4. `git push -u origin feat/w10-research-trigger-semantics`
5. `gh pr create --base main --title "feat(curiosity): W10 — trigger semantics fix + ResearchPlan schema"` with the body shape at the bottom.

If the sprint is genuinely blocked, open a draft PR titled `[BLOCKED] feat(curiosity): W10 …`, file a PHX ticket, stop.

---

## Why this etappe exists

The Wave 1 demo proved that the loop closes mechanically. It also proved that the loop closes for the wrong reasons and produces unconvincing output. The trigger fires on graph topology (constellation thinness) instead of on whether the synthesized answer actually satisfied the user. Strong answers (verdict=good) trigger pointless Gutenberg searches that return zero results. The cockpit looks like a system that fails politely.

W10 fixes that gating. It also adds the `ResearchPlan` schema field that W11 will populate — landing the schema first means W11's PR is purely behavioural and easier to review.

W10 ships **no new LLM call, no new adapter, no new UI**. It is the structural minimum: change the gate, extend the trigger schema, plumb the manual cockpit button.

---

## Locked knobs

### Knob 1 — Trigger gate is verdict-based, not topology-based

Today `GrowthBridge.maybe_emit` gates on `stub_verdict.stub_signal_strength >= settings.curiosity.growth_bridge.trigger_threshold`. This gate is replaced by:

```python
def maybe_emit(
    self,
    *,
    origin_query: str,
    origin_query_run_id: str,
    answer_verdict: Literal["good", "partial", "poor", "failed"],
    cited_node_count: int,
    stub_verdict: StubVerdict,
    region_descriptor: RegionDescriptor,
    explicit_user_request: bool = False,
) -> CuriosityTrigger | None:
    ...
```

Decision rules (locked, in this exact order):

1. If `not self._settings.enabled` → return `None`.
2. If `explicit_user_request` is True → emit (skip all other checks; user said yes). Set `trigger.gap_class` per Knob 2; set `trigger.trigger_reason="user_request"`.
3. If `answer_verdict in ("partial", "poor", "failed")` AND `cited_node_count < self._settings.min_cited_for_no_research` → emit. Set `trigger.trigger_reason="weak_answer"`.
4. Otherwise → return `None`.

Note that `stub_signal_strength` no longer participates in the gate. It is still recorded on the trigger as evidence (it is a useful debug signal; just not the gate). The `stub_verdict` parameter is also still used to derive `gap_class` per Knob 2 (so the field-extraction logic in Knob 2 below remains intact).

### Knob 2 — `gap_class` derivation rule (refined)

Same priority order as the W7-A version, but it now uses a wider set of signals because the verdict-based gate no longer filters out the "answer was good but constellation looked thin" cases:

1. If `cited_node_count == 0` AND `stub_verdict.poor_named_entity_coverage` is True → `ENTITY_UNKNOWN`.
2. Else if `cited_node_count <= 1` → `REGION_THIN`.
3. Else if `stub_verdict.low_edge_density` is True → `EDGE_DENSITY_LOW`.
4. Else (verdict was `partial`/`poor` despite reasonable citation count) → `REGION_THIN` (treat as the most general gap; the planner in W11 will refine).

The `GapClass` enum stays unchanged.

### Knob 3 — `trigger_reason` field on `CuriosityTrigger`

Add to `src/theogony/curiosity/trigger.py`:

```python
class TriggerReason(StrEnum):
    WEAK_ANSWER = "weak_answer"
    USER_REQUEST = "user_request"


class CuriosityTrigger(BaseModel):
    # ... existing fields stay verbatim ...
    trigger_reason: TriggerReason  # NEW, mandatory, no default
    answer_verdict: Literal["good", "partial", "poor", "failed"]  # NEW, mandatory
    cited_node_count: int = Field(ge=0)  # NEW, mandatory
```

These are mandatory so the auditor can replay the gate decision deterministically. There is no migration story for old triggers on disk; the existing `CuriosityRunReport` JSON files from the demo runs become unreadable when this PR lands. That is acceptable — the demo data is throwaway. Add a one-line note to the PR body about this.

### Knob 4 — `ResearchPlan` schema (skeleton only; W11 populates)

Add to `src/theogony/curiosity/trigger.py`:

```python
class ResearchStepKind(StrEnum):
    WIKIDATA_LOOKUP = "wikidata_lookup"        # by name or by Q-id
    GUTENBERG_SEARCH = "gutenberg_search"      # by query string
    WIKIPEDIA_FETCH = "wikipedia_fetch"        # by article title
    WEB_FETCH = "web_fetch"                    # by URL


class ResearchStep(BaseModel):
    """One typed planned step. The Planner (W11) constructs this; W10 only defines the shape."""

    model_config = ConfigDict(extra="forbid")

    kind: ResearchStepKind
    target: str = Field(min_length=1, max_length=500)
    rationale: str = Field(default="", max_length=500)
    expected_evidence_kind: Literal["entity", "biographical", "geographic", "primary_text", "encyclopedic", "current_events"] = "encyclopedic"


class ResearchPlan(BaseModel):
    """A small typed plan; produced by the LLM planner in W11."""

    model_config = ConfigDict(extra="forbid")

    steps: list[ResearchStep] = Field(default_factory=list, max_length=5)
    planner_model_id: str = ""           # populated by W11
    planner_cost_eur: float = Field(default=0.0, ge=0.0)


class CuriosityTrigger(BaseModel):
    # ... existing fields ...
    research_plan: ResearchPlan | None = None   # NEW; W10 leaves None, W11 fills
```

`ResearchStepKind` deliberately omits a `WEB_SEARCH` value. Web search is a tool the planner LLM uses internally to construct fetch-by-URL steps; it is not a step kind. The planner emits e.g. `WEB_FETCH(url="https://en.wikipedia.org/wiki/Sven_Hedin")` after running the tool, not `WEB_SEARCH(query="Sven Hedin")`.

### Knob 5 — Settings update

Edit `src/theogony/config/settings.py`:

```python
class GrowthBridgeSettings(BaseModel):
    """Couple verdict + user request to acquisition triggers (Wave 2 W10)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    min_cited_for_no_research: int = Field(default=3, ge=0, le=20)
    max_triggers_per_query: int = Field(default=1, ge=1, le=5)
    # `trigger_threshold` is REMOVED. Stub_signal_strength no longer gates emission.
```

If old YAML / .env files still set `THEOGONY_CURIOSITY__GROWTH_BRIDGE__TRIGGER_THRESHOLD`, pydantic-settings should error on the unknown field (extra="forbid"). That is the intended behaviour: the demo `.demo.env` file shipped by W9 must be updated as part of this PR.

Update the W9 reset script `demo/reset_living_growth.sh` to write the new env shape into `.demo.env`. Specifically: drop `THEOGONY_CURIOSITY__GROWTH_BRIDGE__TRIGGER_THRESHOLD` if it appears, leave `THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true` in place.

### Knob 6 — `QueryPipeline._finalize_report` rewiring

In `src/theogony/retrieval/pipeline.py` around the existing growth-bridge call (search for `self._growth_bridge.maybe_emit`), update the call site to pass the new mandatory parameters:

```python
trigger = self._growth_bridge.maybe_emit(
    origin_query=query,
    origin_query_run_id=report.run_id,
    answer_verdict=verdict,           # already in scope from query_verdict() above
    cited_node_count=cited_count,     # already in scope
    stub_verdict=stub_verdict,
    region_descriptor=region_descriptor,
    explicit_user_request=False,      # the pipeline path always sets False; cockpit path sets True
)
```

Add a public helper on `QueryPipeline` for the manual button path:

```python
async def emit_user_research_request(
    self,
    *,
    origin_query: str,
    origin_query_run_id: str,
    answer_verdict: Literal["good", "partial", "poor", "failed"],
    cited_node_count: int,
    stub_verdict: StubVerdict,
    region_descriptor: RegionDescriptor,
) -> CuriosityTrigger | None:
    """Emit a trigger as if the user clicked 'research this further'."""
    if self._growth_bridge is None or self._report_writer is None:
        return None
    trigger = self._growth_bridge.maybe_emit(
        origin_query=origin_query,
        origin_query_run_id=origin_query_run_id,
        answer_verdict=answer_verdict,
        cited_node_count=cited_node_count,
        stub_verdict=stub_verdict,
        region_descriptor=region_descriptor,
        explicit_user_request=True,
    )
    if trigger is None:
        return None
    # The W7-A finalize_report shape writes the CuriosityRunReport. Re-use that logic
    # via a small private helper extracted in this PR. Do not duplicate the writer call.
    self._write_curiosity_report_for(trigger)
    return trigger
```

### Knob 7 — Cockpit "research this further" button (minimal UI)

Add to `src/theogony/cockpit/templates/explorer.html`, only when `growth_enabled` is True:

- a small button labelled "Research this further" beneath each completed answer
- the button POSTs to a new endpoint `POST /cockpit/api/research-request` with `{run_id, query}`
- on success, the cockpit shows a small toast "Research requested" — no new SSE stream in this PR (W11 will hook it into the growth stream)

New endpoint in `src/theogony/cockpit/router.py`:

```python
@router.post("/api/research-request", response_class=JSONResponse)
async def explorer_research_request(...):
    """Emit a CuriosityTrigger with explicit_user_request=True for the named completed run."""
    ...
```

The endpoint reads the named `QueryRunReport` from disk, reconstructs the parameters needed for `emit_user_research_request`, calls the helper, returns `{trigger_id}` or `{trigger_id: null}` when the bridge is disabled.

The button does **not** trigger Argus in this PR. W11 wires planning; W12 wires acquisition; this PR only makes the trigger fire. Watch for "research request received but nothing happens" cockpit feedback being clear: explicit toast says "Trigger emitted; planning + acquisition land in W11/W12."

### Knob 8 — Tests for the deprecation

When the user has `THEOGONY_CURIOSITY__GROWTH_BRIDGE__TRIGGER_THRESHOLD` in their env or .demo.env after W9, the system should fail loudly at startup. Add one test that asserts pydantic raises on the unknown field:

```python
def test_old_trigger_threshold_setting_raises_validation_error(monkeypatch):
    monkeypatch.setenv("THEOGONY_CURIOSITY__GROWTH_BRIDGE__TRIGGER_THRESHOLD", "0.5")
    with pytest.raises(ValidationError):
        Settings()
```

This is a hard fail by design — silent ignore would let users believe the old gate still works.

---

## Files to add / change

**New**

- `tests/test_w10_trigger_semantics.py` — gate behaviour, gap_class refinement, ResearchPlan schema round-trip, deprecation guard.
- `tests/cockpit/test_research_request_endpoint.py` — POST /cockpit/api/research-request happy path + bridge-disabled path.

**Edit**

- `src/theogony/curiosity/trigger.py` — add `TriggerReason`, `ResearchStepKind`, `ResearchStep`, `ResearchPlan`; extend `CuriosityTrigger` with `trigger_reason`, `answer_verdict`, `cited_node_count`, `research_plan`.
- `src/theogony/curiosity/growth_bridge.py` — replace gate per Knob 1; refine gap_class derivation per Knob 2.
- `src/theogony/config/settings.py` — drop `trigger_threshold`; add `min_cited_for_no_research`.
- `src/theogony/retrieval/pipeline.py` — update `maybe_emit` call site (Knob 6); extract `_write_curiosity_report_for`; add `emit_user_research_request`.
- `src/theogony/cockpit/router.py` — add `POST /api/research-request`.
- `src/theogony/cockpit/templates/explorer.html` — add the conditional button + minimal JS handler (~30 LOC).
- `src/theogony/cockpit/static/js/explorer_growth.js` — add the button handler (post + toast).
- `demo/reset_living_growth.sh` — drop the obsolete env var.
- `tests/test_curiosity_trigger.py` — extend the existing W7-A tests with the new fields.
- `tests/test_curiosity_growth_bridge.py` — update tests to match the new gate.
- `tests/test_retrieval_pipeline.py` — update wiring tests.

**Forbidden in this PR**

- Any new LLM call. The planner is W11.
- Any new acquisition adapter. W12.
- Any change under `src/theogony/agents/`. The Argus refactor is W11.
- Any change to `src/theogony/cockpit/growth_stream.py` beyond minimal field-name updates if absolutely required by the trigger schema change. The SSE vocabulary change is W13.
- Any new dependency.
- Any backlog clean-up.

---

## Acceptance criteria (machine-runnable)

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/curiosity src/theogony/config/settings.py src/theogony/retrieval/pipeline.py src/theogony/cockpit/router.py
```

### A2 — Unit tests

```bash
pytest -q tests/test_w10_trigger_semantics.py tests/cockpit/test_research_request_endpoint.py
```

Required behaviours covered:

- `test_gate_returns_none_when_disabled`
- `test_gate_returns_none_on_good_verdict_even_if_constellation_thin`
- `test_gate_emits_on_partial_verdict_with_low_citations`
- `test_gate_emits_on_explicit_user_request_regardless_of_verdict`
- `test_gap_class_priority_entity_unknown_first`
- `test_research_plan_schema_round_trip`
- `test_research_plan_max_5_steps_enforced`
- `test_old_trigger_threshold_setting_raises_validation_error`
- `test_research_request_endpoint_emits_trigger_with_user_request_reason`
- `test_research_request_endpoint_returns_null_when_bridge_disabled`

### A3 — Existing test suite stays green

```bash
pytest -q
```

Including the W7-A / W7-B / W8 / W9 tests. Where a test asserts the old gate behaviour, it must be **replaced** (not deleted silently). Old-gate tests removed in this PR are listed in the PR body.

### A4 — Living-demo smoke

```bash
pytest -q -m living_demo
```

The W7-A smoke test must be updated to use the new gate path (verdict-based). The W8 cockpit smoke must continue to pass without changes (no SSE vocabulary changes in W10).

### A5 — Manual reset script sanity

```bash
THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh
cat .demo.env
```

`.demo.env` must not contain `TRIGGER_THRESHOLD` and must contain `ENABLED=true`. Then verify:

```bash
.venv/bin/theogony cockpit serve --host 127.0.0.1 --port 8000
# in another shell:
curl -s -X POST http://127.0.0.1:8000/cockpit/api/research-request \
     -H 'Content-Type: application/json' \
     -d '{"run_id":"<some recent query run_id>","query":"What does Daedalus do?"}'
```

The response should contain a `trigger_id` and a written `CuriosityRunReport` should appear in `data/run_reports/curiosity/`.

---

## STOP-and-file rules

- The pydantic-settings deprecation guard cannot be implemented without rewriting `Settings` plumbing → file PHX, stop. Use a plain `__init_subclass__` or model validator if the standard `extra="forbid"` does not catch the env var.
- The cockpit template structure makes it impossible to add a button beneath answers without editing more than 30 LOC of `explorer.html` → file PHX, document the cockpit-template debt, stop.
- The `QueryPipeline.ask` flow does not yield a clean place to extract `_write_curiosity_report_for` without a >100 LOC refactor → file PHX, stop. (You should be able to extract a 10-15 LOC helper.)

---

## PR description template

```
W10 — Research trigger semantics + ResearchPlan schema

Implements Living Demo Wave 2 slice 1 per docs/etappes/W10_research_trigger_semantics_brief.md.
Builds on Wave 1 (W7-A through W9). Sister sprint of W11/W12/W13.

What this PR does:
- replaces the constellation-thinness trigger gate with a verdict-based gate
  (fires only on partial/poor verdict OR explicit user request)
- extends CuriosityTrigger with trigger_reason / answer_verdict /
  cited_node_count / research_plan (skeleton only; populated in W11)
- adds the ResearchPlan / ResearchStep schemas (no behaviour yet)
- adds POST /cockpit/api/research-request and the cockpit button
- removes the now-obsolete trigger_threshold setting (loud failure on stale
  env vars; .demo.env updated)

What this PR does NOT do:
- it does not add the LLM planner (W11)
- it does not add any new acquisition adapter (W12)
- it does not change the SSE vocabulary (W13)
- it does not delete CuriosityRunReport files on disk (they become unreadable
  by design; the demo data is throwaway — see PR body note)

Old-gate tests removed: <list>

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/curiosity src/theogony/config/settings.py
       src/theogony/retrieval/pipeline.py src/theogony/cockpit/router.py`
- `pytest -q`
- `pytest -q -m living_demo`
- manual reset + research-request POST per A5

PHX tickets filed: <list, or "none">

@hesiod-review
```
