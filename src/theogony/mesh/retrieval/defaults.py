"""The shipped retrieval defaults, in one place.

They lived as literals at four call sites and a fifth in the Cockpit, which is
how PHX-1069 raised the answer budget from 30 to 50 everywhere except the
Cockpit — the demo surface kept serving 30 for a day while the documented
number was the one measured at 50. A constant cannot drift from itself.

Every value here is pinned by `tests/mesh/retrieval/test_retrieval_defaults.py`,
which exists because a mutation test found that changing `top_k` to 7,
`k_seeds` to 1, `mmr_lambda` to 0, `ppr_iters` to 1 or `name_anchors` to False
left all 1,696 tests green (PHX-1079). Numbers nothing asserts are numbers
nothing protects.
"""

from __future__ import annotations

# How many nodes a Constellation carries. Measured against the founding gold set
# on `data/mesh-founding` (47 questions, 5,002 nodes): recall runs 65% at 30 and
# 74% at 50, for a median 87.2 ms -> 90.4 ms. Three milliseconds for nine points
# (PHX-1069). The previous 30 was never justified by cost — nothing was measuring
# the trade at all until the gold set existed.
#
# Deliberately not higher. 100 reaches 85% for 15 ms, and 200 reaches 95%, so the
# ranking is largely right and what is tight is the budget. But a Constellation is
# read by a language model, and there is no measurement yet of whether more context
# completes an answer or dilutes it. That measurement, not the latency, is what
# gates going further.
DEFAULT_TOP_K = 50

# Seeds drawn by diversified injection (MMR over the ANN candidates, with a
# guaranteed seat per weight class since PHX-1091).
#
# Set to 1 on the consolidated founding mesh, by the same tune/test protocol
# PHX-1091 used to set 5 — choose k on one half, report on the other, both
# directions, three shuffles — because the protocol's answer changed when the
# substrate did. On the *unconsolidated* mesh k=1 lost held-out in 3 of 6 splits
# (−0.043 / −2 full, −0.021 / −2, −0.032 / −2), which is why 5 was right then.
# After Oneiros consolidation merged 68 entity candidates into their entities
# (PHX-1097), one seed *is* the entity rather than one of its six fragments, and
# k=1 is selected on the tune half in 6 of 6 splits and wins the held-out half
# in 5 of 6, never losing recall:
#
#     held-out Δ vs k=5     +0.092/+1  +0.087/0  +0.071/0  +0.109/+1  0.000/−1  +0.159/+2
#
# Whole set, split by question kind, consolidated mesh: genealogical 0.747 → 0.880,
# narrative 0.861 → 0.861. Answer arm (deepseek-chat, three runs): 53% → 59%,
# graph over prior knowledge +2 → +11 (PHX-1099).
#
# Re-measured under the corrected gold set (PHX-1098): the closed-book arm
# stands at 86%, the constellation at 75%, so the margin over prior knowledge
# is −11 on this corpus — the model knows Hesiod by heart and the old gold had
# under-scored it. The decision above rests on the retrieval tune/test split,
# which the correction does not touch; the answer-arm line is kept as measured.
#
# What this gives up, said plainly: at k=1 weight-class stratification has no
# seats to allocate and is inert — the doctrine's multi-scale guarantee does not
# earn its keep on this corpus. The mechanism stays built for meshes and callers
# that seed wider; the default follows the measurement.
DEFAULT_K_SEEDS = 1

# ANN candidates the seed selector chooses from.
DEFAULT_ANN_LIMIT = 64

# MMR relevance/diversity trade-off; 1.0 is pure relevance, 0.0 pure diversity.
DEFAULT_MMR_LAMBDA = 0.6

# Personalised-PageRank restart probability and iteration count. PPR is the
# default operator on the strength of PHX-1034.
DEFAULT_PPR_ALPHA = 0.15
DEFAULT_PPR_ITERS = 12

# Hops for the non-PPR operators.
DEFAULT_HOPS = 3
DEFAULT_DAMPING = 0.5

# Look up the entities a question names outright and seed on them. Worth +17
# points of recall on the founding gold set for 8 ms (PHX-1068), which is why it
# is on rather than a lever.
DEFAULT_NAME_ANCHORS = True

# Scale edges whose relation resolves to a Wikidata property. Off: see
# `theogony.mesh.typed_edges` for the curve and for why it is not on yet
# (PHX-1070).
DEFAULT_TYPED_EDGE_BOOST = 1.0
