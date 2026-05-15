"""Source-anchor helpers for text- and paragraph-level hierarchy."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.schemas import ConsolidatedNode


def build_source_anchor_description(*, source_type: str, title: str, anchor: str) -> str:
    return f"{source_type}: {title} ({anchor})"


def build_paragraph_anchor_title(*, title: str, paragraph_number: int) -> str:
    return f"{title} paragraph {paragraph_number}"


def build_source_anchor_node(
    *,
    source_type: str,
    title: str,
    anchor: str,
    semantic_vector: list[float],
    frame_vector: list[float],
    description_vector: list[float] | None,
    tags: list[str],
) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        is_source_anchor=True,
        source_url=anchor,
        semantic_vector=semantic_vector,
        frame_vector=frame_vector,
        description_vector=description_vector,
        description=build_source_anchor_description(
            source_type=source_type,
            title=title,
            anchor=anchor,
        ),
        tags=tags,
    )
