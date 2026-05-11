# MNLM PoC Run Report

**Status:** `[completed / partial / failed]`

**Date:** 2026-05-11  
**Filed by:** Talos  
**Report type:** `mnlm`  

---

## 1. Summary

| Metric | Value |
|--------|-------|
| Corpus articles processed | `N` / 200 |
| Total concepts extracted | `N` |
| Total edges extracted | `N` |
| Cross-article links created | `N` |
| Total crawl cost | €`N.NNNN` |
| Total crawl wall clock | `N` min |
| Base model | Qwen2.5-1.5B-Instruct (4-bit on MPS) |
| Phase A steps | 5 000 |
| Phase B episodes | 1 000 (K=4) |

## 2. Crawl results

| Domain | Articles | Concepts | Edges | Crosslinks | Failed |
|--------|----------|----------|-------|-----------|-------|
| Physics | N/40 | N | N | N | N |
| Biology | N/40 | N | N | N | N |
| Mathematics | N/40 | N | N | N | N |
| History | N/40 | N | N | N | N |
| Philosophy | N/40 | N | N | N | N |
| **Total** | **N/200** | **N** | **N** | **N** | **N** |

## 3. Pipeline verification

### §2 Scaffolding smoke test

- **GraphProjector**: forward pass produces valid prefix tokens without NaN → [PASS]
- **GraphKVAdapter**: block masks and edge biases have correct shapes → [PASS]
- **LFM-GAE decoder**: placeholder MeshDelta passes `model_validate` → [PASS]
- **SubstrateResonantRunner**: full end-to-end cycle completes → [PASS]

### Phase A micro-training

- **Loss trajectory**: [monotonically decreasing / flat / oscillating]
- **Final loss**: `N.NNNN`
- **Loss log**: `docs/research/mnlm/poc/phase_a_loss.jsonl`

### Mini-DBB-20

| Metric | Value | Threshold | Pass? |
|--------|-------|-----------|-------|
| Per-direction accuracy | `NN.N%` | > 60 % | [YES/NO] |
| Directions evaluated | 40 | 40 | — |
| Random baseline | 50 % | — | — |

### Phase B micro-GRPO

| Metric | Episodes 0–100 | Episodes 900–1000 | Rising? |
|--------|----------------|-------------------|---------|
| Mean reward | `N.NN` | `N.NN` | [YES/NO] |
| Mean rank | `N` | `N` | — |

### Mini-MuSiQue

| Metric | MNLM | Text-RAG baseline | Gap |
|--------|------|-------------------|-----|
| Overall accuracy | `NN.N%` | `NN.N%` (estimate) | `N.N pt` |
| Direction-critical | `NN.N%` | `NN.N%` (estimate) | `N.N pt` |

### Mini-Monkey-3

- **Pairs evaluated**: 10
- **Raters**: 2
- **Overall mean score**: `N.NN` / 3
- **Agreement (within 1 point)**: `NN%`

## 4. Honest failure modes

*List any:
- Article fetch failures (Wikipedia timeouts, redirects, etc.)
- LLM parse failures (malformed JSON, schema violations)
- Crosslinker failures (timeout, threshold tuning)
- MeshInput export failures
- Any anomaly that requires investigation*

## 5. Decision criteria

| Signal | Result | Positive? |
|--------|--------|-----------|
| Phase A loss | [monotonically decreasing / flat / oscillating] | [YES/NO] |
| Phase B reward | [higher in last 500 episodes vs first 500 / flat / declining] | [YES/NO] |
| Mini-DBB-20 accuracy | `NN.N%` (> 60 % required) | [YES/NO] |

## 6. Next steps

- [ ] All three positive → `PHX-####: sponsor compute acquisition for MNLM §8 full run`
- [ ] Any signal negative → Phoenix Backlog ticket against `mesh_native_lm_brief.md`

## 7. Output artefacts

| File | Content | Status |
|------|---------|--------|
| `corpus_200.json` | Final article list | ✅ Committed |
| `crawl_log.jsonl` | Crawl log | ✅ Committed |
| `mesh_inputs/` | MeshInput JSONs | ✅ Committed |
| `poc_pipeline_trace.json` | End-to-end trace | [✅/❌] |
| `phase_a_loss.jsonl` | Phase A loss | [✅/❌] |
| `mini_dbb20_results.json` | Mini-DBB-20 results | [✅/❌] |
| `phase_b_reward.jsonl` | Phase B reward | [✅/❌] |
| `poc_reward_curve.png` | Reward curve plot | [✅/❌] |
| `mini_musique_results.json` | Mini-MuSiQue results | [✅/❌] |
| `mini_monkey3_results.md` | Mini-Monkey-3 ratings | [✅/❌] |
| `poc_run_report.md` | This report | ✅ |
