# Depth bands (PHX-0059 Phase 1)

Every `KnowledgeNode` carries `depth_band: int ∈ [0..5]`. The binary **Ephemera / Mneme** `layer` enum remains the coarse trust boundary; bands add a **six-step ladder** inside and across that boundary.

## Semantics

| Band | Layer (typical) | Meaning (short) |
|------|-----------------|-----------------|
| 0–2 | Ephemera | raw → settling → promotable |
| 3–5 | Mneme | freshly promoted → well-embedded → canonical |

## Derivation

`derive_depth_band` (`src/theogony/memory/depth_band.py`) combines:

- **Embeddedness** `0.6 * effective_connectivity + 0.4 * vitality`, where `effective_connectivity` boosts baseline connectivity with the mean of positive `pheromone_delta` on incident edges (W2), scaled by `Settings.depth_band.pheromone_bonus_weight` (default `0.5`).
- **Idle days** since `last_accessed` for cooling Mneme transitions.

## `DepthBandPhase`

- **Default-off** tick phase (`depth_band` in `enabled_phases`).
- **One band per tick** toward the derived target (`step_one_toward_target`).
- **Layer transitions follow band crossings**: Ephemera stepping to ≥3 calls `promote`; Mneme stepping to ≤2 calls `degrade`.
- Legacy MNEME rows with `depth_band < 3` are silently aligned to band **3** once before stepping so pre-W4 data does not block the ladder.

## Relationship to classic promote / degrade phases

The historical `promote` / `degrade_mneme` phases remain available and default-on. Operators may run **either** threshold-based promotion **or** band-driven promotion — running both is supported but redundant; pick one policy per deployment.

## Pre-W4 data

Nodes without `depth_band` deserialize as `0`. The first `DepthBandPhase` pass walks them toward their honest band; until then, filters on `depth_band` may look sparse on legacy corpora.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`MORPHEUS.md`](MORPHEUS.md).
