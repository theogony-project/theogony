"""Source-anchor entity creation — correct description format."""

from __future__ import annotations

from theogony.mesh.ingestion.source_anchor import (
    build_paragraph_anchor_title,
    build_source_anchor_description,
    build_source_anchor_node,
)


def test_source_anchor_description_wikipedia() -> None:
    desc = build_source_anchor_description(
        source_type="Wikipedia article",
        title="Thomas Addison",
        anchor="https://en.wikipedia.org/wiki/Thomas_Addison",
    )
    assert (
        desc == "Wikipedia article: Thomas Addison (https://en.wikipedia.org/wiki/Thomas_Addison)"
    )


def test_source_anchor_description_book() -> None:
    desc = build_source_anchor_description(
        source_type="Book",
        title="The History of Endocrinology, by John Smith",
        anchor="ISBN:978-0-12-345678-9",
    )
    assert desc == "Book: The History of Endocrinology, by John Smith (ISBN:978-0-12-345678-9)"


def test_source_anchor_description_web() -> None:
    desc = build_source_anchor_description(
        source_type="Web page",
        title="Pantheon Project",
        anchor="https://example.org/about",
    )
    assert desc == "Web page: Pantheon Project (https://example.org/about)"


def test_paragraph_anchor_title() -> None:
    assert (
        build_paragraph_anchor_title(title="Trans-Himalaya", paragraph_number=3)
        == "Trans-Himalaya paragraph 3"
    )


def test_source_anchor_node_marks_anchor() -> None:
    node = build_source_anchor_node(
        source_type="Book",
        title="Trans-Himalaya",
        anchor="gutenberg_43497",
        semantic_vector=[0.1] * 8,
        frame_vector=[0.2] * 4,
        description_vector=[0.3] * 8,
        tags=["gutenberg", "source_anchor", "text"],
    )
    assert node.is_source_anchor is True
    assert node.source_url == "gutenberg_43497"
    assert node.description_vector == [0.3] * 8
