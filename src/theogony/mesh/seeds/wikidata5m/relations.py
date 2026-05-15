"""Hand-curated P-ID registry with doctrine-safe fallbacks."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RelationMapping:
    relation_kind: str
    relation_descriptor: str
    mapped: bool


_KNOWN_RELATIONS: dict[str, tuple[str, str]] = {
    "P17": ("attribute", "country"),
    "P19": ("attribute", "place_of_birth"),
    "P20": ("attribute", "place_of_death"),
    "P21": ("attribute", "sex_or_gender"),
    "P26": ("attribute", "spouse"),
    "P27": ("attribute", "country_of_citizenship"),
    "P31": ("hierarchy", "instance_of"),
    "P39": ("attribute", "position_held"),
    "P50": ("attribution", "author"),
    "P54": ("attribute", "member_of_sports_team"),
    "P57": ("attribution", "director"),
    "P69": ("attribute", "educated_at"),
    "P101": ("attribute", "field_of_work"),
    "P106": ("attribute", "occupation"),
    "P108": ("attribute", "employer"),
    "P131": ("hierarchy", "located_in_administrative_territorial_entity"),
    "P166": ("attribute", "award_received"),
    "P170": ("attribution", "creator"),
    "P279": ("hierarchy", "subclass_of"),
    "P355": ("semantic", "subsidiary"),
    "P361": ("hierarchy", "part_of"),
    "P407": ("attribute", "language_of_work_or_name"),
    "P463": ("attribute", "member_of"),
    "P495": ("attribute", "country_of_origin"),
    "P527": ("hierarchy", "has_part"),
    "P569": ("temporal", "date_of_birth"),
    "P570": ("temporal", "date_of_death"),
    "P577": ("temporal", "publication_date"),
    "P580": ("temporal", "start_time"),
    "P582": ("temporal", "end_time"),
    "P585": ("temporal", "point_in_time"),
    "P641": ("attribute", "sport"),
    "P710": ("attribution", "participant"),
    "P737": ("causal", "influenced_by"),
    "P800": ("attribute", "notable_work"),
    "P1026": ("attribute", "doctoral_advisor"),
    "P1412": ("attribute", "languages_spoken"),
    "P1598": ("attribute", "consecrator"),
    "P161": ("attribute", "cast_member"),
}


def _normalise_descriptor(value: str) -> str:
    raw = value.strip().lower()
    raw = raw.replace("-", " ")
    raw = re.sub(r"[^a-z0-9\s]", "", raw)
    raw = re.sub(r"\s+", "_", raw)
    return raw or "semantic_relation"


def resolve_relation_mapping(pid: str, aliases: list[str]) -> RelationMapping:
    known = _KNOWN_RELATIONS.get(pid)
    if known is not None:
        relation_kind, relation_descriptor = known
        return RelationMapping(
            relation_kind=relation_kind,
            relation_descriptor=relation_descriptor,
            mapped=True,
        )
    alias = aliases[0] if aliases else pid
    return RelationMapping(
        relation_kind="semantic",
        relation_descriptor=_normalise_descriptor(alias),
        mapped=False,
    )
