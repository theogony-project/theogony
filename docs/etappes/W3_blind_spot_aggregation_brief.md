# W3 — Aggregated Stub Detection (PHX-0058 Phase 1)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-22  
**Branch:** new branch off `main`, e.g. `feat/w3-blind-spot-aggregation`  
**Scope:** one PR  
**Predecessor:** Phase 0 closed by F1 + F2 + F3. W1 (Cluster v1, PR #52) + W2 (Edge-Pheromone, PR #55) merged. W3 is the **third sprint of Wave 1**.

Direct brief, no Daedalus. Six knobs are pre-locked below. Your job is execution discipline.

---

## Why this etappe exists

`docs/CURIOSITY.md` §"Stub Detection" specifies a six-signal `StubVerdict` that should be emitted on every `QueryRunReport`. **Today it does not exist.** No `StubVerdict` class, no per-query stub computation, no field on `QueryRunReport`. The Curiosity Loop's strategic priority signal — "which thin regions does the world keep asking about?" — has nothing to aggregate.

The PHX-0058 YAML calls this out indirectly ("Generation 1 should already emit `StubVerdict`"). W3 fills both halves of the gap:

- **Part A — Per-query stub detection.** `StubDetector` runs at `QueryPipeline._finalize_report` time, computes a `StubVerdict` from the constellation + answer + thresholds, attaches it to `QueryRunReport`. Six boolean signals (Node count low / Edge density low / Vitality low / Source diversity narrow / Confidence aggregate low / Named-entity coverage poor) plus one aggregate `stub_signal_strength` in [0, 1].
- **Part B — Aggregator over time.** A new default-off `BlindSpotAggregationPhase` in the OneirosWorker scans recent `QueryRunReport`s, clusters stub-firing region descriptors (query_embedding + dominant cluster_id + dominant node_type) using W1's `HDBSCANStrategy`, and emits one `BlindSpotReport` per emergent candidate cluster of recurring thin regions.

The aggregator does **not** dispatch outward research — that is PHX-0037 (Curiosity Loop). W3 ships the **priority signal** PHX-0037 will eventually consume.

---

## Pre-locked design knobs (locked 2026-04-22)

The PHX-0058 YAML left several decisions open. They are closed here:

### Knob 1 — `StubVerdict` shape: six independent signals + one aggregate

Per `docs/CURIOSITY.md`, six heuristics. Each fires independently (boolean), each has a recorded float value (the metric), plus a single aggregate strength in [0, 1].

```python
class StubVerdict(BaseModel):
    """Per-query stub detection (CURIOSITY.md §'Stub Detection')."""

    model_config = ConfigDict(extra="forbid")

    # Independent signals — each fires when its metric crosses the threshold.
    low_node_count: bool = False
    low_edge_density: bool = False
    low_vitality: bool = False
    narrow_source_diversity: bool = False
    low_confidence_aggregate: bool = False
    poor_named_entity_coverage: bool = False

    # Recorded metric values — useful for retrospective threshold tuning.
    node_count: int = Field(default=0, ge=0)
    edge_density: float = Field(default=0.0, ge=0.0)  # edges / max(1, nodes)
    mean_vitality: float = Field(default=0.0, ge=0.0, le=1.0)
    distinct_source_types: int = Field(default=0, ge=0)
    mean_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    named_entities_resolved_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

    # Aggregate: count of fired signals / 6, with a floor at 0 and cap at 1.
    # Fast Path can use this single number as a "how thin is this answer"
    # gauge without re-deriving the six booleans.
    stub_signal_strength: float = Field(default=0.0, ge=0.0, le=1.0)

    # If True, at least one signal fired and the verdict counts as a stub.
    is_stub: bool = False
```

**Aggregate computation:** `stub_signal_strength = sum(fired_signals) / 6`. `is_stub = stub_signal_strength > 0`. Phase 2 may weight signals; Phase 1 is unweighted to avoid pre-tuning.

**Thresholds** live in a new `Settings.curiosity.stub_thresholds` group (Knob 6).

### Knob 2 — Per-query computation: `StubDetector` is a pure helper

```python
class StubDetector:
    """Compute a StubVerdict from a Constellation + Answer + thresholds.

    Pure: no store access, no LLM call, no I/O. Inputs in, verdict out.
    Called by QueryPipeline._finalize_report after the answer + report
    are otherwise assembled.
    """

    def __init__(self, thresholds: StubThresholds) -> None:
        self._t = thresholds

    def detect(
        self,
        *,
        query: str,
        constellation: Constellation,
        answer: Answer,
        named_entities_in_query: list[str] | None = None,
    ) -> StubVerdict: ...
```

`named_entities_in_query` is optional — if None, the `poor_named_entity_coverage` signal records `1.0` (treated as "fully covered", neutral). Phase 1 does not run NER on the query; that is a Phase 2 sub-ticket. The field is included so the API + CLI can supply a pre-extracted entity list when one is available.

### Knob 3 — Region descriptor: small projection captured at finalize-time

For the aggregator to cluster thin queries by similarity, each `QueryRunReport` carries a `RegionDescriptor`:

```python
class RegionDescriptor(BaseModel):
    """Compact projection of the constellation a query landed in.

    Aggregation clusters these descriptors by query_embedding similarity.
    Dominant cluster_id and dominant node_type are tie-breakers when two
    embeddings are close: queries that converge on the same cluster_id
    are more likely to be the same blind spot than embedding alone.
    """

    model_config = ConfigDict(extra="forbid")

    query_embedding: list[float]
    seed_node_count: int = Field(default=0, ge=0)
    dominant_cluster_id: str | None = None
    dominant_node_type: NodeType | None = None
    mean_seed_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
```

Computed inline at `_finalize_report` time from the already-assembled constellation. Embedding is reused from step 1 of the pipeline (no re-embedding cost).

### Knob 4 — Aggregator placement: `TickPhase`, default-off, cadence-checked

`BlindSpotAggregationPhase` is a `TickPhase` that ships in `OneirosWorker.DEFAULT_PHASE_REGISTRY` but is **not** in the default `enabled_phases` list. Operators opt in.

The phase cadence-checks against the most recent `BlindSpotReport` on disk (mirrors `ReclusterPhase`'s pattern from W1):

```python
async def run(self, ctx: TickContext) -> None:
    cfg = ctx.cfg.curiosity  # NEW

    last = ctx.writer.most_recent("blindspot") if ctx.writer else None
    if last is not None:
        elapsed_s = (ctx.started_at - last.created_at).total_seconds()
        if elapsed_s < cfg.aggregation_interval_s:
            return

    # Scan QueryRunReports inside the window.
    reports = _load_query_reports_in_window(
        ctx.writer, window_days=cfg.window_days
    ) if ctx.writer else []
    stub_reports = [r for r in reports if r.stub_verdict and r.stub_verdict.is_stub]
    if len(stub_reports) < cfg.min_hits:
        ctx.extras["blind_spot_aggregation"] = {
            "skipped": "below min_hits",
            "stub_reports_in_window": len(stub_reports),
        }
        return

    candidates = await _aggregate_blind_spots(
        stub_reports=stub_reports,
        clustering_strategy=HDBSCANStrategy(min_cluster_size=cfg.min_hits),
        thresholds=cfg,
    )

    # Persist one BlindSpotReport per candidate.
    for cand in candidates:
        report = _build_blind_spot_report(cand)
        ctx.writer.write(report)

    ctx.extras["blind_spot_aggregation"] = {
        "stub_reports_scanned": len(stub_reports),
        "candidates_emitted": len(candidates),
    }
```

Reusing W1's `HDBSCANStrategy` is intentional — it already exists, is tested, and the input is the right shape (a list of embeddings → cluster assignments). The min_cluster_size parameter doubles as the `min_hits` threshold.

### Knob 5 — Hestia hook: reserved field, always False in Phase 1

The PHX-0058 YAML includes a Hestia review check ("person-as-target check on aggregated candidates"). Hestia (PHX-0039) does not exist yet. W3 reserves the schema slot:

```python
class BlindSpotCandidate(BaseModel):
    # ...
    requires_hestia_review: bool = False  # PHX-0039 will flip to True
    hestia_review_status: Literal["not_required", "pending", "approved", "blocked"] = (
        "not_required"
    )
```

In Phase 1, `requires_hestia_review` is always False, `hestia_review_status` is always `"not_required"`. PHX-0039 will introduce a `HestiaReview` pass that flips them based on entity type (person vs. concept vs. place) and topic sensitivity. The field is reserved so PHX-0039 lands without schema migration.

### Knob 6 — Thresholds: `Settings.curiosity` group

```python
class StubThresholds(BaseModel):
    """Per-query stub-detection thresholds (CURIOSITY.md §'Stub Detection')."""

    model_config = ConfigDict(extra="forbid")

    min_node_count: int = Field(default=3, ge=0)
    min_edge_density: float = Field(default=0.5, ge=0.0)
    min_mean_vitality: float = Field(default=0.3, ge=0.0, le=1.0)
    min_distinct_source_types: int = Field(default=2, ge=0)
    min_mean_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    min_named_entities_resolved_ratio: float = Field(default=0.5, ge=0.0, le=1.0)


class CuriositySettings(BaseModel):
    """W3 — stub detection + blind-spot aggregation."""

    model_config = ConfigDict(extra="forbid")

    stub_thresholds: StubThresholds = Field(default_factory=StubThresholds)
    window_days: float = Field(default=30.0, ge=0.0)
    min_hits: int = Field(default=3, ge=2)
    aggregation_interval_s: float = Field(default=86400.0, ge=0.0)  # daily
```

The aggregation interval is in seconds (not days) for parity with `tick_interval_s`; defaults to 86400 (one day).

---

## Goal

After this PR:

- `StubVerdict`, `RegionDescriptor`, `BlindSpotCandidate`, `BlindSpotReport` exist as Pydantic models in `reporting/models.py`.
- `QueryRunReport` carries `stub_verdict: StubVerdict | None` and `region_descriptor: RegionDescriptor | None`.
- `StubDetector` runs in `QueryPipeline._finalize_report` for every query (default-on; cost is sub-millisecond).
- `BlindSpotAggregationPhase` is registered in `OneirosWorker.DEFAULT_PHASE_REGISTRY` (default **off** in `enabled_phases`).
- `Settings.curiosity` group exists with the four knobs from Knob 6.
- `RunReportWriter` knows how to round-trip `BlindSpotReport`; `most_recent("blindspot")` works.
- `theogony reports list --type blindspot` and `theogony reports show <id>` work.
- `theogony curiosity blindspots [--force]` triggers a one-shot aggregation pass.
- `pantheon_reports_list` / `pantheon_reports_show` MCP tools accept `blindspot` as a report type.
- New `tests/test_stub_detector.py`, `tests/test_blind_spot_aggregation.py`, `tests/test_blind_spot_aggregation_phase.py`, `tests/test_blind_spot_integration.py` cover the contracts. The 10-query integration test from the PHX-0058 acceptance criteria lives in the integration file.
- New `docs/BLIND_SPOTS.md` documents the principle, the six signals, and the aggregator. `docs/CURIOSITY.md` §"Stub Detection" updated from "should already emit" to "ships in W3".

---

## Scope decisions (read first)

### 1. The `StubDetector`

Lives at `src/theogony/curiosity/stub_detector.py`. Pure logic; ~120 lines including docstrings.

```python
class StubDetector:
    name = "stub_detector"

    def __init__(self, thresholds: StubThresholds) -> None:
        self._t = thresholds

    def detect(
        self,
        *,
        query: str,
        constellation: Constellation,
        answer: Answer,
        named_entities_in_query: list[str] | None = None,
    ) -> StubVerdict:
        # 1. node_count
        node_count = len(constellation.nodes)
        low_node_count = node_count < self._t.min_node_count

        # 2. edge_density
        edges = len(constellation.edges)
        edge_density = edges / max(1, node_count)
        low_edge_density = edge_density < self._t.min_edge_density

        # 3. mean_vitality (use confidence as a Phase-1 stand-in;
        #    full vitality lives on KnowledgeNode, not ConstellationNode;
        #    Phase 2 may extend ConstellationNode if the proxy is poor)
        if constellation.nodes:
            mean_vitality = sum(n.confidence for n in constellation.nodes) / node_count
        else:
            mean_vitality = 0.0
        low_vitality = mean_vitality < self._t.min_mean_vitality

        # 4. source diversity
        source_types = {n.source_ref.source_type for n in constellation.nodes}
        distinct_source_types = len(source_types)
        narrow_source_diversity = (
            distinct_source_types < self._t.min_distinct_source_types
        )

        # 5. mean confidence (already in [0,1] on ConstellationNode)
        mean_confidence = mean_vitality  # same input in Phase 1
        low_confidence_aggregate = mean_confidence < self._t.min_mean_confidence

        # 6. named entity coverage — Phase 1 contract: if named_entities_in_query
        #    is None, treat as 1.0 (fully covered). Otherwise, count how many
        #    appear as cited node ids OR as labels in the constellation.
        if named_entities_in_query:
            cited_set = set(answer.cited_node_ids)
            label_set = {n.label for n in constellation.nodes}
            resolved = sum(
                1 for ent in named_entities_in_query
                if ent in cited_set or ent in label_set
            )
            ratio = resolved / max(1, len(named_entities_in_query))
        else:
            ratio = 1.0
        poor_named_entity_coverage = (
            ratio < self._t.min_named_entities_resolved_ratio
        )

        # Aggregate
        fired = sum([
            low_node_count,
            low_edge_density,
            low_vitality,
            narrow_source_diversity,
            low_confidence_aggregate,
            poor_named_entity_coverage,
        ])
        strength = fired / 6.0

        return StubVerdict(
            low_node_count=low_node_count,
            low_edge_density=low_edge_density,
            low_vitality=low_vitality,
            narrow_source_diversity=narrow_source_diversity,
            low_confidence_aggregate=low_confidence_aggregate,
            poor_named_entity_coverage=poor_named_entity_coverage,
            node_count=node_count,
            edge_density=edge_density,
            mean_vitality=mean_vitality,
            distinct_source_types=distinct_source_types,
            mean_confidence=mean_confidence,
            named_entities_resolved_ratio=ratio,
            stub_signal_strength=strength,
            is_stub=strength > 0.0,
        )
```

**Phase 1 honest compromise**: `mean_vitality` is computed from `ConstellationNode.confidence`, not from `KnowledgeNode.scores.vitality()`. The slim DTO does not carry vitality. Phase 2 may extend the slim DTO if the proxy proves misleading; for Phase 1 the calibration data this generates is the point — we want the dataset before tuning the metric.

### 2. The `RegionDescriptor` computation

Lives in the same module as `StubDetector` or in a tiny `region_descriptor.py`. Computed inline at `_finalize_report` time:

```python
def compute_region_descriptor(
    *,
    query_embedding: list[float],
    constellation: Constellation,
    retrieval_result: MultiHopResult,
) -> RegionDescriptor:
    seed_count = retrieval_result.seed_count
    nodes = constellation.nodes

    # Dominant cluster_id — most common across constellation nodes.
    # ConstellationNode is a slim DTO and does NOT carry cluster_id today.
    # Phase 1 contract: extend ConstellationNode with cluster_id (one
    # field, parallel to W1's cluster_label conversation, but for routing
    # not for label persistence). Required for region_descriptor to do
    # its job.
    cluster_counts: dict[str, int] = {}
    for n in nodes:
        cid = getattr(n, "cluster_id", None)
        if cid:
            cluster_counts[cid] = cluster_counts.get(cid, 0) + 1
    dominant_cluster_id = (
        max(cluster_counts, key=cluster_counts.get) if cluster_counts else None
    )

    # Dominant node_type — most common.
    type_counts: dict[NodeType, int] = {}
    for n in nodes:
        type_counts[n.node_type] = type_counts.get(n.node_type, 0) + 1
    dominant_node_type = (
        max(type_counts, key=type_counts.get) if type_counts else None
    )

    mean_conf = (
        sum(n.confidence for n in nodes) / max(1, len(nodes)) if nodes else 0.0
    )

    return RegionDescriptor(
        query_embedding=list(query_embedding),
        seed_node_count=seed_count,
        dominant_cluster_id=dominant_cluster_id,
        dominant_node_type=dominant_node_type,
        mean_seed_confidence=mean_conf,
    )
```

**`ConstellationNode.cluster_id` extension is required.** Mirror W1's `KnowledgeNode.cluster_label` pattern: add `cluster_id: str | None = None` to `ConstellationNode`, populate it from the `KnowledgeNode.cluster_id` in `from_knowledge_node`. Both backends already round-trip the field on `KnowledgeNode`; this just exposes it in the slim DTO.

### 3. The `BlindSpotAggregationPhase`

Per Knob 4. Lives at `src/theogony/curiosity/blind_spot_aggregation_phase.py` (~150 lines including helpers).

Important detail: **the W1 `TickContext` already carries `writer: RunReportWriter | None`** (extended for `ReclusterPhase`). W3 inherits that plumbing. No further changes to `TickContext`.

The aggregation algorithm:

```python
async def _aggregate_blind_spots(
    *,
    stub_reports: list[QueryRunReport],
    clustering_strategy: ClusteringStrategy,
    thresholds: CuriositySettings,
) -> list[BlindSpotCandidate]:
    """Cluster stub-firing region descriptors; emit one candidate per cluster."""
    # Collect (run_id, descriptor) pairs.
    descriptors = [
        (r.run_id, r.region_descriptor)
        for r in stub_reports
        if r.region_descriptor is not None
    ]
    if len(descriptors) < thresholds.min_hits:
        return []

    node_ids = [run_id for run_id, _ in descriptors]
    embeddings = [d.query_embedding for _, d in descriptors]

    # Reuse W1's clustering machinery — embeddings → cluster assignments.
    result = await asyncio.to_thread(
        clustering_strategy.cluster, node_ids, embeddings
    )

    candidates: list[BlindSpotCandidate] = []
    for cluster_idx, _centroid in result.centroids.items():
        members = [
            run_id for run_id, ci in result.assignments.items() if ci == cluster_idx
        ]
        if len(members) < thresholds.min_hits:
            continue

        # Aggregate signals across the contributing reports.
        contributing = [r for r in stub_reports if r.run_id in members]
        agg_strength = sum(r.stub_verdict.stub_signal_strength for r in contributing) / len(contributing)

        # Pick the most common dominant cluster_id and node_type across members.
        cluster_id_counts: dict[str, int] = {}
        node_type_counts: dict[NodeType, int] = {}
        for r in contributing:
            d = r.region_descriptor
            if d.dominant_cluster_id:
                cluster_id_counts[d.dominant_cluster_id] = (
                    cluster_id_counts.get(d.dominant_cluster_id, 0) + 1
                )
            if d.dominant_node_type:
                node_type_counts[d.dominant_node_type] = (
                    node_type_counts.get(d.dominant_node_type, 0) + 1
                )

        candidates.append(
            BlindSpotCandidate(
                contributing_run_ids=members,
                centroid_embedding=list(result.centroids[cluster_idx]),
                stub_signal_strength=agg_strength,
                dominant_cluster_id=(
                    max(cluster_id_counts, key=cluster_id_counts.get)
                    if cluster_id_counts else None
                ),
                dominant_node_type=(
                    max(node_type_counts, key=node_type_counts.get)
                    if node_type_counts else None
                ),
                requires_hestia_review=False,  # Knob 5 — Phase 1 hardcode
                hestia_review_status="not_required",
            )
        )
    return candidates
```

### 4. `BlindSpotReport` shape

```python
class BlindSpotCandidate(BaseModel):
    """One detected pattern: K thin queries that share an embedding region."""

    model_config = ConfigDict(extra="forbid")

    contributing_run_ids: list[str]  # the QueryRunReport run_ids that fired
    centroid_embedding: list[float]
    stub_signal_strength: float = Field(ge=0.0, le=1.0)
    dominant_cluster_id: str | None = None
    dominant_node_type: NodeType | None = None
    requires_hestia_review: bool = False  # Knob 5
    hestia_review_status: Literal[
        "not_required", "pending", "approved", "blocked"
    ] = "not_required"


class BlindSpotReport(RunReportBase):
    """One aggregator pass — emitted per BlindSpotCandidate."""

    report_type: Literal["blindspot"] = "blindspot"
    candidate: BlindSpotCandidate
    window_days: float = Field(ge=0.0)
    aggregator_algorithm: Literal["hdbscan", "kmeans"] = "hdbscan"
    stub_reports_scanned: int = Field(default=0, ge=0)
```

One report per candidate (vs. one report wrapping all candidates) — matches the existing one-report-per-pass pattern (`OneirosTickReport`, `ClusteringRunReport`). Each candidate is independently triagable.

### 5. `QueryPipeline` integration

`StubDetector` is constructed once in the pipeline (`__init__`), invoked at `_finalize_report` time. Add to `QueryPipeline.__init__`:

```python
def __init__(
    self,
    embedder: EmbeddingProvider,
    retriever: MultiHopRetriever,
    assembler: ConstellationAssembler,
    synthesizer: AnswerSynthesizer,
    relevance: RelevanceTracker,
    edge_pheromone: EdgePheromoneTracker,
    *,
    stub_detector: StubDetector | None = None,  # NEW
    strategy: RetrievalStrategy | None = None,
    settings: Settings | None = None,
    report_writer: RunReportWriter | None = None,
) -> None:
    # ...
    self._stub_detector = stub_detector or StubDetector(
        thresholds=(settings or Settings()).curiosity.stub_thresholds
    )
```

`_finalize_report` adds:

```python
stub_verdict = self._stub_detector.detect(
    query=query,
    constellation=constellation,
    answer=answer,
    named_entities_in_query=None,  # reserved; phase-2 sub-ticket adds NER
)
region_descriptor = compute_region_descriptor(
    query_embedding=query_embedding,
    constellation=constellation,
    retrieval_result=retrieval_result,
)
```

Add both to the returned `QueryRunReport`. **Keep `gaps_identified` unchanged** — it is a different (existing) signal and the W3 stub_verdict does not subsume it.

`QueryPipeline.ask` receives `query_embedding` from step 1. Plumb it into `_finalize_report` (currently it isn't passed because nothing downstream needed it).

### 6. CLI + API + MCP

**CLI:**

- `theogony reports list --type blindspot` — extend the existing `--type` literal.
- `theogony reports show <id>` — already type-agnostic; extend the report-loading dispatch in the implementation.
- `theogony curiosity blindspots [--force]` — new sub-command. Triggers a one-shot aggregation pass via `run_one_aggregation_pass(...)` (mirrors W1's `theogony recluster --force`). Prints the candidates as a small Rich table.

**API:** no DTO change in W3 (the report list/show is already there via `pantheon_reports_*`).

**MCP:** `pantheon_reports_list` / `pantheon_reports_show` extend their `report_type` enum to include `"blindspot"`.

### 7. `Settings.curiosity` placement

Top-level `Settings.curiosity = Field(default_factory=CuriositySettings)`. Mirror the existing `Settings.clustering` pattern from W1.

---

## Implementation plan (file-by-file)

### `src/theogony/curiosity/__init__.py` (new)

Re-exports: `StubDetector`, `StubVerdict`, `RegionDescriptor`, `compute_region_descriptor`, `BlindSpotAggregationPhase`, `run_one_aggregation_pass`. Tight surface.

### `src/theogony/curiosity/stub_detector.py` (new)

`StubDetector` per Scope decision 1. ~150 lines including docstring.

### `src/theogony/curiosity/region_descriptor.py` (new)

`compute_region_descriptor` per Scope decision 2. ~50 lines.

### `src/theogony/curiosity/blind_spot_aggregator.py` (new)

`_aggregate_blind_spots`, `_load_query_reports_in_window`, helpers. ~120 lines.

### `src/theogony/curiosity/blind_spot_aggregation_phase.py` (new)

`BlindSpotAggregationPhase` per Knob 4 + Scope decision 3. ~120 lines.

### `src/theogony/curiosity/runner.py` (new)

`run_one_aggregation_pass(store, settings, writer, *, force=False) -> list[BlindSpotReport]`. Used by `theogony curiosity blindspots --force` and by tests. ~50 lines.

### `src/theogony/reporting/models.py`

Add `StubVerdict`, `RegionDescriptor`, `BlindSpotCandidate`, `BlindSpotReport`. Extend `QueryRunReport` with `stub_verdict: StubVerdict | None = None` and `region_descriptor: RegionDescriptor | None = None`. The `None` defaults preserve old reports on disk.

### `src/theogony/reporting/writer.py`

Add `BlindSpotReport` to `ReportType` union. Extend `most_recent` to dispatch on `"blindspot"`.

### `src/theogony/core/model.py`

Add `cluster_id: str | None = None` to `ConstellationNode`; populate it in `from_knowledge_node`. (This is the only `model.py` change W3 needs.)

### `src/theogony/retrieval/pipeline.py`

Per Scope decision 5. Inject `StubDetector` (default = construct from settings). Compute `stub_verdict` + `region_descriptor` in `_finalize_report`. Plumb `query_embedding` from `ask` into `_finalize_report`.

### `src/theogony/config/settings.py`

Add `StubThresholds` and `CuriositySettings` per Knob 6. Wire `Settings.curiosity = Field(default_factory=CuriositySettings)`.

### `src/theogony/memory/oneiros.py`

Register `"blind_spot_aggregation": BlindSpotAggregationPhase` in `DEFAULT_PHASE_REGISTRY`. The `enabled_phases` default does **not** include it.

### `src/theogony/api/dependencies.py`

Construct `StubDetector(thresholds=settings.curiosity.stub_thresholds)` and pass to `QueryPipeline`.

### `src/theogony/api/app.py`

Lifespan: instantiate `StubDetector`, pass to pipeline. Same shape as the W2 `EdgePheromoneTracker` wiring.

### `src/theogony/cli.py`

Add `--type blindspot` to the existing `theogony reports list` literal. Add the new `theogony curiosity` sub-typer with one command `blindspots [--force]`.

### `src/theogony/mcp/server.py`

Extend the report-type enum on `pantheon_reports_list` / `pantheon_reports_show` to include `"blindspot"`. The implementation already dispatches on the directory name; one-line change to the input schema.

### `tests/test_stub_detector.py` (new)

- `test_detect_returns_no_stub_when_constellation_is_dense_and_diverse`.
- `test_detect_fires_low_node_count_below_threshold`.
- `test_detect_fires_low_edge_density_when_few_edges`.
- `test_detect_fires_narrow_source_diversity_when_one_source_type`.
- `test_detect_fires_low_mean_confidence_when_proxy_below_threshold`.
- `test_detect_named_entity_coverage_records_one_when_input_is_none`.
- `test_detect_named_entity_coverage_records_actual_ratio_when_input_supplied`.
- `test_aggregate_strength_equals_fired_signal_count_over_six`.
- `test_is_stub_true_iff_strength_above_zero`.

### `tests/test_blind_spot_aggregator.py` (new)

- `test_aggregator_returns_empty_when_below_min_hits`.
- `test_aggregator_emits_one_candidate_per_cluster`.
- `test_aggregator_skips_reports_without_region_descriptor`.
- `test_aggregator_aggregates_strength_across_contributing_reports`.
- `test_aggregator_picks_most_common_dominant_cluster_id`.

### `tests/test_blind_spot_aggregation_phase.py` (new)

- `test_phase_skips_when_within_cadence`.
- `test_phase_runs_when_no_previous_blindspot_report`.
- `test_phase_skips_when_below_min_hits`.
- `test_phase_writes_one_report_per_candidate`.
- `test_phase_publishes_observability_to_ctx_extras`.

### `tests/test_blind_spot_integration.py` (new — high-value gate)

- `test_ten_synthesized_query_reports_yield_one_blind_spot_candidate`. Setup: synthesise 10 `QueryRunReport`s with `StubVerdict.is_stub = True` and three different region embeddings (5 + 3 + 2 hits). Assert: HDBSCAN forms a cluster on the 5-hit region (above min_hits=3), one BlindSpotReport is emitted, `contributing_run_ids` are the 5 expected ones.

### `tests/test_pipeline_stub_verdict_integration.py` (new — small integration)

- `test_query_pipeline_attaches_stub_verdict_to_report`.
- `test_query_pipeline_attaches_region_descriptor_with_dominant_cluster_id`.

### Documentation touches

1. `docs/BLIND_SPOTS.md` (new, ~140 lines): documents the principle (the chronicle should know which thin regions it keeps being asked about), the six signals, the `StubDetector`, the aggregator, the `BlindSpotReport` shape, the cadence default, the CLI surface, and a "Phase 2 / open questions" section listing: per-cluster stub statistics (compose with W1), Hestia review (PHX-0039), Curiosity dispatch (PHX-0037), differential bump intensity for high-strength blind spots.

2. `docs/CURIOSITY.md` §"Stub Detection" — change the "should already emit" framing to "ships in W3 (PHX-0058 Phase 1)". Cross-reference `docs/BLIND_SPOTS.md`.

3. `docs/PHOENIX_BACKLOG.md` PHX-0058 catalogue entry: append `"Phase 1 closed by W3 (PR #...): per-query StubVerdict + RegionDescriptor on QueryRunReport, BlindSpotAggregationPhase (default-off) reusing W1's HDBSCANStrategy, BlindSpotReport persisted via RunReportWriter, theogony curiosity blindspots CLI, MCP report tool extension. Phase 2 sub-tickets: NER on query for entity coverage, Hestia review (PHX-0039 dependency), differential bump intensity, per-cluster stub statistics."`

4. `docs/ARCHITECTURE.md` — short paragraph in the relevant section announcing the stub-detection + blind-spot loop. Cross-reference `docs/BLIND_SPOTS.md`.

5. `docs/INDEX.md` — add `BLIND_SPOTS.md` to the discoverability list.

---

## Cost-benefit considerations

**Token cost**: similar to W2. Composer adds a new subpackage (`curiosity/`), three new model classes + extensions on two existing reports, integration in `QueryPipeline._finalize_report`, a new TickPhase, a new CLI subgroup, MCP enum extension, and ~25 new tests. Estimate ≤ €0.90 of Composer execution.

**Runtime cost**:

- Per-query `StubDetector.detect` is **default-on**. Pure computation over the already-assembled constellation; sub-millisecond. The `RegionDescriptor` reuses the already-computed query embedding. Total added latency per query: ~0.5 ms.
- `BlindSpotAggregationPhase` is **default-off**. When enabled, the cost is one `most_recent` read per tick (cadence check; cheap), and on the daily run, scanning ~30 days of `QueryRunReport`s on disk + one HDBSCAN clustering pass over their region embeddings. For 1000 queries / 30 days that is sub-second; for 100k queries / 30 days that is ~30 s — within the OneirosWorker's per-tick budget when scheduled appropriately (the daily cadence ensures it never runs more often).
- Disk cost: `QueryRunReport` payload grows by ~1 KB per report (StubVerdict + RegionDescriptor with the 384-dim embedding). Acceptable.

**Test cost**: ~25 new tests; estimated ~1.5 s wall-clock added (the integration test runs HDBSCAN on a 10-vector embedding set).

**Failure modes worth watching**:

- **`region_descriptor` requires `ConstellationNode.cluster_id`** — if you forget to extend the slim DTO, `dominant_cluster_id` is always `None` and the aggregator loses one of its tie-breakers. The unit test `test_query_pipeline_attaches_region_descriptor_with_dominant_cluster_id` is the canary.
- **Backward-compat on QueryRunReport**: existing reports on disk lack `stub_verdict` and `region_descriptor`. Pydantic defaults handle the read; the aggregator's `_load_query_reports_in_window` must guard against `None` descriptors and skip them. The unit test `test_aggregator_skips_reports_without_region_descriptor` covers this.
- **HDBSCAN parameter sensitivity** — `min_cluster_size = min_hits` (default 3) is small. On a sparse stub set, HDBSCAN may flag almost everything as noise. The integration test asserts the expected cluster forms; if it fails on real data, lower `min_hits` for the test fixture rather than tuning the production default.
- **Cadence drift** — `aggregation_interval_s` default 86400 (one day). If the OneirosWorker tick interval is the default 60 s, the cadence check runs every 60 s but the actual aggregation runs every 86400 s. That math is correct; the test `test_phase_skips_when_within_cadence` is the regression gate.
- **Privacy footgun** — `RegionDescriptor.query_embedding` is the 384-float embedding of a possibly-sensitive query. It is now persisted in every QueryRunReport. PHX-0039 (Hestia) will eventually scrub or hash these for sensitive queries; W3 simply persists them, but document the risk in `docs/BLIND_SPOTS.md` so the operator sees the trade-off.

---

## Out of scope (do not do)

- **Do not** implement Hestia review logic. The reserved field stays False in Phase 1. PHX-0039 owns the flip.
- **Do not** dispatch outward research on emitted blind spots. That is PHX-0037 (Curiosity Loop).
- **Do not** run NER on the query in Phase 1 to populate `named_entities_in_query`. The argument exists; callers may supply an already-extracted list, but Phase 1 does not add NER. That is a Phase 2 sub-ticket.
- **Do not** weight signals in the aggregate (`stub_signal_strength`). Phase 1 is unweighted to avoid pre-tuning. Phase 2 may weight after measurement.
- **Do not** add per-cluster stub statistics (one StubVerdict per cluster_id rather than aggregate). That is PHX-0060 Phase 2 territory and benefits from real W3 data first.
- **Do not** introduce a Mind-Map render of blind spots. That is PHX-0038.
- **Do not** add an MCP `pantheon_blindspots_list` tool with custom payload. The existing `pantheon_reports_list` extension covers the surface; a custom tool is a Phase 2 follow-up if measured friction calls for it.
- **Do not** introduce a separate `BlindSpotAggregator` worker outside the OneirosWorker. The TickPhase shape from F2 is the right home; spinning a second worker would duplicate lifespan plumbing.

---

## Done when

- [ ] `src/theogony/curiosity/` exists with the six new files from the implementation plan.
- [ ] `StubVerdict`, `RegionDescriptor`, `BlindSpotCandidate`, `BlindSpotReport` exist in `reporting/models.py`.
- [ ] `QueryRunReport` carries `stub_verdict` and `region_descriptor` (both `Optional`, default `None`).
- [ ] `ConstellationNode.cluster_id` exists; `from_knowledge_node` populates it.
- [ ] `Settings.curiosity` group exists with the four knobs.
- [ ] `OneirosWorker.DEFAULT_PHASE_REGISTRY` includes `"blind_spot_aggregation"`. `OneirosSettings.enabled_phases` default does **not** include it.
- [ ] `QueryPipeline` integrates `StubDetector` + `RegionDescriptor` computation.
- [ ] `theogony reports list --type blindspot` and `theogony reports show <id>` work.
- [ ] `theogony curiosity blindspots [--force]` works.
- [ ] `pantheon_reports_list` / `pantheon_reports_show` MCP tools accept `"blindspot"` as a `report_type`.
- [ ] All existing tests stay green without modification (full `pytest -q`).
- [ ] New tests cover the five new test files; all green.
- [ ] `tests/test_blind_spot_integration.py::test_ten_synthesized_query_reports_yield_one_blind_spot_candidate` is the high-value gate; it must pass.
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy src/theogony/curiosity/` clean (strict).
- [ ] `docs/BLIND_SPOTS.md` exists; `docs/CURIOSITY.md`, `docs/PHOENIX_BACKLOG.md`, `docs/ARCHITECTURE.md`, `docs/INDEX.md` updated.
- [ ] PR title: `feat(curiosity): W3 — Aggregated Stub Detection (PHX-0058 Phase 1)`. PR body lists the six resolved knobs, confirms zero default-path regression on existing query tests, and includes the result of the 10-query integration test.

---

## After this PR

W3 closes PHX-0058 Phase 1 and unlocks the last Wave-1 sprint:

- **W4 — PHX-0059 Morpheus-as-Associator**: the dreamer agent now has three signals to act on:
  1. `cluster_id` partitions (W1) — associate within a cluster, escalate cross-cluster.
  2. `pheromone_delta` per edge (W2) — distinguish well-trodden trails from fresh discovery candidates.
  3. `BlindSpotReport` heat-map (W3) — prioritise associations that would close known blind spots, not random ones.

After Wave 1 (W4 lands), the substrate has: clusters, pheromones, stubs, an active dreamer. That is the operational shape PHX-0061 (federation), PHX-0062 (negative knowledge), and PHX-0063+ build on top of.
