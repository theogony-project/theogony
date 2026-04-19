"""Unit tests for the fixed relation-type vocabulary (Plan §3.3)."""

from __future__ import annotations

import pytest

from theogony.extraction.relation_types import (
    RELATION_TYPE_TO_WIKIDATA,
    RELATION_TYPES,
    RELATION_TYPES_LIST,
    RelationType,
    is_known_relation_type,
    normalise_relation_type,
)


class TestVocabularyShape:
    def test_relation_types_is_non_empty_frozenset(self) -> None:
        assert isinstance(RELATION_TYPES, frozenset)
        assert len(RELATION_TYPES) >= 15  # Plan §3.3 calls for ~20

    def test_relation_types_includes_plan_examples(self) -> None:
        # Plan §3.3 lists these explicitly — they must remain stable.
        plan_required = (
            "LOCATED_IN",
            "TRAVELED_TO",
            "MET",
            "BORN_IN",
            "MEMBER_OF",
            "INFLUENCED_BY",
        )
        for required in plan_required:
            assert required in RELATION_TYPES, f"plan-required type missing: {required}"

    def test_relation_types_includes_other_bucket(self) -> None:
        # Plan §3.3 explicitly: "plus a free-text OTHER bucket
        # flagged for review."
        assert "OTHER" in RELATION_TYPES

    def test_list_form_has_same_members_as_frozenset(self) -> None:
        # The list exists for prompt-assembly determinism; the contents
        # must always match the frozenset.
        assert set(RELATION_TYPES_LIST) == RELATION_TYPES
        assert len(RELATION_TYPES_LIST) == len(RELATION_TYPES)

    def test_enum_values_match_strings(self) -> None:
        for enum_member in RelationType:
            assert enum_member.value == enum_member.name


class TestWikidataMapping:
    def test_mapping_contains_known_relations(self) -> None:
        # Sanity: a few well-known mappings stay stable.
        assert RELATION_TYPE_TO_WIKIDATA["LOCATED_IN"] == "P131"
        assert RELATION_TYPE_TO_WIKIDATA["BORN_IN"] == "P19"
        assert RELATION_TYPE_TO_WIKIDATA["DIED_IN"] == "P20"
        assert RELATION_TYPE_TO_WIKIDATA["AUTHOR_OF"] == "P50"

    def test_mapping_keys_are_subset_of_vocabulary(self) -> None:
        # No phantom mappings — every mapped key must be a real type.
        for key in RELATION_TYPE_TO_WIKIDATA:
            assert key in RELATION_TYPES, f"unmapped relation type: {key}"

    def test_mapping_values_match_p_id_pattern(self) -> None:
        for value in RELATION_TYPE_TO_WIKIDATA.values():
            assert value.startswith("P") and value[1:].isdigit(), (
                f"invalid Wikidata P-ID format: {value}"
            )

    def test_other_has_no_wikidata_mapping(self) -> None:
        # The free-text bucket has no canonical Wikidata equivalent
        # by construction.
        assert "OTHER" not in RELATION_TYPE_TO_WIKIDATA


class TestIsKnownRelationType:
    @pytest.mark.parametrize("value", ["LOCATED_IN", "TRAVELED_TO", "MET", "BORN_IN", "OTHER"])
    def test_known_returns_true(self, value: str) -> None:
        assert is_known_relation_type(value) is True

    @pytest.mark.parametrize("value", ["", "located_in", "Traveled To", "MARRIED", "X"])
    def test_unknown_returns_false(self, value: str) -> None:
        # Case-sensitivity is intentional — the vocabulary is uppercase.
        # Mixed-case / unknown / empty all return False; callers should
        # use ``normalise_relation_type`` to coerce best-effort inputs.
        assert is_known_relation_type(value) is False


class TestNormaliseRelationType:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("LOCATED_IN", "LOCATED_IN"),
            ("located_in", "LOCATED_IN"),
            ("  located_in  ", "LOCATED_IN"),
            ("traveled to", "TRAVELED_TO"),
            ("born-in", "BORN_IN"),
            ("Member of", "MEMBER_OF"),
        ],
    )
    def test_normalises_case_whitespace_and_separators(self, raw: str, expected: str) -> None:
        assert normalise_relation_type(raw) == expected

    @pytest.mark.parametrize("raw", ["", "MARRIED", "ATTACKED", "x", "   "])
    def test_unknown_falls_back_to_other(self, raw: str) -> None:
        # Plan §3.3: unknown types are preserved as OTHER and flagged
        # for review. They are not dropped — that would lose signal.
        assert normalise_relation_type(raw) == "OTHER"

    def test_already_canonical_unchanged(self) -> None:
        for canonical in RELATION_TYPES:
            assert normalise_relation_type(canonical) == canonical
