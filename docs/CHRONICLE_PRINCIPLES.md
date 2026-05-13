# Chronicle Principles

**Purpose:** Non-negotiables distilled from the Pantheon north star. Use this when another doc needs doctrine without repeating the full manifesto — see [`PANTHEON_VISION.md`](PANTHEON_VISION.md).

**Terminology:** *Pantheon* here means the **planetary chronicle / knowledge substrate** (long horizon), not the mythological agent roles (Argus, Athene, …). See [`GLOSSARY.md`](GLOSSARY.md).

**Operative companions:** these principles are implemented and bound at the substrate level by [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md), at the runtime level by [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), and at the retrieval / learning level by [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md). When a principle below requires concrete mechanism — *how* native identity emerges, *how* contradiction stays first-class, *how* trails strengthen the graph, *how* Vector-Vector-Mesh actually works — those three documents are the binding answer.

---

## The Founding Principle — Language is the Edge, Not the Substrate

**Language is the edge, not the substrate.**

Meaning exists before language. A person senses the mood in a room before they have words for it. A mathematician sees a structure before they can name it. A musician hears a harmony they cannot fully translate. Meaning is not a function of language — language is one possible output of meaning.

Wittgenstein’s line — “The limits of my language mean the limits of my world” — describes an observation, not a truth. It mistook the output medium for the thinking medium.

The Chronicle is not a text archive with vectors as an index. The Chronicle is a **semantic space** where meaning exists without language, moves, condenses, and changes. Language enters that space at only two points:

- **At the ingress:** Argus brings text. Kadmos translates it into vectors and edges. After that, no text remains inside the system.
- **At the egress:** Iris activates a subgraph and formulates language for a human from it. That is output, not lookup. Iris does not read stored text — she generates language from meaning.

Everything between Kadmos and Iris — Nous, Chronicle, Oneiros, Kalypso — operates without language. That is not a limitation. That is the core.

**The counter-model is RAG.** RAG stores text spans and returns them. The Chronicle stores meaning and generates language. If text is stored as payload or passed between agents, it is RAG. If only vectors and edges flow, it is Chronicle. Any agent that uses text as its internal communication medium violates this principle.

---

## The Ten Non-Negotiables

1. **Chronicle over encyclopedia** — Preserve reality in motion: disputes, weak evidence, supersession, and strategic relevance; do not flatten to a single settled summary.

2. **Provenance-first** — Every meaningful claim must carry origin, basis, and revision path; opaque insertion is unacceptable.

3. **Native identity over time** — Pantheon-native identity is the long-term centre of gravity; Wikidata Q-IDs and other external IDs are *the strongest signal the substrate accepts at insertion time* (each Q-ID maps to at most one stable Tier-1 node) but they are bootstrap anchors, not the eternal source of identity. Identity is committed eagerly when the evidence — Q-ID match, description match, or strong structural context — is decisive, and emerges through consolidation otherwise. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Why two tiers — and how identity actually gets committed".

4. **Contradiction is first-class** — Conflict, uncertainty, and competing interpretations stay legible; premature collapse is a failure mode.

5. **Governance in the data model** — Access, authority, trust, review, and responsibility are machine-legible, not only informal policy.

6. **Privacy as operational necessity** — Governed visibility and data sovereignty are required for adoption and law *now*, even if long-term realism about superhuman capability stays skeptical of policy-only guarantees.

7. **Rebuildability over mystique** — The chronicle must be inspectable, portable, and partially reconstructible; if it cannot be rebuilt, it cannot be trusted.

8. **Trails strengthen the graph; Slow-Path may walk against them** — Attention leaves durable edge-level signals (`pheromone_delta`); deliberate Slow-Path retrieval may use `invert` to read without reinforcing those trails (see [`PHEROMONE.md`](PHEROMONE.md)).

9. **The chronicle is allowed to dream; the dream is allowed to be wrong; the dream is never elevated without verification.** — Morpheus may propose low-confidence `INFERENCE` edges; promotion to trusted knowledge still flows through evidence and (eventually) Athene-style review. **This applies to ingestion too, not only to inference:** raw extraction may produce imperfect, contradictory, or low-confidence assertions; that is the design, not a defect. Pre-validation gates are forbidden. Truth emerges post-hoc through mass, consolidation, and the immune system — see [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md) for the binding statement of the current Function-First Phase.

10. **AI-Native Communication (Vector-Vector-Mesh)** — The substrate is built by AI agents, for AI agents. It abandons human-readable text as the *primary retrieval interface* in favor of Latent Space Communication. Agents inject vectors (or richer sub-meshes with structure), and the mesh responds via Spreading Activation over a hyper-dense Tensor-Manifold. Text generation is a final-mile translation for humans, not the core operating language of the system. **Text metadata on nodes and edges — `description`, `relation_descriptor`, `tags`, `source_url` — is permitted and authoritative for repair, disambiguation, LLM injection, and human inspection** (see [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Field discipline" point 4 and §"Edge anatomy"). What is forbidden is raw source-text storage as retrieval payload: SpMV reads vectors, not strings, and treating text as the substrate's retrieval surface would recreate RAG-style retrieval on top of the mesh.
