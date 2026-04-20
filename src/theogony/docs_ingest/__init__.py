"""
Documentation-aware ingest path for the Chronik.

A parallel pipeline to ``extraction/`` (Gutenberg-style narrative
prose), tuned for the very different genre of repository
documentation: hierarchical Markdown, project-internal vocabulary,
glossary as the canonical entity source, no Wikidata resolution.

The output is a set of :class:`KnowledgeNode` and :class:`KnowledgeEdge`
records compatible with the existing :class:`KnowledgeStore` protocol.
This package is **deterministic** — no LLM calls, no Wikidata round
trips, fully reproducible from a given snapshot of the docs.

Public surface:

- :func:`build_chronicle` — orchestrates parsing + extraction + embedding
- :func:`write_dump` / :func:`read_dump` — JSONL.gz round-trip for the
  pre-built ``pantheon_self`` seed shipped in the wheel
- :class:`RepoSnapshot` — the input shape (a set of Markdown files
  rooted at a repo)

Why parallel rather than reused: the existing ``extraction.pipeline``
assumes prose narrative + Wikidata-resolvable entities + LLM-driven
relation extraction. Repo docs are structured, project-internal, and
fully covered by deterministic parsing. Mixing the two would
contaminate both — the docs pipeline would never benefit from the
prose-pipeline's Stage-4 LLM disambiguation, and the prose pipeline
would inherit the docs-pipeline's Markdown structural assumptions.
"""

from __future__ import annotations

from theogony.docs_ingest.dump import read_dump, write_dump
from theogony.docs_ingest.pipeline import RepoSnapshot, build_chronicle

__all__ = [
    "RepoSnapshot",
    "build_chronicle",
    "read_dump",
    "write_dump",
]
