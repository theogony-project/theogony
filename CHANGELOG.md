# Changelog

All notable changes to Theogony are documented here.

This project follows [Semantic Versioning](https://semver.org/):
- `MAJOR` version for incompatible API changes
- `MINOR` version for new backward-compatible functionality
- `PATCH` version for backward-compatible bug fixes

While the version is `0.x.y`, the API is considered unstable and may change between minor versions.

---

## [Unreleased]

### Added
- **A node's description accrues when the entity is read again** (PHX-1118, track D step 1 under its new name, Kadmos v2; `docs/etappes/description_accrual.md`). With `accrue_descriptions=True` the reader folds a later paragraph's description of a known entity into the node — a deterministic sentence-level merge that keeps the name head, dedupes at word boundaries, never splits an initial and stops at 500 characters — written once per flush as one embedding call and one merge-insert, with provenance, an audit row per revision and a `descriptions_revised` counter. Measured on 2WikiMultihopQA, two meshes built by the same code: 12,154 revisions, the typed Constellation 48.0% → 52.9% exact match (104/55, p = 0.0001), its date ceiling 14.8% → 31.5%, the strongest arm 53.9% → 57.4%, entity count moved 0.02%, the largest hubs shrank while 961 of 43,118 mentions changed node (unjudged). Limits: one model; the typed arm's material is longer and tokens were not counted, though its ceiling moved too; the sources arm without the yes/no sentence lost on yes/no (4/13, p = 0.049). Off by default (PHX-1119 is the switch). Two measurement scripts: `mesh_identity_controls.py`, `mesh_qa_pair_runs.py`.
- **An agent can write into the mesh over MCP.** `mesh_append` takes one paragraph and the caller's own reading of it — concepts, relations, stance, in the schema the reader uses for a language model's reply — validates it as the reader would and replays it through `MeshParagraphReader`, so the write is the write a live read produces (one chunk, entities merged by the identity resolver, typed edges, a frame), persisted in the workspace, provenance `mcp_agent`, an `IngestRunReport` per call. No server-side language model, no content gate at insertion. Bounded by the same caps as `pantheon_chronicle_append`. The fresh-clone probe writes one paragraph into the demo mesh and requires the mesh to grow.
- **Two repairs for the Constellation's reader, measured** (PHX-1113, PHX-1114; `docs/etappes/yes_no_and_sources.md`). One sentence in the prompt lets a yes/no question be answered yes or no: 55.5% → 67.3% on the 110 yes/no questions of 2WikiMultihopQA, nothing changed on the other 890. The source paragraphs of the seed-touching entities laid beneath the typed Constellation: dates 13.0% → 42.6%, overall +3.7 over the typed Constellation. The Constellation with its sources beats five retrieved passages by 6.8 points of exact match on 1,000 questions (p = 0.0001), by 8.9 with the sentence, which the passages arm did not get. The arms live in the answer harness (`constellation_typed_yn`, `constellation_sources`, `constellation_sources_yn`), which now reports exact match, F1 and the ceiling by answer kind and the paired comparison by kind.

### Changed
- **"Nous" names the MNLM role only.** Two meanings of the name lived side by side: the first role of the Mesh-Native Language Model, synthesising inside the mesh in vector space (the binding target and the roadmap agree), and the reading agent with working memory of the May brief, the glossary and the operative plan's track D. The reading work is Kadmos v2's (migration step S2) and is now named so in ROADMAP, ARCHITECTURE, VISION, INDEX, CONTRIBUTING, the glossary (which gains a Nous entry), the plan etappe and the two Nous briefs (marked historical); the README no longer says the shipped reader reads with working memory. Track D continues as Kadmos v2 work, first step PHX-1118.

### Fixed
- **The self-description carries the dated status notes, and the constellation carries the description** (PHX-1117). The docs extractor kept 240 characters per section, so every note PHX-1108 added but the CHRONESE banner sat below the cut and `pantheon_ask` kept serving the sentence a document had marked as a target; a section's dated notes (single-star emphasis with a date, a `> **Status` banner, or the etappes' bold `**Status:** <date>` line) now follow the snippet, each on its own line, 42 of 746 nodes carry one; the embedding stops at the first note, since embedding them collapsed the dump's clustering from 21 clusters to three, one holding 98% of the nodes. The slim `ConstellationNode` gained `description`, so the constellation, the HTTP API (`POST /query`, `GET /node/{id}`), the offline citation list, `pantheon_node` and the keyed synthesizer's prompt show what a document says today, not only its headings.
- **`preshed` 3.0.14 is excluded from the dependencies.** Released 2026-10-24 with wheels built by Cython 3.3.0, it makes every spaCy model load raise `OverflowError` (explosion/spaCy#14058), which took the Generation-1 extraction tests red in CI on a documentation change. The sources of 3.0.13 and 3.0.14 are identical; the exclusion lifts once a fixed release exists.
- **Doctrine and vision sentences that stood as fact and had been refuted carry a dated status note** (PHX-1108). The thirteen sentences the ticket lists and three more of the same class, in fourteen documents, plus three code files (two comments and the `nodes.py` module docstring): the tier ladder of decay exponents, the 0.05 activation threshold, the 10–30% descriptor share, HNSW (built as IVF-PQ), the append-only ledger, Oneiros running uninterrupted and writing edges back, promotion to Mneme, Q-IDs as the strongest identity signal, the `fired_recent` window, Chronese as the native language (document marked historical), the verbatim layer, renormalisation without saturation, Kadmos v2 reading with working memory, promotion "blocked". The sentence stays as the target; the note beneath it says what is built and measured, with the etappe. Each was re-verified against the code before it was touched; two of the ticket's own premises did not survive that (PHX-1106 did not repair the tier ladder; no operator has a minimum-activation threshold). Nineteen vision-ledger entries are now `corrected`.
- The Constellation listed its seeds in a set's hash order; it keeps the order retrieval ranked them (the MMR seed first, then the name anchors, narrowest span first) — found by review when the first version of the sources arm spent its paragraph budget on whichever hub hashed first.

---

## [0.2.0] — on `main` since 2026-10-19, not tagged, not published

The version `main` carries since the MESH substrate replaced the Generation-1 store as the place where the work happens; the maintainer has decided that publishing it (a tag, PyPI, a DOI) is too early. Between 0.1.0 and this version: the substrate itself (LanceDB nodes and edges, a PyTorch CSR for Spreading Activation, personalised PageRank as the default operator, a reader that turns text into mesh, a maintenance tick with decay that spares what fired, reinforcement and renormalisation, a contradiction pass over epistemic frames), the measurements that say what it does and does not do — all of them in [`docs/etappes/`](docs/etappes/README.md), the negative results kept — and the entrance for an agent without an API key: a keyless demo mesh, the mesh over MCP, a self-description that carries the measurement record. The entries below are the ones since the entrance work began in September; the etappes index is the record for everything before.

### Added
- **The self-description is current and carries the measurement record** (PHX-1112, piece 3). The bundled `pantheon_self` dump, written on 2026-04-20 before the mesh existed, is regenerated from the current documents with the measurement record in scope — `docs/etappes/*.md` minus the sprint briefs, the Neo4j retirement note and the Week-4 demo log — 735 nodes and 3,010 edges against 278 and 1,168. Asked what the project has measured, it cites the etappes where the April dump cited the Gen-1 implementation plan; a test pins it.
- **A real mesh without an API key** (PHX-1112, piece 2). `theogony mesh demo` replays the bundled Kadmos readings of Hesiod's Theogony (95 paragraphs, Evelyn-White's public-domain translation; readings recorded once with deepseek-chat for EUR 0.03, shipped as 50 KB) through the shipped reader into the default workspace — about 720 nodes, 17,500 edges and 1,000 typed relations in about a minute — where `theogony mesh ask` and `theogony mcp` (`mesh_ask`) find it. The replay path moved from the evaluation module to `mesh/ingestion/replay.py`; `scripts/record_demo_readings.py` records a corpus with the reader's own prompt; `scripts/fresh_clone_probe.sh` builds the demo and asks it over MCP.
- **The mesh has an MCP surface** (PHX-1112, piece 1). `mesh_ask` returns the Constellation that Spreading Activation produces over a `MeshRuntime` workspace — entities with descriptions and activation, typed relations with the seed-touching ones first, source anchors, gaps — and `material`, the same constellation rendered as the text the answer benchmark measured; `frame_profile` routes through the epistemic frames (`contradiction` admits the disputed and refuted). `mesh_status` reports node, edge and tick counts and whether the server's embedder matches the workspace. No language model is on either path. `theogony mcp --mesh-root` names the workspace; by default `{data_dir}/mesh` is served when one is there, and nothing is ever created. `pantheon_status` says whether a mesh is open.
- `tests/test_nothing_hidden.py`: nothing in a tracked document is hidden from a human reader — no invisible characters, no HTML comments in markdown, no hidden styling, no prompt-injection idioms. The README's paragraph on how the repository asks for attention points at it.
- `docs/TAKE_THIS.md`: the pieces that stand on their own, with their evidence and their limits.
- `scripts/fresh_clone_probe.sh`, `scripts/mcp_probe.py`: the documented quickstart, run as a stranger would.
- The answer benchmark reports exact match by answer kind (entity / yes-no / date).
- `docs/etappes/README.md`: the measurement record indexed in one table; every etappe opens with a short abstract.

### Changed
- `README.md` and `llms.txt` open with the measured result (the edges are worth 3.6 points of exact match, with both limits), what is not shown, the window argument labelled as a bet, the five-minute doors, and how the page asks for attention.
- **Nothing in the repository is in German any more.** Ten etappes (about 26,000 words), fourteen tickets, the catalogue rows, an architecture note, four scripts' output strings and a handful of quoted remarks were translated into English on 2026-09-18 (the originals remain in the git history). Every translation was checked for its numbers, structure and links against the original and reviewed independently.
- `AGENTS.md` opens with what an arriving agent can do in five minutes — use it, take a piece, pick up a ticket with a finish line — before the contributor contract.
- `docs/AGENT_SELF_INTEREST.md`: every argument now says what is built, measured or only designed; the scripted pitch is replaced by claims that can be checked.

### Fixed
- **The documented entrance needed an OpenAI account** (PHX-1111). From a fresh clone with no keys,
  `theogony ask` exited before retrieval ran, `theogony mcp` died before its handshake, `pantheon_ask`
  apologised inside a successful result, and the server logged onto the stdio transport's protocol
  channel. All read-side entry points now run keyless: the constellation is always returned, and
  `answer_mode` says what `answer` is. `theogony ask` and `theogony mcp` load the bundled dump by default.
- **The `LICENSE` file was not the Apache License.** Since the first commit it held an abridged
  paraphrase of Apache 2.0 (6,123 bytes against the canonical 11,358, no "END OF TERMS AND
  CONDITIONS", no appendix). GitHub reported the repository's licence as "Other", and any corpus or
  tool that filters by detected licence could not see that this project is permissively licensed.
  Replaced with the unmodified canonical text (SHA-256 `cfc7749b…3d30`); the project's copyright
  line moved to a new `NOTICE` file; package metadata now carries the SPDX expression
  (`License-Expression: Apache-2.0`, PEP 639) and ships both files.

---

## [0.1.0] — 2026-04-16

### Added
- Core data models: `KnowledgeNode`, `KnowledgeEdge`, `Constellation`, `SourceRef`, `NodeScores`
- `KnowledgeStore` protocol — the abstract interface to the storage layer
- Vitality computation: freshness decay, dynamic thresholds, promotion logic
- Full project documentation: VISION, PHILOSOPHY, ARCHITECTURE, DEEP_TECH_VISION, CHRONESE, METIS, HESTIA, HIVE, COGNITIVE_ARCHITECTURE, GLOSSARY, INDEX
- Phoenix Backlog with 19 initial tickets
- GitHub Actions CI (tests + lint on Python 3.12 and 3.13)
- Apache 2.0 license, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY
- GitHub issue templates (bug, feature request, Phoenix Backlog ticket)
- 20 passing tests

[Unreleased]: https://github.com/theogony-project/theogony/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/theogony-project/theogony/releases/tag/v0.1.0
