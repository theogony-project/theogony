# W14 - Athene v0.1: Verification Pool + T-Helper Worker (Living Demo Wave 3, slice 2)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-25
**Branch:** `feat/w14-athene-verifier`
**Scope:** one PR (curiosity/immune-system code + CLI + cockpit visibility + tests; no acquisition/retrieval changes)
**Predecessor:** W13 merged on `main` (PR #99). `docs/IMMUNE_SYSTEM.md` merged on `main` (PR #97).
**Sprint slot:** Living Demo W14 (second in Wave 3)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (PR #99 must be merged; if not, this brief is blocked).
2. `git checkout -b feat/w14-athene-verifier`
3. Implement.
4. `git push -u origin feat/w14-athene-verifier`
5. `gh pr create --base main --title "feat(curiosity): W14 - Athene verifier + verification pool sampling"` with the PR body shape at the bottom.

---

## Why this etappe exists

W13 removed the clinic gate. Content now flows into the Chronik without `HestiaLite` or `HestiaSentinel`, and each successful ingest registers a lightweight disk-backed `PoolEntry` in `src/theogony/curiosity/verification_pool.py`.

That is only half of the immune-system posture. W14 makes the first immune cell real:

- the verification pool becomes a bounded, queryable sampling reservoir instead of a flat list of JSON files
- Athene v0.1 samples pool entries asynchronously, outside the ingest path
- Athene writes `Finding` records as first-class Chronik nodes
- the cockpit gets enough immune-system visibility that an operator can see "content entered pool -> Athene sampled -> finding written"

Athene v0.1 is deliberately narrow. She is not a fact oracle. She does not browse the web. She does not call an LLM. She performs structural and groundedness checks using data already inside the system: `PoolEntry`, `IngestRunReport`, and the Chronik store. Fact-level adversarial verification comes later through richer Athene iterations plus Eris/Nemesis/Chronos. This sprint proves the immune-system loop without reintroducing a synchronous gate.

---

## Doctrine constraints

These are not negotiable:

- Athene is post-hoc. No caller may await Athene before ingest completes.
- Athene never blocks, rejects, deletes, demotes, or rewrites content.
- Athene writes observations only: `Finding` nodes plus optional `FLAGGED_BY` edges.
- Athene samples. She does not try to cover 100% of the pool.
- Athene defaults off in ordinary operation. The demo path enables her explicitly.
- No pre-gate content filter may be introduced under another name.

If implementation pressure makes any of these hard, the correct action is STOP-and-file, not a workaround.

---

## Locked knobs

### Knob 1 - Extend `PoolEntry` into a real sampling reservoir entry

Edit `src/theogony/curiosity/verification_pool.py`.

Replace the loose `lifecycle: str` with a literal and add the fields below.

```python
PoolLifecycle = Literal["unobserved", "sampled_by_athene", "cleared", "archived"]

class PoolEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_label: str
    ingest_run_id: str | None = None
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lifecycle: PoolLifecycle = "unobserved"

    source_type: str | None = None
    source_identifier: str | None = None
    target_node_ids: list[str] = Field(default_factory=list)
    sampled_by: list[str] = Field(default_factory=list)
    sampled_at: datetime | None = None
    cleared_at: datetime | None = None
    finding_ids: list[str] = Field(default_factory=list)
```

Backwards compatibility with W13 pool files is required: old entries that contain only `entry_id`, `candidate_label`, `ingest_run_id`, `acquired_at`, `lifecycle` must still parse. The new fields all have defaults, so this should be natural.

Add methods to `VerificationPool`:

```python
def get(self, entry_id: str) -> PoolEntry | None: ...
def stats(self) -> VerificationPoolStats: ...
def sample_for_athene(
    self,
    *,
    sample_rate: float,
    max_entries: int,
    min_entries: int,
    seed: int | None = None,
) -> list[PoolEntry]: ...
def mark_sampled_by_athene(self, entry_id: str, *, finding_ids: list[str]) -> PoolEntry: ...
```

`VerificationPoolStats` lives in the same module:

```python
class VerificationPoolStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = 0
    unobserved: int = 0
    sampled_by_athene: int = 0
    cleared: int = 0
    archived: int = 0
    findings_total: int = 0
```

Sampling rules:

- Only entries with `lifecycle == "unobserved"` are eligible.
- Default sample rate is 2%.
- If the pool has at least one eligible entry and Athene is enabled, sample at least one entry per pass (`min_entries=1`).
- Sampling is non-deterministic in production (`seed=None` uses `random.SystemRandom`).
- Tests pass a fixed seed to make selection deterministic.
- `max_entries` caps sampled entries after the sample-rate calculation.

No archive/retention logic in W14. Archiving is W15+.

### Knob 2 - Enrich pool registration with source metadata when available

Edit `src/theogony/agents/argus.py`.

When registering the pool entry after ingest, pass:

- `source_type` from the selected `SourceCandidate.source_type`
- `source_identifier` from the selected `SourceCandidate.identifier`
- `target_node_ids=[]` for now

Do not widen `IngestRunner.run_from_raw_content` in W14. The current runner returns only `ingest_run_id`; changing that contract would touch more code than this sprint needs. Athene v0.1 targets the pool entry and ingest report, not individual content nodes. Later W15/W16 work may add target-node resolution.

Update `VerificationPool.register(...)` signature:

```python
def register(
    self,
    candidate_label: str,
    ingest_run_id: str | None = None,
    *,
    source_type: str | None = None,
    source_identifier: str | None = None,
    target_node_ids: list[str] | None = None,
) -> PoolEntry: ...
```

Keep old positional calls working.

### Knob 3 - Finding schema and Chronik write-back

Add a `FINDING = "finding"` member to `NodeType` in `src/theogony/core/model.py`.

Add a new module: `src/theogony/curiosity/finding.py`.

```python
FindingType = Literal[
    "no_issue_observed",
    "ingest_report_missing",
    "ingest_failed",
    "ingest_partial",
    "low_resolution_quality",
    "high_schema_violation_rate",
    "high_parse_error_rate",
]

FindingSeverity = Literal["info", "low", "medium", "high", "critical"]
FindingCell = Literal["athene"]

class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(default_factory=lambda: f"FINDING-{uuid.uuid4()}")
    finding_type: FindingType
    severity: FindingSeverity
    cell: FindingCell = "athene"
    pool_entry_id: str
    ingest_run_id: str | None = None
    target_node_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    sampled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolution_action: Literal["none", "annotated", "demoted", "deleted", "escalated_to_human"] = "none"

    def to_knowledge_node(self) -> KnowledgeNode: ...
```

`Finding.to_knowledge_node()` creates a `KnowledgeNode`:

- `id = finding_id`
- `node_type = NodeType.FINDING`
- `label = f"Athene finding: {finding_type}"`
- `description` is a short human-readable sentence joining severity + pool entry + ingest run
- `epistemic_status = EpistemicStatus.OBSERVED`
- `layer = Layer.EPHEMERA`
- `source_ref = SourceRef(source_type="athene", identifier=finding_id, snippet="; ".join(evidence[:3]))`
- `properties` includes every scalar field plus `target_node_ids` and `evidence`

Do not create a subclass of `KnowledgeNode`. The current store expects ordinary `KnowledgeNode` records. A conversion method is enough.

Add helper:

```python
def flag_edges_for_finding(finding: Finding) -> list[KnowledgeEdge]:
    ...
```

For each `target_node_id`, create:

- `source_id = target_node_id`
- `target_id = finding.finding_id`
- `relation_type = "FLAGGED_BY"`
- `epistemic_type = EdgeType.AGENT`
- `confidence = 0.8`
- `weight = 0.5`
- `source_ref = SourceRef(source_type="athene", identifier=finding.finding_id)`

In W14, `target_node_ids` will normally be empty. The helper is still required and tested so W15/Chronos can build on it.

### Knob 4 - Athene v0.1 worker

Add `src/theogony/agents/athene.py`.

Public API:

```python
class AtheneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    sample_rate: float = Field(default=0.02, ge=0.0, le=1.0)
    min_entries_per_pass: int = Field(default=1, ge=0, le=100)
    max_entries_per_pass: int = Field(default=50, ge=1, le=500)
    low_resolution_ratio_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    schema_violation_rate_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    parse_error_rate_threshold: float = Field(default=0.1, ge=0.0, le=1.0)

class AtheneRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sampled_count: int = 0
    findings_written: int = 0
    pool_entries_marked: int = 0
    skipped_reason: str | None = None

class AtheneVerifier:
    def __init__(
        self,
        *,
        store: KnowledgeStore,
        pool: VerificationPool,
        settings: AtheneSettings,
        run_reports_dir: Path,
    ) -> None: ...

    async def run_once(self, *, seed: int | None = None) -> AtheneRunSummary: ...
```

`run_once()`:

1. If `settings.enabled` is false: return summary with `skipped_reason="athene disabled"`.
2. Sample entries via `pool.sample_for_athene(...)`.
3. For each sampled entry, load its `IngestRunReport` from `run_reports_dir / "ingest" / f"{ingest_run_id}.json"` if `ingest_run_id` is not None.
4. Produce findings using Knob 5 rules.
5. Convert findings to `KnowledgeNode`s and write them to the store via `batch_upsert_nodes`.
6. Write `FLAGGED_BY` edges via `batch_upsert_edges` (often empty in W14).
7. Mark the pool entry `sampled_by_athene` with the written finding IDs.
8. Return `AtheneRunSummary`.

Important: `run_once()` is a post-hoc worker. It does not ingest content and does not call Argus.

### Knob 5 - Athene v0.1 checks

Athene v0.1 uses only the `IngestRunReport`. No LLM, no web, no external calls.

For each sampled pool entry:

1. If `ingest_run_id is None` or the report file is missing:
   - finding_type = `ingest_report_missing`
   - severity = `medium`
   - evidence = `["missing ingest report for pool_entry_id=<id>"]`

2. If report `status == "failed"` or report `verdict == "failed"`:
   - finding_type = `ingest_failed`
   - severity = `high`
   - evidence includes report status, verdict, verdict_reasoning

3. Else if report `status == "partial"` or report `verdict in {"partial", "poor"}`:
   - finding_type = `ingest_partial`
   - severity = `medium`
   - evidence includes report status, verdict, verdict_reasoning

4. Else if `report.quality_flags.low_tier_ratio >= low_resolution_ratio_threshold`:
   - finding_type = `low_resolution_quality`
   - severity = `low`
   - evidence includes the actual ratio and threshold

5. Else if `report.quality_flags.schema_violation_rate >= schema_violation_rate_threshold`:
   - finding_type = `high_schema_violation_rate`
   - severity = `medium`
   - evidence includes actual rate and threshold

6. Else if `report.quality_flags.parse_error_rate >= parse_error_rate_threshold`:
   - finding_type = `high_parse_error_rate`
   - severity = `medium`
   - evidence includes actual rate and threshold

7. Else:
   - finding_type = `no_issue_observed`
   - severity = `info`
   - evidence = `["Athene sampled this pool entry and observed no structural issue in the ingest report."]`

One sampled pool entry produces exactly one Finding in W14. Later versions may produce multiple findings per entry.

### Knob 6 - Settings

Move `AtheneSettings` from `agents/athene.py` into `src/theogony/config/settings.py` if needed to avoid import cycles. Preferred final shape:

```python
class AtheneSettings(BaseModel):
    ...

class CuriositySettings(BaseModel):
    ...
    athene: AtheneSettings = Field(default_factory=AtheneSettings)
```

Environment variables:

- `THEOGONY_CURIOSITY__ATHENE__ENABLED`
- `THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE`
- `THEOGONY_CURIOSITY__ATHENE__MIN_ENTRIES_PER_PASS`
- `THEOGONY_CURIOSITY__ATHENE__MAX_ENTRIES_PER_PASS`

Defaults:

- enabled: `False`
- sample_rate: `0.02`
- min_entries_per_pass: `1`
- max_entries_per_pass: `50`

### Knob 7 - CLI command

Add command under existing `curiosity_app` in `src/theogony/cli.py`:

```bash
theogony curiosity athene-run --once --store memory
```

Options:

- `--once` required for W14. If omitted, print help and exit code 2. No daemon loop in W14.
- `--store` same choices as `curiosity run-pending`: `memory` or `neo4j`, default `memory`.
- `--seed <int>` optional, test-only deterministic sampling. Do not mention it in operator docs except as a test aid.

CLI behaviour:

- If Athene disabled: print "Athene disabled" and exit 0.
- If no eligible entries: print "sampled=0 findings=0" and exit 0.
- Else print "sampled=<n> findings=<m> pool_marked=<k>" and exit 0.

No long-running worker in W14. The daemon/scheduler is W15+ or a later operational ticket.

### Knob 8 - Cockpit immune-system visibility

Add a small read-only endpoint and panel. Keep it modest.

Endpoint:

```text
GET /cockpit/api/verification-pool
```

Response:

```python
class VerificationPoolStatusDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stats: VerificationPoolStats
    recent_entries: list[PoolEntry]  # max 10, newest first
```

The endpoint reads `VerificationPool(settings).entries()`, computes stats, returns the ten newest entries by `acquired_at`. No store access.

Cockpit UI:

- Add a compact "Immune system" block near the Research live panel.
- It shows:
  - pool total
  - unobserved
  - sampled_by_athene
  - findings_total
- It fetches once on page load and once after a research stream emits `research_complete`.
- No live SSE for Athene in W14.

If cockpit wiring threatens the diff cap, keep the endpoint and tests, and add a TODO in the brief implementation PR body. Do not block Athene core on UI polish.

### Knob 9 - Demo scripts and docs

Edit `demo/reset_living_growth.sh`:

- add `THEOGONY_CURIOSITY__ATHENE__ENABLED=true`
- add `THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE=1.0`
- add comment:
  ```bash
  # Demo mode samples every pool entry so the immune-system panel visibly changes.
  # Production default remains 0.02.
  ```

Edit `demo/living_growth.md` and `docs/LIVING_DEMO.md`:

- Add a post-research optional beat:
  ```text
  Operator runs: theogony curiosity athene-run --once --store neo4j
  Cockpit Immune system panel updates: sampled_by_athene increases, one Finding appears.
  ```

Do not claim the demo proves factual correctness. It proves post-hoc immune-system sampling and first-class Findings.

### Knob 10 - Backlog hygiene

Append to `docs/PHOENIX_BACKLOG.md` under `## Wave 3 annotations`:

```markdown
- PHX-0062 (Negative Knowledge): **W14 dependency note.** Athene v0.1 writes Finding nodes
  and `FLAGGED_BY` edges only. Chronos in W15 consumes these Findings and starts writing
  `CONTRADICTS` / `SUPERSEDED_BY` edges. W14 must not implement negative-knowledge actions.

- PHX-0071 (Mnemosyne): **W14 metric source.** VerificationPoolStats and Athene Findings
  become one of Mnemosyne's metric streams in W17. The W14 schema should stay simple and
  queryable: pool stats, finding types, severity, sampled_at.
```

If `PHX-0062.yaml` does not exist, do not create it in W14. The catalogue append is enough.

---

## Files to add / change

**New**

- `src/theogony/curiosity/finding.py`
- `src/theogony/agents/athene.py`
- `tests/curiosity/test_finding.py`
- `tests/agents/test_athene.py`

**Edit**

- `src/theogony/curiosity/verification_pool.py` - full W14 pool entry, stats, sampling, mark-sampled
- `src/theogony/agents/argus.py` - pass source metadata into pool register
- `src/theogony/core/model.py` - add `NodeType.FINDING`
- `src/theogony/config/settings.py` - add `AtheneSettings` under `CuriositySettings`
- `src/theogony/cli.py` - add `curiosity athene-run --once`
- `src/theogony/cockpit/router.py` - add pool status endpoint
- `src/theogony/cockpit/explorer.py` / template / JS as needed for the small Immune system panel
- `demo/reset_living_growth.sh`
- `demo/living_growth.md`
- `docs/LIVING_DEMO.md`
- `docs/PHOENIX_BACKLOG.md`
- existing W13 pool tests in `tests/curiosity/test_verification_pool.py`

**Forbidden in this PR**

- No LLM calls from Athene.
- No web calls from Athene.
- No content rejection, deletion, demotion, or quarantine.
- No Chronos behaviour (`CONTRADICTS`, `SUPERSEDED_BY`, confidence demotion, deletion logs).
- No scheduler/daemon loop. `--once` only.
- No changes to research planner, evaluator, acquisition adapters, extraction, or retrieval, except the narrow `argus.py` pool metadata pass-through.
- No new top-level package.

---

## Acceptance criteria (machine-runnable)

### A1 - Lint and type

```bash
ruff format
ruff check
mypy src/theogony/curiosity src/theogony/agents src/theogony/config/settings.py src/theogony/cli.py src/theogony/cockpit src/theogony/core/model.py
```

### A2 - Pool sampling and stats

```bash
pytest -q tests/curiosity/test_verification_pool.py
```

Required tests:

- `test_pool_entry_backwards_compatible_with_w13_shape`
- `test_pool_stats_counts_lifecycle_and_findings`
- `test_sample_for_athene_samples_at_least_min_when_enabled`
- `test_sample_for_athene_respects_max_entries`
- `test_mark_sampled_by_athene_persists_finding_ids`

### A3 - Finding conversion

```bash
pytest -q tests/curiosity/test_finding.py
```

Required tests:

- `test_finding_to_knowledge_node_uses_node_type_finding`
- `test_finding_node_properties_include_pool_entry_and_evidence`
- `test_flag_edges_for_finding_creates_flagged_by_edges`
- `test_flag_edges_for_finding_empty_targets_returns_empty_list`

### A4 - Athene worker

```bash
pytest -q tests/agents/test_athene.py
```

Required tests:

- `test_athene_disabled_returns_skipped_summary`
- `test_athene_no_entries_returns_zero_summary`
- `test_athene_missing_ingest_report_writes_medium_finding`
- `test_athene_failed_ingest_report_writes_high_finding`
- `test_athene_clean_ingest_report_writes_no_issue_observed`
- `test_athene_marks_pool_entry_sampled_after_writing_finding`
- `test_athene_never_calls_ingest_or_argus`

Use an in-memory store fixture for the Finding node assertions.

### A5 - CLI smoke

```bash
pytest -q tests/cli/test_athene_cli.py
```

Required tests:

- `test_athene_run_once_disabled_exits_zero`
- `test_athene_run_once_prints_sampled_and_findings_counts`
- `test_athene_run_requires_once_flag`

### A6 - Cockpit pool status endpoint

```bash
pytest -q tests/cockpit/test_verification_pool_status_endpoint.py
```

Required tests:

- `test_verification_pool_status_returns_stats`
- `test_verification_pool_status_limits_recent_entries_to_ten`

### A7 - Full suite

```bash
pytest -q
```

### A8 - No pre-gate regression

```bash
rg 'HestiaLite|HestiaSentinel|hestia_review|pre.?gate' src/ tests/ && exit 1
```

This command must return non-zero (no matches). If legitimate doctrine comments in docs match, ignore docs; source and tests must stay clean.

---

## STOP-and-file rules

- If writing Finding nodes requires a store schema migration beyond adding `NodeType.FINDING`, STOP and file PHX. W14 should write ordinary `KnowledgeNode`s with `node_type=finding`.
- If the current in-memory and Neo4j stores disagree on `NodeType.FINDING`, STOP and file PHX. Do not special-case one backend.
- If retrieving target node IDs from `ingest_run_id` requires widening `IngestRunner` or `IngestionResult`, do not do it in W14. Leave `target_node_ids=[]`, document in PR body, and file PHX if needed.
- If cockpit panel work pushes the PR over the diff cap, keep the endpoint and Athene core, omit the JS panel, and document the omission. Do not cut Athene core to save UI.
- If any implementation path awaits Athene before completing ingest, STOP. That is a doctrine violation.

---

## PR description template

```markdown
W14 - Athene verifier + verification pool sampling

Implements Living Demo Wave 3 slice 2 per docs/etappes/W14_athene_brief.md.
Builds on W13 pre-gate removal (PR #99) and the immune-system doctrine (PR #97).

What this PR does:
- extends VerificationPool from W13 stub into a sampling reservoir
- adds Finding schema and writes findings as KnowledgeNode(node_type=finding)
- adds AtheneVerifier.run_once(): samples pool entries, checks ingest reports, writes findings
- adds `theogony curiosity athene-run --once`
- adds cockpit verification-pool status endpoint and small Immune system panel
- updates demo docs to show optional Athene run after research

What this PR does NOT do:
- no LLM calls, web calls, fact-oracle behaviour
- no rejection, deletion, demotion, quarantine, Chronos actions
- no scheduler/daemon loop
- no changes to planner/evaluator/acquisition/extraction/retrieval

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/curiosity src/theogony/agents src/theogony/config/settings.py src/theogony/cli.py src/theogony/cockpit src/theogony/core/model.py`
- `pytest -q tests/curiosity/test_verification_pool.py`
- `pytest -q tests/curiosity/test_finding.py`
- `pytest -q tests/agents/test_athene.py`
- `pytest -q tests/cli/test_athene_cli.py`
- `pytest -q tests/cockpit/test_verification_pool_status_endpoint.py`
- `pytest -q`
- no-pre-gate regression rg check

Notes / deviations:
<list, or "none">

PHX tickets filed:
<list, or "none">

@hesiod-review
```
