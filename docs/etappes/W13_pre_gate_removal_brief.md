# W13 — Pre-Gate Removal (Living Demo Wave 3, slice 1)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-25
**Branch:** `feat/w13-pre-gate-removal`
**Scope:** one PR (agent code + config + cockpit vocabulary + docs; no new data-model schema)
**Predecessor:** W10, W11, W12 merged on `main`; Doctrine PR #97 merged on `main`.
**Sprint slot:** Living Demo W13 (first in Wave 3)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (W10/11/12 and Doctrine PR #97 must all be merged; if not, this brief is blocked).
2. `git checkout -b feat/w13-pre-gate-removal`
3. Implement.
4. `git push -u origin feat/w13-pre-gate-removal`
5. `gh pr create --base main --title "feat(curiosity): W13 — pre-gate removal + verification pool stub + cockpit vocab update"` with the PR body shape at the bottom.

---

## Why this etappe exists

W10-W12 built a real research loop. That loop still runs Argus candidates through `HestiaSentinel` — a synchronous content-judge gate — before anything touches the ingest pipeline. The gate works, but it is architecturally wrong.

The immune-system doctrine (`docs/IMMUNE_SYSTEM.md`) forbids synchronous content-judge pre-gates entirely. Content must flow into the chronicle without a gate; a background organism (Athene / Chronos / Nemesis / Eris / Mnemosyne) samples and acts asynchronously.

W13 implements that inversion:

- Removes `HestiaLite` and `HestiaSentinel` from the ingest path.
- Routes all acquired content into a typed **verification pool** (a lightweight stub for now; the full pool is Athene's W14 work).
- Updates the cockpit SSE vocabulary so the user sees the open-flow posture (`acquired_into_pool`) instead of the clinic posture (`hestia_review`).
- Cleans up the configuration to remove the pre-gate settings groups.

The cockpit vocabulary from W13 (old brief) that references `hestia_review` as a phase is replaced. The demo recording is deferred; what ships in W13 is the doctrine-clean ingest path, not a new recording.

---

## Locked knobs

### Knob 1 — Remove HestiaLite and HestiaSentinel from the ingest path

Delete both modules and their tests. Remove all configuration that references them.

**Files to delete:**

- `src/theogony/agents/hestia_lite.py`
- `src/theogony/agents/hestia_sentinel.py`
- `tests/test_hestia_lite.py`
- `tests/test_hestia_sentinel.py` (if it exists)

**Files to edit (removing references):**

- `src/theogony/agents/argus.py` — remove the sentinel call and the `AuditDecision` branch; after the evaluator approves candidates, they go directly to the verification pool writer (Knob 2 below), then to ingest. The `argus.py` constructor no longer accepts or creates a Hestia instance.
- `src/theogony/curiosity/argus_wiring.py` — remove the sentinel instantiation and wiring.
- `src/theogony/config/settings.py` — remove `HestiaLiteSettings` and `HestiaSentinelSettings`. If these groups are already absent (W12 may have partially cleaned up), skip.
- `demo/.demo.env` (and `demo/.demo.env.example` if it exists) — remove `THEOGONY_CURIOSITY__HESTIA_SENTINEL__*` and `THEOGONY_CURIOSITY__HESTIA_LITE__*` env vars.

**Behaviour change:** after the evaluator selects candidates, Argus passes them directly to the ingest pipeline without any content-judgement gate. The only remaining pre-ingest checks are the operative self-defense reflexes that already live in the acquisition adapters (HTTPS enforcement, robots.txt compliance, rate limits, response size cap, redirect-chain cap, content-type validation, timeout). Those stay; they are not content judges. Do not touch them.

There is no "minimal Hestia floor". No CSAM block, no keyword block, no domain block. The immune system handles content post-hoc. If this feels wrong, re-read `docs/IMMUNE_SYSTEM.md §"What pre-gates do — and do not — do"`.

### Knob 2 — Verification pool stub

The real verification pool (a queryable sampling reservoir with lifecycle tracking) is W14 work (Athene). W13 needs a **stub** that:

- accepts pool entries (one per acquired candidate after evaluator approval)
- is queryable ("what is in the pool?") with a trivial implementation
- writes pool entries to disk at `settings.run_reports_dir/verification_pool/<pool_entry_id>.json`

This stub is minimal by design. It will be replaced in W14 by the full pool.

**New file:** `src/theogony/curiosity/verification_pool.py`

```python
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field
from theogony.config.settings import Settings


class PoolEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_label: str
    ingest_run_id: str | None = None
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lifecycle: str = "unobserved"  # unobserved | sampled | cleared | archived


class VerificationPool:
    """Stub pool. W14 replaces this with the full sampling reservoir."""

    def __init__(self, settings: Settings) -> None:
        self._pool_dir = Path(settings.run_reports_dir) / "verification_pool"
        self._pool_dir.mkdir(parents=True, exist_ok=True)

    def register(self, candidate_label: str, ingest_run_id: str | None = None) -> PoolEntry:
        entry = PoolEntry(candidate_label=candidate_label, ingest_run_id=ingest_run_id)
        (self._pool_dir / f"{entry.entry_id}.json").write_text(
            entry.model_dump_json(indent=2)
        )
        return entry

    def entries(self) -> list[PoolEntry]:
        return [
            PoolEntry.model_validate_json(p.read_text())
            for p in sorted(self._pool_dir.glob("*.json"))
        ]
```

Wire the pool into `argus.py`: after a candidate is successfully ingested, call `pool.register(candidate_label=candidate.label, ingest_run_id=run_report.ingest_run_id)`. Argus receives a `VerificationPool` instance from `argus_wiring.py`.

### Knob 3 — SSE vocabulary update (clinic → immune-system language)

The W8/W13-original vocabulary contained `hestia_review` as a phase name. That event implies a synchronous gate decision visible to the user. It is removed.

The vocabulary from the original W13 brief is otherwise kept, with one rename:

| Old event type | New event type | Change reason |
|---|---|---|
| `hestia_review` | `acquired_into_pool` | reflects the immune-system posture; content flows in, not through a gate |

Updated `acquired_into_pool` payload:

```
event: acquired_into_pool
data: {
  "candidate_label": str,
  "pool_entry_id": str,
  "bytes_acquired": int
}
```

**All other event types from the original W13 vocabulary stay as defined** in the original W13 brief (Knob 1 of that doc): `query_phase`, `query_complete`, `trigger_emitted`, `planning_started`, `planning_step_search`, `planning_complete`, `executing_step`, `step_candidates`, `evaluating`, `evaluation_complete`, `acquiring`, `acquired`, `ingesting`, `ingested`, `research_complete`, `error`.

Remove the `hestia_review` event emission from `src/theogony/cockpit/growth_stream.py`. Add `acquired_into_pool` immediately after the `acquired` event (same place in the flow, different semantics — "acquired and placed in the pool" rather than "approved by gate").

### Knob 4 — Cockpit panel update (single vocabulary line)

In `src/theogony/cockpit/static/js/explorer_growth.js`: the handler that renders `hestia_review` events is removed. Add a handler for `acquired_into_pool` that renders a brief line in the Outcome section: "📥 `<candidate_label>` acquired — verification pending". The rest of the cockpit panel from the original W13 brief (three-section Plan / Execution / Outcome shape) is implemented as-specified; only this one event handler changes.

### Knob 5 — CuriosityRunReport: remove sentinel fields

The `CuriosityRunReport` schema may have fields related to HestiaLite/Sentinel decisions (from W7-B or W12). Remove any sentinel-specific fields:

- `hestia_approvals: int` → remove
- `hestia_rejections: int` → remove
- `hestia_llm_calls: int` → remove

If none of those fields exist, skip. The `total_cost_eur` field (originally specified for W13 in the old brief, Knob 6) is still added if it is not already present: it sums planner + evaluator costs only (no sentinel cost any more).

### Knob 6 — Demo scripts: open-flow posture

`demo/reset_living_growth.sh`:

- remove: `THEOGONY_CURIOSITY__HESTIA_SENTINEL__ENABLED=true` (and any HestiaLite equivalent)
- keep: `THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true`, `THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED=true`, `THEOGONY_CURIOSITY__EVALUATOR__ENABLED=true`
- add: comment block explaining the open-flow posture
  ```bash
  # Content flows into the chronicle without a pre-gate content judge.
  # The immune system (Athene / Chronos / ...) observes and acts asynchronously.
  # See docs/IMMUNE_SYSTEM.md for doctrine.
  ```

`demo/living_growth.md`: replace the "HestiaSentinel approved" beat with:

```
01:25  Acquiring and ingesting in parallel.
       Pool entries created — verification happens asynchronously.
       Counters tick: nodes added, edges added.
```

Do not add a recording script or demo walk-through for Wave 3. The live recording happens after W14/W15 when the verification pool is visible in the cockpit.

### Knob 7 — Backlog hygiene

Append to `docs/PHOENIX_BACKLOG.md` (at the end, under a new heading `## Wave 3 annotations`):

```
- PHX-0037: append: "**Wave 3 starting (W13+):** Pre-gate removed. HestiaLite and HestiaSentinel
  deleted. Content flows directly into verification pool after evaluator approval. Immune-system
  doctrine (docs/IMMUNE_SYSTEM.md) governs. Cell types (Athene/Chronos/Nemesis/Eris/Mnemosyne)
  will implement post-hoc verification in W14-W17."

- PHX-0039 (Hestia full): append: "**W12 HestiaSentinel shape removed in W13.** Hestia's correct
  long-term role is as a post-hoc drift monitor and escalation receiver, not a synchronous gate.
  The full PHX-0039 Hestia implementation remains open and aligns with the immune-system doctrine
  (docs/IMMUNE_SYSTEM.md §'The cell types')."

- PHX-0067 (Eris): append: "**Wave 3 context:** Eris is W16 work. She is the adaptive-immunity
  layer in the immune system architecture. Red-team campaigns against an isolated test pantheon.
  Findings as first-class chronicle nodes. See docs/IMMUNE_SYSTEM.md §'Adaptive immunity — Eris'."

- PHX-0068 (Nemesis): append: "**Wave 3 context:** Nemesis is W16 work. She is the antibody-memory
  layer. Periodic structural auditor: confidence inflation, echo chambers, pheromone autobahns.
  Read-only; findings as first-class chronicle nodes. See docs/IMMUNE_SYSTEM.md §'Antibody memory —
  Nemesis'."

- PHX-0071 (Mnemosyne): append: "**Wave 3 context (major scope expansion):** Mnemosyne's role in
  the immune-system doctrine (docs/IMMUNE_SYSTEM.md §'Consciousness — Mnemosyne') is significantly
  larger than the original ticket described. She is no longer only a per-query meta-classifier.
  She is the consciousness layer: reads all cell-class findings, defines her own success metrics
  (LLM-driven), A/B-tests her own thresholds and prompts, writes MnemosyneExperiment nodes back
  into the chronicle, and drafts structured PHX-Backlog entries for the next Phoenix incarnation.
  W17 implements this expanded role. The user explicitly chose: Mnemosyne self-defines metrics
  (not hardcoded, not human-defined). The original W5 Brief describes the meta-query-classifier
  part which becomes a small subset of the W17 scope."
```

No new PHX tickets in W13 unless they surface during implementation.

---

## Files to add / change

**New**

- `src/theogony/curiosity/verification_pool.py` (Knob 2)

**Edit**

- `src/theogony/agents/argus.py` — remove sentinel call, wire pool registration (Knob 1 + 2)
- `src/theogony/curiosity/argus_wiring.py` — remove sentinel instantiation, inject pool (Knob 1 + 2)
- `src/theogony/config/settings.py` — remove HestiaLiteSettings + HestiaSentinelSettings (Knob 1)
- `src/theogony/cockpit/growth_stream.py` — replace `hestia_review` with `acquired_into_pool` (Knob 3)
- `src/theogony/cockpit/static/js/explorer_growth.js` — remove hestia_review handler, add acquired_into_pool handler (Knob 4); implement three-section panel shape from old W13 brief §Knob 2
- `src/theogony/cockpit/templates/explorer.html` — three-section panel scaffolding from old W13 brief §Knob 2
- `src/theogony/cockpit/router.py` — add `GET /api/research-request-stream/{trigger_id}` from old W13 brief §Knob 3
- `src/theogony/reporting/models.py` — remove sentinel fields from CuriosityRunReport; add `total_cost_eur` if absent (Knob 5)
- `src/theogony/curiosity/growth_bridge.py` — `verdict_reasoning` text update: `"research initiated for weak answer"` / `"research initiated by user request"` (from old W13 brief §Knob 6)
- `demo/reset_living_growth.sh` — remove sentinel env vars, add open-flow comment (Knob 6)
- `demo/living_growth.md` — replace HestiaSentinel beat (Knob 6)
- `demo/living_growth_hosted.md` — same update
- `docs/PHOENIX_BACKLOG.md` — Knob 7 appendings
- `README.md` — Living Demo section: replace "governed per-candidate by HestiaSentinel" with "content flows into the chronicle without a pre-gate; the immune system verifies post-hoc"

**Delete**

- `src/theogony/agents/hestia_lite.py`
- `src/theogony/agents/hestia_sentinel.py`
- `tests/test_hestia_lite.py`
- `tests/test_hestia_sentinel.py` (if it exists)

**Forbidden in this PR**

- Any change to the research planner, evaluator, or acquisition adapters (W11/W12 stable).
- Any change to extraction, retrieval, or the main ingest pipeline beyond wiring out the sentinel.
- Introducing any new content-judge pre-gate of any kind.
- Writing a new demo recording script or walk-through.
- Any new PHX ticket not triggered by implementation friction.

---

## Acceptance criteria (machine-runnable)

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/agents src/theogony/curiosity src/theogony/reporting/models.py src/theogony/config/settings.py src/theogony/cockpit
```

### A2 — HestiaLite and HestiaSentinel are gone

```bash
ls src/theogony/agents/hestia_lite.py 2>/dev/null && exit 1
ls src/theogony/agents/hestia_sentinel.py 2>/dev/null && exit 1
ls tests/test_hestia_lite.py 2>/dev/null && exit 1
# no source references remain
rg 'hestia_lite\|HestiaLite\|hestia_sentinel\|HestiaSentinel' src/ tests/ && exit 1
```

All four must return non-zero (artefacts not found, no references).

### A3 — Verification pool stub works

```bash
pytest -q tests/curiosity/test_verification_pool.py
```

Required tests (Talos writes these):

- `test_pool_register_writes_json_entry`
- `test_pool_entries_returns_all_registered`

### A4 — SSE vocabulary: `hestia_review` gone, `acquired_into_pool` present

```bash
pytest -q tests/cockpit/test_growth_stream.py
```

Required new assertion (add to existing test file or new file):

- `test_growth_stream_emits_acquired_into_pool_not_hestia_review`
- `test_acquired_into_pool_payload_contains_pool_entry_id`

### A5 — Full test suite stays green

```bash
pytest -q
```

Any tests that asserted `hestia_review` events must be updated to assert `acquired_into_pool`.
Any tests that relied on `HestiaLite` or `HestiaSentinel` instances must be updated to use the direct evaluator → pool → ingest path.
The count of broken tests not covered by A2 deletions must be zero.

### A6 — Settings reject old Hestia env vars

```bash
pytest -q tests/config/test_settings_reject_deprecated_env.py
```

Required test (if the pattern from W10's `trigger_threshold` test already exists, follow the same shape):

- `test_settings_rejects_THEOGONY_CURIOSITY__HESTIA_SENTINEL__ENABLED`
- `test_settings_rejects_THEOGONY_CURIOSITY__HESTIA_LITE__ENABLED`

If `Settings` uses pydantic-settings with `extra="forbid"` for the curiosity sub-model, these tests should pass naturally. If not, document the gap in the PR body and file a PHX ticket.

---

## STOP-and-file rules

- Removing HestiaLite + HestiaSentinel breaks more than 10 tests not covered by the explicit test-file deletions in A2 → file PHX, list the cascades, stop.
- Any part of the acquisition adapters requires a Hestia instance at runtime (not found via dependency injection but by direct import) → file PHX, stop. This indicates W12 introduced a hard coupling that must be severed before W14.
- The cockpit `EventSource` browser API does not accept the research-request-stream pattern → follow the same resolution as the original W13 brief's STOP rule (GET endpoint paired with POST trigger creation; if still broken, file PHX and stop).

---

## PR description template

```
W13 — Pre-gate removal + verification pool stub + cockpit vocab update

Implements Living Demo Wave 3 slice 1 per docs/etappes/W13_pre_gate_removal_brief.md.
Opens Wave 3 (immune-system architecture). Builds on W10 + W11 + W12 + Doctrine PR #97.

Doctrine pivot: content flows into the chronicle without a synchronous content-judge gate.
HestiaLite and HestiaSentinel are deleted. All acquired candidates go directly to the
verification pool (stub) and then to ingest. The immune system (Athene / Chronos / ...) will
observe and act asynchronously starting in W14. See docs/IMMUNE_SYSTEM.md.

What this PR does:
- deletes HestiaLite and HestiaSentinel (agents + tests + config)
- adds VerificationPool stub (pool.register on every post-evaluator candidate)
- removes hestia_review SSE event; adds acquired_into_pool SSE event
- implements the three-section cockpit panel from the original W13 brief
  (Plan / Execution / Outcome; acquired_into_pool renders as "acquired — verification pending")
- wires GET /api/research-request-stream/{trigger_id} endpoint
- updates demo scripts: removes sentinel env vars, replaces the "HestiaSentinel approved" beat
- appends Wave 3 context to PHX-0037, PHX-0039, PHX-0067, PHX-0068, PHX-0071

What this PR does NOT do:
- it does not implement the full verification pool (W14)
- it does not implement Athene or any cell class (W14-W17)
- it does not write a new demo recording script
- it does not change the planner / evaluator / adapters / extraction / retrieval

Tests updated to remove hestia_review assertions: <list>
Tests deleted: <list (hestia_lite, hestia_sentinel)>
Tests added: test_pool_register_writes_json_entry, test_pool_entries_returns_all_registered,
             test_growth_stream_emits_acquired_into_pool_not_hestia_review,
             test_acquired_into_pool_payload_contains_pool_entry_id,
             test_settings_rejects_deprecated_hestia_env_vars

Acceptance criteria run locally:
- ruff format && ruff check
- mypy src/theogony/agents src/theogony/curiosity src/theogony/reporting/models.py
       src/theogony/config/settings.py src/theogony/cockpit
- pytest -q
- A2 grep assertions (all return non-zero)

PHX tickets filed: <list, or "none">

@hesiod-review
```
