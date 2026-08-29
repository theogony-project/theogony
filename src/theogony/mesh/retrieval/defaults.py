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
# Narrowed 8 -> 5 on the founding gold set, and the value is the tune/test split
# rather than the sweep. The sweep alone says 1:
#
#     k_seeds     1     2     3     5     8    16    32
#     recall     84%   82%   78%   80%   77%   71%   64%
#     full       36    35    36    38    37    33    27
#
# But tuned on one half and reported on the other, k=1 loses: -2 points of recall
# and **-9 points of questions answered in full** on held-out data. k=5 never
# loses — +6 recall and +4 full in one direction, level with 8 in the other. The
# aggregate best was overfitted to half the set, which is the failure this repo
# has walked into twice before (PHX-1090).
#
# Why this is not simply "narrower is better": Spreading Activation's advantage
# does live at narrow seeding — that is the seeding ceiling, confirmed end-to-end
# at +5.0 exact match on 2WikiMultihopQA at S=2 (PHX-1089) — but at k=1 the class
# seats have nothing to allocate, so stratification goes inert and the guarantee
# the doctrine asks for disappears. 5 is where both hold.
DEFAULT_K_SEEDS = 5

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
