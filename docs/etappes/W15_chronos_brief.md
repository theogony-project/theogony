# W15 - Chronos v0.1: Finding Consumer + Negative-Knowledge Actions (Living Demo Wave 3, slice 3)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-25
**Branch:** `feat/w15-chronos-recycler`
**Scope:** one PR (Chronos worker + pool lifecycle + report + CLI + tests; no acquisition/retrieval/planner changes)
**Predecessor:** W14 merged on `main` (PR #101). `docs/IMMUNE_SYSTEM.md` merged on `main` (PR #97).
**Sprint slot:** Living Demo W15 (third in Wave 3)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (PR #101 must be merged; if not, this brief is blocked).
2. `git checkout -b feat/w15-chronos-recycler`
3. Implement.
4. `git push -u origin feat/w15-chronos-recycler`
5. `gh pr create --base main --title "feat(curiosity): W15 - Chronos recycler + negative-knowledge actions"` with the PR body shape at the bottom.

---

## Why this etappe exists

W14 made the first immune cell real: Athene samples the verification pool and writes `Finding` nodes into the Chronik. But a finding is still only an observation. The immune system needs a response layer.

W15 adds Chronos v0.1: the T-killer / recycler cell. Chronos reads already-written Athene findings, decides what response is appropriate, writes negative-knowledge edges where the semantics are strong enough, optionally demotes target-node confidence, and marks pool entries as cleared after the response is recorded.

Chronos v0.1 is deliberately conservative:

- no hard deletes
- no web calls
- no LLM calls
- no new acquisition
- no synchronous gate
- no action before Athene has written a finding
- no `SUPERSEDED_BY` edge unless an explicit replacement target exists (W15 does not have one, so `SUPERSEDED_BY` is reserved but not emitted)

This sprint proves the second half of the immune-system loop: "sample -> finding -> response -> pool cleared", without pretending W14's structural findings are full factual refutations.

---

## Doctrine constraints

These are non-negotiable:

- Chronos is post-hoc. No caller may await Chronos before ingest completes.
- Chronos never fetches, searches, plans, evaluates, or verifies new content.
- Chronos does not delete in W15. Hard deletion requires explicit future doctrine + append-only deletion log.
- Chronos only acts on persisted Findings, never on raw user queries or raw acquired content.
- Chronos writes every action as inspectable data: `ChronosRunReport`, updated Finding properties, pool lifecycle, and negative-knowledge edges where applicable.
- Chronos must distinguish "structural ingest concern" from "factual contradiction". Structural findings may demote confidence; they must not be mislabeled as `CONTRADICTS`.

If implementation pressure makes any of these hard, STOP and file PHX.

---

## Current W14 interfaces Chronos must use

These exist on `main` after PR #101:

- `src/theogony/curiosity/verification_pool.py`
  - `PoolEntry.lifecycle in {"unobserved", "sampled_by_athene", "cleared", "archived"}`
  - `PoolEntry.finding_ids: list[str]`
  - `VerificationPool.entries()`
  - `VerificationPool.get(entry_id)`
  - `VerificationPool.stats()`
  - `VerificationPool.mark_sampled_by_athene(...)`
- `src/theogony/curiosity/finding.py`
  - `Finding`
  - `Finding.to_knowledge_node()`
  - `flag_edges_for_finding(...)`
- `src/theogony/agents/athene.py`
  - `AtheneVerifier.run_once(...)`
- `src/theogony/core/model.py`
  - `NodeType.FINDING`
- `KnowledgeStore`
  - `get_node`
  - `batch_upsert_nodes`
  - `batch_upsert_edges`
  - `batch_update_scores`

Do not invent a new storage abstraction. Use these.

---

## Locked knobs

### Knob 1 - Extend Finding for Chronos-readable action state

Edit `src/theogony/curiosity/finding.py`.

Widen `FindingType` with exactly these future-facing values:

```python
"factual_error_suspected",
"internal_contradiction",
```

Widen `FindingCell` from `Literal["athene"]` to:

```python
FindingCell = Literal["athene", "chronos"]
```

Do not make this a free string. Nemesis/Eris will widen it later in W16.

Add helper functions:

```python
def finding_from_node(node: KnowledgeNode) -> Finding:
    """Parse a Finding from a KnowledgeNode(node_type=finding)."""

def resolved_finding_node(
    finding: Finding,
    *,
    resolved_at: datetime,
    resolution_action: Literal["none", "annotated", "demoted", "deleted", "escalated_to_human"],
) -> KnowledgeNode:
    """Return an updated KnowledgeNode with resolution fields changed."""
```

`finding_from_node` reads from `node.properties`. It raises `ValueError` if `node.node_type != NodeType.FINDING` or required properties are absent.

`resolved_finding_node` must preserve the original `finding_id`, `finding_type`, `severity`, `cell`, `pool_entry_id`, `ingest_run_id`, `target_node_ids`, `evidence`, and `sampled_at`, and update only:

- `resolved_at`
- `resolution_action`

No migration of old W14 findings is required; W14 already stored these properties.

### Knob 2 - Add pool clear method

Edit `src/theogony/curiosity/verification_pool.py`.

Add:

```python
def mark_cleared(self, entry_id: str) -> PoolEntry:
    ...
```

Behaviour:

- raises `ValueError("pool entry not found: <entry_id>")` if missing
- sets `lifecycle="cleared"`
- sets `cleared_at=datetime.now(UTC)`
- preserves `sampled_by`, `sampled_at`, and `finding_ids`
- persists the updated JSON
- returns the updated `PoolEntry`

No archive method in W15. Archiving remains future work.

### Knob 3 - Negative-knowledge edge helper

Add `src/theogony/curiosity/negative_knowledge.py`.

Public API:

```python
NEGATIVE_RELATION_TYPES = {"CONTRADICTS", "SUPERSEDED_BY"}

def contradiction_edges_for_finding(
    finding: Finding,
    *,
    confidence: float,
    weight: float,
) -> list[KnowledgeEdge]:
    ...
```

Rules:

- Emit no edges if `finding.target_node_ids` is empty.
- Emit no edges unless `finding.finding_type in {"factual_error_suspected", "internal_contradiction"}`.
- For each target node id, create:
  - `source_id = target_node_id`
  - `target_id = finding.finding_id`
  - `relation_type = "CONTRADICTS"`
  - `epistemic_type = EdgeType.AGENT`
  - `confidence = confidence`
  - `weight = weight`
  - `source_ref = SourceRef(source_type="chronos", identifier=finding.finding_id)`
  - `properties = {"cell": "chronos", "finding_type": finding.finding_type, "pool_entry_id": finding.pool_entry_id}`

`SUPERSEDED_BY` is not emitted in W15. Keep the constant so PHX-0062's relation family is visible, but do not create a helper for it until a replacement target exists.

This distinction matters: W14's structural findings (`ingest_failed`, `low_resolution_quality`, etc.) are not factual contradictions. Chronos may demote their target nodes if targets exist, but must not write `CONTRADICTS` for them.

### Knob 4 - Chronos settings

Edit `src/theogony/config/settings.py`.

Add:

```python
class ChronosSettings(BaseModel):
    """Chronos recycler (Living Demo W15)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_entries_per_pass: int = Field(default=100, ge=1, le=1000)
    min_severity_for_demotion: Literal["medium", "high", "critical"] = "medium"
    confidence_demote_delta: float = Field(default=0.1, ge=0.0, le=1.0)
    negative_edge_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    negative_edge_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    hard_delete_enabled: bool = False
```

Add to `CuriositySettings`:

```python
chronos: ChronosSettings = Field(default_factory=ChronosSettings)
```

`hard_delete_enabled` must exist and must stay unused in W15 except for a test asserting it does not trigger deletion. It is a future-policy placeholder.

Environment variables:

- `THEOGONY_CURIOSITY__CHRONOS__ENABLED`
- `THEOGONY_CURIOSITY__CHRONOS__MAX_ENTRIES_PER_PASS`
- `THEOGONY_CURIOSITY__CHRONOS__CONFIDENCE_DEMOTE_DELTA`

Defaults:

- enabled: `False`
- max_entries_per_pass: `100`
- min_severity_for_demotion: `"medium"`
- confidence_demote_delta: `0.1`
- negative_edge_confidence: `0.8`
- negative_edge_weight: `0.7`
- hard_delete_enabled: `False`

### Knob 5 - Chronos worker

Add `src/theogony/agents/chronos.py`.

Public API:

```python
class ChronosAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pool_entry_id: str
    finding_id: str
    finding_type: str
    severity: str
    action: Literal["cleared_no_issue", "annotated", "demoted", "negative_edge_written", "skipped_missing_finding"]
    target_node_ids: list[str] = Field(default_factory=list)
    edges_written: int = Field(default=0, ge=0)
    nodes_demoted: int = Field(default=0, ge=0)
    reason: str = ""

class ChronosRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processed_entries: int = 0
    findings_seen: int = 0
    findings_resolved: int = 0
    negative_edges_written: int = 0
    nodes_demoted: int = 0
    pool_entries_cleared: int = 0
    skipped_reason: str | None = None
    actions: list[ChronosAction] = Field(default_factory=list)

class ChronosRecycler:
    def __init__(
        self,
        *,
        store: KnowledgeStore,
        pool: VerificationPool,
        settings: ChronosSettings,
    ) -> None: ...

    async def run_once(self) -> ChronosRunSummary: ...
```

Candidate selection:

- Only process `PoolEntry` rows with `lifecycle == "sampled_by_athene"`.
- Only process rows where `finding_ids` is non-empty.
- Sort by `sampled_at` ascending, then `acquired_at` ascending.
- Limit to `settings.max_entries_per_pass`.

For each finding id:

1. Load node via `store.get_node(finding_id)`.
2. If missing: append `ChronosAction(action="skipped_missing_finding")`; do not clear pool entry.
3. Parse with `finding_from_node`.
4. If `finding.finding_type == "no_issue_observed"`:
   - update finding node with `resolution_action="annotated"`
   - mark pool entry cleared
   - action = `cleared_no_issue`
5. Else:
   - create contradiction edges via `contradiction_edges_for_finding(...)`
   - write edges via `batch_upsert_edges`
   - if severity is at or above `min_severity_for_demotion` and `target_node_ids` non-empty, demote target confidence by `confidence_demote_delta`
   - update finding node with:
     - `resolution_action="demoted"` if any node demoted
     - else `resolution_action="annotated"`
   - mark pool entry cleared
   - action:
     - `negative_edge_written` if edges were written
     - `demoted` if no edges but demotion happened
     - `annotated` otherwise

Severity order:

```python
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
```

Demotion algorithm:

- For each target node id:
  - `node = await store.get_node(target_id)`
  - if missing: skip
  - `new_confidence = max(0.0, node.scores.confidence - settings.confidence_demote_delta)`
  - write via `batch_update_scores([ScoreUpdate(node_id=target_id, confidence=new_confidence, vitality=node.scores.model_copy(update={"confidence": new_confidence}).vitality())])`

No layer degradation in W15. Do not call `store.degrade`. Layer movement belongs to a later Chronos pass once false-positive/false-negative telemetry exists.

### Knob 6 - Chronos run report

Add `src/theogony/curiosity/chronos_report.py`.

```python
class ChronosRunReport(RunReportBase):
    report_type: Literal["chronos"] = "chronos"
    processed_entries: int = Field(ge=0)
    findings_seen: int = Field(ge=0)
    findings_resolved: int = Field(ge=0)
    negative_edges_written: int = Field(ge=0)
    nodes_demoted: int = Field(ge=0)
    pool_entries_cleared: int = Field(ge=0)
    actions: list[ChronosAction] = Field(default_factory=list)
```

Update:

- `RunReportBase.report_type` literal to include `"chronos"`
- `src/theogony/reporting/writer.py` `ReportType`, `most_recent`, and imports to support `ChronosRunReport`

Report verdict rules:

- `good` if completed and no anomalies
- `partial` if some findings were missing or some target nodes missing
- `poor` if zero pool entries cleared while findings were seen
- `failed` only on unexpected exception (the CLI may let exceptions surface; tests focus on normal paths)

This report is mandatory. AGENTS.md says new pipelines emit reports; Chronos is a pipeline.

### Knob 7 - CLI command

Add command under existing `curiosity_app` in `src/theogony/cli.py`:

```bash
theogony curiosity chronos-run --once --store memory
```

Options:

- `--once` required. If omitted, print help and exit code 2. No daemon loop in W15.
- `--store` choices: `memory` or `neo4j`, default `memory`.

CLI behaviour:

- If Chronos disabled: print `Chronos disabled` and exit 0.
- If no eligible entries: print `processed=0 findings=0 cleared=0` and exit 0.
- Else print `processed=<n> findings=<m> cleared=<k> demoted=<d> negative_edges=<e>` and exit 0.
- Always write a `ChronosRunReport` to `settings.run_reports_dir / "chronos"`.

### Knob 8 - Cockpit visibility

W14 added `GET /cockpit/api/verification-pool` and a small Immune system panel.

In W15, keep this small:

- Ensure the panel shows `cleared`.
- Add a line for `findings_total`.
- No Chronos SSE.
- No live daemon status.
- No graph visualisation of contradiction edges.

If W14 already shows both `cleared` and `findings_total`, no UI change is required. Add/adjust one endpoint test to assert `cleared` is present in the DTO.

### Knob 9 - Demo docs

Edit `demo/living_growth.md` and `docs/LIVING_DEMO.md`.

After the W14 Athene optional beat, add:

```text
Operator runs: theogony curiosity chronos-run --once --store neo4j
Cockpit Immune system panel updates: cleared increases.
If Athene found only no_issue_observed findings, Chronos clears without negative edges.
If Athene found an issue with target nodes, Chronos writes negative-knowledge edges and may demote confidence.
```

Do not claim the demo proves truth repair. It proves immune response plumbing: Findings are consumed, actions are recorded, and pool entries clear.

Edit `demo/reset_living_growth.sh`:

- add `THEOGONY_CURIOSITY__CHRONOS__ENABLED=true`
- keep Athene demo sample rate at `1.0`

### Knob 10 - Backlog hygiene

Append to `docs/PHOENIX_BACKLOG.md` under `## Wave 3 annotations`:

```markdown
- PHX-0062 (Negative Knowledge): **W15 partial implementation.** Chronos v0.1 consumes
  Athene Finding nodes and writes `CONTRADICTS` edges only for finding types that are
  semantically factual (`factual_error_suspected`, `internal_contradiction`) and have
  explicit target_node_ids. `SUPERSEDED_BY`, negation-node surfacing in retrieval, and
  synthesizer contradiction display remain open.

- PHX-0071 (Mnemosyne): **W15 metric source.** ChronosRunReport becomes another metric
  stream for Mnemosyne W17: findings_seen, findings_resolved, negative_edges_written,
  nodes_demoted, pool_entries_cleared.
```

No new PHX ticket unless implementation friction triggers a STOP rule.

---

## Files to add / change

**New**

- `src/theogony/agents/chronos.py`
- `src/theogony/curiosity/negative_knowledge.py`
- `src/theogony/curiosity/chronos_report.py`
- `tests/agents/test_chronos.py`
- `tests/curiosity/test_negative_knowledge.py`
- `tests/curiosity/test_chronos_report.py`
- `tests/cli/test_chronos_cli.py`

**Edit**

- `src/theogony/curiosity/finding.py` - parse/update helpers; widen finding type/cell
- `src/theogony/curiosity/verification_pool.py` - add `mark_cleared`
- `src/theogony/config/settings.py` - add `ChronosSettings`
- `src/theogony/reporting/models.py` - add `report_type="chronos"` to `RunReportBase`
- `src/theogony/reporting/writer.py` - support `ChronosRunReport`
- `src/theogony/cli.py` - add `curiosity chronos-run --once`
- `src/theogony/cockpit/router.py` / cockpit tests only if `cleared` is not already exposed
- `demo/reset_living_growth.sh`
- `demo/living_growth.md`
- `docs/LIVING_DEMO.md`
- `docs/PHOENIX_BACKLOG.md`

**Forbidden in this PR**

- No LLM calls.
- No web calls.
- No hard deletes.
- No calls to `store.degrade`.
- No scheduler/daemon loop.
- No changes to Argus, ResearchPlanner, Evaluator, acquisition adapters, extraction, retrieval, or answer synthesis.
- No `SUPERSEDED_BY` edges in W15.
- No broad PHX-0062 retrieval/synthesizer surfacing work.

---

## Acceptance criteria (machine-runnable)

### A1 - Lint and type

```bash
ruff format
ruff check
mypy src/theogony/agents src/theogony/curiosity src/theogony/config/settings.py src/theogony/reporting src/theogony/cli.py src/theogony/cockpit src/theogony/core/model.py
```

### A2 - Finding helpers

```bash
pytest -q tests/curiosity/test_finding.py
```

Required new tests:

- `test_finding_from_node_round_trips_w14_finding`
- `test_finding_from_node_rejects_non_finding_node`
- `test_resolved_finding_node_updates_resolution_fields_only`

### A3 - Pool clear method

```bash
pytest -q tests/curiosity/test_verification_pool.py
```

Required new tests:

- `test_mark_cleared_sets_lifecycle_and_cleared_at`
- `test_mark_cleared_preserves_finding_ids`
- `test_mark_cleared_missing_entry_raises`

### A4 - Negative knowledge helper

```bash
pytest -q tests/curiosity/test_negative_knowledge.py
```

Required tests:

- `test_contradiction_edges_for_factual_error_with_targets`
- `test_contradiction_edges_for_internal_contradiction_with_targets`
- `test_no_contradiction_edges_for_structural_finding_types`
- `test_no_contradiction_edges_without_targets`
- `test_negative_edge_properties_reference_chronos_and_pool_entry`

### A5 - Chronos worker

```bash
pytest -q tests/agents/test_chronos.py
```

Required tests:

- `test_chronos_disabled_returns_skipped_summary`
- `test_chronos_no_eligible_entries_returns_zero_summary`
- `test_chronos_clears_no_issue_observed_pool_entry`
- `test_chronos_missing_finding_does_not_clear_pool_entry`
- `test_chronos_writes_contradicts_for_factual_targeted_finding`
- `test_chronos_does_not_write_contradicts_for_structural_finding`
- `test_chronos_demotes_target_confidence_for_medium_or_higher_targeted_finding`
- `test_chronos_does_not_call_store_degrade_or_delete`
- `test_chronos_updates_finding_resolution_properties`

Use `InMemoryKnowledgeStore` for all tests.

### A6 - Chronos report

```bash
pytest -q tests/curiosity/test_chronos_report.py
```

Required tests:

- `test_chronos_run_report_serializes_with_report_type_chronos`
- `test_run_report_writer_round_trips_chronos_report`

### A7 - CLI smoke

```bash
pytest -q tests/cli/test_chronos_cli.py
```

Required tests:

- `test_chronos_run_once_disabled_exits_zero`
- `test_chronos_run_once_prints_counts`
- `test_chronos_run_requires_once_flag`

### A8 - Cockpit status remains green

```bash
pytest -q tests/cockpit/test_verification_pool_status_endpoint.py
```

Add assertion if absent:

- `test_verification_pool_status_includes_cleared_count`

### A9 - Full suite

```bash
pytest -q
```

### A10 - No gate / no hard-delete regression

```bash
rg 'HestiaLite|HestiaSentinel|hestia_review' src/ tests/ && exit 1
rg 'delete_node\\(|store\\.degrade\\(' src/theogony/agents/chronos.py tests/agents/test_chronos.py && exit 1
```

Both commands must return non-zero.

---

## STOP-and-file rules

- If Chronos cannot parse W14 Finding nodes from `KnowledgeNode.properties`, STOP and file PHX. Do not invent a second finding store.
- If writing `CONTRADICTS` edges requires schema/index changes, STOP and file PHX. Relation types are strings today; this should not require a migration.
- If implementing target-node resolution from `ingest_run_id` is tempting, STOP. W15 uses only `Finding.target_node_ids`. W14 usually leaves them empty.
- If tests require touching retrieval or answer synthesis to handle contradiction edges, STOP. That is later PHX-0062 work, not W15.
- If a code path deletes nodes, calls `store.degrade`, or waits for Chronos before ingest completion, STOP. That violates W15 scope.

---

## PR description template

```markdown
W15 - Chronos recycler + negative-knowledge actions

Implements Living Demo Wave 3 slice 3 per docs/etappes/W15_chronos_brief.md.
Builds on W14 Athene verifier (PR #101) and the immune-system doctrine (PR #97).

What this PR does:
- adds ChronosRecycler.run_once(): consumes sampled Athene findings from the verification pool
- adds `mark_cleared` to VerificationPool
- adds Finding parse/update helpers
- adds negative-knowledge helper for `CONTRADICTS` edges when findings are semantically factual and targeted
- demotes target confidence for medium+ targeted findings
- writes ChronosRunReport
- adds `theogony curiosity chronos-run --once`
- updates demo docs and PHX annotations

What this PR does NOT do:
- no hard deletes
- no `SUPERSEDED_BY` edges
- no retrieval/synthesizer contradiction surfacing
- no LLM/web calls
- no scheduler/daemon loop
- no pre-gate or synchronous ingest dependency

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/agents src/theogony/curiosity src/theogony/config/settings.py src/theogony/reporting src/theogony/cli.py src/theogony/cockpit src/theogony/core/model.py`
- `pytest -q tests/curiosity/test_finding.py`
- `pytest -q tests/curiosity/test_verification_pool.py`
- `pytest -q tests/curiosity/test_negative_knowledge.py`
- `pytest -q tests/agents/test_chronos.py`
- `pytest -q tests/curiosity/test_chronos_report.py`
- `pytest -q tests/cli/test_chronos_cli.py`
- `pytest -q tests/cockpit/test_verification_pool_status_endpoint.py`
- `pytest -q`
- no-gate/no-hard-delete rg checks

Notes / deviations:
<list, or "none">

PHX tickets filed:
<list, or "none">

@hesiod-review
```
