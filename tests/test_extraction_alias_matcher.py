"""Unit tests for the alias matcher (Plan §3.4 Stage 2)."""

from __future__ import annotations

import pytest

from theogony.extraction.alias_matcher import (
    AliasMatchStrength,
    best_match,
    fully_normalise,
    is_match,
)


class TestExactMatch:
    def test_byte_identical_returns_exact(self) -> None:
        assert best_match("Aufschnaiter", ["Aufschnaiter"]) == AliasMatchStrength.EXACT

    def test_exact_short_circuits_other_levels(self) -> None:
        # When the mention is already exact-equal, the matcher must
        # return immediately — no point lowering to CASE just because
        # a CASE-equal alias also happens to be in the list.
        assert (
            best_match("Aufschnaiter", ["aufschnaiter", "Aufschnaiter"]) == AliasMatchStrength.EXACT
        )


class TestCaseFold:
    def test_uppercase_matches_lowercase_at_case_level(self) -> None:
        assert best_match("AUFSCHNAITER", ["Aufschnaiter"]) == AliasMatchStrength.CASE

    def test_lowercase_matches_titlecase_at_case_level(self) -> None:
        assert best_match("aufschnaiter", ["Aufschnaiter"]) == AliasMatchStrength.CASE

    def test_german_eszett_case_folds_to_ss(self) -> None:
        # Per Unicode, "ß".casefold() == "ss"; "Straße" and "Strasse"
        # collapse to the same casefold form. Real Wikidata aliases
        # include both spellings of German place names.
        assert best_match("Strasse", ["Straße"]) == AliasMatchStrength.CASE


class TestWhitespaceCollapse:
    def test_double_space_collapses(self) -> None:
        assert best_match("Uttar  Kashi", ["Uttar Kashi"]) == AliasMatchStrength.WHITESPACE

    def test_leading_trailing_whitespace_collapses(self) -> None:
        assert best_match("  Tibet  ", ["Tibet"]) == AliasMatchStrength.WHITESPACE

    def test_tab_treated_as_whitespace(self) -> None:
        # str.split() splits on any Unicode whitespace including \t.
        assert best_match("Sven\tHedin", ["Sven Hedin"]) == AliasMatchStrength.WHITESPACE


class TestNormalised:
    def test_diacritic_strip_matches(self) -> None:
        # NFKD-decompose + drop Mn category turns "Kämpa" into "Kampa".
        # Plan §3.4 Stage 2 lists this exact case ("Kämpa" ↔ "Khampa"
        # — but Khampa is a separate transliteration; the basic
        # diacritic case is the cleaner unit test).
        assert best_match("Kämpa", ["Kampa"]) == AliasMatchStrength.NORMALISED

    def test_uttar_kashi_vs_uttarkashi_does_not_match(self) -> None:
        # Whitespace-collapse alone makes "Uttar Kashi" → "Uttar Kashi"
        # (already collapsed) and "Uttarkashi" → "Uttarkashi". They
        # are different strings with different characters; only a
        # space-removal step (which we deliberately do NOT do, because
        # it would turn "York shire" into "Yorkshire") could match
        # them. The plan acknowledges this case as the kind of fuzzy
        # match LLM disambiguation should handle, not the regex pass.
        assert best_match("Uttar Kashi", ["Uttarkashi"]) == AliasMatchStrength.NONE

    def test_combining_full_path_matches(self) -> None:
        # "Kämpa" with combining diacritic + uppercase + extra spaces
        # all collapse to the same fully-normalised form as "kampa".
        assert best_match("  KÄMPA  ", ["kampa"]) == AliasMatchStrength.NORMALISED

    def test_ligature_decomposes_via_casefold(self) -> None:
        # Surprise: "ﬁ" (U+FB01 LATIN SMALL LIGATURE FI) casefolds to
        # "fi" without needing NFKD — Unicode case-folding incorporates
        # compatibility decomposition for characters of category Lo
        # with NFKC_Casefold mappings. So this lands at CASE level,
        # not NORMALISED. The matcher remains correct: it returns the
        # *strongest* level achieved, and CASE is stronger than
        # NORMALISED. Documented here as a "guard the assumption"
        # case so a future contributor who edits the ladder knows
        # this interaction exists.
        assert best_match("ﬁnger", ["finger"]) == AliasMatchStrength.CASE


class TestNoMatch:
    def test_completely_different_strings_return_none(self) -> None:
        assert best_match("Tibet", ["China"]) == AliasMatchStrength.NONE

    def test_empty_alias_set_returns_none(self) -> None:
        assert best_match("Tibet", []) == AliasMatchStrength.NONE

    def test_substring_alone_does_not_match(self) -> None:
        # We do not want "Tibet" to match "Tibet Autonomous Region"
        # at any normalisation level — substring containment is a
        # different operation (and a different mistake to make).
        assert best_match("Tibet", ["Tibet Autonomous Region"]) == AliasMatchStrength.NONE


class TestBestAcrossSet:
    def test_returns_strongest_when_multiple_levels_present(self) -> None:
        # Aliases include a CASE-only match and a NORMALISED-only
        # match. The matcher must return CASE (the higher one).
        result = best_match("Aufschnaiter", ["aufschnaiter", "AÜFSCHNAITER"])
        assert result == AliasMatchStrength.CASE

    def test_iteration_order_does_not_change_result(self) -> None:
        # Order-independence: the matcher is order-stable. We verify
        # by reversing.
        forward = best_match("Aufschnaiter", ["aufschnaiter", "AÜFSCHNAITER"])
        backward = best_match("Aufschnaiter", ["AÜFSCHNAITER", "aufschnaiter"])
        assert forward == backward

    def test_exact_in_middle_short_circuits(self) -> None:
        # An EXACT hit anywhere in the iteration must short-circuit;
        # no point continuing through millions of aliases (in the
        # extreme case) once we have the strongest possible answer.
        result = best_match(
            "Tibet",
            ["something", "Tibet", "another"],  # EXACT in middle
        )
        assert result == AliasMatchStrength.EXACT


class TestFullyNormalise:
    def test_idempotent(self) -> None:
        # Applying twice must equal applying once — guards against
        # someone "improving" the function and breaking the property.
        original = "  KÄMPA  "
        once = fully_normalise(original)
        twice = fully_normalise(once)
        assert once == twice

    def test_strips_diacritic_lowercases_collapses(self) -> None:
        assert fully_normalise("  KÄMPA  ") == "kampa"

    def test_empty_string_stays_empty(self) -> None:
        assert fully_normalise("") == ""

    def test_pure_whitespace_collapses_to_empty(self) -> None:
        assert fully_normalise("   \t  \n  ") == ""


class TestIsMatch:
    @pytest.mark.parametrize(
        "mention, aliases, expected",
        [
            ("Tibet", ["Tibet"], True),
            ("TIBET", ["Tibet"], True),
            ("Kämpa", ["Kampa"], True),
            ("Tibet", ["China"], False),
            ("Tibet", [], False),
        ],
    )
    def test_is_match_summarises_to_bool(
        self, mention: str, aliases: list[str], expected: bool
    ) -> None:
        assert is_match(mention, aliases) is expected
