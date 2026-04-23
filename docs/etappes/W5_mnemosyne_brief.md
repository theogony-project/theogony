# W5 — Mnemosyne Phase 1 (PHX-0071)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-22  
**Branch:** new branch off `main`, e.g. `feat/w5-mnemosyne`  
**Scope:** one PR  
**Predecessor:** Wave 1 closed (W4 PR #63 + W3 + W2 + W1 all merged). PHX-0070 stub-synth fix landed (PR #65). PHX-0073 (Asklepios) filed alongside this brief but **not** required for W5 — Mnemosyne is upstream-independent. W5 is the **first sprint of Wave 2**.

Direct brief, no Daedalus. Six knobs are pre-locked. Sprint sized similarly to W3.

---

## Why this etappe exists

The chronicle today has no agent that **recognises when a query is about the chronicle itself**. Such queries arrive constantly — the 2026-04-22 conversation about heterogeneous embedding dimensions was one (now recorded in `docs/QUESTIONS_FROM_THE_FIELD.md` as the manual-precursor seed). Today they get answered like any other query and the architectural signal evaporates. Tomorrow Mnemosyne catches them, persists them as `self_referential=True` observations, and — when the pattern is strong enough — drafts a Phoenix Backlog proposal for human review.

The full PHX-0071 spec describes a five-step pipeline (per-query classification → persist meta-flag → aggregate observations → draft BacklogProposal → Hestia review). W5 ships **Phase 1**: steps 1, 2, and 3 — the per-query classifier, the persisted meta-flags, and the aggregator that emits structured `MnemosyneObservation` records. Steps 4 (BacklogProposal drafting) and 5 (Hestia review hook) are deferred to a Phase-2 sub-ticket because they need either a real Hestia (PHX-0039) or a deliberately-scoped prompt-driven LLM drafter; Phase 1 keeps the surface deterministic and produces the input that Phase 2 will consume.

The shape mirrors W3 (StubDetector + BlindSpotAggregationPhase) deliberately — Mnemosyne is the same pattern at the meta-cognitive level. Reusing W3's machinery (clustering, region descriptors, cadence-checked TickPhases, gitignored draft directories) keeps the implementation small and the architectural surface consistent.

---

## Pre-locked design knobs (locked 2026-04-22)

The PHX-0071 YAML left several decisions implicit. They are closed here:

### Knob 1 — Classifier path: heuristic-first, LLM-fallback opt-in

```python
class MetaQueryClassifier:
    """Decide whether a query is self-referential to the Chronik.

    Phase 1 default: deterministic keyword + structural heuristic.
    Sub-millisecond, no I/O. The query, the answer, and the cited
    node ids are scanned against a curated list of self-referential
    markers. The output verdict is one of:
      - "self_referential" (high confidence yes)
      - "not_self_referential" (high confidence no)
      - "uncertain" (mid-band)

    When mode = heuristic_with_llm_fallback (default), uncertain-band
    verdicts escalate to a small LLM call that decides; the LLM call
    is rate-limited per Knob 4.
    """

    def classify(
        self,
        *,
        query: str,
        answer: Answer,
        cited_node_ids: Sequence[str],
        constellation: Constellation,
    ) -> MetaClassification: ...
```

The heuristic is the default and ships in `src/theogony/agents/mnemosyne_classifier.py`:

```python
# Curated marker set — the chronicle's own vocabulary.
_META_KEYWORDS_HIGH = frozenset({
    "chronik", "chronicle", "pantheon", "theogony",
    "embedding", "vector dimension", "vector database",
    "schema", "knowledge node", "knowledge edge",
    "oneirosworker", "morpheus", "athene", "hestia",
    "argus", "zeus", "helios", "cluster_id", "depth_band",
    "pheromone", "constellation", "stub_verdict",
    "blindspot", "backlog", "phx-",
})
_META_KEYWORDS_MID = frozenset({
    "agent", "retrieval", "store", "ingest",
    "tick", "phase", "report", "audit",
    "graph", "modality", "model_id", "provider",
})
```

Scoring (Phase 1, deliberately simple — Phase 2 may train a classifier):

- High-keyword hit in query OR (high-keyword hit in any cited node label) → `self_referential`
- ≥ 2 mid-keyword hits across query+answer → `self_referential`
- Exactly 1 mid-keyword hit AND query length ≥ 50 chars → `uncertain`
- No keyword hits → `not_self_referential`

`uncertain` is the only verdict that triggers the LLM-fallback path when `mode = heuristic_with_llm_fallback`.

### Knob 2 — Storage: meta-flag persisted on cited nodes (additive only)

When `MetaClassification.verdict == "self_referential"`, every node in `Answer.cited_node_ids` gets:

```python
node.properties["self_referential_in_runs"] = (
    node.properties.get("self_referential_in_runs", []) + [run_id]
)
```

Implementation: a small `KnowledgeStore` helper `mark_self_referential(node_ids, run_id)` that does an atomic batch update on the `properties.self_referential_in_runs` field. Both backends implement.

The append-only list is intentional — over time, a node that keeps being cited in self-referential queries accumulates run_ids, which is itself the strongest possible signal that the topic is architecturally important. Phase-2 Mnemosyne can use length-of-list as a cluster strength multiplier.

### Knob 3 — Per-tick aggregation as a default-off TickPhase

Mirrors W3's `BlindSpotAggregationPhase`. Lives at `src/theogony/agents/mnemosyne_phase.py`:

```python
class MnemosyneAggregationPhase:
    name = "mnemosyne_aggregation"

    async def run(self, ctx: TickContext) -> None:
        cfg = ctx.cfg.mnemosyne

        # Cadence check against the most-recent MnemosyneObservation report.
        last = ctx.writer.most_recent("mnemosyne") if ctx.writer else None
        if last is not None:
            elapsed_s = (ctx.started_at - last.created_at).total_seconds()
            if elapsed_s < cfg.aggregation_interval_s:
                return

        # Collect QueryRunReports inside the window where stub_verdict
        # has been computed AND the meta_classification verdict is
        # "self_referential".
        observations = _load_meta_observations_in_window(
            ctx.writer, window_days=cfg.window_days,
        ) if ctx.writer else []
        if len(observations) < cfg.min_observations:
            ctx.extras["mnemosyne_aggregation"] = {
                "skipped": "below min_observations",
                "observations_in_window": len(observations),
            }
            return

        # Cluster region descriptors via W1's HDBSCAN.
        clusters = await _cluster_observations_by_region(
            observations, min_cluster_size=cfg.min_observations
        )

        # Phase 1: emit one MnemosyneObservationCluster per cluster.
        # NO BacklogProposal drafting — that is Phase 2.
        for c in clusters:
            report = _build_observation_cluster_report(c, window_days=cfg.window_days)
            ctx.writer.write(report)

        ctx.extras["mnemosyne_aggregation"] = {
            "observations_scanned": len(observations),
            "clusters_emitted": len(clusters),
        }
```

`MnemosyneObservationCluster` (the per-pass Pydantic) is the **input** that the Phase-2 BacklogProposal drafter will consume. Phase 1 stops at the structured cluster — operator can already read these reports and write PHX tickets manually.

### Knob 4 — LLM-fallback rate limiting + budget cap

When `classifier_mode = heuristic_with_llm_fallback`:

- Mid-band uncertain verdicts escalate to an LLM classification call.
- Hard cap: `Settings.mnemosyne.max_llm_classifications_per_hour` (default 30).
- Per-call cost capped at `Settings.mnemosyne.llm_classification_max_cost_eur` (default 0.001 — about 1k tokens with Claude Haiku).
- The fallback uses the active LLM provider via `build_llm_from_settings` — no new provider integration.
- When the hourly cap is exhausted, uncertain verdicts default to `not_self_referential` (conservative — false negatives only); a counter is recorded in `MnemosyneObservation.llm_fallback_skipped: bool`.

When `classifier_mode = heuristic_only`:

- All uncertain verdicts default to `not_self_referential`.
- No LLM calls regardless of budget.
- Phase-1 conservative default for any deployment without a configured LLM provider, OR for any deployment that wants zero meta-classification cost.

### Knob 5 — Read-only on the chronicle (Mnemosyne writes proposals, never knowledge)

Mnemosyne is read-only on the **knowledge** surface:

- ✅ Allowed: `properties["self_referential_in_runs"]` append on cited nodes (additive metadata).
- ✅ Allowed: write `MnemosyneObservation` records to the report directory.
- ✅ Allowed: write `MnemosyneObservationCluster` records to the report directory.
- ❌ Forbidden: any other node mutation (label, description, scores, layer, depth_band, cluster_id).
- ❌ Forbidden: any edge mutation.
- ❌ Forbidden: writing to `phoenix-backlog/`.
- ❌ Forbidden: writing to `prompts/`.
- ❌ Forbidden: writing to `Settings.run_reports_dir/backlog_proposals/` in Phase 1 (that comes with Phase 2's drafter).

A unit test enforces these invariants — `tests/test_mnemosyne_invisibility.py` calls Mnemosyne's full path against a fixture store and asserts no node/edge mutation occurred beyond the allowlist.

### Knob 6 — Settings + retention

```python
class MnemosyneSettings(BaseModel):
    """Mnemosyne meta-cognitive auditor (PHX-0071 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True)  # per-query classification on
    classifier_mode: Literal[
        "heuristic_only",
        "heuristic_with_llm_fallback",
    ] = "heuristic_with_llm_fallback"
    window_days: float = Field(default=14.0, ge=1.0)
    min_observations: int = Field(default=3, ge=2)
    aggregation_interval_s: float = Field(default=86400.0, ge=0.0)  # daily
    max_llm_classifications_per_hour: int = Field(default=30, ge=0)
    llm_classification_max_cost_eur: float = Field(default=0.001, ge=0.0)
```

`enabled=True` is the per-query classifier default-on (cost is sub-ms heuristic). The `MnemosyneAggregationPhase` is **default-off** in `OneirosSettings.enabled_phases` (operator opts in by adding `"mnemosyne_aggregation"` to the list). This split mirrors W3 exactly.

Observation retention defers to existing `RunReportWriter` retention. Phase 2 may add a Mnemosyne-specific retention knob if observation accumulation outpaces the writer's general policy.

---

## Goal

After this PR:

- `MetaClassification`, `MnemosyneObservation`, `MnemosyneObservationCluster` exist as Pydantic models in `src/theogony/reporting/models.py`.
- `MetaQueryClassifier` lives in `src/theogony/agents/mnemosyne_classifier.py`; pure logic; ~150 lines.
- `MnemosyneLLMFallback` lives in `src/theogony/agents/mnemosyne_llm_fallback.py`; rate-limited LLM escalation; ~80 lines.
- `MnemosyneAggregationPhase` lives in `src/theogony/agents/mnemosyne_phase.py`; default-off; ~150 lines.
- `KnowledgeStore` Protocol gains `mark_self_referential(node_ids: Sequence[str], run_id: str) -> None`. Both backends implement.
- `QueryRunReport` gains `meta_classification: MetaClassification | None = None`.
- `QueryPipeline._finalize_report` invokes the classifier (after `stub_verdict` computation, mirroring the existing pattern), persists the result on the report, and (when verdict == self_referential) marks the cited nodes via the new store helper.
- `Settings.mnemosyne` group exists with the knobs from Knob 6.
- `OneirosWorker.DEFAULT_PHASE_REGISTRY` registers `"mnemosyne_aggregation"`. `OneirosSettings.enabled_phases` default does **not** include it.
- `RunReportWriter` knows how to round-trip `MnemosyneObservationCluster` (the per-pass aggregator output).
- `theogony reports list --type mnemosyne` and `theogony reports show <id>` work.
- `theogony mnemosyne classify "<question>"` (CLI diagnostic) prints the heuristic verdict for a one-shot query.
- `pantheon_reports_list` / `pantheon_reports_show` MCP tools accept `"mnemosyne"` as a `report_type`.
- New tests: `tests/test_mnemosyne_classifier.py`, `tests/test_mnemosyne_llm_fallback.py`, `tests/test_mnemosyne_phase.py`, `tests/test_mnemosyne_pipeline_integration.py`, `tests/test_mnemosyne_invisibility.py`.
- New `docs/MNEMOSYNE.md` documents the meta-cognitive layer; `docs/HIVE.md`, `docs/GLOSSARY.md`, `docs/PHILOSOPHY.md`, `docs/PHOENIX_BACKLOG.md` updated.

---

## Scope decisions (read first)

### 1. The `MetaQueryClassifier`

Lives at `src/theogony/agents/mnemosyne_classifier.py`. ~150 lines.

```python
class MetaClassificationVerdict(StrEnum):
    SELF_REFERENTIAL = "self_referential"
    NOT_SELF_REFERENTIAL = "not_self_referential"
    UNCERTAIN = "uncertain"


class MetaClassification(BaseModel):
    """Per-query meta-cognitive classification (PHX-0071 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    verdict: MetaClassificationVerdict
    high_keyword_hits: int = Field(default=0, ge=0)
    mid_keyword_hits: int = Field(default=0, ge=0)
    cited_label_meta_hits: int = Field(default=0, ge=0)
    classifier_mode_used: Literal["heuristic", "llm_fallback"] = "heuristic"
    llm_fallback_skipped: bool = False  # true when budget exhausted
    llm_cost_eur: float = Field(default=0.0, ge=0.0)


class MetaQueryClassifier:
    name = "mnemosyne"

    def __init__(
        self,
        *,
        cfg: MnemosyneSettings,
        llm_fallback: MnemosyneLLMFallback | None = None,
    ) -> None:
        self._cfg = cfg
        self._llm_fallback = llm_fallback

    async def classify(
        self,
        *,
        query: str,
        answer: Answer,
        cited_node_ids: Sequence[str],
        constellation: Constellation,
    ) -> MetaClassification: ...
```

**Heuristic implementation** per Knob 1, deterministic and cheap. Lowercase tokenisation; substring match against the curated keyword sets; aggregate counts; verdict per the rules.

When `cfg.classifier_mode == "heuristic_with_llm_fallback"` AND verdict is `uncertain` AND the fallback's budget is not exhausted → call `await self._llm_fallback.classify(query, answer, ...)` and override the verdict with the LLM's result.

When the LLM call returns or budget is exhausted, the classification's `classifier_mode_used` and `llm_fallback_skipped` fields are populated honestly so the audit log preserves the full classification trace.

### 2. The `MnemosyneLLMFallback` rate-limited escalator

Lives at `src/theogony/agents/mnemosyne_llm_fallback.py`. ~80 lines.

```python
class MnemosyneLLMFallback:
    """Rate-limited LLM classifier for Mnemosyne's uncertain band.

    Holds a sliding-window counter of recent calls + a per-call
    cost cap. When either limit is exceeded, classify() returns
    None (caller defaults to "not_self_referential" in that
    case).
    """

    def __init__(
        self,
        llm: LLMProvider,
        *,
        max_calls_per_hour: int,
        max_cost_eur_per_call: float,
    ) -> None: ...

    async def classify(
        self,
        *,
        query: str,
        answer: Answer,
    ) -> MetaClassification | None: ...
```

Prompt is short, structured, and packaged in `src/theogony/agents/prompts/mnemosyne_classifier.md` (~30 lines). Output is constrained to a single JSON line: `{"verdict": "self_referential" | "not_self_referential", "rationale": "<short>"}`. Caller validates with Pydantic.

The fallback's prompt and output schema are fully spec'd in the new `docs/MNEMOSYNE.md` so future contributors can audit what the system "considers self-referential".

### 3. The `MnemosyneAggregationPhase`

Per Knob 3. Lives at `src/theogony/agents/mnemosyne_phase.py`. ~150 lines including private helpers.

`_load_meta_observations_in_window` walks `settings.run_reports_dir/query/` for files newer than `now - window_days` and extracts those whose `meta_classification.verdict == "self_referential"`. The function is identical in shape to W3's `_load_query_reports_in_window` for stub aggregation — extract a generic walker into `src/theogony/reporting/loader.py` if the duplication bothers you, but Phase-1 honest scope is "two functions, one per consumer".

`_cluster_observations_by_region` reuses the W1 `HDBSCANStrategy`:

```python
async def _cluster_observations_by_region(
    observations: list[QueryRunReport],
    *,
    min_cluster_size: int,
) -> list[MnemosyneObservationCluster]:
    descriptors = [
        (r.run_id, r.region_descriptor)
        for r in observations
        if r.region_descriptor is not None
    ]
    if len(descriptors) < min_cluster_size:
        return []

    node_ids = [run_id for run_id, _ in descriptors]
    embeddings = [d.query_embedding for _, d in descriptors]
    strategy = HDBSCANStrategy(min_cluster_size=min_cluster_size)
    result = await asyncio.to_thread(strategy.cluster, node_ids, embeddings)

    clusters: list[MnemosyneObservationCluster] = []
    for cluster_idx, centroid in result.centroids.items():
        members = [
            run_id for run_id, ci in result.assignments.items() if ci == cluster_idx
        ]
        if len(members) < min_cluster_size:
            continue
        contributing = [r for r in observations if r.run_id in members]
        clusters.append(_build_cluster(contributing, centroid))
    return clusters
```

`_build_cluster` aggregates: contributing run_ids, dominant_node_type, dominant_cluster_id, mean keyword hit-rate, cited node ids that recur most often. The shape is the **input contract for Phase-2's BacklogProposal drafter** — keep all the signal the future drafter would need.

### 4. `MnemosyneObservationCluster` shape

```python
class MnemosyneObservationCluster(RunReportBase):
    """Per-pass cluster of self-referential observations."""

    report_type: Literal["mnemosyne"] = "mnemosyne"
    centroid_embedding: list[float]
    contributing_run_ids: list[str]
    contributing_query_count: int = Field(ge=0)
    aggregate_keyword_hits: int = Field(ge=0)
    dominant_node_type: NodeType | None = None
    dominant_cluster_id: str | None = None
    most_recurrent_cited_node_ids: list[str] = Field(default_factory=list)
    window_days: float = Field(ge=0.0)
    requires_hestia_review: bool = False  # reserved for Phase 2
    hestia_review_status: Literal[
        "not_required", "pending", "approved", "blocked"
    ] = "not_required"
```

`requires_hestia_review` and `hestia_review_status` are reserved fields — always defaulted in Phase 1; Phase 2's BacklogProposal drafter will flip them based on the cluster's content.

### 5. `QueryPipeline` integration

The classifier slots in next to the existing W3 stub_detector — both run in `_finalize_report` and produce attached fields on the `QueryRunReport`. Sequence:

```python
# In _finalize_report, AFTER stub_verdict computation:

stub_verdict = self._stub_detector.detect(...)  # existing W3
region_descriptor = compute_region_descriptor(...)  # existing W3

meta_classification = await self._mnemosyne.classify(
    query=query,
    answer=answer,
    cited_node_ids=answer.cited_node_ids,
    constellation=constellation,
)

# After report assembly, mark cited nodes if self-referential.
# The store call is fire-and-forget for the purpose of this query
# (the marking is an audit signal, not a retrieval-affecting mutation).
if meta_classification.verdict == MetaClassificationVerdict.SELF_REFERENTIAL:
    await self._store.mark_self_referential(answer.cited_node_ids, run_id)

return QueryRunReport(
    ...,
    stub_verdict=stub_verdict,
    region_descriptor=region_descriptor,
    meta_classification=meta_classification,  # NEW
)
```

`QueryPipeline.__init__` gains `mnemosyne: MetaQueryClassifier | None = None` (default constructed from settings). `api/dependencies.py`, `cli.py`, `mcp/server.py` all wire it via the same factory pattern as `StubDetector`.

### 6. `KnowledgeStore.mark_self_referential`

```python
async def mark_self_referential(
    self,
    node_ids: Sequence[str],
    run_id: str,
) -> None:
    """Append run_id to each node's properties['self_referential_in_runs'].

    Atomic per-node. Idempotent: appending the same run_id twice
    is a no-op (the list dedupes). Nonexistent node ids are silent
    no-ops (matches batch_update_scores).
    """
    ...
```

Both backends implement. In-memory: simple dict-of-list. Neo4j: `UNWIND` + `SET n.properties.self_referential_in_runs = coalesce(n.properties.self_referential_in_runs, []) + $run_id` with a uniqueness filter.

### 7. CLI + MCP touches

- `theogony reports list --type mnemosyne` — extends the existing literal.
- `theogony reports show <id>` — already type-agnostic, just the dispatch update.
- `theogony mnemosyne classify "<question>"` — diagnostic that runs only the heuristic classifier on a one-shot query (no constellation, no answer; just keyword scoring) and prints the verdict with the keyword hit breakdown. ~30 lines.
- `pantheon_reports_list` / `pantheon_reports_show` MCP tools extend their `report_type` enum to include `"mnemosyne"`.

---

## Implementation plan (file-by-file)

### `src/theogony/agents/mnemosyne_classifier.py` (new)

`MetaQueryClassifier` + `MetaClassificationVerdict` + `MetaClassification` Pydantic + the heuristic logic. ~150 lines.

### `src/theogony/agents/mnemosyne_llm_fallback.py` (new)

`MnemosyneLLMFallback` rate-limited escalator. ~80 lines.

### `src/theogony/agents/prompts/mnemosyne_classifier.md` (new)

Short structured system prompt for the LLM-fallback path. ~30 lines. Follows the same `importlib.resources`-loadable pattern as the AnswerSynthesizer prompt.

### `src/theogony/agents/mnemosyne_phase.py` (new)

`MnemosyneAggregationPhase` + private helpers. ~150 lines.

### `src/theogony/reporting/models.py`

Add `MetaClassificationVerdict`, `MetaClassification`, `MnemosyneObservationCluster`. Extend `QueryRunReport` with `meta_classification: MetaClassification | None = None`.

### `src/theogony/reporting/writer.py`

Add `MnemosyneObservationCluster` to `ReportType` union. Extend `most_recent` dispatch.

### `src/theogony/core/store.py`

Add `mark_self_referential` per Scope decision 6.

### `src/theogony/stores/memory.py`

Implement `mark_self_referential`. Update node property round-trip (already supports `properties` dict; just confirm the append-and-dedupe semantics are honoured).

### `src/theogony/stores/neo4j_store.py`

Implement `mark_self_referential`. Cypher pattern in Scope decision 6. Add a small index on `properties.self_referential_in_runs` IS NOT NULL (optional; helps the future Phase-2 drafter scan cited self-referential nodes efficiently).

### `src/theogony/config/settings.py`

Add `MnemosyneSettings` per Knob 6. Wire `Settings.mnemosyne = Field(default_factory=MnemosyneSettings)`.

### `src/theogony/retrieval/pipeline.py`

Per Scope decision 5. Inject `MetaQueryClassifier`. Compute `meta_classification` after `stub_verdict`. Call `mark_self_referential` when verdict matches.

### `src/theogony/api/dependencies.py`

Construct `MetaQueryClassifier(cfg=settings.mnemosyne, llm_fallback=...)` and pass to `QueryPipeline`.

### `src/theogony/api/app.py`

Lifespan: instantiate the classifier (and the fallback if `classifier_mode != "heuristic_only"` AND `provider != "stub"`), pass to pipeline.

### `src/theogony/cli.py`

Same swap in the `_run_ask` flow. Add the new `theogony mnemosyne classify "<question>"` diagnostic command (~30 lines). Extend `theogony reports list --type` literal.

### `src/theogony/mcp/server.py`

Same swap in the `pantheon_ask` lifespan. Extend the `pantheon_reports_list`/`pantheon_reports_show` `report_type` enum with `"mnemosyne"`.

### `src/theogony/memory/oneiros.py`

Register `"mnemosyne_aggregation": MnemosyneAggregationPhase` in `DEFAULT_PHASE_REGISTRY`. The `enabled_phases` default does **not** include it.

### `tests/test_mnemosyne_classifier.py` (new)

- `test_heuristic_returns_self_referential_for_high_keyword_hit_in_query`.
- `test_heuristic_returns_self_referential_for_high_keyword_hit_in_cited_node_label`.
- `test_heuristic_returns_self_referential_for_two_mid_keyword_hits`.
- `test_heuristic_returns_uncertain_for_one_mid_keyword_hit_long_query`.
- `test_heuristic_returns_not_self_referential_when_no_keywords`.
- `test_classify_records_keyword_hit_breakdown`.

### `tests/test_mnemosyne_llm_fallback.py` (new)

- `test_fallback_classify_returns_verdict_when_under_budget`.
- `test_fallback_classify_returns_none_when_rate_limit_exhausted`.
- `test_fallback_classify_returns_none_when_per_call_cost_exceeded`.
- `test_fallback_validates_llm_response_shape`.

### `tests/test_mnemosyne_phase.py` (new)

- `test_phase_skips_when_within_cadence`.
- `test_phase_runs_when_no_previous_mnemosyne_report`.
- `test_phase_skips_when_below_min_observations`.
- `test_phase_writes_one_cluster_per_emergent_pattern`.
- `test_phase_publishes_observability_to_ctx_extras`.

### `tests/test_mnemosyne_pipeline_integration.py` (new — high-value gate)

`test_pipeline_attaches_meta_classification_and_marks_self_referential_nodes`:
1. Build a fixture pipeline with `provider="stub"` (so the OfflineAnswerSynthesizer ships a cited answer).
2. Load 5 nodes into an in-memory store, all with labels containing self-referential keywords (`"Pantheon"`, `"OneirosWorker"`, etc.).
3. Submit a query whose text hits multiple keywords ("How does the OneirosWorker promote nodes between depth bands?").
4. Assert `result.report.meta_classification.verdict == "self_referential"`.
5. Assert each cited node's `properties["self_referential_in_runs"]` contains the run_id.

`test_pipeline_skips_marking_when_not_self_referential`:
1. Same fixture; query "What is the weather in Tibet?".
2. Assert verdict `not_self_referential`.
3. Assert no node was marked.

### `tests/test_mnemosyne_invisibility.py` (new)

The Knob-5 read-only contract test:
1. Build a pipeline.
2. Snapshot store state (node count, edge count, all node labels, all node confidences, all edge weights).
3. Run 5 queries through the pipeline (mix of self-referential and not).
4. Snapshot store state again.
5. Assert: node count unchanged; edge count unchanged; all labels unchanged; all confidences unchanged; all edge weights unchanged.
6. Assert: only difference is `properties.self_referential_in_runs` accumulated on cited nodes from the self-referential queries.

### Documentation touches

1. `docs/MNEMOSYNE.md` (new, ~140 lines): documents the meta-cognitive layer, the keyword sets, the verdict ladder, the LLM-fallback path + its prompt, the aggregation cadence, the Phase-1 vs Phase-2 split (Phase 1 stops at MnemosyneObservationCluster; Phase 2 ships the BacklogProposal drafter + Hestia hook), the gitignored draft directory, the read-only contract.

2. `docs/HIVE.md` Auditors table: add Mnemosyne row alongside Eris (PHX-0067) and Nemesis (PHX-0068). Note Asklepios (PHX-0073) as the upcoming triage role.

3. `docs/GLOSSARY.md`: Mnemosyne entry. Self-referential entry. Meta-classification entry.

4. `docs/PHILOSOPHY.md`: short section "the chronicle grows where it is asked questions about its growth" cross-linking PHX-0071.

5. `docs/PHOENIX_BACKLOG.md` PHX-0071 entry: append `"Phase 1 closed by W5 (PR #...): MetaQueryClassifier (heuristic + LLM-fallback) + per-cited-node self_referential_in_runs append + MnemosyneAggregationPhase (default-off, reuses W1 HDBSCAN). Phase 2 sub-tickets: BacklogProposal drafter, Hestia review hook, gitignored draft directory write path, theogony backlog proposals CLI."`

6. `docs/QUESTIONS_FROM_THE_FIELD.md` "How to add an entry" section: add a small note that once W5 ships, Mnemosyne classifies queries automatically and the manual workflow becomes the documented fallback for high-signal entries that the heuristic might miss.

---

## Cost-benefit considerations

**Token cost**: smaller than W3, similar shape. ~700 LoC new code + ~250 LoC tests + ~140 LoC docs. Estimate ≤ €0.80 of Composer execution.

**Runtime cost**:

- Per-query heuristic classifier: sub-millisecond. **Default-on**; net overhead per `pantheon_ask` call < 1 ms.
- LLM fallback: opt-in via `classifier_mode`, rate-limited at 30/hour, per-call cost capped at €0.001. Worst-case daily cost on a hammered deployment: ~€0.72/day. Default budget setting protects.
- Aggregator phase: **default-off**. When enabled, scans recent QueryRunReports + runs HDBSCAN once per cadence. Sub-second on the bundled seed; ~5 s for 10k QueryRunReports.
- Disk cost: `MetaClassification` adds ~200 bytes per QueryRunReport; `properties.self_referential_in_runs` adds ~30 bytes per cited node per self-referential query. Acceptable.

**Test cost**: ~16 new tests; estimated ~1 s wall-clock added.

**Failure modes worth watching**:

- **Keyword overfit**: the curated keyword sets reflect 2026-04-22 vocabulary. A query about "the substrate" (without using the word "Pantheon") should still classify as self-referential — but the heuristic currently misses it. The LLM fallback exists exactly for this case; the `classifier_mode` default is `heuristic_with_llm_fallback` so the fallback catches edge cases when budget allows. If the fallback budget is consistently exhausted, that is a signal that the keyword set needs updating — file a small docs PR adding observed-missing keywords; do NOT widen the heuristic beyond the curated list.
- **LLM-fallback prompt drift**: the LLM may return verdicts that diverge from the heuristic's stated semantics. The integration test (`test_pipeline_attaches_meta_classification_and_marks_self_referential_nodes`) uses the heuristic-only path so it is deterministic. The LLM-fallback test (`test_fallback_validates_llm_response_shape`) only validates schema, not semantic correctness — that is a Phase-2 sub-ticket if measured drift becomes a problem.
- **`run_id` plumbing**: the classifier's `mark_self_referential` call needs the `run_id` from the pipeline. `TickContext.run_id` was added in W4. `QueryPipeline._finalize_report` already mints one — confirm it is in scope when calling `mark_self_referential`.
- **Self-referential count grows unbounded**: the `properties["self_referential_in_runs"]` list grows monotonically per node. For nodes cited in 1000s of self-referential queries, the list becomes large. Phase-1 contract: list is purely an audit signal; no user-facing read consumer reads it. Phase 2 may add a cap-and-summarise behaviour. File a small follow-up if the list size becomes operationally annoying.
- **Stub provider with self-referential queries**: the OfflineAnswerSynthesizer (PHX-0070) is what generates `cited_node_ids` on stub deploys. The integration test depends on this — confirm that the synthesizer-routing factory already routes correctly when `provider="stub"`.

---

## Out of scope (do not do)

- **Do not** implement the BacklogProposal drafter. That is Phase 2.
- **Do not** implement the Hestia review hook for proposals. That is Phase 2 + needs PHX-0039 to ship first.
- **Do not** write to `phoenix-backlog/` or `prompts/` from any Mnemosyne path. Period.
- **Do not** mutate `cited_node_ids` choice or any retrieval scoring based on self-referential signal. The signal is purely audit; retrieval stays neutral. Re-weighting by self-referential history is a Phase-2 design conversation.
- **Do not** train a learned classifier. Phase 1 is heuristic + opt-in LLM fallback. Trained classifier is a separate Phase-3 sub-ticket once enough observation data exists.
- **Do not** add per-modality keyword sets. Heuristic is global Phase 1; per-modality keyword sets pair naturally with PHX-0002 Phase 2.
- **Do not** consume Asklepios (PHX-0073) findings. Mnemosyne handles **user queries**; Asklepios handles **auditor findings**. Different upstream sources, different agents.
- **Do not** change the OfflineAnswerSynthesizer (PHX-0070). The integration depends on it but does not modify it.

---

## Done when

- [ ] `MetaClassificationVerdict`, `MetaClassification`, `MnemosyneObservationCluster` exist in `reporting/models.py`.
- [ ] `QueryRunReport.meta_classification: Optional` exists.
- [ ] `MetaQueryClassifier` exists in `src/theogony/agents/mnemosyne_classifier.py`; pure logic; tested in isolation.
- [ ] `MnemosyneLLMFallback` exists in `src/theogony/agents/mnemosyne_llm_fallback.py`; rate-limited; tested in isolation.
- [ ] `MnemosyneAggregationPhase` exists in `src/theogony/agents/mnemosyne_phase.py`; default-off TickPhase; cadence-checked.
- [ ] `KnowledgeStore.mark_self_referential` exists; both backends implement.
- [ ] `Settings.mnemosyne` group exists.
- [ ] `OneirosWorker.DEFAULT_PHASE_REGISTRY` includes `"mnemosyne_aggregation"`. `OneirosSettings.enabled_phases` default does **not** include it.
- [ ] `QueryPipeline._finalize_report` invokes the classifier and marks self-referential nodes.
- [ ] `theogony mnemosyne classify "<question>"` CLI works.
- [ ] `theogony reports list --type mnemosyne` and `theogony reports show <id>` work.
- [ ] `pantheon_reports_list` / `pantheon_reports_show` MCP tools accept `"mnemosyne"`.
- [ ] All existing tests stay green without modification (full `pytest -q`).
- [ ] All new tests pass.
- [ ] `tests/test_mnemosyne_pipeline_integration.py::test_pipeline_attaches_meta_classification_and_marks_self_referential_nodes` is the high-value gate; must pass.
- [ ] `tests/test_mnemosyne_invisibility.py` enforces the read-only contract.
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy --strict` clean on `src/theogony/agents/mnemosyne_*.py`.
- [ ] `docs/MNEMOSYNE.md` exists; `docs/HIVE.md`, `docs/GLOSSARY.md`, `docs/PHILOSOPHY.md`, `docs/PHOENIX_BACKLOG.md`, `docs/QUESTIONS_FROM_THE_FIELD.md` updated.
- [ ] PR title: `feat(agents): W5 — Mnemosyne Phase 1 (PHX-0071)`. PR body lists the six resolved knobs, confirms zero default-path regression on existing query tests, and includes the `theogony mnemosyne classify` output for the embedding-modalities question from `docs/QUESTIONS_FROM_THE_FIELD.md` (it should classify `self_referential` with high confidence).

---

## After this PR

W5 closes Mnemosyne Phase 1. The chronicle now classifies every query for meta-reference and accumulates the audit data the Phase-2 drafter will consume. The user-visible payoff: `pantheon_status` can surface a `recent_self_referential_query_count` field; the operator can scan `theogony reports list --type mnemosyne` to see emergent meta-themes; PHX tickets can be filed by hand from those reports until Phase 2 automates the drafting step.

Phase 2 sub-ticket (file separately when this lands): the BacklogProposal drafter that consumes `MnemosyneObservationCluster` records and emits draft PHX YAML skeletons to a gitignored directory, with Hestia review on each. Pairs naturally with PHX-0039 Hestia implementation.

W6 candidates (operator picks):

- **PHX-0072 Proteus Phase 1** — twin-agent A/B testing for prompt evolution. Direct sister of Mnemosyne (audits prompts vs. audits queries).
- **PHX-0073 Asklepios Phase 1** — auditor-finding triage to fix tickets. Direct sister of Mnemosyne (audits Eris/Nemesis vs. audits user queries).
- **PHX-0002 Phase 1** — heterogeneous embedding spaces (the additive schema + per-modality vector_search filter). Sets the foundation for cross-modal Pantheon.
- **PHX-0061 Vector-Routed Federation** — the strategic Wave-2 sprint that turns Pantheon from one chronicle into the protocol for many.

Recommended next: **W6 = PHX-0072 Proteus** — once Mnemosyne ships, every prompt in the system (including Mnemosyne's own LLM-fallback prompt) is an A/B-testable best practice. Proteus's data quality grows quickly because Mnemosyne is producing observations of where the agent stack is being asked hard meta-questions.
