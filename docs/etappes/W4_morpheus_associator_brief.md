# W4 — Morpheus-as-Associator + depth bands (PHX-0059 Phase 1)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-22  
**Branch:** new branch off `main`, e.g. `feat/w4-morpheus-associator`  
**Scope:** one PR  
**Predecessor:** Phase 0 closed by F1 + F2 + F3. W1 (Cluster, PR #52) + W2 (Pheromone, PR #55) + W3 (Stub Detection, PR via #56-impl). W4 is the **fourth and final sprint of Wave 1**.

Direct brief, no Daedalus. Eight knobs are pre-locked below. Your job is execution discipline.

---

## Why this etappe exists

The `OneirosWorker` today is **a lifecycle worker, not an associator**. Its tick measures, scores, promotes, and degrades — but it never creates a single new edge. Two structural problems flow from that gap:

- **The chronicle never enriches itself internally.** All edges come from extraction-time relation extraction; once a node is in the store, no further graph structure accrues to it from background work. New ingest sits in EPHEMERA as an island until something external mentions it again.
- **Promotion is a binary cliff.** A node is either EPHEMERA or MNEME. The user's image (conversation 2026-04-20) is much finer: knowledge sits in *layers* of varying embeddedness, and use + dreaming pushes it deeper. Today `connectivity` is continuous [0,1] but the *layer* representation is binary, so the graph cannot reflect the gradation.

W4 ships Phase 1 of the dreamer:

- **Part 1 — `MorpheusAssociator`** — a default-off `TickPhase` that, per tick, picks a small batch of weakly-connected EPHEMERA nodes and proposes new edges via two cheap deterministic signals: embedding similarity inside a cosine band, and source-document co-occurrence. Proposed edges land with `epistemic_type=INFERENCE`, `confidence=0.4`, and `properties["proposed_by"]="morpheus"`. Athene (PHX-0007 dependency) will eventually verify them; until then they sit in EPHEMERA at low confidence so retrieval can use them at low weight without elevating them.
- **Part 2 — Depth bands** — a new `depth_band: int [0..5]` on every `KnowledgeNode`, derived deterministically from connectivity + vitality + idle-days. Promotion / degradation become **band-step transitions** (one band per tick) instead of direct cross-layer jumps. The binary `Layer` enum stays as a derived view of the band (0–2 = EPHEMERA, 3–5 = MNEME) so all existing code keeps working.
- **Coupling to W2 (pheromone)**: edges with positive `pheromone_delta` count as "stronger" connectivity for band derivation, so well-trodden trails accelerate band ascent. The user's *Durchsickern-durch-Benutzung* effect becomes literal.
- **Coupling to W1 (clusters)**: Morpheus restricts proposals to within the same `cluster_id` by default; cross-cluster proposals are still emitted but tagged `properties["cross_cluster"]=True` (matching W1's edge convention) so they can be filtered or elevated.
- **No coupling to W3**: blind-spot prioritisation of Morpheus targets is interesting but tangles two new systems; deferred to a Phase-2 sub-ticket.

This is the deterministic floor. LLM-driven associative dreaming ("propose links you cannot mechanically derive") is PHX-0004 (Crystallized Inference) and explicitly out of scope.

---

## Pre-locked design knobs (locked 2026-04-22)

The PHX-0059 YAML left several decisions implicit. They are closed here:

### Knob 1 — Worker placement: `TickPhase`, default-off, after promote/degrade

Two new `TickPhase` registrations in `OneirosWorker.DEFAULT_PHASE_REGISTRY`, both **default-off** in `enabled_phases`:

- `"depth_band"` → `DepthBandPhase` (Part 2; computes the band, performs the one-step transition).
- `"morpheus"` → `MorpheusPhase` (Part 1; calls `MorpheusAssociator.propose_associations`).

Phase order when both are enabled: the canonical sequence becomes `snapshot_ephemera → count_neighbors → recompute_scores → write_scores → promote → degrade_mneme → depth_band → morpheus`. Rationale: Morpheus needs the freshest connectivity numbers AND the freshest band assignments to choose the right targets.

Operators opt in by adding both names to `enabled_phases`. Enabling only `morpheus` without `depth_band` is allowed; `MorpheusPhase` reads `connectivity` directly when the band is not yet maintained.

### Knob 2 — Two deterministic signals in Phase 1 (not four)

The PHX-0059 YAML lists four signals. Phase 1 ships the two with the cleanest implementation:

1. **Embedding similarity inside a cosine band**: for each candidate node, find other nodes whose embedding cosine similarity falls in `[embedding_band_low, embedding_band_high]` (default `[0.6, 0.9]`). The band is **deliberately not the top-N nearest neighbours**: very-near (>0.9) candidates are likely near-duplicates that PHX-0011 (Knowledge Condensation) handles, and very-far (<0.6) candidates are too noisy. The band is the "interesting middle".
2. **Source co-occurrence**: two nodes whose `source_ref.identifier` matches (same source document) but which are not yet directly connected. This is `WHERE source_ref.identifier IS NOT NULL AND identifier == candidate.source_ref.identifier`. Cheap, deterministic, and high-signal — co-mention in a single source is a real association the original extractor missed.

The YAML's other two signals (**temporal proximity**, **glossary mention overlap**) are deferred to Phase-2 sub-tickets:

- Temporal proximity needs structured time extraction on every node; today `time` is just a `node_type` literal, not a parsed datetime.
- Glossary mention overlap needs sentence-level mention spans on the source side, which the current ingest pipeline does not expose.

Both deferrals are explicit so the Phase-2 sub-tickets can land cleanly without retrofit.

### Knob 3 — Proposed edge shape: `INFERENCE` + `confidence=0.4` + provenance dict

```python
proposed_edge = KnowledgeEdge(
    source_id=src.id,
    target_id=tgt.id,
    relation_type="ASSOCIATED_WITH",  # generic; Athene may sharpen
    weight=0.5,                        # baseline; pheromone may move it
    confidence=0.4,                    # Phase-1 default per the YAML
    epistemic_type=EdgeType.INFERENCE,
    source_ref=None,                   # no source — it's an inference
    evidence_span=None,
    properties={
        "proposed_by": "morpheus",
        "signal": signal_name,         # "embedding" or "cooccurrence"
        "signal_value": signal_value,  # cosine for embedding; identifier for cooccurrence
        "tick_run_id": ctx.run_id,     # cross-reference to the OneirosTickReport
        "cross_cluster": src_cluster != tgt_cluster,  # W1 convention
    },
)
```

`relation_type="ASSOCIATED_WITH"` is the deliberate generic — Phase 1 cannot honestly claim a specific relation. Athene (when implemented) sharpens it; the LLM-dreaming follow-up (PHX-0004) may propose typed relations directly.

### Knob 4 — Per-node and per-tick caps (the cost ceiling)

```python
class MorpheusSettings(BaseModel):
    """Morpheus associator (PHX-0059 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    batch_size: int = Field(default=50, ge=1, le=500)
    proposals_per_node_cap: int = Field(default=5, ge=1, le=50)
    embedding_band_low: float = Field(default=0.6, ge=0.0, le=1.0)
    embedding_band_high: float = Field(default=0.9, ge=0.0, le=1.0)
    candidate_isolation_max_edges: int = Field(default=5, ge=0)
    cluster_scope: Literal["within_only", "within_and_cross"] = "within_and_cross"
```

Per tick: process at most `batch_size` candidate nodes; each candidate produces at most `proposals_per_node_cap` proposed edges. Hard ceiling: `batch_size × proposals_per_node_cap = 250 new edges per tick by default`.

Candidate selection: nodes in EPHEMERA with `count_neighbors < candidate_isolation_max_edges` (the "lonely Ephemera" set). Process oldest-first (newest ingest gets first dibs at association on the next tick). Once a node has `≥ candidate_isolation_max_edges`, Morpheus leaves it alone.

### Knob 5 — Depth-band derivation: deterministic from existing scores

```python
def derive_depth_band(node: KnowledgeNode, *, idle_days: float) -> int:
    """Return depth_band ∈ [0, 5] from the node's lifecycle signals.

    Bands form a one-way ladder; the actual band assignment per
    tick is bounded to ±1 from the current band so transitions
    are visible across many ticks rather than instant jumps.
    """
    conn = node.scores.connectivity      # [0, 1]
    vit = node.scores.vitality()         # [0, 1] (composite)

    # Combined "embeddedness score" — weighted toward connectivity
    # because that is what bands are fundamentally about.
    embeddedness = 0.6 * conn + 0.4 * vit

    if node.layer is Layer.EPHEMERA:
        if embeddedness < 0.20:
            return 0   # raw Ephemera
        if embeddedness < 0.45:
            return 1   # settling Ephemera
        return 2       # promotable Ephemera

    # Layer.MNEME
    if idle_days >= 30 and vit < 0.35:
        return 3       # cooling Mneme
    if embeddedness < 0.65:
        return 3       # freshly promoted Mneme
    if embeddedness < 0.85:
        return 4       # well-embedded Mneme
    return 5           # canonical Mneme
```

The band is **derived**, not stored as the source of truth — but it IS persisted on `KnowledgeNode` after each `DepthBandPhase` tick so consumers (Mind-Map, retrieval, Morpheus's own candidate selection) can read it without re-computing.

### Knob 6 — Band-step transitions: one band per tick, not direct jumps

`DepthBandPhase` enforces the smoothing:

```python
async def run(self, ctx: TickContext) -> None:
    cfg = ctx.cfg.depth_band
    async for node in ctx.store.export_layer(Layer.EPHEMERA):
        target_band = derive_depth_band(node, idle_days=...)
        new_band = _step_one(node.depth_band or 0, target_band)
        if new_band != (node.depth_band or 0):
            await ctx.store.update_depth_band(node.id, new_band)
            ctx.depth_band_transitions += 1

    async for node in ctx.store.export_layer(Layer.MNEME):
        target_band = derive_depth_band(node, idle_days=...)
        new_band = _step_one(node.depth_band or 3, target_band)
        if new_band != (node.depth_band or 3):
            await ctx.store.update_depth_band(node.id, new_band)
            ctx.depth_band_transitions += 1


def _step_one(current: int, target: int) -> int:
    if target > current:
        return current + 1
    if target < current:
        return current - 1
    return current
```

**Layer transitions follow band crossings**, not the existing `promote_threshold` math:

- A Band-2 EPHEMERA node whose target band is 3 gets `update_depth_band(3)` AND a layer change to MNEME in the same store call (the store decides; see Scope decision 4 below).
- A Band-3 MNEME node whose target band is 2 gets a degrade to EPHEMERA + band 2 in the same call.

The existing `promote()` / `degrade()` hooks remain in the store Protocol — they are the atomic operations the band phase calls. The existing `PromotePhase` and `DegradeMnemePhase` continue to work for operators who run them without the depth-band phase.

### Knob 7 — Pheromone integration: `effective_connectivity` for band math

When computing `embeddedness` in `derive_depth_band`, the connectivity score should reflect pheromone bumps (W2). Concrete shape:

```python
def effective_connectivity(node: KnowledgeNode, *, edges_for_node: list[KnowledgeEdge]) -> float:
    """Connectivity boosted by accumulated pheromone deltas on this node's edges."""
    base = node.scores.connectivity
    if not edges_for_node:
        return base
    pheromone_bonus = sum(max(0.0, e.pheromone_delta) for e in edges_for_node) / len(edges_for_node)
    return min(1.0, base + 0.5 * pheromone_bonus)
```

The 0.5 coefficient is tuneable; defaults documented in `Settings.depth_band.pheromone_bonus_weight`. Phase 1 ships the default; Phase 2 may tune from data.

This requires `DepthBandPhase` to load the edges per node — same `get_edges_among` / `get_neighborhood` shape Morpheus uses. Single store call per band tick (fetch all in-batch); not a regression.

### Knob 8 — Cluster scope for Morpheus proposals

`Settings.morpheus.cluster_scope` Literal:

- `"within_only"`: Morpheus only proposes edges where `src.cluster_id == tgt.cluster_id`. Cross-cluster bridges are deferred.
- `"within_and_cross"` (default): both within and cross-cluster proposals are allowed; cross-cluster ones are tagged `properties["cross_cluster"]=True`. The retrieval stack (W2 `pheromone_mode`, W1 `cluster_narrow`) already respects the flag.

Within-only is the conservative choice for an operator running Morpheus on a noisy corpus; the default is open because cross-cluster bridges are exactly the kind of "surprising association" the dreamer is supposed to surface.

`bridge_score` computation on cross-cluster proposals is **deferred** to a Phase-2 sub-ticket (paired with PHX-0060 Phase 2). Phase 1 just emits the boolean flag.

---

## Goal

After this PR:

- `KnowledgeNode.depth_band: int = Field(default=0, ge=0, le=5)` exists; both backends round-trip it.
- `derive_depth_band` lives in `src/theogony/memory/depth_band.py` and is unit-tested independently of any worker.
- `DepthBandPhase` lives in `src/theogony/memory/depth_band_phase.py`; default-off; one-band-per-tick smoothing; layer transitions follow band crossings.
- `MorpheusAssociator` lives in `src/theogony/memory/morpheus.py`; pure logic; takes a candidate set + a store + thresholds, returns a list of proposed `KnowledgeEdge`s.
- `MorpheusPhase` lives in `src/theogony/memory/morpheus_phase.py`; default-off; calls the associator and persists proposals.
- `KnowledgeStore` Protocol gains:
  - `list_low_connectivity_nodes(*, layer: Layer, max_edges: int, batch_size: int) -> list[KnowledgeNode]`
  - `find_similar_nodes_in_band(embedding, *, band_low: float, band_high: float, exclude_ids: set[str], top_k: int, layer: Layer | None = None) -> list[ScoredNode]`
  - `update_depth_band(node_id: str, depth_band: int, *, layer: Layer | None = None) -> None`
- Both backends implement the three new methods.
- `OneirosTickReport` gains optional `morpheus: MorpheusBreakdown | None` and `depth_band: DepthBandBreakdown | None`. Both default `None`; populated only when the corresponding phases ran.
- `Settings.morpheus`, `Settings.depth_band` groups exist with the knobs from Knob 4 and Knob 5.
- `OneirosWorker.DEFAULT_PHASE_REGISTRY` registers `"depth_band"` and `"morpheus"`. `OneirosSettings.enabled_phases` default is **unchanged**.
- New `tests/test_morpheus_associator.py`, `tests/test_morpheus_phase.py`, `tests/test_depth_band_derivation.py`, `tests/test_depth_band_phase.py`, `tests/test_morpheus_integration.py` cover the contracts. The integration test runs Morpheus over the bundled `pantheon_self` seed for 10 ticks.
- New `docs/MORPHEUS.md` documents the dreamer; `docs/DEPTH_BANDS.md` documents the band ladder. `docs/ARCHITECTURE.md` updated. `docs/GLOSSARY.md` learns the new terms.

---

## Scope decisions (read first)

### 1. The `MorpheusAssociator`

Lives at `src/theogony/memory/morpheus.py`. Pure logic; ~200 lines.

```python
@dataclass(frozen=True)
class AssociationProposal:
    """Output of one MorpheusAssociator.propose_associations call."""

    edges: list[KnowledgeEdge]
    candidates_considered: int
    candidates_with_proposals: int
    candidates_skipped_no_neighbors_in_band: int


class MorpheusAssociator:
    """Deterministic association proposals (PHX-0059 Phase 1)."""

    name = "morpheus"

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        cfg: MorpheusSettings,
    ) -> None:
        self._store = store
        self._cfg = cfg

    async def propose_associations(
        self,
        *,
        run_id: str,
    ) -> AssociationProposal:
        # 1. Pick the candidate batch — lonely Ephemera, oldest first.
        candidates = await self._store.list_low_connectivity_nodes(
            layer=Layer.EPHEMERA,
            max_edges=self._cfg.candidate_isolation_max_edges,
            batch_size=self._cfg.batch_size,
        )

        all_proposals: list[KnowledgeEdge] = []
        candidates_with = 0
        candidates_no_band = 0

        for cand in candidates:
            proposals_for_cand: list[KnowledgeEdge] = []

            # Signal 1 — embedding band
            if cand.embedding:
                similar = await self._store.find_similar_nodes_in_band(
                    embedding=cand.embedding,
                    band_low=self._cfg.embedding_band_low,
                    band_high=self._cfg.embedding_band_high,
                    exclude_ids={cand.id},
                    top_k=self._cfg.proposals_per_node_cap,
                )
                for scored in similar:
                    if self._cfg.cluster_scope == "within_only":
                        if scored.node.cluster_id != cand.cluster_id:
                            continue
                    proposals_for_cand.append(
                        _build_proposal(
                            src=cand,
                            tgt=scored.node,
                            signal="embedding",
                            signal_value=str(scored.score),
                            run_id=run_id,
                        )
                    )

            # Signal 2 — source cooccurrence
            if cand.source_ref and cand.source_ref.identifier:
                cooccurring = await _list_cooccurring_nodes(
                    self._store, cand, exclude_ids={cand.id}
                )
                for other in cooccurring:
                    if self._cfg.cluster_scope == "within_only":
                        if other.cluster_id != cand.cluster_id:
                            continue
                    proposals_for_cand.append(
                        _build_proposal(
                            src=cand,
                            tgt=other,
                            signal="cooccurrence",
                            signal_value=cand.source_ref.identifier,
                            run_id=run_id,
                        )
                    )

            # Per-node cap + dedupe (same (src, tgt) pair from multiple signals)
            proposals_for_cand = _dedupe_pairs(proposals_for_cand)
            proposals_for_cand = proposals_for_cand[: self._cfg.proposals_per_node_cap]

            if proposals_for_cand:
                candidates_with += 1
                all_proposals.extend(proposals_for_cand)
            else:
                candidates_no_band += 1

        return AssociationProposal(
            edges=all_proposals,
            candidates_considered=len(candidates),
            candidates_with_proposals=candidates_with,
            candidates_skipped_no_neighbors_in_band=candidates_no_band,
        )
```

**`_list_cooccurring_nodes`** is a private helper inside the same module; it walks the store via a small query (`source_ref.identifier == cand.source_ref.identifier AND id != cand.id`). Add a one-liner helper to `KnowledgeStore` if the existing API does not already support filtering by `source_ref.identifier`.

**`_dedupe_pairs`** keeps the proposal with the higher `signal_value` per `(src, tgt)` pair when both signals fire.

### 2. The `MorpheusPhase`

Wraps the associator. Lives at `src/theogony/memory/morpheus_phase.py`. ~80 lines.

```python
class MorpheusPhase:
    name = "morpheus"

    async def run(self, ctx: TickContext) -> None:
        cfg = ctx.cfg.morpheus
        associator = MorpheusAssociator(ctx.store, cfg=cfg)

        proposal = await associator.propose_associations(run_id=ctx.run_id)
        if proposal.edges:
            await ctx.store.batch_upsert_edges(proposal.edges)

        ctx.extras["morpheus"] = {
            "candidates_considered": proposal.candidates_considered,
            "candidates_with_proposals": proposal.candidates_with_proposals,
            "candidates_skipped_no_neighbors_in_band": proposal.candidates_skipped_no_neighbors_in_band,
            "edges_proposed": len(proposal.edges),
        }
```

`TickContext` does not yet carry `run_id`. Extend it to do so (one-liner; `OneirosWorker._tick` already mints a run id at finalize-time, just plumb it earlier).

### 3. The `derive_depth_band` function

Lives at `src/theogony/memory/depth_band.py`. Pure function per Knob 5. ~80 lines including the `effective_connectivity` helper from Knob 7.

The function is fully unit-testable without any store: takes a `KnowledgeNode`, a list of its `KnowledgeEdge`s, and a `now: datetime` for idle-day computation. Returns `int`. No side effects.

### 4. The `DepthBandPhase`

Lives at `src/theogony/memory/depth_band_phase.py`. ~120 lines.

```python
class DepthBandPhase:
    name = "depth_band"

    async def run(self, ctx: TickContext) -> None:
        # Iterate both layers; for each node, derive the target band,
        # step ±1 toward it, persist the new band. If the band crosses
        # the EPHEMERA/MNEME boundary (2↔3), also call promote/degrade.
        transitions = 0
        layer_changes = 0
        for layer in (Layer.EPHEMERA, Layer.MNEME):
            async for node in ctx.store.export_layer(layer):
                edges = await ctx.store.get_neighborhood(node.id, depth=1, min_weight=0.0)
                idle_days = (ctx.started_at - _aware(node.last_accessed)).total_seconds() / 86400.0
                target = derive_depth_band(node, edges_for_node=edges.edges, idle_days=idle_days)

                current = node.depth_band or (0 if layer is Layer.EPHEMERA else 3)
                new_band = _step_one(current, target)
                if new_band == current:
                    continue

                # Boundary crossings: 2 → 3 means promote, 3 → 2 means degrade.
                if layer is Layer.EPHEMERA and new_band >= 3:
                    await ctx.store.promote(node.id)
                    layer_changes += 1
                elif layer is Layer.MNEME and new_band <= 2:
                    await ctx.store.degrade(node.id)
                    layer_changes += 1

                await ctx.store.update_depth_band(node.id, new_band)
                transitions += 1

        ctx.extras["depth_band"] = {
            "transitions": transitions,
            "layer_changes": layer_changes,
        }
```

**Implementation note**: the existing `PromotePhase` / `DegradeMnemePhase` continue to exist and continue to work; operators choose which set of phases to run via `enabled_phases`. The classic phases use the existing thresholds; `DepthBandPhase` uses the band ladder. Running both is supported but redundant — document it in `docs/DEPTH_BANDS.md` as "either-or".

### 5. New `KnowledgeStore` methods

```python
async def list_low_connectivity_nodes(
    self,
    *,
    layer: Layer,
    max_edges: int,
    batch_size: int,
) -> list[KnowledgeNode]:
    """Return up to batch_size nodes in the given layer whose edge count is < max_edges.

    Order: oldest created_at first (so newest ingest gets first
    chance at association on the next tick). Both backends implement
    via a single round-trip.
    """
    ...


async def find_similar_nodes_in_band(
    self,
    embedding: list[float],
    *,
    band_low: float,
    band_high: float,
    exclude_ids: set[str],
    top_k: int,
    layer: Layer | None = None,
) -> list[ScoredNode]:
    """Vector search restricted to a cosine-similarity band [band_low, band_high].

    Differs from existing vector_search: that one returns the top-k
    most-similar nodes (no lower bound). This one returns the top-k
    nodes whose similarity falls inside the band — the "interesting
    middle" Morpheus targets.
    """
    ...


async def update_depth_band(
    self,
    node_id: str,
    depth_band: int,
    *,
    layer: Layer | None = None,
) -> None:
    """Set node's depth_band to the given value. Optional layer change in the same call.

    Single round-trip. Silent no-op for unknown node_id (matches
    the existing update_scores semantics).
    """
    ...
```

Neo4j: `find_similar_nodes_in_band` builds on the existing HNSW query but adds a `WHERE` clause filtering the cosine score. In-memory: brute-force scan filtered by the band — acceptable for the bundled seed; the Neo4j path is the production answer.

### 6. `OneirosTickReport` extensions

```python
class MorpheusBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates_considered: int = Field(default=0, ge=0)
    candidates_with_proposals: int = Field(default=0, ge=0)
    candidates_skipped_no_neighbors_in_band: int = Field(default=0, ge=0)
    edges_proposed: int = Field(default=0, ge=0)


class DepthBandBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transitions: int = Field(default=0, ge=0)
    layer_changes: int = Field(default=0, ge=0)
    distribution: dict[int, int] = Field(default_factory=dict)  # band → count

class OneirosTickReport(RunReportBase):
    # ... existing fields ...
    morpheus: MorpheusBreakdown | None = None
    depth_band: DepthBandBreakdown | None = None
```

`OneirosWorker._finalize_report` populates `morpheus` from `ctx.extras.get("morpheus")` and `depth_band` from `ctx.extras.get("depth_band")` — same pattern W3 uses. `None` when the phase did not run.

### 7. `KnowledgeNode.depth_band` schema

```python
depth_band: int = Field(
    default=0,
    ge=0,
    le=5,
    description=(
        "Depth-band ladder [0..5]: bands 0-2 are EPHEMERA strata "
        "(raw → settling → promotable), bands 3-5 are MNEME strata "
        "(freshly promoted → well-embedded → canonical). Derived by "
        "DepthBandPhase from connectivity + vitality + idle-days. "
        "See docs/DEPTH_BANDS.md."
    ),
)
```

Both backends round-trip it. New nodes get `depth_band=0` from the default. Pre-W4 data on disk also defaults to 0 on read (Pydantic), and the first `DepthBandPhase` tick walks them up to their honest band.

### 8. CLI + MCP touches

- `theogony recluster` already exists for W1 one-shot. Add **`theogony oneiros tick [--phase NAME ...]`** — a one-shot single-tick driver, useful for testing and operator-controlled associative passes. Optional flags pass through `enabled_phases`. ~30 lines in `cli.py`.
- `pantheon_status` MCP tool gains a small `morpheus_proposals_recent` count (read from the most recent OneirosTickReport with a non-null morpheus block) — purely diagnostic.

---

## Implementation plan (file-by-file)

### `src/theogony/memory/morpheus.py` (new)

`MorpheusAssociator` + `AssociationProposal` + `_build_proposal` + `_dedupe_pairs` + `_list_cooccurring_nodes`. ~200 lines.

### `src/theogony/memory/morpheus_phase.py` (new)

`MorpheusPhase` per Scope decision 2. ~80 lines.

### `src/theogony/memory/depth_band.py` (new)

`derive_depth_band` + `effective_connectivity` + `_step_one` (private). ~80 lines.

### `src/theogony/memory/depth_band_phase.py` (new)

`DepthBandPhase` per Scope decision 4. ~120 lines.

### `src/theogony/core/model.py`

Add `depth_band: int` to `KnowledgeNode` per Scope decision 7.

### `src/theogony/core/store.py`

Add the three new methods per Scope decision 5.

### `src/theogony/stores/memory.py`

Implement the three new methods. Update node round-trip to include `depth_band`. Add a small private index `_low_connectivity_set` if the brute-force scan becomes a hot path (Phase-1 contract: brute force is OK for the seed).

### `src/theogony/stores/neo4j_store.py`

Implement the three new methods. The `find_similar_nodes_in_band` extends the existing HNSW query with a `WHERE score >= $band_low AND score < $band_high` clause. `list_low_connectivity_nodes` uses an `OPTIONAL MATCH` count + `WHERE c < $max_edges`. `update_depth_band` is a one-line `SET`. Update `_node_to_props` / `_node_from_props` to round-trip `depth_band`.

### `src/theogony/stores/_schema.py`

Add `BTREE INDEX FOR (n:KnowledgeNode) ON (n.depth_band)` so Mind-Map queries by band stay fast. Do **not** add a separate index on connectivity — the existing one is enough.

### `src/theogony/config/settings.py`

Add `MorpheusSettings` and `DepthBandSettings` per Knobs 4 + 7. Wire into top-level `Settings`. The `DepthBandSettings` only needs `pheromone_bonus_weight: float = Field(default=0.5, ge=0.0, le=2.0)`; everything else lives inside `derive_depth_band` as constants for now.

### `src/theogony/memory/oneiros.py`

Register both new phases in `DEFAULT_PHASE_REGISTRY`. The default `enabled_phases` does **not** include them. Plumb `run_id` into `TickContext` (one-liner; mint earlier in `_tick`).

### `src/theogony/memory/tick_phase.py`

Add `run_id: str` to `TickContext`. Default value at construction-time in `OneirosWorker._tick` is `new_run_id()`.

### `src/theogony/reporting/models.py`

Add `MorpheusBreakdown` and `DepthBandBreakdown`. Extend `OneirosTickReport` with the two optional fields per Scope decision 6.

### `src/theogony/cli.py`

Add `theogony oneiros tick [--phase NAME ...]` per Scope decision 8 (small).

### `src/theogony/mcp/server.py`

Extend `pantheon_status` payload with the `morpheus_proposals_recent` field.

### `tests/test_depth_band_derivation.py` (new)

- `test_derive_band_zero_for_isolated_ephemera`.
- `test_derive_band_two_for_promotable_ephemera`.
- `test_derive_band_three_for_freshly_promoted_mneme`.
- `test_derive_band_five_for_canonical_mneme`.
- `test_derive_band_drops_to_three_for_idle_low_vitality_mneme`.
- `test_effective_connectivity_includes_pheromone_bonus`.
- `test_effective_connectivity_clamped_to_one`.

### `tests/test_depth_band_phase.py` (new)

- `test_phase_steps_one_band_at_a_time`.
- `test_phase_promotes_when_band_crosses_to_three`.
- `test_phase_degrades_when_band_crosses_to_two`.
- `test_phase_writes_distribution_to_extras`.
- `test_phase_handles_pre_w4_nodes_without_depth_band`.

### `tests/test_morpheus_associator.py` (new)

- `test_propose_skips_when_no_low_connectivity_candidates`.
- `test_propose_emits_embedding_band_proposals`.
- `test_propose_skips_top_n_above_band_high`.
- `test_propose_emits_cooccurrence_proposals`.
- `test_propose_dedupes_same_pair_from_two_signals`.
- `test_propose_respects_proposals_per_node_cap`.
- `test_propose_marks_cross_cluster_in_properties`.
- `test_propose_within_only_filters_cross_cluster`.
- `test_proposed_edges_have_correct_metadata`.

### `tests/test_morpheus_phase.py` (new)

- `test_phase_persists_proposals`.
- `test_phase_writes_extras_with_breakdown`.
- `test_phase_handles_empty_candidate_set_silently`.

### `tests/test_morpheus_integration.py` (new — high-value gate)

- `test_pantheon_self_morpheus_run_proposes_plausible_edges`. Setup: load the bundled `pantheon_self` seed into the in-memory store, run `MorpheusPhase` once. Assert: at least 5 proposals emitted, all carry `epistemic_type=INFERENCE` + `confidence=0.4` + `properties["proposed_by"]="morpheus"`. At least one proposal is between two nodes from different `source_ref.identifier`s (cross-source association). At least one proposal is in the embedding band (signal=embedding) and at least one is from co-occurrence.
- `test_depth_band_phase_stratifies_pantheon_self_seed`. Setup: load the seed, run `DepthBandPhase` 3 times (multi-step). Assert: bands 0-5 distribution is non-degenerate (at least 3 distinct bands populated); no node skipped a band on a single tick.

### Documentation touches

1. `docs/MORPHEUS.md` (new, ~150 lines): documents the dreamer principle, the two Phase-1 deterministic signals, the proposed-edge shape and how Athene will eventually verify it, the cluster-scope knob, and a "Phase 2 / open questions" section listing: temporal-proximity signal, glossary-mention signal, LLM-driven dreaming (PHX-0004), Athene verification (PHX-0007), bridge_score on cross-cluster proposals, blind-spot-aware target selection (composes with W3).

2. `docs/DEPTH_BANDS.md` (new, ~100 lines): documents the six-band ladder, the derivation formula, the one-band-per-tick smoothing, the EPHEMERA↔MNEME boundary at the 2↔3 crossing, and the relationship to the existing PromotePhase / DegradeMnemePhase ("either-or").

3. `docs/ARCHITECTURE.md` Memory section: replace the binary EPHEMERA/MNEME paragraph with a band-aware version. Cross-reference both new docs.

4. `docs/GLOSSARY.md`: add entries for `depth_band`, `Morpheus associator`, `embedding band`, `cooccurrence signal`.

5. `docs/PHOENIX_BACKLOG.md` PHX-0059 catalogue entry: append `"Phase 1 closed by W4 (PR #...): MorpheusAssociator + MorpheusPhase (default-off, embedding-band + cooccurrence signals), depth_band schema + DepthBandPhase (default-off, one-band-per-tick smoothing, layer transitions follow band crossings), KnowledgeStore Protocol additions (list_low_connectivity_nodes, find_similar_nodes_in_band, update_depth_band), pheromone-aware effective_connectivity. Phase 2 sub-tickets: temporal-proximity signal, glossary-mention signal, LLM-driven dreaming (PHX-0004), Athene verification (PHX-0007), bridge_score, blind-spot-aware targeting."`

6. `docs/HIVE.md` §"Morpheus": expand the "Builder" line into a short paragraph noting the deterministic Phase-1 scope and the LLM-driven Phase-2 path (PHX-0004).

7. `docs/CHRONICLE_PRINCIPLES.md`: add a one-liner — "The chronicle is allowed to dream; the dream is allowed to be wrong; the dream is never elevated without verification."

---

## Cost-benefit considerations

**Token cost**: largest of Wave 1 because it ships two coupled features (Morpheus + depth bands). Composer adds two new TickPhases, two new pure-logic modules, three new store methods on both backends, schema changes, plumbing through reports / settings / CLI / MCP, and ~20 new tests. Estimate ≤ €1.40 of Composer execution. Bigger than W3, similar to W1.

**Runtime cost**:

- Both new phases are **default-off**. Existing deployments see zero overhead until operators opt in.
- When enabled:
  - `DepthBandPhase`: walks every node in both layers each tick, with one `get_neighborhood` per node. For 1000 nodes, that is ~1 s per tick on the in-memory store, ~5 s on Neo4j. Acceptable at the default 60 s tick interval.
  - `MorpheusPhase`: bounded by `batch_size × proposals_per_node_cap` (default 250 new edges per tick worst case). In practice the band-restricted vector search drops most candidates to zero. Sub-second on the seed.
- Disk cost: `KnowledgeNode` payload grows by 1 small int (`depth_band`). `KnowledgeEdge` payload unchanged (Morpheus uses existing `properties` dict).

**Test cost**: ~22 new tests; estimated ~2 s wall-clock added (the integration test runs the phase against the 278-node seed 3 times for the depth-band stratification check).

**Failure modes worth watching**:

- **Embedding-band miscalibration**: `[0.6, 0.9]` is a guess. If too tight, Morpheus emits zero proposals on the seed; if too wide, it floods the chronicle with low-quality associations. The integration test asserts ≥ 5 proposals on the seed — if it fails, the band needs widening (lower `band_low`).
- **Pre-W4 data without `depth_band`**: existing nodes default to 0 on read. The first `DepthBandPhase` tick walks them all up to their honest band; until then, queries that filter on `depth_band >= N` return nothing for legacy data. Document in `docs/DEPTH_BANDS.md`.
- **Layer-band desync**: a Band-3 node MUST be in MNEME; a Band-2 node MUST be in EPHEMERA. The store-level constraint is enforced by `DepthBandPhase`'s promote/degrade calls when crossing the boundary. A unit test (`test_phase_promotes_when_band_crosses_to_three`) is the regression gate.
- **`run_id` plumbing**: the proposed-edge `properties["tick_run_id"]` allows tracing every Morpheus edge back to the tick that proposed it. If `TickContext.run_id` plumbing breaks, the field is empty — useful audit signal silently lost. Test it in `test_proposed_edges_have_correct_metadata`.
- **Brute-force `find_similar_nodes_in_band` on Neo4j**: HNSW is good at top-k, less good at "top-k inside a band". The Cypher pattern (`vector.similarity.cosine(n.embedding, $q) AS score WHERE score >= $low AND score < $high`) works but post-filters. For 100k nodes that is acceptable; for 10M it would not scale. PHX-0001 (custom store) eventually handles it; Phase 1 is fine.

---

## Out of scope (do not do)

- **Do not** add LLM-driven associative dreaming. That is PHX-0004 (Crystallized Inference). Phase 1 is deterministic-only.
- **Do not** implement Athene verification of proposed edges. That is PHX-0007. Phase 1 leaves proposals at `confidence=0.4` and lets retrieval use them at low weight.
- **Do not** add the temporal-proximity signal or the glossary-mention signal. Phase-2 sub-tickets per Knob 2.
- **Do not** compute `bridge_score` on cross-cluster proposals. Phase-2 sub-ticket per Knob 8 (paired with PHX-0060 Phase 2).
- **Do not** wire blind-spot-aware target selection (W3). Composing two new systems in one PR is too much surface area; that is a Phase-2 follow-up that benefits from real W3 signal first.
- **Do not** retire the existing `PromotePhase` / `DegradeMnemePhase`. They stay; operators choose. `DepthBandPhase` is the new option, not the replacement.
- **Do not** add a Mind-Map render of bands. That is PHX-0038.
- **Do not** introduce a separate Morpheus worker outside `OneirosWorker`. The TickPhase shape is the right home.
- **Do not** use the embedding-band signal to trigger duplicate detection (>0.9 similarity). PHX-0011 (Knowledge Condensation) owns that; Morpheus's `band_high=0.9` is the deliberate upper bound that hands duplicates off.

---

## Done when

- [ ] `KnowledgeNode.depth_band` exists; both backends round-trip it.
- [ ] `derive_depth_band` lives in `src/theogony/memory/depth_band.py`; pure, fully unit-tested.
- [ ] `DepthBandPhase` lives in `src/theogony/memory/depth_band_phase.py`; default-off; one-band-per-tick.
- [ ] `MorpheusAssociator` lives in `src/theogony/memory/morpheus.py`; pure logic.
- [ ] `MorpheusPhase` lives in `src/theogony/memory/morpheus_phase.py`; default-off; calls the associator.
- [ ] `KnowledgeStore` Protocol gains `list_low_connectivity_nodes`, `find_similar_nodes_in_band`, `update_depth_band`; both backends implement.
- [ ] `OneirosWorker.DEFAULT_PHASE_REGISTRY` includes `"depth_band"` and `"morpheus"`. `OneirosSettings.enabled_phases` default does **not** include them.
- [ ] `Settings.morpheus` and `Settings.depth_band` groups exist.
- [ ] `OneirosTickReport.morpheus` and `OneirosTickReport.depth_band` exist (both `Optional`, default `None`).
- [ ] `TickContext.run_id` is plumbed through.
- [ ] `theogony oneiros tick [--phase NAME ...]` works.
- [ ] `pantheon_status` MCP tool exposes `morpheus_proposals_recent`.
- [ ] All existing tests stay green without modification (full `pytest -q`).
- [ ] New tests cover the five new test files; all green.
- [ ] `tests/test_morpheus_integration.py::test_pantheon_self_morpheus_run_proposes_plausible_edges` is the high-value gate; must pass.
- [ ] `tests/test_morpheus_integration.py::test_depth_band_phase_stratifies_pantheon_self_seed` passes.
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy` clean (strict) on the new modules.
- [ ] `docs/MORPHEUS.md`, `docs/DEPTH_BANDS.md` exist; `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`, `docs/HIVE.md`, `docs/CHRONICLE_PRINCIPLES.md`, `docs/PHOENIX_BACKLOG.md` updated.
- [ ] PR title: `feat(memory): W4 — Morpheus associator + depth bands (PHX-0059 Phase 1)`. PR body lists the eight resolved knobs, confirms zero default-path regression on existing tests, and includes the result of both integration gates.

---

## After this PR

W4 closes PHX-0059 Phase 1 and **closes Wave 1 entirely**. The substrate now has:

- **Cluster routing (W1)** — brain-region partitioning + cluster_narrow retrieval.
- **Pheromone trails (W2)** — used edges strengthen, unused decay, Slow-Path can walk against the trail.
- **Stub aggregation (W3)** — recurring blind spots emit BlindSpotReports.
- **Active dreaming (W4)** — Morpheus closes connectivity gaps deterministically; depth bands turn the binary EPHEMERA/MNEME cliff into a smooth six-step ladder.

This is the operational shape **PHX-0061 (Vector-Routed Federation)**, **PHX-0062 (Negative Knowledge)**, and **PHX-0063+ (Chronik-Diff, Portable Constellation, Time-Machine)** build on top of. Wave 2 begins.
