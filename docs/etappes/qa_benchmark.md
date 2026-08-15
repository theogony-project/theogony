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

## Results — Kadmos-grade construction (LLM extraction)

The first-cut left one dominant suspect: the entity bridges were spaCy-NER
**co-occurrence**, which bridges every pair of entities sharing a passage whether
or not they are related. So the follow-up experiment asks: *do clean, typed
relational edges — Kadmos v2's own LLM extraction — carry the multi-hop signal
that noisy co-occurrence bridges do not?*

**Design: one corpus, one question set, two graphs.** Identical passages,
embeddings, passage-kNN backbone, BM25 and bridge capping. The *only* difference
is where entity↔entity bridges come from. Extraction uses Kadmos's real
`SYSTEM_PROMPT` and `ParagraphReadingOutput` schema
(`scripts/mesh_qa_kadmos.py`), so this measures the substrate's actual reading
contract.

Run on the **full corpora**, same as the first-cut above, so the numbers are
directly comparable. Extraction: `deepseek-chat` at concurrency 24 —
2Wiki 6,089 passages (0 failures, €1.53, 22 min), HotpotQA 9,811 passages
(6 failures = 0.06 %, €2.77, 34 min). **Total €4.30.**

| | 2Wiki cheap | 2Wiki Kadmos | HotpotQA cheap | HotpotQA Kadmos |
|---|---:|---:|---:|---:|
| entity nodes | 31,794 | 32,499 | 55,155 | 61,540 |
| entity bridges | 323,314 | **37,281** | 489,540 | **77,303** |
| bridges per entity | 10.2 | **1.15** | 8.9 | **1.26** |
| `sa_raw` recall@5 | 0.151 | **0.221** | 0.147 | **0.303** |
| `sa_ppr` recall@5 | 0.686 | 0.687 | 0.823 | 0.815 |
| kNN recall@5 (reference) | 0.683 | 0.683 | 0.832 | 0.832 |

Density sweep, `sa_ppr` recall@5 as the bridge fraction grows:

| construction | 0 % | 25 % | 50 % | 100 % | kNN |
|---|---:|---:|---:|---:|---:|
| 2Wiki cheap | **0.691** | 0.688 | 0.687 | 0.686 | 0.683 |
| 2Wiki Kadmos | **0.691** | 0.688 | 0.690 | 0.687 | 0.683 |
| HotpotQA cheap | 0.807 | 0.822 | 0.818 | 0.823 | **0.832** |
| HotpotQA Kadmos | 0.800 | 0.800 | 0.805 | 0.815 | **0.832** |

**What this shows — consistent across both datasets:**

1. **The extraction did what it was supposed to.** Kadmos bridges are **6–9×
   sparser** (1.2 vs 9–10 per entity): it asserts relations instead of bridging
   everything that co-occurs. The construction difference is real, not marginal.
2. **Clean edges rescue the naive operator — substantially.** `sa_raw` improves
   **+46 %** on 2Wiki (0.151 → 0.221) and **+106 %** on HotpotQA (0.147 → 0.303).
   Hub collapse is therefore partly an artefact of *noisy bridges*, not only of
   the operator. This is the clearest positive effect of Kadmos-grade extraction
   found anywhere in this benchmark.
3. **…but they add nothing to the fair operator.** `sa_ppr` moves +0.001 (2Wiki)
   and **−0.008** (HotpotQA). **Clean edges and degree normalisation are
   substitutes, not complements** — each fixes what the other already fixed. This
   is the sharpest result of the run.
4. **Still no crossover, in either construction, on either dataset.** SA reaches
   parity on 2Wiki (+0.004) and stays *below* kNN on HotpotQA (−0.017). On 2Wiki
   the best SA configuration is **zero entity bridges** (0.691) — the entity layer
   contributes nothing net-positive there, and the small edge SA holds over kNN
   comes from diffusion over the *passage-kNN* graph, not from entity structure.

**The hypothesis is refuted on this evidence.** Kadmos-grade edges do not lift
degree-aware Spreading Activation above dense-kNN parity. The predicted multi-hop
advantage is **not** explained by edge cleanliness — a genuinely useful finding,
because it removes the most plausible remaining explanation and forces the search
elsewhere.

One honest nuance in favour of clean edges: on HotpotQA the Kadmos density curve
rises monotonically (0.800 → 0.815) while the cheap curve is flat and noisy — the
*direction* is right, the *level* is not. More clean bridges do help; they start
from a lower base and never reach kNN.

**Where to look next** (hypotheses, not conclusions):

- **The seeding ceiling — the strongest suspect.** SA seeds from the top-10
  passages by query cosine, so it *starts inside kNN's neighbourhood*. Bridges can
  only re-rank and expand from there; a gold passage far from every seed is rarely
  reached before damping kills the mass. If retrieval is seeded by the thing it is
  meant to beat, parity may be structural. Testing this means seeding differently
  (entity-anchored seeds, query-term seeds, larger seed sets).
- **Propagation shape.** 3 hops at damping 0.5 may be too shallow, or too steep,
  for bridge paths to contribute.
- **The benchmark itself.** 2Wiki/HotpotQA gold passages share heavy lexical
  overlap with their questions, so embeddings may already be near the achievable
  ceiling; a corpus where the answer genuinely cannot be found by similarity is a
  fairer test of the claim.

## Results — the seeding ceiling (and the correction it forces)

The two runs above left one structural variable untested: **seeding**. SA is
seeded from the top-S passages by query cosine, so it starts *inside* the
neighbourhood dense kNN already returns. A method that only re-ranks its own
seeds cannot beat the retriever that produced them, however good its edges are.

`scripts/mesh_qa_seeding.py` sweeps seeding scheme × seed count and reports three
diagnostics that make this answerable rather than inferable: **rescue rate** (of
the gold passages the seeds *missed*, the fraction SA pulls into its top-5 —
SA's unique contribution), **head-to-head** hits, and **seed retention**.

### The parity was an artefact of the harness

At **S = 5**, on both multi-hop datasets, with the Kadmos graph:

| | seed retention | rescue rate | SA recall@5 | kNN recall@5 |
|---|---:|---:|---:|---:|
| 2WikiMultihopQA | **1.000** | **0.000** | 0.683 | 0.683 |
| HotpotQA | **1.000** | **0.000** | 0.832 | 0.832 |

SA's top-5 is *entirely* its seed set, it rescues **not one** gold passage the
seeds missed, and its recall equals kNN's **to three decimals**. That is not
approximate parity — it is identity. **The earlier "SA ties kNN" result was a
property of the seeding configuration (S = 10 ≥ k = 5), not of the substrate.**
The benchmark was measuring a re-ranker of kNN output and calling it a graph.

### Given room, the graph does contribute

Narrowing the seeds forces propagation to do the work. Full sweep, all questions:

| dataset | best config | SA recall@5 | kNN recall@5 | Δ | rescue rate |
|---|---|---:|---:|---:|---:|
| 2WikiMultihopQA | hybrid, S=2 | **0.797** | 0.683 | **+0.114** | 0.421 |
| HotpotQA | passage, S=3 | **0.862** | 0.832 | **+0.030** | 0.362 |

Both datasets peak at narrow seeding and fall back to exactly kNN at S = 5. The
rescue rate is what makes this readable: at the optimum SA is recovering 36–42 %
of the gold its seeds never contained — the graph is reaching past the embedding,
which is the whole claim.

### Held out, so the number is not selected on the data it is measured on

Picking the best (mode, S) from a sweep and quoting it is selection on the test
set. `--tune-test` splits the questions in half, selects the configuration on the
tune half, and reports only that configuration on the held-out half:

| dataset | selected on tune | held-out SA@5 | held-out kNN@5 | Δ |
|---|---|---:|---:|---:|
| 2WikiMultihopQA (multi-hop) | hybrid, S=2 | **0.818** | 0.717 | **+0.102** |
| HotpotQA (multi-hop) | passage, S=3 | **0.857** | 0.827 | **+0.030** |
| PopQA (single-hop control) | passage, S=10 | 0.497 | 0.503 | −0.007 |

**This is the first evidence in this benchmark that Spreading Activation beats
dense kNN** — on held-out questions, with the configuration chosen without seeing
them.

The control behaves exactly as it should: on single-hop PopQA the tuning half
selected the **widest** seeding on offer (S=10), i.e. it found no benefit in
letting the graph work and settled on the configuration closest to plain kNN —
and the held-out difference is −0.007, inside noise. Gains where multi-hop
structure exists, no regression where it does not, is the bar HippoRAG 2 set and
the failure that sank GraphRAG/LightRAG as general retrievers.

**Caveats that keep this honest:**

- **There is no universal setting.** The selected configuration differs per corpus
  (hybrid S=2 / passage S=3 / passage S=10). S must be tuned per deployment; this
  is a tunable regime, not a constant.
- **The kNN baseline is untuned and un-reranked.** It has no knob to tune, and a
  cross-encoder rerank would raise it. The honest next step is to make the
  baseline *harder*, not to bank the current margin.
- **PopQA ran on the cheap construction** (no cached Kadmos readings for that
  corpus), so its control status covers seeding, not extraction quality.
- Single 384-d embedder throughout; absolute numbers stay a lower bound.

### The correction this forces to the earlier conclusions

The first two runs concluded that neither density nor edge cleanliness lifts SA
past kNN. That conclusion stands *for the configuration it was measured in* — and
that configuration was over-seeded to the point where no edge property could have
mattered. Two consequences:

- **The Kadmos-grade A/B needs re-reading.** Clean edges showed no benefit to
  `sa_ppr` at S = 10 — but at S = 10 nothing could show a benefit, because SA was
  returning its seeds. Whether clean edges help *at narrow seeding* is now an open
  question the earlier run cannot answer.
- **Production was never in the broken regime.** `retrieve()` defaults to
  `k_seeds = 8` with `top_k = 30` (S/k ≈ 0.27), well inside the range where the
  graph must work. The benchmark's S/k = 2.0 was unrepresentative of the system it
  was measuring. The relevant quantity appears to be **S relative to the retrieval
  depth**, not S alone.

## Reading the numbers honestly

- Absolute recall is a **lower bound**: a 384-d `bge-small-en` embedder and no
  cross-encoder rerank. HippoRAG's published numbers use a 7B embedder
  (NV-Embed-2). The point here is the **harness**, the **SA−kNN density curve**,
  and the **construction A/B** — not to top a leaderboard.
- Every method is measured against the *same* embedder, so the SA-vs-kNN contrast
  is unaffected by that ceiling; a stronger embedder would lift both arms.
- Remaining fidelity upgrades, in order of expected payoff now that construction
  has been tested: (1) **alternative seeding** — the leading suspect above, and the
  only untested structural variable; (2) `bge-large-en-v1.5` embedder;
  (3) a `bge-reranker-v2-m3` cross-encoder to strengthen the kNN baseline (making
  the bar *harder*, which is the honest direction); (4) the full 1,000-question
  splits for exact comparability with published HippoRAG numbers.
- What would change the conclusion: a seeding scheme under which `sa_ppr` clears
  kNN by more than noise on both multi-hop sets, without regressing PopQA.

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
