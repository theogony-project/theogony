# Mesh-Native Language Model — Architecture Brief

> **Realignment status (2026-05-13):** this brief was filed on 2026-05-10, three days before the MESH-substrate pivot. The **core architectural commitments survive the pivot unchanged**: Llama-3-8B + LoRA, Graph-KV input, Latent Flow Matching output, Substrate-Resonant Recurrence, Spreading-Activation alignment via Graph-GRPO, three-stage falsifier (DBB-200 → MuSiQue → Monkey-3). What has been re-aligned in this realignment pass: §3.5 edge typing (codebook → MESH-doctrine edge descriptors), §4.1 / §4.2 Pydantic schemas (single embedding → multi-vector nodes, `layer` → `consolidation_tier`, AKA-IDs → ULIDs, codebook IDs → relation descriptors), §5 training references (Gen-1 store paths → MESH runtime paths), §7 Kadmos contract (re-anchored to the MESH eager-linking discipline), §8 sprint roadmap (re-anchored as the body of Migration-Plan Step S5 — depends on S1–S4 having landed first), §13 PoC-pass (executed pre-pivot under Gen-1 doctrine; results preserved in `docs/research/mnlm/poc_legacy/`; the post-pivot PoC track is `docs/research/mnlm/poc_mesh/`). Sections not edited are §0, §1, §2, §3.1–§3.4, §3.6, §6, §9, §10, §11, §12 — they were doctrinally compatible already.

**Status:** BINDING architecture decision for the Mesh-Native Language Model. Partially research work — sections explicitly marked **[RESEARCH]** remain open and are resolved during implementation, not before.

**Filed by:** Hesiod (architect) — 2026-05-10. Realigned to MESH doctrine 2026-05-13.
**Inputs:** the five Round-1 research artifacts in docs/research/mnlm/{opus,codex,gemini,deepresearch,DeepSeek}.md plus the verified literature floor (Graph-KV, LatentRxnFlow, Graph-GRPO, Attention-as-Binding).
**Operative doctrine:** [MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md), [MESH_IMPLEMENTATION.md](../MESH_IMPLEMENTATION.md), [MESH_RETRIEVAL.md](../MESH_RETRIEVAL.md), [MESH_MIGRATION_PLAN.md](../MESH_MIGRATION_PLAN.md). The MESH triplet is operative for substrate-layer behaviour, runtime, and use; the migration plan sequences this brief's implementation as the body of Step S5. Older doctrine kept as context: [TARGET_ARCHITECTURE.md](../TARGET_ARCHITECTURE.md) (the architectural floor), [BUILD_DOCTRINE.md](../BUILD_DOCTRINE.md), [IMMUNE_SYSTEM.md](../IMMUNE_SYSTEM.md), [CHRONICLE_PRINCIPLES.md](../CHRONICLE_PRINCIPLES.md), [AGENTS.md](../../AGENTS.md).
**Supersedes:** [mesh_native_lm_research_brief.md](mesh_native_lm_research_brief.md) as the operative MNLM document. The research brief remains as the question source; this document is the answer.
**Hand-off target:** Talos, once Migration-Plan Steps S1–S4 have landed. The "three concrete next commits" list in §10 is then the Step-S5 Sprint-1 candidate set.

---

## 0. Framing — this brief refuses to compromise

Theogony is not building a graph-augmented LLM. It is building the substrate beneath AI systems — a knowledge mesh where meaning lives as vectors and weighted edges, where raw source text is not the retrieval primitive, and where reasoning happens **in** the substrate, not over a serialised representation of it. The Mesh-Native Language Model is the cognitive primitive that makes this real. (Per the MESH triplet that this brief was realigned to: short, regenerable summary metadata — node descriptions, edge relation descriptors, source-anchor URLs — *is* permitted as agent-readable annotation in the substrate; what is forbidden is raw source text as retrieval payload. The MNLM's input and output schemas in §4 honour this rule.)

The temptation in any architecture-decision brief is to choose the smallest, most-precedented path forward — to ship something fast and grow it later. **Hesiod refuses this temptation here.** The MNLM as architecturally watered down to "GNP soft prompts + discrete mutation tokens + COCONUT-style latent CoT" is *just a slightly fancier RAG agent*. It works. It ships. It is not what the project is building.

The five Round-1 artifacts and the verified Round-12 literature floor give us — for the first time — the technical permission to build the actual MNLM rather than the conservative compromise. This brief takes that permission.

What this means in practice:

- The architecture commits to **Graph-KV** for input, not GNP soft prompts. Topology becomes a first-class signal in attention itself, not a flattened prefix.
- The architecture commits to **Latent Flow Matching with a Graph-Autoencoder reconstruction head** for output, not discrete mutation-token sequences. Contradiction, revision, and uncertainty become native mathematical features of the output trajectory.
- The architecture commits to **Substrate-Resonant Recurrence** as the *default*, not an A/B-testable optional. The MNLM and the Chronik share recurrent state; that is the architectural definition of "thinks in the mesh".
- The architecture commits to **Spreading-Activation alignment via Graph-GRPO** as the primary RL training signal, with Kadmos-imitation as a one-pass warmup. The substrate is the teacher.
- The architecture commits to a **three-stage falsifier** that ends with a Monkey-3 emergent-knowledge test, the empirical validation of the project's central thesis.

Sections marked **[RESEARCH]** remain open and are resolved during implementation, with explicit research checkpoints at week 4, 8, and 12. That is not an architecture-decision flaw; it is the appropriate epistemic state for a project committing to a radically new design. Hesiod's job here is not to eliminate uncertainty — it is to lock the *shape* of the answer space and let the experiment resolve the parameters.

---

## 1. What Hesiod inherits from Round 1

Five artifacts; their consolidation into Hesiod's decisions:

| Artifact | Standout contribution(s) Hesiod adopts | What Hesiod overrides |
|---|---|---|
| `opus.md` | **Substrate-Resonant Recurrence**, **Kadmos-imitation as warmup-training data source**, three-layer boundary enforcement (type-level + service-level + import-linter), layered `MeshInput` with role-specific `aux` lane | "discrete mutation tokens" (4-of-5 consensus) — overridden in favour of Latent Flow Matching |
| `codex.md` | `model_validator(mode="after")` graph-integrity check, the cleanest Pydantic discipline of the round, edge endpoint validation, validation-failure failure modes | "GNP soft prompts as primary input path" — overridden in favour of Graph-KV |
| `gemini.md` | Stance C as the explicit, named position (typed edges AND latent CoT, both necessary, neither sufficient alone) | Insufficient design depth elsewhere; not load-bearing beyond Stance C confirmation |
| `deepresearch.md` | **Graph-KV input mechanism**, **Latent Flow Matching output mechanism**, **Graph-GRPO RL training**, VSA-binding-head theoretical framing | "VSA binding heads as primary v1 mechanism" — deferred to v2 research; the theoretical foundation (Dhayalkar 2025) is real but unvalidated at scale |
| `DeepSeek.md` | Falsifier decision rule (5-point overall + 10-point on direction-critical subset), the 3-stage curriculum framing for training, the most calibrated honesty about open unknowns | "GNP + relation-aware attention bias only" — overridden in favour of Graph-KV (which subsumes the attention-bias mechanism) |

Cross-artifact consensus that locks immediately, with no further decision needed:

1. **Frozen base model in the 7–8 B class** (Llama-3-8B-Instruct selected — see §3.1), LoRA-adapted on attention projections, never trained from scratch.
2. **The 8-primitive mutation contract**: `ADD_NODE`, `ADD_EDGE`, `REVISE_NODE`, `MERGE_NODES`, `SPLIT_NODE`, `INVALIDATE`, `EMIT_FINDING`, `EMIT_ACTIVATION_PACKET`. The MNLM does not emit hard-delete primitives — destruction at the substrate level is decided by the agent-driven cleanup discipline in [MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md) §"Agent-driven cleanup" (Argus, Athene, Chronos roles) and by Oneiros's pathology / therapy loop (§"Pathology and therapy"). The MNLM emits `Invalidate` and `EmitFinding`; the system decides post-hoc whether the supersession warrants demotion or removal, always with audit-ledger entries.
3. **No raw source text inside the MNLM module boundary.** Enforced at three independent layers (Pydantic union shape; service interface; repo-level import-linter contract). Short summary metadata (a node's `description`, an edge's `relation_descriptor`, a source-anchor's `source_url`) is permitted and matches the MESH-substrate field discipline — these are agent-readable annotations, not the retrieval surface.
4. **Stance C** on the systematicity question (§9.1) — typed edges *and* latent CoT, both necessary, neither sufficient alone.
5. **The falsifier's primary axis is directional binding** (the Fodor / Pylyshyn challenge). The architecture stands or falls on whether typed edges + latent CoT + Substrate-Resonance preserve agent-patient direction across multi-hop reasoning.

These five do not need to be debated again. The remaining decisions are §3.
---

## 2. Verified literature floor — what Hesiod can actually build on

The four key citations that drove `deepresearch.md`'s ambitious architecture have been verified against arXiv and OpenReview. All four exist and are real publications. Their applicability to the MNLM differs:

| Paper | Citation | Verdict for MNLM | Used by Hesiod for |
|---|---|---|---|
| **Graph-KV: Breaking Sequence via Injecting Structural Biases into Large Language Models** | Wang et al., NeurIPS 2025, arXiv:2506.07334. Code: `Graph-COM/GraphKV`. | **Real, with public reference implementation.** Existing application is to citation networks and RAG — not arbitrary knowledge meshes — so adaptation work is required, but the core mechanism (KV-cache as condensed segment representation; graph-structured block masks; positional-encoding sharing across source/target segments) directly fits the MNLM. | §3.2 input mechanism — adopted as **primary**, not as v2 option. |
| **Driving Reaction Trajectories via Latent Flow Matching (LatentRxnFlow)** | Shen & Zhang, arXiv:2602.10476. | **Real, but domain is chemistry / retrosynthesis.** The mechanism (Graph-Autoencoder backbone + Conditional Flow Matching + ODE-based inference) is general; the demonstration that it transfers to general semantic-mesh deltas is the **research bet** of Hesiod's output choice (§3.3). The trajectory-level diagnostics and intrinsic uncertainty signals are domain-independent properties. | §3.3 output mechanism — adopted with **[RESEARCH]** flag. The Talos roadmap §8 includes a fallback path. |
| **Graph-GRPO: Stabilizing Multi-Agent Topology Learning via Group Relative Policy Optimization** | arXiv:2603.02701, Tsinghua + Donghua. | **Real, but the application is multi-agent communication topology**, not mesh-delta synthesis. The math (group sampling + relative reward + edge-level credit assignment) generalises directly; the specific reward shape needs to be re-engineered around Spreading-Activation alignment. | §5.2 RL stage — adopted as the GRPO variant of choice. |
| **Attention as Binding: A Vector-Symbolic Perspective on Transformer Reasoning** | Dhayalkar, arXiv:2512.14709, AAAI 2026. | **Real, but a theory paper.** Proposes "explicit binding/unbinding heads", "hyperdimensional memory layers", VSA-inspired training objectives. None empirically validated at scale; no reference implementation. | §9.1 [RESEARCH] open question. Provides the *language* in which we describe what Substrate-Resonance has to achieve, but is not a load-bearing implementation choice in v1. |

**Interpretation.** Graph-KV is the only one of the four that is engineering-precedent. The other three are theoretical/transfer claims. That is enough for Hesiod to commit, *with eyes open*: the MNLM is genuinely new architectural work, and the [RESEARCH] flag on §3.3 (LFM output) and §9.1 (VSA binding heads) is honest acknowledgement, not hedge.
---

## 3. The locked architecture

### 3.1 Base model and adapter class

**Locked: Llama-3-8B-Instruct, frozen, with rank-16 LoRA on `q_proj`, `k_proj`, `v_proj`, `o_proj` only.**

Rationale:

- 7–8 B is the smallest scale at which the post-2024 latent-CoT and graph-prompt literature documents stable behaviour. Smaller models (3 B class) are likely to fail the §6 falsifier's directional-binding threshold; 70 B class is doctrine-violating cost-per-call territory and is reserved for a possible Oneiros-class deployment, not the base MNLM service.
- Llama-3-8B-Instruct is open-weights with a permissive licence, exposes the internal layers needed for Graph-KV attention-mask injection, and is the most-replicated base model in the 2025–2026 graph-prompting literature (LLaMA-Adapter V2, GIMLET, GNP all use Llama-class bases).
- LoRA on q/k/v/o keeps trainable params at ~25 M; combined with the GraphProjector (~5 M) and the LFM/GAE decoder head (~10 M, see §3.3), total trainable surface is ~40 M. This fits a single 80 GB H100 for both training and inference.

Closed-API models (GPT, Claude, Gemini) are explicitly out. Hesiod confirms `deepresearch.md` §2.4's statement: closed APIs prohibit the runtime injection of soft prompts, prohibit the structural manipulation of attention masks required for Graph-KV, and prohibit the extraction of un-decoded last-layer hidden states required for Latent Flow Matching. Without open weights, the MNLM degenerates into RAG.

### 3.2 Input mechanism — Graph-KV as primary

**Locked: hybrid Graph-KV + Graph-Neural-Prompting projection. Graph-KV provides the structural attention mask; GNP provides the continuous content projection of node features.**

The naive "soft prompt + frozen LLM" path (LLaMA-Adapter / GNP-only) flattens the topology into a prefix sequence. The MNLM must do better than that, because the brief's whole point is that edges are first-class signal. Graph-KV (NeurIPS 2025) gives us the mechanism:

- **Per-node KV prefill.** Each node in the input subgraph is encoded by a GraphGPS-class encoder (with HGT-style edge-type embeddings and Laplacian positional encoding), then projected into the LLM's hidden dimension. The result is N node-level KV pairs prefilled into selected layers of the LLM.
- **Graph-structured block-mask attention.** Attention is restricted by the subgraph's adjacency: a target segment attends only to the KV caches of its source segments per the graph topology. This sparsifies the attention matrix and emulates a message-passing step natively inside the transformer's self-attention layers — without modifying the LLM's weights.
- **Positional-encoding sharing.** Source segments share a positional range [0, L); target segments share [L, 2L). This deliberate overlapping neutralises the "lost in the middle" positional bias and prevents context-window exhaustion as subgraph size grows.
- **Edge-type as continuous attention bias.** The edge embeddings (from the GraphGPS encoder, optionally enriched with the connection-description embedding from Kadmos) project into a per-attention-head bias added to the logits before softmax. This is the GNP-content channel. Without it, edge typing is approximated; with it, the model attends differently to "A LOVES B" vs "A FEARS B" by construction.

What this gives us that GNP alone cannot:

- **First-class structural signal at every layer**, not only at the embedding-projection stage.
- **Linear scaling in nodes**, not in (nodes × context) — the block-mask makes each node attend only to its graph neighbourhood, not to all preceding tokens.
- **Edge typing preserved as orthogonal directions in attention space**, not as proximity in flattened embedding space.

Cap for v1: subgraphs up to ~1024 nodes per call. Above that, the substrate's pre-call Spreading-Activation primitive prunes to top-1024 by relevance (existing `TensorMeshEngine` capability, no new code). This is sufficient for any focused reasoning window the project will run in v1.

The Graph-COM/GraphKV reference implementation is the integration starting point for Talos. It targets citation networks and RAG; the adaptation to general semantic meshes is the engineering work in §8 weeks 3–6.

### 3.3 Output mechanism — Latent Flow Matching with Graph-Autoencoder reconstruction **[RESEARCH]**

**Locked: Latent Flow Matching trajectory + Graph-Autoencoder reconstruction head + Pydantic-constrained `MeshDelta` packaging. Discrete-mutation-token fallback specified in §8 week 8 if LFM training proves unstable.**

This is the most ambitious commitment in this brief, and it is marked **[RESEARCH]**. The mechanism is from chemistry (LatentRxnFlow); its transfer to general semantic-mesh deltas is the unproven step. Hesiod commits to it anyway, because the alternative (discrete mutation tokens) gives away the architectural property that makes the MNLM revolutionary: **contradictions, revisions, and uncertainty as native mathematical features of the trajectory**.

The mechanism:

- **Conditional Flow Matching trajectory.** Given the LLM's terminal hidden state(s) after Substrate-Resonant Recurrence (§3.4), a Conditional Flow Matching module learns a time-dependent vector field `v_θ(z; t, conditioning)` that drives an initial latent state `z_0` toward a final latent state `z_1` representing the structural delta. This is *not* a token-by-token generation — it is a continuous ODE integration over the latent space.
- **Native representation of contradiction.** A contradiction is a *bifurcation in the vector field*: two attractor basins reachable from the same `z_0` depending on local conditions. The MNLM does not need a `CONTRADICTS` token; it has a topologically distinct trajectory.
- **Native representation of revision.** A revision is *kinetic overshooting*: the trajectory diverges from the basin of the original concept and flows toward a new attractor. Again, no special token.
- **Native uncertainty signal.** Trajectory geometry — high curvature, extended oscillation, multiple basin transitions — is an intrinsic measure of epistemic uncertainty. The MNLM emits this as `MeshDelta.trajectory_entropy` for the post-hoc immune system to read.
- **Graph-Autoencoder reconstruction head.** Once the ODE integration stabilises at `z_1`, a deterministic Graph-Autoencoder reconstructs the structural delta — a bounded set of `MutationPrimitive` instances — from the final latent state. The reconstruction is type-safe: the GAE's output head is constrained-decoding into the sealed Pydantic union.

What this gives us that discrete tokens cannot:

- **Auditability of intermediate states.** The post-hoc immune system (Athene-Light, etc.) can inspect any `z_t` along the trajectory to localise where a hallucination or logic error was introduced — *before* the final delta committed.
- **Quarantine semantics.** The trajectory exists fully in latent space until the GAE reconstruction step. The output `MeshDelta` is a *Bounded Constellation* — typed, provenance-stamped, never blindly merged.
- **Direct expression of superposition during reasoning.** The trajectory can hold multiple incompatible structural hypotheses in superposition until late integration, exactly the property COCONUT-style latent reasoning gives at the token level — but for graph synthesis instead of token synthesis.

The **[RESEARCH]** flag means: §8 week 8 is a hard go/no-go checkpoint. If the LFM head fails to converge against the §5 training stack, Talos falls back to discrete mutation tokens (the 4-of-5 artifact consensus path) for v1.1, and LFM moves to v2 research. The week-8 decision is locked: don't sandbag, don't extend, decide and proceed.

### 3.4 Internal mechanism — Substrate-Resonant Recurrence as the default

**Locked: every K-th latent reasoning step (K = 3 default, configurable) interleaves a one-hop call to `TensorMeshEngine.spreading_activation`, with the resulting top-k constellation projected back into the next input embedding via the same GraphProjector.**

This is the architectural commitment that turns the MNLM from "a graph-prompted LLM" into "a model that thinks *with* the substrate". Opus's contribution; adopted whole, with default ON. Not an A/B-testable optional.

The loop (inside one `MeshInput` → `MeshDelta` call):

1. Initial state `h_0` = Graph-KV-conditioned LLM output after the first forward pass over the input subgraph.
2. **For each latent step `t = 1, …, T`:**
   - Standard COCONUT-style recurrence: `h_t = LLM(h_{t-1})` for non-resonance steps.
   - **Resonance step (every K-th `t`):** pool `h_t` to a stimulus vector; call `TensorMeshEngine.spreading_activation(stimulus, max_hops=1, top_k=8)` against the *current state of the substrate* (not just the input subgraph); take the resulting constellation and re-project it through the GraphProjector to produce a fresh structural prefix for the next `h_{t+1}`.
3. Stop on AdaAnchor-style stability gate (mean cosine change < 0.01 across two consecutive non-resonance steps) or `max_latent_steps = 16`.
4. Final `h_T` enters the Latent Flow Matching decoder (§3.3).

Why one-hop SA inside the loop, not multi-hop SA from a fixed stimulus: because the LLM mutates `h_t` between calls, K invocations of one-hop SA are not equivalent to K-hop SA from a fixed starting point. They are *steered* propagation — the MNLM decides, between hops, which direction to push the energy. This is the fan-effect-aware, lateral-inhibition-aware version of Spreading Activation that pure substrate-side SA (without an LM in the loop) cannot do.

What this gives us that nobody else proposed:

- **The MNLM and the substrate share recurrent state.** This is the literal definition of "thinks in the mesh".
- **Reuses the existing `src/theogony/core/tensor_engine.py` primitive.** No new substrate code; only a thin wrapper that exposes one-hop SA as a callable from inside the MNLM service.
- **Bounds latency.** With K = 3, T = 16, max 5 SA calls per MNLM call, ~5–20 ms each at 1024-node scope, total resonance overhead ~25–100 ms per call. Acceptable for everything except very high-throughput Oneiros workloads (which can disable resonance via `MeshInputContext.sa_interleave_K = 0`).

### 3.5 Edge typing — MESH-doctrine edge anatomy

**Locked: edges follow [MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md) §"Edge anatomy" exactly. Quantitative core (`weight`, `decay_tier`, `frame_consistency`, `eligibility`) drives the SpMV hot path; optional semantic descriptors (`relation_descriptor`, `relation_kind`, `description`, `pids`, `creation_context`) carry agent-readable typing. There is no codebook ID and no separate "nuance" vector — those engineering choices from the pre-MESH version of this brief have been superseded by the MESH doctrine.**

The 4-of-5 Round-1 consensus chose a discrete codebook + 32-dim nuance hybrid. That decision was sensible against the pre-MESH single-embedding-per-node substrate, but it has been overtaken by the substrate doctrine: in the MESH triplet, edge typing is *not* the substrate's retrieval primitive (SpMV reads weights), and the descriptive characterisation of a relation (what kind of relation it is, in human / agent terms, with optional Wikidata P-ID anchors) is a free-form metadata surface, not an enum.

What this means for the MNLM:

- **`relation_descriptor`** is a short string label set by Kadmos at edge creation (`"owns"`, `"located_in"`, `"contradicts"`, `"is_section_of"`, etc.). The MNLM can emit any short string here at `AddEdge` time. It is not constrained to a codebook.
- **`relation_kind`** is a broader category string (`"attribute"`, `"ownership"`, `"hierarchy"`, `"temporal"`, `"causal"`, `"co-occurrence"`, `"extraction"`, `"attribution"`). Useful for cross-edge reasoning but not enum-validated.
- **`pids`** is a list of Wikidata property identifiers (`P19` place of birth, `P31` instance of, `P50` author, `P276` location, `P585` point in time, `P580` start time, …). Each P-ID is a one-to-one identifier, exactly as Q-IDs are on nodes. The MNLM may emit zero, one, or several P-IDs per edge when it has high-confidence Wikidata alignment.
- **`description`** is a longer free-text relation summary (up to ~512 chars) for the cases where the short label is too compressed. Like node descriptions, it is regenerable and authoritative for agent and human inspection but not the retrieval surface.
- **The substrate's automatic dynamics ignore all of the above.** SpMV propagates over `(source, target, weight, decay_tier, frame_consistency)`. The descriptors travel for repair, deduplication, contradiction resolution, and consumer formatting — exactly the cleanup operations the immune system and Oneiros do post-hoc.

**Edge directionality and the binding question.** The §6 falsifier still tests whether the MNLM preserves agent-patient direction across multi-hop reasoning. Under the MESH edge model, direction lives in `(source_id, target_id)` ordering plus the asymmetric weight tensor — exactly the topology Graph-KV attends over. The pre-MESH worry was that without a discrete codebook the system would lose semantic distinctions like `LOVES` vs `FEARS`; under MESH, that semantic distinction lives in `relation_descriptor` + the directional weight, and the Graph-KV block-mask attention sees both. The architectural bet on Substrate-Resonance preserving binding is unchanged; what changes is how the relation type is *carried*, not what is carried.

**Bootstrap.** Kadmos v2 produces relation descriptors during reading. The bootstrap vocabulary inherits the Round-9 internal codebook entries (`BINDS_TO`, `REINFORCES`, `CAUSED_BY`, `ABSTRACTION_OF`, `MODULATES`, `CONTRADICTS`, `is_section_of`, `extracted_from`, `subject`, `located_in`, `happened_in_year`, …) as starting strings, not as enum slots. The vocabulary grows as Kadmos encounters new relations. Oneiros consolidates near-synonymous descriptors over time when they consistently co-occur on equivalent structural positions; this is part of the agent-driven cleanup pass, not a separate codebook-maintenance subsystem.

**Pure-continuous VSA approach.** The v2 research question (§9.1) remains: can VSA-binding heads in Graph-KV attention obviate even the relation_descriptor string, recovering all directionality from purely continuous edge embeddings? Open. The MESH-doctrine edge anatomy does not preclude this — `relation_descriptor` is optional. A future MNLM version that doesn't emit it can still produce valid MESH edges; the system's existing post-hoc descriptor surface would simply be empty for those edges.

### 3.6 Boundary text channel — three-layer machine-checkable enforcement

**Locked: three-layer enforcement, adapted to the MESH-doctrine field discipline.**

The MNLM-internal rule is: **no raw source text crosses into the MNLM as retrieval payload, and the MNLM does not emit prose**. Short summary metadata permitted by the MESH substrate (node `description` up to ~512 chars; edge `relation_descriptor` short label; edge `description` up to ~512 chars; source-anchor descriptions) flows through the MNLM as bounded `str` fields with explicit length caps, exactly as MESH defines them. The three independent layers:

- **Type-level (Pydantic):** the `MutationPrimitive` sealed union allows the bounded summary-metadata fields the MESH doctrine specifies (`AddNode.description`, `AddNode.tags`, `AddEdge.relation_descriptor`, `AddEdge.description`, etc.) with explicit `max_length` caps matching MESH §"Field discipline". Every other `str` field on a primitive is a typed enum, an ID pattern, or a hash. There is no free-form text payload. Any future agent attempting to add a `RawTextNote` primitive cannot do so without editing the sealed union — which fails layer 3.
- **Service-level (Python):** the MNLM service exposes only `MeshInput → MeshDelta`. No `respond_in_natural_language`, no `summarize`, no `chat_completion`. The MNLM service's `__init__.py` imports nothing from `transformers.pipelines.text_generation` or any text-generation API. The Latent Flow Matching head decodes only into the constrained Pydantic union. This is structural, not policy.
- **Repo-level (import-linter):** `pyproject.toml` carries an import-linter forbidden contract that prevents the MNLM module from importing any text-generation pipeline from any source. Enforced in CI; violating it fails `pytest -q` even before any test runs. A separate optional package (`theogony-debug-peephole`, sibling repo) provides human-readable summaries of `MeshDelta`s for development debugging — its only purpose is debugging, and the MNLM module is forbidden by import-linter from importing it.

This is the difference between doctrine-by-convention and doctrine-by-contract. The MNLM cannot accidentally widen its text surface beyond what MESH explicitly permits — it would have to *fail CI* to do so.
---

## 4. The locked Pydantic schemas

These schemas are the binding contract. They live, in implementation, under the new substrate package introduced by Migration-Plan Step S1 (`src/theogony/mesh/`) — the exact module path inside that package is one of the §10 Sprint-1 decisions. Kadmos's post-embedding output must conform to `MeshInput`; the MNLM service's only output shape is `MeshDelta`. Talos may extend with sibling DTOs (e.g. `MnlmRunReport`) but may not modify the shapes below without a Phoenix-Backlog ticket (PHX-1000+) and Daedalus review.

These DTOs are **projection-views over the substrate's canonical types**: a `MeshInputNode` projects from a Tier-0 or Tier-1+ substrate node (see [`MESH_SUBSTRATE.md`](../MESH_SUBSTRATE.md) §"Node anatomy"); a `MeshInputEdge` projects from the substrate edge tensor + optional Lance metadata table (see [`MESH_SUBSTRATE.md`](../MESH_SUBSTRATE.md) §"Edge anatomy"). The DTOs carry exactly what the MNLM forward pass needs and no more — they are explicitly *not* the substrate's storage shape.

### 4.1 MeshInput — substrate ↔ MNLM contract

```python
from __future__ import annotations
from datetime import datetime
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Vector1024 = Annotated[list[float], Field(min_length=1024, max_length=1024)]
Vector128 = Annotated[list[float], Field(min_length=128, max_length=128)]
Vector64 = Annotated[list[float], Field(min_length=64, max_length=64)]

ULIDPattern = r"^[0-9A-HJKMNP-TV-Z]{26}$"  # Crockford base-32, 128-bit ULID
QIDPattern = r"^Q[1-9][0-9]*$"
PIDPattern = r"^P[1-9][0-9]*$"


class MeshInputNode(BaseModel):
    """Projection of a substrate node into the MNLM input.

    Mirrors MESH_SUBSTRATE.md §"Node anatomy" (both Tier-0 ChunkNode and
    Tier-1+ ConsolidatedNode collapse into this view; the difference is
    visible via consolidation_tier and is_candidate / is_anchor /
    is_source_anchor flags).
    """
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(pattern=ULIDPattern)
    consolidation_tier: int = Field(default=0, ge=0, le=8)
    is_candidate: bool = False
    is_anchor: bool = False
    is_source_anchor: bool = False

    # Per-substrate-doctrine multi-vector node representation.
    semantic_vector: Vector1024
    frame_vector: Vector64
    structural_vector: Vector128 | None = None
    temporal_vector: Annotated[list[float], Field(min_length=16, max_length=16)] | None = None
    description_vector: Vector1024 | None = None

    # Bounded summary metadata (per MESH §"Field discipline" point 4 / 5).
    description: str | None = Field(default=None, max_length=512)
    tags: list[str] = Field(default_factory=list, max_length=64)
    qids: list[str] = Field(default_factory=list, max_length=8)
    source_url: str | None = Field(default=None, max_length=512)

    # Activation telemetry from the substrate's current state.
    activation_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    node_potential: float | None = Field(default=None, ge=0.0)


class MeshInputEdge(BaseModel):
    """Projection of a substrate edge into the MNLM input.

    Mirrors MESH_SUBSTRATE.md §"Edge anatomy". The quantitative core
    drives Graph-KV's block-mask + edge-bias attention; the optional
    descriptors are agent-readable metadata, never the retrieval primitive.
    """
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=ULIDPattern)
    target_id: str = Field(pattern=ULIDPattern)

    # Quantitative core (read by SpMV; mandatory).
    weight: float = Field(ge=0.0)
    decay_tier: int = Field(default=0, ge=0, le=8)
    frame_consistency: float = Field(default=1.0, ge=0.0, le=1.0)

    # Optional semantic descriptors (read by agents; ignored by SpMV).
    relation_descriptor: str | None = Field(default=None, max_length=128)
    relation_kind: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    pids: list[str] = Field(default_factory=list, max_length=8)
    creation_context: str | None = Field(default=None, max_length=64)


class MeshInputContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["nous", "oneiros", "kalypso", "generic"]
    role_config_id: str | None = Field(default=None, max_length=128)

    # Query intent projected by the calling agent.
    intent_semantic_vector: Vector1024 | None = None
    intent_frame_vector: Vector64 | None = None

    # Budget and recurrence configuration.
    mutation_budget: int = Field(default=64, ge=1, le=1024)
    latent_step_cap: int = Field(default=16, ge=1, le=64)
    sa_interleave_K: int = Field(default=3, ge=0, le=16)
    sa_recurrence_top_k: int = Field(default=8, ge=1, le=64)
    sa_recurrence_max_hops: Literal[1, 2] = 1

    embedding_model_id: str = Field(min_length=1, max_length=128)


class MeshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mnlm-input/2"] = "mnlm-input/2"  # bumped at MESH realignment
    run_id: str = Field(min_length=1, max_length=64)
    call_id: str = Field(min_length=1, max_length=64)
    nodes: list[MeshInputNode] = Field(min_length=1, max_length=1024)
    edges: list[MeshInputEdge] = Field(default_factory=list, max_length=8192)
    active_node_ids: list[str] = Field(min_length=1, max_length=512)
    context: MeshInputContext
    aux: dict[str, Any] = Field(default_factory=dict)
    stamped_at: datetime

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
```

The `aux: dict[str, Any]` lane is opus's layered-schema escape hatch. The base MNLM ignores it; role-specialised heads (Oneiros, Kalypso, future) may opt into specific keys without breaking the core schema.

**Schema version bumped to `mnlm-input/2`** to reflect the MESH-doctrine realignment. The v1 shape (with `Vector384` single embedding, `layer` enum, `relation_codebook_id`, AKA-IDs) is retired with this brief; any pre-MESH artefact carrying `schema_version == "mnlm-input/1"` belongs to the legacy PoC track and is not consumed by post-S1 MNLM code.

### 4.2 MeshDelta — MNLM → substrate contract, with LFM-trajectory metadata

```python
from typing import Discriminator, Tag, Union


class _MutationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op_id: str = Field(min_length=1, max_length=64)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale_embedding: Vector1024 | None = None


class AddNode(_MutationBase):
    """Propose a new node on the substrate. Created as Tier-0 chunk by default;
    Oneiros decides post-hoc whether to consolidate into Tier-1+. See
    MESH_SUBSTRATE.md §"Why two tiers — and how identity actually gets committed"."""
    kind: Literal["add_node"] = "add_node"
    proposed_node_id: str = Field(pattern=ULIDPattern)
    proposed_tier: Literal[0, 1] = 0  # higher tiers are earned via Oneiros, not declared

    # Per-substrate-doctrine multi-vector node payload.
    semantic_vector: Vector1024
    frame_vector: Vector64
    structural_vector: Vector128 | None = None
    description_vector: Vector1024 | None = None  # populate for entity-class Tier-1 candidates

    # Bounded summary metadata.
    description: str | None = Field(default=None, max_length=512)
    tags: list[str] = Field(default_factory=list, max_length=64)
    qids: list[str] = Field(default_factory=list, max_length=8)

    # Eager-linking signal that motivated creation, if any (Q-ID match, description match,
    # tag+structural match, or none → emergent path with is_candidate=True).
    eager_link_signal: Literal["qid", "description", "tag_structural", "emergent"] = "emergent"

    # Optional source-anchor reference (if the node references a Tier-1 source entity).
    source_anchor_id: str | None = Field(default=None, pattern=ULIDPattern)

    # Optional flag for the special node classes.
    is_anchor: bool = False
    is_source_anchor: bool = False
    source_url: str | None = Field(default=None, max_length=512)  # only when is_source_anchor


class AddEdge(_MutationBase):
    """Propose a new edge on the substrate. Quantitative core is mandatory;
    semantic descriptors are optional agent-readable metadata."""
    kind: Literal["add_edge"] = "add_edge"
    source_id: str = Field(pattern=ULIDPattern)
    target_id: str = Field(pattern=ULIDPattern)

    # Quantitative core (drives SpMV).
    weight: float = Field(default=0.5, ge=0.0)
    decay_tier: int = Field(default=0, ge=0, le=8)
    frame_consistency: float = Field(default=1.0, ge=0.0, le=1.0)

    # Optional semantic descriptors (agent / repair / human inspection).
    relation_descriptor: str | None = Field(default=None, max_length=128)
    relation_kind: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    pids: list[str] = Field(default_factory=list, max_length=8)
    creation_context: str = Field(default="mnlm_proposal", max_length=64)


class ReviseNode(_MutationBase):
    """Update an existing node's vectors / description / tags. Oneiros decides
    whether the revision warrants a supersession edge or in-place update."""
    kind: Literal["revise_node"] = "revise_node"
    target_node_id: str = Field(pattern=ULIDPattern)
    revision_kind: Literal["update", "reinterpretation", "confidence_shift", "reweight"]

    new_semantic_vector: Vector1024 | None = None
    new_frame_vector: Vector64 | None = None
    new_description: str | None = Field(default=None, max_length=512)
    new_tags: list[str] | None = None  # if set, replaces the tag list


class MergeNodes(_MutationBase):
    """Propose merging two-or-more Tier-1 candidates into one stable Tier-1 node.
    The substrate's agent-driven cleanup path (MESH_SUBSTRATE.md §"Deduplication")
    formally applies the merge via Oneiros on its next tick with full audit."""
    kind: Literal["merge_nodes"] = "merge_nodes"
    surviving_id: str = Field(pattern=ULIDPattern)
    absorbed_ids: list[str] = Field(min_length=2, max_length=16)
    merged_semantic_vector: Vector1024
    merged_description: str | None = Field(default=None, max_length=512)


class SplitNode(_MutationBase):
    """Propose splitting one node into two-or-more children. Used when a
    consolidated entity turns out to span distinct identities. Effective-resistance
    preservation is the substrate's job (MESH_SUBSTRATE.md §"Sub-node splits"),
    not the MNLM's — the MNLM only proposes the semantic split."""
    kind: Literal["split_node"] = "split_node"
    original_id: str = Field(pattern=ULIDPattern)
    child_node_ids: list[str] = Field(min_length=2, max_length=16)
    child_semantic_vectors: list[Vector1024] = Field(min_length=2, max_length=16)
    child_descriptions: list[str | None] = Field(default_factory=list, max_length=16)


class Invalidate(_MutationBase):
    """Mark a node as no longer reflecting the substrate's current best understanding.
    The substrate writes a CONTRADICTS or SUPERSEDED_BY edge; Oneiros decides post-hoc
    whether the topological weight pattern justifies further therapy."""
    kind: Literal["invalidate"] = "invalidate"
    target_node_id: str = Field(pattern=ULIDPattern)
    reason_embedding: Vector1024
    finding_code: Literal["contradiction", "unsupported", "stale", "schema_conflict", "structural_anomaly"]


class EmitFinding(_MutationBase):
    """Surface a structural / epistemic concern to the immune system as a first-class
    Finding node (per MESH_SUBSTRATE.md §"Agent-driven cleanup" + the Pantheon
    immune-system findings schema)."""
    kind: Literal["emit_finding"] = "emit_finding"
    finding_node_id: str = Field(pattern=ULIDPattern)
    finding_type: Literal[
        "internal_contradiction", "unsupported_claim",
        "echo_chamber", "pheromone_autobahn", "confidence_inflation",
        "refutation_absorption", "saturation_lockout",
        "structural_anomaly", "other",
    ]
    target_node_ids: list[str] = Field(default_factory=list, max_length=64)
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    description: str | None = Field(default=None, max_length=512)


class EmitActivationPacket(_MutationBase):
    """Inject a per-node activation delta into the substrate, biasing future
    Spreading Activation passes. The MNLM's primary mechanism for steering
    the substrate's attention without committing structural mutations."""
    kind: Literal["emit_activation_packet"] = "emit_activation_packet"
    packet_id: str = Field(pattern=ULIDPattern)
    node_energy_deltas: list[tuple[str, float]] = Field(max_length=4096)


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


class TrajectoryMetadata(BaseModel):
    """LFM-specific output telemetry. Read by the immune system; not by other agents."""
    model_config = ConfigDict(extra="forbid")

    trajectory_entropy: float = Field(ge=0.0)
    integration_steps: int = Field(ge=1, le=128)
    final_basin_id: str = Field(min_length=1, max_length=64)
    bifurcations_observed: int = Field(default=0, ge=0)
    max_curvature: float = Field(default=0.0, ge=0.0)
    converged: bool


class MeshDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mnlm-output/2"] = "mnlm-output/2"  # bumped at MESH realignment
    run_id: str
    call_id: str
    model_id: str = Field(min_length=1, max_length=128)
    produced_at: datetime
    primitives: list[MutationPrimitive] = Field(default_factory=list, max_length=4096)
    trajectory: TrajectoryMetadata
    latent_steps_used: int = Field(ge=0, le=64)
    sa_cycles_used: int = Field(ge=0, le=64)
    halted_reason: Literal[
        "stable", "budget_exhausted", "step_cap", "lfm_converged",
        "lfm_failed_convergence", "decoder_constraint_violation", "error",
    ]
    provenance_hash: str = Field(min_length=16, max_length=128)
    failure_reason_code: str | None = None
```

Notes on what is and is not in the schema:

- **No hard-delete primitive.** Destruction is decided post-hoc by the substrate's agent-driven cleanup and therapy mechanisms — see [MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md) §"Agent-driven cleanup" and §"Pathology and therapy". The MNLM emits `Invalidate` and `EmitFinding`; Oneiros and Argus then decide, at tick boundaries with audit, whether the topological evidence warrants demotion, removal, or staged therapy. This matches the MESH-doctrine principle that destruction is always permitted under audit, never silent.
- **ULIDs everywhere.** All IDs are 26-character Crockford-base-32 ULIDs per [MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md) §"Field discipline" point 2. AKA-IDs are a Gen-1 convention and do not appear in post-MESH schemas.
- **Multi-vector AddNode payload.** A new node carries its semantic vector at minimum, frame vector mandatory (the substrate's polarity surface), structural and description vectors optional (recommended for entity-class Tier-1 candidates). This matches MESH_SUBSTRATE.md §"Node anatomy" and §"Field discipline" point 4.
- **`description` field on AddNode / AddEdge / EmitFinding** is a bounded summary string (max 512 chars). It is read by agents and humans for repair and inspection; it is not the substrate's retrieval primitive. Length cap matches MESH §"Field discipline".
- **`TrajectoryMetadata` is the LFM-specific telemetry surface.** It is read by the immune system, never by other agents. `trajectory_entropy`, `bifurcations_observed`, and `max_curvature` are the intrinsic uncertainty signals from §3.3.
- **`provenance_hash`** is the cryptographic trace of which input KV-cache slices, which Substrate-Resonance constellations, and which LFM trajectory produced this `MeshDelta`. The substrate write layer stores it in the audit ledger alongside every committed primitive so the immune system can replay the call deterministically if a finding requires it.

**Schema version bumped to `mnlm-output/2`** at the MESH realignment. The v1 shape (single embedding fields, `layer`, `relation_codebook_id`, `nuance`, AKA-IDs, `parent_node_ids`) is retired; pre-MESH artefacts carrying `schema_version == "mnlm-output/1"` belong to the legacy PoC track.

### 4.3 MnlmRunReport — sibling to existing RunReports

```python
class MnlmRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mnlm-runreport/1"] = "mnlm-runreport/1"
    run_id: str
    started_at: datetime
    completed_at: datetime
    role: Literal["nous", "oneiros", "kalypso", "generic"]
    calls_made: int = Field(ge=0)
    calls_succeeded: int = Field(ge=0)
    primitives_emitted_total: int = Field(ge=0)
    primitives_by_kind: dict[str, int] = Field(default_factory=dict)
    mean_trajectory_entropy: float | None = None
    mean_latent_steps: float | None = None
    mean_sa_cycles: float | None = None
    halted_reason_counts: dict[str, int] = Field(default_factory=dict)
    verdict: Literal["completed", "partial", "failed"]
    findings_emitted: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=4096)
```

This composes with the existing `IngestRunReport` / `QueryRunReport` / `OneirosTickReport` shapes in `src/theogony/reporting/models.py` and is one of the three Sprint-1 commits (§10).
---

## 5. The locked training stack

**Locked: two-phase curriculum. Phase A is supervised warmup from Kadmos. Phase B is Graph-GRPO with Spreading-Activation alignment as the loss surface — the substrate is the teacher.**

### 5.1 Phase A — Kadmos-imitation warmup

Opus's contribution; adopted whole. The Kadmos v2 reading loop already produces, per `ReadingStep`, the exact pair the MNLM needs: `(prior ReadingState + hypothesis candidates) → (understanding update)`. After Kadmos's internal embedding pass, this pair is structurally identical to a `(MeshInput, MeshDelta)` tuple in the post-MESH schema. Mapping:

| Kadmos `understanding update` field | `MeshDelta.primitives[i].kind` |
|---|---|
| `new_concepts[i]` (entity or concept candidate; eager-linking signal recorded) | `add_node` (with `eager_link_signal` populated, `proposed_tier=1` for confidently-linked entity candidates, `proposed_tier=0` for chunk observations) |
| `new_connections[i]` (reference edge from a Tier-0 chunk to a Tier-1 entity / concept / source-anchor; or between Tier-1 nodes) | `add_edge` (with `relation_descriptor` / `relation_kind` / `pids` populated when Kadmos has high confidence) |
| `revisions[i].type == "update"` | `revise_node` |
| `revisions[i].type == "split"` | `split_node` |
| `revisions[i].type == "merge"` | `merge_nodes` |
| `revisions[i].type == "invalidate"` | `invalidate` |
| `confirmed_hypotheses[i]` | `emit_activation_packet` (positive energy delta) |
| `rejected_hypotheses[i]` | `emit_activation_packet` (negative energy delta) |
| `synthesis` | `add_node` with `proposed_tier=1` and tags identifying the synthesis role |
| `open_tensions[i]` | `emit_finding` with `finding_type == "structural_anomaly"` |
| `source_extraction[i]` (Kadmos emitting / linking a source-anchor entity) | `add_node` with `is_source_anchor=True` and `source_url` populated |

This means: every Kadmos run on every Wikipedia article generates ~hundreds of training pairs at zero marginal cost beyond what the project will pay anyway to run Kadmos. The training corpus is the Chronik's own bootstrap log.

**Loss for Phase A:**

- Cross-entropy on the LFM head's reconstruction of the discrete enum fields of each `MutationPrimitive` (`kind`, `proposed_tier`, `eager_link_signal`, `finding_code`, `finding_type`, etc.) — supervised against Kadmos's labels.
- MSE on the continuous fields (`semantic_vector`, `frame_vector`, `structural_vector`, `description_vector`, `rationale_embedding`, edge `weight`, edge `frame_consistency`) against Kadmos's emitted vectors and substrate-state values.
- Token-level cross-entropy (with a tokenized constrained-decoding head) on the short string descriptor fields (`description`, `tags`, `relation_descriptor`, `relation_kind`) against Kadmos's labels — these are bounded summary metadata, not free prose, so the loss surface is constrained.
- A small auxiliary trajectory-stability loss on the LFM head: penalise solutions where the integration is unstable (high `max_curvature` without a meaningful bifurcation).

**Cost:**

- Corpus: 10 k Wikipedia articles run through Kadmos → ~5 M training pairs. The articles already exist; Kadmos v2 will run them anyway. Marginal corpus cost: zero (already paid by Kadmos's own roadmap).
- Training: 5 M pairs × 1 epoch on the ~40 M trainable surface (LoRA + GraphProjector + GAE+CFM head) on one 80 GB H100 ≈ 80–120 GPU-hours ≈ 250–400 EUR at spot rates.
- Phase A is a one-pass warmup, not an optimisation target. Stop when the held-out cross-entropy plateaus (delta < 1 % over 5 k steps).

### 5.2 Phase B — Graph-GRPO with Spreading-Activation alignment **[primary]**

This is the radical training signal. The MNLM is not optimised against an oracle's tokens or against Kadmos's labels. It is optimised against the substrate's own retrieval primitive: **the model is rewarded only when its proposed mesh delta improves the precision and recall of Spreading Activation on held-out probes.** This is the training-side instantiation of the three-factor reinforcement learning principle that lives in the substrate's own doctrine ([MESH_RETRIEVAL.md](../MESH_RETRIEVAL.md) §"Three-factor reinforcement learning"); the MNLM's Phase B and the substrate's runtime Hebbian feedback are two ends of the same loop.

The Graph-GRPO mechanism (arXiv:2603.02701, adapted for mesh-delta synthesis):

1. For each training query, sample a *group* of K = 8 distinct `MeshDelta` candidates from the current MNLM policy. Each is sampled with mild trajectory-noise injection in the LFM head to ensure diversity.
2. For each candidate, apply it to a copy of the substrate, then run the substrate's Spreading Activation primitive (post-MESH path: `src/theogony/mesh/runtime/spreading.py` per Migration-Plan Step S3; the Step-S3 implementation also brings in MESH-doctrine diversified injection — MMR + weight-class stratification + optional sub-mesh signature) against a held-out probe. Compute the rank of the target node in the resulting Constellation.
3. **Edge-level advantage:** for each `MutationPrimitive` `m` in candidate `i`, compute the marginal contribution of `m` to the group's relative reward (ablate `m` and re-run SA; difference in rank is `m`'s contribution). The substrate's eligibility-trace mechanism ([MESH_RETRIEVAL.md](../MESH_RETRIEVAL.md) §"Eligibility traces") is the inference-time analogue of this training-time edge-level credit assignment.
4. **GRPO update:** apply policy gradient to maximise group-relative reward, using edge-level advantages to assign credit to specific mutations rather than the whole delta.
5. Auxiliary penalties:
   - **Mutation sparsity:** penalty proportional to `len(primitives) / mutation_budget`. Discourages graph inflation.
   - **Directional consistency:** explicit penalty when `AddEdge` is emitted in a direction (`source_id → target_id` ordering plus asymmetric weight) that the verified-truth probe rejects. This is the loss-surface companion of the §6 falsifier and matches the MESH-doctrine principle that direction lives in the topology, not in a separate type system.
   - **Frame consistency:** penalty when an `AddEdge` emits with `frame_consistency` that is inconsistent with the endpoints' `frame_vector`s. Trains the model to be honest about polarity / refutation / hypothesis framing.
   - **Schema-validity:** any `MutationPrimitive` that fails Pydantic validation in the GAE reconstruction step is a hard reward-zero, not a soft penalty.

**Why this is the primary signal:**

- The substrate's own retrieval primitive becomes the loss. There is no oracle whose token distribution the MNLM is asymptotically capped at. The MNLM can in principle exceed any text-RAG teacher because the loss is grounded in *what makes the mesh work*, not in *what an LLM writes about a graph*.
- It directly tests the project's central architectural bet (Stance C, §0): if typed edges + latent CoT + Substrate-Resonance preserve binding, the post-mutation activation will retrieve correctly; if they fail, the loss surfaces it immediately.
- It scales naturally with corpus size. As the Chronik grows, the held-out probe set grows; the loss becomes more discriminating; the model converges to a better policy.

**Cost:**

- Probe set: 50 k held-out (probe_vector, expected_top_k) pairs derived from Kadmos's own multi-hop reading patterns + curated cross-article inference cases (subset of the Monkey-3 protocol, §6.3).
- Training: 50 k episodes × K = 8 group samples × ~5 SA evaluations per sample × ~100 ms per SA call ≈ 200–400 GPU-hours on one 80 GB H100 ≈ 600–1 200 EUR.
- Convergence signal: stop when the directed-edge F1 on held-out validation plateaus AND the §6.1 DBB-200 falsifier crosses the 95 % threshold AND the contradiction-path false-positive rate has not worsened.

**Total Phase A + Phase B marginal cost: ~1 000–1 600 EUR.** Within function-first budget.

### 5.3 Why distillation from a frontier-LLM-with-RAG teacher is rejected

Three of the five Round-1 artifacts proposed an oracle-based distillation phase. Hesiod rejects it for v1:

- It introduces an asymptotic ceiling at the oracle's accuracy. The MNLM cannot exceed its teacher.
- It re-introduces text into the training loop — even if the teacher is run separately and only its outputs are converted to graph operations, the MNLM is implicitly being trained to imitate text-mediated reasoning.
- It is more expensive than the alternatives.

If Phase A + Phase B fail to converge, oracle distillation re-enters scope as a v1.1 fallback. Until then, the substrate is the only teacher.

### 5.4 The substrate-as-teacher principle, in one sentence

The MNLM is the first agent in the project whose training loop closes against the Chronik's own retrieval primitive rather than against text or against an external oracle. *That* is the design property that makes it mesh-native, training-side; §3.4 makes it mesh-native, inference-side.
---

## 6. The locked falsifier stack

**Locked: three-stage falsifier. DBB-200 micro-gate at week 6, MuSiQue-4hop production validation at week 10, Monkey-3 emergent-knowledge test at week 12.**

The three stages test increasingly ambitious claims, each building on the previous. Each has a hard go/no-go decision rule.

### 6.1 Stage 1 — DBB-200 (week 6, 24 GPU-hours, single number)

Adopted from `opus.md` §H. The minimal-pair test of compositional binding.

**Setup:** 200 synthetic minimal pairs of the form `(A_i, R, B_i)` and `(B_i, R, A_i)` where `R ∈ {LOVES, OWES, EXAMINED, KILLED, OUTRANKS}`. Names from a 4 k-name vocabulary, no name pair appears in both directions. Each pair becomes a 6-node, 8-edge mini-mesh embedded with `BAAI/bge-small-en-v1.5` and asserted as a typed edge of relation `R`. Both directions ingested as separate constellations.

**The MNLM is queried** with a `MeshInput` whose focal subgraph is the constellation, plus an `intent_vector` derived from the textual prompt "what is the direction of `R` in this constellation?". The MNLM emits one of: an `EmitFinding(structural_anomaly)` if it disagrees with the asserted direction; an `AddEdge` re-asserting in its preferred direction; or an `EmitActivationPacket` confirming the asserted direction.

**Metric:** accuracy = #correct directions identified / 400 (per-direction, not per-pair).

**Decision rule:**
- ≥ 95 %: pass. Stance C holds; the SR-MNLM's typed-edge-plus-latent-CoT bet for compositional binding works. Proceed to Stage 2.
- 80–95 %: marginal. Re-weight the directional-consistency penalty in §5.2 and re-run once. Three-iteration cap.
- < 80 %: **fail.** Stance C fails; the architecture cannot bind direction. Triggers the week-6 architecture revision branch in §8.

**Why this is the right Stage 1:** it is the cheapest test that probes the project's central architectural bet in isolation, separated from Kadmos quality, retrieval quality, and corpus distribution. 24 GPU-hours, single number, defensible threshold. If the MNLM cannot bind direction here, no downstream claim about the architecture's reasoning power survives.

### 6.2 Stage 2 — MuSiQue 4-hop (week 10, ~4 weeks of preparation, two thresholds)

Adopted from `DeepSeek.md` §Q8 with the deepresearch corpus refinement. The production validation against a real benchmark.

**Setup:** Build a Golden Chronik from the supporting Wikipedia paragraphs of 5 000 MuSiQue questions (Trivedi et al. 2022, arXiv:2108.00573). Run Kadmos v2 on those paragraphs to produce vector subgraphs. Each MuSiQue question is associated with a subgraph containing all necessary facts plus several distractors. Hold out 500 questions for evaluation, ensuring 50 % have direction-critical roles ("who is the mother of X" vs "whose mother is X") and 25 % involve negation.

**Baseline:** text-RAG on Llama-3-8B-Instruct, with the same factual content serialised as flattened text passages, zero-shot prompting. Identical base model, identical corpus.

**MNLM evaluation path:** each question's `intent_vector` is derived from the question text via the same embedder; the MNLM ingests the corresponding subgraph plus the intent; emits a `MeshDelta`; the substrate is re-queried via Spreading Activation; the top-1 activated node's `description` is the predicted answer. (Earlier drafts named a `label_for_provenance_only` field; that is a retired pre-MESH field — post-realignment consolidated nodes carry `description`.)

**Ablation controls (required).** The answer is read off the substrate *the MNLM just wrote to*, so the MNLM can move any node to top-1 by emitting an `AddEdge`(question-entity → answer). Two controls isolate its actual contribution and must be reported alongside the MNLM number:
- **Frozen-mesh control** — the same post-query Spreading Activation over the Golden Chronik **without applying any MNLM `MeshDelta`**. If this already returns the correct top-1 node, the answer was Kadmos's and the MNLM added nothing.
- **Parametric-only control** — the frozen base Llama-3-8B answering **closed-book, no mesh input**. The base was pretrained on Wikipedia, the source of MuSiQue; a correct closed-book answer means the "win" is pretrained recall laundered through a written edge, not substrate reasoning.

A pass requires the MNLM to beat **both** controls, not merely to be non-inferior to text-RAG. Report all four numbers (MNLM, text-RAG, frozen-mesh, parametric-only) side by side; the thresholds below are then necessary, not sufficient.

**Metric:** exact-match accuracy of the answer entity.

**Decision rule:**
- Overall accuracy gap: MNLM accuracy more than **5 percentage points below** the text-RAG baseline ⇒ fail.
- Direction-critical subset: MNLM accuracy more than **10 percentage points below** the text-RAG baseline on the direction-critical questions ⇒ fail.
- Either failure triggers the week-10 architecture revision branch in §8.

**Why both thresholds:** the overall threshold tests whether the MNLM is competitive at all; the direction-critical threshold tests whether the architectural bet on Substrate-Resonance + typed edges is paying off. A v1 that beats text-RAG on overall accuracy but loses on direction-critical is *the wrong design* for what the project is building, even if it ships.

### 6.3 Stage 3 — Monkey-3 Emergent-Knowledge Test (week 12, the revolutionary validation)

This is the test the project has named "Monkey 3" since `TARGET_ARCHITECTURE.md` was first written. Hesiod operationalises it here as the third-stage falsifier — the test that distinguishes "MNLM is a very good RAG" from "MNLM is something new".

**Setup:** Construct a corpus of 100 cross-domain analogy pairs in which the answer to a target question requires inferring a structural correspondence across two unrelated source articles, where neither article alone contains the answer. Example: a fluid-dynamics article on Bernoulli's principle, a cellular-biology article on capillary action — the question requires noticing the structural isomorphism. Source articles are *not* present in MuSiQue and *not* in Kadmos's training corpus; they are held out cleanly.

**MNLM evaluation path:** ingest both source articles via Kadmos v2; let the MNLM operate over the combined Chronik (with Substrate-Resonant Recurrence enabled); query with the target question's intent vector; expect the MNLM's `MeshDelta` to include synthesis nodes connecting the two domains, and the post-delta SA query to retrieve the correct cross-domain answer.

**Baseline 1:** text-RAG on Llama-3-8B-Instruct over the same source articles. Expected to fail on most cross-domain analogies because the answer is not in any single chunk.

**Baseline 2:** text-RAG on Llama-3-70B-Instruct (compute-equivalent ceiling) over the same source articles. Expected to do better than 8 B but still degrade on cross-domain.

**Baseline 3 — frozen-mesh control:** post-query Spreading Activation over the combined Chronik **without the MNLM's `MeshDelta`**. Isolates whether the cross-domain link was Kadmos's or the MNLM's.

**Baseline 4 — parametric-only control:** frozen Llama-3-8B answering **closed-book**. The worked Bernoulli ↔ capillary-action example is a standard textbook analogy almost certainly in pretraining; a correct closed-book answer falsifies the "emergent synthesis" reading of any MNLM win.

**Contamination guard (required):** at least half of the 100 analogy pairs must be drawn from **fictional or synthetic domains** with no plausible pretraining presence, so a win cannot be pretrained-analogy recall. Note too that the MNLM path spends more test-time compute (≤16 latent steps + interleaved SA calls) than one RAG pass, so beating the 8 B baseline on compute alone is not the claim — the 70 B compute-equivalent ceiling (Baseline 2) is the more honest comparator, and a win over 8 B that does not also approach 70 B should be read as compute, not architecture.

**Metric:** human-judged answer correctness on a 0–3 Likert scale, blind-rated against the systems' outputs (MNLM + the four baselines/controls). Inter-rater reliability (κ ≥ 0.7) is required.

**Decision rule:**
- MNLM mean rating > 8 B baseline (p < 0.05): **the architecture demonstrably synthesises cross-source structure that text-RAG cannot reach**. The project's central thesis is empirically supported.
- MNLM mean rating ≈ 8 B baseline: the MNLM is a competent retrieval system but does not exceed RAG. v1 ships, but the [PHX-####] ticket "synthesis ceiling investigation" is opened.
- MNLM mean rating < 8 B baseline: **the architecture is worse than RAG.** Significant architectural revision required before further investment.

**Why this stage is non-negotiable:** the project has been writing "Monkey 3" on its whiteboard since 2026-04. If Hesiod ships an MNLM brief without binding a Stage-3 falsifier that operationalises it, the project never closes the loop on its own founding claim. This stage is the difference between *building* the substrate and *believing in* the substrate.

### 6.4 Falsifier-stack summary

| Stage | When | Cost | Tests | Outcome if pass | Outcome if fail |
|---|---|---|---|---|---|
| DBB-200 | week 6 | 24 GPU-h | Compositional binding in isolation | Proceed to Stage 2 | Architecture revision (§8 week-6 branch) |
| MuSiQue-4hop | week 10 | ~4 weeks prep + 1 day eval | Production-grade multi-hop QA, with direction-critical subset | Proceed to Stage 3 | Architecture revision (§8 week-10 branch) |
| Monkey-3 | week 12 | ~1 week prep + human rating | Emergent cross-source synthesis | The project's central thesis is supported | Open PHX-#### "synthesis ceiling investigation" |

Each stage is harder than the previous. Each cost is justified only if the previous stage passed. This is the discipline opus's micro-falsifier and DeepSeek's macro-falsifier together suggested — Hesiod adds the third stage that makes the falsifier stack *load-bearing for the project's identity*, not just for the architecture's quality.
---

## 7. Kadmos contract — re-anchored against the MESH eager-linking discipline

The `MeshInput` schema in §4.1 is the binding contract between Kadmos's post-embedding output and every MNLM-class agent. Under the MESH realignment, Kadmos v2's responsibility is broader than it was in the pre-MESH version of this brief: Kadmos v2 is now Migration-Plan **Step S2** ([MESH_MIGRATION_PLAN.md](../MESH_MIGRATION_PLAN.md) §"Step S2"), and its job is to write Tier-0 chunks and Tier-1+ entity / concept / source-anchor candidates *directly into the substrate* via the eager-linking discipline ([MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md) §"Why two tiers — and how identity actually gets committed"). The MNLM then *reads* that substrate state into its `MeshInput` projection — Kadmos no longer assembles a `MeshInput` directly; it populates the substrate, and the MNLM projects from the substrate when it queries.

### 7.1 The substrate is the contract; `MeshInput` is the projection

The previous version of this section asked Kadmos to "produce, at the end of its embedding pass, an artifact structurally identical to a `MeshInput` instance". The MESH realignment changes that flow:

- Kadmos v2 writes to the substrate. Tier-0 chunks, Tier-1+ entity / concept / source-anchor candidates, reference edges with optional `relation_descriptor` / `relation_kind` / `pids`. Eager linking applies the three-signal hierarchy (Q-ID match / description match / tag+structural match) at insertion. See [MESH_MIGRATION_PLAN.md](../MESH_MIGRATION_PLAN.md) §"Step S2 — Kadmos v2 writes into the new substrate" for the binding deliverables.
- When the MNLM is invoked, it constructs a `MeshInput` by *projecting* the currently-relevant substrate sub-graph: the active set plus its multi-hop neighbourhood, with per-node multi-vector representation and per-edge quantitative-plus-optional-descriptor shape.
- The projection step is `src/theogony/mesh/runtime/...` (introduced by Step S1 / S3) plus the MNLM service wrapper. It is not part of Kadmos.

### 7.2 What Kadmos does NOT need to change beyond its MESH-doctrine deliverable

- The reading loop, working memory, revision policy, and granularity choice (Kadmos v2 brief §3) are unchanged.
- The labelled intermediate `ReadingState` shape is unchanged. Labels remain transitional debugging metadata.
- The internal embedding pass already produces vectors of the right dimensionality (1024 from BGE-M3 class for the semantic vector; 64 for the frame vector; smaller for any auxiliary vectors).

The amendment vs. the pre-MESH Kadmos brief is: where the pre-MESH version asked Kadmos to *emit* a `MeshInput`-shaped artefact, the post-MESH version asks Kadmos to *write into the substrate* using MESH-conformant schemas. The structural surface is the substrate's `ChunkNode` / `ConsolidatedNode` / `Edge` / `EdgeMetadata` Pydantic models from Step S1, not the MNLM's `MeshInput`.

### 7.3 Direction of compliance, restated

The substrate's `ChunkNode` / `ConsolidatedNode` / `Edge` types are the canonical truth. Kadmos writes them. The MNLM projects from them into `MeshInput`. Both Kadmos and the MNLM conform to the substrate; neither one is the substrate's source of truth.

If a future Kadmos extension produces structure the substrate's schemas cannot represent, that is a Phoenix Backlog ticket (PHX-1000+) against `MESH_SUBSTRATE.md`, routed to whoever owns substrate doctrine at that point, not a silent schema drift. If the MNLM needs a projection that the substrate cannot produce, that is a Phoenix Backlog ticket against this brief.
---

## 8. Talos sprint roadmap — the body of Migration-Plan Step S5

The roadmap below is the body of [Migration-Plan Step S5](../MESH_MIGRATION_PLAN.md#step-s5--full-oneiros-tick-consolidation-splits-pathology-surveillance-therapy-three-factor-rl) — the full Oneiros tick, three-factor reinforcement learning, and the MNLM as its training-time loop. It is **not executable before Migration-Plan Steps S1, S2, S3, S4 have landed**: S1 produces the substrate skeleton this work targets, S2 produces the Kadmos-v2 ingest the training corpus needs, S3 produces the diversified-injection Spreading Activation the GRPO reward function calls, S4 wires the surfaces (CLI, MCP, Cockpit) so a trained MNLM can be observed.

This 12-week roadmap is therefore "Step S5, expanded". When Talos picks up S5, the roadmap below tells them what S5 contains in detail. Until then, this roadmap is binding *as a plan* but not actionable *as the next step*.

Three research checkpoints (weeks 4, 8, 12 of S5, *not* of the overall project) gate progression with concrete go/no-go decisions.

### Weeks 1–2: Schemas and scaffolding (within Step S5)

- **W1 commit 1:** `feat(mesh-mnlm): add MeshInput, MeshDelta, MutationPrimitive, TrajectoryMetadata Pydantic v2 schemas under src/theogony/mesh/mnlm/dto.py with extra="forbid", model_validator graph-integrity check, ULID-pattern IDs, multi-vector node payload per MESH_SUBSTRATE.md §"Node anatomy", and import-linter rule forbidding text-generation imports.` (Round-trip tests are now against the MESH-substrate ChunkNode / ConsolidatedNode / Edge types from Step S1, not against KnowledgeNode / KnowledgeEdge.)
- **W1 commit 2:** `feat(reporting): add MnlmRunReport sibling under src/theogony/reporting/models.py with verdict heuristics that flag mutation_budget_exhaustion as 'partial' and lfm_failed_convergence as 'failed'.`
- **W2 commit 1:** `feat(mesh-mnlm): scaffold GraphProjector (subgraph → continuous prefix tokens) + Graph-KV adapter (block-mask attention + edge-type bias injection) over a vendored copy of Graph-COM/GraphKV reference impl, no training, smoke test against Llama-3-8B-Instruct.`
- **W2 commit 2:** `feat(mesh-mnlm): scaffold LFM-GAE decoder head (Conditional Flow Matching + Graph-Autoencoder reconstruction) targeting MutationPrimitive sealed-union output, no training, parametric type-safe constrained decoding test.`

### Weeks 3–4: Substrate-Resonant Recurrence and the MeshInput projector

- **W3:** wire the MESH-substrate Spreading Activation primitive (`src/theogony/mesh/runtime/spreading.py` from Step S3) into the LLM forward pass as the K-th-step interleave (§3.4). Implement `sa_interleave_K`, `sa_recurrence_top_k`, `sa_recurrence_max_hops` from `MeshInputContext`. Smoke-test against a small in-substrate toy mesh; assert latency budget (~25–100 ms added per call). Note: this step depends on Step S3's diversified injection landing; the K-th-step interleave inside the MNLM uses the substrate's `spreading_activation` interface, which already includes MMR + weight-class stratification.
- **W4 commit 1:** `feat(mesh-mnlm): MeshInput projector that constructs a MeshInput instance from a substrate sub-graph. Reads ChunkNode / ConsolidatedNode rows from Lance, edges from the sparse CSR tensor + Lance metadata table, projects into the multi-vector MeshInput shape from §4.1.`
- **W4 commit 2:** integration test: Kadmos v2 (from Step S2) reads a Wikipedia article, the substrate accumulates Tier-0 chunks plus eager Tier-1 entities, the MeshInput projector pulls a sub-graph, the MNLM ingests it (no training yet), produces a deterministic `MeshDelta`. End-to-end shape check.

**Research checkpoint W4:**
- Does Graph-KV adaptation work mechanically against the frozen Llama-3-8B over a real MESH-substrate sub-graph (forward pass produces non-degenerate outputs; multi-vector input is handled correctly; edge descriptors flow through as attention biases)? If not, fall back to GNP soft-prompts and re-time the roadmap. Decision binary, recorded in a `MnlmRunReport(verdict="failed", notes=...)` artifact committed to `docs/research/mnlm/poc_mesh/checkpoints/W4.md`.

### Weeks 5–6: Phase-A Kadmos-imitation training and DBB-200

- **W5:** prepare the Phase-A training corpus (10 k Wikipedia articles run through Kadmos v2 against the MESH substrate, ~5 M `(MeshInput, MeshDelta)` pairs harvested from Kadmos's reading-step output stream — reformulated against the post-MESH eager-linking discipline per §5.1's updated mapping table). Sanity-check the mapping on 100 random pairs.
- **W5 commit:** Phase-A training loop — supervised cross-entropy on discrete fields + MSE on continuous fields + auxiliary trajectory-stability loss. Configured for 1 epoch on one 80 GB H100. Reproducible config in `configs/mnlm/phase_a.yaml`.
- **W6 day 1–4:** run Phase-A. ~80–120 GPU-hours.
- **W6 day 5–7:** **DBB-200 evaluation (Stage-1 falsifier).** Build the 200 minimal pairs synthesizer. Run the trained MNLM. Compute per-direction accuracy.

**Research checkpoint W6 (DBB-200 falsifier):**
- ≥ 95 %: pass. Proceed to Phase B (week 7).
- 80–95 %: marginal. Re-weight the directional-consistency penalty in §5.2 and re-run Phase A once. Three-iteration cap; if still marginal, decision-tree to "marginal-pass" branch.
- < 80 %: **fail.** Two options: (a) revert §3.3 LFM commitment, fall back to discrete mutation tokens, retrain Phase A; (b) re-architect (escalate to Daedalus). Hesiod prefers (a) if directional-binding works at the structural level but LFM is the failure mode; (b) if directional-binding itself fails (which would falsify Stance C and require revisiting §0).

### Weeks 7–10: Phase-B Graph-GRPO training and MuSiQue evaluation

- **W7–W8:** Phase-B Graph-GRPO training. Build the held-out probe set (50 k probes derived from Kadmos multi-hop reading patterns). Implement group sampling, edge-level credit assignment, mutation-sparsity / directional-consistency / schema-validity penalties. ~200–400 GPU-hours over both weeks.

**Research checkpoint W8 (LFM convergence):**
- Does the LFM head converge under Phase B? Specifically: does `MeshDelta.trajectory.converged == True` for ≥ 95 % of held-out queries; is the held-out reward trajectory monotonically improving across the last 5 k episodes; is the schema-validity rate ≥ 99 %?
- Pass: continue.
- Fail (LFM diverges or schema-validity collapses): hard fall-back to discrete-mutation-token decoder for v1.1. The LFM commitment moves to v2 research. Update §3.3 status, commit a `MnlmRunReport(verdict="partial")` documenting the fall-back. Continue to MuSiQue eval with the discrete-token v1.1.

- **W9:** prepare MuSiQue-derived Golden Chronik. Run Kadmos v2 on the supporting paragraphs. Build the 500-question held-out set. Build the text-RAG baseline.
- **W10:** **MuSiQue 4-hop evaluation (Stage-2 falsifier).** Run both systems on the 500 held-out questions. Compute overall and direction-critical accuracy.

**Research checkpoint W10 (MuSiQue falsifier):**
- Pass thresholds (overall within 5 pt; direction-critical within 10 pt of text-RAG baseline): proceed to Monkey-3.
- Fail: open architecture-revision Phoenix ticket. Hesiod brief receives an amendment. Talos does not proceed to Stage 3 until revision lands.

### Weeks 11–12: Monkey-3 emergent-knowledge test

- **W11:** build the 100 cross-domain analogy pair corpus. Recruit ~5 blind human raters. Pre-register the rating protocol.
- **W12:** **Monkey-3 evaluation (Stage-3 falsifier).** Run MNLM, 8 B text-RAG baseline, 70 B text-RAG baseline. Collect blind human ratings. Compute statistical significance.

**Research checkpoint W12 (Monkey-3 / project-thesis falsifier):**
- MNLM mean rating > 8 B baseline (p < 0.05): the project's central thesis is supported. **v1 ships.**
- MNLM ≈ 8 B baseline: v1 ships, PHX-#### "synthesis ceiling investigation" opens.
- MNLM < 8 B baseline: v1 does not ship as Nous; architectural revision is mandatory; Hesiod brief returns to research mode.

### Total budget

- Compute: ~280–520 GPU-hours on one 80 GB H100 for the full Phase A + Phase B + 3 falsifier evals. ~850–1 600 EUR at spot rates.
- Wall clock: 12 weeks for one Talos-class agent + one human reviewer at the 3 research checkpoints.
- Engineering surface: ~6 new modules under `src/theogony/agents/mnlm/`, one amendment to Kadmos's export step, one new `MnlmRunReport` schema, one `pyproject.toml` import-linter contract, one Graph-KV vendored fork integrated. Estimated ~3 000–5 000 LoC of net new code.
---

## 9. Open research questions [RESEARCH]

This brief is in parts research work. The following questions are explicitly open. They are not blockers for v1 — Hesiod has locked v1 with sensible defaults — but each is a real open question whose resolution will shape v2 and beyond.

### 9.1 VSA binding heads and the systematicity bound [RESEARCH]

Dhayalkar 2025 ("Attention as Binding") proposes that transformer self-attention can implement an approximate Vector Symbolic Architecture, with explicit binding/unbinding heads enforcing role-filler separation. The theory is real; the empirical scaling has not been demonstrated for graph-structured inputs.

The v1 design uses a discrete codebook + continuous nuance for edge typing (§3.5). This is the safe bet, but it is not maximally radical. If the v2 question is "can we eliminate the discrete codebook entirely and rely on Substrate-Resonance + VSA-style binding heads to recover systematicity from purely continuous edge embeddings?", the answer is empirically open.

**The v2 research question:** does adding VSA-binding heads to the Graph-KV attention layers measurably improve directional binding (DBB-200) over the v1 hybrid codebook+nuance design? If yes by ≥ 5 percentage points on DBB-200, v2 deprecates the codebook and moves to pure-continuous edge typing. If no, the codebook stays.

**The v2 experiment:** train one v1.5 with VSA-binding-head adapter (Dhayalkar's "explicit binding/unbinding heads"), evaluate on DBB-200 and on a structurally-isomorphic-but-vocabulary-shifted variant. Cost: ~50 GPU-hours.

### 9.2 Inter-MNLM latent communication [RESEARCH]

Run-1 and Run-12 both surveyed LatentMAS (KV-cache transfer between agents) and Cache-to-Cache (C2C / KVComm). The cross-artifact consensus was: SA-mediated coordination via the Chronik is the primary channel; a direct latent channel is needed only for high-bandwidth multi-step collaborative reasoning (e.g. Nous and Oneiros iterating rapidly on the same hypothesis without polluting the Chronik with intermediate states).

v1 ships **without** a direct latent channel between MNLMs. All inter-MNLM coordination flows through the substrate, and the substrate's append-only ledger provides the audit trail. This is the conservative, doctrine-conformant choice.

**The v2 research question:** does adding an explicit `LatentPacket` direct channel between MNLM roles (Nous → Oneiros, Oneiros → Kalypso) improve cross-role task throughput on a multi-stage reasoning benchmark relative to substrate-only mediation? If yes, define the typed packet shape, the alignment matrix `W_a` for cross-role hidden-state transfer (LatentMAS-style), and the immune-system surveillance hooks.

**The v2 experiment:** build a 50-task multi-role benchmark where Nous proposes, Oneiros consolidates, Kalypso explores. Compare substrate-only vs latent-channel coordination on task completion rate, latency, and post-hoc finding rate. Cost: ~30 GPU-hours.

### 9.3 Substrate-Resonant Recurrence ablation [RESEARCH]

The v1 design defaults to `sa_interleave_K = 3`. But the value is not justified empirically — opus picked it as a reasonable default from cognitive plausibility heuristics. The actual question is open.

**The v2 research question:** what is the optimal `sa_interleave_K` as a function of subgraph size and reasoning depth? Specifically: does `K = 1` (resonance every step) give better directional binding than `K = 3` at the cost of higher latency? Does `K = 0` (resonance disabled) match v1 performance on simple queries while saving compute? Does `K` interact with `latent_step_cap`?

**The v2 experiment:** ablation over `K ∈ {0, 1, 2, 3, 5, 8}` × `latent_step_cap ∈ {4, 8, 16, 32}` on DBB-200 + a held-out MuSiQue subset. Find the Pareto frontier (accuracy × latency × cost). Cost: ~80 GPU-hours.

### 9.4 The bifurcation interpretation of contradiction [RESEARCH]

§3.3 commits to LFM with the claim that contradictions become bifurcations in the trajectory. This is a *theoretical* claim; the empirical question is whether the LFM head, trained on Phase A + Phase B, actually learns to express contradictions as bifurcations rather than as some other failure mode (e.g. extended oscillation, premature convergence to one of two basins).

**The v2 research question:** in the trained MNLM, does the trajectory entropy and bifurcation count *correlate* with the actual presence of contradictions in the output `MeshDelta`? If yes, the post-hoc immune system can rely on `TrajectoryMetadata` as a contradiction detector; if no, the metadata is uninformative and the immune system must continue with structural inspection of committed primitives.

**The v2 experiment:** seed the MNLM with synthetic contradictions and synthetic non-contradictions (matched difficulty); measure correlation between `trajectory.bifurcations_observed` and the binary contradiction label. Cost: ~10 GPU-hours.

### 9.5 The 512-relation codebook composition [RESEARCH]

§3.5 commits to a 512-entry codebook bootstrapped from Kadmos's emergent relation clusters. The exact composition is not yet determined. This is a near-term Talos task during week 1, but the question of whether 512 is the right cardinality (vs 256, 1024, dynamic growth) is open.

**The v2 research question:** does codebook cardinality measurably affect MNLM accuracy on direction-critical questions? Specifically: at what cardinality does the codebook become a *bottleneck* (too few entries to express needed nuance) vs *noise* (too many entries, model confuses similar ones)?

**The v2 experiment:** train v1 variants at codebook cardinalities {128, 256, 512, 1024, 2048}; evaluate on MuSiQue direction-critical subset; find the sweet spot. Cost: ~150 GPU-hours (substantial, because each variant is its own Phase A + Phase B run).

### 9.6 Mode collapse in the LFM head [RESEARCH]

The LFM head's risk profile (§3.3 [RESEARCH] flag) includes mode collapse: if Graph-GRPO over-rewards one or two `MutationPrimitive` kinds (most likely `EmitActivationPacket`, the cheapest), the LFM trajectory may collapse to always navigating toward those basins regardless of input.

**The v1 mitigation:** per-primitive frequency rebalancing in the loss, primitive-class-balanced sampling in training (covered in §5.2 implementation but not yet tuned).

**The v2 research question:** at production scale, does the rebalancing prevent collapse? If yes, the v1 mitigation is sufficient. If no, what additional regularisation is needed — KL penalty against a primitive-distribution prior? Curriculum that introduces rarer primitives later?

**The v2 experiment:** measure the empirical primitive distribution on 10 k unseen `MeshInput`s; compare to the corpus's natural primitive distribution; flag mismatches > 2× as collapse signal.
---

## 10. Three concrete next commits — Step-S5 Sprint-1 candidates for Talos

These are the three commits Hesiod recommends as the first Sprint-1 PRs **within Step S5 of the migration plan**. They are atomic, each one lands without depending on training results, and they require Migration-Plan Steps S1–S4 to have merged on `main` first. Until S1–S4 land, this list is the post-S4 to-do; it is not the next immediate work.

1. `feat(mesh-mnlm): add MeshInput, MeshDelta, MutationPrimitive, TrajectoryMetadata Pydantic v2 schemas under src/theogony/mesh/mnlm/dto.py with extra="forbid", ULID-pattern IDs, multi-vector node payload per MESH_SUBSTRATE.md §"Node anatomy", quantitative-core-plus-optional-descriptor edge shape per MESH_SUBSTRATE.md §"Edge anatomy", model_validator graph-integrity check, sealed mutation union via Discriminator+Tag, round-trip tests against the MESH-substrate ChunkNode / ConsolidatedNode / Edge types from Step S1, and import-linter contract in pyproject.toml forbidding text-generation imports from src/theogony/mesh/mnlm/.`

2. `feat(reporting): add MnlmRunReport sibling under src/theogony/reporting/models.py with verdict heuristics (mutation_budget_exhaustion → 'partial'; lfm_failed_convergence → 'failed'; primitive distribution telemetry; trajectory_entropy aggregates; substrate-write counts so the immune system can correlate MNLM activity with downstream agent-cleanup events).`

3. `feat(mesh-mnlm): scaffold GraphProjector + Graph-KV adapter + LFM-GAE decoder head + SubstrateResonantRunner wrapping Llama-3-8B-Instruct with rank-16 LoRA on q/k/v/o, no training in this commit — just shape, smoke test against an in-substrate toy mesh, and a minimal reproducible inference example. Include a Phase-A training stub that loads (MeshInput, MeshDelta) pairs from the post-MESH Kadmos-v2 substrate-write stream.`

After these three: weeks 3–4 of S5 (substrate-resonant recurrence wiring + MeshInput projector) per §8.
---

## 11. What this brief is NOT

- **It is not the Nous brief.** Nous is the first concrete role that the MNLM primitive will be deployed in. The Nous brief — control loop, write permissions on the Chronik, trigger conditions, role-specific `aux` keys, deployment topology — is written *after* Talos's v1 ships and Stage-2 falsifier passes. Hesiod will file it then. Until then, the v1 MNLM service operates with the generic role; Nous is a configuration, not a separate codebase.

- **It is not the Oneiros or Kalypso brief.** Both will be written after Nous v1 ships and the project has empirical evidence about what MNLM-class deployment actually needs. The v1 schemas (`MeshInputContext.role` accepts "oneiros" and "kalypso" already) leave room for them; the actual deployment specs come later.

- **It is not an egress-agent brief.** Egress (the language-out boundary) is explicitly out of scope for this brief and for v1. If the MNLM works, egress is downstream and tractable. If it doesn't, egress is irrelevant. The project is not thinking about egress now.

- **It is not a substrate redesign.** The MESH triplet ([MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md) + [MESH_IMPLEMENTATION.md](../MESH_IMPLEMENTATION.md) + [MESH_RETRIEVAL.md](../MESH_RETRIEVAL.md)) is operative; TARGET_ARCHITECTURE.md is the architectural floor underneath it. LanceDB columnar nodes + PyTorch sparse CSR edges + batched-SpMV Spreading Activation are not under review by this brief. The MNLM uses the substrate; it does not replace it.

- **It is not a Kadmos rewrite.** The §7 amendment is structural-only: a final post-embedding projection step. Kadmos's reading-loop architecture is unchanged.

- **It is not a final answer.** Three sections are explicitly [RESEARCH]; six v2 research questions are queued. Hesiod's job is to lock the architecture *enough* that Talos can build, *not* to pretend uncertainty does not exist. The uncertainty is the design, in those sections.

- **It is not a manifesto.** It is a binding decision document with research-mode subsections. The radical commitment in §0 is a commitment to *build*, not to *believe*. The §6 falsifier stack ensures that what is built can be measured against what was claimed.
---

## 12. Hand-off to Talos

This brief is the binding architecture decision. Talos's job, **once Migration-Plan Steps S1–S4 have landed**:

1. Read this document. Read [AGENTS.md](../../AGENTS.md), [MESH_SUBSTRATE.md](../MESH_SUBSTRATE.md), [MESH_IMPLEMENTATION.md](../MESH_IMPLEMENTATION.md), [MESH_RETRIEVAL.md](../MESH_RETRIEVAL.md), [MESH_MIGRATION_PLAN.md](../MESH_MIGRATION_PLAN.md), [BUILD_DOCTRINE.md](../BUILD_DOCTRINE.md), and the Round-1 artifacts in `docs/research/mnlm/`.
2. Open a branch `feat/mesh-s5-mnlm-scaffolding` and land the three §10 commits as separate atomic PRs against `main`.
3. Proceed week-by-week per §8. At each research checkpoint (W4, W6, W8, W10, W12 of S5), commit a `MnlmRunReport(verdict=...)` artifact to `docs/research/mnlm/poc_mesh/checkpoints/W<N>.md` documenting the outcome and the decision taken.
4. If a checkpoint triggers a fall-back (W6 < 80 %, W8 LFM divergence, W10 MuSiQue failure), do not silently re-architect. File a Phoenix Backlog ticket (PHX-1000+) against this brief, escalate to Daedalus, and wait for an amended brief before continuing. Honest-failure ([BUILD_DOCTRINE.md](../BUILD_DOCTRINE.md)) is non-negotiable here.
5. When the W12 Stage-3 falsifier passes (or fails), file the result and stop. The Nous brief comes next on top of the now-empirically-grounded MNLM primitive.

This brief lives at `docs/etappes/mesh_native_lm_brief.md`. It is the operative MNLM document, realigned to the MESH triplet on 2026-05-13. The research brief that triggered this work ([mesh_native_lm_research_brief.md](mesh_native_lm_research_brief.md)) remains as the question source; this document is the answer.

The five Round-1 artifacts in `docs/research/mnlm/` are preserved as input. They are not superseded; they are inputs to this synthesis. Future agents auditing this decision can replay the synthesis from those artifacts plus the verified literature floor in §2, *with the MESH-doctrine realignment applied per the banner at the top of this brief*.

---

## 13. Sponsor-Track: Minimal PoC Pass

> **Status: pre-MESH PoC executed; post-MESH PoC pending Steps S1–S3.** The PoC defined in this section was executed against the Gen-1 substrate before the 2026-05-13 MESH pivot. Its artefacts — Phase-A loss curve, Phase-B Micro-GRPO reward curve, Mini-DBB-20 / Mini-MuSiQue / Mini-Monkey-3 evaluations, end-to-end pipeline trace — are preserved at `docs/research/mnlm/poc_legacy/` and remain valid as an *existence proof for the Gen-1 stack*. They do **not** validate the post-MESH architecture, because the substrate they ran against (single embedding per node, no frame vectors, no eager linking, no source-anchor entities, "no text in mesh" misread as "no text at all") is the substrate the migration plan is replacing. The post-MESH PoC track lives at `docs/research/mnlm/poc_mesh/` and is awaiting Steps S1–S3 of the migration plan; its README spells out what carries forward and what must be re-run. The subsections below define the *shape* of a minimal-PoC pass; the post-MESH PoC follows that shape with substrate-appropriate substitutions.

**Purpose:** Before the full §8 sprint is feasible, the project needs to demonstrate that the architecture is buildable and that the key signals exist. This section defines a minimal, budget-constrained pass through the entire pipeline — not to produce a trained MNLM, but to produce evidence sufficient for a compute-sponsor pitch.

The §8 roadmap is not modified. The PoC pass is a precursor to it, executed with reduced corpus, reduced training steps, and reduced model size where permitted.

### 13.1 What the PoC pass proves — and does not prove

**Proves:**
- The Graph-KV adapter integrates with a frozen Llama-class base model without numerical degeneration
- The LFM-GAE decoder head produces `MeshDelta` objects that pass Pydantic validation at the sealed-union level
- The Substrate-Resonant Recurrence loop runs within the latency budget (~25–100 ms per SA call) on the existing `TensorMeshEngine`
- Phase A loss decreases monotonically on the micro-corpus (the supervised signal is real)
- The Phase B SA-alignment reward discriminates between better and worse candidate deltas (the RL signal is real)
- Directional binding accuracy is above chance on Mini-DBB-20 (the architecture is not structurally broken)
- The end-to-end pipeline executes: Kadmos article → `MeshInput` → MNLM → `MeshDelta` → SA query → activation result

**Does not prove:**
- That the model meets the §6 falsifier thresholds (95 % DBB-200, MuSiQue within 5 pt, Monkey-3 > baseline)
- That the LFM head converges stably at production corpus scale
- That Phase B GRPO training converges to a good policy
- Any production-readiness claim

The PoC pass is an existence proof, not a quality proof. The quality proof is §8.

### 13.2 Scaled-down execution plan

| Step | §8 Full Scale | §13 PoC Scale | Compute |
|---|---|---|---|
| Schemas + scaffolding (§10 W1–2) | Full — unchanged | **Identical to §8.** No compromise on schemas. | 0 GPU-h |
| Graph-KV + Recurrence smoke test | Llama-3-8B-Instruct, FP16 | **Llama-3.2-1B** (4-bit quant), forward pass only. | ~1–2 GPU-h |
| Kadmos amendment (§7, W4) | Full amendment, 200 LoC | **Identical to §8.** Contract compliance is not scaled. | 0 GPU-h |
| Phase A micro-training (W5–6) | 10 k articles, ~5 M pairs, 1 epoch | **200 articles, ~50 k pairs, 2 000–5 000 gradient steps.** Convergence not required; loss must decrease. | ~5–10 GPU-h |
| Mini-DBB-20 (instead of DBB-200) | 200 pairs, ≥ 95 % target | **20 pairs, target: accuracy > 60 % (above chance).** Not a pass/fail gate — a direction signal. | ~1–2 GPU-h |
| Phase B micro-GRPO (W7–8) | 50 k episodes, K = 8 | **1 000 episodes, K = 4.** Goal: reward mean rises over first 500 episodes. | ~5–10 GPU-h |
| Mini-MuSiQue (50 questions) | 500 questions, two thresholds | **50 questions, no hard threshold.** Record accuracy; note direction vs text-RAG baseline. | ~1 GPU-h |
| Mini-Monkey-3 (10 pairs, 2 raters) | 100 pairs, 5 raters, κ ≥ 0.7 | **10 pairs, 2 raters, qualitative only.** No statistical significance test. | 0 GPU-h + ~2 h human time |
| **Total** | **280–520 GPU-h, ~850–1 600 EUR** | **~15–25 GPU-h, ~15–50 EUR** | |

### 13.3 Model choice for the PoC

§3.1 locks **Llama-3-8B-Instruct** as the production base model. That decision is not changed.

For the PoC pass, **Llama-3.2-1B** (or equivalent 1 B-class open-weights model) is permitted as the pipeline validator. Rationale: the PoC is testing whether the *stack* runs, not whether the *model* meets the §6.1 directional-binding threshold. A 1 B model is expected to produce weaker binding accuracy than 8 B — this is acceptable at PoC scale. The jump to 8 B is the first thing the sponsor budget buys.

If the PoC uses a 1 B model, the Mini-DBB-20 result must be reported as "1B-class model, not directly comparable to §6.1" in the `MnlmRunReport`. Do not report it as a scaled-down version of the Stage-1 falsifier — it is a pipeline smoke test, not a falsifier result.

### 13.4 Output artifacts the PoC must produce

Talos commits the following to `docs/research/mnlm/poc_mesh/` after the post-MESH PoC pass (the pre-MESH Gen-1 PoC artefacts of the same name are at `docs/research/mnlm/poc_legacy/`):

1. `mesh_run_report.md` — a `MnlmRunReport`-structured narrative covering: which model was used, how many training steps, Mini-DBB-20 accuracy, Phase B reward curve (start vs end), Mini-MuSiQue result, Mini-Monkey-3 qualitative notes, honest failure modes observed, comparison vs. the Gen-1 baseline at `docs/research/mnlm/poc_legacy/poc_run_report.md`, and an explicit statement of what the PoC does and does not prove.
2. `mesh_pipeline_trace.json` — one end-to-end trace: a single Kadmos-v2 article ingested into the MESH substrate, a single `MeshInput` projected, a single `MeshDelta` emitted, a single Spreading-Activation result returned. Stored as a reproducible fixture for sponsor demonstrations.
3. `mesh_reward_curve.png` — the Phase B micro-GRPO reward curve (1 000 episodes) against the MESH substrate's SA primitive. A rising curve is the signal; a flat or falling curve is a finding that requires investigation before the sponsor pitch.
4. `comparison_vs_legacy.md` — explicit before-and-after numbers vs. the Gen-1 baseline. This is the document that demonstrates the MESH-substrate's superiority for MNLM training (or, honestly, its parity / inferiority, if the signals are weaker).

### 13.5 Sponsor handoff

After the PoC artifacts are committed, the human commander reviews `mesh_run_report.md`. If the pipeline ran and the signals are directionally positive (loss fell in Phase A, reward rose in Phase B, Mini-DBB-20 > 60 % on the post-MESH substrate, comparison-vs-legacy shows at least parity), file a Phoenix Backlog ticket (PHX-1000+) `PHX-####: sponsor compute acquisition for MNLM §8 full run` with the PoC artifacts attached as evidence. Then wait for compute access before executing §8.

If the post-MESH PoC produces a negative signal (loss does not fall, reward is flat, Mini-DBB-20 ≈ 50 %, comparison-vs-legacy shows regression), do not pitch the sponsor. File a Phoenix Backlog ticket against this brief and escalate to Daedalus. The PoC has done its job: it found the failure cheaply, before spending 1 600 EUR on a broken design.

---

*Hesiod withdraws. The architecture belongs to Talos and to the experiments that decide §8 W6, W10, W12 — and, before those, to Migration-Plan Steps S1–S4 that produce the substrate the experiments run against, and to the post-MESH PoC pass in §13 that earns the right to run them.*
