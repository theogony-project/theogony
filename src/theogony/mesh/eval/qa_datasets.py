"""HippoRAG_v2 QA dataset access + corpus subsampling.

Dataset I/O for the QA-retrieval benchmark, kept apart from the scoring compute
in :mod:`theogony.mesh.eval.qa_retrieval` (which stays pure and offline-testable).

The files come from ``osunlp/HippoRAG_v2`` — the preprocessed release the
HippoRAG papers evaluate on. Using it as-is is what makes numbers comparable to
published work; hand-rebuilding the shared corpus and the supporting-passage
labels is the usual way that comparability gets lost.
"""

from __future__ import annotations

import json
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from theogony.mesh.eval.qa_retrieval import QAPassage, QAQuestion

HF_BASE = "https://huggingface.co/datasets/osunlp/HippoRAG_v2/resolve/main"

DATASETS: dict[str, tuple[str, str]] = {
    "2wikimultihopqa": ("2wikimultihopqa.json", "2wikimultihopqa_corpus.json"),
    "musique": ("musique.json", "musique_corpus.json"),
    "hotpotqa": ("hotpotqa.json", "hotpotqa_corpus.json"),
    "popqa": ("popqa.json", "popqa_corpus.json"),
}


@dataclass
class QADataset:
    passages: list[QAPassage]
    questions: list[QAQuestion]
    gold_coverage: float


def download(url: str, dest: Path) -> None:
    """Fetch ``url`` to ``dest`` unless a non-empty file is already there."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "theogony-bench/1.0"})
    with urllib.request.urlopen(req) as resp, dest.open("wb") as fh:  # noqa: S310 (fixed host)
        fh.write(resp.read())


def normalize_title(title: str) -> str:
    return title.strip().lower()


def load_dataset(
    name: str,
    cache_dir: Path,
    *,
    max_questions: int = 0,
    seed: int = 0,
) -> QADataset:
    """Fetch + parse one HippoRAG_v2 dataset.

    Gold passages are the question's supporting passages, matched to the shared
    corpus by title. The multi-hop trio ships HotpotQA-native ``supporting_facts``
    (``[title, sent_id]`` pairs); PopQA uses ``paragraphs`` with ``is_supporting``.
    Both shapes are handled. ``gold_coverage`` reports the fraction of gold
    references that actually resolved against the corpus — a value below 1.0 means
    the benchmark is scoring against an incomplete answer key and must be reported.
    """
    query_file, corpus_file = DATASETS[name]
    query_path = cache_dir / query_file
    corpus_path = cache_dir / corpus_file
    download(f"{HF_BASE}/{query_file}", query_path)
    download(f"{HF_BASE}/{corpus_file}", corpus_path)

    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    passages = [
        QAPassage(idx=i, title=str(p.get("title", "")), text=str(p.get("text", "")))
        for i, p in enumerate(corpus)
    ]
    title_to_idx: dict[str, int] = {}
    for p in passages:
        title_to_idx.setdefault(normalize_title(p.title), p.idx)

    raw_q = json.loads(query_path.read_text(encoding="utf-8"))
    questions: list[QAQuestion] = []
    matched_gold = 0
    total_gold = 0
    for q in raw_q:
        gold_titles: set[str] = set()
        for fact in q.get("supporting_facts", []):
            if isinstance(fact, (list, tuple)) and fact:
                gold_titles.add(normalize_title(str(fact[0])))
        for para in q.get("paragraphs", []):
            if para.get("is_supporting"):
                gold_titles.add(normalize_title(str(para.get("title", ""))))

        gold: set[int] = set()
        for gt in gold_titles:
            total_gold += 1
            idx = title_to_idx.get(gt)
            if idx is not None:
                gold.add(idx)
                matched_gold += 1
        if not gold:
            continue
        ans = q.get("answer")
        if isinstance(ans, list):
            ans = ans[0] if ans else ""
        questions.append(
            QAQuestion(
                qid=str(q.get("_id") or q.get("id") or ""),
                question=str(q.get("question", "")),
                answer=str(ans),
                gold_idxs=gold,
            )
        )
    if max_questions and len(questions) > max_questions:
        questions = random.Random(seed).sample(questions, max_questions)
    return QADataset(
        passages=passages,
        questions=questions,
        gold_coverage=matched_gold / max(1, total_gold),
    )


def subsample_corpus(
    data: QADataset,
    *,
    corpus_size: int,
    seed: int = 0,
) -> QADataset:
    """Shrink the corpus to every gold passage plus random distractors.

    LLM extraction over a full 6k–12k-passage corpus is affordable but slow, so the
    Kadmos-grade comparison runs on a focused corpus. Every gold passage is kept
    (the answer key stays intact) and distractors are sampled to reach
    ``corpus_size``, so retrieval is still a needle-in-haystack task.

    Passage indices are rebuilt densely and every question's ``gold_idxs`` is
    remapped, so the result is a self-consistent dataset. Absolute recall on a
    smaller corpus is *easier* and therefore not comparable to a full-corpus run —
    but both constructions see the identical subsample, which is what the A/B
    contrast needs.

    ``corpus_size <= 0`` (or a size at least as large as the corpus) disables
    subsampling and returns the dataset untouched, which keeps results comparable
    to a published full-corpus run.
    """
    if corpus_size <= 0 or corpus_size >= len(data.passages):
        return data

    gold_idxs: set[int] = set()
    for q in data.questions:
        gold_idxs |= q.gold_idxs

    keep = set(gold_idxs)
    if corpus_size > len(keep):
        pool = [p.idx for p in data.passages if p.idx not in keep]
        extra = random.Random(seed).sample(pool, min(corpus_size - len(keep), len(pool)))
        keep |= set(extra)

    old_to_new = {old: new for new, old in enumerate(sorted(keep))}
    passages = [
        QAPassage(idx=old_to_new[p.idx], title=p.title, text=p.text)
        for p in data.passages
        if p.idx in old_to_new
    ]
    questions = [
        QAQuestion(
            qid=q.qid,
            question=q.question,
            answer=q.answer,
            gold_idxs={old_to_new[g] for g in q.gold_idxs},
        )
        for q in data.questions
    ]
    return QADataset(passages=passages, questions=questions, gold_coverage=data.gold_coverage)
