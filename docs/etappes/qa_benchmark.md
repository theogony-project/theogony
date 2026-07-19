# QA-retrieval benchmark — Spreading Activation vs kNN / BM25

**Operationalises README empirical question 2:** *does Spreading Activation over
a dense vector-graph retrieve better than kNN + heuristic traversal at high edge
density?* — as a standard, externally-comparable measurement instead of an
internal link-prediction number.

This is the etappe that turns *believing* the retrieval thesis into *showing* it
on the benchmarks the graph-retrieval field actually uses.

## What it measures

Passage **recall@2 / @5** over the **shared per-dataset corpus**, the protocol
HippoRAG / HippoRAG 2 established (retrieve over the whole corpus, gold = a
question's supporting passages), on:

- **Multi-hop trio** — MuSiQue, 2WikiMultihopQA, HotpotQA (where graph structure
  is expected to help).
- **Single-hop control** — PopQA (the no-regression test: SA must not hurt
  single-hop retrieval, the failure that sank GraphRAG/LightRAG as general
  retrievers).

Methods compared, all over the same corpus so the comparison isolates the
retrieval *mechanism*:

| method | what it is |
|---|---|
| `bm25` | lexical baseline (Okapi BM25, dependency-free) |
| `knn` | dense retrieval — question↔passage cosine, **no graph** (the geometry-only reference) |
| `sa` | Spreading Activation — dense query→passage seeding, then PPR-style propagation over the graph |

## The headline: the edge-density ablation

The novel contribution. No published study measures retrieval quality as an
explicit **function of edge density** for activation vs kNN. This harness does:
it holds the geometric backbone fixed and sweeps the fraction of **entity-bridge
edges**, reading whether the SA recall curve *pulls away from* the (flat,
edge-independent) kNN reference as structural density rises. That crossover is
the phase transition the architecture bets on
([`scaling.py`](../../src/theogony/mesh/eval/scaling.py) does the same on
link-prediction; this does it on QA recall).

## Construction: cheap and LLM-free (first-cut), Kadmos-grade later

The graph is built **without any paid LLM**, which the literature establishes as
a legitimate first data point — LinearRAG (ICLR 2026, relation-free spaCy-entity
graph) and SPRIG (2026, NER co-occurrence + PPR) both match or beat LLM-KG
GraphRAG on this exact trio:

- **passage nodes** — one per corpus passage, embedded locally (BGE).
- **entity nodes** — local spaCy NER (`en_core_web_sm`), normalized + deduped.
- **edges** — passage↔entity containment, entity↔entity co-occurrence (the
  structural bridge and density dial), passage↔passage semantic-kNN (geometric).

The retrieval kernel (`propagate`) is **identical** to the substrate's, so this
measures the real primitive; only the *construction* is cheap. **Kadmos v2 LLM
extraction is a documented fidelity upgrade**, not a prerequisite — swap the
graph builder, keep the harness.

Everything runs **offline after a one-time dataset fetch** and needs no new
dependencies (spaCy + sentence-transformers are already project deps; BM25 is
hand-rolled; datasets fetch over plain HTTP).

## Results — first-cut (LLM-free construction)

First run: `n = 300` questions/dataset, `bge-small-en-v1.5` embeddings, spaCy
`en_core_web_sm` entities, `knn-k = 10`, seed = 0. Gold coverage 1.000 (every
question's supporting titles matched the shared corpus). **Passage recall@5:**

| dataset | type | BM25 | kNN (dense) | SA raw | SA ppr |
|---|---|---:|---:|---:|---:|
| 2WikiMultihopQA | multi-hop | 0.639 | **0.683** | 0.151 | **0.686** |
| HotpotQA | multi-hop | 0.733 | **0.832** | 0.147 | 0.823 |
| PopQA | single-hop (control) | 0.390 | **0.512** | 0.090 | 0.510 |

Edge-density ablation (SA ppr recall@5 as the entity-bridge fraction grows, vs
the flat kNN reference):

| dataset | ppr@5 @0% | @25% | @50% | @100% | kNN (flat) |
|---|---:|---:|---:|---:|---:|
| 2WikiMultihopQA | 0.691 | 0.688 | 0.687 | 0.686 | 0.683 |
| HotpotQA | 0.807 | 0.822 | 0.818 | 0.823 | 0.832 |
| PopQA | 0.512 | 0.512 | 0.510 | 0.510 | 0.512 |

**Three findings, all consistent across the three datasets:**

1. **Naive Spreading Activation collapses** (SA raw recall@5 = 0.09–0.15
   everywhere). This is an external confirmation of the substrate's own
   hub-collapse diagnosis (PHX-1042): degree hubs — common entities like dates
   and frequent names — absorb the activation. **Degree-awareness is mandatory,
   not a tuning knob.**
2. **Degree-aware SA (PPR) reaches dense-kNN parity and does not regress on
   single-hop.** SA ppr ties kNN within ±0.01 on all three, and PopQA — the
   single-hop control — is 0.510 vs 0.512, i.e. **no regression**. This is the
   exact test that sank GraphRAG / LightRAG as general retrievers; the substrate's
   fair operator passes it.
3. **No phase transition on cheap construction.** The density curve is flat
   (2Wiki, PopQA) to slightly-below-kNN (HotpotQA); adding entity-bridge edges
   does **not** lift SA past kNN. On this graph the multi-hop advantage the thesis
   predicts does not appear — the cheap NER co-occurrence bridges are too noisy to
   carry it.

**Honest bottom line.** The thesis (README Q2) is **neither confirmed nor
refuted** here — and that is the point of a first-cut: it establishes the
measurement, reproduces the known failure mode externally, finds SA↔kNN parity,
and *localises* the open question. The predicted multi-hop lift requires **clean
relational edges (Kadmos-grade LLM extraction)**, not cheap co-occurrence. The
harness now hands the next experiment a concrete bar to beat: **kNN recall@5 of
0.68 (2Wiki) / 0.83 (HotpotQA) / 0.51 (PopQA)**. If Kadmos-grade construction
cannot clear that, the thesis is in trouble; if it clears it *and* the density
curve turns positive, that is the first real evidence for it.

## Reading the numbers honestly

- Absolute recall is a **lower bound**: cheap spaCy+BGE construction, no
  cross-encoder rerank, no LLM extraction. HippoRAG's published numbers use a 7B
  embedder (NV-Embed-2) + LLM OpenIE. The point of this first-cut is the
  **harness** and the **SA−kNN density curve**, not to top a leaderboard.
- Fidelity upgrades, in order of expected payoff: (1) `bge-large-en-v1.5`
  embedder; (2) a `bge-reranker-v2-m3` cross-encoder for the kNN+rerank baseline
  (`--reranker`, downloads ~568 MB); (3) Kadmos-grade LLM extraction for the
  graph; (4) the full 1,000-question splits for exact comparability.

## How to run

```bash
# multi-hop, first-cut (offline after the dataset fetch; no LLM key needed)
./.venv/bin/python scripts/mesh_qa_retrieval.py --dataset 2wikimultihopqa --max-questions 300 --knn-k 10

# single-hop no-regression control
./.venv/bin/python scripts/mesh_qa_retrieval.py --dataset popqa --max-questions 300

# the density ablation is always emitted; tune it with --densities
./.venv/bin/python scripts/mesh_qa_retrieval.py --dataset hotpotqa --densities 0.0,0.1,0.25,0.5,1.0
```

Reports land in `data/run_reports/mesh_eval/qa_retrieval_<run_id>.json`. Compute
lives in [`src/theogony/mesh/eval/qa_retrieval.py`](../../src/theogony/mesh/eval/qa_retrieval.py)
(pure, unit-tested offline); the driver is
[`scripts/mesh_qa_retrieval.py`](../../scripts/mesh_qa_retrieval.py).

## References

- HippoRAG 2 — *From RAG to Memory* (arXiv:2502.14802) · dataset `osunlp/HippoRAG_v2`
- LinearRAG (arXiv:2510.10114) · SPRIG / *Democratizing GraphRAG* (arXiv:2602.23372)
- MuSiQue (arXiv:2108.00573) · 2WikiMultihopQA · HotpotQA · PopQA
