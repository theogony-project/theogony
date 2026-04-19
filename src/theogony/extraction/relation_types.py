"""
Fixed vocabulary of relation types for Gen 1 (Plan §3.3).

Plan §3.3 calls for "~20 hand-picked types relevant to travel/biography":
``LOCATED_IN``, ``TRAVELED_TO``, ``MET``, ``BORN_IN``, ``MEMBER_OF``,
``INFLUENCED_BY``, etc., plus a free-text ``OTHER`` bucket flagged for
review. The closed set keeps the LLM extraction prompt tight and the
JSON-Schema enum small enough that Gemini 2.5 Flash Lite reliably
honours it (Plan §3.3a "JSON-Schema quality is good enough for our
fixed-vocabulary use case").

Adding a new type:

1. Append to :data:`RELATION_TYPES` with a one-line docstring above
   the entry explaining the canonical English usage.
2. Update the system prompt in ``relations.py`` if the new type needs
   special handling (most additions do not).
3. The tests in ``test_extraction_relation_types.py`` will pick up
   the addition automatically; add a parametrised case if the new
   type has a non-obvious canonical phrasing.

Removing a type is harder — existing nodes / edges in the store may
reference it. Treat removal as a migration, not a code change.

Why hand-picked rather than Wikidata's full property list:

- Wikidata has ~10 000 properties; an enum that large defeats every
  benefit of a closed vocabulary.
- Most Wikidata properties are domain-specific (railway gauges,
  protein domains, …) and irrelevant to travel literature.
- Hand-picking forces us to define a cohesive shape — every type
  here is a plausible relation between two NER-extracted entities
  in narrative prose.

Mapping to Wikidata P-IDs is recorded in :data:`RELATION_TYPE_TO_WIKIDATA`
for future use (Plan §9.3 records both the curated type and the
Wikidata P-ID on each edge for cross-source convergence in Gen 2).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class RelationType(StrEnum):
    """The fixed vocabulary of relation types for Gen 1 extraction.

    Names follow the convention ``SUBJECT_VERB[_PREP]`` in the
    direction subject → object — e.g. ``BORN_IN`` reads as
    "subject was born in object". Reversal cases (``CHILD_OF`` vs
    ``PARENT_OF``) are deliberately not encoded both ways here; the
    extractor picks the more directly attested direction from the
    source.
    """

    LOCATED_IN = "LOCATED_IN"
    """X is located in Y. Default for static place-of relationships."""

    PART_OF = "PART_OF"
    """X is a part of Y. Use for whole-part decompositions
    (region of a country, chapter of a book)."""

    TRAVELED_TO = "TRAVELED_TO"
    """X traveled to Y. The signature relation for travel narratives."""

    TRAVELED_FROM = "TRAVELED_FROM"
    """X departed from / left Y. Counterpart to TRAVELED_TO."""

    REACHED = "REACHED"
    """X arrived at / reached Y. Slightly stronger than TRAVELED_TO —
    implies completion of journey to that destination."""

    MET = "MET"
    """X met / encountered Y (a person)."""

    BORN_IN = "BORN_IN"
    """X was born in / at Y."""

    DIED_IN = "DIED_IN"
    """X died in / at Y."""

    MEMBER_OF = "MEMBER_OF"
    """X is a member of (group, organisation, expedition) Y."""

    WORKS_FOR = "WORKS_FOR"
    """X works for / is employed by Y."""

    AUTHOR_OF = "AUTHOR_OF"
    """X wrote / authored Y. Use for books, articles, reports."""

    INFLUENCED_BY = "INFLUENCED_BY"
    """X was influenced by / inspired by Y."""

    NEAR = "NEAR"
    """X is near / close to Y. Spatial proximity, not containment."""

    DESCRIBED_BY = "DESCRIBED_BY"
    """X is described / characterised by Y. Narrator's framing."""

    RULED_BY = "RULED_BY"
    """X was ruled / governed by Y. Use for political authority."""

    ALLIED_WITH = "ALLIED_WITH"
    """X allied / cooperated with Y. Voluntary partnership."""

    OPPOSED_TO = "OPPOSED_TO"
    """X opposed / fought / was hostile to Y."""

    FOUNDED = "FOUNDED"
    """X founded / established Y."""

    CITED = "CITED"
    """X cited / referenced Y."""

    OTHER = "OTHER"
    """Free-text bucket for relations that the LLM identified but
    that do not fit any other type. Edges with this type SHOULD be
    flagged for human review (Plan §3.3) — they are valid signal but
    unverified shape."""


RELATION_TYPES: frozenset[str] = frozenset(t.value for t in RelationType)
"""Set form of the vocabulary, suitable for membership tests and
direct inclusion in JSON-Schema ``enum`` arrays."""


RELATION_TYPES_LIST: list[str] = [t.value for t in RelationType]
"""Insertion-ordered list, useful for prompt assembly when the LLM
benefits from a stable enumeration order."""


# Mapping to Wikidata P-IDs where there is a clean correspondence.
# Plan §9.3: edges may carry both a curated type and a Wikidata P-ID
# (e.g. ``relation_type="LOCATED_IN"``, ``properties["wikidata_p_id"]="P131"``)
# so cross-source convergence in Gen 2 has a structural anchor.
# Types without a clean Wikidata equivalent are absent from the dict
# (callers should treat absence as "no canonical Wikidata mapping").
RELATION_TYPE_TO_WIKIDATA: Final[dict[str, str]] = {
    RelationType.LOCATED_IN.value: "P131",  # located in administrative entity
    RelationType.PART_OF.value: "P361",
    RelationType.BORN_IN.value: "P19",  # place of birth
    RelationType.DIED_IN.value: "P20",  # place of death
    RelationType.MEMBER_OF.value: "P463",
    RelationType.WORKS_FOR.value: "P108",  # employer
    RelationType.AUTHOR_OF.value: "P50",  # author
    RelationType.INFLUENCED_BY.value: "P737",
    RelationType.RULED_BY.value: "P6",  # head of government — closest
    RelationType.FOUNDED.value: "P112",  # founder
    RelationType.CITED.value: "P2860",  # cites work
}


def is_known_relation_type(value: str) -> bool:
    """Cheap membership test against the fixed vocabulary.

    Returns False for empty strings, unknown types, or wrong case.
    Used by :class:`RelationExtractor` to drop relations whose
    ``relation_type`` field does not match the enum, mapping them
    to OTHER instead.
    """
    return value in RELATION_TYPES


def normalise_relation_type(value: str) -> str:
    """Map an LLM-supplied relation_type string to a canonical form.

    Handles the most common drift: case differences, surrounding
    whitespace, and underscore-vs-space confusion. Returns the
    canonical uppercase form when the input matches; otherwise
    returns ``"OTHER"`` so the relation is preserved but flagged.
    """
    if not value:
        return RelationType.OTHER.value
    candidate = value.strip().upper().replace(" ", "_").replace("-", "_")
    if candidate in RELATION_TYPES:
        return candidate
    return RelationType.OTHER.value


__all__ = [
    "RELATION_TYPES",
    "RELATION_TYPES_LIST",
    "RELATION_TYPE_TO_WIKIDATA",
    "RelationType",
    "is_known_relation_type",
    "normalise_relation_type",
]
