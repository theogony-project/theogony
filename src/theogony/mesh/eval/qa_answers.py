"""End-to-end answers on the HippoRAG trio, scored the way the field scores them.

PHX-1087 built the first answer measurement this repo has ever had, on the
founding corpus, and it could not settle anything: 47 questions, a noise floor of
two to three points, and a corpus of canonical Greek mythology that the model
answers at 50% with no context at all. The arms landed within four points of each
other, which is neither support nor refutation.

This is the measurement that can settle it. 1,000 questions per dataset, gold
answers from the HippoRAG_v2 release, corpora the model has not memorised as
canon, and the same four retrieval methods the recall benchmark already scores —
so a recall number and an answer number are about the same retrieval.

Scored with SQuAD-style exact match and token F1 against the gold answer string,
which is what the multi-hop QA literature reports, so these numbers can be put
beside published ones rather than only beside each other.

Four arms, and `closed_book` is again the control that makes the rest readable:
2WikiMultihopQA and HotpotQA are built from Wikipedia, and a model that has read
Wikipedia may simply know. What any of this supports is a *difference*.
"""

from __future__ import annotations

import asyncio
import re
import string
from collections import Counter
from dataclasses import dataclass
from typing import Any

from theogony.mesh.eval.qa_retrieval import QAPassage, QAQuestion

ARMS = ("closed_book", "bm25", "knn", "sa_ppr")

_SYSTEM = (
    "Answer the question using ONLY the passages given. Reply with the shortest "
    "span that answers it — a name, a date, a phrase — and nothing else. No "
    "sentence, no explanation."
)
_SYSTEM_CLOSED = (
    "Answer the question from your own knowledge. Reply with the shortest span "
    "that answers it — a name, a date, a phrase — and nothing else. No sentence, "
    "no explanation."
)


def _normalise(text: str) -> str:
    """SQuAD normalisation: lowercase, strip articles, punctuation and extra space."""
    text = text.lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def exact_match(prediction: str, gold: str) -> float:
    return float(_normalise(prediction) == _normalise(gold))


def token_f1(prediction: str, gold: str) -> float:
    """SQuAD token F1 — the metric that gives partial credit for a partial answer."""
    pred_tokens = _normalise(prediction).split()
    gold_tokens = _normalise(gold).split()
    if not pred_tokens or not gold_tokens:
        return float(pred_tokens == gold_tokens)
    common = Counter(pred_tokens) & Counter(gold_tokens)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def best_over_golds(prediction: str, golds: list[str]) -> tuple[float, float]:
    """EM and F1 against the closest acceptable answer.

    Standard SQuAD practice, and not optional here: PopQA's key accepts
    "politician", "political leader", "political figure", "polit." and "pol" for
    the same fact. Scoring against one of them alone reports failures that are
    not failures.
    """
    if not golds:
        return (0.0, 0.0)
    return (
        max(exact_match(prediction, g) for g in golds),
        max(token_f1(prediction, g) for g in golds),
    )


@dataclass
class QAAnswerResult:
    qid: str
    arm: str
    question: str
    gold: str
    answer: str
    em: float = 0.0
    f1: float = 0.0
    gold_in_context: bool = False


def build_context(passages: list[QAPassage], indices: list[int], *, top_k: int) -> str:
    return "\n\n".join(
        f"[{n}] {passages[i].title}\n{passages[i].text}"
        for n, i in enumerate(indices[:top_k], 1)
        if 0 <= i < len(passages)
    )


async def _ask(llm: Any, system: str, prompt: str, semaphore: asyncio.Semaphore) -> str:
    async with semaphore:
        for attempt in range(3):
            try:
                raw = await llm.complete(
                    prompt, system=system, max_output_tokens=48, temperature=0.0
                )
                return (getattr(raw, "text", None) or str(raw)).strip()
            except Exception:  # noqa: BLE001 - a transient provider error is not a result
                if attempt == 2:
                    return ""
                await asyncio.sleep(2.0 * (attempt + 1))
        return ""


async def answer_dataset(
    llm: Any,
    questions: list[QAQuestion],
    passages: list[QAPassage],
    rankings: dict[str, list[list[int]]],
    *,
    arms: tuple[str, ...] = ARMS,
    top_k: int = 5,
    concurrency: int = 12,
) -> list[QAAnswerResult]:
    """Ask every question once per arm, concurrently, and score EM / F1.

    Concurrency is bounded rather than unlimited: 12,000 calls at one request in
    flight is ten hours, and at no limit it is a rate-limit error storm. A failed
    call after three tries scores as an empty answer rather than aborting the run
    — losing one question of a thousand is survivable, losing the run is not.
    """
    semaphore = asyncio.Semaphore(concurrency)
    jobs: list[tuple[QAAnswerResult, Any, list[str]]] = []
    for arm in arms:
        for qi, question in enumerate(questions):
            if arm == "closed_book":
                system, prompt = _SYSTEM_CLOSED, f"Question: {question.question}"
                in_context = False
            else:
                indices = rankings[arm][qi]
                context = build_context(passages, indices, top_k=top_k)
                system = _SYSTEM
                prompt = f"Passages:\n{context}\n\nQuestion: {question.question}"
                haystack = _normalise(context)
                in_context = any(_normalise(g) in haystack for g in question.acceptable)
            result = QAAnswerResult(
                qid=question.qid,
                arm=arm,
                question=question.question,
                gold=question.answer,
                answer="",
                gold_in_context=in_context,
            )
            jobs.append((result, _ask(llm, system, prompt, semaphore), question.acceptable))

    answers = await asyncio.gather(*(coro for _, coro, _ in jobs))
    for (result, _, golds), answer in zip(jobs, answers, strict=True):
        result.answer = answer
        result.em, result.f1 = best_over_golds(answer, golds)
    return [result for result, _, _ in jobs]


def summarise_qa_answers(results: list[QAAnswerResult]) -> dict[str, dict[str, float]]:
    """Per arm: EM, F1, and how often the gold answer was in the passages at all.

    `gold_in_context` is the ceiling each arm was working against. An arm that
    retrieved the answer 70% of the time and scored 40% EM has a reading problem;
    one that retrieved it 40% of the time and scored 38% has a retrieval problem.
    Reporting only the EM cannot tell those apart — the same conflation that
    produced three wrong diagnoses on the founding corpus (PHX-1067).
    """
    out: dict[str, dict[str, float]] = {}
    for arm in sorted({r.arm for r in results}):
        rows = [r for r in results if r.arm == arm]
        n = max(1, len(rows))
        out[arm] = {
            "questions": float(len(rows)),
            "exact_match": sum(r.em for r in rows) / n,
            "f1": sum(r.f1 for r in rows) / n,
            "gold_in_context": sum(1.0 for r in rows if r.gold_in_context) / n,
            "empty_answers": float(sum(1 for r in rows if not r.answer)),
        }
    return out
