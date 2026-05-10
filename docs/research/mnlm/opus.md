# MNLM design — Opus

Model: Claude Opus 4.7 (slug: `opus`)
Date: 2026-05-10
Filed by: claude-opus-4.7
Brief: docs/etappes/mesh_native_lm_research_brief.md

---

## A. Three-sentence summary

A Mesh-Native Language Model is a frozen 3–7 B parameter instruction-tuned LLM (Qwen 2.5-3B / Llama 3.1-8B class), wrapped by two thin LoRA-adapted modules — a `GraphProjector` that turns a Kadmos-emitted vector subgraph into ~128 continuous prefix tokens, and a `MeshDecoder` head that turns ~32 latent output tokens into a typed Pydantic `MeshDelta` of `MutationPrimitive`s — and operated by a substrate-resonant recurrence loop where every K-th latent reasoning step is interleaved with a one-hop spreading-activation cycle on the existing `TensorMeshEngine`, so the MNLM and the substrate share recurrent state. The training signal is **teacher-forced trajectory imitation from Kadmos itself**: every Kadmos v2 `ReadingStep` already produces the (mesh-context-in, structural-update-out) pair the MNLM needs; no new corpus, no frontier-LLM-with-RAG teacher, no synthetic graph completion task. The falsifier is a 200-pair directional-binding minimal-pair benchmark on synthetic mini-meshes ("John LOVES Mary" vs. "Mary LOVES John"); below 95 % directional-edge accuracy after 24 GPU-hours of LoRA adaptation, the typed-edge-plus-latent-CoT bet for compositional binding fails and Stance C (§J) collapses into a Stance-B-only fallback that needs more linguistic scaffolding than the architecture wants.

## B. Scope statement

I address §4.1 (input format and the Kadmos contract), §4.2 (output format), §4.4 (training signal), §4.5 (frozen-LLM adaptation), §4.6 (boundary text channel — the machine-checkable enforcement), §4.7 (latent reasoning), §4.8 (mutation contract), and §10 (the systematicity question, Stance C). I leave §4.3 (inter-agent communication beyond what falls out of shared substrate writes), §4.9 (cross-cycle working memory inside the MNLM beyond a one-call horizon), and §4.10 (control-plane shape — trigger/budget/scope) to other agents in the round; my position there is "the substrate's append-only, locks-free shape already answers most of the control-plane question, the MNLM call is a transaction with a mutation budget, full stop", and I would rather a sibling artifact deepen that than I sketch it shallowly. I take an explicit, opinionated position on §4.1 — the schema must be *layered*, not flat — which I name in §I as a friendly amendment to the brief's "MNLM defines the schema, Kadmos conforms" framing.

## C. Architecture proposal — the Substrate-Resonant MNLM (SR-MNLM)

### C.1 The shape

```
                       MeshInput (Pydantic)
                              │
                              ▼
                    ┌──────────────────────┐
                    │   GraphProjector      │   LoRA-trained MLP
                    │   subgraph → ~128     │   (~5 M params)
                    │   continuous prefix   │
                    │   embedding tokens    │
                    └──────────┬───────────┘
                              │
                              ▼  prefix
        ┌──────────────────────────────────────────┐
        │  Frozen base LM (Qwen 2.5-3B / Llama 3.1-8B │
        │  Instruct), LoRA adapters on q,k,v,o,        │
        │  ~25 M trainable params total                │
        │                                              │
        │   K latent reasoning steps (Coconut-style):  │
        │   h_{t+1} = LLM( concat(                     │
        │       h_t,                                   │
        │       GraphProjector(                        │
        │           SA(stimulus = pool(h_t),           │
        │              max_hops = 1,                   │
        │              top_k_seeds = 8))               │
        │       ) )    every K-th step                 │
        │                                              │
        │   Otherwise: h_{t+1} = LLM(h_t)              │
        │                                              │
        │   Stop: AdaAnchor-style stability gate or    │
        │   max_latent_steps=16 (whichever first)      │
        └──────────────────────┬───────────────────────┘
                              │
                              ▼  ~32 output latent tokens
                    ┌──────────────────────┐
                    │   MeshDecoder         │   LoRA-trained head
                    │   latent → typed      │   (~3 M params)
                    │   MutationPrimitive   │   constrained decoding
                    │   sequence            │   (sealed Pydantic union)
                    └──────────┬───────────┘
                              │
                              ▼
                       MeshDelta (Pydantic)
```

### C.2 Why this shape, in one paragraph each

**Frozen base LM, not from scratch.** Brief §7 rules out from-scratch foundation training. A 3–7 B Qwen 2.5 or Llama 3.1 with LoRA on attention projections is the smallest unit that has shown, in the 2025–2026 literature, the latent-CoT and continuous-soft-prompt behaviours we need (COCONUT scaling experiments, GNP / Q-Former projection work). I deliberately go *smaller* than the 70 B class — the MNLM will run as a service called by Nous / Oneiros / Kalypso many times per Chronik tick, and a 70 B inference budget is doctrine-violating cost-per-call territory. Pick the smallest model that crosses the latent-binding threshold (§H falsifier sets that threshold).

**GraphProjector + MeshDecoder as the only trained surfaces.** This is the minimum integration §4.5 asks for. ~33 M trainable params total (5 M projector + 25 M LoRA + 3 M decoder head); the rest is frozen. This fits the function-first cost band: a 7 B base + 33 M trainable LoRA-class adaptation can be trained on a single 80 GB H100 in 24–72 h on the Kadmos-derived dataset described in §F. No vocabulary expansion. No model-soup tricks. No alternative tokenizer.

**Substrate-resonant recurrence.** This is the only non-obvious commitment in my design. The standard COCONUT / AdaAnchor proposal is `h_{t+1} = LLM(h_t)` — the LLM iterates its own hidden state until a stability gate fires. I extend this so that every K-th step (K∈{2,3}, hyperparameter) the recurrence interleaves a *one-hop* call to the existing `TensorMeshEngine.spreading_activation` (`src/theogony/core/tensor_engine.py`) with the pooled `h_t` as stimulus, then projects the resulting top-k constellation back into the next input embedding via the same `GraphProjector`. The substrate becomes part of the model's recurrent state. **The model and the Chronik resonate.** Concretely, this means the MNLM can read a fresh Spreading-Activation result without leaving its latent-CoT loop, which is what makes "thinking with the mesh" not a metaphor. It also reuses existing infrastructure — no new substrate code — and keeps the binding interface to Kadmos and downstream LanceDB unchanged.

**Why one-hop SA inside the loop, not the full multi-hop primitive.** Inside the MNLM's recurrence, K invocations of one-hop SA are mathematically equivalent to K-hop SA from the original stimulus (the stimulus drifts each step because the LLM mutates `h_t`), but they let the model *steer* the propagation by reshaping the stimulus between hops. This is the fan-effect-aware, lateral-inhibition-aware version of Spreading Activation: the MNLM is the gate that decides which direction to push energy next. Standard multi-hop SA from a fixed stimulus cannot do this.

**MeshDecoder as constrained-decoding head, not free generation.** The decoder is a small MLP-on-residual that, given the K terminal latent tokens of the LLM, emits a sealed sequence of `MutationPrimitive` values via type-safe constrained decoding (Outlines / lm-format-enforcer style — pick the implementation later). The decoder cannot emit anything outside the sealed union defined in §E. This is the architectural feature that enforces §4.6 / §G boundary discipline at the type level: free text never becomes a possible output of the MNLM. Linter-checkable.

### C.3 Parameter count and memory profile

| Surface | Trainable params | Inference VRAM (fp16) |
|---|---:|---:|
| Frozen base LM (Qwen 2.5-3B) | 0 | ~6 GB |
| LoRA adapters (rank 16, q/k/v/o) | ~25 M | ~50 MB |
| GraphProjector | ~5 M | ~10 MB |
| MeshDecoder head | ~3 M | ~6 MB |
| **Total trainable** | **~33 M** | **~6.1 GB** |

Per call: ~6 GB VRAM, ~250 ms at K=8 latent steps with one SA-recurrence interleave on a single A10G or 4090. At Qwen 2.5-7B / Llama 3.1-8B: ~16 GB VRAM, ~600 ms per call. Both fit on a single workstation-class GPU. This is the cost band §9 of the brief asks for.

## D. I/O schema

Two complete Pydantic v2 models. Both `extra="forbid"`. They live, in implementation, at `src/theogony/agents/mnlm/dto.py`.

### D.1 `MeshInput` — the Kadmos↔MNLM contract

```python
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class MeshInputNode(BaseModel):
    """A single node in the focal subgraph the MNLM is asked to think about."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="AKA-... id, matches KnowledgeNode.id")
    embedding: list[float] = Field(min_length=1, description=(
        "Same vector that LanceDB stores. Dimensionality must match "
        "the MNLM's GraphProjector input dim (config-pinned per deployment, "
        "default 384 = bge-small-en-v1.5)."
    ))
    activation_weight: float = Field(ge=0.0, le=1.0, description=(
        "Salience signal Kadmos attaches at write time: how 'warm' was "
        "this concept in the ReadingState when emitted? For non-Kadmos "
        "callers (Oneiros pulling a constellation), this is the SA "
        "energy at the entry to the MNLM call."
    ))
    node_type_hint: Literal[
        "person","place","concept","event","claim","work",
        "organization","time","quantity","source","finding",
        "experiment","synthesis","other"
    ] = "other"
    layer: Literal["ephemera","mneme"] = "ephemera"

class MeshInputEdge(BaseModel):
    """A typed weighted edge in the focal subgraph."""
    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    relation_type: str = Field(description=(
        "P-ID, codebook entry (BINDS_TO, ...), or the connection-type "
        "string Kadmos's LLM emitted in §3.2 step B."
    ))
    weight: float = Field(ge=0.0, le=1.0)
    edge_embedding: list[float] | None = Field(default=None, description=(
        "Embedding of the connection-description sentence (Kadmos v2 §4) "
        "OR the codebook unit vector for that relation_type. Optional "
        "because the MNLM falls back to the codebook lookup if absent — "
        "Kadmos can save bandwidth by omitting it for codebook edges."
    ))
    bidirectional: bool = False

class MeshInputContext(BaseModel):
    """What the MNLM is being asked to do, as structured context — never free prose."""
    model_config = ConfigDict(extra="forbid")

    role: Literal["nous","oneiros","kalypso","custom"]
    role_config_id: str | None = Field(default=None, description=(
        "References a frozen Pydantic config the MNLM service knows; "
        "lets Nous and Oneiros share the same MNLM weights but differ "
        "in mutation budget, latent step cap, SA-interleave K, etc."
    ))
    intent_vector: list[float] | None = Field(default=None, description=(
        "Optional pooled goal vector, e.g. an Oneiros 'consolidate cluster X' "
        "stimulus or a Kalypso 'find emergence near constellation Y' stimulus. "
        "If present, prepended to GraphProjector input. None for Nous "
        "(Nous's intent is implicit in the focal subgraph)."
    ))
    mutation_budget: int = Field(default=64, ge=1, le=1024, description=(
        "Hard cap on |MeshDelta.primitives| this call may emit. Talos enforces."
    ))
    latent_step_cap: int = Field(default=16, ge=1, le=64)
    sa_interleave_K: int = Field(default=3, ge=0, le=16, description=(
        "0 disables substrate-resonant recurrence (pure Coconut mode)."
    ))

class MeshInput(BaseModel):
    """One MNLM call's complete input. Kadmos must be able to emit this directly."""
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mnlm-input/1"] = "mnlm-input/1"
    call_id: str = Field(description="ULID, mints in MNLM service or by caller.")
    nodes: list[MeshInputNode] = Field(min_length=1, max_length=512, description=(
        "Focal subgraph. 512 cap is the GraphProjector budget (§C.2). "
        "If a caller has more, they must pre-prune via SA + top-k."
    ))
    edges: list[MeshInputEdge] = Field(default_factory=list, max_length=8192)
    context: MeshInputContext
    aux: dict[str, Any] = Field(default_factory=dict, description=(
        "Layered-schema escape hatch (see §I disagreement #1). Ignored "
        "by the base MNLM; consumed by role-specialised heads when they "
        "exist. Forbids breaking changes to the core schema."
    ))
    stamped_at: datetime
```

**Why these choices, briefly.**

- The `nodes`/`edges` separation matches the existing `KnowledgeNode` / `KnowledgeEdge` shape in `src/theogony/core/model.py` exactly, so a Kadmos export and a Chronik subgraph pull both produce `MeshInput` via the same projection function. No duplicate truth.
- `activation_weight` on input nodes is the bridge between Kadmos's `active_concepts[i].activation_weight` (Kadmos v2 §3.1) and the MNLM's recurrence loop. Kadmos can emit it without contortion — it already carries it.
- `intent_vector` is optional because Nous (the first MNLM the project will build) does not need it; the focal subgraph *is* the intent. Oneiros and Kalypso benefit from it. Keeping it optional avoids forcing Nous to invent a goal vector.
- `aux: dict[str, Any]` is the explicit schema-evolution lane I argue for in §I. It is the *only* `extra` data permitted, and even it is bounded by Pydantic semantics (no nested unsealed unions; the MNLM service ignores it unless a role-specific head opts into a key).

### D.2 `MeshDelta` and `MutationPrimitive` — the output

```python
from typing import Annotated, Union
from pydantic import Discriminator, Tag

# --- Mutation primitives (sealed union via discriminator='kind') ---

class _MutationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale_embedding: list[float] | None = Field(default=None, description=(
        "Optional MNLM-internal explanation as a vector. NEVER text. "
        "Used by Athene-Light's post-hoc check, never by inter-agent comm."
    ))

class AddNode(_MutationBase):
    kind: Literal["add_node"] = "add_node"
    proposed_id: str = Field(description=(
        "AKA-... id; computed by caller via compute_node_id from "
        "(source_anchor, label_for_provenance_only). Label is allowed "
        "ONLY as provenance metadata for Athene; it is not a primary "
        "representation (see TARGET_ARCHITECTURE.md)."
    ))
    embedding: list[float] = Field(min_length=1)
    node_type: Literal[
        "person","place","concept","event","claim","work",
        "organization","time","quantity","source","finding",
        "experiment","synthesis","other"
    ]
    parent_node_ids: list[str] = Field(default_factory=list, description=(
        "When this node is a synthesis, the base nodes it abstracts over."
    ))
    label_for_provenance_only: str | None = Field(default=None, max_length=512)

class AddEdge(_MutationBase):
    kind: Literal["add_edge"] = "add_edge"
    source_id: str
    target_id: str
    relation_type: str
    edge_embedding: list[float] | None = None
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    bidirectional: bool = False

class ReviseNode(_MutationBase):
    kind: Literal["revise_node"] = "revise_node"
    target_id: str
    new_embedding: list[float] | None = None
    new_layer: Literal["ephemera","mneme"] | None = None
    revision_type: Literal["update","reweight","reclassify"]
    supersedes: bool = Field(default=True, description=(
        "True ⇒ chronicle-ledger writes a SUPERSEDED_BY edge automatically; "
        "in-place mutation is forbidden by the substrate's append-only rule."
    ))

class MergeNodes(_MutationBase):
    kind: Literal["merge_nodes"] = "merge_nodes"
    surviving_id: str
    absorbed_ids: list[str] = Field(min_length=1)
    rationale_embedding: list[float] | None = None

class SplitNode(_MutationBase):
    kind: Literal["split_node"] = "split_node"
    original_id: str
    new_nodes: list[AddNode] = Field(min_length=2)

class Invalidate(_MutationBase):
    kind: Literal["invalidate"] = "invalidate"
    target_id: str
    reason_embedding: list[float] = Field(min_length=1, description=(
        "Why this is wrong, as a vector. Athene reads this post-hoc."
    ))

class EmitFinding(_MutationBase):
    kind: Literal["emit_finding"] = "emit_finding"
    finding_type: Literal[
        "internal_contradiction","unsupported_claim",
        "echo_chamber","pheromone_autobahn","confidence_inflation",
        "structural_anomaly","other"
    ]
    target_node_ids: list[str]
    severity: Literal["info","low","medium","high","critical"] = "info"

class EmitActivationPacket(_MutationBase):
    kind: Literal["emit_activation_packet"] = "emit_activation_packet"
    deltas: list[tuple[str, float]] = Field(description=(
        "(node_id, signed_energy_delta) — pure Hebbian, no structural change. "
        "Applied by the substrate as bumps to NodeScores.relevance / "
        "KnowledgeEdge.hebbian_strength via existing batch APIs."
    ), max_length=4096)

MutationPrimitive = Annotated[
    Union[
        Annotated[AddNode, Tag("add_node")],
        Annotated[AddEdge, Tag("add_edge")],
        Annotated[ReviseNode, Tag("revise_node")],
        Annotated[MergeNodes, Tag("merge_nodes")],
        Annotated[SplitNode, Tag("split_node")],
        Annotated[Invalidate, Tag("invalidate")],
        Annotated[EmitFinding, Tag("emit_finding")],
        Annotated[EmitActivationPacket, Tag("emit_activation_packet")],
    ],
    Discriminator(lambda v: v["kind"] if isinstance(v, dict) else v.kind),
]

class MeshDelta(BaseModel):
    """One MNLM call's complete output. The substrate writes it transactionally."""
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mnlm-output/1"] = "mnlm-output/1"
    call_id: str = Field(description="Echoes MeshInput.call_id.")
    primitives: list[MutationPrimitive] = Field(
        default_factory=list,
        description="Empty list is legal (no-op call). Mutation budget enforced.",
    )
    latent_steps_used: int = Field(ge=0)
    sa_cycles_used: int = Field(ge=0)
    halted_reason: Literal[
        "stable","budget_exhausted","step_cap","decoder_eos","error"
    ]
    stamped_at: datetime
```

**Note: `DeleteNode` is not in the union.** Per `IMMUNE_SYSTEM.md`, deletion is Chronos's job, not the MNLM's. `Invalidate` is the strongest mutation an MNLM may emit.

**Note: free-text fields are systematically absent.** The single text field, `AddNode.label_for_provenance_only`, is name-marked, length-capped, and explicitly documented as not a primary representation. It exists because Athene needs *something* to grep when she samples; without it, post-hoc human audit becomes impossible. This is a pragmatic concession, not an architectural compromise.

## E. Mutation contract

The eight `MutationPrimitive` variants in §D.2 are the canonical set. Justification for what is **missing**:

- **No `DELETE_NODE` / `DELETE_EDGE`.** Chronos owns deletion (`IMMUNE_SYSTEM.md` §"T-killer cells"). The MNLM emits `Invalidate` and lets the immune system decide whether the supersession warrants hard delete much later.
- **No `RELABEL_NODE` (text-only).** A label change without an embedding change is a typographical fix, not a knowledge act. If the embedding does not change, the change is doctrine-irrelevant; if it does, `ReviseNode` already covers it.
- **No `BUMP_RELEVANCE` / `BUMP_HEBBIAN` as separate primitives.** Both are folded into `EmitActivationPacket` so the substrate applies them in a single batch update through the existing `RelevanceTracker.bump_all` / pheromone update path. One primitive, not five.
- **No `REQUEST_INGEST_SOURCE_X`.** The MNLM does not get to call Argus. If the focal subgraph is too sparse, the MNLM emits an `EmitFinding(finding_type="structural_anomaly", severity="medium")` and lets a separate orchestrator route the gap to ingestion. The principle: an MNLM's only effect is on the mesh, never on the world.

The primitives compose into a tree only via parent-of relations expressed as edges (`AddEdge` with `relation_type="ABSTRACTION_OF"` etc.). There is no "mutation transaction" or "atomic group" wrapper — the substrate is locks-free; the MNLM service applies primitives in list order and a partial failure produces a `MeshDelta.halted_reason="error"` with the prefix that did succeed kept.

## F. Training signal

I commit to **teacher-forced trajectory imitation from Kadmos itself**, plus a structural-coherence auxiliary loss. Both are shippable now.

### F.1 Primary loss — Kadmos-derived imitation

Kadmos v2 (`docs/etappes/kadmos_v2_brief.md` §3.2) already produces, every reading step, the pair we need:

- **Step input**: the prior `ReadingState` (active concepts, active connections, syntheses, open tensions) plus the hypothesis candidates from cheap parallel search. After Kadmos's internal embedding pass (`kadmos_v2_brief.md` §6.2), this is structurally identical to a `MeshInput`.
- **Step output**: the LLM's "understanding update" — `new_concepts`, `new_connections`, `confirmed_hypotheses`, `rejected_hypotheses`, `revisions`, `synthesis`, `open_tensions`. Every entry has a 1:1 mapping into a `MutationPrimitive` (`new_concepts → AddNode`, `new_connections → AddEdge`, `revisions[type=update] → ReviseNode`, `revisions[type=split] → SplitNode`, `revisions[type=merge] → MergeNodes`, `revisions[type=invalidate] → Invalidate`, `confirmed_hypotheses → EmitActivationPacket(positive)`, `rejected_hypotheses → EmitActivationPacket(negative)`, `synthesis → AddNode(node_type="synthesis", parent_node_ids=...)`).

So every Kadmos reading session of every Wikipedia article generates ~hundreds of (`MeshInput`, `MeshDelta`) pairs at zero marginal cost beyond what the project will already pay to run Kadmos. The training corpus is the Chronik's own bootstrap log.

**Loss**: standard sequence cross-entropy on the `MeshDecoder`'s constrained-decoded token sequence, plus an MSE term on `AddNode.embedding` and `AddEdge.edge_embedding` against the embeddings the Kadmos embedding pass actually emitted. The latter is what teaches the MNLM to *propose vectors*, not just *propose structures*.

### F.2 Auxiliary loss — Spreading-Activation alignment

Reuse the brief's §4.4 fourth option as a regulariser, not the primary signal: for a held-out probe set of (constellation_query_vector, expected_top_k_node_ids) pairs derived from Kadmos's own attention patterns, penalise `MeshDelta`s whose application *worsens* the SA recall on the probe set. This is the "if your write makes the substrate harder to spreading-activate, you wrote the wrong thing" loss. Weight: small (0.1–0.3 of primary), so the imitation signal dominates.

### F.3 Cost ballpark

- Corpus: 10 k Wikipedia articles → ~5 M (`MeshInput`, `MeshDelta`) training pairs. The articles already exist; Kadmos v2 needs to be run on them. At Kadmos's per-article LLM cost (estimated 0.5–2 EUR per Wikipedia article from the Kadmos v2 brief), corpus production is 5 k–20 k EUR. **This corpus is a Chronik asset regardless of MNLM training** — Kadmos was going to run it anyway.
- Adaptation training: ~33 M trainable params × 5 M pairs × 2 epochs on a single 80 GB H100 = ~48–96 GPU-hours = ~150–300 EUR at spot rates. Total marginal cost: **~300 EUR**.
- This fits the function-first cost band by an order of magnitude. The expensive thing was Kadmos, which is in flight; the MNLM is a near-free addition on top.

### F.4 Convergence signal

Stop training when both:
1. The held-out cross-entropy on Kadmos imitation has plateaued (delta < 1 % over 5 k steps), AND
2. The §H falsifier's directional-binding accuracy ≥ 90 %.

If (1) plateaus before (2) crosses 90 %, the architecture is stuck below the binding threshold and the falsifier kills the design (Stance C fallback to Stance B; see §I).

## G. Boundary text channel — and how it stays narrow

Three structurally enforced features make the §4.6 "no text inside" rule machine-checkable, not just doctrinal:

**G.1 Type-level: the `MutationPrimitive` union forbids free text.** No primitive carries an unconstrained `str` field longer than 512 chars, and the only `str` field at all (`AddNode.label_for_provenance_only`) is name-marked and length-capped. A future agent that tries to add a `RawTextNote` primitive cannot do so without editing the sealed union — which fails an import-linter rule (see G.3) and triggers a Daedalus deviation review.

**G.2 Service-level: the MNLM service exposes only `MeshInput → MeshDelta`.** No `respond_in_natural_language`, no `summarize`, no `chat_completion`. The MNLM service's `__init__.py` imports nothing from `transformers.pipelines.text_generation`; the `MeshDecoder` is the only output path. A separate package, **`theogony-debug-peephole`** (a sibling repo, not a subpackage of `theogony`), wraps `MeshDelta` into a human-readable summary on demand for development — its only job is taking a `MeshDelta` and explaining it. It exists outside the substrate path entirely.

**G.3 Repository-level: import-linter rule, enforced in CI.** Add to `pyproject.toml`:

```toml
[tool.importlinter]
[[tool.importlinter.contracts]]
name = "MNLM forbids free-text I/O at the boundary"
type = "forbidden"
source_modules = ["theogony.agents.mnlm"]
forbidden_modules = [
    "theogony_debug_peephole",
    "transformers.pipelines.text_generation",
    # extend per-deployment as needed
]
```

This is the brief's "machine-checkable contract". A `pytest -q` run that includes `import-linter` failing fails CI. Sycophantic agents who try to add a "just one little text channel" cannot do so silently.

The peephole is a real concession. During development, debugging `MeshDelta`s directly is brutal. The principle is: the peephole is *for humans during the agent's own development cycle*, not for production inter-agent communication. It is **never** allowed to be the channel by which Nous talks to Oneiros. That structural separation is the doctrine; G.3 enforces it.

## H. Empirical falsifier — the Directional Binding Benchmark (DBB-200)

### H.1 Setup

Construct 200 synthetic minimal pairs of the form `(A_i, R, B_i)` and `(B_i, R, A_i)` where `R` is one of {`LOVES`, `OWES`, `EXAMINED`, `KILLED`, `OUTRANKS`} — five directional, asymmetric relations. Examples: "John LOVES Mary" / "Mary LOVES John"; "Alice OWES Bob 100 EUR" / "Bob OWES Alice 100 EUR". Names and amounts are synthetic, drawn from a 4 k-name vocabulary, so no name pair appears in both directions.

For each pair, build a 6-node, 8-edge mini-mesh by hand (or by a deterministic synthesizer), embedding nodes with the same `BAAI/bge-small-en-v1.5` model the project uses elsewhere, and asserting the relation as a typed edge with the literal P-ID-style codebook entry for `R`.

Both directions are ingested into the substrate as separate constellations; the MNLM is queried with a `MeshInput` whose focal subgraph is the constellation, plus an `intent_vector` derived from the textual prompt "what is the direction of {R} in this constellation?". The MNLM is asked to emit one `EmitFinding` of type `structural_anomaly` if it disagrees with the asserted direction, OR an `AddEdge` with the relation reasserted in the direction the MNLM judges correct, OR `EmitActivationPacket` confirming the asserted direction.

### H.2 Metric and decision rule

Accuracy = (#correct directions identified by MNLM) / 400. The score is per-direction, not per-pair.

**Pass threshold: ≥ 95 % directional accuracy after 24 GPU-hours of LoRA adaptation on Kadmos imitation.**

- ≥ 95 %: the SR-MNLM's typed-edge-plus-latent-CoT bet for compositional binding works. Stance C in §10 holds. Build Nous on this architecture.
- 80–95 %: marginal — the architecture works on average but fails on a measurable minority. Continue, but re-weight the auxiliary SA-alignment loss and re-test. Three iterations cap.
- < 80 %: Stance C fails. Fall back to Stance B: the architecture is structurally adequate but the latent-CoT side needs a stronger language scaffold. Implication: increase `latent_step_cap`, increase model size to 7 B / 8 B, and accept that the MNLM is more text-LLM-like internally than the brief's framing wants. Or — escalate to Daedalus that the typed-edge story may not solve binding alone, and the project needs to think about Stance A/B/C choice more carefully than this brief allows.

### H.3 Why this falsifier and not an "emergent-knowledge" test

Brief §9 review criteria #3 demands one concrete experiment. The temptation is the more glamorous "Monkey 3" — does the MNLM produce knowledge not in any source? — but that test is hopelessly entangled with Kadmos quality, training distribution, and prompt design, and it cannot be run cheaply enough to be a real falsifier. Directional binding, by contrast, is **the** one test that probes whether typed-edge-plus-latent-CoT solves the Fodor binding problem in the medium the architecture commits to. It is reproducible in a few hundred GPU-hours and produces a single, defensible number. If the architecture cannot bind direction, every downstream claim about the MNLM's reasoning power is hollow.

This is the test I would lose sleep over. Other tests are nice-to-have.

## I. Risk register and honest disagreement

### I.1 Honest disagreements with the brief

**Disagreement 1 — the schema is layered, not flat.** The brief argues "the MNLM input schema is the contract; Kadmos conforms; not the reverse" (§4.1). I half-agree. The *core* schema (`MeshInput` / `MeshDelta` as defined in §D) must be MNLM-defined and Kadmos-conformant. But the brief implicitly assumes a single MNLM input shape that all role specialisations (Nous, Oneiros, Kalypso) share. That is premature unification. Oneiros may want per-cluster aging signals that Nous does not need; Kalypso may want pre-computed cross-cluster overlap statistics that neither needs. The honest design is a *layered* schema: the **core** `MeshInput` is mandatory and shared, but `MeshInput.aux: dict[str, Any]` is the structurally-isolated extension lane each role can opt into. This is what I encode in §D.1. The brief's framing risks Hesiod producing a single-shape schema that has to be broken (with migrations, with Phoenix Backlog tickets) the first time Oneiros's role-specific needs surface. Layering it from the start avoids that.

**Disagreement 2 — "no language inside" is enforceable only at module boundaries, not inside the LLM kernel.** The Coconut-style latent CoT we adopt for the MNLM still rides on a frozen pretrained text LLM whose internal residual stream is, statistically, token-shaped — the model "thinks in" something much closer to language than to vectors, even when it doesn't decode. Saying "the MNLM does not internally use language" is honest only at the *interface* level, where I enforce it (§G). Inside the residual stream, the model is doing what pretrained text LLMs do. The brief should not promise more than this; honest-failure doctrine demands we name the limit. In particular: "the MNLM doesn't think in language" really means "no module boundary the MNLM crosses carries free text". The internal medium is whatever the base LLM's residual stream happens to be. If a future MNLM is trained from scratch (out of scope for this round; brief §7), the internal medium might also become non-linguistic; until then, the kernel is text-shaped and we live with it.

**Disagreement 3 — the brief's §4.4 list is missing the obvious training signal.** §4.4 lists self-supervised graph completion, RL with structural reward, self-distillation against a frontier-LLM-with-RAG teacher, and SA-alignment. The most obvious option — *teacher-forced imitation of Kadmos's existing reading-step output* — is not listed. It is the cheapest and most natural training distribution the project has access to, because Kadmos's `ReadingStep` output is exactly an `MeshInput → MeshDelta` example. I treat this as my §F primary signal and recommend the brief's option list be amended in the next revision.

### I.2 Implementation risks

- **Risk: GraphProjector input dimensionality is fragile.** The projector is trained for one embedding dimensionality (384 for bge-small-en-v1.5). If the embedder changes, retrain projector + LoRA. Mitigation: pin the embedder per deployment in `MeshInput.nodes[i].embedding`'s validator; emit a `MnlmRunReport` anomaly if a mismatch is detected at inference.
- **Risk: the substrate-resonant recurrence compounds latency.** Each SA-interleave call costs ~5–20 ms on a small graph; with K=3 and 16 latent steps that's up to 5 SA calls per MNLM call (~25–100 ms added). On a 1 M-node Chronik this will dominate the call. Mitigation: bound `top_k_seeds=8` and `max_hops=1` inside the recurrence; do not let the MNLM call full-substrate SA from inside the loop.
- **Risk: the MeshDecoder's constrained decoding may collapse to the most common primitive.** Pure cross-entropy will over-emit `EmitActivationPacket` (the cheapest primitive). Mitigation: per-primitive frequency rebalancing in the loss, or a primitive-class-balanced sampler in training.
- **Risk: where this design breaks with current code.** It does not break with `src/theogony/core/tensor_engine.py`, `knowledge_to_mesh.py`, or `model.py`. It does require new modules under `src/theogony/agents/mnlm/` (does not exist yet) and a new `MnlmRunReport` sibling in `src/theogony/reporting/models.py`. The `MeshDelta`-to-store application path will use the existing `KnowledgeStore` batch APIs (`batch_upsert_nodes`, `batch_upsert_edges`, `batch_update_scores`) — no new write surface needed.
- **Risk: the falsifier may be too narrow.** DBB-200 tests directional binding only. It does not test temporal binding, modal binding, negation, or quantifier scope. If the MNLM passes DBB-200 but fails on temporal direction ("A happened *before* B" vs "B happened *before* A") in the wild, that is real signal of a deeper compositionality gap. Recommend: once DBB-200 is passing, build DBB-Temporal-200 and DBB-Negation-200 as follow-on falsifiers. None of them are in this round's scope.

### I.3 Doctrine conformance check

| Doctrine point | Conformance |
|---|---|
| `IMMUNE_SYSTEM.md` — no pre-gates judging content | Conforms. The MNLM has no ingest-blocking surface; `EmitFinding` is a post-hoc report, not a gate. |
| `BUILD_DOCTRINE.md` — function before polish, no human in the substrate path | Conforms. The training corpus self-generates from Kadmos; no human review queue. |
| `CHRONICLE_PRINCIPLES.md` §10 — Vector-Vector-Mesh | Conforms at the module boundary (§G); honest about the kernel's residual-stream limit (§I.1 disagreement 2). |
| `TARGET_ARCHITECTURE.md` — LanceDB + PyTorch CSR substrate | Conforms. Reuses `TensorMeshEngine` and `LanceDBKnowledgeStore` as-is. |
| `AGENTS.md` — Pydantic v2, `extra="forbid"`, RunReports mandatory | Conforms. All DTOs are `extra="forbid"`; a sibling `MnlmRunReport` is the third concrete commit (§J). |

## J. Three concrete next commits

1. `feat(mnlm): add MeshInput, MeshDelta, MutationPrimitive Pydantic v2 schemas under src/theogony/agents/mnlm/dto.py with extra="forbid", import-linter rule forbidding free-text dependencies, and round-trip tests against KnowledgeNode/KnowledgeEdge.`
2. `feat(reporting): add MnlmRunReport sibling to RunReportBase with per-call latent_steps_used, sa_cycles_used, mutation primitive counts, halted_reason, and verdict heuristics that flag mutation_budget_exhaustion as 'partial'.`
3. `feat(mnlm): scaffold GraphProjector (subgraph → 128 continuous prefix tokens) + MeshDecoder (32 latent tokens → constrained MutationPrimitive sequence) + SubstrateResonantRunner wrapping a Qwen 2.5-3B-Instruct base with rank-16 LoRA on q/k/v/o, no training in this commit — just shape, smoke test, and a minimal reproducible inference example with the in-memory store.`

## K. References

- Hao et al., **Training Large Language Models to Reason in a Continuous Latent Space (COCONUT)**. Meta FAIR, 2024. arXiv:2412.06769.
- Tian et al., **Selective Latent Reasoning (SeLaR) in Large Language Models**. 2025. arXiv:2506.* (referenced in `notes/deep_research/run11_gemini.md`; verify exact ID before citing in production).
- Wang et al., **Thinking in Latents: Adaptive Anchor Refinement for Implicit Reasoning (AdaAnchor)**. 2024–2025. arXiv:2410.* (verify).
- Tian et al., **G2GT: Graph-to-Graph Translator** (retrosynthesis). *J. Chem. Inf. Model.* 2024.
- Ma et al., **GraphGPT: Generative Pre-trained Graph Eulerian Transformer**. ICML 2024.
- **LatentMAS** — multi-agent latent communication via shared KV cache. 2025 (verify via `notes/deep_research/run11_gemini.md` table 1).
- **Cache-to-Cache (C2C / KVComm)** — KV-cache fusion for inter-model semantic transfer. 2025.
- **Graph Neural Prompting (GNP)** — soft-prompt projection for KG → frozen LLM. 2024.
- **SYNAPSE** — episodic-semantic memory via spreading activation for LLM agents. 2024–2025.
- **LLaMA-Mesh** (NVIDIA + Tsinghua, arXiv 2411.09595, Nov 2024) and **MeshLLM** (Fang et al., ICCV 2025, arXiv 2508.01242) — *cited as method-precedent for tokenising structured non-linguistic objects, not as architectural ancestor* (per brief §3.5.1).
- Hu et al., **LoRA: Low-Rank Adaptation of Large Language Models**. ICLR 2022.
- Kintsch, **Construction–Integration model of reading comprehension**. *Psychological Review*, 1988 — for the cognitive grounding of Kadmos's working-memory loop, inherited semantically by the MNLM via the §F training corpus.
- Fodor & Pylyshyn, **Connectionism and Cognitive Architecture: A Critical Analysis**. *Cognition*, 1988 — the binding-problem critique the §H falsifier directly probes.
- *Internal:* `docs/TARGET_ARCHITECTURE.md`, `docs/CHRONICLE_PRINCIPLES.md`, `docs/IMMUNE_SYSTEM.md`, `docs/BUILD_DOCTRINE.md`, `docs/etappes/kadmos_v2_brief.md`, `notes/architecture/reading_agent_vision.md`, `notes/architecture/vector_native_spreading_activation.md`, `notes/deep_research/run11_brief.md`, `notes/deep_research/run11_gemini.md`.

---

*Opus withdraws. The architecture belongs to the synthesis step.*
