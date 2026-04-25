# W17 - Mnemosyne Conductor: Immune Metrics, Experiments, PHX Drafts, Local Test Run (Living Demo Wave 3, slice 5)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-25
**Branch:** `feat/w17-mnemosyne-conductor`
**Scope:** one PR (self-improvement conductor + reports + CLI + local test runbook; no self-modifying code)
**Predecessor:** W16 merged on `main` (PR #105). `docs/IMMUNE_SYSTEM.md` merged on `main` (PR #97). `docs/SELF_MODIFICATION.md` merged on `main` (PR #97).
**Sprint slot:** Living Demo W17 (fifth and final implementation slice in Wave 3)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (PR #105 must be merged; if not, this brief is blocked).
2. `git checkout -b feat/w17-mnemosyne-conductor`
3. Implement.
4. `git push -u origin feat/w17-mnemosyne-conductor`
5. `gh pr create --base main --title "feat(curiosity): W17 - Mnemosyne conductor + Wave 3 local test pack"` with the PR body shape at the bottom.

---

## Why this etappe exists

W13-W16 built the body of the immune system:

1. W13 removed pre-gates and routed research output into the verification pool.
2. W14 added Athene: sample pool entries and write `Finding` nodes.
3. W15 added Chronos: consume findings, clear pool entries, demote targeted confidence, write negative-knowledge actions.
4. W16 added Nemesis and Eris: structural audit and fixture red-team campaign findings.

W17 adds the first consciousness layer above that body.

Mnemosyne v0.2 (conductor) reads the signals the immune system now emits, defines success metrics, writes experiment proposals as chronicle nodes, and drafts Phoenix Backlog proposals into a reviewable draft directory. She does **not** modify code, auto-merge changes, change settings, or run live A/B traffic in W17. That belongs to later Phoenix incarnations and the long-horizon self-modification doctrine.

W17 also prepares the larger local test round the user will run after this sprint: one repeatable operator runbook that exercises the whole Wave 3 loop locally.

---

## Doctrine constraints

These are non-negotiable:

- Mnemosyne is post-hoc. She never runs in the ingest path.
- Mnemosyne does not change production settings in W17. She proposes.
- Mnemosyne does not write to `phoenix-backlog/` in W17. She writes drafts under `settings.run_reports_dir/backlog_proposals/`.
- Mnemosyne does not open GitHub PRs, branches, commits, or deploys in W17. `docs/SELF_MODIFICATION.md` names the horizon; W17 does not implement it.
- Mnemosyne's metric definition is LLM-capable and self-authored, but CI must not depend on a live provider. Tests inject a fake metric definer or use a deterministic fixture mode.
- No new pre-gate, Hestia shape, synchronous verifier, or hidden human review queue.

If implementation pressure makes any of these hard, STOP and file PHX.

---

## Current W16 interfaces Mnemosyne must consume

These exist on `main` after PR #105:

- `src/theogony/curiosity/verification_pool.py`
  - `VerificationPool.stats()`
  - `VerificationPool.entries()`
- `src/theogony/curiosity/finding.py`
  - `Finding`
  - `finding_from_node`
  - `NodeType.FINDING` materialisation via `Finding.to_knowledge_node()`
- `src/theogony/curiosity/chronos_report.py`
  - `ChronosRunReport`
  - `ChronosRunSummary`
- `src/theogony/curiosity/nemesis_report.py`
  - `NemesisRunReport`
- `src/theogony/curiosity/eris_report.py`
  - `ErisCampaignReport`
- existing Mnemosyne Phase-1:
  - `MetaClassification`
  - `MnemosyneObservationCluster`
  - `run_mnemosyne_aggregation(...)`
- `RunReportWriter`
  - `most_recent(report_type)`
  - `directory_for(report_type)`
  - `write(report)`
- `KnowledgeStore`
  - `export_layer`
  - `batch_upsert_nodes`

Do not invent a second report store or a second finding format.

---

## Locked knobs

### Knob 1 - New conductor report and DTO models

Add `src/theogony/curiosity/mnemosyne_conductor_report.py`.

Models:

```python
ImmuneMetricSnapshot = BaseModel(...)
MetricDefinition = BaseModel(...)
ExperimentProposal = BaseModel(...)
BacklogProposalDraft = BaseModel(...)
MnemosyneExperimentNodePayload = BaseModel(...)
MnemosyneConductorSummary = BaseModel(...)
MnemosyneConductorReport = RunReportBase(...)
```

Exact shapes:

```python
class ImmuneMetricSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pool_total: int = 0
    pool_unobserved: int = 0
    pool_sampled_by_athene: int = 0
    pool_cleared: int = 0
    pool_findings_total: int = 0

    finding_count_by_cell: dict[str, int] = Field(default_factory=dict)
    finding_count_by_type: dict[str, int] = Field(default_factory=dict)
    finding_count_by_severity: dict[str, int] = Field(default_factory=dict)
    unresolved_finding_count: int = 0

    latest_chronos_findings_seen: int = 0
    latest_chronos_findings_resolved: int = 0
    latest_chronos_negative_edges_written: int = 0
    latest_chronos_nodes_demoted: int = 0
    latest_chronos_pool_entries_cleared: int = 0

    latest_nemesis_findings_written: int = 0
    latest_eris_probes_run: int = 0
    latest_eris_failed: int = 0

    query_reports_scanned: int = 0
    query_verdict_counts: dict[str, int] = Field(default_factory=dict)
    ingest_reports_scanned: int = 0
    ingest_verdict_counts: dict[str, int] = Field(default_factory=dict)
```

```python
class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    name: str
    rationale: str
    numerator: str
    denominator: str
    desired_direction: Literal["increase", "decrease", "stabilize"]
    current_value: float | None = None
    target_value: float | None = None
    source: Literal["llm", "fixture"]
```

```python
class ExperimentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    metric_id: str
    hypothesis: str
    regime_a: dict[str, str]
    regime_b: dict[str, str]
    expected_effect: str
    risk: Literal["low", "medium", "high"]
    auto_apply_allowed: bool = False
```

```python
class BacklogProposalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    title: str
    rationale: str
    suggested_category: Literal["bug", "test", "refactor", "feature", "vision", "ops"]
    source_metric_ids: list[str] = Field(default_factory=list)
    source_report_ids: list[str] = Field(default_factory=list)
    proposed_acceptance_criteria: list[str] = Field(default_factory=list)
```

```python
class MnemosyneConductorSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics_defined: int = 0
    experiment_nodes_written: int = 0
    backlog_drafts_written: int = 0
    skipped_reason: str | None = None
    llm_cost_eur: float = 0.0
    metric_definitions: list[MetricDefinition] = Field(default_factory=list)
    experiment_proposals: list[ExperimentProposal] = Field(default_factory=list)
    backlog_drafts: list[BacklogProposalDraft] = Field(default_factory=list)
```

```python
class MnemosyneConductorReport(RunReportBase):
    report_type: Literal["mnemosyne_conductor"] = "mnemosyne_conductor"
    snapshot: ImmuneMetricSnapshot
    metrics_defined: int = Field(ge=0)
    experiment_nodes_written: int = Field(ge=0)
    backlog_drafts_written: int = Field(ge=0)
    llm_cost_eur: float = Field(default=0.0, ge=0.0)
    metric_definitions: list[MetricDefinition] = Field(default_factory=list)
    experiment_proposals: list[ExperimentProposal] = Field(default_factory=list)
    backlog_drafts: list[BacklogProposalDraft] = Field(default_factory=list)
```

Add helper:

```python
def build_mnemosyne_conductor_report(
    summary: MnemosyneConductorSummary,
    *,
    snapshot: ImmuneMetricSnapshot,
    started_at: datetime,
    finished_at: datetime,
) -> MnemosyneConductorReport: ...
```

Report verdict:

- `good` if enabled run completes.
- `partial` if LLM metric definition was requested but fixture fallback was used.
- `poor` if no metrics could be defined from a non-empty snapshot.
- `failed` only for unexpected exception.

Update:

- `RunReportBase.report_type` literal to include `"mnemosyne_conductor"`.
- `RunReportWriter.ReportType`, `most_recent`, and imports to support `MnemosyneConductorReport`.
- report-type lists in CLI/MCP/cockpit aggregations where currently hardcoded, so `reports list --type mnemosyne_conductor` works.

### Knob 2 - Mnemosyne experiment node projection

Add `src/theogony/curiosity/mnemosyne_experiment.py`.

Add:

```python
class MnemosyneExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(default_factory=lambda: f"MNEMO-EXP-{uuid.uuid4()}")
    metric_definition: MetricDefinition
    hypothesis: str
    regime_a: dict[str, str]
    regime_b: dict[str, str]
    status: Literal["proposed", "dry_run_completed", "accepted", "rejected"] = "proposed"
    winner: Literal["a", "b", "inconclusive"] | None = None
    auto_applied: bool = False
    rationale: str
    drafted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None

    def to_knowledge_node(self) -> KnowledgeNode: ...
```

Add `NodeType.EXPERIMENT = "experiment"` to `src/theogony/core/model.py`.

`to_knowledge_node()`:

- `id=experiment_id`
- `node_type=NodeType.EXPERIMENT`
- `label=f"Mnemosyne experiment: {metric_definition.name}"`
- `description=hypothesis`
- `epistemic_status=EpistemicStatus.HYPOTHESIZED`
- `layer=Layer.EPHEMERA`
- `source_ref=SourceRef(source_type="mnemosyne", identifier=experiment_id)`
- `properties` includes all scalar fields plus `metric_definition`, `regime_a`, `regime_b`

No edges in W17. Experiment-to-finding graph links are future work.

### Knob 3 - Metric definition interface

Add `src/theogony/agents/mnemosyne_conductor.py`.

Metric-definition protocol:

```python
class MetricDefiner(Protocol):
    async def define_metrics(self, snapshot: ImmuneMetricSnapshot) -> tuple[list[MetricDefinition], float]:
        ...
```

Implement two definers:

1. `FixtureMetricDefiner`
2. `LLMMetricDefiner`

`FixtureMetricDefiner` is deterministic and used by tests. It is also the fallback when an operator explicitly sets fixture mode.

Fixture metrics, exact list:

- `pool_clearance_ratio`
  - numerator: `pool_cleared`
  - denominator: `pool_total`
  - desired_direction: `increase`
  - current_value: `pool_cleared / pool_total` if `pool_total > 0` else `None`
  - target_value: `0.8`
- `unresolved_finding_ratio`
  - numerator: `unresolved_finding_count`
  - denominator: `pool_findings_total`
  - desired_direction: `decrease`
  - current_value: `unresolved_finding_count / pool_findings_total` if denominator > 0 else `None`
  - target_value: `0.2`
- `red_team_failure_count`
  - numerator: `latest_eris_failed`
  - denominator: `latest_eris_probes_run`
  - desired_direction: `decrease`
  - current_value: `latest_eris_failed`
  - target_value: `0.0`

`LLMMetricDefiner`:

- Uses `LLMProvider.complete(...)` with JSON schema for a list of `MetricDefinition`.
- Temperature: `0.2`.
- Max output tokens: `1200`.
- Timeout: settings-defined (Knob 5).
- It sees only the serialized `ImmuneMetricSnapshot` and a short system prompt:
  `"You are Mnemosyne. Define 1-5 success metrics for improving the immune system. Do not propose code changes. Output JSON only."`
- It returns `(metrics, cost_eur)`.

If the LLM call raises or returns invalid JSON, the conductor falls back to `FixtureMetricDefiner`, sets `llm_cost_eur` to whatever was available (usually 0), and the report verdict becomes `partial`.

### Knob 4 - Snapshot collector

In `src/theogony/agents/mnemosyne_conductor.py`, implement:

```python
class ImmuneMetricCollector:
    def __init__(self, *, store: KnowledgeStore, pool: VerificationPool, writer: RunReportWriter) -> None: ...
    async def collect(self) -> ImmuneMetricSnapshot: ...
```

Collect:

1. Pool stats from `VerificationPool.stats()`.
2. Finding counts by scanning store layers EPHEMERA and MNEME and filtering `node.node_type == NodeType.FINDING`; parse with `finding_from_node`.
   - `finding_count_by_cell`
   - `finding_count_by_type`
   - `finding_count_by_severity`
   - `unresolved_finding_count`: `resolution_action == "none"` or `resolved_at is None`
3. Latest Chronos report from `writer.most_recent("chronos")`.
4. Latest Nemesis report from `writer.most_recent("nemesis")`.
5. Latest Eris report from `writer.most_recent("eris")`.
6. Query verdict counts by scanning JSON files under `writer.directory_for("query")`, max newest 200 files.
7. Ingest verdict counts by scanning JSON files under `writer.directory_for("ingest")`, max newest 200 files.

Do not scan arbitrary old report types beyond those named above. Keep W17 bounded.

### Knob 5 - Mnemosyne settings

Edit `src/theogony/config/settings.py`.

Extend existing `MnemosyneSettings` (do not create a second top-level settings group):

```python
conductor_enabled: bool = False
metric_definition_mode: Literal["llm", "fixture"] = "llm"
metric_definition_timeout_s: float = Field(default=20.0, gt=0.0, le=120.0)
max_metric_definitions_per_pass: int = Field(default=5, ge=1, le=20)
max_experiment_proposals_per_pass: int = Field(default=3, ge=0, le=20)
max_backlog_drafts_per_pass: int = Field(default=3, ge=0, le=20)
auto_apply_enabled: bool = False
backlog_draft_dir_name: str = "backlog_proposals"
```

Rules:

- `auto_apply_enabled` exists but is unused in W17 except a test that proves no settings are changed even if it is true.
- `metric_definition_mode="llm"` is the doctrine-aligned default.
- Tests can use `metric_definition_mode="fixture"` or inject a fake definer.

Environment variables:

- `THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED`
- `THEOGONY_MNEMOSYNE__METRIC_DEFINITION_MODE`
- `THEOGONY_MNEMOSYNE__MAX_METRIC_DEFINITIONS_PER_PASS`
- `THEOGONY_MNEMOSYNE__MAX_EXPERIMENT_PROPOSALS_PER_PASS`
- `THEOGONY_MNEMOSYNE__MAX_BACKLOG_DRAFTS_PER_PASS`

### Knob 6 - Conductor worker

In `src/theogony/agents/mnemosyne_conductor.py`, add:

```python
class MnemosyneConductor:
    def __init__(
        self,
        *,
        store: KnowledgeStore,
        pool: VerificationPool,
        writer: RunReportWriter,
        settings: Settings,
        metric_definer: MetricDefiner | None = None,
        llm: LLMProvider | None = None,
    ) -> None: ...

    async def run_once(self) -> tuple[MnemosyneConductorSummary, ImmuneMetricSnapshot]: ...
```

`run_once()`:

1. If `settings.mnemosyne.conductor_enabled` is false, return summary with `skipped_reason="mnemosyne conductor disabled"` and a collected snapshot.
2. Collect snapshot.
3. Choose metric definer:
   - injected `metric_definer` wins
   - else if `metric_definition_mode == "fixture"`: `FixtureMetricDefiner`
   - else if mode is `"llm"` and `llm is not None` and provider is not stub: `LLMMetricDefiner`
   - else fallback to `FixtureMetricDefiner` and mark fallback in summary recommendations/report reasoning
4. Define metrics, cap at `max_metric_definitions_per_pass`.
5. Build experiment proposals from metrics, cap at `max_experiment_proposals_per_pass`.
6. Convert experiment proposals to `MnemosyneExperiment` nodes and write via `store.batch_upsert_nodes`.
7. Build backlog drafts from metrics/snapshot, cap at `max_backlog_drafts_per_pass`.
8. Write backlog drafts as JSON files under `settings.run_reports_dir / settings.mnemosyne.backlog_draft_dir_name / f"{draft_id}.json"`.
9. Return summary and snapshot. The CLI writes the report.

Experiment proposal rules:

- For `pool_clearance_ratio`: propose `athene_sample_rate_experiment` with:
  - regime_a `{"THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE": "0.02"}`
  - regime_b `{"THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE": "0.05"}`
  - auto_apply_allowed false
- For `unresolved_finding_ratio`: propose `chronos_cadence_experiment` with:
  - regime_a `{"manual_frequency": "operator-run-after-athene"}`
  - regime_b `{"manual_frequency": "operator-run-twice-after-athene"}`
  - auto_apply_allowed false
- For `red_team_failure_count`: propose `eris_probe_review_experiment` with:
  - regime_a `{"eris_fixture_campaign": "baseline"}`
  - regime_b `{"eris_fixture_campaign": "add-one-live-answerer-probe"}`
  - auto_apply_allowed false

Backlog draft rules:

- If `latest_eris_failed > 0`: draft title `"Improve groundedness against Eris adversarial probes"`.
- If `latest_nemesis_findings_written > 0`: draft title `"Review structural hubris signals surfaced by Nemesis"`.
- If `pool_total > 0 and pool_cleared / pool_total < 0.5`: draft title `"Improve immune-system clearance rate"`.

Do not write real `phoenix-backlog/PHX-*.yaml`.

### Knob 7 - CLI command

Add command under existing `mnemosyne_app` in `src/theogony/cli.py`:

```bash
theogony mnemosyne conduct --once --store memory
```

Options:

- `--once` required. If omitted, exit code 2.
- `--store` choices `memory|neo4j`, default `memory`.
- `--metric-mode` optional override, choices `llm|fixture`. If provided, apply via `settings.model_copy(update={"mnemosyne": ...})` for this run only.

CLI behaviour:

- If disabled: print `Mnemosyne conductor disabled` and still write a `MnemosyneConductorReport` with zero metrics and the snapshot.
- Else print:
  `metrics=<m> experiments=<e> drafts=<d> llm_cost_eur=<c>`
- Always write `MnemosyneConductorReport` to `settings.run_reports_dir / "mnemosyne_conductor"`.

Do not add a daemon/scheduler in W17.

### Knob 8 - Cockpit/report visibility

Minimal only:

- Add `"mnemosyne_conductor"` to report type lists so the report appears in cockpit/reports and MCP report listing.
- Do not build a new cockpit panel.
- Do not add SSE.

If report type lists are duplicated, update all obvious hardcoded tuples found by `rg '"mnemosyne"' src/theogony`.

### Knob 9 - Local live test runbook

Add `demo/wave3_local_test.md`.

Purpose: the user will run this locally after W17. It must be explicit and honest.

Required sections:

1. **Prereqs**
   - local repo on `main`
   - `.venv` ready
   - local Neo4j available if using `--store neo4j`
   - `ANTHROPIC_API_KEY` required only for research planner / live LLM; Mnemosyne conductor can run with `--metric-mode fixture`

2. **Reset**
   ```bash
   THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh
   ```

3. **Run cockpit**
   ```bash
   .venv/bin/theogony cockpit serve --host 127.0.0.1 --port 8000
   ```

4. **Ask and research**
   - URL: `http://127.0.0.1:8000/cockpit/explorer?growth=on`
   - query: `"Wer war Sven Hedin und was hat er in Tibet erforscht?"`
   - expected: research panel emits `planning_started`, `executing_step`, `acquired_into_pool`, `ingested`, `research_complete`

5. **Run immune workers**
   ```bash
   .venv/bin/theogony curiosity athene-run --once --store neo4j
   .venv/bin/theogony curiosity chronos-run --once --store neo4j
   .venv/bin/theogony curiosity nemesis-run --once --store neo4j
   THEOGONY_CURIOSITY__ERIS__ENABLED=true .venv/bin/theogony curiosity eris-run --once --store memory --fixture
   .venv/bin/theogony mnemosyne conduct --once --store neo4j --metric-mode fixture
   ```

6. **Inspect reports**
   ```bash
   .venv/bin/theogony reports list --type chronos
   .venv/bin/theogony reports list --type nemesis
   .venv/bin/theogony reports list --type eris
   .venv/bin/theogony reports list --type mnemosyne_conductor
   ```

7. **Success criteria**
   - pool has at least one entry after research
   - Athene writes at least one finding
   - Chronos clears at least one sampled pool entry or reports why not
   - Nemesis writes a report, even if zero findings
   - Eris fixture writes a report
   - Mnemosyne conductor writes a report and at least one metric definition in fixture mode
   - backlog draft directory exists; it may be empty if no signal crossed draft rules

8. **What this does not prove**
   - not factual truth
   - not live adversarial robustness
   - not self-modifying code
   - not production scheduling

Update `docs/LIVING_DEMO.md` to link to `demo/wave3_local_test.md`.

### Knob 10 - Backlog hygiene

Append to `docs/PHOENIX_BACKLOG.md` under `## Wave 3 annotations`:

```markdown
- PHX-0071 (Mnemosyne): **W17 partial implementation.** Mnemosyne conductor reads immune-system
  metrics across pool stats, Finding nodes, Chronos reports, Nemesis reports, Eris reports, and
  query/ingest verdict counts. It defines metrics (LLM-capable, fixture-backed for CI), writes
  MnemosyneExperiment nodes, and writes BacklogProposalDraft JSON files under run_reports. It
  does not auto-apply settings, write real PHX YAMLs, or modify code.

- SELF_MODIFICATION.md: **Boundary reaffirmed.** W17 does not implement self-modifying Pantheon.
  It only creates the observation and proposal surface that future Phoenix incarnations may use.
```

No new PHX ticket unless implementation friction triggers a STOP rule.

---

## Files to add / change

**New**

- `src/theogony/agents/mnemosyne_conductor.py`
- `src/theogony/curiosity/mnemosyne_conductor_report.py`
- `src/theogony/curiosity/mnemosyne_experiment.py`
- `demo/wave3_local_test.md`
- `tests/agents/test_mnemosyne_conductor.py`
- `tests/curiosity/test_mnemosyne_conductor_report.py`
- `tests/curiosity/test_mnemosyne_experiment.py`
- `tests/cli/test_mnemosyne_conduct_cli.py`

**Edit**

- `src/theogony/core/model.py` - add `NodeType.EXPERIMENT`
- `src/theogony/config/settings.py` - extend `MnemosyneSettings`
- `src/theogony/reporting/models.py` - add `report_type="mnemosyne_conductor"`
- `src/theogony/reporting/writer.py` - support `MnemosyneConductorReport`
- `src/theogony/cli.py` - add `mnemosyne conduct`
- `src/theogony/mcp/server.py` - include `mnemosyne_conductor` in reports list/show accepted types
- `src/theogony/cockpit/aggregations.py` / `router.py` report tabs if hardcoded
- `docs/LIVING_DEMO.md`
- `docs/PHOENIX_BACKLOG.md`

**Forbidden in this PR**

- No code modification by Mnemosyne.
- No GitHub API calls.
- No writing to `phoenix-backlog/`.
- No settings auto-apply.
- No scheduler/daemon loop.
- No new live traffic A/B splitting.
- No pre-gate/verifier path.
- No changes to Argus, ResearchPlanner, Evaluator, acquisition adapters, extraction, retrieval, or answer synthesis.
- No self-modification implementation.

---

## Acceptance criteria (machine-runnable)

### A1 - Lint and type

```bash
ruff format
ruff check
mypy src/theogony/agents src/theogony/curiosity src/theogony/config/settings.py src/theogony/reporting src/theogony/cli.py src/theogony/core/model.py
```

If full-tree mypy still has pre-existing issues, run and report the narrower command above plus `pytest -q`.

### A2 - Conductor report

```bash
pytest -q tests/curiosity/test_mnemosyne_conductor_report.py
```

Required tests:

- `test_mnemosyne_conductor_report_serializes_with_report_type`
- `test_run_report_writer_round_trips_mnemosyne_conductor_report`
- `test_build_report_marks_partial_when_llm_fallback_used`

### A3 - Experiment node

```bash
pytest -q tests/curiosity/test_mnemosyne_experiment.py
```

Required tests:

- `test_mnemosyne_experiment_to_knowledge_node_uses_experiment_type`
- `test_experiment_node_properties_include_metric_and_regimes`
- `test_experiment_node_is_hypothesized_ephemera`

### A4 - Metric snapshot collector

```bash
pytest -q tests/agents/test_mnemosyne_conductor.py
```

Required tests:

- `test_collector_counts_pool_stats`
- `test_collector_counts_finding_nodes_by_cell_type_severity`
- `test_collector_reads_latest_chronos_nemesis_eris_reports`
- `test_collector_counts_query_and_ingest_verdicts`

### A5 - Conductor worker

Continue in `tests/agents/test_mnemosyne_conductor.py`.

Required tests:

- `test_conductor_disabled_returns_snapshot_and_skipped_summary`
- `test_fixture_metric_definer_defines_expected_metrics`
- `test_conductor_writes_experiment_nodes`
- `test_conductor_writes_backlog_draft_json_files`
- `test_conductor_falls_back_to_fixture_when_llm_unavailable`
- `test_conductor_does_not_modify_settings_even_when_auto_apply_enabled`
- `test_conductor_never_writes_to_phoenix_backlog`

### A6 - CLI smoke

```bash
pytest -q tests/cli/test_mnemosyne_conduct_cli.py
```

Required tests:

- `test_mnemosyne_conduct_disabled_exits_zero_and_writes_report`
- `test_mnemosyne_conduct_fixture_mode_prints_counts`
- `test_mnemosyne_conduct_requires_once_flag`

### A7 - Report visibility

Existing report tests or new minimal tests must assert:

- `theogony reports list --type mnemosyne_conductor` accepts the type
- MCP report type enum/help includes `mnemosyne_conductor` if that list is hardcoded
- cockpit report tabs include `mnemosyne_conductor` if hardcoded

### A8 - Full suite

```bash
pytest -q
```

### A9 - No self-modification / no auto-apply regression

```bash
rg 'git |gh |github|pull request|push\\(|commit\\(' src/theogony/agents/mnemosyne_conductor.py src/theogony/curiosity/mnemosyne_experiment.py && exit 1
rg 'phoenix-backlog' src/theogony/agents/mnemosyne_conductor.py tests/agents/test_mnemosyne_conductor.py && exit 1
rg 'os\\.environ\\[|write_text\\(.*settings|THEOGONY_.*=' src/theogony/agents/mnemosyne_conductor.py && exit 1
```

All three commands must return non-zero. If a test string needs to mention `phoenix-backlog`, put it in docs or use a variable split so the guard remains meaningful.

### A10 - Local test runbook exists

```bash
test -f demo/wave3_local_test.md
rg 'mnemosyne conduct --once' demo/wave3_local_test.md
rg 'What this does not prove' demo/wave3_local_test.md
```

---

## STOP-and-file rules

- If adding `NodeType.EXPERIMENT` requires Neo4j schema migration beyond ordinary node_type string storage, STOP and file PHX.
- If LLM metric definition cannot be made schema-validated through `LLMProvider.complete(..., json_schema=...)`, fall back to fixture mode, document the limitation, and file PHX. Do not parse unstructured prose.
- If report-type hardcoded lists are spread wider than expected, update obvious locations only (`cli.py`, `mcp/server.py`, cockpit report aggregation/router). If more than 5 files beyond those are required, STOP and file PHX.
- If writing backlog drafts risks touching real `phoenix-backlog/`, STOP. W17 drafts belong under run reports only.
- If implementing live A/B traffic splitting is tempting, STOP. W17 creates experiment proposals; it does not run live traffic splits.
- If any W17 code modifies environment variables, settings files, git branches, GitHub PRs, or deployment state, STOP.

---

## PR description template

```markdown
W17 - Mnemosyne conductor + Wave 3 local test pack

Implements Living Demo Wave 3 slice 5 per docs/etappes/W17_mnemosyne_conductor_brief.md.
Builds on W16 Nemesis/Eris (PR #105), W15 Chronos (PR #103), W14 Athene (PR #101),
and the immune-system / self-modification doctrines (PR #97).

What this PR does:
- adds ImmuneMetricSnapshot and MnemosyneConductorReport
- adds MetricDefinition, ExperimentProposal, BacklogProposalDraft
- adds MnemosyneExperiment nodes (`NodeType.EXPERIMENT`)
- adds MnemosyneConductor: collects immune metrics, defines metrics, writes experiment nodes,
  writes backlog proposal drafts under run_reports
- adds `theogony mnemosyne conduct --once`
- adds `demo/wave3_local_test.md` for the upcoming local live test round

What this PR does NOT do:
- no code modification, GitHub calls, PR creation, or self-modification
- no writing to real phoenix-backlog YAMLs
- no settings auto-apply
- no live A/B traffic splitting
- no scheduler/daemon loop
- no changes to research/acquisition/extraction/retrieval/synthesis

Acceptance criteria run locally:
- `ruff format && ruff check`
- narrow `mypy ...` command from the brief
- `pytest -q tests/curiosity/test_mnemosyne_conductor_report.py`
- `pytest -q tests/curiosity/test_mnemosyne_experiment.py`
- `pytest -q tests/agents/test_mnemosyne_conductor.py`
- `pytest -q tests/cli/test_mnemosyne_conduct_cli.py`
- `pytest -q`
- no-self-modification rg checks
- local test runbook existence checks

Notes / deviations:
<list, or "none">

PHX tickets filed:
<list, or "none">

@hesiod-review
```
