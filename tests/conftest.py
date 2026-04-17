"""Shared pytest fixtures for the Theogony test suite."""

from __future__ import annotations

from theogony.core import KnowledgeNode, NodeType, SourceRef


def make_source_ref(
    location: str = "chapter_03:offset_18433",
    snippet: str | None = None,
) -> SourceRef:
    """Construct a deterministic SourceRef for fixture nodes."""
    return SourceRef(
        source_type="gutenberg",
        identifier="Gutenberg:944",
        location=location,
        snippet=snippet,
        language="en",
    )


def make_node(
    label: str = "Test Node",
    *,
    node_type: NodeType = NodeType.PLACE,
    location: str | None = None,
    embedding: list[float] | None = None,
    confidence: float = 0.5,
) -> KnowledgeNode:
    """Construct a KnowledgeNode pinned to a unique-by-location SourceRef.

    The default ``location`` is derived from ``label`` so distinct
    fixture nodes get distinct deterministic IDs (per §9.5) without
    the caller having to manage source-ref uniqueness manually.
    """
    ref = make_source_ref(location=location or f"loc:{label}")
    node = KnowledgeNode(
        label=label,
        node_type=node_type,
        source_ref=ref,
        embedding=embedding or [],
    )
    node.scores.confidence = confidence
    return node
