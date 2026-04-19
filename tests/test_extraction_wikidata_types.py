"""Unit tests for the spaCy NER → Wikidata type mapping (Plan §3.4 Stage 3)."""

from __future__ import annotations

import pytest

from theogony.core.model import NodeType
from theogony.extraction.wikidata_types import (
    EVENT,
    FAC,
    GPE,
    LANGUAGE,
    LAW,
    LOC,
    NORP,
    ORG,
    PERSON,
    PRODUCT,
    WORK_OF_ART,
    acceptable_wikidata_types,
    is_resolvable,
    node_type_for_ner_label,
)


class TestPlanContractTypes:
    """The Q-IDs Plan §3.4 Stage 3 lists verbatim must remain accepted."""

    def test_person_accepts_q5(self) -> None:
        assert "Q5" in PERSON

    def test_gpe_accepts_plan_quartet(self) -> None:
        for required in ("Q486972", "Q515", "Q6256", "Q3024240"):
            assert required in GPE, f"plan-required Q-ID missing: {required}"

    def test_org_accepts_q43229(self) -> None:
        assert "Q43229" in ORG

    def test_loc_includes_river_lake_mountain(self) -> None:
        for q in ("Q47521", "Q23397", "Q8502"):
            assert q in LOC

    def test_work_of_art_includes_book(self) -> None:
        assert "Q571" in WORK_OF_ART

    def test_norp_includes_ethnic_and_religion(self) -> None:
        assert "Q41710" in NORP
        assert "Q9174" in NORP

    def test_language_is_q34770(self) -> None:
        assert frozenset({"Q34770"}) == LANGUAGE

    def test_all_label_constants_are_frozensets(self) -> None:
        # Catches the "I changed PERSON to a set literal and broke
        # callers that called .add()" failure mode early.
        for fs in (PERSON, GPE, LOC, ORG, FAC, EVENT, WORK_OF_ART, NORP, LANGUAGE, LAW, PRODUCT):
            assert isinstance(fs, frozenset)


class TestResolvability:
    """``is_resolvable`` separates entities from literals."""

    @pytest.mark.parametrize(
        "label",
        ["PERSON", "GPE", "LOC", "ORG", "FAC", "EVENT", "WORK_OF_ART", "NORP", "LANGUAGE"],
    )
    def test_entity_labels_are_resolvable(self, label: str) -> None:
        assert is_resolvable(label) is True

    @pytest.mark.parametrize(
        "label", ["DATE", "TIME", "MONEY", "PERCENT", "QUANTITY", "ORDINAL", "CARDINAL"]
    )
    def test_literal_labels_are_not_resolvable(self, label: str) -> None:
        assert is_resolvable(label) is False

    def test_unknown_label_is_not_resolvable(self) -> None:
        # Conservative: unknown spaCy labels never silently enter the
        # Wikidata round-trip path. Better to mint an AKA-only node
        # than to issue an HTTP request whose response we cannot type.
        assert is_resolvable("MADE_UP_LABEL") is False

    def test_product_and_law_are_resolvable_with_empty_filter(self) -> None:
        # PRODUCT and LAW go through resolve() but accept any surviving
        # candidate (no type filter). The empty frozenset is the signal.
        assert is_resolvable("PRODUCT") is True
        assert is_resolvable("LAW") is True
        assert acceptable_wikidata_types("PRODUCT") == frozenset()
        assert acceptable_wikidata_types("LAW") == frozenset()


class TestAcceptableTypes:
    def test_returns_frozenset(self) -> None:
        # Frozensets are hashable, immutable, set-typed — the right
        # container for "membership test against a small fixed set".
        assert isinstance(acceptable_wikidata_types("PERSON"), frozenset)

    def test_unknown_label_raises_keyerror(self) -> None:
        # Callers must gate on is_resolvable() first; KeyError makes
        # the contract explicit rather than silently returning empty.
        with pytest.raises(KeyError):
            acceptable_wikidata_types("MADE_UP_LABEL")

    def test_person_has_only_q5(self) -> None:
        # Q5 is the single canonical instance-of for any human. We
        # deliberately don't accept Q215627 (person — broader,
        # includes fictional characters) at this stage; that
        # distinction matters and a Tier-3 alias match plus Q5 is
        # the right precision floor.
        assert acceptable_wikidata_types("PERSON") == frozenset({"Q5"})

    def test_gpe_does_not_overlap_with_loc(self) -> None:
        # Travel-history disambiguation depends on these being
        # non-overlapping: a "GPE" mention should not slip through to
        # a Q47521 (river) candidate via overlap.
        assert acceptable_wikidata_types("GPE") & acceptable_wikidata_types("LOC") == frozenset()


class TestNodeTypeMapping:
    @pytest.mark.parametrize(
        "ner_label, expected",
        [
            ("PERSON", NodeType.PERSON),
            ("GPE", NodeType.PLACE),
            ("LOC", NodeType.PLACE),
            ("FAC", NodeType.PLACE),
            ("ORG", NodeType.ORGANIZATION),
            ("EVENT", NodeType.EVENT),
            ("WORK_OF_ART", NodeType.WORK),
            ("DATE", NodeType.TIME),
            ("TIME", NodeType.TIME),
            ("MONEY", NodeType.QUANTITY),
            ("CARDINAL", NodeType.QUANTITY),
        ],
    )
    def test_known_labels_map_to_expected_node_type(
        self, ner_label: str, expected: NodeType
    ) -> None:
        assert node_type_for_ner_label(ner_label) == expected

    def test_unknown_label_falls_back_to_other(self) -> None:
        # The mention is already extracted; refusing to mint a node
        # for an unknown label is worse than mistyping it as OTHER.
        assert node_type_for_ner_label("MADE_UP_LABEL") == NodeType.OTHER

    def test_norp_language_law_product_map_to_other(self) -> None:
        # These are entity-like but Theogony's NodeType enum doesn't
        # carry a "concept" finer than OTHER for them in Gen 1.
        # Keeping them as OTHER is the cheapest defensible choice;
        # PHX-deferred to revisit when a measurable downstream
        # consumer needs the distinction.
        for label in ("NORP", "LANGUAGE", "LAW", "PRODUCT"):
            assert node_type_for_ner_label(label) == NodeType.OTHER
