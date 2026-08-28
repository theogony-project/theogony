"""Scoring for the answer-quality arms.

The LLM half cannot be unit-tested cheaply; what can and must be pinned is the
scoring, because every claim the experiment makes is a *difference between arms*
and a scorer that treats them differently would manufacture one.
"""

from __future__ import annotations

from theogony.mesh.eval.corpus_answers import (
    ARMS,
    AnswerResult,
    _score,
    summarise_answers,
)


def test_a_name_is_found_however_the_answer_is_punctuated() -> None:
    found, missed = _score("Hestia, Demeter, Hera, Hades and Zeus.", ["Hestia", "Zeus", "Cronus"])
    assert found == ["Hestia", "Zeus"]
    assert missed == ["Cronus"]


def test_a_name_is_not_found_inside_a_longer_word() -> None:
    """`_normalise` pads with spaces so `Eos` does not match `Eosphorus`.

    Without this the scorer inflates every arm equally — but it inflates the
    arm with the longest answers most, which is exactly the confound the
    experiment is built to avoid.
    """
    found, _ = _score("Eosphorus", ["Eos"])
    assert found == []
    found, _ = _score("Eos and Eosphorus", ["Eos"])
    assert found == ["Eos"]


def test_scoring_ignores_case_and_footnote_digits() -> None:
    """The corpus writes "Hestia 1618" and that reaches node names."""
    found, _ = _score("HESTIA 1618, demeter", ["Hestia", "Demeter"])
    assert found == ["Hestia", "Demeter"]


def test_an_arm_that_says_nothing_scores_nothing() -> None:
    result = AnswerResult(
        id="q",
        arm="constellation",
        kind="genealogical",
        question="?",
        expected=["A", "B"],
        answer="UNKNOWN",
        said_unknown=True,
    )
    assert result.recall == 0.0
    assert not result.complete


def test_the_summary_reports_each_arm_apart() -> None:
    """One number over all arms would be meaningless — the arms are the experiment."""
    rows = [
        AnswerResult(
            id="q1",
            arm="closed_book",
            kind="g",
            question="?",
            expected=["A", "B"],
            answer="A",
            found=["A"],
            missed=["B"],
        ),
        AnswerResult(
            id="q1",
            arm="constellation",
            kind="g",
            question="?",
            expected=["A", "B"],
            answer="A, B",
            found=["A", "B"],
        ),
    ]
    summary = summarise_answers(rows)
    assert set(summary) == {"closed_book", "constellation"}
    assert summary["closed_book"]["answer_recall"] == 0.5
    assert summary["constellation"]["answer_recall"] == 1.0
    assert summary["constellation"]["complete_answers"] == 1.0


def test_the_closed_book_arm_exists_and_is_first() -> None:
    """It is the control that makes the others readable, not an afterthought.

    The founding corpus is Hesiod and the model has read Hesiod: measured, it
    answers 50% of the gold set with no context at all. A constellation arm
    reported without it would be uninterpretable.
    """
    assert ARMS[0] == "closed_book"
    assert set(ARMS) == {"closed_book", "vector_only", "constellation"}
