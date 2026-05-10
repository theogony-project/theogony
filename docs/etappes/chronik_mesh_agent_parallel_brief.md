# Parallel brief: Chronicle mesh agent (creative design track)

**Status:** Work order for several external builder agents (Cursor, Codex, …) — **not** a substitute for [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md) or Daedalus planning documents.  
**Language:** English (repository standard); code comments stay English.  
**Goal:** Independent designs for a **first real Chronicle agent** whose **primary I/O is not free prose** but **structures of the semantic mesh** (LanceDB or comparable / new internal representation). Short term, **dual mode** (text + mesh) is allowed as long as the mesh path is **first-class**, not merely “embeddings around a chat”.

---

## 1. Binding guardrails (do not reinvent these)

The following are **already decided** — your proposals must respect them or mark an **explicit** deviation with rationale (for human Daedalus review):

1. **Substrate language:** The Chronicle operates on **vectors + weighted, typed edges**; classic “text RAG as core” is **not** the target (see TARGET_ARCHITECTURE).
2. **Retrieval primitive:** **Spreading activation** over tensor / CSR-like structures is the **intended** query mechanism — **no** multi-hop Cypher / pointer-chasing path as the production default.
3. **Persistence direction:** **LanceDB** (or a explicitly named successor in the same spirit: append-only, vector-close) is the obvious candidate for cold storage; Neo4j is **not** a target substrate for the core mesh.
4. **Schema discipline:** Public DTOs = **Pydantic v2**, `extra="forbid"`. No ad-hoc dicts for agentic I/O.
5. **Honest failure:** Every non-trivial pipeline writes **RunReports** with structured `verdict` — no silent exceptions outward.
6. **AGENTS.md / CONTRIBUTING.md:** Branch hygiene, tests, no secrets in the repo.

What is **deliberately open** (you may be creative here):

- Exact **serialization** of a “mesh slice” (Arrow? ULID-scoped Lance fragment? custom frozen DTO?).
- How an agent **writes** (append-only deltas vs transactional patches; idempotency keys).
- How **potential / activation** is measured and written back (energy vector? scalar fields on edges? Hebbian update rules).
- Whether and how a **minimal text channel** (only for Iris / human, or for seed stimuli) coexists.

---

## 2. Problem statement in one sentence

> Define a **Chronicle agent** that **primarily** communicates with **mesh structures** (node/edge tensors, constellation-like slices, activation profiles) and can **read + write** the Chronicle — optionally with a controlled text side channel, but **without** the agent being “just a chatbot with tool calls”.

---

## 3. Your deliverables (per agent / per branch)

Each agent produces **one** coherent artifact (not seven half-finished ones):

| # | Artifact | Minimum content |
|---|----------|-----------------|
| A | **Agent interface** | What **inputs** / **outputs** (Pydantic models)? What **operations** on the mesh? |
| B | **Read path** | How does a stimulus (vector or referenced mesh slice) become a **constellation** / activation map? Which steps, which data source? |
| C | **Write path** | Which **mutations** are allowed? How do you limit drift, duplicates, contradiction (no pre-gates — prefer post-hoc reports)? |
| D | **Activation / potential** | Concrete rules or algorithms for how “potential” surfaces and how **Hebbian** / relevance updates might apply. |
| E | **Minimal prototype** (optional) | Small Python module or notebook sketch showing the I/O models (does **not** have to merge into the main repo). |
| F | **Risks & open questions** | What blocks integration into Theogony? Where does your design break with current code? |

---

## 4. Explicit creative freedoms

- You may propose **new** intermediate data structures (“mesh handle”, “session subgraph”, “activation packet”) as long as you spec them **precisely**.
- You may deliver **two** competing designs (A/B) if you name the trade-offs clearly.
- You may propose **which** parts of today’s `QueryPipeline` scaffolding should **go** and what is minimally necessary instead — but label it a **proposal**, not merge-ready architecture.

---

## 5. Non-goals (save effort)

- No full **train-from-scratch** LLM as the core solution for this agent.
- No **Neo4j/Cypher** as a new standard.
- No **500-page** vision — short, precise, implementation-adjacent.
- No **pre-content gates** before insertion (see IMMUNE_SYSTEM / BUILD_DOCTRINE).

---

## 6. Repo context (starting points)

- [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md) — pipeline picture, “no text in substrate”, spreading activation.
- [`src/theogony/core/tensor_engine.py`](../../src/theogony/core/tensor_engine.py) — `TensorMeshEngine.spreading_activation`.
- [`src/theogony/core/knowledge_to_mesh.py`](../../src/theogony/core/knowledge_to_mesh.py) — bridge KnowledgeNode/Edge → CSR.
- [`src/theogony/stores/lancedb_store.py`](../../src/theogony/stores/lancedb_store.py) — LanceDB + `load_into_tensor_engine` (current: partial MVP).
- [`src/theogony/core/store.py`](../../src/theogony/core/store.py) — `KnowledgeStore` protocol (being cleaned / replaced — check **current** state on your branch).
- [`ROADMAP.md`](../../ROADMAP.md) — term **Nous** (“potential actual”).

---

## 7. Submission format

- **One** Markdown file or **one** PDF per agent, **≤ 12 pages** equivalent.
- Top: **3-sentence summary** + **list of touched repo paths** (reference only, no mandatory merge).
- Bottom: **next 3 concrete commits** (one line each) that *you* would make.

---

## 8. Review criteria (for the human commander)

- Is mesh I/O **first-class** or only an attachment?
- Are mutations **auditable** and reportable?
- Is the proposal **implementable in ~2–4 weeks** by a Talos-like agent, or only metaphor?
- Does anything contradict **TARGET_ARCH** — and if so, is the rationale **worth** a Daedalus decision?

---

*End of parallel brief.*
