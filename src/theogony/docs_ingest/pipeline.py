"""
Orchestrate the docs-aware ingest pipeline end-to-end.

Input: a :class:`RepoSnapshot` (a directory + the include/exclude policy
from :mod:`theogony.docs_ingest.repo_walker`).

Output: an :class:`ExtractedChronicle` containing :class:`KnowledgeNode`
and :class:`KnowledgeEdge` records ready to be either persisted to a
:class:`KnowledgeStore` or written to a JSONL.gz dump for later seeding.

Embeddings are optional. When the caller passes an embedder, every
section / glossary-concept node receives a vector via the same
:class:`LocalSentenceTransformerEmbedder` interface the rest of
Theogony uses. When no embedder is supplied, nodes ship with empty
``embedding`` lists; downstream code can re-embed at seed-time if the
deployment uses a different embedding model than what generated the
dump.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest.extractors import (
    DEFAULT_REPO_BASE_URL,
    ExtractedChronicle,
    extract_document_nodes,
    extract_glossary_concepts,
    extract_link_edges,
    extract_mention_edges,
    extract_part_of_edges,
    extract_section_nodes,
)
from theogony.docs_ingest.markdown_parser import (
    ParsedDocument,
    ParsedSection,
    parse_markdown,
)
from theogony.docs_ingest.repo_walker import (
    DEFAULT_EXCLUDE,
    DEFAULT_INCLUDE,
    walk_repo,
)
from theogony.extraction.embedding import EmbeddingProvider


@dataclass(frozen=True)
class RepoSnapshot:
    """Input shape for the docs pipeline.

    ``repo_root`` is the directory to walk; ``include`` / ``exclude``
    follow the conventions in :mod:`theogony.docs_ingest.repo_walker`.
    ``repo_base_url`` is the GitHub blob URL inserted into each node's
    :class:`SourceRef` so citations link back to the canonical source.
    """

    repo_root: Path
    include: tuple[str, ...] = DEFAULT_INCLUDE
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE
    repo_base_url: str = DEFAULT_REPO_BASE_URL


def _parse_all(snapshot: RepoSnapshot) -> list[ParsedDocument]:
    walked = walk_repo(
        snapshot.repo_root,
        include=snapshot.include,
        exclude=snapshot.exclude,
    )
    parsed: list[ParsedDocument] = []
    for f in walked:
        raw = f.abs_path.read_text(encoding="utf-8")
        parsed.append(parse_markdown(f.rel_path, raw))
    return parsed


def _index_sections(
    parsed_docs: Iterable[ParsedDocument],
    section_nodes: list[KnowledgeNode],
) -> dict[str, list[tuple[ParsedSection, KnowledgeNode]]]:
    """Build the rel_path → [(section, node)] index used by the edge extractors.

    Pairs are matched by ``(rel_path, line_start, heading)`` — the
    same triple the section node id is hashed from, so the alignment
    is total.
    """
    by_id: dict[tuple[str, int, str], KnowledgeNode] = {}
    for n in section_nodes:
        rel = n.properties.get("rel_path", "")
        line_start = _line_start_from_location(n.source_ref.location)
        by_id[(str(rel), line_start, n.label)] = n

    out: dict[str, list[tuple[ParsedSection, KnowledgeNode]]] = {}
    for doc in parsed_docs:
        pairs: list[tuple[ParsedSection, KnowledgeNode]] = []
        for section in doc.sections:
            key = (doc.rel_path, section.line_start, section.heading)
            node = by_id.get(key)
            if node is None:
                continue
            pairs.append((section, node))
        out[doc.rel_path] = pairs
    return out


def _line_start_from_location(location: str | None) -> int:
    """Reverse the ``L<start>-L<end>`` formatter back into ``start``."""
    if not location or not location.startswith("L"):
        return 0
    head = location[1:].split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return 0


async def _embed_all(
    nodes: list[KnowledgeNode],
    embedder: EmbeddingProvider,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """Mutate every node in place with its embedding.

    Skips nodes that already carry an embedding (idempotent reruns).
    Records ``embedding_model_id`` and ``embedding_dim`` so the seed
    file is honest about which model produced its vectors.
    """
    total = len(nodes)
    for idx, node in enumerate(nodes):
        if node.embedding:
            if progress:
                progress(idx + 1, total)
            continue
        text = _embedding_text_for(node)
        node.embedding = await embedder.embed(text)
        node.embedding_model_id = embedder.model_id
        node.embedding_dim = embedder.dim
        if progress:
            progress(idx + 1, total)


def _embedding_text_for(node: KnowledgeNode) -> str:
    """Choose the text that represents ``node`` for embedding.

    Prefer ``label + description`` to ``label`` alone — the description
    carries the discriminating signal a vector search needs for short
    glossary terms like "Mneme" or "Hestia" that would otherwise have
    near-identical embeddings.
    """
    label = node.label
    desc = node.description or node.source_ref.snippet or ""
    if desc:
        return f"{label}. {desc}"
    return label


def build_chronicle(
    snapshot: RepoSnapshot,
    *,
    embedder: EmbeddingProvider | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> ExtractedChronicle:
    """End-to-end synchronous wrapper for the docs-aware pipeline.

    Internally this calls :func:`build_chronicle_async`; provided for
    callers that have no event loop (CI scripts, simple regen flows).
    """
    return asyncio.run(build_chronicle_async(snapshot, embedder=embedder, progress=progress))


async def build_chronicle_async(
    snapshot: RepoSnapshot,
    *,
    embedder: EmbeddingProvider | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> ExtractedChronicle:
    """Run the full docs-ingest pipeline against ``snapshot``.

    Pipeline stages:

    1. Walk the repo, parse every in-scope ``.md`` file.
    2. Run all node-extractors (documents, sections, glossary concepts).
    3. Run all edge-extractors (PART_OF, LINKS_TO, MENTIONS).
    4. Optionally embed every node via ``embedder``.
    """
    parsed_docs = _parse_all(snapshot)

    document_nodes = extract_document_nodes(parsed_docs, repo_base_url=snapshot.repo_base_url)
    section_nodes = extract_section_nodes(parsed_docs, repo_base_url=snapshot.repo_base_url)
    glossary_nodes = extract_glossary_concepts(parsed_docs, repo_base_url=snapshot.repo_base_url)

    documents_by_rel_path = {n.properties.get("rel_path", ""): n for n in document_nodes}
    sections_by_rel_path = _index_sections(parsed_docs, section_nodes)

    part_of_edges = extract_part_of_edges(documents_by_rel_path, sections_by_rel_path)
    link_edges = extract_link_edges(parsed_docs, sections_by_rel_path, documents_by_rel_path)
    mention_edges = extract_mention_edges(parsed_docs, glossary_nodes, sections_by_rel_path)

    nodes: list[KnowledgeNode] = list(document_nodes) + list(section_nodes) + list(glossary_nodes)
    edges: list[KnowledgeEdge] = list(part_of_edges) + list(link_edges) + list(mention_edges)

    if embedder is not None:
        await _embed_all(nodes, embedder, progress=progress)

    return ExtractedChronicle(nodes=nodes, edges=edges)


__all__ = [
    "RepoSnapshot",
    "build_chronicle",
    "build_chronicle_async",
]
