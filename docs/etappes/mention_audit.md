# Where the moved mentions went (PHX-1120)

> **Abstract.** *Question.* PHX-1118 let a node's description accrue when a
> later passage mentions the entity, and measured +4.9 points of exact match
> on the typed Constellation of the 2Wiki mesh. Its identity controls were
> counts — entity nodes within 0.02%, the largest hubs shrinking — and 961 of
> the 43,118 mentions had landed on a node of another name than without
> accrual. No count can say whether such a move was right. *Method.* The two
> builds' link-decision audit rows, joined on the mention itself (paragraph,
> the label the reader extracted, its occurrence): 962 mentions moved to a node
> of another name. Two judges — deepseek-chat through the project's provider,
> and Claude Opus 5.5 in blind batches of a Claude Code workflow — saw the
> paragraph, the mention and one candidate node at a time, never both and
> without being told the build, and answered *same*, *different* or
> *unclear*; each node was shown with the description it was created with.
> 400 mentions that did not move are the base rate. *Result.* The judges agree
> on 97% of the 2,324 judgments (Cohen's κ = 0.95). Where they agree on what a
> move did, 334 moves took a mention off the right node and 129 onto it;
> counted once per distinct move, 191 losses against 99 gains (p = 7 × 10⁻⁸),
> once per label 131 against 77 (p = 2 × 10⁻⁴). The losses are the
> description signal's, and the direction is in the names: 304 of the 334 left
> a node bearing the mention's name — *Spain* for Madrid or the Spanish
> Empire, *England* for the English Crown. *The first pass was wrong in one
> place.* It showed each node with its final description, and on the new side
> that text had accrued the mention's own note word for word in 667 of 962
> cases;
> deepseek-chat followed the words, and its 188 judgments of *same* that
> Claude called *different* fell to 29 when the nodes were shown as created.
> *Limits.* Two judges, one of them the reader's model, on different
> protocols; mentions of one label move together; 115 more mentions moved to a
> node of the same name and are not judged, 43 of them *Paris* the city on
> *Paris* the Trojan prince. *Consequence.* The answer gain stands as
> measured, on a mesh whose identity was net worse by 205 mentions where both
> judges agree. Two guards follow, to be measured as two arms of PHX-1121;
> the linker's own error is PHX-1122.

**Status:** 2026-11-07, measured twice — the first pass on final
descriptions, the second, reported here, on the descriptions the nodes were
created with; PHX-1120 closed, PHX-1121 and PHX-1122 filed.
**Instrument:** `scripts/mesh_mention_audit.py` — `collect` over
`data/mesh-2wiki-off` and `data/mesh-2wiki-on` (the PHX-1118 builds), `judge`
with deepseek-chat, `export-blind` / `import-blind` for the second judge,
`summarise` for both and their agreement. Under `data/run_reports/phx1120/`:
`items_v2.jsonl`, `judgments_deepseek_v2.jsonl`, `judgments_claude_v2.jsonl`,
`summary_v2.json`; the first pass's files without the suffix. Cost:
deepseek-chat €0.13 to €0.14 per pass of 2,324 judgments (two to three minutes, every
one answered by deepseek-chat, no fallback); the second judge's agents used
about seven million tokens of a Claude Code session over both passes.

## Why a count could not answer it

The identity controls PHX-1118 ran are counts: entity nodes, gold names on one
or several nodes, the top-20 in-degree. A mention that leaves one existing
node for another changes none of them unless a great many move. It does change
the mention counts of the two labels, and that is what the mention diff of
`scripts/mesh_identity_controls.py --against` read: 961 mentions changed node,
768 labels changed count. It joined the builds on labels per chunk, so it
could say how many moved and where to — not whether the new node is the entity
the paragraph talks about. That is a judgment about reference, and the
instrument for it has to judge.

## The instrument

**The join.** Every mention the reader links writes one
`mesh_ingest_link_decision` audit row: the label it extracted, the node it
chose, the signal and score, the paragraph. Both builds replayed the same 6,119
readings, so each mention is in both logs under the same paragraph and label;
a label that occurs twice in one paragraph is told apart by its occurrence.
43,118 mentions in both builds, none in one only. A mention *moved* when the
label its node was created with — the first tag, which accrual never changes
— differs between the builds: 962. The label diff counted 961; the one it
missed is a swap inside paragraph 4089, where *Egyptian language* went from
*Hindi* to *Arabic* and *Hurrian language* from *Aymara* to *Hindi*, wrong in
both builds and invisible to a diff of label counts.

A name is not a node, though, and this join shares the label diff's blind
spot. Matched across builds by the link decision that minted each node, at
least 115 more mentions changed node without changing name; they are counted
here as not moved, and they are not judged. 46 of them are *Paris*, and 43 of
those sat without accrual on the node minted at paragraph 511 as *Capital city
of France* and with it on the node minted at paragraph 173 as *Mythological
prince of Troy, lover of Helen*, which had taken the city's text (below); the
other 3 went to a second city node minted at paragraph 4160.

**The judgment.** One candidate at a time. The judge sees the Wikipedia
paragraph with its article title, the mention with the reader's note on it,
and one node as `name — description`, and answers whether the node denotes the
entity the mention refers to in that paragraph: *same* (another name, spelling
or form of the name counts), *different* (another entity, or a broader,
narrower or related one — a country for its empire, a city for its region, an
award for one of its ceremonies), or *unclear*. The prompt names no build and
no arm. The node is shown with the description it was created with: accrual
keeps the standing text as a byte-identical prefix, so that is the stored
description cut where the first revision began (the revision audit rows record
its length). For a moved mention the old node and the new node are judged
separately, and the two verdicts give an outcome:

| old node | new node | outcome |
|---|---|---|
| different | same | better |
| same | different | worse |
| same | same | both same — two nodes of one entity |
| different | different | both different — two wrong nodes |

**Two judges, two protocols.** deepseek-chat answered through the project's
provider at temperature 0, one judgment per call. Claude Opus 5.5 answered in
batches of forty units, one agent per batch, every batch holding only old or
only new candidates so that no agent saw both nodes of one mention: sixty
batches in the first pass (fifty-eight of forty, two of two), and for the
second pass's new nodes twenty-five more under opaque unit ids. `export-blind`
writes such batches with a key file, and any judge — another model, a person
— can answer them and come back in with `import-blind`. Neither judge saw the
other's answers.

**The base rate.** 400 of the 42,156 mentions whose node kept its name,
sampled with seed 0, judged on their one node (2 of the 400 are among the
same-name moves above).

## The first pass, and what was wrong with it

The first pass showed each node with its final description. For an old node
that is the description it was created with — the build without accrual
revises nothing. For a new node it was the accrued text: 933 of the 962 had
been revised, and in 667 of them the accrued text contained the mention's own
note word for word — in 633 because accrual had folded it in when the mention
linked, in 34 from an earlier mention worded the same.
The judge was being asked whether a node that repeats the mention's words is
the mention's entity. The judges agreed at κ = 0.82 overall, but 0.94 on old
nodes and 0.62 on new ones; of their 211 disagreements, 188 were
deepseek-chat calling *same* what Claude called *different*, 165 of those on
a new node. Where both agreed, the first pass already found the moves net
worse: 252 against 139.

The claim check of this write-up found the cause, and the second pass removed
it by showing each node as created. deepseek-chat's verdicts on old nodes and
on the control, whose text did not change, came back the same 952 times in
962 and 395 in 400 — a test–retest spread of about one percent. On the new
nodes 190 of its verdicts changed, 187 from *same* to *different* and 3 the
other way. Claude changed 19 of its 962 new-node verdicts. The disagreement had been
the instrument, not the judges.

## Results

### The judges agree

| | judgments | observed agreement | Cohen's κ |
|---|---|---|---|
| all | 2,324 | 97.3% | 0.95 |
| old nodes of moved mentions | 962 | 97.1% | 0.94 |
| new nodes of moved mentions | 962 | 97.2% | 0.93 |
| control mentions | 400 | 98.0% | 0.92 |

The 63 disagreements run both ways: 29 judgments deepseek-chat calls *same*
and Claude *different*, 24 the reverse, 10 that one of them calls *unclear*.

### The moves were net worse

| outcome | deepseek-chat | Claude | both judges agree |
|---|---|---|---|
| better | 137 | 141 | 129 |
| worse | 352 | 346 | 334 |
| both same | 102 | 99 | 93 |
| both different | 370 | 365 | 351 |
| unclear | 1 | 11 | 1 |

The judges agree on the outcome of 908 of the 962 moves. Of the old
placements 454 (deepseek-chat) and 451 (Claude) were right, of the new ones
239 and 242. More than a third of the moves went between two wrong nodes:
those mentions were misplaced before accrual touched them.

The moves are not independent: one label moves between the same two nodes
again and again — *Spain* to the Spanish Empire twelve times where the judges
agree, *World War II* to the Battle of France twelve, *England* to the
English Crown eleven, *Ottoman Empire* to *Ottoman forces* eleven, *Spain* to
Madrid eight. The sign test therefore stands at three grains:

| counted once per | better | worse | sign test |
|---|---|---|---|
| mention | 129 | 334 | p = 5 × 10⁻²² |
| distinct move (label, old node, new node) | 99 | 191 | p = 7 × 10⁻⁸ |
| label, by the sign of its net | 77 | 131 | p = 2 × 10⁻⁴ |

The per-label test is the conservative one, and it holds.

### By the signal that placed the new node

Agreed outcomes:

| new placement | better | worse | both same | both different |
|---|---|---|---|---|
| description signal | 66 | 321 | 73 | 301 |
| tag signal | 13 | 13 | 16 | 50 |
| a new node (emergent) | 50 | 0 | 4 | 0 |

The losses are the description signal's: it placed 808 of the 962 moves, 321
of the 334 agreed losses and 66 of the 129 gains. The linker matches the
mention's description against each candidate's, and accrual had changed the
candidates'. Where the linker minted a node instead of linking, the old link
had been wrong in 50 of the 54 moves the judges agree on; in the other 4 the
new node duplicates an entity the old link had right (*Warner Brothers*
beside *Warner Bros.*, *Paramount* beside *Paramount Pictures*, *US* beside
*U.S.*, *Ottoman Sultanate* beside *Ottoman Empire*). A minted node carries the
mention's label and its own note, so a judge can hardly call it anything else;
what the row shows is that the old link was wrong.

### By whether a node bears the mention's name

Agreed outcomes; *named* means the mention's label equals the node's name
after case, accents and punctuation are set aside:

| old node | new node | better | worse | both same | both different |
|---|---|---|---|---|---|
| named | other name | 1 | **304** | 49 | 10 |
| other name | named | **112** | 6 | 40 | 4 |
| other name | other name | 15 | 24 | 2 | 337 |
| named | named | 1 | 0 | 2 | 0 |

A mention that left a node bearing its name for one that does not lost 304
times in 305 decided cases; one that went the other way gained 112 times in
118. The control says the same about links in general, once the mentions that
minted their own node are set apart:

| control mention | right | wrong | judges disagree |
|---|---|---|---|
| minted its own node | 261 | 0 | 0 |
| linked to an existing node it names | 71 | 6 | 2 |
| linked to an existing node of another name | 9 | 45 | 6 |

The judges see the node's name beside the mention, so name equality and their
verdict are not independent evidence; on this mesh it is a strong signal, not
an identity test. All six wrong named links are same-name confusions —
*Santiago* the Chilean capital on Santiago de Cuba, *Paderborn* the city on the
Prince-Bishopric, *House of Commons* of England before 1707 on the United Kingdom's. And 60 of
the 400 control mentions — 15% — sit on a node that does not bear their name.
Every one of them is a re-mention, a link to a node that already existed: 60
of the 139 re-mentions in the sample, 43%, and re-mentions are the only links
accrual draws on. Of PHX-1118's 12,154 revisions, 5,403 (44%) came from a
mention whose label is not the node's name, on 3,056 nodes — the same share,
counted on the revision rows of the build with accrual.

## How the mentions moved

Two things can move a mention when descriptions accrue, and the case that
first looked like the second turned out to be the first.

**The right node drifts.** *Rhône* is a department; on both builds its node
carries the tags `Rhône, department, France, place`, and the tag `France`
names a France mention, so the PHX-1051 guard lets the description match
through. Without accrual four France mentions landed on it this way
(paragraphs 514, 628, 4533, 5264). With accrual the first came at paragraph
509, before Rhône had taken any text. What had changed was *France*: its node,
created as *Country where Wallop was detained during the Napoleonic Wars*, had
two accrued sentences in the store by then (*Kingdom of which Joan II was
queen consort*, from paragraph 282, and *A country in Europe*, from 341),
written at the compaction boundary of paragraph 400. Without accrual the
mention went to France at 0.8467 against Rhône's 0.842; with it, Rhône scored
the same 0.842 and France fell to 0.824 — the losing scores recomputed with the
linker's formula, since the audit row records only the winner. The mention at 515 went the same way (France 0.862 without accrual,
0.828 with it, Rhône 0.836 on both). France's losing scores come from its text
as it stood at that paragraph, re-embedded with the reader's embedder; its
stored vector is its final text's, and would give 0.807 and 0.820.

Rhône then took France's text, four times, and its description came to
describe France:

> Rhône — Department in France where Lyon is located. The country in which
> the Allier department and Montluçon are located. The country where the
> station is located. Country in Europe, where Lyon is located. Country where
> Lyon is located and where the Guillots lived and worked.

But once that text was in the store — at the boundary before paragraph 601 —
it drew no France mention the build without accrual had not already sent
there. After it, the France mentions of paragraphs 628 and 5264 sit on Rhône on both
builds, with lower scores on the accrual build (1.0881 → 1.0283, 0.9202 →
0.8453), and the one at 4533 left Rhône for France. Rhône is a polluted
identity surface, not an attractor.

**A node that took the wrong entity's text attracts it — under the same
name.** *Paris* the Trojan prince was minted at paragraph 173. Mentions of
the city at paragraphs 293, 329 and 486 landed on him on both builds, by the
description signal; with accrual his description took their text (*The
capital city of France, birthplace of Claude Weisz*), and at paragraph 511 the
city mention that minted the city's own node on the build without accrual
linked to the prince instead, at 0.7655. Until paragraph 4160, where the build
minted a second city node (*City in France where Juan Carlos has performed*;
it drew 4 of the city's mentions), the city had no node of its own. The prince
ends with 53 of its mentions: the 43 that sat on the city's node without
accrual, 8 that sat on him on both builds, 2 from other nodes. The two nodes
share a name, so the join above does not count these moves, and a guard that
accrues only from a mention naming its node would not have stopped them —
*Paris* names the prince too.

Across the 334 agreed losses, the new node already held, at the moment of the
decision, text written by an earlier mention with the same label in 185; it
held other accrued text in 43; in 85 only the right node had accrued
(drift); in 21 neither had — matching the right node by name would count two
more as drift, but for those two *Paris* mentions the only node of that name
with accrued text is the prince. That is where each mechanism was possible, not
a measurement of which one acted: the drift condition holds in 65 of the 129
gains as well.

**A hub grew.** PHX-1118 reported that no generic hub grew. One did:
*University of Parma*, 72 mentions without accrual, 71 of them under another
name than its own (63 other labels, 69 placed by the tag signal), rose to 81. Its description became *University where X studied. University where Y
was a professor …*, its description-signal links rose from 2 to 13, and the 11
moves onto it are all wrong where the judges agree (6 worse, 5 between two
wrong nodes). *Queens* grew from 21 to 35 the same way, its *New York City*
mentions from 18 to 32.

## What it means

**For PHX-1118.** The answer measurement is untouched: 48.0% → 52.9% on the
typed Constellation is what the two meshes answered. What changes is the
identity statement: the 962 moves were not neutral. Where both judges agree,
205 more mentions left the right node than reached it — 0.48% of the 43,118 —
and the per-label count, 131 labels net worse against 77, says it is a
direction, not a few loud labels.

**For the default.** PHX-1119 would switch accrual on for the shipped reader
as built. Not before a guard, and the mechanisms ask for two. Accruing only
from a mention that names the node keeps a node from taking a differently
named entity's text — the precondition in 180 of the 185 losses where the new
node held an earlier same-label mention's text; in the other 5 (*Universal*,
*Prussia*) that label is the node's own name. It does not stop the right
node's drift, nor a same-name attractor: *Paris*, or those 5. Leaving the
identity vector as the node was created — the linker matches on it, retrieval
seeds on the semantic vector — would stop both, because the linker would never
see accrued text. PHX-1121 measures two guarded arms — the first guard
alone, and both together — against the build without accrual and PHX-1118's:
the 2Wiki mesh rebuilt, this audit, and the five answer arms in one sitting.

**For the linker.** 43% of the control's re-mentions sit on a node that does
not bear their name and are wrong in 45 of the 54 decided cases. They come in
three shapes the PHX-1051 v2 guard lets through: a tag that names a related
entity (an author on his book, a city on its borough), a category or title
noun inside the label (*film festival* inside *Seattle International Film
Festival*, which is how *Newport International Film Festival* came to hold 123
mentions; *King of England* between Richard I and Henry VIII), and siblings
whose names differ in a numeral or a year. PHX-1122.

## Limits

- **Two judges, one of them the reader's model, on two protocols.**
  deepseek-chat read the corpus in August and judges it here, one call per
  judgment; Claude judged in batches of forty, all old or all new nodes, the
  first pass's ids ending in the side letter (the second pass's new nodes
  under opaque ids). After the correction they agree at κ = 0.95, and the
  main result holds under each judge alone (137 against 352, 141 against 346);
  the tables by signal and by name are drawn on the outcomes both agree on.
- **The first pass's flaw** sat on the new side only and pulled toward
  *same* there, so toward *better*; correcting it strengthened the finding,
  and both passes are reported. A correction that strengthens a result should
  be read with that in mind; the tell here is that one judge's verdicts moved
  (190, 187 of them from *same* to *different*) and the other's barely did
  (19).
- **A judgment of reference** rests on a paragraph and a description of a
  sentence or two; a node whose first description was itself wrong can be
  judged *same* for the wrong entity's name.
- **Mentions of one label move together.** Per-mention p-values overstate the
  evidence; the per-label test is the one to quote.
- **Same-name moves are not judged.** At least 115, about a tenth of the
  moves; the *Paris* case says they include the attractor this audit set out
  to find.
- **The base rate is a sample.** 400 of 42,156; the 15% of differently named
  links is an estimate with a margin of about three and a half points either
  way.
- **One corpus.** 2WikiMultihopQA's passages are first paragraphs of
  Wikipedia articles; a corpus that names its entities by epithets — Hesiod's
  — would put more right links under *another name*.

## How to re-run

```bash
.venv/bin/python scripts/mesh_mention_audit.py collect --a data/mesh-2wiki-off \
    --b data/mesh-2wiki-on --out data/run_reports/phx1120/items_v2.jsonl
THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \
    .venv/bin/python scripts/mesh_mention_audit.py judge \
    --items data/run_reports/phx1120/items_v2.jsonl \
    --out data/run_reports/phx1120/judgments_deepseek_v2.jsonl
.venv/bin/python scripts/mesh_mention_audit.py export-blind \
    --items data/run_reports/phx1120/items_v2.jsonl \
    --out-dir data/run_reports/phx1120/blind --key data/run_reports/phx1120/blind_key.json
# a second judge answers each batch with [{unit_id, verdict, reason}, ...]
.venv/bin/python scripts/mesh_mention_audit.py import-blind data/run_reports/phx1120/answers/*.json \
    --key data/run_reports/phx1120/blind_key.json --judge "<who judged>" \
    --out data/run_reports/phx1120/judgments_second.jsonl
.venv/bin/python scripts/mesh_mention_audit.py summarise \
    --items data/run_reports/phx1120/items_v2.jsonl \
    --judgments data/run_reports/phx1120/judgments_deepseek_v2.jsonl \
    --second data/run_reports/phx1120/judgments_second.jsonl
```

The two meshes are rebuilt from the cached readings by the commands in
[`description_accrual.md`](description_accrual.md) (two replays of about 150
minutes on a quiet machine, no key). The first pass's items came from the
same `collect` before it cut descriptions to their creation, so they are not
reproduced by this code; its files are kept under the same directory.
