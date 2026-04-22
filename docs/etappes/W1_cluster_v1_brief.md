# W1 — Cluster v1 (PHX-0060 Phase 1)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-21  
**Branch:** new branch off `main`, e.g. `feat/w1-cluster-v1`  
**Scope:** one PR  
**Predecessor:** Phase 0 closed by F1 (PR #46) + F2 (PR #49) + F3 (PR #50). W1 is the **first sprint of Wave 1**.

Direct brief, no Daedalus. The four open knobs from `phoenix-backlog/PHX-0060.yaml` were closed in conversation 2026-04-21 and are baked into this brief verbatim — your job is execution discipline.

---

## Why this etappe exists

`ARCHITECTURE.md §"The Knowledge Network as Its Own Index"` has spec'd hierarchical clustering since Gen 1: nodes belong to semantic clusters, each cluster has a centroid vector, retrieval starts at centroids and narrows. The schema slot exists (`KnowledgeNode.cluster_id: str | None`); the store protocol exposes `get_cluster_centroid` and `assign_cluster`; both backends implement them.

**But nothing ever populates `cluster_id`.** The whole hierarchical-index machinery is wired structurally and never triggered. PHX-0060 fills the gap.

W1 ships the Phase-1 foundation:

- A `ClusteringStrategy` Protocol (HDBSCAN default, k-means large-corpus fallback).
- A new `ReclusterPhase` for `OneirosWorker` that runs on a configurable cadence (default monthly) and populates `cluster_id`/`cluster_label` across the whole substrate.
- A `ClusterIndex` that the IngestionPipeline consults at insert-time to give every new node a rough nearest-centroid `cluster_id`.
- A new `ClusterNarrowingRetrievalStrategy` that plugs into the F3 `RetrievalStrategy` Protocol and proves the routing-efficiency win.
- The `KnowledgeStore` Protocol gains `list_clusters()` and `get_cluster_members()`.
- The store schema gains a `cluster_label` field on `KnowledgeNode` and a `cross_cluster` flag on every edge.
- A `ClusteringRunReport` records what each re-cluster pass did.
- An integration test against the bundled `pantheon_self` seed asserts that meaningful clusters emerge.

The four knobs flagged "needs decision" in the PHX-0060 YAML are closed as follows (locked 2026-04-21):

1. **Hierarchy depth (Knob 4):** flat (one level) in Phase 1. Centroids-of-centroids is a Phase-2 sub-ticket.
2. **Cluster identity stability (Knob 5):** two-stage. `cluster_id: str` is the technical handle (re-mints when membership shifts beyond the Jaccard threshold); `cluster_label: str | None` is the persistent semantic name. Inheritance algorithm: max Jaccard overlap ≥ 0.7 → inherit `cluster_id` and `cluster_label`; else mint new `cluster_id`, set `cluster_label = None` (LLM naming is a follow-up sub-ticket).
3. **Specialised sub-agents per cluster (Knob 6):** deferred entirely to a Phase-2 Argonaut sub-ticket. Phase 1 reserves a `properties["agent_class"]: str | None` slot in `ClusterSummary` so the sub-ticket can land without schema migration.
4. **Cross-cluster edge classification (Knob 7):** edges carry `properties["cross_cluster"]: bool`. Computed at edge-insert time (lookup source/target `cluster_id`, set `True` iff they differ) AND re-evaluated by `ReclusterPhase` after each re-cluster pass (single edge sweep). No `bridge_score` in Phase 1 — that is a Phase-2 sub-ticket once Morpheus (PHX-0059) has landed and there is a behavioural gradient to score.

The three already-locked Phase-1 knobs from the PHX-0060 YAML stay locked:

- **Hard clustering** (`cluster_id` single-valued).
- **Hybrid trigger** (periodic re-pass via `ReclusterPhase`, plus nearest-centroid assignment at insert-time via `ClusterIndex`).
- **HDBSCAN default, k-means above the corpus-size threshold.**

---

## Goal

After this PR:

- `src/theogony/clustering/` (new subpackage) defines the `ClusteringStrategy` Protocol, the `HDBSCANStrategy`, the `KMeansStrategy`, the `ClusterIndex`, the cluster-identity algorithm, and the `ReclusterPhase`.
- `src/theogony/retrieval/strategies/cluster_narrowing.py` defines `ClusterNarrowingRetrievalStrategy`, registered under `name = "cluster_narrow"`.
- `KnowledgeNode` gains `cluster_label: str | None` (next to the existing `cluster_id`).
- `KnowledgeEdge.properties` gains a documented `cross_cluster: bool` convention (no schema change to the model — it is a `properties` key per the YAML knob 4 decision).
- `KnowledgeStore` Protocol gains `list_clusters() -> list[ClusterSummary]` and `get_cluster_members(cluster_id) -> AsyncIterator[str]`. Both backends implement them.
- `ClusterSummary` is a new Pydantic model in `core/model.py`.
- `Settings.clustering` group exists with the seven knobs documented in Scope decision 7.
- `ClusteringRunReport` is a new RunReport type wired through the `RunReportWriter`.
- `OneirosWorker.DEFAULT_PHASE_REGISTRY` registers `recluster` (off by default in `enabled_phases`; operators opt in by adding `"recluster"` to the list).
- `IngestionPipeline` calls `ClusterIndex.assign(embedding)` for each new node before upserting; the index is rebuilt from `store.list_clusters()` on pipeline construction and refreshed by `ReclusterPhase` at the end of each re-cluster pass.
- `ConstellationAssembler` is unchanged. The `Constellation` shape is unchanged. Cross-cluster edges are visible only via the `properties["cross_cluster"]` key on existing edges.
- New `tests/test_clustering_*.py` cover the strategy contracts, the identity algorithm, the recluster phase, the cluster-narrowing retrieval, and the seed integration test.
- Documentation: `docs/ARCHITECTURE.md` §"The Knowledge Network as Its Own Index" is updated from "Gen 2 concern" to "implemented in PHX-0060 Phase 1". A new short `docs/CLUSTERING.md` documents the brain-region framing, the four resolved knobs, and the Jaccard-stability algorithm.

---

## Scope decisions (read first)

### 1. The `ClusteringStrategy` Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ClusteringStrategy(Protocol):
    """One concrete clustering strategy.

    Strategies receive a list of embeddings (parallel to a list of
    node_ids) and return a `ClusteringResult`. They are pure: no
    store access, no LLM, no settings beyond construction-time
    configuration. The caller (`ReclusterPhase`) handles persistence
    and the identity-stability mapping.
    """

    name: str  # short stable identifier; matches Settings.clustering.algorithm literal

    def cluster(
        self,
        node_ids: list[str],
        embeddings: list[list[float]],
    ) -> ClusteringResult: ...
```

`name` is a class attribute (parallel to `TickPhase.name` and `RetrievalStrategy.name`).

`cluster` is sync, not async — the underlying sklearn calls are CPU-bound and blocking. The `ReclusterPhase` wraps each call in `asyncio.to_thread`.

### 2. The `ClusteringResult` dataclass

```python
@dataclass(frozen=True)
class ClusteringResult:
    """Output of one ClusteringStrategy.cluster call.

    `assignments` maps node_id -> local cluster index (an int local
    to this result; the identity-stability layer turns local
    indices into stable cluster_ids). Noise points (HDBSCAN's -1
    label) are represented as cluster index -1; the caller decides
    whether to leave them with cluster_id=None or assign them to
    the nearest centroid.

    `centroids` maps local cluster index -> centroid embedding
    (mean of member embeddings; sklearn's HDBSCAN does not produce
    centroids, so the strategy computes them).
    """

    assignments: dict[str, int]
    centroids: dict[int, list[float]]
    algorithm: str  # mirrors strategy.name
    runtime_ms: int
```

### 3. `HDBSCANStrategy`

```python
class HDBSCANStrategy:
    name = "hdbscan"

    def __init__(self, *, min_cluster_size: int = 5) -> None:
        self._min_cluster_size = min_cluster_size

    def cluster(
        self,
        node_ids: list[str],
        embeddings: list[list[float]],
    ) -> ClusteringResult:
        # Use sklearn.cluster.HDBSCAN (sklearn >= 1.3, already a transitive
        # dep via sentence-transformers). Cosine metric is not natively
        # supported by HDBSCAN; pre-normalise embeddings to unit length and
        # use Euclidean — that is mathematically equivalent on the unit
        # sphere and matches the cosine semantics every other layer assumes.
        ...
```

Implementation notes:
- Pre-normalise embeddings to unit length before passing to HDBSCAN (`numpy.linalg.norm` per row, divide; guard against zero-norm rows).
- `HDBSCAN(min_cluster_size=self._min_cluster_size, metric="euclidean")`.
- Compute centroids manually: for each non-noise label, mean the member embeddings, re-normalise to unit length, return as a plain list of floats.
- Noise points (label -1) are passed through to the result. The `ReclusterPhase` handles them per Scope decision 6 (assign to nearest centroid if any centroids exist, else leave `cluster_id = None`).

### 4. `KMeansStrategy`

```python
class KMeansStrategy:
    name = "kmeans"

    def __init__(self, *, n_clusters: int) -> None:
        self._n_clusters = n_clusters

    def cluster(
        self,
        node_ids: list[str],
        embeddings: list[list[float]],
    ) -> ClusteringResult:
        # sklearn.cluster.KMeans with n_init="auto", random_state=0
        # (deterministic for the regression test).
        ...
```

`n_clusters` is determined by the caller. The `ReclusterPhase` picks `n_clusters = max(min_cluster_size_floor, int(sqrt(len(node_ids))))` as a sensible default — Phase 1 does not need an elbow-method search; the operator sets `corpus_size_kmeans_threshold` deliberately because they have already accepted the trade-off.

KMeans always assigns every node (no noise concept). All centroids come back populated.

### 5. The `ClusterIndex` (insert-time nearest-centroid)

In-memory centroid index for the IngestionPipeline:

```python
class ClusterIndex:
    """Insert-time cluster assignment via nearest-centroid lookup.

    Held by the IngestionPipeline; refreshed by ReclusterPhase at
    the end of every re-cluster pass and on pipeline construction
    via ``rebuild_from_store``.

    Empty index (no centroids yet, cold-start corpus): ``assign``
    returns ``None``. The next ReclusterPhase pass will assign
    cluster_id correctly.
    """

    def __init__(self) -> None:
        self._centroids: dict[str, list[float]] = {}  # cluster_id -> centroid
        self._labels: dict[str, str | None] = {}  # cluster_id -> label

    async def rebuild_from_store(self, store: KnowledgeStore) -> None:
        self._centroids.clear()
        self._labels.clear()
        for summary in await store.list_clusters():
            self._centroids[summary.cluster_id] = summary.centroid
            self._labels[summary.cluster_id] = summary.cluster_label

    def replace(self, summaries: list[ClusterSummary]) -> None:
        """Atomic refresh used by ReclusterPhase after a successful pass."""
        self._centroids = {s.cluster_id: s.centroid for s in summaries}
        self._labels = {s.cluster_id: s.cluster_label for s in summaries}

    def assign(self, embedding: list[float]) -> str | None:
        if not self._centroids:
            return None
        # Cosine similarity (embeddings are unit-normalised by the
        # embedder per Plan §3.2). Pre-normalise the input
        # defensively; mismatched norms silently corrupt the rank.
        ...
```

Implementation notes:
- Cosine similarity = dot product on unit-normalised vectors. Use NumPy for the bulk dot product if the centroid count exceeds 100; below that, a Python comprehension is cheaper than the NumPy round-trip.
- `assign` returns the highest-scoring cluster_id; no threshold (the Phase-1 contract is "rough assignment", and the next ReclusterPhase pass overrides anyway).
- The index does NOT decide cluster_label or whether the node is noise — that is the ReclusterPhase's job.

### 6. The `ReclusterPhase`

A new `TickPhase` registered under `name = "recluster"`. Off by default (not in `OneirosSettings.enabled_phases`); operators opt in by adding `"recluster"` to the list. Lives at `src/theogony/clustering/recluster_phase.py`.

```python
class ReclusterPhase:
    name = "recluster"

    async def run(self, ctx: TickContext) -> None:
        cfg = ctx.cfg.clustering  # NEW: see Scope decision 7

        # 1. Cadence check. Skip if last successful re-cluster
        #    happened within recluster_interval_days. The check
        #    reads the most recent ClusteringRunReport via the
        #    report writer (see Scope decision 8 for plumbing).
        if not _should_recluster(ctx, cfg):
            return

        # 2. Collect every node's embedding from every layer.
        all_nodes = await _collect_all_embedded_nodes(ctx.store)
        if len(all_nodes) < cfg.min_corpus_size:
            log.info("recluster: corpus below min_corpus_size; skipping")
            return

        node_ids = [n.id for n in all_nodes]
        embeddings = [n.embedding for n in all_nodes]

        # 3. Pick algorithm: HDBSCAN by default; k-means above
        #    corpus_size_kmeans_threshold OR when explicitly forced.
        strategy = _select_strategy(cfg, len(all_nodes))

        # 4. Cluster (CPU-bound; off the event loop).
        result = await asyncio.to_thread(
            strategy.cluster, node_ids, embeddings
        )

        # 5. Identity-stability mapping (Scope decision 9).
        previous = await ctx.store.list_clusters()
        previous_members = await _materialise_previous_members(
            ctx.store, previous
        )
        identity = map_cluster_identity(
            new_assignments=result.assignments,
            new_centroids=result.centroids,
            previous_summaries=previous,
            previous_members=previous_members,
            jaccard_threshold=cfg.identity_jaccard_threshold,
        )

        # 6. Persist assignments + cluster summaries.
        await _persist_assignments(ctx.store, identity)
        await _persist_cluster_summaries(ctx.store, identity)

        # 7. Re-evaluate cross_cluster flag on every edge.
        #    Single sweep; cheap because edges already store source/target ids.
        await _refresh_cross_cluster_flags(ctx.store)

        # 8. Refresh the IngestionPipeline's ClusterIndex (Scope decision 10).
        ctx.extras["cluster_index_refresh"] = identity.summaries

        # 9. Stash the report payload in ctx.extras for the worker
        #    to surface as a ClusteringRunReport (Scope decision 11).
        ctx.extras["clustering_run"] = ClusteringRunReportPayload(
            algorithm=result.algorithm,
            nodes_processed=len(all_nodes),
            clusters_formed=len(identity.summaries),
            clusters_inherited=identity.inherited_count,
            clusters_minted=identity.minted_count,
            mean_cluster_size=_mean_cluster_size(identity),
            cluster_size_distribution=_size_distribution(identity),
            noise_node_count=identity.noise_count,
            runtime_ms=result.runtime_ms,
        )
```

The phase is intentionally chunky — it owns the whole re-cluster orchestration. The internal helpers (`_select_strategy`, `_collect_all_embedded_nodes`, `_persist_assignments`, …) live in the same module as private functions.

### 7. New `Settings.clustering` group

```python
class ClusteringSettings(BaseModel):
    """Tunables for the clustering stack (PHX-0060 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["auto", "hdbscan", "kmeans"] = "auto"
    recluster_interval_days: float = Field(default=30.0, ge=0.0)
    min_cluster_size: int = Field(default=5, ge=2)
    min_corpus_size: int = Field(default=20, ge=2)
    corpus_size_kmeans_threshold: int = Field(default=100_000, ge=1_000)
    identity_jaccard_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    new_node_assignment: Literal["nearest_centroid", "skip"] = "nearest_centroid"
```

Wire `clustering: ClusteringSettings = Field(default_factory=ClusteringSettings)` into the top-level `Settings` class.

`algorithm = "auto"` means: HDBSCAN below `corpus_size_kmeans_threshold`, k-means at or above it. `"hdbscan"` and `"kmeans"` force the choice (useful for benchmarking and the regression test).

### 8. Cadence check + ClusteringRunReport persistence

`ReclusterPhase` reads the most recent `ClusteringRunReport` from disk via the report writer. The `RunReportWriter` already exposes `list_recent(report_type=...)` — extend it if it does not (one-line addition; mirror the existing `OneirosTickReport` listing).

```python
def _should_recluster(ctx: TickContext, cfg: ClusteringSettings) -> bool:
    # ctx carries a reference to the writer via OneirosWorker; if not
    # already plumbed, add `writer: RunReportWriter` to TickContext.
    writer = ctx.extras.get("writer") or ctx.writer  # whichever exists post-F2
    last = writer.most_recent("clustering")  # returns ClusteringRunReport | None
    if last is None:
        return True
    elapsed_days = (ctx.started_at - last.created_at).total_seconds() / 86400.0
    return elapsed_days >= cfg.recluster_interval_days
```

If `TickContext` does not yet carry the writer, **add `writer: RunReportWriter` to `TickContext`** and thread it through `OneirosWorker._tick`. The other Phase-1 phases ignore it; that is fine.

### 9. Cluster-identity mapping algorithm

The Jaccard-stability algorithm spec'd in detail because every Mind-Map and every external reference depends on it being deterministic and well-tested:

```python
@dataclass
class ClusterIdentityResult:
    """Outcome of mapping a fresh ClusteringResult onto previous cluster_ids.

    `summaries` is the persisted list (one per output cluster).
    `assignments` is node_id -> stable cluster_id (or None for noise).
    `inherited_count` / `minted_count` / `noise_count` are stats for
    the ClusteringRunReport.
    """

    summaries: list[ClusterSummary]
    assignments: dict[str, str | None]
    inherited_count: int
    minted_count: int
    noise_count: int


def map_cluster_identity(
    *,
    new_assignments: dict[str, int],
    new_centroids: dict[int, list[float]],
    previous_summaries: list[ClusterSummary],
    previous_members: dict[str, set[str]],
    jaccard_threshold: float,
) -> ClusterIdentityResult:
    """Map fresh local cluster indices to stable cluster_ids.

    Algorithm:
      1. For each new local cluster index, build the member set.
      2. For each new cluster, compute Jaccard overlap against
         every previous cluster's member set.
      3. Greedy one-to-one matching: process new clusters in
         descending size order; for each, pick the previous
         cluster_id with the highest overlap (>= jaccard_threshold)
         that has not yet been claimed.
      4. New clusters with no qualifying previous match get a fresh
         `cluster_id = "cluster-" + uuid4().hex[:12]` and
         `cluster_label = None`.
      5. Inherited clusters keep both `cluster_id` and `cluster_label`.
      6. Noise points (local index -1) get cluster_id = None.

    Determinism: ties broken by previous_cluster_id ascending
    string compare. The seed integration test depends on this.
    """
    ...
```

Implementation notes:
- One-to-one matching is the simple greedy pass above. Hungarian is overkill for Phase 1.
- Iterate new clusters by size descending so the largest cluster gets first pick of inherited identity — this matches the human intuition that "the code cluster" stays "the code cluster" even if 5% of its members migrate.
- Tie-breaking by ascending `cluster_id` string makes the test deterministic against seeded UUIDs (use `uuid.uuid4()` in production but seed `random` in tests via a fixture).
- `previous_members` is materialised via `store.get_cluster_members(cluster_id)` — async iterator collected into a set per previous cluster. Cost: O(N) total. Fine for Phase 1.

### 10. `ClusterIndex` refresh handoff

`ReclusterPhase` does not own the `ClusterIndex` instance — the IngestionPipeline does. The phase publishes the new summaries via `ctx.extras["cluster_index_refresh"]`. The wiring is:

- `IngestionPipeline.__init__` accepts `cluster_index: ClusterIndex` (default `ClusterIndex()`).
- `IngestionPipeline.start()` (or the constructor; whichever is async) calls `await cluster_index.rebuild_from_store(store)`.
- A small subscriber pattern: `OneirosWorker._tick` checks `ctx.extras.get("cluster_index_refresh")` after the phase loop; if present and the worker holds a reference to the IngestionPipeline's index, it calls `cluster_index.replace(summaries)`.

Concretely: hold a `cluster_index: ClusterIndex | None` reference on the `OneirosWorker` (default `None`). The `api/app.py` lifespan wires both the IngestionPipeline and the OneirosWorker against the same `ClusterIndex` instance. When `OneirosWorker._tick` sees `ctx.extras["cluster_index_refresh"]`, it calls `self._cluster_index.replace(...)`.

If `cluster_index` is `None` (e.g. test setup that does not need ingestion), the phase still runs successfully; the publish is a no-op.

### 11. `ClusteringRunReport`

```python
class ClusteringRunReport(RunReportBase):
    report_type: Literal["clustering"] = "clustering"

    algorithm: Literal["hdbscan", "kmeans"]
    nodes_processed: int = Field(default=0, ge=0)
    clusters_formed: int = Field(default=0, ge=0)
    clusters_inherited: int = Field(default=0, ge=0)
    clusters_minted: int = Field(default=0, ge=0)
    noise_node_count: int = Field(default=0, ge=0)
    mean_cluster_size: float = Field(default=0.0, ge=0.0)
    cluster_size_distribution: list[int] = Field(default_factory=list)
    runtime_ms: int = Field(default=0, ge=0)
```

Wired through `reporting/__init__.py`, `reporting/writer.py` (`ReportType` union), and the `RunReportWriter.most_recent("clustering")` helper.

`OneirosWorker._tick` writes the `ClusteringRunReport` separately from the per-tick `OneirosTickReport`: if `ctx.extras.get("clustering_run")` is present at finalisation time, build a `ClusteringRunReport` from the payload and call `self._writer.write(report)` for it.

### 12. `KnowledgeStore` Protocol additions

Two new methods on the Protocol; both backends implement them.

```python
async def list_clusters(self) -> list[ClusterSummary]:
    """Return one `ClusterSummary` per known cluster (cluster_id is non-null)."""
    ...

def get_cluster_members(self, cluster_id: str) -> AsyncIterator[str]:
    """Async-iterate node_ids belonging to the given cluster."""
    ...
```

`get_cluster_members` is an async generator (sync `def` on the Protocol per the existing `export_layer` convention).

In-memory implementation: the `_clusters: dict[str, set[str]]` index already exists. Wrap.

Neo4j implementation:
- `list_clusters` runs `MATCH (n:KnowledgeNode) WHERE n.cluster_id IS NOT NULL RETURN n.cluster_id AS id, n.cluster_label AS label, count(n) AS member_count, avg(n.embedding) AS centroid, ... GROUP BY n.cluster_id`. The aggregated `avg(embedding)` is a list-of-floats; Neo4j's `reduce` is needed since Bolt does not aggregate lists element-wise natively. Helper Cypher pattern (verified-works):

  ```cypher
  MATCH (n:KnowledgeNode) WHERE n.cluster_id IS NOT NULL
  WITH n.cluster_id AS cid,
       n.cluster_label AS label,
       collect(n.embedding) AS embeddings,
       collect(n.node_type) AS node_types,
       collect(n.source_ref.source_type) AS source_types
  RETURN cid, label, size(embeddings) AS member_count,
         [i IN range(0, size(head(embeddings))-1) |
            reduce(s = 0.0, e IN embeddings | s + e[i]) / size(embeddings)] AS centroid,
         node_types, source_types
  ```

  Compute `dominant_node_type` and `dominant_source_type` in Python from `node_types` / `source_types` (most-common). Don't push that into Cypher — it bloats the query and the corpus is small enough.

- `get_cluster_members` runs `MATCH (n:KnowledgeNode {cluster_id: $cluster_id}) RETURN n.id AS id` and yields each id.

### 13. `ClusterSummary` model

```python
class ClusterSummary(BaseModel):
    """Persisted summary of one knowledge cluster."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    cluster_label: str | None = None
    member_count: int = Field(ge=0)
    centroid: list[float]
    dominant_node_type: NodeType | None = None
    dominant_source_type: str | None = None

    # Reserved for the Argonaut sub-ticket (PHX-0060 Phase-2 follow-up).
    properties: dict[str, Any] = Field(default_factory=dict)
```

The `properties["agent_class"]` slot is the reserved hook (knob 6 decision). Phase 1 leaves it empty.

Lives in `core/model.py` next to the existing knowledge-graph models.

### 14. `KnowledgeNode` schema change: `cluster_label`

Add `cluster_label: str | None = Field(default=None, description="Persistent semantic name; survives re-clustering when membership is stable. See PHX-0060 knob 5.")` next to the existing `cluster_id`.

The store backends serialise/deserialise it identically to `cluster_id`. The Neo4j schema gains an index on `cluster_label` (cheap; matches the existing `cluster_id` index pattern).

### 15. Cross-cluster edge classification

Edges carry `properties["cross_cluster"]: bool`. **No change to `KnowledgeEdge` model**; it is a properties key per the YAML knob 7 decision.

Two write paths:

1. **At edge insert** (in the IngestionPipeline's relation-extraction path, before `store.batch_upsert_edges`): for each edge, look up `source.cluster_id` and `target.cluster_id` from the in-memory ClusterIndex's reverse map (or directly from the nodes being upserted in the same batch). Set `edge.properties["cross_cluster"] = (src_cluster != tgt_cluster) if both are non-None else False`.

2. **After re-cluster** (inside `ReclusterPhase`): single sweep over every edge. Helper:

   ```python
   async def _refresh_cross_cluster_flags(store: KnowledgeStore) -> None:
       # One Cypher query on Neo4j; in-memory walks _edges.
       # Updates properties["cross_cluster"] in-place.
       ...
   ```

   On Neo4j: a single `MATCH (s)-[r]->(t) SET r.properties.cross_cluster = (s.cluster_id <> t.cluster_id)` runs in milliseconds for tens of thousands of edges.

   In-memory: walk the existing `_edges` dict, look up source/target cluster_id from the node store, update.

The ConstellationAssembler does not change. Consumers that want bridge edges filter `[e for e in result.edges if e.properties.get("cross_cluster")]`.

### 16. The `ClusterNarrowingRetrievalStrategy`

New `RetrievalStrategy` registered under `name = "cluster_narrow"`. Lives in `src/theogony/retrieval/strategies/cluster_narrowing.py`.

```python
class ClusterNarrowingRetrievalStrategy:
    name = "cluster_narrow"

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        top_n_clusters: int = 3,
        inner_strategy: RetrievalStrategy | None = None,
    ) -> None:
        self._store = store
        self._top_n_clusters = top_n_clusters
        self._inner = inner_strategy or FixedDepthStrategy(store)

    async def retrieve(
        self,
        embedding: list[float],
        *,
        budget: RetrievalBudget,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        # 1. List all clusters; rank by cosine similarity to query.
        summaries = await self._store.list_clusters()
        if not summaries:
            return await self._inner.retrieve(
                embedding, budget=budget, layer=layer
            )

        ranked = _rank_clusters_by_similarity(embedding, summaries)
        top = ranked[: self._top_n_clusters]

        # 2. Collect candidate node_ids from the top-N clusters.
        candidate_ids: set[str] = set()
        for summary in top:
            async for node_id in self._store.get_cluster_members(summary.cluster_id):
                candidate_ids.add(node_id)

        # 3. Cluster-narrowing fallback: if the top-N clusters cover too
        #    few nodes (< budget.max_nodes), fall back to flat retrieval.
        #    Avoids over-narrowing on small / partially-clustered corpora.
        coverage_floor = max(budget.max_nodes, 20)
        if len(candidate_ids) < coverage_floor:
            return await self._inner.retrieve(
                embedding, budget=budget, layer=layer
            )

        # 4. Run the inner strategy with a candidate-restricted budget.
        #    For Phase 1 we use a simple post-filter: run inner.retrieve
        #    on the full graph, then drop nodes whose id is not in
        #    candidate_ids. Phase 2 may push the candidate set into
        #    the strategy as a hard scope.
        inner_result = await self._inner.retrieve(
            embedding, budget=budget, layer=layer
        )
        filtered = [
            scored
            for scored in inner_result.scored_nodes
            if scored.node.id in candidate_ids
        ]
        return MultiHopResult(
            scored_nodes=filtered,
            seed_count=inner_result.seed_count,
            nodes_per_hop=inner_result.nodes_per_hop,
            final_node_count=len(filtered),
            duplicates_removed=inner_result.duplicates_removed,
            duration_ms=inner_result.duration_ms,
        )
```

Implementation notes:
- `_rank_clusters_by_similarity` is a plain cosine-against-centroid sort. Embeddings are unit-normalised by the embedder; centroids are unit-normalised by the strategies.
- The Phase-1 implementation deliberately uses the **post-filter** rather than a hard candidate restriction in the inner strategy. Reason: the F3 strategies do not yet accept a candidate scope. Phase 2 may extend `RetrievalBudget` with a `candidate_node_ids: set[str] | None` field and push the restriction into the strategy; that is a measurable optimisation, not a correctness change.
- Register the strategy in `Settings.retrieval.strategy` literal: extend it to `Literal["fixed_depth", "edge_product", "cluster_narrow"]`.
- Wire into `_build_strategy` in `api/dependencies.py`. The `cluster_narrow` branch constructs an inner strategy from `Settings.retrieval.cluster_narrow_inner_strategy` (default `"fixed_depth"`).
- Add `cluster_narrow_inner_strategy: Literal["fixed_depth", "edge_product"] = "fixed_depth"` and `cluster_narrow_top_n_clusters: int = Field(default=3, ge=1, le=20)` to `RetrievalSettings`.

### 17. CLI + API exposure

- `theogony ask --strategy cluster_narrow "<question>"` works.
- `POST /query` accepts `strategy="cluster_narrow"`.
- `theogony recluster` (new CLI command): triggers a one-shot run of `ReclusterPhase` against the configured store, prints the resulting `ClusteringRunReport` summary, exits. Useful for the seed integration test and for operators bringing up a fresh deployment that does not yet have any clusters.

  ```python
  @app.command()
  def recluster(
      force: bool = typer.Option(False, "--force", help="Skip cadence check"),
  ) -> None:
      """Run one ClusteringWorker pass against the configured store."""
      ...
  ```

  Implementation: build a small async helper in `clustering/__init__.py` (`run_one_recluster_pass(store, settings, writer, *, force=False)`) that the CLI calls; the helper is also useful for tests.

---

## Implementation plan (file-by-file)

### `src/theogony/clustering/__init__.py` (new)

Re-exports: `ClusteringStrategy`, `ClusteringResult`, `HDBSCANStrategy`, `KMeansStrategy`, `ClusterIndex`, `ReclusterPhase`, `map_cluster_identity`, `ClusterIdentityResult`, `run_one_recluster_pass`. Keep the public surface tight.

### `src/theogony/clustering/protocol.py` (new)

The `ClusteringStrategy` Protocol + `ClusteringResult` dataclass + module docstring referencing PHX-0060.

### `src/theogony/clustering/hdbscan_strategy.py` (new)

`HDBSCANStrategy`. ~80 lines.

### `src/theogony/clustering/kmeans_strategy.py` (new)

`KMeansStrategy`. ~50 lines.

### `src/theogony/clustering/cluster_index.py` (new)

`ClusterIndex`. ~80 lines including the cosine-similarity helper.

### `src/theogony/clustering/identity.py` (new)

`map_cluster_identity` + `ClusterIdentityResult`. ~120 lines including docstrings and the deterministic-tie-break note.

### `src/theogony/clustering/recluster_phase.py` (new)

`ReclusterPhase` + private helpers (`_should_recluster`, `_collect_all_embedded_nodes`, `_select_strategy`, `_persist_assignments`, `_persist_cluster_summaries`, `_refresh_cross_cluster_flags`, `_mean_cluster_size`, `_size_distribution`). ~250 lines including docstrings.

### `src/theogony/clustering/runner.py` (new)

`run_one_recluster_pass(store, settings, writer, *, force=False) -> ClusteringRunReport | None`. ~50 lines. Used by the CLI `theogony recluster` command and by tests.

### `src/theogony/retrieval/strategies/cluster_narrowing.py` (new)

`ClusterNarrowingRetrievalStrategy` + `_rank_clusters_by_similarity` helper. ~120 lines.

### `src/theogony/retrieval/strategies/__init__.py`

Add `"ClusterNarrowingRetrievalStrategy"` to `__all__` and the lazy `__getattr__`.

### `src/theogony/core/model.py`

Add `cluster_label: str | None = ...` to `KnowledgeNode` (next to `cluster_id`). Add the new `ClusterSummary` model. Existing fields untouched.

### `src/theogony/core/store.py`

Add `list_clusters` and `get_cluster_members` to the Protocol. Update the module docstring's "Cluster management" section to mention `ClusterSummary`.

### `src/theogony/stores/memory.py`

Implement `list_clusters` (compute centroids/dominants from `_clusters` index + node embeddings). Implement `get_cluster_members` (async iterate `_clusters[cluster_id]`). Update `assign_cluster` to also accept an optional `cluster_label` (default unchanged). Update batch upsert to read/write `cluster_label`.

### `src/theogony/stores/neo4j_store.py`

Implement `list_clusters` (single Cypher per the spec in Scope decision 12; Python-side dominants). Implement `get_cluster_members`. Add `cluster_label` to the property mapping (round-trip in `_node_from_props` and `_props_from_node`). Add an index on `cluster_label` in `_schema.py`.

### `src/theogony/stores/_schema.py`

Add a Neo4j `BTREE INDEX` on `cluster_label`. The existing `cluster_id` index stays.

### `src/theogony/config/settings.py`

Add `ClusteringSettings` per Scope decision 7. Wire into `Settings`. Extend `RetrievalSettings.strategy` literal to include `"cluster_narrow"`. Add `cluster_narrow_inner_strategy` and `cluster_narrow_top_n_clusters` to `RetrievalSettings`.

### `src/theogony/memory/tick_phase.py`

Extend `TickContext` with `writer: RunReportWriter | None = None` (forward ref via `TYPE_CHECKING`). The other phases ignore it.

### `src/theogony/memory/oneiros.py`

Register `"recluster": ReclusterPhase` in `DEFAULT_PHASE_REGISTRY`. Update `_tick` to:
- pass `writer=self._writer` into the `TickContext`
- after the phase loop, if `ctx.extras.get("clustering_run")` is present, build and write a `ClusteringRunReport`
- if `ctx.extras.get("cluster_index_refresh")` is present and `self._cluster_index is not None`, call `self._cluster_index.replace(...)`

Extend `OneirosWorker.__init__` with `cluster_index: ClusterIndex | None = None`.

### `src/theogony/api/app.py`

In the lifespan, construct a single `ClusterIndex`, call `await cluster_index.rebuild_from_store(store)`, pass it into both `IngestionPipeline(...)` and `OneirosWorker(...)`.

### `src/theogony/ingestion/pipeline.py` (or wherever `batch_upsert_nodes` is currently called from)

Accept `cluster_index: ClusterIndex` (default `ClusterIndex()`). For each new node with an embedding, call `node.cluster_id = cluster_index.assign(node.embedding)` before upserting. Skip nodes without embeddings (their cluster_id stays None).

Also for the relation-extraction path: after each batch of edges is built, set `edge.properties["cross_cluster"]` from the source/target cluster_ids (looked up from the same node batch or from the index).

### `src/theogony/api/dependencies.py`

Extend `_build_strategy` with the `"cluster_narrow"` branch; reads `settings.retrieval.cluster_narrow_inner_strategy` to construct the inner strategy.

### `src/theogony/api/dto.py`

Update `QueryRequest.strategy` literal to include `"cluster_narrow"`.

### `src/theogony/cli.py`

Add `--strategy cluster_narrow` to `theogony ask`. Add the new `theogony recluster` command per Scope decision 17.

### `src/theogony/reporting/models.py`

Add `ClusteringRunReport` per Scope decision 11.

### `src/theogony/reporting/__init__.py`

Re-export `ClusteringRunReport`.

### `src/theogony/reporting/writer.py`

Extend `ReportType` union. Extend `RunReportWriter` with `most_recent(report_type: str) -> RunReportBase | None` if it does not already have a parallel helper. The implementation is a one-liner over the existing on-disk listing.

### `tests/test_clustering_strategies.py` (new)

- `test_clustering_strategy_protocol_runtime_checkable` (HDBSCAN + KMeans both pass `isinstance(s, ClusteringStrategy)`).
- `test_hdbscan_strategy_assigns_obvious_clusters` (synthetic embeddings: three Gaussian blobs in unit-sphere space → exactly three non-noise clusters).
- `test_hdbscan_strategy_marks_outliers_as_noise` (single far-away embedding → label == -1).
- `test_kmeans_strategy_respects_n_clusters` (K=4 → exactly 4 cluster indices).
- `test_clustering_result_centroids_are_unit_normalised` (assert `|centroid| ≈ 1.0` for all centroids).

### `tests/test_clustering_identity.py` (new)

- `test_map_identity_inherits_when_jaccard_above_threshold` (90 % overlap → cluster_id preserved).
- `test_map_identity_mints_when_jaccard_below_threshold` (40 % overlap → fresh cluster_id).
- `test_map_identity_one_to_one_matching` (two new clusters that both overlap one previous → only the larger inherits).
- `test_map_identity_handles_noise_points` (local index -1 → assignments value None).
- `test_map_identity_preserves_label_on_inherit` (previous cluster had cluster_label="code"; inherited cluster carries it).
- `test_map_identity_deterministic_under_ties` (seeded test asserting tie-break by cluster_id ascending).

### `tests/test_cluster_index.py` (new)

- `test_cluster_index_empty_assigns_none`.
- `test_cluster_index_assign_picks_nearest_centroid` (synthetic centroids; assert the closest one wins).
- `test_cluster_index_rebuild_from_store_loads_summaries` (in-memory store with two pre-assigned clusters).
- `test_cluster_index_replace_atomically_swaps_state`.

### `tests/test_recluster_phase.py` (new)

- `test_recluster_phase_skips_when_within_cadence` (mock writer.most_recent returning a recent report).
- `test_recluster_phase_runs_when_no_previous_report`.
- `test_recluster_phase_skips_when_corpus_below_min_corpus_size`.
- `test_recluster_phase_persists_assignments_and_summaries`.
- `test_recluster_phase_refreshes_cross_cluster_edge_flags`.
- `test_recluster_phase_publishes_cluster_index_refresh_to_extras`.
- `test_recluster_phase_writes_clustering_run_report`.

### `tests/test_cluster_narrowing.py` (new)

- `test_cluster_narrowing_falls_back_when_no_clusters_exist`.
- `test_cluster_narrowing_falls_back_when_top_n_coverage_too_low`.
- `test_cluster_narrowing_filters_to_top_n_clusters` (in-memory store with three clusters; query embedding closest to cluster A → result excludes nodes from clusters B/C).
- `test_cluster_narrowing_preserves_multi_hop_result_shape` (`nodes_per_hop` etc. round-trip from the inner strategy).

### `tests/test_pantheon_self_clustering.py` (new — integration)

The high-value test. Loads the bundled `pantheon_self` seed into an in-memory store, runs `run_one_recluster_pass(...)` once, asserts:
- At least 3 clusters emerge.
- The largest cluster's `dominant_node_type` is `concept`.
- Cluster sizes follow a sensible distribution (no single cluster contains > 80 % of nodes; if it does, HDBSCAN params are wrong).
- A known-good query (`"What is Pantheon?"`) returns the same key citations under `cluster_narrow` as under `fixed_depth` — i.e. **no precision regression**.

This is the YAML's "integration test against the bundled `pantheon_self` seed" acceptance criterion, made concrete.

### Documentation touches

1. `docs/ARCHITECTURE.md` — update §"The Knowledge Network as Its Own Index" section: change "Gen 2 concern" framing to "implemented in PHX-0060 Phase 1 (W1)". Add a short paragraph explaining the cluster_id / cluster_label split, the Jaccard-stability algorithm, the cross_cluster edge convention, and the cluster-narrowing retrieval strategy. Cross-reference `docs/CLUSTERING.md`.

2. `docs/CLUSTERING.md` (new, ~150 lines): documents:
   - The brain-region framing (Sprachzentrum, Sehzentrum, Code-/Places-/Fiction-cluster).
   - The four resolved knobs from PHX-0060 (with explicit references to this brief and to the YAML).
   - The cluster_label-vs-cluster_id stability discussion + the Jaccard threshold default.
   - The hybrid trigger (insert-time nearest-centroid + periodic re-cluster).
   - Algorithm-selection rule (HDBSCAN below threshold, k-means above).
   - The cross_cluster edge property and how to query bridge edges.
   - A short "Phase 2 / open questions" section listing: hierarchical centroids, cluster naming via LLM, Argonaut sub-agents per cluster, soft (multi-membership) clustering, bridge_score on cross-cluster edges.

3. `docs/PHOENIX_BACKLOG.md` PHX-0060 catalogue entry: append `"Phase 1 closed by W1 (PR #...): ClusteringStrategy Protocol + HDBSCAN/KMeans + ReclusterPhase + ClusterIndex + ClusterNarrowingRetrievalStrategy + cluster_label/cross_cluster schema + ClusteringRunReport. Phase 2 sub-tickets: hierarchical centroids, LLM cluster naming, Argonaut sub-agents, soft clustering, bridge_score."`

4. `docs/RETRIEVAL_STRATEGIES.md` — add a short section on `cluster_narrow`, its fallback behaviour, and how it composes with an inner strategy.

5. `docs/HIVE.md` §"Argonauts" — add a one-liner: "Argonauts as cluster-specialised sub-agents are reserved by PHX-0060 (`ClusterSummary.properties['agent_class']`); the lifecycle ships in a Phase-2 sub-ticket."

---

## Cost-benefit considerations

**Token cost**: medium-large. Composer needs to introduce a substantial new subpackage (clustering/), add a new RetrievalStrategy, change the schema (add `cluster_label`), extend the store Protocol with two new methods on both backends, add a TickPhase with non-trivial orchestration, add a CLI command, and write ~30 new tests across five test files. Estimate ≤ €1.20 of Composer execution. Bigger than F3.

**Runtime cost**:

- Default-off: `ReclusterPhase` is **not** in the default `enabled_phases` list. Operators opt in. Existing deployments see zero overhead until they enable it.
- When enabled, the per-tick cost is one cadence check (one `most_recent` call against the report dir; cheap). The actual re-cluster fires only every `recluster_interval_days` (default 30). On the bundled `pantheon_self` seed (~280 nodes), the full pass takes < 1 s.
- Insert-time `ClusterIndex.assign` is a cosine similarity against ~10–100 centroids per new node. Sub-millisecond. Acceptable.
- `ClusterNarrowingRetrievalStrategy` is opt-in via `Settings.retrieval.strategy = "cluster_narrow"` or per-request. Default behaviour (`fixed_depth`) is unchanged.

**Test cost**: ~30 new tests; estimated total wall-clock added is ~2 s (the integration test does one HDBSCAN pass on ~280 unit-sphere embeddings).

**Failure modes worth watching**:

- **HDBSCAN parameter sensitivity**: `min_cluster_size` defaults to 5, but on small corpora (e.g. the 280-node seed) HDBSCAN can mark almost everything as noise. The seed integration test is the canary — if it fails, lower `min_cluster_size` for the test fixture rather than tuning the production default.
- **Cosine-vs-Euclidean confusion**: HDBSCAN does not natively support cosine. The pre-normalisation step is non-optional; assert it in the strategy unit tests.
- **Identity-stability flakiness**: the Jaccard greedy is deterministic only if ties are broken consistently. Use seeded UUID generation in tests (`monkeypatch.setattr("uuid.uuid4", ...)`) or sort by (size desc, then deterministic key) before mapping.
- **`cluster_index_refresh` race**: the IngestionPipeline reads the index while `ReclusterPhase` writes it. `ClusterIndex.replace` does an atomic dict-swap (`self._centroids = {...}`), which is thread-safe in CPython under the GIL for dict assignment — but the Pipeline could see the old index for one node mid-publish. That is acceptable: Phase 1 contract is "rough assignment", and the next ReclusterPhase pass corrects.
- **Cross-cluster edge update on Neo4j**: the single `MATCH (s)-[r]->(t) SET r.properties.cross_cluster = ...` query must run inside a transaction with a sensible `apoc.periodic.iterate` batch when the edge count exceeds 100k. For Phase 1 / the seed, plain Cypher is fine; add an issue comment in the helper noting the Phase-2 batching follow-up.

---

## Out of scope (do not do)

- **Do not** implement hierarchical clustering (centroids-of-centroids). That is the Knob-4 Phase-2 sub-ticket.
- **Do not** implement LLM-based cluster naming. That is the Knob-5 Phase-2 sub-ticket. The `cluster_label` field exists; it stays `None` for newly-minted clusters in Phase 1.
- **Do not** implement Argonaut sub-agents. That is the Knob-6 Phase-2 sub-ticket. Phase 1 reserves the `properties["agent_class"]` slot in `ClusterSummary` and stops.
- **Do not** add `bridge_score` to cross-cluster edges. That is the Knob-7 Phase-2 sub-ticket; pairs with PHX-0059 Morpheus.
- **Do not** add soft (multi-membership) clustering. The PHX-0060 YAML already calls this Phase 2.
- **Do not** push the `candidate_node_ids` restriction into `RetrievalBudget`. The Phase-1 `ClusterNarrowingRetrievalStrategy` uses post-filter; the hard-restriction optimisation is a measurable Phase-2 follow-up.
- **Do not** add per-cluster pheromone trails. That is PHX-0057.
- **Do not** add per-cluster blind-spot statistics. That is PHX-0058.
- **Do not** restrict Morpheus to within-cluster. That is PHX-0059.
- **Do not** federate clusters across Chronik instances. That is PHX-0061.
- **Do not** introduce an explicit `ClusteringWorker` separate from `OneirosWorker`. The PHX-0060 YAML allows either; this brief picks "phase inside OneirosWorker" because F2 already provides the pipeline shape, and a separate worker would duplicate lifespan / report-writer plumbing.

---

## Done when

- [ ] `src/theogony/clustering/` exists with the seven new files from the implementation plan.
- [ ] `src/theogony/retrieval/strategies/cluster_narrowing.py` exists; `ClusterNarrowingRetrievalStrategy` is registered in the `Settings.retrieval.strategy` literal and `_build_strategy`.
- [ ] `KnowledgeNode.cluster_label` exists; both backends round-trip it.
- [ ] `KnowledgeStore` Protocol gains `list_clusters` and `get_cluster_members`; both backends implement them.
- [ ] `ClusterSummary` lives in `core/model.py`.
- [ ] `Settings.clustering` group is wired; `Settings.retrieval` literal includes `"cluster_narrow"`.
- [ ] `OneirosWorker.DEFAULT_PHASE_REGISTRY` includes `"recluster"`. `OneirosSettings.enabled_phases` default is unchanged (does **not** include `"recluster"` by default).
- [ ] `OneirosWorker.__init__` accepts `cluster_index: ClusterIndex | None`.
- [ ] `IngestionPipeline` accepts `cluster_index: ClusterIndex` and uses it for new-node assignment + cross-cluster edge flagging.
- [ ] `api/app.py` lifespan wires a single `ClusterIndex` into both the IngestionPipeline and the OneirosWorker.
- [ ] `theogony ask --strategy cluster_narrow ...` works.
- [ ] `theogony recluster [--force]` works.
- [ ] `ClusteringRunReport` is wired through `reporting/models.py`, `reporting/__init__.py`, and `reporting/writer.py`.
- [ ] All existing tests stay green without modification (full `pytest -q`).
- [ ] New tests cover the five new test files; all green.
- [ ] `tests/test_pantheon_self_clustering.py` passes — the seed integration test is the high-value gate.
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy src/theogony/clustering/ src/theogony/retrieval/strategies/cluster_narrowing.py` clean (strict).
- [ ] `docs/ARCHITECTURE.md` §"The Knowledge Network as Its Own Index" updated.
- [ ] `docs/CLUSTERING.md` exists.
- [ ] `docs/PHOENIX_BACKLOG.md` PHX-0060 entry gets the closing note.
- [ ] `docs/RETRIEVAL_STRATEGIES.md` mentions `cluster_narrow`.
- [ ] PR title: `feat(clustering): W1 — Cluster v1 (PHX-0060 Phase 1)`. PR body lists the four resolved knobs (with the locked-in decision for each), confirms zero default-path behaviour change, and links the seed integration test result.

---

## After this PR

W1 closes PHX-0060 Phase 1 and unlocks the rest of Wave 1 because every subsequent Wave-1 ticket either consumes a cluster primitive or composes against the F2 + F3 + W1 foundation:

- **W2 — PHX-0057 Edge-Pheromone**: pheromone trails live in per-cluster spaces. The `cluster_id` field is the partition key. Adds a `PheromoneDecayPhase` to `OneirosWorker` and a `pheromone_mode` honouring branch to each retrieval strategy.
- **W3 — PHX-0058 Aggregated Stub Detection**: per-cluster blind-spot statistics. Reads `cluster_id` and the `KnowledgeStub` records (the `KnowledgeStub` model itself ships in W3).
- **W4 — PHX-0059 Morpheus-as-Associator**: associates within `cluster_id`; cross-cluster bridges get elevated provenance via the existing `cross_cluster` edge flag (no new schema work).

After Wave 1, the substrate has: clusters, pheromones, stubs, and an active dreamer. That is the operational shape PHX-0061 (federation), PHX-0062 (negative knowledge), and PHX-0063+ build on top of.
