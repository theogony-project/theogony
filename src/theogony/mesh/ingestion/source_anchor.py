"""Source-anchor entity description format per MESH_SUBSTRATE.md."""


def build_source_anchor_description(*, source_type: str, title: str, anchor: str) -> str:
    return f"{source_type}: {title} ({anchor})"
