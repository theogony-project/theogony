"""SQuAD scoring for the HippoRAG answer benchmark.

These numbers are meant to sit beside published ones, so the metric has to be the
published metric rather than something similar. Exact match after SQuAD
normalisation (lowercase, strip articles and punctuation, collapse whitespace),
and token F1 for partial credit.

The founding-corpus experiment scored by substring containment of expected entity
names, which was right there — the gold was a set of names — and would be wrong
here, where the gold is one answer span and a verbose reply must not be rewarded
for containing it (PHX-1089).
"""

from __future__ import annotations

import asyncio

from theogony.mesh.eval.qa_answers import (
    ARMS,
    QAAnswerResult,
    _normalise,
    answer_dataset,
    build_context,
    exact_match,
    summarise_qa_answers,
    token_f1,
)
from theogony.mesh.eval.qa_retrieval import QAPassage, QAQuestion


def test_normalisation_follows_squad() -> None:
    assert _normalise("The Beatles.") == "beatles"
    assert _normalise("  A  Hard   Day's Night ") == "hard days night"
    assert _normalise("1963") == "1963"


def test_exact_match_ignores_articles_and_punctuation() -> None:
    assert exact_match("The Beatles", "Beatles") == 1.0
    assert exact_match("beatles.", "The Beatles") == 1.0
    assert exact_match("The Rolling Stones", "The Beatles") == 0.0


def test_a_verbose_answer_does_not_score_an_exact_match() -> None:
    """The founding experiment's substring rule would have given this full credit.

    Here the gold is one span, and "the answer is X" is not X.
    """
    assert exact_match("The answer is Beatles", "Beatles") == 0.0
    assert token_f1("The answer is Beatles", "Beatles") < 1.0
    assert token_f1("The answer is Beatles", "Beatles") > 0.0


def test_token_f1_gives_partial_credit() -> None:
    assert token_f1("John Fitzgerald Kennedy", "John F Kennedy") > 0.5
    assert token_f1("John Fitzgerald Kennedy", "John F Kennedy") < 1.0
    assert token_f1("Paris", "Paris") == 1.0
    assert token_f1("Paris", "London") == 0.0


def test_an_empty_answer_scores_zero_not_one() -> None:
    """A provider error returns "" — it must not read as agreement with an empty gold."""
    assert exact_match("", "Beatles") == 0.0
    assert token_f1("", "Beatles") == 0.0


def test_context_is_numbered_and_bounded() -> None:
    passages = [QAPassage(idx=i, title=f"T{i}", text=f"body {i}") for i in range(6)]
    context = build_context(passages, [3, 1, 4, 0, 5, 2], top_k=3)
    assert context.count("\n\n") == 2, "exactly three passages"
    assert context.startswith("[1] T3")
    assert "T2" not in context, "beyond top_k must be left out"


def test_an_out_of_range_index_is_skipped_rather_than_fatal() -> None:
    passages = [QAPassage(idx=0, title="T", text="body")]
    assert build_context(passages, [0, 99, -1], top_k=5) == "[1] T\nbody"


def test_the_summary_reports_the_ceiling_beside_the_score() -> None:
    """`gold_in_context` says what each arm was working against.

    An arm at 40% EM having retrieved the answer 70% of the time has a reading
    problem; one at 38% having retrieved it 40% of the time has a retrieval
    problem. The EM alone cannot tell them apart.
    """
    rows = [
        QAAnswerResult(
            qid="1",
            arm="knn",
            question="?",
            gold="a",
            answer="a",
            em=1.0,
            f1=1.0,
            gold_in_context=True,
        ),
        QAAnswerResult(
            qid="2",
            arm="knn",
            question="?",
            gold="b",
            answer="",
            em=0.0,
            f1=0.0,
            gold_in_context=True,
        ),
    ]
    summary = summarise_qa_answers(rows)["knn"]
    assert summary["exact_match"] == 0.5
    assert summary["gold_in_context"] == 1.0
    assert summary["empty_answers"] == 1.0


def test_closed_book_is_an_arm_and_gets_no_context() -> None:
    """The control, again. 2Wiki and HotpotQA are Wikipedia; the model has read it."""
    assert ARMS[0] == "closed_book"

    seen: list[str] = []

    class _Recorder:
        async def complete(self, prompt: str, **_: object) -> str:
            seen.append(prompt)
            return "x"

    questions = [QAQuestion(qid="1", question="Who?", answer="x", gold_idxs={0})]
    passages = [QAPassage(idx=0, title="T", text="body")]
    rankings = {"knn": [[0]]}
    asyncio.run(
        answer_dataset(
            _Recorder(), questions, passages, rankings, arms=("closed_book", "knn"), top_k=1
        )
    )
    assert not any("Passages:" in p for p in seen if "Who?" in p and "body" not in p)
    assert any("body" in p for p in seen), "the retrieval arm must see its passages"
    assert any("Passages:" not in p for p in seen), "closed_book must see none"


def test_any_acceptable_form_of_the_answer_counts() -> None:
    """PopQA's key accepts "politician", "political leader", "pol" for one fact.

    Scoring against one of them alone reports failures that are not failures.
    """
    from theogony.mesh.eval.qa_answers import best_over_golds

    golds = ["politician", "political leader", "political figure", "pol"]
    assert best_over_golds("political leader", golds)[0] == 1.0
    assert best_over_golds("politician", golds)[0] == 1.0
    assert best_over_golds("carpenter", golds)[0] == 0.0
    assert best_over_golds("", golds) == (0.0, 0.0)
    assert best_over_golds("anything", []) == (0.0, 0.0)
