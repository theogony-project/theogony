"""Source-anchor entity creation per MESH_SUBSTRATE.md §"Source-anchor entities".

Creates Tier-1+ consolidated nodes flagged with ``is_source_anchor = True``.
The description follows the stable format: ``{type}: {title} ({anchor})``.
"""

from __future__ import annotations

from datetime import UTC, datetime


def build_source_anchor_description(*, source_type: str, title: str, anchor: str) -> str:
    """Return the stable description format ``{type}: {title} ({anchor})``.

    Examples:
        - ``build_source_anchor_description(source_type="Wikipedia article",
          title="Thomas Addison", anchor="https://en.wikipedia.org/wiki/Thomas_Addison")``
          → ``"Wikipedia article: Thomas Addison (https://en.wikipedia.org/wiki/Thomas_Addison)"``

        - ``build_source_anchor_description(source_type="Book",
          title="The History of Endocrinology, by John Smith",
          anchor="ISBN:978-0-12-345678-9")``
          → ``"Book: The History of Endocrinology, by John Smith (ISBN:978-0-12-345678-9)"``
    """
    return f"{source_type}: {title} ({anchor})"


def make_source_anchor_node(
    *,
    source_type: str,
    title: str,
    anchor: str,
    semantic_dim: int = 384,
    frame_dim: int = 64,
) -> dict:  # returns dict for manual creation (avoids circular import)
    """Return a dict that can be used to construct a ConsolidatedNode.

    This is a helper so calling code can set the ULID and any extra fields.
    """

    now = datetime.now(UTC)
    description = build_source_anchor_description(
        source_type=source_type, title=title, anchor=anchor
    )

    return {
        "born_at": now,
        "last_fired_at": now,
        "consolidation_tier": 1,
        "is_source_anchor": True,
        "source_url": anchor,
        "semantic_vector": [0.0] * semantic_dim,
        "frame_vector": [0.0] * frame_dim,
        "description": description,
        "tags": [source_type.lower()],
    }
