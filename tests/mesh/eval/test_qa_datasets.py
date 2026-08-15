"""Corpus subsampling — the answer key must survive index rebuilding.

``subsample_corpus`` renumbers passages densely, so every question's gold indices
have to be remapped in lockstep. A silent off-by-one here would not crash — it
would quietly score the benchmark against the wrong passages, which is the worst
possible failure for a measurement harness.
"""

from __future__ import annotations

from theogony.mesh.eval.qa_datasets import QADataset, subsample_corpus
from theogony.mesh.eval.qa_retrieval import QAPassage, QAQuestion


def _dataset(n_passages: int = 10) -> QADataset:
    passages = [QAPassage(idx=i, title=f"T{i}", text=f"text {i}") for i in range(n_passages)]
    questions = [
        QAQuestion(qid="q0", question="?", answer="a", gold_idxs={2, 7}),
        QAQuestion(qid="q1", question="?", answer="b", gold_idxs={5}),
    ]
    return QADataset(passages=passages, questions=questions, gold_coverage=1.0)


def test_every_gold_passage_survives_and_indices_are_remapped() -> None:
    out = subsample_corpus(_dataset(), corpus_size=5, seed=0)

    assert len(out.passages) == 5
    # Indices are dense and match list position.
    assert [p.idx for p in out.passages] == list(range(5))

    # Gold passages are all still present, and each question points at the passage
    # carrying its original text (not merely at some valid index).
    by_idx = {p.idx: p for p in out.passages}
    assert {by_idx[g].title for g in out.questions[0].gold_idxs} == {"T2", "T7"}
    assert {by_idx[g].title for g in out.questions[1].gold_idxs} == {"T5"}


def test_corpus_size_below_gold_count_keeps_all_gold() -> None:
    # 3 gold passages but only room for 1: gold wins, the answer key stays intact.
    out = subsample_corpus(_dataset(), corpus_size=1, seed=0)
    assert len(out.passages) == 3
    by_idx = {p.idx: p for p in out.passages}
    assert {by_idx[g].title for g in out.questions[0].gold_idxs} == {"T2", "T7"}


def test_non_positive_or_oversized_corpus_size_disables_subsampling() -> None:
    data = _dataset()
    for size in (0, -1, 10, 999):
        out = subsample_corpus(data, corpus_size=size, seed=0)
        assert len(out.passages) == 10
        assert out.questions[0].gold_idxs == {2, 7}  # untouched, original indices


def test_subsampling_is_deterministic_for_a_seed() -> None:
    a = subsample_corpus(_dataset(), corpus_size=6, seed=42)
    b = subsample_corpus(_dataset(), corpus_size=6, seed=42)
    assert [p.title for p in a.passages] == [p.title for p in b.passages]
