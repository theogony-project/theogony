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
- `docs/TAKE_THIS.md`: the pieces that stand on their own, with their evidence and their limits.
- `scripts/fresh_clone_probe.sh`, `scripts/mcp_probe.py`: the documented quickstart, run as a stranger would.
- The answer benchmark reports exact match by answer kind (entity / yes-no / date).
- `docs/etappes/README.md`: the measurement record indexed in one table; the ten German etappes of September 2026 each open with an English abstract.

### Changed
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

### Planned for 0.2.0
- Neo4j KnowledgeStore implementation
- GutenbergAdapter (acquisition from Project Gutenberg)
- Extraction pipeline: NER + Wikidata entity alignment
- Embedding generation (sentence-transformers, local)
- Multi-hop retrieval: vector + graph, recursive, deduplicated
- Minimal CLI: `theogony ingest` and `theogony ask`

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
