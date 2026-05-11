# Chronik Scale Analysis

**Status:** Living document. Update when hardware prices, corpus estimates, or infrastructure assumptions change materially.  
**Companion:** [`PANTHEON_VISION.md`](PANTHEON_VISION.md) §"The Scale of the Chronik" — the stable principles. This document holds the numbers.  
**Last updated:** 2026-05-11

---

## Why this document exists separately

Concrete storage estimates, cost figures, and infrastructure tier descriptions age faster than architectural principles. This document holds the perishable specifics so that `PANTHEON_VISION.md` can remain stable while this document is revised as the project grows and hardware economics change.

---

## The consolidation ratio

When Kadmos reads a Wikipedia article, it extracts concept nodes and edges. When a second article describes the same concept, the MNLM emits a `MergeNodes` primitive rather than a new node. The consolidation ratio — what fraction of raw Kadmos output collapses into existing nodes — has been estimated at **~60–80%** based on embedding-cluster analysis of medium-sized corpora.

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
| Concept nodes | ~500 million | **~100–150 million** |
| Explicit structural edges (Kadmos) | ~1 billion | ~1 billion |
| With kNN similarity wiring (100×) | — | ~10–15 billion |
| Node storage (384-dim float32 embeddings + metadata) | ~850 GB | **~250–380 GB** |
| Edge storage (codebook id + 32-dim nuance + weight) | ~350 GB | ~350–500 GB |
| **Total consolidated storage** | ~1.2 TB raw | **~5–8 TB** |

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

| Tier | Vector store | Sparse adjacency | SA implementation |
|---|---|---|---|
| 0–1 | LanceDB (local/cloud) | PyTorch CSR in RAM | Single-node SpMV |
| 2 | LanceDB Cloud or Milvus | PyTorch CSR, high-memory server | Single-node SpMV |
| 3 | Milvus distributed | GraphBLAS / DistDGL distributed | Hierarchical SA (coarse routing + fine within shard) |
| 4 | Milvus + per-sub-mesh private stores | Global distributed + local private shards | SA with permission masks per tier |

The transition from Tier 1 to Tier 2 is a configuration change (larger server). The transition from Tier 2 to Tier 3 is an infrastructure change (distributed systems). The transition from Tier 3 to Tier 4 is an architectural change (federation protocol, permission masks, sub-mesh ownership model).

Each transition is designed as an addition to the existing substrate, not a rewrite. The LanceDB columnar format, PyTorch CSR layout, and SpMV-based SA primitive are forward-compatible with Milvus, GraphBLAS, and distributed SA at higher tiers.

---

## Periodic maintenance operations

As the Chronik grows, three background operations keep it operationally stable:

**Weekly shard rebalancing (Tier 3+).** A graph partitioning job (METIS or spectral bisection) recalculates shard boundaries to ensure SA queries remain ~90% shard-local. Nodes whose embedding neighbourhood has migrated across shard boundaries are moved. This prevents hot-spots and cross-shard traffic from growing unboundedly.

**Hebbian decay sweep (all tiers).** Edges not traversed by Spreading Activation over a configurable window (default: 90 days) have their `hebbian_strength` decayed. Edges below a minimum threshold are candidates for `Invalidate`. This bounds the growth of the edge layer and prevents dead knowledge from accumulating indefinitely.

**Consolidation pass (all tiers).** The MNLM and immune system continuously emit `MergeNodes` and `Invalidate` primitives as they identify duplicates and contradictions. A weekly consolidation sweep collects pending primitives, applies them in batch, and re-indexes affected nodes. This is the mechanism by which the Chronik shrinks intelligently as it grows in coverage.

---

*Update this document when the PoC empirical consolidation ratio is known, when Tier 1 ingestion completes, or when infrastructure costs change materially. The principles in `PANTHEON_VISION.md` do not need to be updated when numbers change.*
