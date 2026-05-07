"""
Hierarchical multi-pass topology extraction for one text chunk.

Flow: MACRO partition (full chunk) → recursive SUBDIVIDE passes on each span until
``leaf_char_max`` (default 100) or ``max_depth`` is reached. Vertical parent links
use ``ABSTRACTION_OF`` (granular child → broader parent).
"""

from __future__ import annotations

from theogony.core.model import KnowledgeEdge, KnowledgeNode, SourceRef
from theogony.extraction.topology_parser import TopologyParser


def _invalid_offset(x: object) -> bool:
    if x is None:
        return True
    if isinstance(x, bool):
        return True
    if isinstance(x, (int, float)):
        return int(x) < 0
    return True


def normalize_span_within_text(
    char_start: object,
    char_end: object,
    text_len: int,
) -> tuple[int, int]:
    """Map optional LLM offsets to a valid half-open ``[a, b)`` span within ``text_len``."""
    if text_len <= 0:
        return 0, 0
    if _invalid_offset(char_start) or _invalid_offset(char_end):
        return 0, text_len
    assert isinstance(char_start, (int, float))
    assert isinstance(char_end, (int, float))
    a, b = int(char_start), int(char_end)
    a = max(0, min(a, text_len))
    b = max(0, min(b, text_len))
    if a >= b:
        return 0, text_len
    return a, b


async def _drill_subdivide(
    parser: TopologyParser,
    parent_id: str,
    chunk_full: str,
    abs_start: int,
    abs_end: int,
    source_ref: SourceRef,
    extractor_run_id: str,
    *,
    leaf_char_max: int,
    max_depth: int,
    depth: int,
) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
    slice_text = chunk_full[abs_start:abs_end]
    slen = len(slice_text)
    if slen <= leaf_char_max or depth >= max_depth:
        return [], []

    child_nodes, child_edges = await parser.parse_subdivide_slice(
        slice_text,
        source_ref,
        extractor_run_id,
    )

    adjusted: list[KnowledgeNode] = []
    for n in child_nodes:
        cs, ce = n.properties.get("char_start"), n.properties.get("char_end")
        ca, cb = normalize_span_within_text(cs, ce, slen)
        abs_a = abs_start + ca
        abs_b = abs_start + cb
        new_props = {**n.properties, "char_start": abs_a, "char_end": abs_b}
        adjusted.append(n.model_copy(update={"properties": new_props}))

    vert_edges = [
        KnowledgeEdge(
            source_id=cn.id,
            target_id=parent_id,
            relation_type="ABSTRACTION_OF",
            weight=0.72,
            source_ref=source_ref,
            properties={
                "extractor_run_id": extractor_run_id,
                "hierarchy_pass": "vertical_abstraction",
            },
        )
        for cn in adjusted
    ]

    all_nodes = list(adjusted)
    all_edges: list[KnowledgeEdge] = list(child_edges) + vert_edges

    for cn in adjusted:
        a0 = cn.properties.get("char_start")
        a1 = cn.properties.get("char_end")
        if a0 is None or a1 is None:
            continue
        span_a, span_b = int(a0), int(a1)
        if span_b - span_a <= leaf_char_max:
            continue
        # Degenerate: same span as parent → would recurse without progress.
        if span_a == abs_start and span_b == abs_end:
            continue

        sn, se = await _drill_subdivide(
            parser,
            cn.id,
            chunk_full,
            span_a,
            span_b,
            source_ref,
            extractor_run_id,
            leaf_char_max=leaf_char_max,
            max_depth=max_depth,
            depth=depth + 1,
        )
        all_nodes.extend(sn)
        all_edges.extend(se)

    return all_nodes, all_edges


async def extract_chunk_hierarchical(
    parser: TopologyParser,
    text_chunk: str,
    source_ref: SourceRef,
    extractor_run_id: str,
    *,
    leaf_char_max: int = 100,
    max_depth: int = 20,
) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
    """
    MACRO partition of ``text_chunk``, then recursive subdivide until spans are
    at most ``leaf_char_max`` characters (or ``max_depth`` subdivides).
    """
    macro_nodes, macro_edges = await parser.parse_macro_partition(
        text_chunk,
        source_ref,
        extractor_run_id,
    )

    all_nodes: list[KnowledgeNode] = list(macro_nodes)
    all_edges: list[KnowledgeEdge] = list(macro_edges)

    n = len(text_chunk)
    for m in macro_nodes:
        cs, ce = m.properties.get("char_start"), m.properties.get("char_end")
        a0, a1 = normalize_span_within_text(cs, ce, n)
        if a1 - a0 <= leaf_char_max:
            continue

        sn, se = await _drill_subdivide(
            parser,
            m.id,
            text_chunk,
            a0,
            a1,
            source_ref,
            extractor_run_id,
            leaf_char_max=leaf_char_max,
            max_depth=max_depth,
            depth=0,
        )
        all_nodes.extend(sn)
        all_edges.extend(se)

    return all_nodes, all_edges
