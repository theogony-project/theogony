# A node's description accrues when the entity is read again (PHX-1118)

> **Abstract.** *Question.* Track D of the plan — renamed on 2026-10-25 from
> "Nous" to Kadmos v2, reading with state. 2WikiMultihopQA has no documents
> (6,119 passages, one per title), so of the reader's designed mechanics only
> three transfer to it: revision at re-mention, Chronicle hints inside the
> read, and post-hoc synthesis. This is the first. When the reader recognises
> an entity it already holds, the node gains a reference edge and a firing and
> keeps the description of its first mention: 5,725 of the 28,464 mentioned
> nodes on the 2Wiki mesh are mentioned from two or more passages, and all of
> them describe the entity as the first paragraph did (median 78 characters
> on those nodes, 79 over all entity nodes, against the doctrine's 200–500). The typed Constellation's date ceiling is
> 14.8% against 55.6% for the arm that lays source paragraphs beneath it,
> because the description holds what was written once. Does folding the later
> paragraphs' descriptions into the node move the answer? *Method.* The same
> 6,119 cached readings replayed twice through the write path by the same code
> — accrual off, accrual on — then five answer arms on both meshes in one
> sitting (deepseek-chat, 1,000 questions, SQuAD exact match), paired question
> for question with the exact sign test and read by answer kind; the identity
> controls of PHX-1051 on both meshes. *Result.* 12,154 revisions on 6,508
> nodes. The typed Constellation goes from 48.0% to 52.9% exact match (104
> better, 55 worse, p = 0.0001); entity questions 49.3% → 54.1% (85 / 45,
> p = 0.0006); date questions 13.0% → 24.1% with the typed arm's date ceiling
> from 14.8% to 31.5%. The strongest arm, the typed Constellation with its
> source paragraphs and the yes/no sentence, goes from 53.9% to 57.4% (81 / 46,
> p = 0.002) and now beats five passages by 12.1 points (223 / 102). The
> passages arm, which does not read the mesh, moves 0.3 (7 / 4): the sitting
> was stable. Entity nodes 29,786 → 29,781; gold names on two or more nodes 10
> → 11; the largest hubs lost mentions, but 961 of the 43,118 mentions landed
> on a different node than before, many moving from a generic name to a
> narrower neighbour (Spain 40 → 13 as Spanish Empire 3 → 17) — whether they
> are better placed is not judged. *Limits.* One model; the typed arm's
> material is longer with accrual and the harness does not count tokens, but
> its ceiling moved too (61.0% → 66.8%), so the gain is not length alone; the
> sources arm without the yes/no sentence lost on yes/no questions (4 / 13,
> p = 0.049); the per-flush costs were not logged, only the wall-clock, which
> did not move. *Decision.* Both finish lines reached; the ticket is closed.
> Accrual stays off by default in this change; switching it on for the shipped
> reader is PHX-1119.

**Status:** 2026-10-26, measured once (two meshes, one sitting); PHX-1118 closed.
**Instrument:** `scripts/mesh_qa_mesh_ingest.py` (with `--accrue-descriptions`
for the on arm) built `data/mesh-2wiki-off` and `data/mesh-2wiki-on` from the
cached readings `data/raw/qa_bench/kadmos_readings_2wikimultihopqa.jsonl`;
`scripts/mesh_qa_constellation.py` answered five arms on both;
`scripts/mesh_qa_pair_runs.py` paired the two runs arm by arm;
`scripts/mesh_identity_controls.py` read the identity controls, and with
`--against` where the mentions moved. Reports: the
two `IngestRunReport`s (`01M5TTRGRMHNB8FEK75Q893HTC` off, `01M5V37KJ5YMTDZC3PETZAXPG5`
on, both `store.descriptions_revised` as stated), the answer runs
`data/run_reports/qa_constellation/2wiki_1000_phx1118_{off,on}.json`, the
pairing, the controls and the mention diff (`controls_diff.json`) under
`data/run_reports/phx1118/`. Code: commit
`d2c4866` on the branch of this change, both arms.

## The gap, and the step

The survey of 2026-10-25 ([`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md),
§D addendum) found two things before any plan. The name: reading with state is
Kadmos v2 work (ROADMAP §"On the name"), so this etappe says Kadmos v2. The
instrument: 2WikiMultihopQA, the one corpus with an answer arm the model does
not know, has no documents — 6,119 passages under as many titles, one
paragraph each — so document-local working memory has nothing to hold there,
and the founding corpus (prior 86%, [`gold_aliases.md`](gold_aliases.md))
cannot measure an answer. What transfers to a flat corpus is what happens when
a passage mentions an entity an earlier passage created.

Today that is a reference edge and a firing. `EagerLinker.link_reference`
returns the existing node; `merge_identity_evidence` writes only authoritative
Q-IDs, of which the reader offers none; nothing on the read path touches
`description`, `description_vector` or `description_source_chunks`. On
`data/mesh-2wiki` (the September mesh of PHX-1110) 28,464 nodes are mentioned
by a passage, 5,725 of them from two or more, 2,347 from three or more, and
every one keeps its first mention's text. The doctrine's band for a Tier-1
description is 200–500 characters (MESH_SUBSTRATE §"Field discipline", rule 4);
236 of 29,786 entity nodes were inside it.

Why this is the lever on the date ceiling: an entity's description holds what
the reader wrote about the entity once, not every date in every paragraph that
mentions it ([`yes_no_and_sources.md`](yes_no_and_sources.md)). The sources
arm closes that gap with passage text the mesh does not hold and `mesh_ask`
cannot return; richer descriptions close part of it inside the mesh.

## What the write path does now

- **`merge_description(standing, body)`**, pure and deterministic. The
  standing text stays a byte-identical prefix — the name head is what the label
  index, the resolver's aliases and the PHX-1051 naming guard key on. Each
  sentence of the new description whose comparable form (case-folded,
  whitespace-collapsed, without quotes and terminal punctuation) does not
  already occur in the result as whole words is appended in order while the
  result stays within 500 characters; a sentence that would cross the cap stops
  the merge at the sentence boundary. An initial or an abbreviation never ends
  a sentence ("J. R. R. Tolkien" stays one name — the first version split it
  into letters that the dedupe then dropped; found by review). Nothing added
  is not a revision.
- **One pending copy per node.** A node mentioned twice in one window builds
  on its pending copy, not on the stored row; the revisions land once per flush
  — at the compaction boundary (every 200 paragraphs), at the end of the read,
  or at 512 pending nodes — as one `description_many` call and one
  `merge_insert` on `id` (`MeshNodeStore.update_consolidated_many`). Both
  `description_vector` and `semantic_vector` follow the text, as the reader
  sets both from one string at creation and the consolidation pass sets both
  when it regenerates. The precedent the ticket named,
  `replace_all_consolidated`, overwrites the whole table and drops every Lance
  index: right for a maintenance pass that runs once, wrong for a read that
  flushes thirty times.
- **Provenance and audit.** `description_source_chunks` gains the revising
  chunk (once per chunk), `description_generated_at` the time; one staged audit
  row `mesh_ingest_description_revised` per revision, with the lengths before
  and after; `descriptions_revised` in the return dict, the `IngestRunReport`
  and the `mesh_ingest_run` payload, which also records which arm built the
  workspace. If the flush raises, the edges and the staged rows still land and
  a `mesh_ingest_description_flush_failed` row says which revisions did not.
- **The resolver's copy.** The Q-ID path answers from the resolver's cache
  without a store read; after a flush that copy is refreshed to the written row
  (a new `ConceptResolver.refresh`, which adds no alias), or the next mention
  would build on the pre-revision text and overwrite what was accrued. Found by
  review, latent on 2Wiki (no persisted Q-IDs), real on any seeded mesh.
- **Off by default.** `theogony mesh demo`, `mesh_append` and the replay
  cache are unchanged; the prompt and the reading schema do not change.

## What was measured

### The two replays

| | off | on |
|---|---|---|
| wall-clock, replay and final compaction | 149.7 min | 147.2 min |
| `IngestRunReport.duration_s` | 139.1 min | 137.3 min |
| `descriptions_revised` | 0 | 12,154 |
| consolidated nodes | 35,906 | 35,901 |
| entity nodes (not a source anchor) | 29,786 | 29,781 |
| `is_candidate` | 29,786 | 29,781 |
| `kadmos_mentions` edges | 43,118 | 43,118 |
| nodes mentioned from ≥ 2 passages | 5,725 | 5,791 |
| nodes mentioned from ≥ 3 passages | 2,347 | 2,375 |
| nodes with `description_source_chunks` | 0 | 6,508 |
| description characters: median / mean / p90 / max | 79 / 85.4 / 128 / 512 | 90 / 111.6 / 192 / 512 |
| descriptions inside the 200–500 band | 236 | 2,729 |
| link signals: description / tag / emergent | 12,872 / 1,814 / 28,432 | 12,796 / 1,899 / 28,423 |
| embedding model | `BAAI/bge-small-en-v1.5@v1` | same |

The on arm was not slower: its paragraph pass took 109.0 minutes against 113.0
for the off arm, which shared the machine with the test suite for its first
fifteen minutes. The per-flush timings the reader logs at INFO were not
captured by the ingest script, so the in-situ cost of a flush is bounded only
by the wall-clock: thirty-one flushes per corpus, and what one costs is the
next thing to log. The 512-character maximum on both arms is one pre-existing
description; accrual never writes past 500.

### Identity controls

| | off | on |
|---|---|---|
| gold names (836 entity questions) named on no / one / 2+ nodes | 121 / 705 / 10 | 123 / 702 / 11 |
| most nodes named for one gold name | 3 | 4 |
| tag-only carriers of a gold name, total / max | 1,237 / 53 | 1,247 / 53 |
| most-mentioned node | Newport International Film Festival, 123 | the same, 113 |
| next | France 85, United States 72, University of Parma 72 | University of Parma 81, France 76, American 62 |
| mentions that changed node (same chunk, other node) | — | 961 of 43,118 (2.2%) |
| labels whose mention count changed | — | 768 |

Entity nodes moved by five of 29,786 (0.02%, the acceptance allowed 2%); the
candidate flag follows the entity count on both arms. The entity count did not
move, but the linker's decisions did: 961 of the 43,118 mentions landed on a
different node with accrual on, and 768 labels changed their mention count.
The large generic hubs lost — Newport International Film Festival 123 → 113,
France 85 → 76, World War II 64 → 51, Spain 40 → 13, Los Angeles 34 → 11 —
and some of their mentions moved to adjacent or narrower names: Spanish Empire
3 → 17, City of Angels 8 → 22, English Crown 3 → 20, Ottoman forces 8 → 20 as
Ottoman Empire 13 → 0, Academy Award 45 → 61 as Academy Awards 35 → 17; eight
labels gained between 12 and 17 mentions, Venice Grand Prix 8 → 25 the largest.
No generic hub grew, which is the PHX-1051 pattern these controls were written
for; but a mention leaving a proper noun for a semantically adjacent node is
that pattern at a smaller scale, and the entity count, the top-20 and the
gold-name control (10 → 11) cannot see it. The richer surface also matched 66
more nodes from a second passage and shifted 76 link decisions from the
description signal to the tag signal. Whether the 961 moved mentions are better
or worse placed was not judged.

### The answers

One sitting, 2026-10-26 03:25–04:13 UTC, deepseek-chat, 1,000 questions, seed
0, `top_k` 50, `passage_k` 5, `k_seeds` 1, temperature 0; the passages arm
reads the same passage vectors on both runs and is the drift control.

| arm | off | on | Δ | better / worse | p |
|---|---|---|---|---|---|
| passages | 45.0% | 45.3% | +0.3 | 7 / 4 | 0.55 |
| constellation_typed | 48.0% | 52.9% | **+4.9** | 104 / 55 | 0.0001 |
| constellation_typed_yn | 49.6% | 54.6% | **+5.0** | 102 / 52 | 7 × 10⁻⁵ |
| constellation_sources | 52.1% | 54.3% | +2.2 | 74 / 52 | 0.061 |
| constellation_sources_yn | 53.9% | 57.4% | **+3.5** | 81 / 46 | 0.002 |

By answer kind, exact match and the ceiling (how often the answer stood in the
material), off → on:

| kind (n) | arm | exact match | ceiling |
|---|---|---|---|
| entity (836) | constellation_typed | 49.3% → 54.1% (85 / 45, p = 0.0006) | 71.7% → 77.0% |
| | constellation_sources_yn | 52.9% → 55.9% (65 / 40, p = 0.019) | 77.0% → 80.5% |
| | passages | 44.0% → 44.3% | 62.8% → 62.8% |
| yes/no (110) | constellation_typed | 55.5% → 58.2% (12 / 9) | 2.7% → 6.4% |
| | constellation_typed_yn | 66.4% → 73.6% (15 / 7, p = 0.13) | |
| | constellation_sources | 64.5% → 56.4% (4 / 13, p = 0.049) | 5.5% → 7.3% |
| | constellation_sources_yn | 68.2% → 74.5% (13 / 6, p = 0.17) | |
| date (54) | constellation_typed | 13.0% → 24.1% (7 / 1, p = 0.07) | **14.8% → 31.5%** |
| | constellation_sources_yn | 40.7% → 46.3% (3 / 0) | 55.6% → 63.0% |
| | passages | 33.3% → 33.3% | 46.3% → 46.3% |

Within the on run, the typed Constellation beats five passages by 7.6 points
(206 / 130, p = 4 × 10⁻⁵) and the strongest arm by 12.1 (223 / 102,
p < 10⁻⁹); in the off run the strongest arm's margin was 8.9 (197 / 108), the
October figure, so the sitting reproduces the record it extends.

### Against the ticket's finish line

Either of two conditions closed the ticket; both hold. The typed arm gained
4.9 points at p = 0.0001 against a required 2.0 at p < 0.05. The typed date
ceiling rose from 14.8% to 31.5% against a required 25%, and the 836 entity
questions did not lose (85 better, 45 worse). The entity count stayed within
0.02%, no generic hub grew — but 961 of 43,118 mentions changed node, unjudged; every revised node carries provenance, and the audit
rows equal the counter (12,154).

## What this does not show

- **One model, one sitting.** The pairing is the statistic; the totals move
  with the model's mood between months (the unchanged arms' totals here sit
  within a point of October's).
- **Length and content are not separated.** The typed arm renders each node's
  whole description (`_display_name`), so its material is longer on the on
  arm; the harness does not count prompt tokens. The ceiling moved too — the
  answer stood in the material 5.8 points more often — so the gain is at least
  partly content. Recording the material's length per arm is the next
  instrument.
- **The sources arm without the sentence lost on yes/no questions** (64.5% →
  56.4%, 4 / 13, p = 0.049): longer entity text beneath the passages seems to
  pull the model back to answering a yes/no question with an entity. The
  sentence of PHX-1113 repairs it (74.5% with it). The arm `mesh_ask` ships is
  the typed one, which gained on yes/no (12 / 9).
- **The per-flush cost was not logged in situ**; only the wall-clock, which did
  not move.
- **Not revised:** paragraph concepts (their descriptions carry a stance and
  are not name-headed), the first mention's chunk (the linker records none),
  and the 2Wiki mesh's one 512-character description.
- **The linker saw accrued surfaces mid-run** with a staleness window of one
  flush (200 paragraphs). The identity controls bound the effect; they do not
  explain it.
- **961 mentions changed node** between the arms, most leaving a generic hub
  for an adjacent or narrower name. No count above says whether the new
  placement is right; a per-mention audit of the movers is the next identity
  instrument (`scripts/mesh_identity_controls.py --against` lists them).
- **D1b** — a small cached model call regenerating the description instead of
  concatenating — was not run; the concatenation read well enough that the
  fallback arm was not needed.

## Decision

PHX-1118 is closed: reached. Accrual stays off by default in this change, so
`theogony mesh demo` and the fresh-clone probe are unchanged; switching it on
for the shipped reader, and regenerating the demo's recorded numbers, is
PHX-1119. The next step on this track is D2, Chronicle hints inside the read,
with a fresh stateless baseline read in the same week; D3, synthesis from
co-firing, after it ([`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md),
§D addendum).

## How to re-run

```bash
.venv/bin/python scripts/mesh_qa_mesh_ingest.py --dataset 2wikimultihopqa --root data/mesh-2wiki-off --fresh
.venv/bin/python scripts/mesh_qa_mesh_ingest.py --dataset 2wikimultihopqa --root data/mesh-2wiki-on --fresh --accrue-descriptions
.venv/bin/python scripts/mesh_identity_controls.py --root data/mesh-2wiki-off --json data/run_reports/phx1118/controls_off.json
.venv/bin/python scripts/mesh_identity_controls.py --root data/mesh-2wiki-on --json data/run_reports/phx1118/controls_on.json
.venv/bin/python scripts/mesh_identity_controls.py --root data/mesh-2wiki-off --against data/mesh-2wiki-on --dataset '' --json data/run_reports/phx1118/controls_diff.json
THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat .venv/bin/python scripts/mesh_qa_constellation.py --root data/mesh-2wiki-off --arms passages,constellation_typed,constellation_typed_yn,constellation_sources,constellation_sources_yn --passage-vectors data/mesh-2wiki/passage_vectors.npy --out data/run_reports/qa_constellation/2wiki_1000_phx1118_off.json
THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat .venv/bin/python scripts/mesh_qa_constellation.py --root data/mesh-2wiki-on --arms passages,constellation_typed,constellation_typed_yn,constellation_sources,constellation_sources_yn --passage-vectors data/mesh-2wiki/passage_vectors.npy --out data/run_reports/qa_constellation/2wiki_1000_phx1118_on.json
.venv/bin/python scripts/mesh_qa_pair_runs.py --a data/run_reports/qa_constellation/2wiki_1000_phx1118_off.json --b data/run_reports/qa_constellation/2wiki_1000_phx1118_on.json --json data/run_reports/phx1118/pairing.json
```

Two replays of about 150 minutes each, no key; two answer runs of about 23
minutes each, about one euro each on deepseek-chat.
