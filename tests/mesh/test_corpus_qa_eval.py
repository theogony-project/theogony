"""The instrument that should have existed before any retrieval claim was made.

Every retrieval statement about the founding mesh up to now rested on a gold set
invented at the moment of measurement, from a single question. Three diagnoses
came out of that and all three were wrong: consolidation was blamed for what was
a discarded entity name, a growth curve was read from a truncated sample, and an
effect dismissed as noise turned out to be −27% over the full corpus.

These tests pin the two properties that make the instrument trustworthy: the
gold set is quotable from the corpus, and coverage is reported separately from
recall so that a reading problem cannot be mistaken for a retrieval problem.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from theogony.mesh.eval.corpus_qa import (
    GOLD_PATH,
    GoldQuestion,
    QuestionResult,
    _normalise,
    load_gold,
    summarise,
    summarise_by_kind,
)

CORPUS = Path("data/raw/founding/pg348_the.txt")


def test_the_gold_set_loads_and_is_not_trivial() -> None:
    gold = load_gold()
    # Exact, not a floor. `>= 30` let the README go on advertising "32 questions"
    # for six days after PHX-1073 widened the set to 47 — a floor cannot notice
    # that a published number stopped matching the file (PHX-1080).
    assert len(gold) == 47, "gold set size changed: update README.md and the PHX entry too"
    assert sum(len(q.expect) for q in gold) == 111
    assert all(q.expect for q in gold), "a question with no expected entity scores nothing"
    assert len({q.id for q in gold}) == len(gold), "ids must be unique"


def test_every_answer_is_quotable_from_the_corpus() -> None:
    """The gold set is grounded in the text, not in general knowledge.

    Authoring it this way caught three wrong assumptions: the volume contains no
    "Works and Days", so no Pandora's jar and no golden race, and its Pandora is
    Deucalion's daughter who bore Graecus.
    """
    if not CORPUS.is_file():
        return  # corpus is a data file, not shipped with the package
    flat = re.sub(r"\s+", " ", CORPUS.read_text(encoding="utf-8"))
    flat = re.sub(r"\s\d{3,4}\b", "", flat)  # inline footnote markers
    flat = re.sub(r"\(ll?\.[^)]*\)", "", flat).lower()
    for question in load_gold():
        head = re.sub(r"\s+", " ", question.evidence).split(" ... ")[0][:70].lower()
        assert head in flat, f"{question.id}: evidence not found in the corpus"


def test_names_fold_past_inline_footnote_markers() -> None:
    """The corpus writes "Hestia 1618"; the mesh inherits that."""
    assert _normalise("Hestia 1618") == _normalise("Hestia")
    assert _normalise("Zeus") == "zeus"
    assert _normalise("  ") == ""


def test_coverage_and_recall_are_reported_apart() -> None:
    """The distinction the whole module exists for.

    An entity absent from the mesh is a reading failure; one present but not
    retrieved is a retrieval failure. A single blended number hides which one
    you have, and that confusion produced two wrong diagnoses.
    """
    missing_from_mesh = QuestionResult(
        id="q1", question="?", expected=["A", "B"], present=["A"], missing=["B"], retrieved=["A"]
    )
    assert missing_from_mesh.coverage == 0.5
    assert missing_from_mesh.recall == 1.0, "retrieval did everything it could"

    present_but_unfound = QuestionResult(
        id="q2", question="?", expected=["A", "B"], present=["A", "B"], missing=[], retrieved=[]
    )
    assert present_but_unfound.coverage == 1.0
    assert present_but_unfound.recall == 0.0, "reading did everything it could"

    summary = summarise([missing_from_mesh, present_but_unfound])
    assert summary["coverage"] == 0.75
    assert summary["recall_given_coverage"] == 1 / 3
    assert summary["end_to_end"] == 0.25


def test_a_question_with_nothing_in_the_mesh_scores_zero_not_one() -> None:
    """Recall over an empty set must not read as success."""
    nothing = QuestionResult(id="q", question="?", expected=["A"], present=[], missing=["A"])
    assert nothing.coverage == 0.0
    assert nothing.recall == 0.0
    assert summarise([nothing])["recall_given_coverage"] == 0.0


def test_summary_of_no_results_is_defined() -> None:
    summary = summarise([])
    assert summary["questions"] == 0.0
    assert summary["coverage"] == 0.0


def test_gold_questions_carry_their_evidence() -> None:
    for question in load_gold():
        assert isinstance(question, GoldQuestion)
        assert len(question.evidence) > 20, f"{question.id}: evidence too thin to check"


def test_the_recall_curve_is_reported_over_several_budgets() -> None:
    """One number at one budget is the wrong picture.

    Measured on the founding mesh, recall is 65% at top_k=30 and 95% at 200 —
    the top 4% of a 5,002-node substrate. Reading the 65% as "retrieval cannot
    find the answers" points the next piece of work at the wrong place: the
    ranking is largely right and the budget is tight.
    """
    from theogony.mesh.eval import corpus_qa

    calls: list[int] = []

    def fake_evaluate(runtime, embed, *, gold=None, top_k=30, **kw):  # noqa: ANN001, ANN202
        calls.append(top_k)
        return []

    original = corpus_qa.evaluate
    corpus_qa.evaluate = fake_evaluate  # type: ignore[assignment]
    try:
        curve = corpus_qa.recall_curve(None, lambda _: [], ks=(10, 30, 100))  # type: ignore[arg-type]
    finally:
        corpus_qa.evaluate = original  # type: ignore[assignment]

    assert calls == [10, 30, 100], "every requested budget must be measured"
    assert set(curve) == {10, 30, 100}


def test_every_question_declares_its_kind() -> None:
    """The split must live in the file, not in whatever regex measured it that day.

    PHX-1066's lesson is that the aggregate hides per-kind regressions: removing
    co-occurrence edges read as +2 overall and was -10 on narrative questions. So
    every claim since is reported split. The split itself was never checked in,
    and three separate hand-labellings of these 47 questions produced 51%, 55%
    and 57% genealogical — the published numbers depended on which one had been
    written that morning (PHX-1080).
    """
    gold = load_gold()
    assert {q.kind for q in gold} == {"genealogical", "narrative"}
    genealogical = [q for q in gold if q.kind == "genealogical"]
    assert len(genealogical) == 26, "the published share is 55% by question — 26 of 47"
    assert sum(len(q.expect) for q in genealogical) == 75, "and 68% by entity — 75 of 111"


def test_the_labelling_rule_travels_with_the_labels() -> None:
    """A judgement call is only reproducible if the call is written down."""
    raw = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    kinds = raw["_kinds"]
    assert kinds["_rule"], "the rule that assigns a kind must be stated"
    assert kinds["_borderline"], "the close calls must be named, not silently decided"
    labelled = {q["id"] for q in raw["questions"]}
    assert set(kinds["_borderline"]) <= labelled, "a borderline note for a question that is gone"


def test_results_are_summarised_per_kind_and_in_aggregate() -> None:
    """Both, always. Reporting only the aggregate is the documented failure mode."""
    results = [
        QuestionResult(
            id="g",
            question="?",
            expected=["A"],
            present=["A"],
            retrieved=["A"],
            kind="genealogical",
        ),
        QuestionResult(
            id="n", question="?", expected=["B"], present=["B"], retrieved=[], kind="narrative"
        ),
    ]
    by_kind = summarise_by_kind(results)
    assert set(by_kind) == {"genealogical", "narrative", "all"}
    assert by_kind["genealogical"]["recall_given_coverage"] == 1.0
    assert by_kind["narrative"]["recall_given_coverage"] == 0.0
    assert by_kind["all"]["recall_given_coverage"] == 0.5, "the aggregate hides both"
