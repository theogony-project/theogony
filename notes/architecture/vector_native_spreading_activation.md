# Concept: Vector-Native Spreading Activation in the Theogony Mesh

> **Status: historical context (superseded).** This early MVP draft correctly captured the spirit of the substrate architecture (LanceDB + PyTorch CSR, spreading activation as SpMV, latent space injection instead of text-RAG), but has been replaced in every respect by the MESH triplet — [`docs/MESH_SUBSTRATE.md`](../../docs/MESH_SUBSTRATE.md), [`docs/MESH_IMPLEMENTATION.md`](../../docs/MESH_IMPLEMENTATION.md), [`docs/MESH_RETRIEVAL.md`](../../docs/MESH_RETRIEVAL.md). The triplet specifies node anatomy (two tiers, multiple vectors per node, eager identity), edge anatomy (a quantitative core plus optional semantic descriptors), the full dynamics (super-linear decay, saturation, atrophy, renormalisation, splits), pathology and therapy, and the retrieval discipline (diversified injection, frame routing, three-factor RL) — everything this note only sketches. Where this document and the MESH triplet differ, the MESH triplet is authoritative. This note is kept as historical evidence of the early design, not as an implementation template.

**Document status:** MVP draft (Function-First phase) — superseded by the MESH triplet
**Context:** Implementation of a pure vector language and cognitive "spreading activation" for the Theogony knowledge substrate. Per `BUILD_DOCTRINE.md`, the focus is on speed, feasibility, and autonomous growth without human pre-validation.

The Theogony mesh does away with text as the primary communication medium between AI agents. Instead, the substrate operates as a **tensor manifold**, in which both nodes and edges (synapses) exist as high-dimensional vectors. Information retrieval does not proceed through structured query languages (such as Cypher or SQL), but through cognitive activation spreading (spreading activation).

---

## 1. Vector Injection: The Communication Entry Point

How does an LLM "inject" a thought into the mesh without taking the detour through natural language?

*   **The Stimulus (Injection Vector):** Instead of sending a text prompt (`"Wer war Einstein?"`) to a retrieval pipeline, the agent process transmits its internal state directly. Ideally, this is the **temporally aligned sequence of the hidden states of the last layers (Last-Layer Hidden States)** of the transformer architecture.
*   **Fallback for the MVP:** Since commercial APIs (such as OpenAI) often block direct access to hidden states, the MVP uses a dedicated, locally running embedding proxy (e.g. a fast `all-MiniLM-L6-v2` or Nomic-Embed-Text model). The agent sends its raw "thought context", which is immediately converted into a dense vector (the stimulus vector $S_0$) and injected into the mesh. In the long term (with open models such as Llama 3), the token step is skipped entirely ("latent-space communication").
*   **Format:** A high-dimensional Float32 or Bfloat16 tensor that represents the agent's current intentional orientation.

---

## 2. The Spreading Activation Algorithm

As soon as the stimulus vector $S_0$ arrives in the system, the energy spread (spreading activation) through the vector mesh begins, inspired by the ACT-R cognitive architecture.

### The Process (Step by Step):
1.  **Initial Firing:** The stimulus vector $S_0$ is given initial energy $E_{start}$ (e.g. $E=1.0$). The system performs a fast Approximate Nearest Neighbor (ANN) search in vector space to find the $k$ semantically most similar entry nodes. These nodes receive the starting energy.
2.  **Edge Evaluation (Tensor Matrix Multiplication):** From the activated nodes, the energy spreads across the edges (which are themselves vectors!). The system computes the edge weight dynamically. The weight $W$ of an edge to a neighbouring node is determined by:
    *   **Semantic Relevance:** Cosine similarity between the stimulus $S_0$ and the edge vector as well as the target-node vector.
    *   **Hebbian Learning (Reactivation Frequency):** Frequently used edges have a "strengthened" multiplier.
3.  **Energy Propagation:** The energy of the target node $E_{target}$ is calculated as:
    $E_{target} = (E_{source} \times W) - D$
    (Where $D$ is a constant damping factor (decay) per hop).
4.  **Stop Condition:** The spread on a path stops when the energy $E$ of a node falls below a system-wide threshold ($T_{min}$) or a maximum hop distance (e.g. 3 hops) is reached, in order to prevent infinite loops (context exhaustion).

Through lateral inhibition, highly relevant paths are strengthened, while irrelevant, noisy paths die off quickly through the decay $D$.

---

## 3. The "Constellation" (The Result for the LLM)

Instead of returning a flat list of text chunks to the LLM, the mesh delivers a **"Constellation"**.

*   **The Format:** A Constellation is a strongly connected, localised subgraph of vectors (nodes and edges) whose activation energy has exceeded the threshold. In purely technical terms, this is an aggregated tensor matrix.
*   **Processing by the LLM:** The Constellation is "injected" directly into the receiving LLM's latent space (Latent Space Injection). For open-source models, this vector matrix is loaded as **Soft Prompts** or directly into the KV cache (Key-Value Cache). The LLM thereby suddenly "knows" the context without having to read it as text.
*   **Advantage:** The problem of "Context Isolation" in conventional RAG systems is solved. The LLM does not just receive isolated facts, but has the exact mathematical relationship vectors (causality, contradictions) fed directly into its neural network.

---

## 4. Storage Technology for the MVP

Conventional graph databases (GDBs) with pointer-chasing collapse under the load of millions of vector edges. The mesh needs a technology that treats graphs as **continuous tensor arrays**.

**The MVP Tech Stack:**
1.  **LanceDB (Columnar Vector Store):** Serves as the persistent, append-only storage layer. It stores nodes and edges (synapses) as first-class citizens in vector space. It supports versioning (time travel) out of the box, which corresponds to the Theogony principle of immutable provenance.
2.  **PyTorch Tensor Computation Runtime (TCR):** For the actual spreading activation at runtime, the graph is loaded into GPU memory (VRAM) as a **Compressed Unique Source (CUS)** or **Compressed Sparse Row (CSR)** tensor.
3.  **Process:** The propagation of energy is not an iterative "for loop" over nodes, but a massively parallelised matrix multiplication in PyTorch. An energy spread across 100,000 edges thus happens through a single GPU instruction in milliseconds.
4.  **No ACID Transactions:** To maximise ingest speed for agents, there are no classical updates or locks. If a fact is corrected, the system writes a new vector and a "Supersedes" edge (append-only ledger).

---

## Conclusion for the Implementation

This design definitively separates text from machine communication. Text exists only at the periphery (during the initial ingest of Wikipedia, or in the output for a human operator). At the centre, agents communicate through vector matrices and spreading activation via LanceDB/PyTorch — a design that natively unites extreme density (1000x edges vs. nodes) and millisecond retrieval.
