# Nous — pointer

**Status:** Pointer. **No standalone Nous brief exists yet — by design.**
**Date:** 2026-05-10 (updated)

This file used to be a v1 → v2 redirect. The "v2" framing was misleading: there is no meaningful Nous v1, because what was originally called Nous v1 has been re-classified as **Kadmos v1** (a translation layer, not a synthesis layer). See [`kadmos_v2_brief.md`](kadmos_v2_brief.md) for the current Kadmos architecture.

## What Nous now is, in one sentence

Nous is the **first concrete role** of a Mesh-Native Language Model (MNLM) — a language model whose primary input and primary output are vector subgraphs of the Chronik, with text retained only at the outermost ingress (Kadmos).

## Where the architecture lives

The architectural primitive that Nous instantiates — the MNLM as a class — is fully specified in:

→ [`mesh_native_lm_brief.md`](mesh_native_lm_brief.md) — **THE binding architecture brief**, filed by Hesiod 2026-05-10. Locks the Llama-3-8B + Graph-KV + Latent Flow Matching + Substrate-Resonant Recurrence + Graph-GRPO architecture, the binding `MeshInput` / `MeshDelta` Pydantic schemas, the three-stage falsifier, and the 12-week Talos roadmap.

Supporting documents:

→ [`mesh_native_lm_research_brief.md`](mesh_native_lm_research_brief.md) — the *question* the binding brief answers. Repository-internal research order with reading discipline.
→ [`../../notes/deep_research/run12_brief.md`](../../notes/deep_research/run12_brief.md) — the same MNLM question for external research agents (Gemini Deep Research, DeepSeek).
→ [`../research/mnlm/`](../research/mnlm/) — the five Round-1 research artifacts (opus, codex, gemini, deepresearch, DeepSeek) that fed Hesiod's synthesis.

## Why no Nous brief exists yet

By construction. Nous specialises a primitive that is itself still being implemented. The order is:

1. **Architecture binding brief.** ✅ Filed: [`mesh_native_lm_brief.md`](mesh_native_lm_brief.md), 2026-05-10.
2. **Talos implementation of v1.** ⏳ In progress per `mesh_native_lm_brief.md` §8 (12-week sprint).
3. **Stage-1, Stage-2, Stage-3 falsifier results.** ⏳ Weeks 6, 10, 12 of the Talos roadmap.
4. **Nous role brief.** ⏳ Filed *after* (2) and (3) succeed. The Nous brief will specify the role-specific configuration of the MNLM primitive — control loop, write permissions on the Chronik, trigger conditions, role-specific `aux` keys, deployment topology — on top of the now-empirically-grounded MNLM primitive.

Until step 4, this file is a pointer, not a brief.

## What was here before

The original `nous_v2_brief.md` content (pre-2026-05-10) has been moved to [`kadmos_v2_brief.md`](kadmos_v2_brief.md), where it correctly belongs — Kadmos is the translation layer, not Nous.
