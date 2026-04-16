# Changelog

All notable changes to Theogony are documented here.

This project follows [Semantic Versioning](https://semver.org/):
- `MAJOR` version for incompatible API changes
- `MINOR` version for new backward-compatible functionality
- `PATCH` version for backward-compatible bug fixes

While the version is `0.x.y`, the API is considered unstable and may change between minor versions.

---

## [Unreleased]

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
