from __future__ import annotations

from theogony.mesh.seeds.wikidata5m.relations import resolve_relation_mapping


def test_known_pid_maps_to_curated_relation() -> None:
    mapping = resolve_relation_mapping("P31", ["instance of"])

    assert mapping.mapped is True
    assert mapping.relation_kind == "hierarchy"
    assert mapping.relation_descriptor == "instance_of"


def test_unknown_pid_falls_back_cleanly() -> None:
    mapping = resolve_relation_mapping("P999999", ["made up alias"])

    assert mapping.mapped is False
    assert mapping.relation_kind == "semantic"
    assert mapping.relation_descriptor == "made_up_alias"
