# Chronik Scale Analysis

**Status:** Living document. Update when hardware prices, corpus estimates, or infrastructure assumptions change materially.  
**Companion:** [`PANTHEON_VISION.md`](PANTHEON_VISION.md) §"The Scale of the Chronik" — the stable principles. This document holds the numbers. For the substrate's behavioural and runtime spec — the actual storage layout that determines these numbers — see [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) and [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), which are operative.  
**Last updated:** 2026-05-13

---

## Why this document exists separately

Concrete storage estimates, cost figures, and infrastructure tier descriptions age faster than architectural principles. This document holds the perishable specifics so that `PANTHEON_VISION.md` can remain stable while this document is revised as the project grows and hardware economics change.

---

## The consolidation ratio

When Kadmos reads a Wikipedia article, it extracts Tier-0 Observation Chunks and reference edges to Tier-1+ entity / concept / source-anchor nodes. For entities the linker can confidently resolve (Q-ID match, description match, or strong structural context per [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Why two tiers — and how identity actually gets committed"), the chunk's reference edges attach directly to existing Tier-1 nodes — no duplicate is created. For entities the linker cannot confidently resolve, an entity-candidate node is created, and Oneiros consolidates accumulated candidates into stable Tier-1 nodes over later ticks. Concept nodes (without Q-ID) form emergently from co-resonating chunks.

The **consolidation ratio** — what fraction of raw Kadmos-emitted Tier-1 candidates collapses into existing nodes — has been estimated at **~60–80%** based on embedding-cluster analysis of medium-sized corpora.

This ratio is the key variable in all scale estimates below. If it is lower in practice (e.g. 40%), node counts are higher; if higher (e.g. 90%), they are lower. The MNLM PoC pass (§13 of `mesh_native_lm_brief.md`) will produce the first empirical data point.

---

## Scale tiers

### Tier 0 — PoC and Gen 1 development

| Metric | Value |
|---|---|
| Source corpus | 200–10,000 Wikipedia articles |
| Concept nodes (consolidated) | ~15,000 – 1,000,000 |
| Edges (with kNN wiring) | ~150,000 – 100,000,000 |
| Storage | ~50 MB – 5 GB |
| Runtime memory (CSR tensor) | < 4 GB RAM |
| Infrastructure | MacBook Pro M4 Pro, LanceDB local, PyTorch MPS |
| Cost | Hardware already owned |

### Tier 1 — English Wikipedia

| Metric | Raw Kadmos output | After consolidation (~70%) |
|---|---|---|
| Tier-0 observation chunks | ~500 million | unchanged (chunks are not deduplicated; consolidation operates on Tier-1+ candidates) |
| Tier-1+ consolidated nodes (entities + concepts + source-anchors) | ~150–200 million candidates | **~50–100 million stable** |
| Explicit reference edges (Kadmos chunk → Tier-1 node) | ~1.5 billion | ~1.5 billion |
| Hebbian + kNN similarity edges (50–100× over Tier-1 nodes) | — | ~10–15 billion |
| Node storage (multiple vectors per Tier-1 node: 1024-d semantic + 64-d frame + 128-d structural where populated + 1024-d description where populated, plus metadata) | — | **~300–500 GB** |
| Edge storage — quantitative CSR (source, target, weight FP16, decay_tier, frame_consistency) | — | ~50–80 GB |
| Edge storage — Lance metadata table (descriptors on ~10–30% of edges) | — | ~30–60 GB |
| Audit ledger + historical Lance versions | — | ~100–500 GB cumulative |
| **Total consolidated storage** | — | **~5–8 TB** |

Infrastructure at this tier: single high-memory server (512 GB RAM for CSR runtime tensor, NVMe SSD for LanceDB vector store). LanceDB or Milvus. No distributed system required.

Estimated operating cost (2026 hardware/cloud prices): **~500–2,000 EUR/month** on dedicated hardware; **~2,000–6,000 EUR/month** on cloud instances.

### Tier 2 — All Wikipedia language editions

330+ languages, ~60 million articles total. After consolidation, cross-lingual redundancy dominates: most concepts in other languages already exist as nodes from the English edition. Additional sources add cross-lingual edges, not new nodes.

| Metric | Estimate |
|---|---|
| Concept nodes (consolidated) | **~200–400 million** |
| Edges with moderate kNN (50×) | ~10–20 billion |
| Total storage | **~15–50 TB** |
| Infrastructure | Single large server or 2–3 node cluster |
| Estimated cost | ~2,000–8,000 EUR/month |

### Tier 3 — Full public knowledge corpus

Wikipedia (all languages) + scientific literature (Semantic Scholar, arXiv, PubMed, ~200M papers) + open books (Project Gutenberg, Internet Archive, ~5M volumes) + curated web content.

Scientific literature introduces specialist concepts absent from Wikipedia but describes many overlapping concepts at greater depth. Books add cultural, narrative, and historical structure. Web content adds recency and domain diversity.

| Metric | Estimate |
|---|---|
| Concept nodes (consolidated) | **~1–5 billion** |
| Edges at 100× density | ~100–500 billion |
| Total storage | **~50–500 TB** |
| Infrastructure | Distributed vector store (Milvus), distributed sparse adjacency (GraphBLAS-based), hierarchical Spreading Activation |
| Estimated cost | ~50,000–200,000 EUR/month at cloud rates; ~10–50M EUR for owned infrastructure |

This is the threshold at which a serious organisation — not an individual or small team — is required to operate the substrate continuously.

### Tier 4 — Federated scale

Global public layer (Tier 3) plus thousands of institutional sub-meshes plus potentially billions of personal sub-meshes.

The key scaling insight at this tier: **the global layer does not grow proportionally with sub-mesh count**. Personal and institutional sub-meshes add edges to existing bridge nodes in the global layer; they do not add new global nodes. The marginal cost per additional sub-mesh is bounded by that sub-mesh's own private edge volume, which is operated by its owner — not by the global infrastructure.

| Component | Who operates it | Marginal cost |
|---|---|---|
| Global public layer | Central operator | Fixed (Tier 3 cost) |
| Institutional sub-mesh | Institution | ~10–500 EUR/month per institution depending on size |
| Personal sub-mesh | Individual or delegated provider | ~1–10 EUR/month per person |

The global operator's infrastructure cost is decoupled from the number of sub-meshes. Federation distributes both sovereignty and cost.

---

## The biological reference point

The human central nervous system has ~86 billion neurons and ~100 trillion synapses. Cortical neurons average ~7,000 connections each.

At full edge density (1,000:1 edges/nodes target from `TARGET_ARCHITECTURE.md`), the Chronik at Tier 3 scale (5 billion nodes) would have ~5 trillion edges — roughly 1.75 PB of edge data. That is approaching the synaptic count of a human brain.

The Chronik does not need to reach neuron-scale node count to approach synaptic-scale connectivity. Consolidation keeps the node count far below what raw text volume implies — the estimated 1–5 billion consolidated nodes for all public human knowledge is 1–6% of the human neuron count, but with 1,000× edge density would reach ~50% of the human synaptic count. The intelligence lives in the edges.

---

## Infrastructure evolution path

| Tier | Vector store (nodes) | Edge runtime | Edge metadata | SA implementation |
|---|---|---|---|---|
| 0–1 | LanceDB (local/cloud) | PyTorch sparse CSR in RAM (or MPS / consumer GPU) | Lance table | Single-node batched SpMV |
| 2 | LanceDB | PyTorch sparse CSR on A100 / H100 (FP16 weights) | Lance table | Single-node batched SpMM (many concurrent activations) |
| 3 | LanceDB distributed (or Milvus where Lance does not scale) | Sharded sparse CSR per topic cluster; GraphBLAS / DistDGL for cross-shard ops | Lance distributed | Hierarchical SA (coarse routing across shards + fine within shard) |
| 4 | Per-sub-mesh stores plus a global public layer | Distributed sparse CSR with permission masks | Distributed | SA with per-tier permission masks (per [`PANTHEON_VISION.md`](PANTHEON_VISION.md) §"The Federated Substrate") |

The transition from Tier 1 to Tier 2 is a configuration change (larger server, possibly GPU). The transition from Tier 2 to Tier 3 is an infrastructure change (distributed systems). The transition from Tier 3 to Tier 4 is an architectural change (federation protocol, permission masks, sub-mesh ownership model).

Each transition is designed as an addition to the existing substrate, not a rewrite. The LanceDB columnar node format, PyTorch sparse CSR edge tensor, COO delta buffer, and SpMV / SpMM SA primitive are forward-compatible with distributed Lance, GraphBLAS, and per-tier permission masks at higher tiers. The substrate doctrine ([`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md)) is the same at every tier; only the deployment topology changes.

---

## Periodic maintenance operations

The substrate's own dynamics ([`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"The dynamics" and §"Consolidation, splits, and tier promotion") provide bounded growth without external scheduling. Three background operations are nonetheless worth naming here as scale-shapers:

**Oneiros tick (all tiers).** The substrate's single-writer process — runs every few minutes at Tier 0, every 15–30 minutes at Tier 1 dev, hourly at Tier 1 production, every few hours at Tier 2+. Each tick drains the Hebbian delta buffer, applies **super-linear decay** (tier-modulated, `k = 2` for Tier 0, gentler for higher tiers) so unused edges shrink faster than used ones, applies **global homeostatic renormalisation** to keep total-edge-weight / node-count near `R_ideal`, runs consolidations (promoting Tier-0 chunk clusters into Tier-1 entity/concept candidates, merging entity-candidates into stable nodes), and enforces saturation caps (count + weight per tier). The substrate stays bounded by construction, not by a separate sweep.

**Pruner (all tiers).** Triggered only by **resource pressure** — RAM occupancy above threshold, query latency above target, GPU memory above ceiling. When tripped, removes the weakest atrophied nodes and edges first, content-blind, until the trigger condition clears with margin. **Pruning is the only operation that destroys information**; everything else either transforms or moves. In a system with unbounded RAM and compute, nothing is ever pruned.

**Agent-driven cleanup (all tiers).** Argus, Athene, and other Pantheon agents emit findings post-hoc — `MergeProposal` for duplicate Tier-1 nodes, `ContradictionFinding` with `CONTRADICTS` edges, `RemovalProposal` for demonstrably false information (with audit trail and evidence), `RedundancyProposal` for chunks making the same observation. Oneiros applies these findings at tick boundaries with full audit-ledger entries.

**Shard rebalancing (Tier 3+ only).** At distributed scale, a graph-partitioning job (METIS or spectral bisection) recalculates shard boundaries so SA queries remain ~90% shard-local. Nodes whose embedding neighbourhood has migrated across shard boundaries are moved. Single-server tiers (≤ Tier 2) do not need this operation.

---

*Update this document when the PoC empirical consolidation ratio is known, when Tier 1 ingestion completes, or when infrastructure costs change materially. The principles in `PANTHEON_VISION.md` do not need to be updated when numbers change.*
