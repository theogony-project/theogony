# MNLM PoC — Mesh-Substrate Edition

> **Status: open — research track established 2026-05-13.** Awaiting first run.

## Why this directory exists

The Generation-1 MNLM PoC ([`../poc_legacy/`](../poc_legacy/README.md)) was built under the pre-MESH substrate doctrine. That doctrine has been superseded by the [MESH triplet](../../../MESH_SUBSTRATE.md) and the migration is sequenced by [`MESH_MIGRATION_PLAN.md`](../../../MESH_MIGRATION_PLAN.md). The MNLM as an architectural class is not obsolete — if anything it gets a richer training surface under the new doctrine — but the PoC's underlying assumptions have to be re-laid against the new substrate.

This directory holds the next generation of the PoC, run against the MESH substrate as it becomes available.

## What stays from the Gen-1 PoC

- **The three-stage falsifier** (DBB → MuSiQue → Monkey-3) is the right shape and binding for this track too. See [`../poc_legacy/poc_run_report.md`](../poc_legacy/poc_run_report.md) for the Gen-1 baseline numbers and [`../../../etappes/mesh_native_lm_brief.md`](../../../etappes/mesh_native_lm_brief.md) §6 for the canonical specification.
- **The two-phase training shape:** Phase A representation pretraining → Phase B Micro-GRPO with SA-alignment.
- **The 200-article Wikipedia corpus** at `../poc_legacy/corpus_200.json` is a reasonable starting size; whether to reuse it, replace it, or expand it is operator discretion at the time of the first run.

## What is new in this track

- **Substrate is the MESH substrate.** Tier-0 Observation Chunks and Tier-1+ Consolidated Nodes per [`MESH_SUBSTRATE.md`](../../../MESH_SUBSTRATE.md) §"Node anatomy". Eager linking with the three-signal hierarchy (Q-ID / description / structural). Source-anchor entities for every cited source. Multiple per-node vectors (semantic + frame + optional structural / temporal / description).
- **Edges have a quantitative core plus optional semantic descriptors.** SpMV hot path stays narrow; agent inspection and repair can reason about `relation_descriptor` / `relation_kind` / `description` / `pids` / `creation_context` when needed.
- **Diversified injection is the retrieval discipline.** Maximum Marginal Relevance + weight-class stratification + (when the agent provides structure) sub-mesh signature search via Weisfeiler-Lehman hashing. See [`MESH_RETRIEVAL.md`](../../../MESH_RETRIEVAL.md) §"Diversified injection".
- **Three-factor reinforcement learning is doctrine.** The Micro-GRPO loop now has an explicit place in the substrate's dynamics — Hebbian update modulated by consumer feedback, with eligibility traces for multi-hop credit assignment. The MNLM is not bolted on top of an indifferent substrate; the substrate adjusts toward the MNLM's productive activation patterns and away from its noise. See [`MESH_RETRIEVAL.md`](../../../MESH_RETRIEVAL.md) §"Three-factor reinforcement learning".
- **Frame-sensitive resonance** is the substrate's mechanism for representing polarity, refutation, and modality. The MNLM's training signal therefore distinguishes "Kendall thought Thyroxine was an oxindole derivative" (historical-attributional frame) from "Thyroxine is iodothyronine" (current-ontological frame) without relying on string negation. See [`MESH_RETRIEVAL.md`](../../../MESH_RETRIEVAL.md) §"Frame-sensitive resonance".

## What needs to happen before this track can run

1. **MESH substrate Step S1 merged** — the substrate skeleton (schemas, Lance tables, sparse CSR runtime, minimal Oneiros) per [`MESH_MIGRATION_PLAN.md`](../../../MESH_MIGRATION_PLAN.md) §"Step S1".
2. **MESH substrate Step S2 merged** — Kadmos v2 producing Tier-0 chunks + eager Tier-1 entities into the new substrate.
3. **MESH substrate Step S3 merged** — diversified injection + frame routing retrieval available against the new substrate.

Steps S1–S3 produce the substrate over which the new MNLM PoC trains and evaluates. Before they merge, **this directory is intentionally empty**: there is nothing useful to build against.

## Outputs this directory will eventually carry

- `mesh_run_report.md` — the prose report (analogous to Gen-1's `poc_run_report.md`).
- `phase_a_loss.jsonl` — Phase-A training trace against the new substrate.
- `phase_b_reward.jsonl` — Phase-B Micro-GRPO reward curve.
- `dbb20_results_mesh.json`, `musique_results_mesh.json`, `monkey3_results_mesh.md` — the three-stage falsifier results against the new substrate.
- `comparison_vs_legacy.md` — explicit before-and-after numbers vs. the Gen-1 baseline in `../poc_legacy/`.

## Storage hygiene

The `mesh_inputs/` style scratch directory under `poc_legacy/` accumulated ~500 MB of intermediate Kadmos-v1 chunks during the Gen-1 PoC. That class of intermediate data is now `.gitignore`d under `docs/research/mnlm/poc_*/mesh_inputs/` and `docs/research/mnlm/poc_*/*.log`. Persistent research evidence (training curves, evaluation JSONs, the run report) is committed; raw crawler outputs and log files are not.

## Open questions for the first run

- Which 200 (or N) articles? Reusing `../poc_legacy/corpus_200.json` enables direct comparison; using a fresh corpus avoids confounders from the Gen-1 doctrine bias.
- Which embedding model for `semantic_vector` (the Gen-1 PoC used a smaller model; BGE-M3 class is the doctrine default but expensive at PoC scale).
- Which frame-encoder bootstrap (a heuristic cue-word extractor at first, or a contrastively-trained small encoder once labelled frame pairs exist).
- What is the right Phase-B reward shape now that three-factor learning is doctrine — does the SA-alignment term subsume the eligibility trace term, or are they complementary?

These belong in the first run's brief, not in this README.
