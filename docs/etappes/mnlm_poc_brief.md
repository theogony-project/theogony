# MNLM PoC Pass — Sprint Brief

**Status:** OPERATIVE. Supersedes §13 of `mesh_native_lm_brief.md` as the executable sprint document for the PoC pass. §13 remains as the architecture-level description; this brief is the day-by-day handoff to Talos.

**Filed by:** Hesiod  
**Date:** 2026-05-11  
**Parent document:** [mesh_native_lm_brief.md](mesh_native_lm_brief.md) §13  
**Hand-off target:** Talos  
**Compute environment:** MacBook Pro M4 Pro, 48 GB unified memory (local, MPS) + RunPod (saved for §8 full run — not needed for PoC)

---

## 0. What this brief decides

Four open questions from §13 of `mesh_native_lm_brief.md` are locked here:

1. **Which 200 articles?** → §1. Five domains × 40 articles, with cross-domain structural pairs explicit.
2. **Which base model?** → Qwen2.5-1.5B-Instruct. Not Llama. See §2.
3. **Where does compute run?** → Entirely on M4 Pro local (MPS). RunPod budget is preserved for the §8 full run. See §3.
4. **Does Kadmos need extension before crawling starts?** → No. Crawling starts immediately with the existing `theogony kadmos read` CLI. The §7 MeshInput-export amendment is implemented in parallel (Week 1), not as a prerequisite to crawling. See §4.

---

## 1. The 200-article corpus

### 1.1 Selection rationale

The corpus serves two purposes simultaneously:

- **Phase A training data:** enough structural diversity that the micro-training loss is meaningful, not a single-domain overfit.
- **Monkey-3 seed material:** cross-domain structural analogies must exist *in the corpus* for the Stage-3 test to be valid. Articles are selected so that at least 10 cross-domain structural pairs can be constructed at Week 9.

Five domains, 40 articles each. Within each domain, articles are selected for structural richness (many concepts, many typed relations) rather than length or fame.

### 1.2 Seed titles per domain

Talos uses these seeds to anchor each domain. The remaining slots (up to 40 per domain) are filled by following Wikipedia's "See also" and category links, preferring articles with ≥ 10 internal links to other in-corpus articles. No article is fetched twice; duplicates across domains are resolved in favour of the domain where the article is most structurally central.

**Physics / Natural Science (40 articles)**

| # | Seed title |
|---|---|
| 1 | Bernoulli's principle |
| 2 | Ohm's law |
| 3 | Entropy |
| 4 | Thermodynamics |
| 5 | Fluid dynamics |
| 6 | Maxwell's equations |
| 7 | Special relativity |
| 8 | Wave–particle duality |
| 9 | Conservation of energy |
| 10 | Electromagnetism |

Fill remaining 30 by following physics category links. Prefer articles covering a *mechanism* (not a biography or a list).

**Biology / Life Science (40 articles)**

| # | Seed title |
|---|---|
| 1 | Natural selection |
| 2 | Cell membrane |
| 3 | Action potential |
| 4 | DNA replication |
| 5 | Immune system |
| 6 | Protein folding |
| 7 | Homeostasis |
| 8 | Synaptic plasticity |
| 9 | Enzyme catalysis |
| 10 | Capillary action |

Fill remaining 30 from biology category. Same preference for mechanism articles.

**Mathematics / Formal Systems (40 articles)**

| # | Seed title |
|---|---|
| 1 | Graph theory |
| 2 | Markov chain |
| 3 | Fourier transform |
| 4 | Fixed-point theorem |
| 5 | Eigenvalues and eigenvectors |
| 6 | Cellular automaton |
| 7 | Information theory |
| 8 | Bayes' theorem |
| 9 | Topology |
| 10 | Network theory |

Fill remaining 30 from mathematics category.

**History / Social Systems (40 articles)**

| # | Seed title |
|---|---|
| 1 | Industrial Revolution |
| 2 | Scientific Revolution |
| 3 | French Revolution |
| 4 | Roman Empire |
| 5 | Byzantine Empire |
| 6 | Printing press |
| 7 | Enlightenment |
| 8 | Cold War |
| 9 | Silk Road |
| 10 | Renaissance |

Fill remaining 30 from history category. Prefer articles covering systemic change or network effects (trade routes, communication technologies, institutional transitions) over individual-biography articles.

**Philosophy / Cognition (40 articles)**

| # | Seed title |
|---|---|
| 1 | Epistemology |
| 2 | Emergence |
| 3 | Systems thinking |
| 4 | Reductionism |
| 5 | Analogy |
| 6 | Cognitive dissonance |
| 7 | Mental model |
| 8 | Abstraction |
| 9 | Causality |
| 10 | Feedback |

Fill remaining 30 from philosophy and cognitive science categories.

### 1.3 Known cross-domain structural pairs (Monkey-3 anchors)

These pairs are explicitly in-scope for the Mini-Monkey-3 evaluation at Week 9. They are noted here so Talos can verify that both sides of each pair land in the corpus:

| Pair | Domain A | Domain B | Structural isomorphism |
|---|---|---|---|
| Bernoulli ↔ Ohm | Physics (fluid) | Physics (electrical) | Pressure/voltage drives flow against resistance |
| Natural selection ↔ Markov chain | Biology | Mathematics | State transitions with differential fitness/probability |
| Entropy (thermodynamics) ↔ Information entropy | Physics | Mathematics | Disorder / uncertainty as a state function |
| Immune system ↔ Feedback control | Biology | Philosophy/Cognition | Adaptive response loop with memory |
| Industrial Revolution ↔ Cellular automaton | History | Mathematics | Local rules propagating systemic phase transition |
| Synaptic plasticity ↔ Bayes' theorem | Biology | Mathematics | Belief/weight update proportional to evidence |
| Roman Empire ↔ Network theory | History | Mathematics | Hub-and-spoke topology, single-point-of-failure dynamics |
| Printing press ↔ Graph theory | History | Mathematics | Accelerated diffusion across sparse→dense graphs |
| Protein folding ↔ Fixed-point theorem | Biology | Mathematics | System converging to minimum-energy stable state |
| Fluid dynamics ↔ Eigenvalues and eigenvectors | Physics | Mathematics | Stable flow modes as principal directions |

If any pair's A-side or B-side article was not fetched by Kadmos during the main crawl, fetch it as a supplement (does not count against the 200 budget; fetched explicitly for Monkey-3).

### 1.4 Article list file

Talos commits the final resolved list of 200 titles (after fill-out) to:

```
docs/research/mnlm/poc/corpus_200.json
```

Format:
```json
[
  {"title": "Bernoulli's principle", "domain": "physics", "url": "https://en.wikipedia.org/wiki/Bernoulli%27s_principle", "monkey3_pair": "Ohm's law"},
  ...
]
```

`monkey3_pair` is null for articles not in a cross-domain pair.

---

## 2. Base model: Qwen2.5-1.5B-Instruct

**Locked: `Qwen/Qwen2.5-1.5B-Instruct` from Hugging Face.**

Rationale for Qwen over Llama for the PoC:

- Qwen2.5-1.5B-Instruct has stronger instruction-following at 1.5B than Llama-3.2-1B-Instruct, which matters for the Phase A supervised warmup (the model needs to follow the structural output format).
- Qwen2.5 has better multilingual coverage, relevant if the corpus expansion later includes non-English sources.
- The 1.5B size fits comfortably in M4 Pro unified memory in bfloat16 (~3 GB), leaving headroom for LoRA optimizer states and the GraphProjector + LFM-GAE decoder (~500 MB total for PoC scale).
- The production target remains Qwen2.5-7B-Instruct (not Llama-3-8B-Instruct as written in `mesh_native_lm_brief.md` §3.1 for the Llama-based full run). **This brief supersedes §3.1 on model family only:** the production MNLM uses Qwen, not Llama. The adapter class (rank-16 LoRA on q/k/v/o), the frozen base, and the trainable-surface size (~40 M) are unchanged.

LoRA configuration for the PoC:
- Rank: 8 (reduced from rank-16 in production — sufficient for the PoC, halves trainable params)
- Target modules: `q_proj`, `k_proj`, `v_proj`, `o_proj`
- Trainable params: ~12 M (LoRA) + ~5 M (GraphProjector stub) + ~5 M (LFM-GAE decoder stub) = ~22 M total

---

## 3. Compute split: entirely local for the PoC

**All PoC steps run on M4 Pro MPS. RunPod budget is not spent on the PoC.**

Justification:

| Step | M4 Pro estimate | Feasible? |
|---|---|---|
| Kadmos crawl (200 articles) | ~4–8 h wall clock, ~3–5 EUR LLM API cost | Yes. Runs in background. |
| Schema + scaffolding | 0 GPU | Yes |
| Kadmos amendment (§7) | 0 GPU | Yes |
| Smoke test (Qwen2.5-1.5B, 4-bit) | ~10 min | Yes |
| Phase A micro-training (5 k steps, batch 4) | ~2–4 h on MPS | Yes |
| Mini-DBB-20 | ~20 min | Yes |
| Phase B micro-GRPO (1 k episodes, K=4) | ~2–4 h on MPS | Yes |
| Mini-MuSiQue (50 questions) | ~30 min | Yes |
| Mini-Monkey-3 (10 pairs, 2 raters) | ~0 GPU, ~2 h human | Yes |
| **Total compute** | **~5–10 h wall clock on MPS** | **Fully local** |

The RunPod budget (~61 EUR after top-up) is reserved for:
- Phase A full training in §8 (~80–120 GPU-h on H100, ~250–400 EUR)
- Phase B Graph-GRPO in §8 (~200–400 GPU-h, ~600–1 200 EUR)

The PoC is the evidence that justifies spending that budget. Do not pre-spend it.

---

## 4. Kadmos: crawl starts immediately, amendment in parallel

**Kadmos needs no extension before crawling begins.**

The existing CLI command works:
```bash
theogony kadmos read "Bernoulli's principle"
```

This produces an `AnnotatedReading` JSON and a `KadmosRunReport`, and writes to the persistent LanceDB Chronik. Both artifacts are valid regardless of whether the §7 MeshInput-export amendment exists.

**Crawl strategy:**

Run all 200 articles in batches of 20, sequentially per domain. Do not parallelise beyond what the LLM API rate limit permits. Each article run produces:
- `AnnotatedReading` JSON persisted under `settings.run_reports_dir/kadmos/`
- `KadmosRunReport` (verdict: completed / partial / failed)
- LanceDB entries for all concepts and edges

Failed runs (verdict="failed") are re-queued once. Persistent failures are skipped and logged; if more than 10 articles fail outright, investigate before continuing.

**The §7 amendment is implemented in Week 1 (Sprint-1 commit 3, see §5 below), in parallel with the crawl.** Once the amendment is live, Talos runs a post-processing pass over the already-produced `AnnotatedReading` JSONs to emit `MeshInput`-shaped exports without re-crawling. The LLM API is not called again for this step.

---

## 5. Sprint plan: four weeks

This is tighter than §8's 12-week roadmap. The PoC is purely about stack validation, not production quality.

### Week 1: Crawl + schemas + amendment

**Parallel tracks:**

*Track A — Crawl (background, starts day 1):*
- Begin Kadmos crawl of 200 articles, physics domain first
- Commit `docs/research/mnlm/poc/corpus_200.json` before starting (so the list is locked, not discovered ad-hoc)
- Log each completed article to `docs/research/mnlm/poc/crawl_log.jsonl` (one line per article: title, verdict, concept_count, edge_count, duration_s, cost_eur)

*Track B — Schemas:*
- `feat(mnlm): add MeshInput, MeshDelta, MutationPrimitive, TrajectoryMetadata Pydantic v2 schemas` (§10 commit 1 from `mesh_native_lm_brief.md`)
- `feat(reporting): add MnlmRunReport` (§10 commit 2)
- Import-linter contract in `pyproject.toml`

*Track C — Kadmos amendment:*
- `feat(kadmos): add post-embedding MeshInput export step` (§10 commit 3 from `mesh_native_lm_brief.md` §7)
- After crawl completes: run post-processing pass to emit `MeshInput` JSONs from existing `AnnotatedReading` files
- Commit post-processing results to `docs/research/mnlm/poc/mesh_inputs/` (one file per article, named by title slug)

### Week 2: Scaffolding + smoke test

- `feat(mnlm): scaffold GraphProjector + Graph-KV adapter + LFM-GAE decoder + SubstrateResonantRunner` (§10 commit 3, code part)
- Load `Qwen/Qwen2.5-1.5B-Instruct` in 4-bit on MPS
- Pick one `MeshInput` from the crawl output; run full forward pass: `MeshInput → GraphProjector → Graph-KV forward → SubstrateResonantRunner (K=3, T=4) → LFM-GAE → MeshDelta`
- Assert: no NaN, `MeshDelta` passes `model_validate`, at least one `MutationPrimitive` emitted, SA latency per call < 200 ms

Commit the smoke-test trace as `docs/research/mnlm/poc/poc_pipeline_trace.json`.

### Week 3: Phase A micro-training + Mini-DBB-20

- Prepare training dataset: load all `MeshInput` + corresponding `AnnotatedReading` pairs, apply §5.1 mapping table, produce ~50 k `(MeshInput, MeshDelta)` training tuples
- Run Phase A micro-training: 5 000 steps, batch size 4, AdamW with cosine LR decay, on MPS
- Log loss every 100 steps to `docs/research/mnlm/poc/phase_a_loss.jsonl`
- After training: synthesise 20 Mini-DBB minimal pairs (use the same generator script as §6.1, reduced to 20 pairs), run evaluation, log results

Commit `docs/research/mnlm/poc/phase_a_loss.jsonl` and `docs/research/mnlm/poc/mini_dbb20_results.json`.

### Week 4: Phase B micro-GRPO + Mini-MuSiQue + Mini-Monkey-3 + report

- Phase B micro-GRPO: 1 000 episodes, K=4, reward = SA rank improvement, three auxiliary penalties. Log reward mean every 50 episodes to `docs/research/mnlm/poc/phase_b_reward.jsonl`. Generate `poc_reward_curve.png` from this log.
- Mini-MuSiQue: fetch 50 MuSiQue questions, run Kadmos on their supporting paragraphs (new crawl, does not count against the 200-article corpus), build text-RAG baseline, run both, log accuracy
- Mini-Monkey-3: select 10 cross-domain pairs from §1.3, run MNLM and 1.5B text-RAG baseline, human rating by 2 raters (qualitative only)
- Write `docs/research/mnlm/poc/poc_run_report.md` (full MnlmRunReport-structured narrative)

---

## 6. Output artefacts

All committed to `docs/research/mnlm/poc/`:

| File | Content | When |
|---|---|---|
| `corpus_200.json` | Final article list, 200 entries with domain + monkey3_pair | Before crawl starts |
| `crawl_log.jsonl` | One line per article: title, verdict, concept_count, edge_count, duration_s, cost_eur | End of Week 1 |
| `mesh_inputs/` | One `MeshInput` JSON per article | End of Week 1 |
| `poc_pipeline_trace.json` | One end-to-end trace: article → MeshInput → MeshDelta → SA result | End of Week 2 |
| `phase_a_loss.jsonl` | Loss every 100 steps over 5 000-step micro-training | End of Week 3 |
| `mini_dbb20_results.json` | 20-pair results, per-direction accuracy | End of Week 3 |
| `phase_b_reward.jsonl` | Episode reward every 50 episodes over 1 000 episodes | End of Week 4 |
| `poc_reward_curve.png` | Reward curve plot | End of Week 4 |
| `mini_musique_results.json` | 50-question accuracy: MNLM vs text-RAG | End of Week 4 |
| `mini_monkey3_results.md` | 10-pair qualitative ratings, 2 raters | End of Week 4 |
| `poc_run_report.md` | Full MnlmRunReport-structured narrative | End of Week 4 |

---

## 7. Decision criteria

After Week 4, the human commander reads `poc_run_report.md` and checks three signals:

| Signal | Positive | Negative |
|---|---|---|
| Phase A loss | Monotonically decreasing over 5 000 steps | Flat or oscillating without trend |
| Phase B reward | Mean reward higher in episodes 500–1 000 than in episodes 0–500 | Flat or declining |
| Mini-DBB-20 accuracy | > 60 % (above chance = 50 %) | ≤ 55 % (indistinguishable from chance) |

All three positive → file `PHX-####: sponsor compute acquisition for MNLM §8 full run`, attach PoC artefacts, proceed to sponsor outreach.

Any signal negative → file Phoenix Backlog ticket against `mesh_native_lm_brief.md`, escalate to Daedalus. Do not pitch a sponsor before understanding why the signal failed.

---

## 8. What does NOT need to be good

This is a PoC pass. The following are explicitly out of scope and not to be chased:

- MeshDelta quality or semantic correctness (the model is not trained to convergence)
- Mini-DBB-20 accuracy ≥ 95 % (that is the §6.1 production threshold, not the PoC threshold)
- Mini-MuSiQue accuracy competitive with text-RAG (not required; record direction only)
- Mini-Monkey-3 statistical significance (qualitative only)
- Any performance optimisation of the MPS training loop

If Talos finds itself optimising any of the above during the PoC sprint, stop and redirect to the next item on the sprint plan.

---

*This brief is the operative PoC document. The crawl starts on day 1.*
