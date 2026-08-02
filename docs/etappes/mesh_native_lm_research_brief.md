# Research brief — the Mesh-Native Language Model (MNLM)

**Status:** **Superseded by [`mesh_native_lm_brief.md`](mesh_native_lm_brief.md) as the operative document (2026-05-10).** This research brief remains as the *question source* — the prompt that triggered Round-1 parallel research and the five artifacts in `../research/mnlm/`. The five artifacts plus the verified literature floor were synthesised into the binding architecture brief; read that for the answer. This brief stays here for audit / replay of the synthesis.

**Original status:** Research order for in-repo agents (Cursor, Codex, Claude Code, Cline, …). **Not** an implementation plan. **Not** a substitute for [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md), [`docs/etappes/kadmos_v2_brief.md`](kadmos_v2_brief.md), or any Daedalus planning document.
**Filed by:** Chaos (vision / reflection role) — handoff to many parallel research agents, then to Hesiod for synthesis, then to Talos for any implementation that follows.
**Date:** 2026-05-10
**Companion (sister doc):** [`notes/deep_research/run12_brief.md`](../../notes/deep_research/run12_brief.md) — the same question phrased self-contained for external research agents (Gemini Deep Research, Manus, Perplexity Pro). When in doubt, the two briefs must agree on the **question**; the in-repo brief is the binding one for what an answer must respect to be merge-relevant.

---

## 0. Why this brief exists

The repository already binds three things tightly:

- **The substrate.** [`TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md): vectors + typed weighted edges, LanceDB + PyTorch, Spreading Activation, no text after Kadmos. Decided.
- **The ingress.** [`kadmos_v2_brief.md`](kadmos_v2_brief.md): an LLM-with-working-memory that *reads* a text source and emits a labeled intermediate, which is then collapsed into vectors by an internal embedding pass. Decided as architecture, in implementation.

Everything *after Kadmos and before any future egress* is unbuilt and underspecified: Nous (synthesis), Oneiros (consolidation), Kalypso (emergent discovery), plus a list of agents we have not yet named. The far-future translation of a constellation back into human language is explicitly out of scope here — if MNLMs work, that egress is tractable downstream; if they don't, it doesn't matter. We are not thinking about it.

These mesh-internal agents share one structural property, and it is the property no other layer has:

> **Their primary input is a vector subgraph. Their primary output is a vector subgraph. Text is never their internal medium.**

That is the language model class this brief asks the agent population to characterise.

The reason this is one brief and not five is simple. Every "Chronik agent" we will ever need (Nous, Oneiros, Kalypso, future agents we have not named) is a specialisation of the same underlying primitive: a model that natively consumes and produces mesh. If we build that primitive once, the agents are configurations of it. If we build five of them as bespoke pipelines, we build five RAG stacks dressed in mythological clothing.

We call this primitive the **Mesh-Native Language Model (MNLM)** — a language model whose primary I/O is a vector subgraph of a *semantic* knowledge mesh (the Chronik). For the namespace collision with 3D-mesh-generating LLMs (LLaMA-Mesh, MeshGPT, MeshLLM) and with distributed-inference mesh networks (the `Mesh-LLM/mesh-llm` GitHub project), see §3.5.

Nous is, by this brief's definition, an MNLM. Not "an LLM that produces synthesis nodes", not "a GNN with a language model attached" — an MNLM. Oneiros and Kalypso are MNLMs too. They are different *roles*; the *class* is one. The first MNLM the project actually builds will be Nous, but the architecture comes first; the Nous brief comes after.

---

## 1. The question — one sentence

> **What does a language model look like whose primary input and primary output are vector subgraphs of the Chronik, with text retained only at the outermost ingress (Kadmos) — and explicitly not as its internal medium of representation, reasoning, or inter-agent communication?**

Everything below is in service of producing a well-grounded, falsifiable answer to this.

---

## 2. Where the MNLM sits in the pipeline

```
World text (Wikipedia, books, web)
    │
    ▼
KADMOS v2 ─── translation layer ──────────────── decided (kadmos_v2_brief.md)
    │   text → labeled intermediate → embedding pass → vector mesh
    │   labels transitional, vectors final
    │
    │   ┌──────────────────────────────────────────────────────────┐
    │   │ KADMOS-OUTPUT  ≡  MNLM-INPUT                             │
    │   │ The post-embedding shape Kadmos emits IS the binding     │
    │   │ contract this brief asks the field to specify. Kadmos    │
    │   │ conforms to the MNLM input schema — not the reverse.     │
    │   └──────────────────────────────────────────────────────────┘
    ▼
                ┌──────────────────────────────────────────┐
                │  CHRONIK — vector substrate              │
                │  LanceDB columnar store +                │
                │  PyTorch CSR tensor at runtime           │
                │  (decided — TARGET_ARCHITECTURE.md)      │
                └──────────────────────────────────────────┘
                   ▲                                   ▲
                   │                                   │
   ┌───────────────┘                                   └───────────────┐
   │                                                                   │
   ▼                                                                   ▼
NOUS  (first MNLM instance)                                       ONEIROS / KALYPSO  (further MNLM roles)
input:  vector subgraph                                           input:  activation patterns / subgraphs
output: denser vector subgraph                                    output: new edges, new
        (synthesis nodes,                                                  syntheses, demoted
         diagonal edges,                                                   weak nodes
         revisions)
                                       ▲
                                       │
                          (other mesh-native roles
                           we have not yet named)

   ⋯ at some far boundary, language eventually leaves the substrate again
   (egress; explicitly out of scope for this brief).
```

The MNLM is the **shared family** that powers everything inside the active region. It is not Nous specifically; it is what Nous, Oneiros, Kalypso, and the as-yet-unnamed agents instantiate. Each of those is a *role* (a deployment, a budget, a control loop, a permission set on the substrate). The *class* is the MNLM.

This brief is **not** a brief for any one role. It is a brief for the **architectural primitive** they all share. A separate Hesiod brief will, downstream, take this synthesis and turn it into the first concrete MNLM the project builds — almost certainly Nous, since Nous is what the substrate is missing most urgently after Kadmos lands.

---

## 3. What is binding (do not reopen)

These are not under research. If your proposal contradicts them, mark the contradiction explicitly and route it to a Phoenix Backlog ticket (`PHX-####`) for Daedalus review. Do not silently route around them.

1. **No text storage after Kadmos.** Source-anchor IDs (URL + timestamp) exist for the immune system. Nothing else. Strings are not knowledge.
2. **No Neo4j / Cypher path for the core mesh.** [`RETIREMENT_NEO4J_MULTIHOP.md`](RETIREMENT_NEO4J_MULTIHOP.md). LanceDB-on-disk + PyTorch-CSR-at-runtime is the substrate.
3. **Spreading Activation is the retrieval primitive.** Not kNN-only. Not multi-hop Cypher. Spreading Activation as `SpMV` over the typed weighted edge tensor.
4. **Schemas are Pydantic v2, `extra="forbid"`.** All MNLM input/output DTOs must be Pydantic v2 models, not ad-hoc dicts. [`AGENTS.md`](../../AGENTS.md) §1.
5. **RunReports are mandatory.** Any non-trivial MNLM operation produces an `IngestRunReport` / `QueryRunReport` / `OneirosTickReport` / a new sibling type with a structured `verdict`. [`AGENTS.md`](../../AGENTS.md) §2.
6. **Honest-failure, not pre-validation.** [`BUILD_DOCTRINE.md`](../BUILD_DOCTRINE.md). MNLM proposals must not introduce content gates. Imperfect mesh writes are fine; silent crashes are not.
7. **No human in the substrate path.** [`BUILD_DOCTRINE.md`](../BUILD_DOCTRINE.md) §6. Anything an MNLM produces that requires a human reviewer to advance is doctrine-violating.
8. **Function-First Phase doctrine still rules.** Numeric SLAs do not get prescribed up front; they emerge from running stacks. Mass first, polish later.
9. **Pre-gates judging content are forbidden.** [`IMMUNE_SYSTEM.md`](../IMMUNE_SYSTEM.md). MNLM proposals that depend on a synchronous correctness filter before accepting a mesh-chunk are doctrine-violating.

You have considerable creative freedom *within* these constraints. The list below is the part of the design surface you are explicitly invited to explore.

---

## 3.5 Prior art and the naming collision — what an MNLM is **not**

The phrase "Mesh + LLM" is already taken in two unrelated research lines. Both share surface vocabulary; neither shares architecture or purpose with what an MNLM does. Name them so external readers do not collapse the concept, and so we cite the parts of their work that *do* transfer as **technique-precedent** rather than as architectural ancestry.

### 3.5.1 Three-dimensional geometric mesh generation (LLaMA-Mesh / MeshGPT / MeshLLM)

| Work | Citation | What it does |
|------|----------|--------------|
| **LLaMA-Mesh** | NVIDIA + Tsinghua, arXiv 2411.09595, Nov 2024 | Fine-tunes LLaMA to generate 3D triangle meshes (vertex coordinates, face indices) **as plain text tokens**, with no vocabulary expansion. Unified text-and-mesh chat model. |
| **MeshGPT** | Siddiqui et al., CVPR 2024, arXiv 2311.15475 | Decoder-only transformer (no pre-trained LM) that autoregressively generates triangle meshes via an **RQ-VAE codebook of geometric primitives**. |
| **MeshLLM** | Fang et al., ICCV 2025, arXiv 2508.01242 | Successor to LLaMA-Mesh. Two contributions: **Primitive-Mesh Decomposition** (split a 3D mesh into structurally meaningful sub-units, scaling the dataset ~50×) and improved topology inference from vertex connectivity. |

Their domain is **computer graphics — 3D content generation**. The "mesh" is a Blender / OBJ-style geometric model. Their language model emits *spatial geometry*. Our language model emits *semantic structure*. The vocabulary is the same; the medium is different.

**What transfers as technique-precedent** (cite, do not adopt as architecture):

- **LLaMA-Mesh's plain-text-token serialisation** is direct precedent for our §4.1 candidate "Eulerian / Hamiltonian path serialisation". Same trick applied to a different structured object: tokenise the structure as text, fine-tune a frozen LM, no vocabulary expansion. We can do this with `(node_id, embedding_quantised, edge_id, target_id)` quadruples instead of `(vertex_x, vertex_y, vertex_z)` triples.
- **MeshGPT's RQ-VAE codebook** is direct precedent for our §4.2 candidate "learned codebook of structural primitives". Same trick: train an RQ-VAE to compress complex structural primitives into a discrete codebook, train the LM to predict codebook tokens. For us the primitives are typed edge-with-context patterns, not triangles.
- **MeshLLM's Primitive-Mesh Decomposition** is direct precedent for our §4.10 (granularity) — break a large knowledge mesh into semantically self-contained sub-units the MNLM consumes one at a time, exactly as MeshLLM breaks a large 3D mesh into bounded structural primitives.

A research artifact may cite these works as **method ancestors for tokenisation and decomposition**. It must not cite them as architectural ancestors for the MNLM. Their job is graphics; ours is knowledge.

### 3.5.2 Distributed inference mesh networks (`Mesh-LLM/mesh-llm`)

The `github.com/Mesh-LLM/mesh-llm` project (Apache-2.0, ~942 ★ as of May 2026) is a **distributed LLM inference system**. It pools GPU capacity across machines, exposes an OpenAI-compatible API on `localhost:9337`, splits dense models via pipeline parallelism, and routes requests across a network mesh of compute nodes. Petals-class. Llama.cpp under the hood.

The "mesh" here is a **mesh network of compute nodes**, not a graph data structure. The project has no architectural overlap with what we are doing; its only possible relevance to Theogony is as a *deployment substrate* one day, when MNLMs need to run distributed.

Mention only for disambiguation. Do not cite as architectural precedent of any kind.

### 3.5.3 What the MNLM **is**, restated against the collision

A Mesh-Native Language Model in the Theogony sense is a language model whose primary input and primary output are **vector subgraphs of a semantic knowledge mesh** (the Chronik). The mesh is typed weighted edges over node embeddings, encoding meaning. Not 3D geometry. Not a compute network. Meaning, in the medium meaning is computed in.

We keep the term MNLM despite the collision because (a) the acronym MNLM itself is not used by any of the cited prior art, (b) "Mesh-Native" cleanly captures the substrate-orientation stance, and (c) the alternative names are worse. On first reference in any external publication or external brief, spell out "Mesh-Native Language Model (semantic-mesh substrate; not 3D geometry, not a compute mesh)".

---

## 4. Where the design surface is open

These are the substantive open questions. Each is research-shaped, not yes/no. Pick the ones your branch will address; you do not have to answer all of them in one document.

### 4.1 Input format — and the binding contract with Kadmos

What does it mean to "give a vector subgraph to a language model"?

- **Continuous soft prompts.** Project nodes and edges into the model's embedding space and prepend them as continuous tokens. Decoder reads them as if they were prefix context. Survey: Graph Neural Prompting (GNP), Q-Former-style adapters, prompt embedding APIs (e.g. vLLM `prompt_embeds`).
- **KV-cache injection.** Build the subgraph's representation directly into the model's attention KV-cache, bypassing the embedding layer. Survey: LatentMAS, Cache-to-Cache (C2C / KVComm).
- **Eulerian or Hamilton-path serialisation.** Linearise the subgraph into a reversible token sequence (Graph Eulerian Transformer / GraphGPT-style). Lossy in topology but compatible with stock causal LMs. *This is the same architectural trick LLaMA-Mesh / MeshLLM use for 3D geometry — see §3.5.1 — applied to a different structured object.*
- **Adjacency-tensor as a sparse positional encoding.** Treat the subgraph adjacency matrix as a structural prior added into self-attention scores (graph-attention biasing).
- **Hybrid.** Continuous prefix for content, sparse attention bias for topology, KV-injection for "warm" working memory.

The question your design must answer: **does the MNLM see edges as first-class signal, or does it see edges only through a flattened token sequence?** Pick one. Defend it with a falsifier.

#### The Kadmos contract

The shape you specify here is **not just an MNLM input format**. It is the **binding interface between Kadmos and every MNLM-class agent in the system**.

Kadmos v2 ([`kadmos_v2_brief.md`](kadmos_v2_brief.md) §4) currently produces, after its internal embedding pass, a vector mesh of:

- concept nodes with embeddings, activation weights, revision history,
- understanding edges whose embedding is the embedding of the LLM-authored connection-description sentence,
- synthesis nodes with computed positions in vector space.

That post-embedding shape is *informally* described in the Kadmos brief because the MNLM-side of the interface has not been specified yet. Your job here is to specify it. Once the MNLM input schema is fixed by the synthesis of this research round, the Kadmos v2 brief receives a closing amendment that locks Kadmos's embedding-pass output to exactly that shape.

**Direction of compliance:** the MNLM input schema is the contract. Kadmos conforms. *Not the reverse.* This is because the MNLM is the harder, newer, more constraining end of the interface, and because every other MNLM role (Oneiros, Kalypso, …) reads from the same substrate and therefore needs the same input shape. There is one mesh schema in the system, and the MNLM defines it.

A research artifact must therefore specify `MeshInput` in §D as a Pydantic v2 model that **a Kadmos embedding pass can produce without contortion**. If your design's `MeshInput` requires a structure Kadmos cannot reasonably emit (e.g. requires per-node attention weights from a frontier LLM's hidden state at write time, which Kadmos does not have), declare that as a Risk in §I and propose how Kadmos's pipeline would have to change.

### 4.2 Output format

What is a "mesh-out" actually?

- **Subgraph delta.** A list of additions / mutations / supersessions: new node embeddings, new typed edges, revisions of existing nodes (analogous to Kadmos v2's `revisions` field).
- **Activation pattern.** A function over existing nodes (an energy distribution), which a downstream consolidation step turns into edge updates. Hebbian-shaped.
- **Latent-token stream that a graph decoder reverses.** The MNLM emits special latent tokens; a graph-decoder head turns them into structural changes. Survey: G2GT (Graph-to-Graph Translator), latent-flow-matching for structural prediction.
- **A new constellation.** A bounded subgraph "as such", bundled with provenance and a confidence per element, written to LanceDB by an export step.

Your design must specify: **the Pydantic shape of one mesh-output unit**. The shape is the contract.

### 4.3 Inter-agent communication

Two MNLMs talking to each other. Today, agents talk by writing English. That is RAG-thinking on the inside.

Open: continuous KV-cache exchange (LatentMAS / C2C), shared write-into-the-Chronik-and-let-Spreading-Activation-do-the-talking, or a typed "activation packet" DTO that two MNLMs both understand. Specify which, and what the bandwidth and loss profile is. The repository's principle is *Vector-Vector-Mesh* ([`CHRONICLE_PRINCIPLES.md`](../CHRONICLE_PRINCIPLES.md) Non-Negotiable 10) — anything where agents internally exchange free prose is, by doctrine, the wrong shape.

### 4.4 Training signal

A model whose output is a vector subgraph has no obvious next-token target. What does it train against?

- **Self-supervised graph completion.** Mask edges, predict them. Cheap, but teaches topological pattern-matching, not synthesis.
- **Trajectory-based RL with structural reward.** Reward syntheses that increase the reachability or compressibility of the graph; penalise contradictions surfaced later by Athene-light. Survey: Latent-GRPO, latent flow matching with intrinsic uncertainty.
- **Self-distillation against an oracle stack.** Use a frontier text-LLM-with-RAG as the teacher; train the MNLM to recover its inferences from mesh inputs alone. The teacher disappears; the MNLM keeps the inference behaviour.
- **Spreading-Activation alignment.** Train the MNLM to produce mesh deltas such that, after Spreading Activation, target probes activate the intended subgraph. The retrieval primitive itself becomes the loss.

Pick one and commit. State the training-data shape (synthetic? bootstrapped from Kadmos v2 outputs? Wikipedia-derived?). State the cost ballpark. State the falsifier.

### 4.5 Frozen-LLM adaptation path

Training an MNLM from scratch is out of scope for this repository. The realistic question is: which **frozen pretrained LLM** can be cheaply adapted to read and write meshes, and how?

- **LoRA / prefix-tuning on a Llama-3 / Qwen-3 / Gemma class model.** Freeze the body, train a thin set of adapter weights to handle the mesh prefix and the latent output tokens.
- **Soft-prompt / Q-Former style projection.** A small projection MLP turns a `(node_embedding, edge_embedding)` graph into a sequence of continuous tokens the frozen LLM ingests as prefix.
- **No adaptation at all — purely prompted continuous context.** Use a model whose API exposes a continuous-prompt interface and treat the MNLM as a *protocol* on top of an unmodified base LM.

Your design must say: **what is the smallest integration that can ship?** That is the shape Talos will eventually build.

### 4.6 The boundary text channel — and how it stays narrow

The MNLM family must retain *some* text I/O at the *outermost* boundaries — not as part of any internal MNLM reasoning step, but as a separate, narrow, structurally isolated channel:

- **Bootstrap supervision.** During development, debugging a mesh-only output is brutal. A "translation peephole" — a thin channel that turns a mesh-output fragment into a human-readable summary on demand — must exist for the agent's own development cycle.
- **Eventual external boundary.** At some far horizon language has to leave the substrate again for human consumption. This is an entirely separate concern (the egress agent), explicitly out of scope for this brief, and its design comes *after* MNLMs work, not in parallel with them. Do not waste design budget on it here.

The hard rule for any MNLM proposal: **the text channel does not leak inside.** No agent-to-agent communication runs through it. No internal reasoning step uses it. Specify the architectural feature that enforces this — interface-level, type-level, or runtime-level. A doctrine assertion is not enough; the contract has to be machine-checkable.

### 4.7 Latent reasoning step

Inside the MNLM, between input mesh and output mesh, the model has to *think*. The question is whether thinking has to be linguistic.

Survey:

- **COCONUT (Meta FAIR, 2024).** Continuous-thought recurrence: the final hidden state is fed back as the next input embedding without ever being decoded into a token. Reasoning happens entirely in latent space.
- **AdaAnchor / SeLaR / CoLaR (2024–2026).** Entropy-gated continuous reasoning to prevent premature collapse into greedy token paths.
- **Latent chain-of-thought as superposition.** Continuous states encode multiple alternative reasoning trajectories simultaneously; emergent breadth-first search on planning tasks.

A real MNLM proposal must explain whether its internal reasoning step is text-CoT, latent-CoT, both, or alternation between them as a function of confidence / entropy. State why.

### 4.8 Operations on the mesh — what an MNLM is allowed to do

An MNLM does not have unbounded write access. The doctrine of post-hoc immune defense ([`IMMUNE_SYSTEM.md`](../IMMUNE_SYSTEM.md)) replaces synchronous pre-gates, but it does not replace *typed mutation contracts*. Specify exactly which mutation primitives an MNLM emits:

- `ADD_NODE` (vector + minimal provenance)
- `ADD_EDGE` (typed, weighted, optionally vectorised)
- `REVISE_NODE` (supersedes a prior node; never an in-place overwrite)
- `MERGE_NODES` (with rationale embedding)
- `SPLIT_NODE` (one becomes two)
- `INVALIDATE` (mark wrong, preserve provenance, trigger immune-system review)
- `EMIT_FINDING` (the MNLM's own immune-system output, e.g. "this subgraph contradicts itself")
- `EMIT_ACTIVATION_PACKET` (energy redistribution without structural change — Hebbian)

Pick the canonical set. Justify what is missing. Explicitly: **the MNLM cannot delete.** Deletion is Chronos's job ([`IMMUNE_SYSTEM.md`](../IMMUNE_SYSTEM.md)).

### 4.9 Working memory inside the MNLM

Kadmos v2 already established that *reading* needs working memory. Does *thinking* need a different one?

A Nous-class MNLM does not "read in time" — it consumes a subgraph atemporally. But Oneiros and Kalypso may *iterate*: Spreading-Activation cycle 1 produces a constellation, the MNLM proposes mesh deltas, cycle 2 runs over the updated mesh, etc. Specify whether the MNLM holds working memory across cycles, or whether each cycle is stateless and the substrate carries the state.

### 4.10 Granularity

When does the MNLM run? On every Kadmos write? On a triggered probe? Continuously in the background? Specify a control-plane shape — at minimum:

- the **trigger** (event-driven? scheduled? operator-initiated?)
- the **scope** (which subgraph the agent is allowed to read and to modify)
- the **budget** (compute, mutations per call, depth of Spreading Activation)
- the **commit boundary** (when does an MNLM call finish — is it a transaction?)

The substrate is append-only and locks-free. The MNLM contract has to live with that.

---

## 5. What an answer looks like

You are *not* writing an essay. You are writing a **research artifact** that another agent in this repo can pick up and turn into an implementation plan or a falsifiable experiment. Each agent produces **one** document, in the shape below.

### Required content

| # | Section | Minimum content |
|---|---------|-----------------|
| 0 | **Header** | At the very top of the file: `Model: <name + slug>`, `Date: <today>`, `Filed by: <model name>`, `Brief: docs/etappes/mesh_native_lm_research_brief.md`. |
| A | **Three-sentence summary** | The architecture choice, the training signal, the falsifier. |
| B | **Scope statement** | Which of §4.1–4.10 you are addressing. Which you explicitly leave to others. |
| C | **Architecture proposal** | Concrete model class, adaptation path, parameter count band, memory profile. Diagram allowed. |
| D | **I/O schema** | At least two **complete Pydantic v2 models**: `MeshInput` / `MeshOutput` (or your renaming). `ConfigDict(extra="forbid")`. Field types, units, cardinalities, invariants. |
| E | **Mutation contract** | The mutation primitives §4.8 the MNLM emits, as Pydantic enums or sealed unions. |
| F | **Training signal** | What loss, what data, what cost band, what convergence signal. |
| G | **Boundary channel** | How text I/O is permitted at the boundary and structurally prevented from leaking inside. |
| H | **Empirical falsifier** | One concrete experiment (≤ 1 page) that would falsify your design. Must specify dataset, metric, and decision rule. |
| I | **Risk register** | What blocks integration into Theogony. Where your design breaks with current code in `src/theogony/`. **If you disagree with this brief, name the disagreement here — do not silently route around it.** |
| J | **Three concrete next commits** | One line each. The actual commits you would make on top of `main` if asked. |
| K | **References** | Papers, with year. No vague gestures. Include arXiv IDs where available. |

### Length

≤ 12 pages of dense prose, equivalent to ~6–8k words. No 800-page manifestos. Compression is part of the deliverable.

The output file path and discipline (no branch, no commit) are specified in §8.

---

## 6. Reading order — required before writing

Read these in order. Not all of them, but in this order; stop when you have enough orientation. Skipping the early items is doctrine-violating.

1. [`AGENTS.md`](../../AGENTS.md) — repository discipline, branch hygiene, schema-first, RunReports, commit conventions.
2. [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md) — binding substrate target. **Non-negotiable.**
3. [`docs/CHRONICLE_PRINCIPLES.md`](../CHRONICLE_PRINCIPLES.md) — the twelve non-negotiables. Especially §10 (Vector-Vector-Mesh).
4. [`docs/BUILD_DOCTRINE.md`](../BUILD_DOCTRINE.md) — Function-First doctrine; what "honest failure" means and is **not**.
5. [`docs/IMMUNE_SYSTEM.md`](../IMMUNE_SYSTEM.md) — why pre-gates judging content are forbidden; what cell-class workers do post-hoc.
6. [`docs/etappes/RETIREMENT_NEO4J_MULTIHOP.md`](RETIREMENT_NEO4J_MULTIHOP.md) — the operative note on what was removed and what replaced it.
7. [`docs/etappes/kadmos_v2_brief.md`](kadmos_v2_brief.md) — the translation layer architecture; everything *upstream* of the MNLM. Specifically §3.2 (the reading act) for the model the MNLM will inherit semantically; §4.1 (mesh density); §6 (technical substrate).
8. [`docs/etappes/chronik_mesh_agent_parallel_brief.md`](chronik_mesh_agent_parallel_brief.md) — the prior, narrower brainstorm for *one* mesh agent. The MNLM brief generalises that question. Read it as the seed; do not duplicate it.
9. [`notes/architecture/reading_agent_vision.md`](../../notes/architecture/reading_agent_vision.md) — the user's own articulation of what reading-as-synthesis looks like; the MNLM family is the post-Kadmos extension of that vision into agents that no longer read text.
10. [`notes/architecture/vector_native_spreading_activation.md`](../../notes/architecture/vector_native_spreading_activation.md) — the Spreading-Activation primitive in detail, in German.
11. [`notes/deep_research/run10_brief.md`](../../notes/deep_research/run10_brief.md) and [`notes/deep_research/run11_brief.md`](../../notes/deep_research/run11_brief.md) — prior research questions on cognitively-plausible reading and on the sub-linguistic substrate. The MNLM question is downstream of these.
12. [`notes/deep_research/run11_gemini.md`](../../notes/deep_research/run11_gemini.md) — Gemini Deep Research's response to run 11. Useful prior literature dump on COCONUT, GraphGPT, LatentMAS, Kairos / validation-gated Hebbian, SLM V3.3 / FRQAD, etc. Treat it as **a literature pointer, not an architectural commitment.** That report is uneven; some of its authorities are real, some are likely fabricated. Verify before citing.
13. **If they exist:** `notes/deep_research/run12_gemini.md` and `notes/deep_research/run12_deepseek.md` — external Deep Research responses to the *same* question this brief asks. Treat as **literature floor**, not as a template to imitate. Verify any citation before reusing it. Your artifact must be your own design, not a re-rendering of the external answer.

### Code worth touching before specifying

- [`src/theogony/core/tensor_engine.py`](../../src/theogony/core/tensor_engine.py) — `TensorMeshEngine.spreading_activation`. The MNLM will sit on top of this primitive.
- [`src/theogony/core/knowledge_to_mesh.py`](../../src/theogony/core/knowledge_to_mesh.py) — bridge `KnowledgeNode` / `KnowledgeEdge` → CSR. The MNLM's input format conversation lives here.
- [`src/theogony/stores/lancedb_store.py`](../../src/theogony/stores/lancedb_store.py) — the cold-side substrate. The MNLM will, eventually, write through this.
- [`src/theogony/core/model.py`](../../src/theogony/core/model.py), [`src/theogony/api/dto.py`](../../src/theogony/api/dto.py), [`src/theogony/reporting/models.py`](../../src/theogony/reporting/models.py) — Pydantic shapes. Your `MeshInput` / `MeshOutput` must compose with these, not replace them.

---

## 7. Non-goals — save effort, do not propose these

- A **train-from-scratch foundation model** as the core path. Out of scope. We do not have the budget. The realistic answer is *adaptation of frozen pretrained LLMs*.
- A **return to Neo4j / Cypher** anywhere in the data path. [`RETIREMENT_NEO4J_MULTIHOP.md`](RETIREMENT_NEO4J_MULTIHOP.md). Don't.
- A **synchronous content-judging gate** in front of the MNLM. [`IMMUNE_SYSTEM.md`](../IMMUNE_SYSTEM.md). Don't. Post-hoc Findings are the model.
- A **manifesto, vision document, or strategy paper**. [`AGENTS.md`](../../AGENTS.md) Don'ts §5. The deliverable is engineering-adjacent prose, not philosophy.
- An **800-page literature review.** Run10/Run11 already produced those. Cite, don't replay.
- A **redesign of the substrate** (LanceDB / PyTorch CSR). Decided. If your MNLM design needs a different substrate, file a Phoenix Backlog ticket with the rationale and stop.
- A **rewrite of Kadmos**. Kadmos v2 is in flight. The MNLM consumes Kadmos's output; it does not reach back into the translation layer. The one legitimate effect of this brief on Kadmos is the §4.1 contract: Kadmos's post-embedding output schema is locked to whatever MNLM input schema synthesis settles. That is a parameter change, not a rewrite.
- An **egress / answer-to-humans agent.** Out of scope. If MNLMs work, egress is downstream and tractable; if MNLMs do not work, egress is irrelevant. We are not thinking about egress now. Do not propose architectures whose primary justification is "this also gives us egress for free".

---

## 8. How to run this — operator and agent rules

This brief is consumed by several parallel Cursor agents in one round. The operator launches each agent with a slug; each agent produces one artifact and stops. There is no branch, no PR, no commit. The operator handles git afterwards.

Design diversity is the point. If your design contradicts another agent's, that is signal for the synthesis step, not a problem to flatten.

### File output — the only file you write

Each agent writes exactly one file:

```
docs/research/mnlm/<SLUG>.md
```

`<SLUG>` is a short identifier for your model class, assigned by the operator. The current round's pool: `opus`, `codex`, `gemini`, `sonnet`, `gpt5_mid`. Create the directory if it does not exist.

The header block at the top of that file is mandatory and specified in §5 (row 0).

### Discipline — do this exactly

1. **One file per agent.** No branch. No commit. `git add` is forbidden in this round. Leave the file unstaged. The operator commits.
2. **Do not edit other files.** Not this brief. Not `AGENTS.md`. Not `kadmos_v2_brief.md`. Not other agents' artifacts already present in `docs/research/mnlm/`. If you think this brief is wrong, name the disagreement in §I (Risk register) of *your* artifact — do not silently route around it.
3. **Do not coordinate.** No reading of sibling artifacts in `docs/research/mnlm/` mid-flight. Different inductive biases produce different designs; that is the value, not a defect.
4. **No code shipped into `src/theogony/` from this round.** Research first, plan second, code third. Synthesis in §11 produces the implementation brief; only then does Talos build.

### What happens after the round

A separate Hesiod synthesis agent reads every artifact in `docs/research/mnlm/` plus the external responses in `notes/deep_research/run12_*.md`, and produces `docs/etappes/mnlm_hesiod_brief.md`. That is when architecture decisions actually get made — including the binding `MeshInput` schema (§4.1) and therefore the locked Kadmos↔MNLM contract.

---

## 9. Review criteria — what makes an answer merge-relevant

The human commander (currently Jakob; over time, the operator role) reviews under these criteria:

1. **Mesh-first, not RAG-first.** Is the MNLM truly mesh-native, or is it a text LLM with a graph veneer? Answer must survive the test "if I delete every English string from the runtime, does this still work?".
2. **Schema-discipline.** Are the I/O Pydantic models complete, `extra="forbid"`, and compose-able with the existing model surface?
3. **Falsifiability.** Is there *one* concrete experiment that would kill the proposal? Vague "more research needed" answers fail this criterion.
4. **Doctrine-conformance.** Does the proposal respect [`IMMUNE_SYSTEM.md`](../IMMUNE_SYSTEM.md), [`BUILD_DOCTRINE.md`](../BUILD_DOCTRINE.md), and [`CHRONICLE_PRINCIPLES.md`](../CHRONICLE_PRINCIPLES.md)? Deviations require an explicit Daedalus-routed deviation note.
5. **Implementability.** Is this implementable in 2–4 weeks by a Talos-class agent on top of the current codebase? Or does it require infrastructure that does not exist?
6. **Cost band.** Is the training/serving cost specified, and within an order of magnitude that the project can entertain?
7. **Honest disagreement.** Did the agent push back on the brief where the brief is shaky? Sycophantic conformance fails this criterion as hard as off-spec rebellion does.

---

## 10. The deepest thing the MNLM has to answer for

Underneath all of §4 is one open question that no individual proposal will fully resolve. State your stance on it explicitly, even if you cannot settle it:

> **Can a language model "think" in a medium that is not language — and if so, what does the *systematicity* of that thought look like?**

The Fodor / Pylyshyn critique (Language of Thought, binding problem, "John loves Mary" vs. "Mary loves John") has a real edge here. A vector subgraph can encode "John", "Mary", and "Love" close to each other; whether it can natively *bind* the agent-patient direction without a syntactic scaffold is the unsolved technical-philosophical question.

Three plausible stances, each defensible, each with consequences:

- **Stance A — typed edges suffice.** The directional `LOVES`-edge from John-node to Mary-node binds the relation. Compositionality is recovered from edge typing. No language needed.
- **Stance B — typed edges are insufficient; latent CoT inside the MNLM is the language.** The MNLM still uses a serial reasoning trajectory in continuous space (Coconut-style), and *that* is the systematic substrate, not the mesh.
- **Stance C — neither works alone; the MNLM is intrinsically dual.** Mesh for associative retrieval, latent CoT for compositional binding, with a controlled exchange between them.

Pick one. Defend it. Name the experiment that would settle it.

---

## 11. Output, then stop

When the file at `docs/research/mnlm/<SLUG>.md` is written, report the path and stop. Do not commit. Do not re-engage. The operator handles git; a separate Hesiod synthesis run handles cross-artifact consolidation; Talos handles whatever implementation the synthesis demands. Each role withdraws when its artifact is delivered.

The first MNLM the project actually builds will almost certainly be Nous (the synthesis role on the Chronik). The Hesiod brief makes that explicit and locks the contract in §4.1 between Kadmos's embedding-pass output and the MNLM's `MeshInput` schema. None of that is your concern as a Round-1 agent.

---

*Chaos withdraws. The architecture belongs to the field of agents who answer next.*
