"""The answer key must be found, or the question dropped — never invented.

PopQA has no `answer` field: the gold lives in `obj`, with synonyms in
`possible_answers` and `o_aliases`. Reading `row["answer"]` and stringifying the
result produced the literal string `"None"` as the gold for all 1,000 of its
questions, and a full end-to-end run scored **0.0% in every arm including
closed-book** before anyone noticed.

It went unnoticed because the recall benchmark next door reads only `gold_idxs`
and never touches the answer at all — the field was carried for years without a
consumer (PHX-1089).
"""

from __future__ import annotations

from theogony.mesh.eval.qa_datasets import _answer_key


def test_the_plain_answer_field_is_used_when_present() -> None:
    assert _answer_key({"answer": "Berlin"}) == ("Berlin", [])


def test_a_list_valued_answer_takes_its_first_element() -> None:
    assert _answer_key({"answer": ["Berlin", "Berlin, Germany"]})[0] == "Berlin"


def test_popqa_shape_resolves_to_obj_plus_its_aliases() -> None:
    answer, aliases = _answer_key(
        {
            "obj": "politician",
            "possible_answers": '["politician","political leader"]',
            "o_aliases": '["pol","polit."]',
        }
    )
    assert answer == "politician"
    assert "political leader" in aliases
    assert "pol" in aliases
    assert "politician" not in aliases, "the primary must not repeat among the aliases"


def test_a_row_with_no_answer_anywhere_returns_empty_not_the_string_None() -> None:
    """The defect itself. `str(None)` is `"None"`, and `"None"` scores zero forever."""
    assert _answer_key({"question": "Who?"}) == ("", [])
    assert _answer_key({"answer": None}) == ("", [])
    assert _answer_key({"answer": []}) == ("", [])


def test_aliases_alone_are_enough_to_score_a_question() -> None:
    answer, aliases = _answer_key({"possible_answers": ["Columbia", "Columbia, Missouri"]})
    assert answer == "Columbia"
    assert aliases == ["Columbia, Missouri"]
