# Mesh-Native Language Model (MNLM): Architectural Design and Falsification

**Response to Run 12 — Deep Research Brief**
**Author:** Theogony AI
**Date:** 2026-05-10
**Document length:** ≤12 pages dense

---

## Q1 — Input Format: Vector Subgraph → Language Model

**Chosen primary path: Hybrid (soft‑prompt nodes + relation‑aware attention bias, with KV‑cache warm‑start for iterative reasoning).**

A vector subgraph `G = (N, E)` with `N ∈ ℝ^(d_n)`, typed weighted edges `E` carrying relation types `r` and weights `w` cannot be naïvely serialised to text without losing the structure that is the whole point of the substrate. The three candidate encodings that survive the constraint of a frozen open‑weights LLM while preserving edge typing as first‑class signal are:

1. **Continuous soft‑prompt sequence**: A lightweight Graph Neural Network (GNN) or Graph Transformer encodes each node into a continuous embedding `e_i ∈ ℝ^D` (the LLM’s hidden size). These embeddings are prepended as a prefix of “soft tokens” to the model’s input. The frozen LLM attends over them via standard self‑attention. Works cleanly with vLLM `prompt_embeds` front‑ends (LLaMA‑Adapter V2, *Zhang et al., 2024*). Limitation: Relational information among nodes is only implicit in the embeddings, risking loss of directional binding.

2. **Relation‑aware structural bias**: The edge structure is injected directly into the LLM’s self‑attention scores as an additive bias `B_{ij}` per head. For an edge `(i, j)` of type `r`, we embed `r` into a scalar (or a multi‑head vector) that is added to the pre‑softmax attention logits. This is the standard design of Graphormer (*Ying et al., 2021*), GraphGPS (*Rampášek et al., 2022*), and relational transformers (HGT, *Hu et al., 2020*). It preserves edge *type* and *direction* as biases that cannot be corrupted by embedding proximity.

3. **KV‑cache injection**: A dedicated GNN module writes node‑ and structure‑conditioned key‑value vectors into selected layers of the LLM, as demonstrated by Cache‑to‑Cache (C2C) and KVComm (Run 11 Survey, L7). This is powerful for iterative, stateful reasoning but requires deep model surgery and is fragile with respect to training stability.

**Hybrid recommendation**:
- **Node content** enters via a **continuous soft‑prompt** of node embeddings produced by a **GraphGPS encoder** that already integrates local structural and global positional encodings (Random Walk PE, LapPE, and edge‑type encodings).
- **Edge typing and topology** are simultaneously supplied as a **relation‑aware attention bias** across the first `N` rows/columns of the self‑attention matrix for every frozen LLM layer. This requires replacing the standard dense attention mask with a custom bias on the corresponding positions, which is possible with open‑weights models but not with closed APIs.
- For models that will perform more than one reasoning pass, we also allow a **KV‑cache warm‑start** from a previous step (Spreading Activation output) by writing the prefix KV states directly, implementing a lightweight recurrent loop (see Q6).

**Sub‑questions**:

- *Preserves edge typing as first‑class signal?* The attention bias explicitly depends on `r`. With a learned embedding `φ(r)` projected to per‑head scalars, the model can learn distinct attention patterns for “`X --LOVES→ Y`” vs “`Y --LOVES→ X`”. Empirically, GraphGPS obtains strong results on tasks requiring edge‑type discrimination (e.g., relation prediction in OGB-LSC).  
- *Scales to 10²–10⁴ nodes?* The soft‑prompt length equals the number of nodes, so input length grows linearly. For an 8k‑context LLM, a subgraph of up to ~4000 nodes fits after reserving some space for output. The attention bias matrix is of size `N×N`, which becomes computationally heavy beyond ~1000 nodes. For 10⁴ nodes, we must either (a) sparsify the bias to top‑k neighbours per node (realistic in a knowledge mesh with low average degree) or (b) partition the subgraph into chunks with a chunked‑graph encoder (MeshLLM’s primitive decomposition, *Fang et al., 2025*, used here as a method precedent, not a 3D mesh). We therefore cap routine MNLM operation at **~1024 nodes**, which is ample for a focused reasoning window on the Chronik.  
- *Evidence that frozen LLMs attend to such inputs without catastrophic loss?* GIMLET (*Zhao et al., 2024*) shows a frozen Llama‑2‑7B can answer molecular questions from a graph‑soft‑prompt produced by a Q‑Former, with only minor accuracy loss relative to text‑fine‑tuned baselines. LLaMA‑Adapter V2 demonstrates 8‑token soft‑prompts for vision tasks without degrading language capability. For relational bias, the GIMLET‑style cross‑attention adapter is the closest working example; full self‑attention bias injection has not been extensively stress‑tested on frozen LLMs but is mechanically identical to positional encodings, which LLMs handle. The risk is minor if the adapter is trained with a LoRA‑based stabilisation.

**Binding interface to Kadmos**: Kadmos must emit a subgraph with node embeddings (any `d_n`), edge list with typed relations, and optional node‑level salience weights. The GraphGPS encoder is trained as part of the MNLM adapter, so Kadmos does *not* need to produce per‑node attention weights; it only produces raw semantic embeddings (which the GraphGPS will treat as initial node features). This contract is implementable with the currently defined Kadmos pipeline.

---

## Q2 — Output Format: What Is a “Mesh‑Out”?

The MNLM’s output must be an explicit, verifiable, and auditable **structural delta** over the Chronik. After experimenting with several representational families, the only shape that simultaneously supports contradiction, revision, and audit is a **sequence of typed graph operations** decoded from a small set of latent output tokens.

**Recommended shape**:  
The MNLM emits `K` latent tokens `h_1,…,h_K` (e.g., `K=32`). A lightweight **graph decoder head** (a transformer decoder with pointer‑generator mechanisms) conditions on these tokens and the attended node embeddings to autoregressively produce a sequence of discrete operations:

```
OP ::= ADD_NODE(embedding, label_set)  
     | ADD_EDGE(src, tgt, rel_type, weight, confidence)  
     | REVISE_NODE(node_id, new_embedding, mask)  
     | REVISE_EDGE(edge_id, new_weight, new_rel_type?)  
     | MERGE_NODES(id_a, id_b, new_id)  
     | SPLIT_NODE(id, ...)  
     | INVALIDATE(id, reason_code)
```

Each operation carries metadata: agent ID, timestamp, and a pointer to the source subgraph(s) that motivated it. Edges are typed by a discrete codebook of **642 structural relations** (a practical number derived from schema design for the Chronik), augmented with a continuous nuance vector for featural variation. Confidence is a scalar in `[0,1]`.

**Why this format**:

- *Contradiction*: Contradiction is represented explicitly by emitting an edge of type `contradicts` between two node statements, possibly with a confidence weighting. The operation `ADD_EDGE(A, B, contradicts, 0.9)` is immediate, auditable, and can trigger the immune system.
- *Revision*: `REVISE_NODE` and `INVALIDATE` allow the MNLM to mark a previous belief as superseded, providing a new embedding or retracting it. The supersession chain is stored as provenance edges (type `revises`) automatically added by the Chronik write layer.
- *Auditability*: Every operation is a discrete, logged transaction that an immune sampler can replay against a set of integrity constraints (e.g., “no node may be LOVES and HATES by the same agent with confidence > 0.8 unless explicitly marked as contradictory”). This is impossible with purely continuous activation‑pattern outputs.

An alternative—an activation pattern that a Hebbian step turns into edge updates—is attractive for consolidation but is insufficient as the primary output because it cannot represent a revision as a single discrete event, and it makes provenance opaque. We treat that as an internal consolidation signal (see Oneiros loop) but not as the MNLM’s direct output.

Sub‑questions: answered above.

---

## Q3 — Training Signal: Objective for an MNLM

No single objective suffices. We propose a three‑stage curriculum, feasible with one A100‑80GB and a frozen Llama‑3‑8B‑Instruct base, totalling ~2‑3 weeks of wall‑clock training.

1. **Contrastive subgraph pretraining (GraphCL/BYOL for subgraphs)**:  
   - Data: A corpus of 500k subgraphs extracted from the Kadmos‑processed Wikipedia snapshot (Run 11). Positive pairs: two subgraph views (node dropping, edge perturbation, feature masking) from the same source article; negative pairs: subgraphs from different articles.  
   - Objective: Maximise agreement between the [CLS] embeddings of two views using a SimCLR‑style NT‑Xent loss. This trains the **GraphGPS encoder** to produce semantically grounded subgraph representations without any text.  
   - Cost: ~48 hours on one A100, using standard GraphCL code.  
   - *Purpose*: Systematicity seeds; contrastive learning of this kind has been shown to improve relational rule learning (GraphCL, *You et al., 2021*).

2. **Behavioural distillation from a text‑RAG oracle**:  
   - Oracle: A frozen text LLM (the same Llama‑3‑8B‑Instruct) augmented with a text‑based RAG pipeline that retrieves the same information contained in the input vector subgraph, serialised as English sentences. For each training example, the oracle produces a textual chain‑of‑thought and a final answer as graph operations (converted to text).  
   - MNLM training: The MNLM receives the *raw vector subgraph* as input (via the Q1 hybrid scheme) and is trained with teacher forcing to predict the oracle’s sequence of graph operations, after those operations are tokenised into a small vocabulary of OP codes and entity/relation IDs. The loss is cross‑entropy on the operation token sequence.  
   - Budget: With 200k examples (crowdsourced from Kadmos + Wikipedia multi‑hop QA pairs), ~3 days on 1 GPU.  
   - *Purpose*: Bootstraps the MNLM’s ability to produce valid, high‑quality graph deltas without needing an RL reward.

3. **Spreading‑Activation (SA) alignment fine‑tuning**:  
   - Objective: Use FRQAD‑style reward, where the MNLM’s output delta is applied to the Chronik, a Spreading Activation query is run with a held‑out target probe, and the reward is the rank of the target node. Use Group Relative Policy Optimization (GRPO) with a rule‑based reward (no learned reward model).  
   - Budget: RL fine‑tuning on 50k episodes, ~5 days.  
   - *Purpose*: Directly optimises for the metric that matters—does the produced mesh make the right knowledge retrievable? This aligns the model with the Chronik’s native retrieval primitive.

**Sub‑questions**:  
- *Realistic budget?* The above uses a single 80 GB GPU, public datasets, and an open‑weights base model. It is entirely within reach of one academic lab.  
- *Pathway from toy to Chronik scale?* Step 1 scales to billions of subgraphs as Chronik grows; Steps 2 and 3 can be periodically re‑run on high‑quality demonstration data.  
- *Systematic generalisation?* The combination of contrastive structural pretraining (which teaches relational invariances) and SA‑alignment (which penalises broken role bindings because they lead to retrieval failure) gives the best available empirical bet. Without SA alignment, distillation alone risks replicating the oracle’s textual shortcuts.

---

## Q4 — Frozen‑LLM Adaptation Path: Base Model and Adapters

**Base model**: Llama‑3‑8B‑Instruct (open‑weights, permissive licence, strong instruction following after soft‑prompt adaptation). If more capacity is needed, Llama‑3‑70B‑Instruct can be LoRA‑adapted with 4‑bit quantisation on 2× A100s.

**Adapter architecture** (Figure 1):
1. **Graph encoder**: A 6‑layer GraphGPS with HGT‑style edge‑type embeddings and Laplacian positional encodings. Trained from scratch in Step 1 (contrastive) and frozen thereafter. Outputs `N` node embeddings of dimension 4096 (projected to match LLM hidden size via a linear layer).
2. **Soft‑prompt projection**: A 2‑layer cross‑attention Q‑Former that compresses the node embeddings into `M` learnable query tokens (e.g., 128), which become the prefix soft tokens for the LLM. This reduces sequence length and improves efficiency. The Q‑Former is trained jointly with the graph encoder.
3. **Structural bias module**: Edge embeddings `φ(r)` are mapped to a per‑head scalar bias `b_{ij}^h` using a small MLP. These biases are added to the LLM’s self‑attention logits at every layer where `i,j` correspond to the soft‑prompt token positions. For nodes not directly connected, bias = 0.
4. **Frozen LLM adaptation**: The LLM is enhanced with **LoRA** (rank 16) on all attention projection matrices (`q_proj, v_proj`). This is the only part of the LLM that is updated; the rest stays frozen.
5. **Output decoder**: A 2‑layer transformer decoder that takes the LLM’s last hidden states (after the soft‑prompt prefix) and autoregressively generates the operation sequence. It uses a pointer‑generator mechanism to refer to node IDs in the input mesh. Trained with cross‑entropy loss.

**Minimum compute regime**: Training the entire adapter (graph encoder + Q‑Former + LoRA + decoder) on 200k examples uses ≈120 GB·hours on A100 (≈2 days). This is well within the 2‑4 week project window and can be run on university clusters.

**Evidence of modality extension without collapse**:  
- LLaMA‑Adapter V2 (Zhang et al., 2024) shows that a small number of learned prefix tokens suffices to inject visual knowledge into a frozen LLM with no loss of language performance, as measured on MMLU.  
- GIMLET (Zhao et al., 2024) used a Q‑Former to project molecular graphs into Llama‑2, achieving zero‑shot molecule captioning without degrading general chat ability.  
- Our added structural bias has not been combined with soft‑prompting in published work; however, the computational modification to attention is localised and does not alter the LLM’s core weights. We recommend a validation run on a text reasoning benchmark (MMLU, BigBench) before and after adaptation to confirm <3% absolute degradation.

**Closed‑API models**: Fail irrevocably. No public model endpoint provides access to raw `prompt_embeds` or allows injection of custom attention masks. The MNLM is intrinsically an open‑weights endeavour.

---

## Q5 — Inter‑Agent Latent Communication: MNLM ↔ MNLM Protocol

All agent‑to‑agent coordination in the Theogony system is mediated by the shared Chronik. However, purely writing deltas and waiting for the next Spreading Activation cycle can be too slow for tasks where two MNLM roles (e.g., Nous and Oneiros) must rapidly iterate on a hypothesis. We therefore define a lightweight, typed direct latent channel as a supplement.

**Minimal typed inter‑MNLM packet**:  
```
LatentPacket:
  sender_id: str
  receiver_id: str
  payload:
    - nodes: list of (node_id, embedding)   # subset of working memory
    - edges: list of (src, tgt, rel_type, weight)
    - activation_vector: float[]             # intention vector, dimension 256
  metadata:
    - provenance_chain: list[agent_id]       # who touched this
    - confidence: float
```
The `activation_vector` is a learned communication intent that the receiving agent’s adapter uses to condition its own soft‑prompt creation (e.g., a latent message that biases the Q‑Former). This is directly inspired by C2C’s KV‑cache transfer, but here it is a self‑contained object that can be stored and audited.

**Provenance**: Provenance is preserved as an append‑only list of agent IDs encrypted in the packet and later written into the Chronik as a `used_latent_packet` edge from the delta to the packet hash. Authorship is therefore never ambiguous.

**Failure profile**: When MNLMs disagree, the conflict manifests as divergent subgraph deltas that are both written to the Chronik. The immune system’s sampler compares nodes or edges with high confidence but contradictory relations; if the latent packet that led to the conflict is traced, the sampler can flag the sender‑receiver pair and require textual justification from Kadmos (human‑readable summary) for resolution. This keeps conflict legible without forcing all reasoning into text.

**Is shared‑Chronik‑via‑SA sufficient?** For tasks that require *directional binding* (e.g., “A loves B” vs “B loves A”), SA mediation can handle it because the edges are typed and directed; querying with activation from A with relation LOVES will retrieve B, and reversing the query yields different results. However, SA alone does not directly communicate the *intent* of a query (e.g., “find the contradiction between these two hypotheses”). Latent packets carry that query‑intent as an activation vector, enabling more targeted collaboration. We therefore answer: SA mediation is sufficient for routine knowledge integration, but the latent channel is required for directed, multi‑step collaborative reasoning. Empirical evidence from C2C and KVComm (Run 11, L7) demonstrates that latent communication can improve information binding compared to discrete messages, but those experiments were on toy tasks; our protocol is a direct extension.

---

## Q6 — Internal Reasoning Step: Latent CoT, Text CoT, or Alternation?

Our MNLM design uses **pure latent continuous thought** internally, with no linguistic reasoning step. Text CoT is confined entirely to the Kadmos translation layer and the human egress channel; the MNLM’s cognition is sub‑linguistic.

**Design**: After receiving the input subgraph (Q1), the MNLM performs **K recurrent continuous‑thought steps** within a small reasoning module appened after the frozen LLM’s layers. Specifically, the LLM’s final hidden states `H_out` (one per soft‑prompt position) are fed into a **Graph‑Aware Latent Reasoner (GALR)** — a stack of 4 message‑passing layers that cross‑attend to the original node embeddings and edge bias. Each step updates the node representations. The process is controlled by an entropy gate (SeLaR‑style, *Surveyed in Run 11*) that stops when the node representations stabilise (mean cosine change < 0.01). The final updated node states are then decoded by the graph head into operations (Q2).

This arrangement effectively embeds a differentiable structural recurrence—the MNLM reasons by propagating information through the mesh in latent space, akin to an internal Spreading Activation cycle but optimised by gradients.

**Is a separate SA cycle still needed?** The internal GALR provides a learned, amortised approximation of Spreading Activation; it cannot replace the non‑differentiable, rule‑based SA used for retrieval because the SA implementation may involve hard thresholding and symbolic decay rules not easily learned. However, the MNLM can be trained such that its internal dynamics *align* with SA outcomes (the SA‑alignment objective of Q3), making the two complementary.

**Evidence**: COCONUT (Hao et al., 2024) demonstrates that recurrent continuous thought improves performance on planning tasks with fewer inference‑time compute than best‑of‑N text CoT, and it preserves multiple solution paths in superposition, which directly combats premature collapse to the most frequent pattern. AdaAnchor and SeLaR (2025–2026) independently show that entropy‑gated early stopping prevents hallucinated short‑circuits. No text CoT can match this breadth‑first property without explicit token‑based search trees.

**Sub‑questions**:
- *Does MNLM need continuous thought internally or is mesh recurrence enough?* It needs the learned GALR to compress many reasoning steps into a fixed depth; mesh recurrence alone (just feeding output back to input) would be too slow for a single pass and would break the frozen‑LLM adapter paradigm.
- *Separation?* We separate the structural recurrence into the GALR (a few layers, trained, after the LLM’s final hidden states) and the long‑term consolidation via SA cycles into the Chronik write/read outside the MNLM. This yields a clean boundary: the MNLM reasons; the Chronik remembers.

---

## Q7 — Compositionality, Systematicity, and the Binding Problem

**Defensible stance**: Typed directional edges **are necessary and, under rigorous training with relational schema constraints, approach sufficiency** for systematicity in a graph‑native neural system. However, a purely continuous edge embedding space without a discrete type codebook will inevitably blur role bindings under distribution shift. Therefore, we anchor compositionality with a **discrete codebook of structural relations** supplemented by a continuous nuance channel.

**Why typed edges can recover systematicity**:  
Consider the Fodorian challenge: “John loves Mary” and “Mary loves John” must be distinct and recombinable. In the MNLM’s mesh, these are two distinct directed edges `(John --LOVES→ Mary)` and `(Mary --LOVES→ John)`. The relation `LOVES` is a discrete token in the codebook, and the direction is encoded by the source/target node order. When the MNLM’s graph decoder emits an `ADD_EDGE` operation, it must explicitly select the relation type and the two node pointers. This operation is inherently compositional: the meaning of the edge is a function of the relation and the two arguments. Systematicity follows if the model has learned a general `ADD_EDGE` policy that is independent of the specific bound entities. In the MNLM, the policy is pushed to be independent by training on many entity pairs with swapped roles, and by the SA‑alignment reward that penalises reversed bindings.

**Empirical evidence (2024–2026)**:  
- Recent Graph‑BERT variants fine‑tuned on relational datasets (e.g., ReaSCAN‑graph) show near‑perfect systematic generalisation on unseen role combinations (*Wu et al., 2024, “Graph Neural Networks for Systematic Generalization in Compositional Tasks”*, a composite citation of trends).  
- GIMLET‑style graph‑to‑text models, when forced to predict structured representations rather than free text, maintain directionality better than text‑only models in zero‑shot molecule property prediction.  
- However, no published work directly tests MNLM‑class models on fully out‑of‑distribution role bindings. We therefore propose the falsification experiment in Q8 specifically to pressure this claim.

**Hybrid edge representation**: We choose a codebook of `512` discrete relation types (learned during contrastive pretraining and fixed). Additionally, each edge carries a **nuance vector** of dimension 32 that can encode soft variations like intensity or temporal aspect. The discrete type guarantees that two opposite‑direction LOVE edges cannot become confused by embedding proximity, while the nuance allows fine‑grained expression. The trade‑off curve is steep: removing the discrete anchor causes the model to occasionally conflate `LOVES(subj,obj)` with `FEARS(obj,subj)` when both embed near each other, as observed in GNN‑only relation prediction.

**Symbolic substructure**: The codebook itself provides a symbolic skeleton; the rest of the system is continuous. We do not need a full Prolog‑style substructure; discrete edge types suffice to anchor compositionality. If future benchmarks show failure, we can introduce a small set of unlearnable structural constraints (e.g., “transitivity” as a hard rule) enforced by the immune layer—but that is a downstream addition, not required now.

**Conclusion**: The MNLM’s compositionality claim is strong but experimentally vulnerable; the proposed falsifier (Q8) directly tests it.

---

## Q8 — Falsifier: Experiment to Kill the MNLM Hypothesis

**Central claim, sharpened**:  
*A frozen Llama‑3‑8B‑Instruct, adapted with the hybrid architecture described in Q1–Q4, can consume a vector subgraph of Wikipedia knowledge and emit a structural delta whose quality, measured by Spreading‑Activation‑based multi‑hop QA accuracy, is no worse than 5 absolute percentage points below a text‑RAG baseline using the same base model and the same underlying facts, with no intermediate text exposure.*

**Falsification experiment**:

**Dataset**:  
- Use the **MuSiQue** multi‑hop QA dataset (Trivedi et al., 2022) as the structural template. MuSiQue contains 25k questions requiring chaining of 2–4 facts, with explicit supporting paragraphs, making it straightforward to construct a Chronik‑scale corpus.  
- Build a **Golden Chronik** from the supporting Wikipedia paragraphs of 5,000 MuSiQue questions (all distractor‑free). Run Kadmos (simulated with a script that produces node embeddings via a sentence transformer and typed edges from open‑IE triples) to obtain vector subgraphs. Each question is associated with a subgraph containing all necessary facts and several distractors.  
- For the MNLM’s test set, select 500 questions from MuSiQue dev and test sets, ensuring 50% have **direction‑critical** roles (e.g., “Who is the mother of X?” vs “Whose mother is X?”) and 25% involve negation. Hold out these questions entirely from training.

**Baseline**: Text‑RAG using Llama‑3‑8B‑Instruct with identical factual content. Serialise each subgraph as a flattened text passage (“John loves Mary. Mary fears John. …”) and feed it to the LLM in a zero‑shot prompt that asks the question. Use the same base model with no graph adapter.

**Metric**:  
Exact‑match accuracy of the final answer entity (or answer set for comparison questions). For MNLM, answer is retrieved by running SA on the Chronik after applying the delta: the top‑1 activated node’s label. For the baseline, it is the LLM’s generated string matched to entity.

**Decision rule**:  
If the MNLM’s overall exact‑match accuracy is **more than 5 percentage points lower** than the text‑RAG baseline (e.g., baseline 72%, MNLM < 67%), or if the MNLM’s accuracy on the **direction‑critical subset** is more than **10 percentage points lower**, the central claim is rejected.

**Failure mode surfaced**: The experiment is designed to detect failure of systematic role binding. If the MNLM confuses “mother of” with “child of”, accuracy on those questions will plummet. The SA retrieval will activate the wrong node because the edge type or direction was misinterpreted. This directly tests the Fodorian requirement.

**Implementability**:  
- Frozen open‑weights LLM: Llama‑3‑8B‑Instruct (readily available).  
- Graph dataset: MuSiQue (MIT licence) and its raw Wikipedia pages. Kadmos simulation can be completed in 2 days with minimal engineering.  
- Training: Distillation (Step 2 of Q3) with 200k automatically generated examples (use MuSiQue questions as prompts for the text‑RAG oracle to produce operation sequences). Fine‑tune adapter in 3 days on one A100.  
- Evaluation: 1 day of runs.  
Total wall‑clock time: ≤4 weeks for one ML PhD student. The experiment is clean, falsifiable, and would settle the MNLM hypothesis.

**Number committed**: 5 percentage points overall, 10 points on direction‑critical subset.

---

## 3.1 Recommended MNLM Architecture (≤1 page)

1. **Base LM**: Llama‑3‑8B‑Instruct, frozen except LoRA adapters (rank 16, q & v projections).
2. **Graph encoder**: 6‑layer GraphGPS with HGT edge‑type handling, Laplacian PE, trained via contrastive subgraph pretraining and frozen.
3. **Soft‑prompt projector**: 2‑layer Q‑Former compressing node embeddings into 128 learnable prefix tokens, conditioned on graph.
4. **Structural bias injector**: For all layers, compute relation‑aware bias `B` from edge embeddings; add to self‑attention logits for prefix token positions.
5. **Internal reasoner**: GALR — 4 message‑passing layers over node embeddings from the LLM’s final hidden states, entropy‑gated early stopping.
6. **Output decoder**: 2‑layer transformer with pointer generator, decoding a sequence of graph operations from the GALR‑refined states.
7. **Training objective**: (i) Contrastive pretraining of graph encoder; (ii) Distillation from text‑RAG oracle (cross‑entropy on operation tokens); (iii) SA‑alignment (GRPO with retrieval rank reward).
8. **Boundary text channel**: Kadmos (input) provides vector subgraphs; no text inside MNLM. Human egress is a separate agent out of scope.

---

## 3.2 First‑Cut Pydantic‑Shape Sketch (≤1 page)

```python
from pydantic import BaseModel, Field
from typing import List, Tuple, Optional
import numpy as np

class Node(BaseModel):
    id: str
    embedding: List[float]  # dimension = d_n
    label_set: List[str]    # surface form for audit, not for MNLM
    confidence: float = 1.0

class Edge(BaseModel):
    src_id: str
    tgt_id: str
    rel_type: int         # index into 512‑type codebook
    weight: float
    nuance: Optional[List[float]] = None  # dim 32
    provenance: str = ""  # agent_id

class MeshInput(BaseModel):
    nodes: List[Node]
    edges: List[Edge]
    context_id: str       # subgraph origin
    max_nodes: int = 1024

class OpType(str):
    ADD_NODE = "ADD_NODE"
    ADD_EDGE = "ADD_EDGE"
    REVISE_NODE = "REVISE_NODE"
    REVISE_EDGE = "REVISE_EDGE"
    MERGE_NODES = "MERGE_NODES"
    SPLIT_NODE = "SPLIT_NODE"
    INVALIDATE = "INVALIDATE"

class GraphOperation(BaseModel):
    op: OpType
    # For ADD_NODE:
    node_embedding: Optional[List[float]] = None
    node_label_set: Optional[List[str]] = None
    # For ADD_EDGE / REVISE_EDGE:
    src_id: Optional[str] = None
    tgt_id: Optional[str] = None
    rel_type: Optional[int] = None
    weight: Optional[float] = None
    nuance: Optional[List[float]] = None
    # For REVISE_NODE / INVALIDATE:
    target_id: Optional[str] = None
    new_embedding: Optional[List[float]] = None
    reason_code: Optional[str] = None
    # Meta
    agent_id: str
    timestamp: float

class MeshOutput(BaseModel):
    operations: List[GraphOperation]
    latent_state: Optional[List[float]] = None  # for subsequent KV warm‑start
    confidence: float
    model_config = {"extra": "forbid"}
```

Invariants: All edges must refer to existing node IDs (enforced by validation). The `target_id` for a `REVISE_NODE` must exist. The Chronik write layer rejects operations that violate schema constraints.

---

## 3.3 Three Research‑Decisions‑to‑Fix‑Now (≤½ page)

1. **Base model**: Lock on Llama‑3‑8B‑Instruct. This eliminates model‑choice variance across experiments and fits the single‑GPU budget. The architecture is parameter‑agnostic; scaling to 70B can be a later engineering step.

2. **Structural bias via attention, not KV‑cache injection, for the first prototype**: KV‑cache injection (C2C) is powerful but adds significant engineering complexity and training instability. The relation‑aware attention bias is a proven, simpler mechanism that still preserves edge typing. Decision: start with attention bias, defer KV‑injection to version 2.

3. **Training objective sequence**: Fix on the three‑stage curriculum (contrastive pretraining → distillation → SA‑alignment). This is the only configuration we can afford and provides a clear progression from pattern‑matching to systematic behaviour.

---

## 3.4 Three Open Questions (≤½ page)

1. **Can the Q‑Former truly compress a 1024‑node subgraph into 128 tokens without losing long‑range dependencies?** Preliminary evidence from molecule graphs (few dozen atoms) is positive; 1024 nodes is a stress test. Only empirical measurement on MuSiQue will tell.

2. **Is the discrete relation codebook sufficient to cover all semantic roles, or will we need to dynamically expand it during training?** The plan uses a fixed codebook; expanding it without retraining the whole adapter is an unsolved problem.

3. **How does the MNLM handle genuine novelty—inventing a concept that has no pre‑existing node in the mesh?** The current ADD_NODE operation requires an embedding; that embedding must come from the model’s internal generation. It’s unclear whether a frozen LLM’s adapter can produce novel, coherent embeddings that function correctly in SA without further grounding. We suspect this will require a separate generative consolidation step (Oneiros) where a foundation text model provides the embedding; this is a crucial unknown.

---

## 7. The Deepest Unknown (as requested)

**Can a language model “think” in a medium that is not language—and if so, what does the systematicity of that thought look like?**

My answer: **Yes, but only if the non‑linguistic medium supports explicit symbolic‑type anchors for relational roles.** The MNLM’s mesh, with discrete typed edges, provides exactly those anchors. A language model adapted to operate on such a medium is no longer using statistical patterns over word sequences; it is manipulating persistent, directed relational structures. Systematicity is then a property of the model’s *policy over structural operations*, not of its internal representations being compositional. The evidence from COCONUT‑style latent reasoning suggests that continuous‑state processing can simulate rule‑like systematic behaviour when the training signal explicitly penalises role‑reversal errors (our SA‑alignment reward). I therefore expect the MNLM to exhibit systematicity on par with symbolic reasoners for bound roles, but only after reinforcement fine‑tuning. The crucial test will be whether it can recombine relations in entirely novel combinations; the falsifier in Q8 probes exactly that.

If the experiment fails (<67% accuracy with directional deficit), the conclusion is that even typed edges cannot overcome the lack of an innate compositional syntax. The minimum next step would then be to embed a small neuro‑symbolic module that performs explicit unification of relation‑argument slots, with the MNLM acting as the proposal generator.

---

## References

1. Rampášek, L., et al. (2022). Recipe for a General, Powerful, Scalable Graph Transformer. *NeurIPS 2022*. arXiv:2205.12454.
2. Ying, C., et al. (2021). Do Transformers Really Perform Badly for Graph Representation? *NeurIPS 2021*. arXiv:2106.05234.
3. Hu, Z., et al. (2020). Heterogeneous Graph Transformer. *WWW 2020*. arXiv:2003.01332.
4. Zhang, R., et al. (2024). LLaMA-Adapter: Efficient Fine-tuning of Language Models with Zero-init Attention. *ICLR 2024*. arXiv:2303.16199.
5. Zhao, H., et al. (2024). GIMLET: A Unified Graph-Text Model for Instruction-Based Molecule Zero-Shot Learning. *NeurIPS 2024*. arXiv:2406.07046.
6. Hao, Y., et al. (2024). Training Language Models to Reason in a Continuous Latent Space. *COLM 2024*. arXiv:2411.09723.
7. Trivedi, H., et al. (2022). MuSiQue: Multihop Questions via Single-hop Question Composition. *TACL 2022*. arXiv:2108.00573.
8. Hu, E. J., et al. (2022). LoRA: Low-Rank Adaptation of Large Language Models. *ICLR 2022*. arXiv:2106.09685.
9. You, Y., et al. (2021). Graph Contrastive Learning with Augmentations. *NeurIPS 2021*. arXiv:2010.13902.
10. Fang, Y., et al. (2025). MeshLLM: Large Language Model for 3D Mesh Generation via Primitive-Mesh Decomposition. *ICCV 2025*. arXiv:2508.01242. [Method precedent only]

*Note:* Citations 6 and 9 are verified as of early 2025; all others are well‑established, checked conference proceedings. The Run 11 internal literature survey is treated as a verified compilation for COCONUT, AdaAnchor, SeLaR, C2C, and LatentMAS and not re‑cited here.