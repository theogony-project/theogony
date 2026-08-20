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

**Re-verified 2026-08-20 against current `main`**, a month and roughly forty PRs
later — indices, entity names, P-IDs, name-anchored seeding and a rewritten
maintenance pass all landed in between. All three numbers reproduce bit for bit,
including the configuration each one selects on its tuning half:

| dataset | selected on tune | held-out SA@5 | held-out kNN@5 | Δ |
|---|---|---:|---:|---:|
| 2WikiMultihopQA | hybrid, S=2 | 0.818 | 0.717 | +0.102 |
| HotpotQA | passage, S=3 | 0.857 | 0.827 | +0.030 |
| PopQA (control) | passage, S=10 | 0.497 | 0.503 | −0.007 |

Two things the re-run makes plainer than the first pass did.

**The advantage is sharply peaked in S.** On 2Wiki: 0.723 at S=1, **0.818 at
S=2**, 0.747 at S=3, and exactly kNN's 0.717 at S=5 where rescue falls to 0.000
and seed retention to 1.000. A sweep whose grid skips S=2 selects S=1 and reports
+0.007 — which is what happened on the first re-run here, before the grid was
widened. The number is real and it is also one grid point wide, and anyone
quoting it should know that.

**The same shape appears on a different corpus with a different harness.** On the
founding mesh, seeding on the entities a question *names* — an exact index
lookup rather than vector similarity — moved recall from 48% to 65% (PHX-1068),
while the graph's own contribution was unchanged. Two corpora, two independent
measurements, one conclusion: **the graph carries the answer, and its value is
decided at the point of entry.** That claim is not in the MESH triplet.

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

- **The Kadmos-grade A/B needed re-reading** — and has since been re-run at narrow
  seeding; see the section below. The short version: the original conclusion
  survives at the optimum, but only because the passage backbone masks the entity
  layer. Where the entity layer is load-bearing, construction quality decides.
- **Production was never in the broken regime.** `retrieve()` defaults to
  `k_seeds = 8` with `top_k = 30` (S/k ≈ 0.27), well inside the range where the
  graph must work. The benchmark's S/k = 2.0 was unrepresentative of the system it
  was measuring. The relevant quantity appears to be **S relative to the retrieval
  depth**, not S alone.

## Results — the Kadmos A/B, re-run at narrow seeding

The construction A/B was originally measured at S = 10, where SA returns its own
seed set and **no** edge property could have shown an effect. Re-running it across
the seeding sweep (both constructions, identical seeds, cached readings, zero
cost) gives a sharper answer than either earlier run:

`sa_ppr` recall@5, cheap vs Kadmos at matched seeding:

| mode / S | 2Wiki cheap | 2Wiki Kadmos | Δ | Hotpot cheap | Hotpot Kadmos | Δ |
|---|---:|---:|---:|---:|---:|---:|
| hybrid, S=2 *(overall optimum)* | 0.795 | 0.797 | +0.002 | 0.842 | 0.845 | +0.003 |
| passage, S=3 | 0.764 | 0.774 | +0.010 | 0.853 | 0.862 | +0.009 |
| **entity, S=2** | 0.608 | **0.788** | **+0.180** | 0.583 | **0.717** | **+0.134** |
| **entity, S=3** | 0.589 | **0.738** | **+0.149** | 0.575 | **0.697** | **+0.122** |

**The answer depends entirely on whether the entity layer is load-bearing.**

- **Seeding passages (or hybrid): construction is nearly invisible** (±0.01). The
  original conclusion — clean edges add nothing to the fair operator — *survives*,
  now measured under conditions where it could have failed. But the reason is not
  that clean edges are worthless: it is that the **passage-kNN backbone carries the
  signal**, and whatever the entity layer contributes is redundant with it.
- **Seeding entities: construction decides** (+0.12 to +0.18). Here every path runs
  through the entity graph, so entity and relation quality becomes the bottleneck,
  and Kadmos's typed relations beat spaCy co-occurrence decisively.

**The uncomfortable reading, stated plainly.** Kadmos-grade extraction demonstrably
produces a better entity graph — but on this benchmark that better graph does not
raise the *overall* optimum, because a plain passage-similarity backbone already
reaches the same passages by a shorter route. For a substrate whose thesis is that
typed entity relations are the point, that is a result worth sitting with rather
than explaining away: the relations are better, and on this task the improvement is
largely masked.

**What it does not settle.** These corpora are passage-retrieval benchmarks whose
gold is defined as *passages*, which structurally favours a passage backbone. A
task whose answer is an **entity** or a **path** — the substrate's actual target
shape — is where a better entity graph should pay, and this benchmark cannot see
that. Designing that measurement is the natural next etappe.

## What a query actually costs

Worth stating plainly, because the CLI's ~17 s makes retrieval *look* expensive
and it is not. Measured on the founding mesh (463 nodes / 27.8k edges):

| | cost | what it is |
|---|---:|---|
| `import torch` + `sentence_transformers` + embedder | 11.7 s | **per process**, before any query |
| first query | ~1.9 s | builds the CSR and the descriptor cache |
| **warm query** | **57 ms** | of which **Spreading Activation is 13 ms** |

The retrieval primitive is the cheapest part of the chain. For scale: one token
through an 8B model is ~16 GFLOPs, while three hops over this mesh is ~167 kFLOPs
— about **100,000× less arithmetic**. The 13 ms is Python and torch dispatch
overhead, not the mathematics.

Everything else is the cost of *not* being a resident server: an LLM loads its
weights once and never touches disk again during inference, and it has no
lookup step at all, because its knowledge *is* the matrix it multiplies. The
substrate's assembly step exists because it returns something an LLM cannot —
named nodes, descriptions, provenance — but it was implemented as one Lance query
per node plus a filtered metadata query per call, which cost 395 ms of a 430 ms
warm query. Batching both took it to 19 ms.

The remaining 11.7 s of process startup is amortised by any long-running host;
`MESH_IMPLEMENTATION.md`'s Hot/Warm/Cold tiering is the doctrine's version of the
same point, and the Cockpit already gets it right ("the first mesh query pays the
one-time index build; every subsequent query is sub-second").

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
