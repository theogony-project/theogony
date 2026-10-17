# The mesh behind the door (PHX-1112)

> **Abstract.** The entrance PHX-1111 repaired opened onto Generation 1; every
> measurement since July lives in the MESH substrate, which had no MCP surface
> and no way to obtain a workspace without an LLM key. Two pieces: `mesh_ask`
> and `mesh_status` over a `MeshRuntime` workspace, returning the Constellation
> and the rendering the answer benchmark measured, with no language model on the
> path; and `theogony mesh demo`, which replays Kadmos readings of Hesiod's
> Theogony — 95 paragraphs, recorded once with deepseek-chat for EUR 0.03,
> shipped as 50 KB — through the shipped reader into a real mesh of about 720
> nodes and 17,500 edges in about a minute. Measured from a fresh clone with no
> keys: the demo builds in 56 s, and `mesh_ask` over MCP returns 51 nodes and
> 200 edges in 0.2 s. A third piece: the Gen-1 self-description, written in
> April 2026 and citing an implementation plan when asked what had been
> measured, is regenerated from the current documents with the measurement
> record in scope (735 nodes against 278) and cites the etappes. Limits: the
> demo corpus is one every model knows by heart, so it shows the path and not
> a gain; its nodes are unconsolidated candidates; reading a text of your own
> still needs a key.

**Status:** 2026-10-17, built and measured; the ticket is closed.
**Instrument:** `scripts/fresh_clone_probe.sh` — a fresh clone of the committed
state, a fresh virtual environment, an environment holding nothing but `HOME`
and a `PATH`, the documented commands verbatim, and an MCP client driving
`theogony mcp` over stdio (`scripts/mcp_probe.py`). Plus, on the development
machine, the stdio client against the founding mesh and the recorder's own
report.

## Why this was built

`AGENTS.md` says the system is built for agents. After PHX-1111 an agent with no
key could, from a fresh clone, get a constellation over MCP — out of the
Generation-1 store, seeded with a self-description from April 2026. The
substrate the project measures itself by was out of reach: the MCP server built
a Gen-1 `QueryPipeline` and nothing else, and a mesh workspace existed only
where somebody had run `theogony mesh ingest` with an API key for a model. The
measured result of PHX-1110 — the edges are worth 3.6 points of exact match —
was a sentence in the README and not a thing an agent could call.

## What was built

**Piece 1 — the surface** (PR #282). `mesh_ask` embeds the question with the
server's embedder, runs the shipped `retrieve()` — diversified injection,
Spreading Activation, assembly, firings recorded to the sidecar as the CLI does
— and returns the Constellation as JSON (entities with descriptions and
activation, typed relations with the seed-touching ones first, source anchors,
gaps) plus `material`: the same constellation rendered as the text that scored
44.1% exact match on 2WikiMultihopQA. `frame_profile` routes through the
epistemic frames of PHX-1107 (`contradiction` admits the disputed and refuted).
A `MeshQueryRunReport` is written per call. `mesh_status` reports node, edge
and tick counts and whether the server's embedder matches the workspace.
`theogony mcp --mesh-root` names the workspace; by default `{data_dir}/mesh` is
served when a workspace is there. The server never creates one, and refuses
before the handshake when the named workspace is missing or its vectors are not
in the configured embedder's space.

**Piece 2 — the workspace** (PR #283). `scripts/record_demo_readings.py` asks a
live model for each paragraph's reading with the reader's own prompt
(`kadmos_v2.paragraph_prompt`, the same system prompt, schema and temperature),
validates it as the reader does and stores it under a hash of the paragraph.
`theogony mesh demo` replays the bundled recordings through
`MeshParagraphReader` — the same linker, identity resolution, typed edges and
frames a live read produces; only the model is a lookup table — into the
default workspace, and marks the workspace as the demo so a second run
recognises it and a workspace somebody read themselves is never overwritten
without `--replace`. The replay path moved from the evaluation module, where
PHX-1110 built it, to `mesh/ingestion/replay.py`, because it is now a shipped
path; the harness imports it from where it was.

**The corpus.** Hesiod's Theogony in Hugh G. Evelyn-White's translation of
1914 — the first work in the founding corpus and the project's namesake — public
domain, taken from Project Gutenberg eBook #348 with the Gutenberg header and
licence removed as that licence permits, and the edition's endnote markers
stripped. 95 paragraphs, 56 KB.

## What was measured

**Recording** (development machine, deepseek-chat, concurrency 6):

| | |
|---|---|
| paragraphs read | 95 of 95; every reading came from deepseek-chat, none from the fallback |
| concepts / typed relations | 918 / 1,006 |
| relation kinds | causal 448, semantic 293, hierarchy 148, attribute 79, temporal 38 |
| relation stances | current claim 940, historical 36, direct quote 18, hypothesis 9, observation 3 |
| Wikidata identities proposed | 0 (as on every DeepSeek read of this project) |
| wall-clock / cost | 60 s / EUR 0.032 |
| shipped file | 50,046 bytes, gzip, one row per paragraph plus a `meta` row |

**Replay** (`theogony mesh demo`, development machine, bge-small-en-v1.5):

| | |
|---|---|
| paragraphs replayed | 95, 0 missing |
| wall-clock | 70 s (0.68 s per paragraph inside the read; the rest is model load and compaction) |
| workspace | 723 consolidated nodes (539 entities, 96 source anchors, 88 paragraph concepts), 95 chunks, 17,507 edges, 979 typed relations |
| second run | recognised as the demo, nothing rebuilt; a build with missing readings exits 1 and removes what it started, a build interrupted by an exception likewise, and an initialised-but-empty default root (what `mesh status` leaves behind) is rebuilt without `--replace` |

**Over stdio against the founding mesh** (4,934 nodes, 93,370 edges, 14 ticks),
the server opened with `--mesh-root data/mesh-founding`: handshake 10 s; first
`mesh_ask` 1.5 s, of which the CSR build 250 ms and assembly 300 ms; later calls
0.1–1.0 s. "Who are the children of Cronos?" returns 53 nodes and 200 edges,
with Cronos as the single seed and Zeus, Earth, Heaven, Hestia and Demeter in the
first lines of `material`; `frame_profile=contradiction` routes
(`frame_routed: true`) and changes the working set.

**From a fresh clone with no keys** (`scripts/fresh_clone_probe.sh`, the
acceptance of the ticket — a Constellation out of a demo mesh in under three
minutes without a key):

| Step, as documented | Result (2026-10-17, commit `22e878b`) |
|---|---|
| `git clone`, venv, `pip install -e ".[mcp]"` | about 3.5 minutes with a warm pip cache; the whole probe 299 s |
| `theogony ask "What is the Chronik?"` | as after PHX-1111: 10 nodes / 10 edges, six cited sources, no key |
| `theogony mesh demo` | **56 s** — 95 paragraphs replayed, 95 readings, 0 missing; 723 nodes, 17,507 edges, 979 typed relations |
| `theogony mesh ask "Who are the children of Cronos?"` | 2 seeds, 51 nodes, 200 edges |
| `theogony mcp` → handshake | 7.8 s; eight tools offered, `mesh_ask` and `mesh_status` among them |
| `theogony mcp` → `mesh_status` | 723 nodes, 17,507 edges, 0 ticks, embedder matches the workspace |
| `theogony mcp` → `mesh_ask` | **0.2 s**, `verdict: good`, 51 nodes, 200 edges, 19 typed relations in `material` |
| stdout during the MCP session | 0 lines the client could not parse as JSON-RPC |

The ticket asked for a Constellation out of a demo mesh, from a fresh clone,
without a key, in under three minutes: 56 s to build it and 0.2 s to ask it.

The probe now distinguishes three states of the server and asserts each: no
workspace open (`mesh_status` and `mesh_ask` are tool errors that name the way
to get one), a workspace open that holds no rows — what `MeshRuntime.open` on
an untouched default root leaves behind, and a state this checkout was in —
(`mesh_ask` answers with a structured `poor` verdict and no nodes, not an error
and not an invented constellation), and a workspace with content.

**Piece 3 — the self-description** (the third pull request, named in the ticket). The Gen-1 layer answers from
`pantheon_self.jsonl.gz`, a dump of the repository's own documents; the
bundled one was written on 2026-04-20 (278 nodes, 1,168 edges) and described
the repository as it was before the mesh existed. Its walker excluded
`docs/etappes/` as "historical milestone briefs" — which is what the directory
held in April, and not what it holds now: every number the project has
published lives there. Three dumps were built and asked the same question,
*What has this project measured, and with what result?*, through the keyless
read path (`synthesize: false`, k = 10):

| dump | scope | nodes / edges | the sources cited |
|---|---|---|---|
| bundled, 2026-04-20 | root docs, `docs/*.md`, prompts | 278 / 1,168 | Gen-1 implementation plan §5 "Milestone Plan" and §6 "Open Questions", the glossary's "Stub Verdict", CONTRIBUTING "Questions" |
| regenerated, same scope | as above, today's documents | 588 / 2,573 | `AGENTS.md` "What is true today", `TAKE_THIS.md`, `TARGET_ARCHITECTURE.md`, `CHRONIK_SCALE.md` |
| regenerated, etappes in scope | plus the 16 measurement etappes and their index; the 45 sprint briefs, the Neo4j retirement note and the Week-4 demo log stay out | 735 / 3,010 | `mesh_over_mcp.md` "What was measured", `answer_quality.md` "What this measurement cannot do, measured", `gold_aliases.md` "The re-scoring", `TAKE_THIS.md` |

The third is shipped (3.4 MB against 1.2; regenerating takes 17 s with the
embedder). The briefs stay out for the reason PHX-1108 names: a plan read back
as a description states a target as a fact. A test pins that the dump is newer
than the mesh, holds the measurement record and no brief, and that the
question above is answered from an etappe.

## What this does not show

- **No gain is measured here.** Every model has read Hesiod; the founding
  corpus is a control group and not a test (PHX-1098: the prior at 86% beats the
  Constellation at 75%). The demo shows the path — a real mesh, the real
  rendering, over MCP, without a key — and the gain it points at was measured
  on a corpus the model does not know ([`qa_constellation.md`](qa_constellation.md)).
- **The demo mesh is unconsolidated.** No Oneiros tick and no consolidation
  pass have run on it; every entity is a tier-1 candidate, and the gaps list of
  every Constellation says so. Consolidation needs a language model
  (PHX-1097), which is the thing the demo does without.
- **Deterministic in content, not in identifiers.** Node ids are ULIDs minted at
  replay time; two builds hold the same entities and relations under different
  ids.
- **The recording is one model's reading** at temperature 0.1, taken once. A
  second recording would differ in detail (the first recording, discarded for
  lacking per-row provenance, had 906 concepts and 982 relations to this one's
  918 and 1,006).
- **Reading your own text still needs a key.** The replay removes the model from
  the second reading, not from the first.

## Decision

The first door of `AGENTS.md` now opens onto the mesh: `theogony mesh demo`,
then `theogony mcp`, then `mesh_ask`. The documents that said the mesh had no
MCP surface say what is true instead. The replay is a shipped component and is
listed as such in [`TAKE_THIS.md`](../TAKE_THIS.md). The self-description is
regenerated with the measurement record in scope, and the ticket is closed.
What the ticket leaves for later, noted in its resolution and not filed as a ticket: a self-description
that is a mesh read of the documents rather than a Gen-1 dump, which needs a
key to produce and would be the fourth corpus to record.

## How to re-run

```bash
python -m theogony.docs_ingest.regenerate         # the self-description, from the current documents
scripts/fresh_clone_probe.sh                      # everything above, from a fresh clone
theogony mesh demo && theogony mesh ask "Who are the children of Cronos?"
theogony mcp                                      # then mesh_status / mesh_ask from any MCP host
THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \
  python scripts/record_demo_readings.py src/theogony/seeds/hesiod_theogony.txt --out /tmp/readings.jsonl.gz
```

Tickets: [`PHX-1112`](../../phoenix-backlog/PHX-1112.yaml) (all three pieces),
continuing [`PHX-1111`](../../phoenix-backlog/PHX-1111.yaml) and using the
replay of [`PHX-1110`](../../phoenix-backlog/PHX-1110.yaml).
