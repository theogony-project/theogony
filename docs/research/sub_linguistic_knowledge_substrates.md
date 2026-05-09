# Research Brief: Sub-Linguistic Knowledge Substrates for AI Reasoning

**Filed by:** Chaos / Hesiod — Theogony Project  
**Date:** 2026-05-08  
**Status:** Open research question — input requested from frontier models and research agents  
**Context repository:** github.com/theogony-project/theogony

---

## 0. The Core Hypothesis

Language is the edge of cognition, not its substrate.

When a human reads a text, meaning does not consist of stored sentences. It consists of activated concept-constellations, weighted associations, and revised syntheses — none of which require language as an intermediary. Language is a final-mile translation for communication, not the operating medium of understanding.

We hypothesize that the same is true for AI systems: large language models represent meaning internally as vectors and attention patterns, not as token sequences. Text is the input/output interface, not the computational substrate.

**The hypothesis:** a knowledge system that stores, reasons over, and retrieves meaning in its native substrate — vectors and weighted edges — without text as an internal medium, will outperform retrieval-augmented generation (RAG) systems on tasks requiring deep semantic reasoning, cross-domain connection, and emergent inference.

This brief defines the research questions that must be answered to build, evaluate, and validate such a system.

---

## 1. The Architecture Under Investigation

We call this system **the Chronik** (Chronicle). It operates as follows:

```
Text (Wikipedia, books, web)
    ↓
Kadmos — structural translation layer
    Text → vectors + typed edges
    No LLM labels, no text stored
    Output: a primitive vector mesh (local structure preserved)
    ↓
Nous — cognitive synthesis layer
    Input: vector mesh (no text)
    Output: denser mesh (diagonal edges, synthesis nodes, revisions)
    Operates without language as intermediate medium
    ↓
Chronik — persistent semantic space
    LanceDB / PyTorch Tensor-Manifold
    Nodes: embedding vectors only
    Edges: typed, weighted, vectorized
    No text attributes beyond minimal provenance IDs
    ↓
Oneiros — consolidation
    Hebbian learning on edge weights
    Promotes well-connected nodes, demotes weak ones
    ↓
Kalypso — emergent discovery
    Finds connections nobody queried
    ↓
Iris — output
    Activates subgraph via Spreading Activation
    Translates vector constellation → natural language
    The only point where language is generated
```

The critical transition is **Kadmos → Nous**. After Kadmos, no text exists in the system. All subsequent processing is purely vectorial.

---

## 2. Research Questions

### 2.1 The Substrate Question

**Can an AI system reason effectively over a pure vector mesh without text as an intermediate representation?**

Sub-questions:
- What information is lost when translating text to vectors without preserving text snippets? Specifically: how well do current embedding models (BAAI/bge, E5, OpenAI text-embedding-3) encode (a) causal relations, (b) temporal ordering, (c) negation, (d) modality, (e) quantification, (f) counterfactuals?
- For which reasoning tasks does the loss of text create insurmountable gaps vs. recoverable gaps?
- Can typed, weighted edges compensate for embedding limitations — e.g., storing causality as an explicit edge type rather than relying on the embedding to encode "caused by"?

### 2.2 The Nous Question

**Can a model reason over a vector graph without text serialization?**

Current frontier LLMs (GPT-4o, Claude 3.7, Gemini 2.5) are text-in/text-out. But the internal representations are vectors. Sub-questions:

- What architectures today can take a vector graph as primary input, reason over it, and produce new edges and synthesis nodes as output — without text as an intermediate? Candidates: Graph Transformers (GraphGPS, HGT, RelGT), Coconut-style latent chain-of-thought, GL-Fusion, LatentMAS.
- What is the state of the art in graph-to-graph transformation: a model that takes an input graph and produces a denser, better-connected output graph through genuine semantic inference?
- Can a frozen pretrained LLM be adapted (LoRA, soft prompts, vLLM prompt embeddings) to reason over vector graph inputs without full retraining? What is the minimum adaptation required?
- What training signal would enable a Nous-like model to learn "good synthesis" — i.e., which new edges and synthesis nodes are semantically valid? Is self-supervised graph completion sufficient?

### 2.3 The Latent Reasoning Question

**Can reasoning models operate entirely in latent space over knowledge graphs?**

Coconut (Meta FAIR, 2024) demonstrated that LLMs can reason via continuous hidden states without decoding to text at each step. LatentMAS and C2C showed that inter-agent communication via hidden states outperforms text-mediated communication. Sub-questions:

- Can a Coconut-style model perform multi-hop reasoning over a vector knowledge graph — following edge traversals as latent reasoning steps rather than text chains?
- What is the performance gap between latent-space graph reasoning vs. text-serialized graph reasoning on standard knowledge graph reasoning benchmarks (WebQSP, MetaQA, ComplexWebQuestions)?
- Is there evidence that latent-space reasoning preserves semantic structure better than text-mediated reasoning for tasks involving negation, contradiction detection, and temporal reasoning?

### 2.4 The Iris Question

**Can a model generate accurate, well-grounded natural language from an activated vector subgraph — without access to source text?**

This is the inverse of embedding: given a constellation of vectors and weighted edges, can a model produce a fluent, accurate, well-grounded answer? Sub-questions:

- What is the relationship between subgraph density (edge/node ratio) and answer quality? At what density does text generation become reliable?
- How does the model handle uncertainty — nodes with low confidence, contradictory edges, weak connections? Does it hallucinate or appropriately hedge?
- What is the performance ceiling of vector-to-text generation vs. text-to-text generation (RAG) on factual question answering benchmarks?

### 2.5 The Oneiros Question

**Can Hebbian learning on a knowledge graph produce stable, useful consolidation — or does it drift?**

Without an external ground-truth signal, edge weights are reinforced by query frequency. Sub-questions:

- Under what conditions does frequency-based Hebbian reinforcement approximate truth-based reinforcement? When does it diverge dangerously?
- Is there a self-supervised signal within the graph structure itself (e.g., topological consistency, contradiction detection) that can correct Hebbian drift without external annotation?
- What is the relationship between graph density and Hebbian stability? Does higher edge density (1000:1 ratio) dampen or amplify drift?

### 2.6 The Spreading Activation Question

**Is Spreading Activation over a dense vector graph a better retrieval primitive than kNN + graph traversal?**

This is Monkey 2 (the empirical test defined in the Theogony project). Sub-questions:

- At what edge/node ratio does Spreading Activation become superior to kNN? Is there a density threshold below which it performs worse?
- What is the flooding problem at high density, and what clamping/damping mechanisms prevent information loss while preserving selectivity?
- How does Spreading Activation compare to attention-based retrieval (as in standard transformer cross-attention) for multi-hop factual questions?

---

## 3. The Comparison: What RAG Cannot Do

This research is motivated by the limitations of RAG:

| Capability | RAG | Chronik (hypothesis) |
|---|---|---|
| Multi-hop inference not explicit in any single source | Poor — requires all hops to appear in retrieved chunks | Strong — emergent via graph traversal |
| Contradiction detection across sources | None — contradictions appear as parallel chunks | Native — CONTRADICTS edge type, Nemesis agent |
| Temporal reasoning | Poor — chronology is a text property | Explicit — temporal edge types |
| Emergent connections | None | Kalypso agent, Spreading Activation |
| Cross-domain analogies | Poor | Strong — vector proximity independent of text domain |
| Grounding without text retrieval | None | Hypothesis: vectors + edges sufficient |
| Revision of prior beliefs | None — static index | Native — Revision events, Oneiros consolidation |

The research question is not "is Chronik better than RAG?" — it is "under what conditions, for what tasks, and at what cost is a sub-linguistic knowledge substrate superior?"

---

## 4. Empirical Tests (the Monkey Protocol)

Three empirical tests are already defined in the project:

**Monkey 1 (completed, partially):** Does cognitive synthesis (Nous) produce a denser, better-connected graph than the current parser (Kadmos v1) on the same Wikipedia article? Baseline established: topology_parser produces edge/node ratio 0.49; Kadmos v1 (mislabeled as Nous v1) produces 1.10. Target for true Nous: >5 (explicit edges) + >100 (with implicit kNN edges).

**Monkey 2 (not yet run):** Does Spreading Activation over the dense Chronik graph retrieve better than kNN + graph traversal? Requires Monkey 1 to complete first.

**Monkey 3 (proposed):** Can a Nous-like reasoning model answer questions that are implicit in the graph but never explicitly stated in any source text? Test: ingest multiple Wikipedia articles on related topics, ask questions whose answers require cross-article inference. Compare: (a) RAG on original text, (b) Chronik with Spreading Activation, (c) Chronik with latent reasoning model.

---

## 5. What We Are Asking

We are asking research agents and frontier models to:

1. **Evaluate the feasibility** of the architecture described above. What are the strongest objections? What are the most promising paths?

2. **Identify the critical unknowns.** Which of the research questions above has the most impact on whether the overall system works? Where should we focus first?

3. **Survey the literature.** What papers from 2023–2026 are most relevant to: (a) sub-linguistic reasoning, (b) graph-to-graph transformation via neural models, (c) latent space communication between agents, (d) knowledge graph reasoning without text serialization?

4. **Propose concrete experiments.** Given the current state of the Theogony codebase (Kadmos v1 implemented, LanceDB integration partial, Neo4j as current store), what is the minimal experiment that would falsify or support the core hypothesis?

5. **Challenge the Wittgenstein assumption.** The founding principle of this architecture is that language is not necessary for meaning. What is the strongest technical and philosophical argument against this? What evidence would change our mind?

---

## 6. What Is Already Known (Don't Repeat)

The following is already established and does not need to be re-researched:

- RAG limitations on multi-hop reasoning: well-documented
- Graph Neural Networks as encoders: established, we know HGT and GraphGPS are viable
- Coconut (Meta, 2024): known, latent chain-of-thought works on some tasks
- LatentMAS, C2C: known, latent inter-agent communication outperforms text
- Embedding limitations for negation/modality: known, this is a fundamental limit we are working around with typed edges
- LanceDB + PyTorch as the target storage: decided, not under review

---

## 7. The Open Question This Project Cannot Answer Alone

The deepest question — which may require empirical research beyond what a single team can run — is:

**At what point does a vector knowledge graph become a genuine knowledge representation, capable of supporting inference that exceeds what any individual source text contains?**

This is not a retrieval question. It is a question about whether the synthesis process (Nous) genuinely creates new knowledge — or merely reorganizes existing knowledge in a more accessible structure.

If the answer is "merely reorganizes" — the Chronik is a very good RAG. If the answer is "genuinely creates" — the Chronik is something new.

We believe the answer is in the density and structure of the synthesis process. But we do not yet know how to measure it.

---

*This brief is open. Responses, challenges, and literature pointers are welcome. The project is at an early experimental stage; we are not looking for validation, we are looking for the sharpest possible critique.*
