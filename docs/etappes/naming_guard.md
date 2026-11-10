# A link only onto a node the mention names (PHX-1122)

> **Abstract.** *Question.* PHX-1120 judged 400 random links of the 2Wiki
> mesh: 60 sat on an existing node that does not bear the mention's name, and
> where two blind judges agree they were wrong 45 times in 54. All of them
> passed the PHX-1051 v2 guard, which admits a link when a tag the mention
> shares with the node token-overlaps the label, or when the resolver remembers
> the label for the node. *Method.* A names guard, built as a switch beside v2:
> a description or tag link is admitted only onto a node whose name — the label
> it was created with — is the mention's label once case, Latin, Greek and
> Cyrillic diacritics, abbreviation marks and apostrophes are set aside, or onto
> one the reader tied to the mention from both sides; never onto a
> paragraph-concept node. The rule took three passes against PHX-1120's judged
> links, each reviewed. Then the bundled Hesiod demo and the 2Wiki mesh were
> rebuilt from the same cached readings under v2, `names` and `names_entities`
> (the guard for entity mentions only), and measured with PHX-1051's identity
> controls and PHX-1120's audit: a seeded sample of 2,000 of the 6,249 mentions
> that moved to a node of another name, all 351 that moved to another node of
> the same name, and a fresh base rate of 400 links. *Result.* Of 400 random
> links under names, 2 sit on an existing node of another name, both right;
> under v2 it was 60, 51 of them wrong to the same judge. Of the 2,000 sampled
> moves, 1,607 left a wrong node for the right one and 9 went the other way
> (per label 1,340 against 8). The cost is fragmentation: 327 were right on both
> sides, so the entity now has a second node — about 1,000 of the 6,249 (938 to
> 1,105 at 95%) — and so are 314 of the 351 same-name moves; entity nodes grew
> by 20% (29,786 → 35,770), gold names on two or more nodes 10 → 30, on none
> 121 → 82. A link onto a node that bears the name is wrong as often as before
> (8 of 102, v2 7 of 79), always a homonym, and a node of one name minted for
> another entity still draws mentions — Australia's national cricket team six
> of the country's in the sample. On the Hesiod demo, where names are epithets,
> the two judges agree on 28 moves better, none worse, 15 fragmented
> (κ = 0.78). *Limits.* On 2Wiki one judge so far, Claude Opus 5.5 —
> deepseek-chat waits on its balance — and no answers yet; a sample; one
> reading model; the name test is exact, so every variant fragments
> (*Louis XV of France* beside *Louis XV*); paragraph-concept placements are
> counted, not judged. *Decision.* The default stays v2. The guard ships as a
> switch (`--naming-guard`); whether it replaces v2 waits on the answer sitting
> and on human review, since it changes the linker's identity rule (PHX-1051).

**Status:** 2026-11-10. Identity measured: on the demo with two judges, on the
2Wiki mesh with one. The second judge and the answer sitting wait on the
DeepSeek balance (PHX-1123). PHX-1122 stays in progress.
**Instrument:** `scripts/mesh_qa_mesh_ingest.py --naming-guard names` and
`--naming-guard names_entities` built `data/mesh-2wiki-names` and
`data/mesh-2wiki-names-entities`; v2 is PHX-1118's `data/mesh-2wiki-off`.
`scripts/mesh_mention_audit.py collect --same-name` and its blind batches;
`scripts/mesh_identity_controls.py`, which now also counts where the
paragraph concepts landed. Reports: the `IngestRunReport`s
`01M6Z034M29WFAD0TZRYHA0Z44` (names) and `01M6YZR1A0FQTPJZPF1RZJSGGM`
(names_entities); the controls, the audit items, the sample, the base-rate
items, Claude's verdicts and their summaries under `data/run_reports/phx1122/`,
the demo's as `demo_*` in the same directory.
Code: the builds ran at `a9d525b`, whose linker and resolver are this
branch's byte for byte; the reader, the replay and the ingest script differ by
PHX-1121's accrual switches, which are off in these builds.

## The rule, and how it got there

The PHX-1051 v2 guard admits an eager link onto a candidate when a tag the
mention shares with the candidate token-overlaps the mention's label, or when
the resolver already remembers the label for the candidate. PHX-1120's random
sample of the 2Wiki mesh found that door wide open: of the re-mentions placed
on a node of another name, the two judges call 45 of 54 wrong. Every one of
the 45 came through a shared tag. In 21 the tag is the label itself: a related
entity's name (*New York City* on *Queens*, *Jens Bjørneboe* on his novel), a
category the label names, a namesake carrying the label. In 22 it is a
category or title noun inside the label: *film festival* took *Seattle
International Film Festival* onto *Newport International Film Festival*,
*King of England* took *Richard I of England* onto *Henry VIII*, and the entity
type the reader adds as a tag took *Grammy Award* onto one of its categories
through "award". In 2 it is a sibling whose name differs in a numeral or a
year: *John I, Lord of Polanen* on *John II*, *The Bat* of 1926 on the play of
1920.

The names guard reads one thing: the candidate's name, the label it was
created with, which the reader puts first in its tags and no later link
changes. A mention is admitted if its label is that name once case, Latin,
Greek and Cyrillic diacritics, abbreviation marks and apostrophes are set
aside and a hyphen, dash or comma is read as a space (`U.S.` = `US`,
`México` = `Mexico`, `K.J. Apa` = `KJ Apa`). It is also admitted if the reader
tied the two together from both sides: the mention tagged with the node's
name, the node created with the mention's label among its tags, and the same
numerals (`Siam` onto `Thailand`, not `Edward III` onto `Edward II`). A
remembered label is not consulted. A paragraph-concept node is created without
its label among its tags, so its first tag is a topic ("film", "career"): it
bears no name, and no mention links onto it. A paragraph concept is itself
named like any mention. The guard touches the description and tag tiers; the
Q-ID path is unchanged.

It took three passes, each reviewed by four lenses with three skeptics per
finding:

1. **Variants.** The first rule also admitted a plural, a qualifier on a name
   specific enough on its own, and an acronym. The review reproduced wrong
   merges in each: `King James I of Scotland` onto `King James I` (James VI
   and I) — of the 41 qualifier links the rule would add on 2Wiki at a score
   that clears the linker, about 18 are namesakes; `Back in Black` onto `Back
   to Black`, `The Rolling Stones` onto `Rolling Stone`; `NY` onto `Neil
   Young`. On PHX-1120's judged sample the variants had kept 41 right links
   against 1 wrong, but that sample holds only links v2 made, so it cannot
   show what they admit that v2 refused. They went.
2. **The fold.** The second rule dropped a leading "the" and ran words
   together. The review found it admitting merges v2 had refused: `The
   Predator` (2018) onto `Predator` (1987) at 0.910, `The Iron Man` (1924)
   onto `Iron Man` (2008), `Golmaal` onto `Gol Maal`. On the judged sample
   the two fold steps kept no right link the stricter fold loses. They went.
3. **The rule above**, on the judged sample (PHX-1120's second pass, the links
   that minted their own node set apart). Of the control sample's 131 decided
   links, v2 kept 80 right and 51 wrong; the names rule refuses 45 of the 51
   and 7 of the 80 — *Charles Dickens* onto *Dickens*, *Louis XV of France*
   onto *Louis XV*, *Episcopal Church (USA)* onto *Episcopal Church*. Of the
   moved mentions' 1,744 decided links it refuses 1,177 of 1,198 wrong and 141
   of 546 right.

A refused link mints a node, so the rule's cost is fragmentation. The
substrate's identity doctrine is eager when the evidence is clear and emergent
when it is not: a candidate node can be merged later, while a wrong fusion is
"expensive to undo" ([`MESH_SUBSTRATE.md`](../MESH_SUBSTRATE.md), identity).
That is the trade the measurement weighs.

## How it was measured

**Builds.** Three builds of the 2Wiki mesh from the same 6,119 cached
readings, accrual off in all: v2 (PHX-1118's `off`), `names`, and
`names_entities`. The third exists because `names` changes two layers at
once: where entity mentions link, and where paragraph concepts land. Under v2,
1,360 of the 4,510 paragraph concepts share a paragraph-concept node with other
paragraphs and 2,070 sit on an entity's node. `names_entities` applies the
guard to entity mentions and leaves paragraph concepts under v2. Its entity
layer is `names'` unit for unit: the 6,249 moves by name are the same mentions
with the same nodes on both sides, and the same-name moves differ by one
(*Hyderabad*, 351 against 350).

**The audit** is PHX-1120's, with PHX-1121's extension that matches a node
across builds by the mention that minted it, so a move between two nodes of
one name counts too. There are too many moves to judge them all, so the items
are a sample: 2,000 of the 6,249 mentions that moved to a node of another name
(seed 1122), all 351 that moved to another node of the same name, and 400
mentions that did not move. Claude Opus 5.5 judged them in 128 blind batches of
a Claude Code workflow — one candidate node at a time, never both, each node
shown with the description it was created with. deepseek-chat, PHX-1120's
other judge, has not judged them: its balance ran out on 2026-11-08 (PHX-1123)
and is still out. The demo's moves had both judges, deepseek-chat before the
balance ran out.

**The base rate.** PHX-1120's base rate is 400 links of the v2 build. The
ticket asks for a fresh control sample of mentions that did not move; between
v2 and names those are the mentions both guards place alike, so their errors
say nothing about where the names build differs. The base rate here is
therefore 400 links of the names build drawn at random (seed 1122), each judged
on its node. For a like-for-like comparison, v2's base rate is PHX-1120's
sample re-read with the same single judge.

**Identity controls.** PHX-1051's (`scripts/mesh_identity_controls.py`):
entity count, in-degree, gold names, where the mentions moved against v2, and
now where each paragraph's concept landed — the target of the paragraph's
`summarised_as` edge, since a paragraph concept writes no link-decision row and
the audit cannot see it.

## On the Hesiod demo

The bundled demo is 95 paragraphs of Hesiod's Theogony, replayed from recorded
readings. It is the corpus where the names guard should cost most: Hesiod names
a god by epithet as often as by name. Under v2 the demo holds 723 consolidated
nodes, 539 of them entities; under names 752 and 569 (+5.6%). `names_entities`
is the same within one edge: 93 of the demo's 95 paragraph concepts carry no
tag but the reader's marker, and with no shared tag that names the label v2
admits such a link only by a remembered label. No name stands on two entity
nodes in any of the three builds.

53 mentions sit on a node of another name under names than under v2. Both
judges saw each mention with one of its two nodes at a time, blind to the
guard (Cohen's κ = 0.78 over 106 judgments; deepseek-chat and Claude Opus 5.5
in blind batches). Where they agree:

| | mentions |
|---|---:|
| v2's node wrong, names' node right | 28 |
| both right — the entity now has a second node | 15 |
| v2's node right, names' node wrong | 0 |
| judges disagree | 10 |

The 28: twelve mentions of *Ocean* that v2 put on the *boundless sea* (the
raging sea among the first things) and two on *sea*; *Iapetus* twice on "Son
of Iapetus"; three different unions — *marriage*, *marriage of Hephaestus and
Aglaea*, *union of Cytherea and Anchises* — on "embrace of Coeus"; *Crete* on
*Iasion*; *Hecatoncheires* on *Obriareus*; *depths of the sea* on "golden
house". The 15 are the epithet cost: *Athena* beside "bright-eyed daughter of
a mighty father", *Aphrodite* beside *Cytherea*, *Uranus* beside "starry
Heaven", *Olympian Zeus* beside *Zeus*, the *Muses* twice beside "ready-voiced
daughters of great Zeus", *Desire* beside *Himerus*.

## On the 2Wiki mesh — identity

| | v2 | names | names_entities |
|---|---:|---:|---:|
| consolidated nodes | 35,906 | 41,890 | 39,853 |
| entity nodes | 29,786 | 35,770 | 33,733 |
| mentioned nodes | 28,464 | 32,436 | 32,435 |
| mentioned from 2+ / 3+ passages | 5,725 / 2,347 | 5,002 / 1,805 | 5,002 / 1,805 |
| gold names on no node / one / 2+ | 121 / 705 / 10 | 82 / 724 / 30 | 82 / 725 / 29 |
| mentions on a node of another name than under v2 | — | 6,249 | 6,249 |
| mentions on another node of the same name | — | 351 | 350 |

The generic hubs come apart: *Newport International Film Festival* holds 123
mentions under v2 and 1 under names, *University of Parma* 72 and 1, *St
Antony's College, Oxford* 30 and 1, *BAFTA Award for Best Film* 26 and 1,
*Pennsylvania* 41 and 7, *Eton* 34 and 6. And names that had no node of their
own get one: counted over the nodes that bear the name, *Italy* goes from 0 to
47 mentions, *Germany* 0 → 46, *New York City* 0 → 51, *Canada* 10 → 48,
*London* 23 → 57, *United States* 80 → 121. Under v2 their mentions sat on a
town, a borough or a hub that carried the name as a tag. The cost is in the
same rows: about 6,000 more nodes, and 30 gold names on two or more nodes
against 10, where a mention of a name met its node below the linker's score and
minted a second one. Both run reports say `poor`, as PHX-1118's and
PHX-1121's did: their low-tier ratio is 0.75 under either guard against 0.66
under v2, above the report's threshold of 0.60.

### Where the mentions went

Claude Opus 5.5, one judge:

| of the judged items | moved by name (2,000 of 6,249) | moved within a name (351) |
|---|---:|---:|
| v2's node wrong, names' node right | 1,607 | 9 |
| v2's node right, names' node wrong | 9 | 25 |
| both right — the entity now has a second node | 327 | 314 |
| both wrong | 47 | 2 |
| unclear | 10 | 1 |

Per label, since mentions of one label tend to move together: of the 1,638
labels among the 2,000 sampled moves, 1,340 moved net better and 8 net worse
(sign test, p < 10⁻¹⁰⁰); among the same-name moves 5 against 16 (p = 0.027).
Of the 400 mentions that did not move, the judge calls 3 wrong on both builds.

**What got better.** 1,127 of the 1,607 now sit on a node they minted
themselves, where v2 had put them on another entity's; the rest linked onto a
node of their name. The most frequent in the sample: *United States* off
*Pennsylvania* (11), *Canada* off *Nova Scotia* (10), *New York City* off
*Queens* (9), *Italy* off *Rome* and off *Siderno* (6 each), *Germany* off the
*Rhineland* (6) and *Brandenburg* (5), *Library of Congress* off the *United
States National Film Registry* (5), *Academy of Motion Picture Arts and
Sciences* off the *Israeli Academy of Film and Television* (3). Over all 6,249
moves the sample puts the better ones at about 5,000 (4,931 to 5,111 at 95%).

**What fragmented.** The 327 are variants of a name the rule refuses, every
one a node the entity already had: a qualifier (*Louis XV of France* beside
*Louis XV*, *Constantine II of Greece* beside *Constantine II*), a full form
(*Denmark* beside *Kingdom of Denmark*), a spelling (*Sybilla* beside *Sibylla
of Burgundy*, *Hainaut* beside *Hainault*, *Muhammad bin Saud* beside *ibn
Saud*), a former name or another name (*Leningrad* beside *St. Petersburg*,
*Catherine II* beside *Catherine the Great*, *Dutch Republic* beside *United
Provinces*), a plural (*Academy Award* beside *Academy Awards*), a
disambiguator (*Casablanca (1942 film)* beside *Casablanca*). These are the
variants the first pass admitted and the review found joining different
entities too. Over all moves, about 1,000 (938 to 1,105 at 95%). The 314
same-name pairs are the same cost under one name: a mention met the entity's
node below the linker's score and minted another.

**What got worse.** By name, 9 of 2,000: namesakes (*Otto I* onto Otto I of
Pomerania, *Thomas* onto Thomas, Count of Perche, *Ameena Begum* onto a
Bangladeshi politician, *Prussia* onto the Baltic region, *Sicily* onto the
Aragonese kingdom where v2 had it on *Trinacria*), the art form onto a film
titled *Cinema* (2), and *León*, the Iberian kingdom, onto *Léon* in Brittany
(2) — the accent fold joining two places. Within a name, 25 of 351, the
homonym the guard cannot see: a node of the name minted for another entity
draws mentions of the one the name usually means — Australia's national
cricket team six mentions of the country, Scotland's two, the Cannes Film
Festival under the name *Cannes* two of the city's, *Paris* the Trojan prince
one; among the rest namesakes (*Margaret of Cleves*, *Margaret of Guelders*,
*Elizabeth Willoughby*) and a word in another sense (*soldier*, *films*,
*director*). PHX-1120 found the same shape in *Paris*; neither guard tells
homonyms apart.

### The base rate

| link, of 400 drawn at random (one judge) | v2 (PHX-1120's sample) | names (seed 1122) |
|---|---|---|
| minted its own node | 261 right | 296 right |
| linked to an existing node it names | 72 right, 7 wrong | 94 right, 8 wrong |
| linked to an existing node of another name | 9 right, 51 wrong | 2 right, 0 wrong |
| wrong in all | 58 | 8 |

*Named* is PHX-1120's test: the label equals the node's name after case,
accents and punctuation are set aside. With both judges, PHX-1120's v2 rows
read 71 / 6 (2 disagreements) and 9 / 45 (6). The two links of another name
under names are ties the reader made from both sides: *Anhalt-Bernburg* onto
*Principality of Anhalt-Bernburg*, *Nice Guys* onto *High Hopes*, a title of
the same film. The 8 wrong named links are homonyms, as v2's six were:
*Napoleon* the Tamil actor on the emperor, *Russia* of 1904 on modern Russia,
*Teplice* the town on its football club, *Dark River* of 1952 on the 2017
film, *Burgundy* the duchy on the county. Re-mentions — the links accrual
draws on — fall from 139 of 400 to 104.

### Paragraph concepts

| of 4,510 paragraph concepts | v2 | names | names_entities |
|---|---:|---:|---:|
| alone on a node of its own | 1,080 | 3,334 | 1,038 |
| on a paragraph-concept node shared with other paragraphs | 1,360 | 0 | 1,281 |
| on an entity node | 2,070 | 1,176 | 2,191 |

Under v2, 274 paragraph-concept nodes are shared, the largest by 99
paragraphs of 99 different articles — Luke Goss, Jackie Kong, Sophie Marceau —
on the node created for "an overview of Luke Goss's career".
Under names no mention links onto a paragraph-concept node, and a paragraph
concept lands on an entity node only when its label is the entity's name
(*Forbidden Ground* on the film). Where a paragraph concept lands is not judged
here.

## What was measured — the answers

Not yet. The answer sitting — the arms of `scripts/mesh_qa_constellation.py`
on v2, names and names_entities, deepseek-chat, 1,000 questions, one sitting,
paired with PHX-1121's builds — waits on the DeepSeek balance that stopped
PHX-1121's sitting (PHX-1123). It is the measurement that weighs about 5,000
corrected placements against about 1,000 mentions on a second node of
their entity.

## Against the acceptance

- *Agreed wrong placements on a differently named node below PHX-1120's 45 of
  400.* None of 400 by one judge. With 2 such links in the sample, the agreed
  count stays below 45 whatever the second judge says.
- *The wrong rate among named re-mentions no higher than its 6 of 77 decided.*
  8 of 102 by one judge, 7.84% against 7.79%; the same judge on v2's sample
  gives 7 of 79, 8.86%. Waits on the second judge.
- *Without fragmenting the entities that are linked correctly today.* Not met:
  about 1,000 moves by name and 314 within a name put a mention of an entity on
  a second node, and gold names on two or more nodes go from 10 to 30.
- *The answer arms against an unchanged baseline.* Outstanding.

## What this does not show

- **One judge on 2Wiki.** Claude Opus 5.5 judged the sample and both base
  rates; the two judges agreed at κ = 0.78 on the demo and at 0.95 on
  PHX-1120's 2Wiki items. The agreed counts wait on deepseek-chat.
- **A sample.** 2,000 of 6,249 moves by name; the counts over all moves carry
  the margins given. The base rates are 400 links each, from different draws on
  different builds.
- **No answers.** Whether the corrected placements gain more than the
  fragmentation costs is the answer sitting's question.
- **Paragraph concepts are counted, not judged.** That 99 careers on one node
  are wrong is a reading of the table, not a verdict.
- **Exact names.** Every variant of a name fragments, and the fragments wait
  for a consolidation pass that merges candidates; none was run on these
  builds.
- **Homonyms.** A node bearing the name is admitted whoever it is; within a
  name the guard lost 25 against 9 gains. The accent fold adds a few of its own
  (*León*, *Léon*).
- **One corpus, one reading model, a small demo.** The readings are
  deepseek-chat's; the demo has 53 moves. 2Wiki names its entities by their
  article titles, which suits a names guard; the demo, which does not, is the
  check in the other direction.
- **The demo's join is not shipped.** `collect` reads 2Wiki's passages, so the
  demo's moves were joined by a scratch script on the two builds' link-decision
  rows (paragraph, label, occurrence); its items and both judges' verdicts are
  under `data/run_reports/phx1122/demo_*`.

## How to re-run

```bash
# the two builds (v2 is PHX-1118's data/mesh-2wiki-off), about ten hours each on a busy machine
.venv/bin/python scripts/mesh_qa_mesh_ingest.py --root data/mesh-2wiki-names --fresh --naming-guard names
.venv/bin/python scripts/mesh_qa_mesh_ingest.py --root data/mesh-2wiki-names-entities --fresh --naming-guard names_entities
# the identity controls, paragraph-concept placement included, and where the mentions went against v2
.venv/bin/python scripts/mesh_identity_controls.py --root data/mesh-2wiki-names --json data/run_reports/phx1122/controls_names.json
.venv/bin/python scripts/mesh_identity_controls.py --root data/mesh-2wiki-off --against data/mesh-2wiki-names --dataset '' \
  --json data/run_reports/phx1122/controls_diff_names.json
# the audit items against v2, and the base rate: the build against itself, 400 links
.venv/bin/python scripts/mesh_mention_audit.py collect --a data/mesh-2wiki-off --b data/mesh-2wiki-names --same-name --seed 1122 \
  --out data/run_reports/phx1122/audit_items_names.jsonl
.venv/bin/python scripts/mesh_mention_audit.py collect --a data/mesh-2wiki-names --b data/mesh-2wiki-names --seed 1122 --control 400 \
  --out data/run_reports/phx1122/base_items_names.jsonl
# the sample: 2,000 of the moves by name, every other item kept
.venv/bin/python - <<'EOF'
import json, random
R = "data/run_reports/phx1122"
items = [json.loads(line) for line in open(f"{R}/audit_items_names.jsonl")]
moved = sorted(i["id"] for i in items if i["group"] == "moved")
keep = set(random.Random(1122).sample(moved, 2000))
with open(f"{R}/audit_items_names_sample.jsonl", "w") as out:
    for i in items:
        if i["group"] != "moved" or i["id"] in keep:
            out.write(json.dumps(i, ensure_ascii=False) + "\n")
EOF
# blind batches; the judge answers each with [{unit_id, verdict, reason}]
.venv/bin/python scripts/mesh_mention_audit.py export-blind --items data/run_reports/phx1122/audit_items_names_sample.jsonl \
  --out-dir <dir> --key data/run_reports/phx1122/blind_names_key.json --seed 1122
.venv/bin/python scripts/mesh_mention_audit.py import-blind <dir>/answers/*.json --key data/run_reports/phx1122/blind_names_key.json \
  --judge "<who judged>" --out data/run_reports/phx1122/audit_judgments_claude_names_sample.jsonl
.venv/bin/python scripts/mesh_mention_audit.py summarise --items data/run_reports/phx1122/audit_items_names_sample.jsonl \
  --judgments data/run_reports/phx1122/audit_judgments_claude_names_sample.jsonl
# the base rate the same way (export-blind --seed 1123, base_judgments_claude_names.jsonl);
# the second judge, once its balance allows, on the same items:
THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \
  .venv/bin/python scripts/mesh_mention_audit.py judge --items data/run_reports/phx1122/audit_items_names_sample.jsonl \
  --out data/run_reports/phx1122/audit_judgments_deepseek_names_sample.jsonl
```

The demo's builds come from the shipped readings, no key:

```python
import asyncio
from pathlib import Path

from theogony.config.settings import Settings
from theogony.mesh import frames
from theogony.mesh.ingestion.replay import load_readings, replay_text
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.seeds import DEMO_CORPUS, demo_corpus_path, demo_readings_path

settings = Settings()
text = demo_corpus_path().read_text(encoding="utf-8")
readings = load_readings(demo_readings_path())
for guard in ("v2", "names", "names_entities"):
    runtime = MeshRuntime(Path(f"data/demo-{guard}"), semantic_dim=settings.embedding.dim,
                          frame_dim=frames.DEFAULT_FRAME_DIM)
    asyncio.run(replay_text(runtime, text, readings, source_type=DEMO_CORPUS.source_type,
                            source_identifier=DEMO_CORPUS.source_identifier, title=DEMO_CORPUS.title,
                            anchor=DEMO_CORPUS.anchor, compact_every=50, settings=settings,
                            naming_guard=guard))
    runtime.compact()
```
