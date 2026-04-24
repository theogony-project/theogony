# W7-A — CuriosityTrigger + GrowthBridge (Living Demo, slice 1)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w7a-curiosity-trigger`
**Scope:** one PR
**Predecessor:** Living Demo Plan (`docs/plans/LIVING_DEMO_PLAN.md`)
**Sprint slot:** Living Demo W7-A (first of four)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

You are running in Cursor auto-mode. Before any code:

1. `git checkout main && git pull --ff-only origin main`
2. `git checkout -b feat/w7a-curiosity-trigger`

After all acceptance criteria pass:

3. `git push -u origin feat/w7a-curiosity-trigger`
4. `gh pr create --base main --title "feat(curiosity): W7-A — CuriosityTrigger + GrowthBridge (PHX-0037 slice 1)"` with the body shape at the bottom of this brief.

If the sprint cannot complete (real ambiguity, real blocker), open a draft PR with `[BLOCKED]` in the title, file a PHX ticket, and stop. Do not improvise around the brief.

---

## Why this etappe exists

The chronicle today emits a [`StubVerdict`](../../src/theogony/reporting/models.py#L245) and a [`RegionDescriptor`](../../src/theogony/reporting/models.py#L268) on every `QueryRunReport`. They are pure observations. Nothing in the system reads them and decides to grow.

W7-A turns those observations into a typed, auditable **decision-shaped object** — a `CuriosityTrigger` — and the small **GrowthBridge** that emits it when a query reveals a real gap. No acquisition yet. The trigger is evidence and intent.

This is the schema spine for W7-B (Argus), W8 (live cockpit panel), and W9 (recording). Get the shape right; everything downstream depends on it.

---

## Locked knobs

### Knob 1 — `CuriosityTrigger` shape

```python
class GapClass(StrEnum):
    ENTITY_UNKNOWN = "entity_unknown"
    REGION_THIN = "region_thin"
    EDGE_DENSITY_LOW = "edge_density_low"


class TriggerBudget(BaseModel):
    """Hard ceilings the downstream agent must honour."""

    model_config = ConfigDict(extra="forbid")

    max_sources_to_fetch: int = Field(default=1, ge=1, le=5)
    max_total_bytes: int = Field(default=2 * 1024 * 1024, ge=1)  # 2 MiB
    max_llm_eur: float = Field(default=0.50, ge=0.0)


class AcquisitionSpec(BaseModel):
    """Hint to the acquisition agent about where to look."""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["gutenberg"] = "gutenberg"  # v1 allowlist
    search_query: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=500)


class CuriosityTrigger(BaseModel):
    """Typed intent to grow the chronicle in a focused region (PHX-0037 slice 1)."""

    model_config = ConfigDict(extra="forbid")

    trigger_id: str = Field(default_factory=new_run_id)
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    origin_query: str
    origin_query_run_id: str

    gap_class: GapClass
    region_descriptor: RegionDescriptor
    stub_signal_strength: float = Field(ge=0.0, le=1.0)

    proposed_acquisition_spec: AcquisitionSpec
    budget: TriggerBudget
```

`source_type` is a `Literal["gutenberg"]` in W7-A. Do not parameterise it for "future flexibility". W7-B will not need it. Web acquisition is forbidden in v1. The widening to a real Literal union is a future PHX, not yours.

### Knob 2 — `GapClass` derivation rules (deterministic)

The bridge picks exactly one `GapClass` per trigger, in the following priority:

1. If `stub_verdict.poor_named_entity_coverage` is true → `ENTITY_UNKNOWN`.
2. Else if `stub_verdict.low_node_count` is true → `REGION_THIN`.
3. Else → `EDGE_DENSITY_LOW`.

These three classes cover the existing `StubVerdict` boolean flags meaningfully without inventing more vocabulary.

### Knob 3 — `proposed_acquisition_spec.search_query` derivation

Deterministic, no LLM:

- If `gap_class == ENTITY_UNKNOWN` and `region_descriptor.dominant_node_type` is not None → `f"{origin_query}"` (the user's own words; the named entities are inside).
- Else → `f"{origin_query}"`.

Yes, both branches use the original query verbatim today. The branching exists so a Phase-2 ticket can sharpen `ENTITY_UNKNOWN` (e.g., "extract the unresolved entity name and search by that") without reshaping the schema. **Do not implement that sharpening now.** The Phase-1 contract is "user query goes through; auditor can see why".

`rationale` is a short human-readable string, deterministic template:

```python
rationale = (
    f"gap_class={gap_class.value} "
    f"stub_signal_strength={stub_signal_strength:.2f} "
    f"seed_node_count={region_descriptor.seed_node_count}"
)
```

### Knob 4 — `Settings.curiosity.growth_bridge`

Extend [`CuriositySettings`](../../src/theogony/config/settings.py#L503):

```python
class GrowthBridgeSettings(BaseModel):
    """Couple stub detection to acquisition triggers (Living Demo W7-A)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    trigger_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_triggers_per_query: int = Field(default=1, ge=1, le=5)


class CuriositySettings(BaseModel):
    # ... existing fields stay verbatim ...
    growth_bridge: GrowthBridgeSettings = Field(default_factory=GrowthBridgeSettings)
```

Default `enabled=False` is mandatory. The demo path enables it explicitly via `THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true`. Do not flip the default; do not add a "convenience" auto-enable.

### Knob 5 — `GrowthBridge` behaviour

```python
class GrowthBridge:
    """Emit at most one CuriosityTrigger per query when the stub signal warrants it."""

    def __init__(self, settings: GrowthBridgeSettings) -> None:
        self._settings = settings

    def maybe_emit(
        self,
        *,
        origin_query: str,
        origin_query_run_id: str,
        stub_verdict: StubVerdict,
        region_descriptor: RegionDescriptor,
    ) -> CuriosityTrigger | None:
        ...
```

Logic:

- If `not self._settings.enabled` → return `None`.
- If `stub_verdict.stub_signal_strength < self._settings.trigger_threshold` → return `None`.
- Pick `gap_class` per Knob 2.
- Build the trigger per Knob 1 + Knob 3.
- Return it.

The bridge is **pure** (no I/O, no store access, no async). All persistence happens via the `CuriosityRunReport` written by the caller.

### Knob 6 — `CuriosityRunReport`

New report type. Add to [`reporting/models.py`](../../src/theogony/reporting/models.py):

```python
class AcquisitionDecision(BaseModel):
    """Argus + HestiaLite outcome (W7-B will populate; W7-A leaves None)."""

    model_config = ConfigDict(extra="forbid")

    candidate_source_type: str | None = None
    candidate_identifier: str | None = None
    candidate_title: str | None = None
    hestia_status: Literal["not_evaluated", "approved", "rejected"] = "not_evaluated"
    hestia_reason: str = ""
    ingest_run_id: str | None = None


class CuriosityRunReport(RunReportBase):
    """One end-to-end curiosity loop run (PHX-0037)."""

    report_type: Literal["curiosity"] = "curiosity"
    trigger: CuriosityTrigger
    decision: AcquisitionDecision = Field(default_factory=AcquisitionDecision)
    bytes_acquired: int = Field(default=0, ge=0)
```

Extensions required (and only these) to existing schemas:

- Extend `RunReportBase.report_type` Literal to include `"curiosity"`.
- Add `"curiosity"` to wherever the writer enumerates report types (search for the existing `"blindspot"` registration; mirror it exactly).

**Do not** add `curiosity` to `REPORT_TABS` in `cockpit/router.py`. That is W8 territory.

### Knob 7 — `RunReportWriter` directory

`run_reports/curiosity/<run_id>.json`. Mirror the `blindspot` shape line-for-line in the writer registration. No new file format. No new schema-on-disk versioning.

### Knob 8 — Pipeline hook point

In [`retrieval/pipeline.py`](../../src/theogony/retrieval/pipeline.py) around the existing `_finalize_report` method, after `stub_verdict` and `region_descriptor` are computed (around line 555):

```python
# --- W7-A: emit curiosity trigger if growth bridge is enabled
if self._growth_bridge is not None:
    trigger = self._growth_bridge.maybe_emit(
        origin_query=query,
        origin_query_run_id=report.run_id,
        stub_verdict=stub_verdict,
        region_descriptor=region_descriptor,
    )
    if trigger is not None:
        curiosity_report = CuriosityRunReport(
            report_type="curiosity",
            started_at=report.started_at,
            finished_at=report.finished_at,
            duration_s=report.duration_s,
            status="completed",
            verdict="good",
            verdict_reasoning="curiosity trigger emitted",
            trigger=trigger,
        )
        self._report_writer.write(curiosity_report)
```

Inject `growth_bridge: GrowthBridge | None = None` into `QueryPipeline.__init__`. Default-construct from settings only when the bridge is actually wired in `build_query_pipeline_from_settings` (the existing factory below `QueryPipeline`). Default of the optional argument stays `None` so unit tests that construct `QueryPipeline` directly are not forced to know about it.

### Knob 9 — No retries, no concurrency, no async on emit

`maybe_emit` is sync. The pipeline is already async; calling a sync method from inside it is fine. Do not wrap it in `asyncio.to_thread`. Do not retry. Do not background-task the writer call.

---

## Files to add / change

**New**

- `src/theogony/curiosity/trigger.py` — the four Pydantic models from Knob 1, plus `GapClass` enum.
- `src/theogony/curiosity/growth_bridge.py` — the `GrowthBridge` class.
- `tests/test_curiosity_trigger.py` — schema round-trip + `extra="forbid"` enforcement.
- `tests/test_curiosity_growth_bridge.py` — bridge logic per Knob 5 (enabled/disabled, threshold, GapClass priority).
- `tests/test_curiosity_run_report.py` — `CuriosityRunReport` JSON round-trip + writer integration.

**Edit**

- `src/theogony/config/settings.py` — add `GrowthBridgeSettings`, attach to `CuriositySettings`.
- `src/theogony/reporting/models.py` — add `AcquisitionDecision`, `CuriosityRunReport`; extend `RunReportBase.report_type` Literal.
- `src/theogony/reporting/writer.py` — register `"curiosity"` directory analogous to `"blindspot"`.
- `src/theogony/retrieval/pipeline.py` — inject `GrowthBridge` and call per Knob 8.
- `tests/test_retrieval_pipeline.py` — extend with one bridge-enabled / one bridge-disabled scenario.

**Forbidden in this PR**

- Any change under `src/theogony/agents/`, `src/theogony/acquisition/`, `src/theogony/cockpit/`. Those belong to W7-B and W8.
- Any new dependency in `pyproject.toml`.
- Any change to `MorpheusPhase`, `DepthBandPhase`, `ReclusterPhase`, `BlindSpotAggregationPhase`, `PheromoneDecayPhase`, `MnemosynePhase`. They are frozen-for-demo per `docs/plans/LIVING_DEMO_PLAN.md`.
- Any change to existing default-on tick phases.

---

## Acceptance criteria (machine-runnable)

All of these must pass before opening the PR.

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/curiosity src/theogony/reporting src/theogony/retrieval/pipeline.py src/theogony/config/settings.py
```

Exit 0. No new ignore comments.

### A2 — New unit tests pass

```bash
pytest -q tests/test_curiosity_trigger.py tests/test_curiosity_growth_bridge.py tests/test_curiosity_run_report.py
```

Each test file exercises one concept. Aim for ~4–8 small tests per file. Examples (write more if a behaviour is not covered):

- `test_curiosity_trigger_round_trip_json`
- `test_curiosity_trigger_rejects_unknown_field` (the `extra="forbid"` guarantee)
- `test_growth_bridge_disabled_returns_none`
- `test_growth_bridge_below_threshold_returns_none`
- `test_growth_bridge_gap_class_entity_unknown_priority`
- `test_growth_bridge_gap_class_region_thin`
- `test_growth_bridge_gap_class_edge_density_low_default`
- `test_curiosity_run_report_round_trip`
- `test_writer_writes_curiosity_to_correct_directory`

### A3 — Existing test suite stays green

```bash
pytest -q
```

Exit 0. No new failures, no new skips, no new xfails.

### A4 — Default-off contract

```bash
pytest -q tests/test_retrieval_pipeline.py
```

The bridge is wired into the pipeline factory. Default `Settings()` has `enabled=False`. Existing tests that exercise the pipeline with default settings must produce **zero** files in `run_reports/curiosity/`.

Add one new test to `tests/test_retrieval_pipeline.py`:

- `test_query_pipeline_with_growth_bridge_enabled_writes_curiosity_report` — set `enabled=True`, threshold low, run a query against an intentionally thin in-memory store, assert exactly one `CuriosityRunReport` lands on disk and matches the expected `gap_class`.

### A5 — Demo-path E2E smoke (mandatory; not mock-only)

Add a small smoke script under `tests/test_living_demo_w7a_smoke.py`:

```python
@pytest.mark.living_demo
async def test_growth_bridge_demo_path_smoke(tmp_path) -> None:
    """W7-A demo path: a thin query enabled-bridge produces a curiosity report on disk."""
    ...
```

Mark `living_demo` as a real pytest marker in `pyproject.toml` (or `pytest.ini` — match whatever the repo uses). Selectable as:

```bash
pytest -q -m living_demo
```

Must pass. This is the truthful demo gate. Mock-only-green is not green. Use the `InMemoryKnowledgeStore` and the `StubLLMProvider` so this test does not touch real services and does not cost money.

---

## STOP-and-file rules

If any of the following is true, **do not improvise**. Open a draft PR titled `[BLOCKED] feat(curiosity): W7-A …`, write a one-paragraph "what I found" in the PR body, file a PHX ticket, and stop:

- The `RunReportWriter` registration of report types is not a simple enumeration mirror of `"blindspot"`. (E.g., it requires a non-trivial dispatch table you cannot extend without rewriting it.)
- `RunReportBase.report_type` Literal cannot be widened without breaking the existing JSON schemas on disk in `data/run_reports/`.
- The pipeline factory has no clean injection point for `GrowthBridge` and would require restructuring more than 30 lines.
- Mypy fails on the new modules with errors that demand `# type: ignore` rather than a fix.

---

## PR description template

```
W7-A — CuriosityTrigger + GrowthBridge

Implements PHX-0037 slice 1 per docs/etappes/W7A_curiosity_trigger_brief.md.

What this PR does:
- adds the typed CuriosityTrigger / TriggerBudget / AcquisitionSpec / GapClass schemas
- adds the GrowthBridge that emits at most one trigger per query when enabled
- adds the CuriosityRunReport report type and writer registration
- wires the bridge into the QueryPipeline behind a default-off settings flag
- ships unit tests + one demo-path E2E smoke (`pytest -m living_demo`)

What this PR does NOT do:
- it does not acquire anything (W7-B)
- it does not change the cockpit (W8)
- it does not touch any default-off frozen tick phase
- it does not enable the bridge by default

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/curiosity src/theogony/reporting src/theogony/retrieval/pipeline.py src/theogony/config/settings.py`
- `pytest -q`
- `pytest -q -m living_demo`

PHX tickets filed in this PR: <list, or "none">

Living Demo Plan reference: docs/plans/LIVING_DEMO_PLAN.md (W7-A row)

@hesiod-review
```
