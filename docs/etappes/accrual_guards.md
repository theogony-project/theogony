# Accrual that follows a name (PHX-1121)

> **Abstract.** *Question.* PHX-1118 let a node's description accrue when a
> later passage mentions the entity and gained 4.9 points of exact match on the
> typed Constellation of the 2Wiki mesh; PHX-1120 then judged the mentions that
> moved node with accrual on, and they were net worse placed. Counted with the
> moves onto another node of the same name, which this ticket adds to the
> audit, 381 mentions left the right node and 135 reached it where two blind
> judges agree. Two guards were built from the two mechanisms PHX-1120 found
> possible: accrue only from a mention whose label is the node's name, and that
> plus an identity vector kept as the node was created. *Method.* The 2Wiki mesh
> rebuilt with each guard from the same 6,119 cached readings; against the build
> without accrual, PHX-1120's audit (two judges, each node shown as it was
> created) and PHX-1051's identity controls; the five answer arms on all four
> builds in one sitting, paired. *Result.* With both guards each of the 43,118
> link decisions is the one the build without accrual made — same node, same
> signal, same score — while 4,145 nodes carry accrued text (6,986 revisions,
> against PHX-1118's 12,154). With the first guard alone at least 714 mentions
> still move, and where the judges agree the arm is net worse, 312 losses against 118
> gains; it takes 129 of PHX-1118's 381 losses away and makes 60 of its own.
> What a name test cannot reach is left: the right node's drift was possible in
> 184 of the 312, and 42 went to *Paris* the Trojan prince, whose name a mention
> of the city bears. The answer sitting is outstanding: the DeepSeek balance
> ran out under it, and its runs were discarded (PHX-1123). *Limits.* One
> reading model and one answering model; the audit judges where mentions sit,
> not what accrued, and the first guard still accrues a homonym's text under the
> name they share; the name test is exact, so a mention under a variant name
> (*Louis XV of France* for *Louis XV*) adds nothing to its node; with the
> identity vector kept, the description a reader sees and the vector the linker
> matches are two different texts. *Decision.* For identity, the second guard
> makes accrual neutral and the first alone does not; which, if either, becomes
> the default (PHX-1119) waits on the answers.

**Status:** 2026-11-08, the identity half measured; the answer sitting waits
on the DeepSeek balance (PHX-1123). PHX-1121 stays in progress.
**Instrument:** `scripts/mesh_qa_mesh_ingest.py --accrue-descriptions` (guard 1
is its default; `--keep-identity-vector` adds guard 2; `--accrue-unnamed`
gives PHX-1118's arm) built `data/mesh-2wiki-named` and
`data/mesh-2wiki-named-kept`; `scripts/mesh_mention_audit.py collect --same-name`
and its blind batches; `scripts/mesh_identity_controls.py`. Reports: the
`IngestRunReport`s `01M6YF1GNT0B6H1PSA64BGMQJ5` (named) and
`01M6YF3ESHM039MNBPF876JWF2` (named-kept); the controls, the audit items,
both judges' verdicts and their summaries for the on and named arms, and
deepseek-chat's on named-kept's 400 control mentions (it has no moves), under
`data/run_reports/phx1121/`.
Code: the PHX-1121 change at commits `0d3794e` (named) and `91f1d0d`
(named-kept) equals this branch's except for two comments; their base,
`efb798e`, predates the PHX-1116 review fixes, PHX-1120 and PHX-1123, which
touch failure paths, the audit instrument and answer code only.

## The two guards

PHX-1120 counted where two mechanisms were possible. A node that holds a link
of another name takes that entity's text: 5,403 of PHX-1118's 12,154
revisions (44%) came from a mention whose label is not the node's name — links
PHX-1120's control found wrong in 45 of 54 decided cases — and in 180 of the
334 agreed losses the node a mention moved to held text from an earlier
mention of the same label that does not name it (England's sentences on the
*English Crown*, which drew 11 England mentions off England). And the right
node's own identity surface drifts as it accrues every context it is
mentioned in: in 85 of the 334, only the right node had accrued text when the
mention left it, a condition that also held in 65 of the 129 gains. In 5 the
new node held such text under its own name (*Universal*, *Prussia*); 64 fit
neither. Rhône is the plainest case of the first: its description came to
describe France.

**Guard 1 — accrue only from a name.** A re-mention's text is folded into the
node only if the mention's label is the node's name — the label the node was
created with, which the reader puts first in its tags (for a node a paragraph
concept created, that concept's first tag, which is seldom its label) — once
case, accents and a possessive 's are set aside and punctuation is read as a
space (so *St. Maurice's Abbey* names *St Maurice Abbey*, and *U.S.* does not
name *US*). The link itself is unchanged: the guard decides what the node learns,
not where the mention goes. Rhône carries the tag "France", so a France
mention still links onto it, as v2's linker decides; its text no longer
reaches Rhône's description. `accrue_unnamed=True` restores PHX-1118's arm.

**Guard 2 — keep the identity vector.** The linker's description signal
matches a mention against a node's `description_vector`; retrieval seeds on its
`semantic_vector`. With `revise_identity_vector=False` a revision re-embeds the
second and leaves the first as the node was created, so the description signal
never matches against accrued text, while retrieval and the rendered
description carry it. Two other paths still read the stored, accrued
description — the Q-ID plausibility check and the resolver's aliases — which on
a mesh with seeded Q-IDs could matter; on 2Wiki neither changed a decision.

## How it was measured

Four builds of the 2Wiki mesh from the same 6,119 cached readings: without
accrual (`off`, PHX-1118's), PHX-1118's accrual (`on`), guard 1 (`named`),
guards 1 and 2 (`named-kept`). The first two are PHX-1118's own meshes; the
last two were rebuilt for this ticket.

The audit is PHX-1120's, with one extension. PHX-1120 matched the two builds'
nodes by name, so a mention that moved between two nodes of one name — *Paris*
the city onto *Paris* the Trojan prince — did not count as moved; at least 115
such moves went unjudged on PHX-1118's arm. `collect --same-name` now matches a
node across builds by the mention that minted it, and judges these moves too.
On PHX-1118's arm, with both judges, the 115 add 47 losses and 6 gains (43 of
the losses *Paris*), so its losses counted the way this ticket counts them are
334 + 47 = **381**, its gains 129 + 6 = 135. Judges as in PHX-1120: deepseek-chat
through the project's provider, one call per judgment, and Claude Opus 5.5 in
blind batches of a Claude Code workflow — one candidate node at a time, never
both, each node shown with the description it was created with.

The identity controls are PHX-1051's (`scripts/mesh_identity_controls.py`),
and the answers are the five arms of `scripts/mesh_qa_constellation.py` on all
four builds in one sitting (deepseek-chat, 1,000 questions, seed 0), paired
question for question with the exact sign test (`scripts/mesh_qa_pair_runs.py`).

## What was measured — identity

### The replays

| | off | on (PHX-1118) | named | named-kept |
|---|---:|---:|---:|---:|
| revisions | 0 | 12,154 | 6,981 | 6,986 |
| re-mentions declined, label not the name | — | — | 6,621 | 6,453 |
| nodes revised | 0 | 6,508 | 4,150 | 4,145 |
| description, median / mean chars | 79 / 85.4 | 90 / 111.6 | 86 / 100.4 | 86 / 100.4 |
| descriptions of 200–500 chars | 236 | 2,729 | 1,581 | 1,577 |
| consolidated nodes | 35,906 | 35,901 | 35,914 | 35,906 |

The declined count is every re-mention the guard turned away, including those
whose text the description already held or that would have crossed the
500-character cap — so it is larger than the 5,403 revisions PHX-1118 made
from such mentions.

### Where the mentions went

| | on (PHX-1118) | named | named-kept |
|---|---:|---:|---:|
| mentions on a node of another name than without accrual | 962 | 623 | **0** |
| mentions on another node of the same name (at least) | 115 | 91 | **0** |
| entity nodes (off: 29,786) | 29,781 | 29,794 | 29,786 |
| gold names on two or more nodes (off: 10) | 11 | 11 | 10 |
| the hub Newport International Film Festival (off: 123) | 113 | 117 | 123 |
| University of Parma (off: 72) | 81 | 72 | 72 |

With the identity vector kept, accrual changes no link decision: each of the
43,118 is the one the build without accrual made — the same node, the same
signal, the same score, the 45 mentions on nodes a paragraph concept created
included. Meanwhile 4,145 nodes carry accrued text.

### The audit

Both judges, each node shown as it was created; κ = 0.94 on each arm. Of the
2,554 judgments per judge for PHX-1118's arm, 1,953 are PHX-1120's own on
identical units; the rest judge the 115 same-name moves and a control sample
redrawn without them (371 of its 400 units new). The named arm's 1,828 are
fresh, Claude's in blind batches under opaque ids. Where they agree:

| | on (PHX-1118) | named | named-kept |
|---|---:|---:|---:|
| moves by name: losses / gains | 334 / 129 | 267 / 114 | 0 / 0 |
| moves to a node of the same name: losses / gains | 47 / 6 | 45 / 4 | 0 / 0 |
| **all moves: losses / gains** | **381 / 135** | **312 / 118** | **0 / 0** |

Guard 1 nets 69 fewer losses: 129 of PHX-1118's 381 are gone, and 60 new ones
appear, 36 of them on mentions that did not move on PHX-1118's arm; of its 135
gains 61 remain and 57 are new. The arm stays net worse than the build without
accrual — 312 against 118 per mention; among the moves by name 142 against 80
per distinct move (p = 4 × 10⁻⁵) and 86 against 51 per label (p = 0.004), the
test to quote, since mentions of one label move together.

Where each loss was possible, counted as PHX-1120 counted it (a revision
reaches the linker at the compaction boundary after it is made):

| guard 1's losses | by name (267) | same name (45) |
|---|---:|---:|
| only the node the mention left had accrued text — drift possible | 184 | 0 |
| the new node held an earlier same-label mention's text | 5 | 44 |
| the new node held other accrued text | 37 | 0 |
| neither node had accrued text | 41 | 1 |

The drift row: *Spain* for the *Spanish Empire* 19 times, *Brazil* for *Rio
Grande do Norte* 11, *India* for *Gurgaon* 7, *England* for *Berkshire* 7,
*Japan* for *Sapporo* 6; the condition also holds in 45 of the 118 gains, so it
marks where drift was possible, not where it acted. The same-name row is the
homonym PHX-1120 found and a naming guard cannot stop: *Paris* the Trojan
prince, whose name a mention of the city bears, takes the city's text and 42
of its mentions. In 38 of the 41 where neither node had accrued, the build
never minted the right node, because the mention that minted it without
accrual had linked elsewhere (*Ottoman Empire* onto *Ottoman forces* 10,
*Paris* onto the *Parisian underworld* 4). Guard 2 removes every move, the
losses and the gains.

## What was measured — the answers

Not yet. The four answer runs of 2026-11-08 ran into an exhausted DeepSeek
balance, and the project's default fallback answered part of their calls with
another model under deepseek-chat's name; they were stopped and discarded
before any pairing, and the harness now answers with the model it names or not
at all (PHX-1123). The sitting is the one described above: four builds, five
arms, one model, paired.

## What this does not show

- **What accrued is not judged.** The judges see each node as it was created,
  and the audit judges where mentions sit, not what descriptions say. Guard 1
  still accrues from a wrong link that bears the node's name: in named-kept's
  control sample, 7 of the 57 re-mentions that revised a description sat on a
  node of another entity (deepseek-chat alone), and under both guards *Paris*
  the prince carries the city's sentences. That the 4,145 accrued descriptions
  describe their own entity is not shown.
- **One reading, one answering model.** The readings are deepseek-chat's, as in
  PHX-1118.
- **One corpus.** 2Wiki names its entities by their article titles; on an
  epithet-heavy text such as the shipped Theogony demo, guard 1 would decline
  more re-mentions that do name the right entity.
- **Mentions of one label move together**, so the per-mention counts overstate
  the evidence; the per-label count is the one to quote. The same-name moves are
  a lower bound: a node no link decision minted cannot be matched.
- **Exact names.** Guard 1 compares names, not entities: a mention that calls a
  node by a variant (*Louis XV of France* for *Louis XV*, 7 mentions in the
  guarded build; *Hugh of Italy* for *Hugh, King of Italy*) links as before and
  adds nothing, even where the node carries the variant among its tags.
- **Two texts per node.** With guard 2 the description a reader is shown has
  accrued; the vector the linker matches has not. Nothing on the node says so
  except the run row (`revise_identity_vector: false`); a consumer that assumes
  the description vector embeds the description reads the creation text.
- **The audit is two judges, on two protocols**, as in PHX-1120: deepseek-chat,
  the reader's own model, one call per judgment; Claude Opus 5.5 in blind
  batches of forty, old or new nodes only. 991 of PHX-1118's arm's Claude
  verdicts are PHX-1120's first pass, under ids that ended in the side letter.
  κ = 0.94 on both arms.

## How to re-run

```bash
# the two guarded arms (the off and on meshes are PHX-1118's)
.venv/bin/python scripts/mesh_qa_mesh_ingest.py --root data/mesh-2wiki-named --fresh --accrue-descriptions
.venv/bin/python scripts/mesh_qa_mesh_ingest.py --root data/mesh-2wiki-named-kept --fresh --accrue-descriptions --keep-identity-vector
# PHX-1118's arm, now that the guard is the default under --accrue-descriptions
# (into a root of its own: data/mesh-2wiki-on is the measured mesh)
.venv/bin/python scripts/mesh_qa_mesh_ingest.py --root data/mesh-2wiki-on-rebuilt --fresh --accrue-descriptions --accrue-unnamed
# the identity controls, per arm
.venv/bin/python scripts/mesh_identity_controls.py --root data/mesh-2wiki-named --json data/run_reports/phx1121/controls_named.json
.venv/bin/python scripts/mesh_identity_controls.py --root data/mesh-2wiki-off --against data/mesh-2wiki-named --dataset '' \
  --json data/run_reports/phx1121/controls_diff_named.json
# the audit, per arm against off
.venv/bin/python scripts/mesh_mention_audit.py collect --a data/mesh-2wiki-off --b data/mesh-2wiki-named --same-name \
  --out data/run_reports/phx1121/audit_items_named.jsonl
THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \
  .venv/bin/python scripts/mesh_mention_audit.py judge --items data/run_reports/phx1121/audit_items_named.jsonl \
  --out data/run_reports/phx1121/audit_judgments_deepseek_named.jsonl
.venv/bin/python scripts/mesh_mention_audit.py export-blind --items data/run_reports/phx1121/audit_items_named.jsonl \
  --out-dir <dir> --key data/run_reports/phx1121/blind_named_key.json --seed 1121
# the second judge answers each batch with [{unit_id, verdict, reason}]
.venv/bin/python scripts/mesh_mention_audit.py import-blind <dir>/answers/*.json --key data/run_reports/phx1121/blind_named_key.json \
  --judge "<who judged>" --out data/run_reports/phx1121/audit_judgments_claude_named.jsonl
.venv/bin/python scripts/mesh_mention_audit.py summarise --items data/run_reports/phx1121/audit_items_named.jsonl \
  --judgments data/run_reports/phx1121/audit_judgments_deepseek_named.jsonl \
  --second data/run_reports/phx1121/audit_judgments_claude_named.jsonl
```
