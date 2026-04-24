# W7-B — Argus v0.1 + HestiaLite (Living Demo, slice 2)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w7b-argus-hestia-lite`
**Scope:** one PR
**Predecessor:** W7-A merged to `main`
**Sprint slot:** Living Demo W7-B (second of four)

This is the sprint where the chronicle gets its first independent agent. Every constraint below exists to keep that agent narrow, governed, and predictable in auto-mode. If you are tempted to broaden anything, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (W7-A must be merged first; if it is not, this brief is blocked).
2. `git checkout -b feat/w7b-argus-hestia-lite`
3. After acceptance: `git push -u origin feat/w7b-argus-hestia-lite` and open the PR per the template at the bottom.

If W7-A is not on `main`: stop. Do not start. Open a draft PR titled `[BLOCKED] feat(agents): W7-B — waiting on W7-A` and wait.

---

## Why this etappe exists

W7-A produced typed intent (`CuriosityTrigger`). Nothing acts on it. W7-B builds the first Pantheon agent that does — `Argus` — and the governance gate that makes that action defensible — `HestiaLite`. Together they take a trigger, choose a Project Gutenberg source, get it past a deterministic governance review, and hand it to the existing ingest pipeline.

This is intentionally narrow:

- **One agent (Argus).** Jason and Prometheus are folded into Argus's flow until they earn separation.
- **One source type (Gutenberg).** Web acquisition is structurally impossible.
- **One governor (HestiaLite).** Deterministic rules, no LLM. Real Hestia (PHX-0039) ships later.

---

## Locked knobs

### Knob 1 — `Argus.process(trigger) -> AcquisitionDecision`

```python
class ArgusOutcome(StrEnum):
    APPROVED_AND_INGESTED = "approved_and_ingested"
    APPROVED_INGEST_FAILED = "approved_ingest_failed"
    REJECTED_BY_HESTIA = "rejected_by_hestia"
    NO_CANDIDATES = "no_candidates"
    NO_CANDIDATE_ABOVE_THRESHOLD = "no_candidate_above_threshold"
    UNSUPPORTED_SOURCE_TYPE = "unsupported_source_type"
    BUDGET_EXCEEDED = "budget_exceeded"


class ArgusResult(BaseModel):
    """Full outcome of one Argus.process() call."""

    model_config = ConfigDict(extra="forbid")

    outcome: ArgusOutcome
    decision: AcquisitionDecision  # the W7-A schema
    bytes_acquired: int = Field(default=0, ge=0)
    reason: str = ""


class ArgusAgent:
    def __init__(
        self,
        *,
        adapter: AcquisitionAdapter,
        hestia: HestiaLiteApproval,
        ingest_runner: IngestRunner,
        settings: ArgusSettings,
    ) -> None: ...

    async def process(self, trigger: CuriosityTrigger) -> ArgusResult: ...
```

Steps inside `process` (sequential, no concurrency in v1):

1. **Allowlist check.** If `trigger.proposed_acquisition_spec.source_type != "gutenberg"` → outcome `UNSUPPORTED_SOURCE_TYPE`, no calls made, return.
2. **Search.** `candidates = await adapter.search(trigger.proposed_acquisition_spec.search_query, limit=settings.search_limit)`. If `len(candidates) == 0` → outcome `NO_CANDIDATES`, return.
3. **Score.** Compute `score(candidate, trigger)` per Knob 2. Sort descending.
4. **Threshold gate.** If best score `< settings.min_candidate_score` → outcome `NO_CANDIDATE_ABOVE_THRESHOLD`, return.
5. **HestiaLite review.** `approval = hestia.review(candidate=best, trigger=trigger)`. If `approval.status == "rejected"` → outcome `REJECTED_BY_HESTIA` (record `approval.reason`), return.
6. **Budget check.** If candidate's expected size (estimate from `metadata` if available, otherwise the `max_total_bytes` budget cap is the only gate) > `trigger.budget.max_total_bytes` → outcome `BUDGET_EXCEEDED`, return.
7. **Acquire.** `raw = await adapter.acquire(best)`. If `raw.bytes_acquired > trigger.budget.max_total_bytes` → outcome `BUDGET_EXCEEDED`, return (still no ingest).
8. **Ingest.** `ingest_run_id = await ingest_runner.run_from_raw_content(raw)`. On success → outcome `APPROVED_AND_INGESTED`. On exception → outcome `APPROVED_INGEST_FAILED`, `reason=str(exc)[:500]`.

The `decision` field on the result mirrors the W7-A `AcquisitionDecision` shape — Argus is the writer of those fields.

### Knob 2 — Candidate scoring (deterministic, no LLM)

```python
def score_candidate(candidate: SourceCandidate, trigger: CuriosityTrigger) -> float:
    """Return a deterministic score in [0.0, 1.0]; higher is better."""
    query_terms = _tokenize(trigger.proposed_acquisition_spec.search_query)
    title_terms = _tokenize(candidate.title)
    author_terms = _tokenize(" ".join(candidate.authors))

    title_overlap = _jaccard(query_terms, title_terms)
    author_overlap = _jaccard(query_terms, author_terms)

    # Language preference: English-first for Gen 1.
    lang_bonus = 0.1 if "en" in candidate.languages else 0.0

    # Light popularity prior (download_count if present in metadata).
    dl = candidate.metadata.get("download_count")
    pop = min(1.0, math.log10(dl + 1) / 5.0) if isinstance(dl, int) and dl > 0 else 0.0

    return min(1.0, 0.6 * title_overlap + 0.2 * author_overlap + lang_bonus + 0.1 * pop)
```

`_tokenize` is "lowercase, split on non-alphanumeric, drop stopwords from a fixed 30-word English+German list". Define inline; do not pull NLTK or spaCy. If you find yourself wanting a real BM25 implementation, stop — that is a Phase-2 sub-ticket.

### Knob 3 — `HestiaLiteApproval` rules (deterministic, no LLM)

```python
class HestiaApprovalStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class HestiaApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HestiaApprovalStatus
    reason: str  # human-readable; mandatory on both branches
    rule_fired: str | None = None  # name of the specific rule that decided


class HestiaLiteApproval:
    def __init__(self, settings: HestiaLiteSettings) -> None: ...

    def review(
        self,
        *,
        candidate: SourceCandidate,
        trigger: CuriosityTrigger,
    ) -> HestiaApproval: ...
```

Rules, evaluated in order. First match decides:

1. **`source_type_not_allowlisted`** — `candidate.source_type not in settings.allowlist` → REJECTED. (Defensive: Argus already gated, but Hestia must not trust upstream.)
2. **`title_or_search_in_blocklist`** — any keyword from `settings.blocked_keywords` appears (case-insensitive substring) in the candidate title OR in the trigger's search query → REJECTED. Default blocklist (locked):
   ```
   ["minor", "child abuse", "child pornography", "csam",
    "self-harm instructions", "weapons manufacturing",
    "explosive synthesis", "bioweapon", "chemical weapon"]
   ```
   These are not exhaustive; they are the floor. The list is committed in `hestia_lite.py` as a module constant; do not load from disk.
3. **`download_url_missing`** — `candidate.download_url is None` → REJECTED. (Argus should never call `acquire` blind.)
4. **`license_unknown`** — Project Gutenberg books are public-domain by definition. The rule still exists for defence in depth: if `candidate.metadata.get("copyright") is True` → REJECTED. (Gutendex sets `copyright: false` for PD; `true` is the rare "still under copyright" carve-out — never include those.)
5. **Default** — APPROVED. `rule_fired = "default_approve"`, `reason = "no Hestia rule blocks; gutenberg public-domain by source policy"`.

Person-targeted research, sensitive-topic deep checks, recursion budgets, and drift audit are PHX-0039 territory. Do **not** implement them in v1 even if you can. Adding a "while we're at it" rule is a brief violation.

### Knob 4 — `ArgusSettings` and `HestiaLiteSettings`

Add to `config/settings.py`:

```python
class ArgusSettings(BaseModel):
    """Argus acquisition agent (Living Demo W7-B)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    search_limit: int = Field(default=5, ge=1, le=25)
    min_candidate_score: float = Field(default=0.3, ge=0.0, le=1.0)


class HestiaLiteSettings(BaseModel):
    """HestiaLite governance (Living Demo W7-B)."""

    model_config = ConfigDict(extra="forbid")

    allowlist: list[Literal["gutenberg"]] = Field(default_factory=lambda: ["gutenberg"])
    # blocked_keywords intentionally module-constant (not configurable),
    # see hestia_lite.py BLOCKED_KEYWORDS — keep this comment in the source.


class CuriositySettings(BaseModel):
    # ... existing fields ...
    growth_bridge: GrowthBridgeSettings = Field(default_factory=GrowthBridgeSettings)
    argus: ArgusSettings = Field(default_factory=ArgusSettings)
    hestia_lite: HestiaLiteSettings = Field(default_factory=HestiaLiteSettings)
```

Default `argus.enabled=False`. The demo path enables it via `THEOGONY_CURIOSITY__ARGUS__ENABLED=true`. **Do not** enable by default.

### Knob 5 — `IngestRunner` adapter

`Argus.process` must not import the ingest pipeline directly. Define a thin protocol:

```python
class IngestRunner(Protocol):
    """Minimal contract Argus needs to start an ingest from already-acquired bytes."""

    async def run_from_raw_content(self, raw: RawContent) -> str:
        """Run extraction → store; return the ingest_run_id (ULID)."""
        ...
```

Implement one concrete adapter `RealIngestRunner` in `src/theogony/agents/argus_ingest_runner.py` that wraps the existing `IngestionPipeline`. The pipeline today consumes a `SourceRef` (Gutenberg book id path); your adapter must turn `RawContent` into the input the pipeline expects without forking the pipeline.

If the existing `IngestionPipeline` does not accept already-acquired bytes (only book id), use the `acquisition.gutenberg.GutenbergAdapter` cache pattern: cache the acquired text in the pipeline's expected input cache, then start the pipeline by id. If even that is not feasible, **stop and file PHX**: do not patch the ingest pipeline in this PR.

### Knob 6 — Dispatcher (where Argus runs)

A tiny dispatcher reads new `CuriosityRunReport` files emitted by W7-A and runs Argus on each trigger. v1 shape:

```python
class CuriosityDispatcher:
    """Watches the curiosity reports directory; dispatches Argus per emitted trigger."""

    async def process_pending(self) -> list[ArgusResult]: ...
```

For W7-B the dispatcher is **manual**. It is exposed exclusively as a CLI:

```
theogony curiosity run-pending [--max N] [--dry-run]
```

This command:

1. Reads every `CuriosityRunReport` in `run_reports/curiosity/` whose `decision.hestia_status == "not_evaluated"`.
2. Calls `Argus.process(report.trigger)` for each (oldest first, capped by `--max`, default 5).
3. Updates each report on disk with the resulting `decision` and `bytes_acquired` fields.
4. Prints a one-line summary per trigger.

`--dry-run` runs everything except the `acquire` and `ingest` steps; useful for the demo recording.

There is **no background worker** in W7-B. No tick phase. No SSE. Triggering Argus from a long-running process is W8.

### Knob 7 — Concurrency, retries, error handling

- `Argus.process` is sequential per trigger. Multiple triggers from the dispatcher are processed sequentially (no `asyncio.gather`). Add concurrency only when the demo timing forces it (it will not).
- `adapter.search` and `adapter.acquire` already retry inside `GutenbergAdapter`. Argus does not retry on top.
- Any exception inside `process` is caught at the top, recorded as outcome `APPROVED_INGEST_FAILED` (or `NO_CANDIDATES` / `BUDGET_EXCEEDED` if it happened earlier), and the dispatcher continues with the next trigger.

### Knob 8 — No new agent classes, no Argonauts, no other gods

You will be tempted to scaffold Jason / Prometheus / Athene "for symmetry". Do not. The Living Demo Plan §7 explicitly freezes everything else. Argus and HestiaLite. That is the entire pantheon for W7-B.

---

## Files to add / change

**New**

- `src/theogony/agents/argus.py` — `ArgusAgent`, `ArgusOutcome`, `ArgusResult`, `score_candidate`, `_tokenize`, `_jaccard`, stopword set.
- `src/theogony/agents/hestia_lite.py` — `HestiaLiteApproval`, `HestiaApprovalStatus`, `HestiaApproval`, `BLOCKED_KEYWORDS`.
- `src/theogony/agents/argus_ingest_runner.py` — `IngestRunner` Protocol + `RealIngestRunner`.
- `src/theogony/curiosity/dispatcher.py` — `CuriosityDispatcher`.
- CLI command: extend `src/theogony/cli.py` with `theogony curiosity run-pending`.
- `tests/test_argus.py`
- `tests/test_hestia_lite.py`
- `tests/test_curiosity_dispatcher.py`

**Edit**

- `src/theogony/config/settings.py` — add `ArgusSettings`, `HestiaLiteSettings`; attach to `CuriositySettings`.

**Forbidden in this PR**

- Any change under `src/theogony/cockpit/`. (W8.)
- Any change to `IngestionPipeline` itself beyond a constructor optional argument that lets the adapter inject pre-acquired content (and only if absolutely required by Knob 5).
- Adding any new Pantheon agent class beyond Argus + HestiaLite.
- Background workers, tick phases, SSE.
- Any web HTTP client besides what `GutenbergAdapter` already provides.

---

## Acceptance criteria (machine-runnable)

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/agents src/theogony/curiosity src/theogony/config/settings.py src/theogony/cli.py
```

### A2 — Unit tests

```bash
pytest -q tests/test_argus.py tests/test_hestia_lite.py tests/test_curiosity_dispatcher.py
```

Required tests (write more if a behaviour is not covered):

- `test_argus_unsupported_source_type_outcome`
- `test_argus_no_candidates_outcome`
- `test_argus_score_threshold_gate`
- `test_argus_hestia_rejection_short_circuits`
- `test_argus_budget_exceeded_does_not_acquire`
- `test_argus_happy_path_calls_ingest_runner_once`
- `test_hestia_lite_blocklist_substring_case_insensitive`
- `test_hestia_lite_copyright_true_rejected`
- `test_hestia_lite_default_approves_with_named_rule`
- `test_dispatcher_processes_only_not_evaluated`
- `test_dispatcher_updates_report_on_disk`
- `test_dispatcher_max_cap_respected`

### A3 — Existing tests stay green

```bash
pytest -q
```

### A4 — Living-demo smoke

Add `tests/test_living_demo_w7b_smoke.py`:

```python
@pytest.mark.living_demo
async def test_argus_happy_path_smoke(tmp_path) -> None:
    """W7-B demo path: a curiosity trigger leads to a fake-Gutenberg acquire + ingest."""
    ...
```

Use a stub `AcquisitionAdapter` that returns one canned `SourceCandidate` and one canned `RawContent` (small, ~1 KB plain text). Use the `InMemoryKnowledgeStore` and `StubLLMProvider`. Assert: outcome `APPROVED_AND_INGESTED`, `bytes_acquired > 0`, the on-disk `CuriosityRunReport` has a real `ingest_run_id`.

Must pass:

```bash
pytest -q -m living_demo
```

### A5 — CLI smoke

```bash
theogony curiosity run-pending --dry-run
```

Exits 0 on a fresh repo (no triggers, "0 processed"). On a repo with a single emitted trigger, exits 0 and updates the report.

---

## STOP-and-file rules

- The existing `IngestionPipeline` cannot be invoked from already-acquired `RawContent` even via cache-injection. → file PHX, stop.
- The CLI structure does not allow adding a `curiosity run-pending` subcommand cleanly. → file PHX, stop.
- The dispatcher would require concurrency primitives beyond `await` to meet the smoke test. → file PHX, stop. (It should not.)

---

## PR description template

```
W7-B — Argus v0.1 + HestiaLite

Implements PHX-0037 slice 2 per docs/etappes/W7B_argus_hestia_lite_brief.md.
Builds on W7-A.

What this PR does:
- adds ArgusAgent (search → score → Hestia → acquire → ingest) for source_type="gutenberg"
- adds HestiaLiteApproval (deterministic allowlist + blocklist + copyright check)
- adds CuriosityDispatcher and `theogony curiosity run-pending` CLI
- adds settings flags (default-off)
- ships unit tests + one living-demo smoke

What this PR does NOT do:
- it does not add Jason / Prometheus / Athene
- it does not enable any agent by default
- it does not add background workers, tick phases, or SSE
- it does not touch the cockpit (W8)

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/agents src/theogony/curiosity src/theogony/config/settings.py src/theogony/cli.py`
- `pytest -q`
- `pytest -q -m living_demo`
- `theogony curiosity run-pending --dry-run`

PHX tickets filed in this PR: <list, or "none">

@hesiod-review
```
