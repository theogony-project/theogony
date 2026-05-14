"""Source-anchor entity creation — description format helper only.

Per MESH_SUBSTRATE.md §"Source-anchor entities":
    ``{type}: {title} ({anchor})``
"""

from __future__ import annotations


def build_source_anchor_description(*, source_type: str, title: str, anchor: str) -> str:
    """Stable description format.

    Examples:
        ``"Wikipedia article: Thomas Addison (https://en.wikipedia.org/wiki/Thomas_Addison)"``
        ``"Book: Trans-Himalaya, by Sven Hedin (https://www.gutenberg.org/ebooks/43497)"``
    """
    return f"{source_type}: {title} ({anchor})"
