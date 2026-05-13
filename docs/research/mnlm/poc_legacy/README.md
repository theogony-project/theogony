# MNLM PoC — Generation-1 (LEGACY)

> **Status: superseded.** This proof-of-concept ran under the **pre-MESH** substrate doctrine — single embedding per node, string-typed edges, the strict "no text in mesh" rule that prohibited any descriptive metadata, no frame vectors, no eager-linking discipline, no source-anchor entities. That doctrine has been replaced by the [MESH triplet](../../../MESH_SUBSTRATE.md): two-tier nodes with multiple per-node vectors, edges with optional semantic descriptors, frame-sensitive polarity, eager identity when Q-ID / description / structural signals are decisive. The new PoC continues under [`../poc_mesh/`](../poc_mesh/README.md).
>
> This directory is preserved as historical research evidence:
>
> - **`poc_run_report.md`** — the prose report of what the Gen-1 PoC achieved.
> - **`phase_a_loss.jsonl`**, **`phase_a_output.log`** — Phase-A training trace (graph projector pretraining).
> - **`phase_b_reward.jsonl`**, **`poc_reward_curve.png`** — Phase-B Micro-GRPO reward curve.
> - **`mini_dbb20_results.json`**, **`mini_musique_results.json`**, **`mini_monkey3_results.md`**, **`mini_monkey3_rating_sheet.md`** — the three-stage falsifier evaluations against the Gen-1 mesh.
> - **`corpus_200.json`** — the 200-article Wikipedia corpus used as input.
> - **`crawl_log.jsonl`** — append-only audit log of the crawler runs that fed the Gen-1 mesh.
> - **`poc_pipeline_trace.json`** — end-to-end execution trace.
>
> The `mesh_inputs/` directory (~500 MB of Kadmos-v1 JSON chunks) was deleted locally as part of the MESH pivot. It was the substrate data the Migration Plan §S6 explicitly discards as "structurally and qualitatively below what the doctrine expects". The chunks can be re-derived from `crawl_log.jsonl` if anyone needs to reproduce the Gen-1 PoC numbers; nothing here points at them as a current dependency.
>
> **Do not build against the artefacts in this directory.** They reflect a doctrine that no longer holds. They are kept for traceability of the Gen-1 falsifier results and for the empirical record of what worked / what did not under the old assumptions.

## What the Gen-1 PoC was trying to falsify

Three stages, in order of difficulty:

1. **DBB-20** — does the graph projector learn directional binding from labelled subgraphs?
2. **MuSiQue** — does the substrate support multi-hop question-answering above a flat RAG baseline?
3. **Monkey-3** — does the MNLM produce cross-domain emergent inference (knowledge that is not in any individual source paragraph but follows from the graph structure)?

See `poc_run_report.md` for the actual numbers.

## What carries forward to `poc_mesh/`

- The three-stage falsifier idea (DBB → MuSiQue → Monkey-3) is the right shape and survives.
- The corpus of 200 Wikipedia articles is a reasonable size for a fresh PoC; whether the same corpus is used or a new one is operator discretion.
- The Phase-A / Phase-B training shape (representation pretraining → Micro-GRPO with SA-alignment) survives in concept.

## What does NOT carry forward

- Single embedding per node. Replaced by multi-vector nodes (semantic + frame + structural + temporal + description).
- String-typed edges as the retrieval primitive. Replaced by quantitative edge tensor (weight + decay_tier + frame_consistency) with optional semantic descriptors.
- "No text in mesh" treated as "no text at all". Replaced by "no raw source text on the retrieval hot path; descriptions and descriptors are explicitly permitted as agent-readable metadata".
- The frozen `KnowledgeNode` / `Layer` / `NodeType` / `EpistemicStatus` schema. Replaced by `ChunkNode` / `ConsolidatedNode` with `consolidation_tier`, `is_candidate`, `is_anchor`, `is_source_anchor` discrete flags.

See [`../../MESH_SUBSTRATE.md`](../../../MESH_SUBSTRATE.md) for what the new substrate actually requires, and [`../../MESH_MIGRATION_PLAN.md`](../../../MESH_MIGRATION_PLAN.md) for how the codebase migrates.
