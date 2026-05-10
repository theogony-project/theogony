Model: Gemini 3.1 Pro (gemini)
Date: 2026-05-10
Filed by: Gemini
Brief: docs/etappes/mesh_native_lm_research_brief.md

## A. Three-sentence summary
The proposed architecture is a Hybrid Graph Neural Prompting (GNP) model that projects continuous vector meshes into the prefix space of a frozen LLM, utilizing continuous latent-space recurrence (COCONUT-style) for intermediate reasoning to prevent language serialization. The model is trained via Latent-GRPO (Group Relative Policy Optimization) to maximize the structural compressibility and spreading-activation reachability of the output graph. Falsification rests on a cross-domain analogical reasoning task where the model must bind agent-patient directionality correctly without text syntax; failure to do so indicates that latent graph reasoning cannot support systematic compositionality.

## B. Scope statement
This artifact addresses §4.1 (Input format), §4.2 (Output format), §4.4 (Training signal), §4.5 (Adaptation path), §4.7 (Latent reasoning), and §4.8 (Mutation contract). It explicitly defers §4.3 (Inter-agent communication) to focus purely on the core reasoning step and §4.10 (Granularity) to the implementation brief.

## C. Architecture proposal
The model employs a **Soft-Prompt Projection with Latent Reasoning** architecture over a frozen base LLM (e.g., Llama-3 or Gemma).
1. **Graph Encoder:** A lightweight Graph Neural Network (GNN) projects the input mesh (node embeddings + edge topologies) into continuous soft prompts.
2. **Latent Reasoner:** The frozen LLM operates in a continuous-thought recurrence loop (COCONUT). It feeds its final hidden state back into itself, gating the recurrence via selective entropy monitoring (SeLaR) to prevent premature collapse into greedy token paths.
3. **Graph Decoder:** The LLM emits specialized latent structural tokens which a trained decoder head translates into discrete graph mutations (the `MeshOutput`).

This approach requires adapting only the encoder and decoder heads while freezing the multi-billion-parameter LLM body, keeping the parameter count band for adaptation < 1B parameters and maintaining a low memory profile compatible with standard serving infrastructure.

## D. I/O schema
```python
from typing import Literal, Union
from pydantic import BaseModel, ConfigDict, Field

class KadmosNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., description="Node ID, matching Chronik rules.")
    embedding: list[float] = Field(..., description="Semantic vector from Kadmos.")
    node_type: str = Field(..., description="Semantic type of the node.")

class KadmosEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    target_id: str
    relation_type: str
    edge_vector: list[float] | None = None
    weight: float = Field(ge=0.0, le=1.0)

class MeshInput(BaseModel):
    """The binding contract for what Kadmos v2 must produce post-embedding."""
    model_config = ConfigDict(extra="forbid")
    nodes: list[KadmosNode]
    edges: list[KadmosEdge]
```

## E. Mutation contract
The MNLM operates on the Chronik via typed mutation primitives. Deletions are forbidden.
```python
class AddNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutation_type: Literal["ADD_NODE"] = "ADD_NODE"
    id: str
    embedding: list[float]
    node_type: str

class AddEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutation_type: Literal["ADD_EDGE"] = "ADD_EDGE"
    source_id: str
    target_id: str
    relation_type: str
    edge_vector: list[float] | None = None
    weight: float = Field(ge=0.0, le=1.0)

class ReviseNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutation_type: Literal["REVISE_NODE"] = "REVISE_NODE"
    target_id: str
    new_embedding: list[float]

class Invalidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutation_type: Literal["INVALIDATE"] = "INVALIDATE"
    target_id: str
    reason_embedding: list[float]

class EmitFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutation_type: Literal["EMIT_FINDING"] = "EMIT_FINDING"
    finding_embedding: list[float]
    involved_node_ids: list[str]

class EmitActivationPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutation_type: Literal["EMIT_ACTIVATION_PACKET"] = "EMIT_ACTIVATION_PACKET"
    node_energy: dict[str, float]

MeshMutation = Union[AddNode, AddEdge, ReviseNode, Invalidate, EmitFinding, EmitActivationPacket]

class MeshOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutations: list[MeshMutation]
```

## F. Training signal
The model is trained via **Trajectory-based RL with structural reward (Latent-GRPO)**.
- **Loss/Reward:** The reward function evaluates the generated `MeshOutput` by simulating Spreading Activation on the updated mesh. High rewards are given if the mutations significantly increase the reachability of target nodes (efficiency) without collapsing graph entropy (diversity).
- **Data:** Bootstrapped synthetic trajectories from Kadmos v2 embeddings running through a teacher Oracle (frontier LLM with text RAG).
- **Cost Band:** Low-to-moderate. RL fine-tuning targets only the adapter weights (~100s of GPU hours, <$5k per convergence run).

## G. Boundary channel
Text I/O is structurally blocked from internal agent reasoning. The `MeshInput` and `MeshOutput` schemas exclusively use continuous floats (`list[float]`) and discrete typed identifiers (`str` IDs, `relation_type`). There is no `text` or `content` string field in the mutation contract. A separate, strictly external "translation peephole" module exists solely for developer debugging, which maps node embeddings back to Kadmos source anchors. The MNLM network graph itself has no text-decoding LM head in its active forward pass.

## H. Empirical falsifier
**The Sub-Linguistic Algebra Test (Curse of Two-Hop Reasoning)**
- **Dataset:** A synthetic vector mesh encoding 10,000 instances of directional, asymmetric relationships (e.g., "A orbits B", "X devours Y").
- **Metric:** The model must traverse the mesh to answer directional queries ("What does X devour?") outputting the correct target node embedding without relying on language tokens.
- **Decision Rule:** If the MNLM fails to distinguish between the agent and patient vectors at a rate significantly better than chance—while a text-serialized baseline LLM succeeds—the design is falsified. This proves the continuous latent space cannot bind relational directionality natively.

## I. Risk register
1. **Premature Collapse in COCONUT:** Continuous latent steps may rapidly collapse into the most probable deterministic token representation, destroying the superposition required for graph synthesis.
2. **Kadmos Contract:** If Kadmos cannot reliably produce high-fidelity `KadmosNode` embeddings without storing text snippets for downstream reference, the `MeshInput` strict continuous requirement will cause fatal information loss.
3. **Disagreement with the Brief:** The brief posits that typed edges might suffice for binding (Stance A). I disagree. Typed edges represent static structure, but *dynamic* reasoning requires maintaining binding across intermediate states. Therefore, Latent CoT (Stance C) is mandatory to hold agent-patient relations in working memory.

## J. Three concrete next commits
1. `feat(model): add MeshInput and MeshOutput Pydantic v2 schemas in src/theogony/core/model.py`
2. `feat(gnp): implement lightweight Graph Neural Prompting encoder for MeshInput`
3. `feat(decoder): implement latent structural token decoder mapping to MeshMutation primitives`

## K. References
- Meta FAIR (2024). *Training Large Language Models to Reason in a Continuous Latent Space*. arXiv:2412.06769.
- Zhang et al. (2024). *SeLaR: Selective Latent Reasoning in Large Language Models*. arXiv:2410.01234.
- Fang et al. (2025). *MeshLLM: Primitive-Mesh Decomposition*. arXiv:2508.01242.
- Fodor, J. A., & Pylyshyn, Z. W. (1988). *Connectionism and cognitive architecture: A critical analysis*. Cognition, 28(1-2), 3-71.

## L. Deepest Question Stance
**Stance C — neither works alone; the MNLM is intrinsically dual.**
A vector subgraph with typed edges acts as a highly efficient associative storage and retrieval layer (System 1). However, typed edges alone cannot perform dynamic compositional binding during multi-hop reasoning. The language model *must* engage in latent Chain-of-Thought (continuous recurrence) to serve as the working memory that systematically binds agent and patient logic over time (System 2). The systematicity of thought arises not from the static mesh, but from the network's ability to hold and transform continuous relational anchors across sequential hidden states.
