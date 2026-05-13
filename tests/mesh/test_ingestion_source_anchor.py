"""Source-anchor entity creation — correct description format."""

from __future__ import annotations

from theogony.mesh.ingestion.source_anchor import (
    build_source_anchor_description,
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
