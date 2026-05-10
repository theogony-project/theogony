Model: Codex 5.3 (`codex`)
Date: 2026-05-10
Filed by: Codex
Brief: `docs/etappes/mesh_native_lm_research_brief.md`

## A) Three-sentence summary

I propose a **dual-medium MNLM (Stance C)**: typed-edge mesh operations are the durable reasoning substrate, while a bounded latent recurrence loop inside a frozen 7B-8B LLM handles compositional binding before emitting structural deltas.  
The training signal is **Spreading-Activation alignment**: the model is rewarded when its proposed mesh mutations improve downstream activation trajectories for held-out probes, rather than when it predicts text tokens.  
The design is falsified if, on a directional-binding benchmark, it cannot beat a token-serialized graph baseline on directed edge F1 and activation target ratio under equal compute.

## B) Scope statement

### Addressed

- `4.1` input format and Kadmos contract
- `4.2` output format
- `4.4` training signal
- `4.5` frozen-LLM adaptation path
- `4.6` boundary text channel isolation
- `4.7` latent reasoning step
- `4.8` mutation contract
- `4.10` trigger/scope/budget/commit boundary

### Explicitly left to others

- `4.3` inter-agent transport protocol details (I only specify the packet shape)
- `4.9` long-horizon persistent working memory policy across Oneiros/Kalypso cycles
- full optimizer/hyperparameter sweep policy for production training

## C) Architecture proposal

### C.1 Model class

`MNLM-CX` (Codex proposal) is a **frozen decoder LLM + mesh adapters + structural decoder**:

1. **Backbone:** frozen open model in the 7B-8B class (target: Qwen/Llama family, BF16 inference).
2. **Input adapter:** relational graph encoder (2-3 layers, edge-type aware) that turns `MeshInput` into:
   - continuous prefix embeddings (content signal),
   - sparse topology bias tensor (edge signal).
3. **Latent reasoning loop:** 2-8 recurrent latent steps before decode; no free-prose intermediate.
4. **Output heads:** emit typed mutation objects (`ADD_EDGE`, `REVISE_NODE`, etc.) with vectors/weights/confidences.

This keeps the LM frozen, moves mesh competence into thin trainable components, and preserves a direct path to current Theogony primitives (`KnowledgeNode`, `KnowledgeEdge`, SpMV retrieval).

### C.2 Adaptation path (smallest shippable integration)

- **Phase 1 (ship):** frozen 7B backbone + LoRA on attention blocks + mesh prefix adapter + structured mutation head.
- **Phase 2:** add latent recurrence gate (confidence/entropy controlled) and activation packet emission.
- **Phase 3:** optional KV-injection for warm-start cross-cycle reasoning.

### C.3 Parameter/memory band

- Backbone: 7B-8B frozen params.
- Trainable params:
  - LoRA adapters: ~20M-60M (rank dependent),
  - mesh adapter + decoder heads: ~40M-90M.
- Total trainable band: ~60M-150M.
- Serving memory (single model, BF16 + KV cache + adapters): roughly 18-28 GB VRAM for 2k-4k effective context and ~2k node windows (batched by subgraph windows).

### C.4 Control-plane shape (`4.10`)

- **Trigger:** event-driven on new Kadmos writes and scheduled Oneiros/Kalypso windows.
- **Scope:** one bounded `MeshInput` subgraph (max node/edge budgets in DTO).
- **Budget:** explicit `hop_budget`, `mutation_budget`, and per-call write caps.
- **Commit boundary:** one `MeshOutput` equals one append-only transaction candidate; partial failures still emit run reports.

## D) I/O schema (binding contract)

`MeshInput` is the Kadmos->MNLM contract. `MeshOutput` is the MNLM->substrate contract.

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Vector384 = Annotated[list[float], Field(min_length=384, max_length=384)]


class MeshNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(pattern=r"^(AKA|TMP|UUID)-[A-Za-z0-9_-]{6,}$")
    embedding: Vector384
    layer: Literal["ephemera", "mneme"]
    activation: float = Field(ge=0.0, le=1.0, description="Current activation energy.")
    confidence: float = Field(ge=0.0, le=1.0)
    revision_depth: int = Field(ge=0, le=64)
    source_anchor: str = Field(
        min_length=1,
        description="URL+timestamp or stable source identifier; no source text payload.",
    )


class MeshEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str = Field(pattern=r"^(EDGE|TMPEDGE)-[A-Za-z0-9_-]{6,}$")
    source_id: str = Field(pattern=r"^(AKA|TMP|UUID)-[A-Za-z0-9_-]{6,}$")
    target_id: str = Field(pattern=r"^(AKA|TMP|UUID)-[A-Za-z0-9_-]{6,}$")
    relation_type: str = Field(
        pattern=r"^(P[0-9]+|BINDS_TO|REINFORCES|CAUSED_BY|ABSTRACTION_OF|MODULATES|CONTRADICTS|UNKNOWN)$"
    )
    weight: float = Field(ge=0.0, le=1.0)
    hebbian_strength: float = Field(ge=0.0)
    relation_embedding: Vector384 | None = None


class MeshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    role: Literal["nous", "oneiros", "kalypso", "generic"]
    embedding_model_id: str = Field(min_length=1)
    nodes: list[MeshNode] = Field(min_length=1, max_length=4096)
    edges: list[MeshEdge] = Field(default_factory=list, max_length=200000)
    active_node_ids: list[str] = Field(min_length=1, max_length=512)
    query_vector: Vector384 | None = None
    hop_budget: int = Field(ge=1, le=6)
    mutation_budget: int = Field(ge=1, le=256)
    max_new_nodes: int = Field(default=32, ge=0, le=256)
    max_new_edges: int = Field(default=256, ge=0, le=4096)
    allow_boundary_text: bool = Field(
        default=False,
        description="Must remain false for internal MNLM calls.",
    )

    @model_validator(mode="after")
    def validate_graph_integrity(self) -> "MeshInput":
        node_ids = {n.node_id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("nodes must have unique node_id values")
        if not set(self.active_node_ids).issubset(node_ids):
            raise ValueError("active_node_ids must be a subset of nodes[].node_id")
        for edge in self.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError("each edge endpoint must exist in nodes")
        return self


class OutputVerdict(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class MeshOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    produced_at: datetime
    verdict: OutputVerdict
    operations: list["MeshMutation"] = Field(default_factory=list, max_length=4096)
    activation_packet: "ActivationPacket | None" = None
    failure_reason_code: str | None = None
```

### D.1 Invariants and units

- Embeddings are fixed-width 384 floats (aligns with current default embedding surface).
- `weight`, `confidence`, `activation` are unit interval `[0,1]`.
- `nodes` must be ID-unique; `active_node_ids` and edge endpoints must resolve inside the same input.
- No field in `MeshInput`/`MeshOutput` carries raw source text.

## E) Mutation contract

Canonical mutation set keeps doctrine constraints (`no delete`) and composes with append-only writes.

```python
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Vector384 = Annotated[list[float], Field(min_length=384, max_length=384)]


class BaseMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale_embedding: Vector384 | None = None
    created_at: datetime


class AddNodeOp(BaseMutation):
    op: Literal["ADD_NODE"] = "ADD_NODE"
    node_id: str
    embedding: Vector384
    layer: Literal["ephemera", "mneme"] = "ephemera"
    source_anchor: str


class AddEdgeOp(BaseMutation):
    op: Literal["ADD_EDGE"] = "ADD_EDGE"
    edge_id: str
    source_id: str
    target_id: str
    relation_type: str
    weight: float = Field(ge=0.0, le=1.0)
    relation_embedding: Vector384 | None = None


class ReviseNodeOp(BaseMutation):
    op: Literal["REVISE_NODE"] = "REVISE_NODE"
    target_node_id: str
    supersedes_node_id: str
    new_embedding: Vector384
    revision_kind: Literal["update", "reinterpretation", "confidence_shift"]


class MergeNodesOp(BaseMutation):
    op: Literal["MERGE_NODES"] = "MERGE_NODES"
    source_node_ids: list[str] = Field(min_length=2, max_length=16)
    merged_node_id: str
    merged_embedding: Vector384


class SplitNodeOp(BaseMutation):
    op: Literal["SPLIT_NODE"] = "SPLIT_NODE"
    source_node_id: str
    child_node_ids: list[str] = Field(min_length=2, max_length=16)
    child_embeddings: list[Vector384] = Field(min_length=2, max_length=16)


class InvalidateOp(BaseMutation):
    op: Literal["INVALIDATE"] = "INVALIDATE"
    target_node_id: str
    finding_code: Literal["contradiction", "unsupported", "stale", "schema_conflict"]


class EmitFindingOp(BaseMutation):
    op: Literal["EMIT_FINDING"] = "EMIT_FINDING"
    finding_node_id: str
    finding_type: str
    target_node_ids: list[str] = Field(default_factory=list)


class EmitActivationPacket(BaseMutation):
    op: Literal["EMIT_ACTIVATION_PACKET"] = "EMIT_ACTIVATION_PACKET"
    packet_id: str
    node_energies: dict[str, float] = Field(default_factory=dict)


class ActivationPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str
    role: Literal["nous", "oneiros", "kalypso"]
    node_energies: dict[str, float] = Field(default_factory=dict)
    topological_focus_ids: list[str] = Field(default_factory=list)


MeshMutation = Annotated[
    AddNodeOp
    | AddEdgeOp
    | ReviseNodeOp
    | MergeNodesOp
    | SplitNodeOp
    | InvalidateOp
    | EmitFindingOp
    | EmitActivationPacket,
    Field(discriminator="op"),
]
```

Notes:

- `DELETE_*` is intentionally absent.
- `INVALIDATE` and `EMIT_FINDING` are first-class for immune-system interoperability.
- `REVISE_NODE` is supersession, never in-place overwrite.

## F) Training signal

### F.1 Committed signal: Spreading-Activation alignment

Train the MNLM to propose `MeshMutation` deltas such that **post-mutation Spreading Activation** better matches desired activation trajectories for probe targets.

### F.2 Objective

- Let `G` be input subgraph, `ΔG` the proposed mutation set, `A_post = SA(G ⊕ ΔG, q)` the post-update activation distribution.
- Training target `A*` is generated from held-out structural truth (masked edges, known cross-level links, contradiction annotations).
- Primary loss: `KL(A* || A_post)` on top-N target and distractor nodes.
- Small regularizers:
  - mutation sparsity penalty (avoid uncontrolled graph inflation),
  - directional consistency penalty (agent/patient reversals),
  - invalid-edge penalty (endpoints missing in scope).

### F.3 Data and cost band

- Data source: Kadmos outputs + Chronicle slices from public corpora (Wikipedia-first), windowed into bounded subgraphs.
- Initial scale: 100k-300k training windows, 5k validation windows.
- Compute band (QLoRA + frozen 7B): roughly 300-900 GPU-hours (A100 class), low four-figure EUR on commodity rental.

### F.4 Convergence signal

Stop when all hold over 3 eval sweeps:

1. Activation target recall@k plateaus (<1% gain),
2. Directed-edge F1 stabilizes (delta <0.5 points),
3. Contradiction-path false positives do not worsen.

## G) Boundary text channel

### Allowed text boundary

Text is allowed only in two explicit adapters:

1. **Ingress adapter (Kadmos):** text -> mesh.
2. **Debug/egress mirror:** mesh fragment -> short human-readable summary.

### Structural non-leak enforcement

- Core MNLM service only accepts/returns `MeshInput`/`MeshOutput`.
- Internal DTO contract forbids free-form text fields (IDs/enums only).
- Agent-to-agent handoff uses `ActivationPacket`, never prose.
- Boundary mirror runs as a separate interface and is read-only relative to mesh writes.

This is machine-checkable at type level and runtime schema validation; it is not policy-by-convention.

## H) Empirical falsifier

### Experiment: Directional Binding Stress Test (falsifies Stance C if it fails)

**Goal:** test whether the proposed MNLM preserves compositional binding better than token-serialized graph baselines.

**Dataset**

- Build a benchmark of 20k-50k bounded subgraphs with directional relations and inverses:
  - causal (`CAUSES` vs reverse),
  - temporal (`BEFORE` vs `AFTER`),
  - role-bound (`agent` vs `patient`) patterns.
- Source from public structured corpora + synthetic perturbations over Kadmos-style graph slices.

**Compared systems**

1. Proposed MNLM-CX (mesh adapter + latent loop + mutation head).
2. Eulerian-token baseline (flatten graph to tokens, same backbone class).

**Metrics**

- Directed edge F1 on newly proposed structural edges.
- Activation Target Ratio (ATR): mean activation on intended targets / inverse confounders after applying deltas and running SpMV retrieval.
- Structural validity rate (schema-valid, scope-valid mutations).

**Decision rule (falsifier)**

The design is falsified if **either**:

- Directed edge F1 is not at least +5 points over baseline, **or**
- ATR < 1.25 on the held-out split, **or**
- structural validity < 99% under constrained budgets.

Failing any condition means the architecture does not justify mesh-first complexity over flattened-token alternatives.

## I) Risk register

1. **Store compatibility risk:** current `LanceDBKnowledgeStore.load_into_tensor_engine` builds ad-hoc relation codebooks at load time, which conflicts with stable relation semantics expected by MNLM mutation heads.
2. **Schema gap risk:** `MeshInput` expects fixed-width embedding consistency and explicit budgets; current Kadmos outputs are richer semantically but not yet locked to one strict mesh DTO.
3. **Runtime integration risk:** practical `prompt_embeds`/adapter serving path is not yet standardized in existing query/ingest pipelines.
4. **Reporting gap risk:** no dedicated `MnlmRunReport` sibling yet for mutation-level diagnostics and verdict semantics.
5. **Quality drift risk:** without careful mutation sparsity penalties, the model can inflate edge count faster than useful signal density.
6. **Doctrinal risk:** any downstream team may reintroduce synchronous correctness gates around MNLM writes; this would directly violate immune-system doctrine and should be rejected.
7. **Disagreement declared:** the brief is correct that Kadmos should conform to MNLM input schema, but in practice this should be implemented as a staged compatibility window (adapter + strict mode), not a one-shot cutover.

## J) Three concrete next commits

1. `feat: add mnlm dto module with MeshInput MeshOutput and sealed mutation union`
2. `feat: add kadmos_to_mnlm adapter and strict schema validation path with run reports`
3. `test: add directional binding falsifier benchmark harness and activation alignment eval`

## K) References

1. Hu et al. (2021). **LoRA: Low-Rank Adaptation of Large Language Models**. arXiv:2106.09685.  
2. Li and Liang (2021). **Prefix-Tuning: Optimizing Continuous Prompts for Generation**. arXiv:2101.00190.  
3. Li et al. (2023). **BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and Large Language Models** (Q-Former). arXiv:2301.12597.  
4. Dettmers et al. (2023). **QLoRA: Efficient Finetuning of Quantized LLMs**. arXiv:2305.14314.  
5. Kwon et al. (2023). **Efficient Memory Management for Large Language Model Serving with PagedAttention (vLLM)**. arXiv:2309.06180.  
6. Ying et al. (2021). **Do Transformers Really Perform Bad for Graph Representation? (Graphormer)**. arXiv:2106.05234.  
7. Hu et al. (2020). **Heterogeneous Graph Transformer**. arXiv:2003.01332.  
8. Rampasek et al. (2022). **Recipe for a General, Powerful, Scalable Graph Transformer (GraphGPS)**. arXiv:2205.12454.  
9. Siddiqui et al. (2024). **MeshGPT: Generating Triangle Meshes with Decoder-Only Transformers**. arXiv:2311.15475.  
10. LLaMA-Mesh (NVIDIA + Tsinghua, 2024). **Text-token mesh generation baseline**. arXiv:2411.09595.  
11. Fang et al. (2025). **MeshLLM**. arXiv:2508.01242.  
12. Collins and Loftus (1975). **A Spreading-Activation Theory of Semantic Processing**. Psychological Review.  
13. Anderson (1996). **ACT: A Simple Theory of Complex Cognition**. American Psychologist.
