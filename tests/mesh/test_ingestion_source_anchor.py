"""Source-anchor entity creation — description format per MESH_SUBSTRATE.md."""

from __future__ import annotations

from theogony.mesh.ingestion.source_anchor import build_source_anchor_description


def test_wikipedia_article() -> None:
    desc = build_source_anchor_description(
        source_type="Wikipedia article",
        title="Thomas Addison",
        anchor="https://en.wikipedia.org/wiki/Thomas_Addison",
    )
    assert desc == "Wikipedia article: Thomas Addison (https://en.wikipedia.org/wiki/Thomas_Addison)"


def test_gutenberg_book() -> None:
    desc = build_source_anchor_description(
        source_type="Book",
        title="Trans-Himalaya, by Sven Hedin",
        anchor="https://www.gutenberg.org/ebooks/43497",
    )
    assert desc == "Book: Trans-Himalaya, by Sven Hedin (https://www.gutenberg.org/ebooks/43497)"


def test_web_page() -> None:
    desc = build_source_anchor_description(
        source_type="Web page",
        title="Pantheon Project",
        anchor="https://example.org/about",
    )
    assert desc == "Web page: Pantheon Project (https://example.org/about)"
