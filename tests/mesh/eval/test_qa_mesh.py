"""The answer arm on a corpus the model does not know (PHX-1110).

Two things are pinned: that the replay rebuilds a mesh from the cached readings
through the shipped write path without an LLM, and that the four arms are built
and scored on the same question the same way. The numbers live in the etappe;
what a test can hold is the plumbing that produced them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import numpy as np
import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.eval.qa_answers import summarise_qa_answers
from theogony.mesh.eval.qa_mesh import (
    QA_ARMS,
    ReplayReadingProvider,
    answer_qa_set,
    build_qa_jobs,
    ingest_cached_readings,
    load_readings,
    nearest_passages,
    paired_qa,
    paragraph_of,
    reading_key,
    readings_by_paragraph,
    sign_test_p,
    unit_rows,
)
from theogony.mesh.eval.qa_retrieval import QAPassage, QAQuestion
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

PASSAGES = [
    QAPassage(
        idx=0,
        title="Marie of Hanover",
        text="Marie of Hanover was the daughter of George V of Hanover.\nShe died in Gmunden.",
    ),
    QAPassage(
        idx=1,
        title="George V of Hanover",
        text="George V of Hanover was the last King of Hanover and the son of Ernest Augustus.",
    ),
    QAPassage(
        idx=2,
        title="Lake Traunsee",
        text="Lake Traunsee lies beside the town of Gmunden in Austria.",
    ),
]


def _reading(*concepts: tuple[str, str], relations: list[tuple[str, str, str]] = ()) -> dict:
    return {
        "concepts": [
            {"label": label, "entity_type": "person", "tags": [], "description": desc, "qids": []}
            for label, desc in concepts
        ],
        "relations": [
            {
                "source": s,
                "target": t,
                "relation_descriptor": d,
                "relation_kind": "hierarchy",
                "rationale": "",
            }
            for s, d, t in relations
        ],
        "paragraph_concept": None,
    }


READINGS = {
    reading_key(PASSAGES[0].text): _reading(
        ("Marie of Hanover", "Daughter of George V of Hanover; died in Gmunden."),
        ("George V of Hanover", "King of Hanover, father of Marie."),
        relations=[("Marie of Hanover", "daughter of", "George V of Hanover")],
    ),
    reading_key(PASSAGES[1].text): _reading(
        ("George V of Hanover", "Last King of Hanover, son of Ernest Augustus."),
        ("Ernest Augustus", "King of Hanover, father of George V."),
        relations=[("George V of Hanover", "son of", "Ernest Augustus")],
    ),
    # passage 2 has no reading: the replay must report it, not invent one
}


def _prompt(passage: QAPassage) -> str:
    return (
        f"PARAGRAPH:\n{paragraph_of(passage)}\n\n"
        "Extract the concepts, relations, and paragraph concept."
    )


def test_the_reading_key_is_the_cache_scripts_key() -> None:
    """blake2b-128 of the passage text, which is what mesh_qa_kadmos.py writes
    and what six thousand cached rows are keyed under."""
    assert reading_key("abc") == hashlib.blake2b(b"abc", digest_size=16).hexdigest()
    assert len(reading_key("")) == 32


def test_load_readings_skips_what_it_cannot_parse(tmp_path) -> None:
    path = tmp_path / "readings.jsonl"
    path.write_text(
        json.dumps({"key": "k1", "reading": {"concepts": []}})
        + "\nnot json\n\n"
        + json.dumps({"no_key": True})
        + "\n",
        encoding="utf-8",
    )
    assert load_readings(path) == {"k1": {"concepts": []}}


def test_the_replay_answers_the_paragraph_prompt_from_the_cache() -> None:
    provider = ReplayReadingProvider(readings_by_paragraph(PASSAGES, READINGS))
    hit = asyncio.run(provider.complete(prompt=_prompt(PASSAGES[0]), system="x", json_schema={}))
    assert json.loads(hit.text)["concepts"][0]["label"] == "Marie of Hanover"
    miss = asyncio.run(provider.complete(prompt=_prompt(PASSAGES[2])))
    assert miss.text == ""
    foreign = asyncio.run(provider.complete(prompt="Something else entirely"))
    assert foreign.text == ""
    assert provider.hits == 1
    assert len(provider.misses) == 2


def test_paragraph_in_recovers_a_passage_with_internal_newlines() -> None:
    """31 of the 2Wiki passages contain a single newline; the reader keeps it
    and the replay must find the paragraph under the identical string."""
    assert ReplayReadingProvider.paragraph_in(_prompt(PASSAGES[0])) == paragraph_of(PASSAGES[0])
    assert ReplayReadingProvider.paragraph_in("no head") is None


def _ingest(tmp_path) -> tuple[MeshRuntime, object]:
    runtime = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=8)
    report = asyncio.run(
        ingest_cached_readings(runtime, PASSAGES, READINGS, source_identifier="test")
    )
    return runtime, report


def test_the_replay_writes_a_mesh_through_the_shipped_reader(tmp_path) -> None:
    runtime, report = _ingest(tmp_path)
    assert (report.hits, report.misses, report.paragraphs) == (2, 1, 3)
    chunks = list(runtime.nodes.iter_chunks())
    assert len(chunks) == 3, "one chunk per passage, the unreadable one included"
    names = {
        n.tags[0] for n in runtime.nodes.iter_consolidated() if n.tags and not n.is_source_anchor
    }
    assert {"Marie of Hanover", "George V of Hanover", "Ernest Augustus"} <= names
    assert report.report["paragraphs"] == 3 and report.report["llm_calls"] == 3
    edges = runtime.edges.load_all_edges()
    assert any(e.relation_descriptor == "daughter of" for e in edges)


def test_a_read_compacts_its_own_workspace_as_it_goes(tmp_path) -> None:
    """One fragment per node until something compacts, and a read of six
    thousand paragraphs never ticks: the rate fell from 0.55 s to over 6 s per
    paragraph before this existed (PHX-1110)."""

    def fragments(root) -> int:
        return len(list((root / "lance" / "consolidated_nodes.lance" / "data").glob("*")))

    loose = MeshRuntime(tmp_path / "loose", semantic_dim=8, frame_dim=8)
    asyncio.run(ingest_cached_readings(loose, PASSAGES, READINGS, compact_every=0))
    tight = MeshRuntime(tmp_path / "tight", semantic_dim=8, frame_dim=8)
    asyncio.run(ingest_cached_readings(tight, PASSAGES, READINGS, compact_every=1))
    assert fragments(tmp_path / "tight") < fragments(tmp_path / "loose")
    assert tight.nodes.consolidated_count() == loose.nodes.consolidated_count()


def _embed(text: str) -> list[float]:
    """Deterministic, and keeps an entity's name close to a question that says it."""
    rng = np.random.default_rng(abs(hash(text.lower().split()[0])) % 2**32)
    return list(rng.standard_normal(8).astype(np.float32))


def test_the_four_arms_are_built_on_one_question_and_scored_alike(tmp_path) -> None:
    runtime, _ = _ingest(tmp_path)
    questions = [
        QAQuestion(
            qid="q1",
            question="Who was the father of Marie of Hanover?",
            answer="George V of Hanover",
            gold_idxs={0},
        ),
        QAQuestion(
            qid="q2",
            question="Where did Marie of Hanover die?",
            answer="Gmunden",
            gold_idxs={0},
            answer_aliases=["Gmunden, Austria"],
        ),
    ]
    vectors = unit_rows(np.asarray([_embed(paragraph_of(p)) for p in PASSAGES], dtype=np.float32))
    llm = StubLLMProvider(default="George V of Hanover")
    results = asyncio.run(
        answer_qa_set(
            runtime, _embed, llm, questions, PASSAGES, vectors, top_k=10, passage_k=2, concurrency=2
        )
    )
    assert len(results) == len(QA_ARMS) * 2
    by = {(r.qid, r.arm): r for r in results}
    # scored against the answer key, same scorer for every arm
    assert by[("q1", "closed_book")].em == 1.0 and by[("q1", "constellation")].em == 1.0
    assert by[("q2", "constellation")].em == 0.0 and by[("q2", "constellation")].f1 == 0.0
    # the material each arm read is the material its ceiling was measured on
    prompts = [c["prompt"] for c in llm.calls]
    assert any("Entities:" in p and "Relations between them:" in p for p in prompts), (
        "constellation shows edges"
    )
    typed = [p for p in prompts if "Relations between them:" in p and "co_mentions" not in p]
    assert typed, "constellation_typed drops the structural descriptors"
    assert any("daughter of" in p for p in typed), "and keeps the read relations"
    assert any("Entities:" in p and "Relations" not in p for p in prompts), "vector arm shows none"
    assert any(p.startswith("Material:\n[1] ") for p in prompts), "passages arm shows passages"
    assert by[("q1", "closed_book")].gold_in_context is False
    summary = summarise_qa_answers(results)
    assert set(summary) == set(QA_ARMS)
    assert summary["closed_book"]["exact_match"] == 0.5


def test_gold_in_context_is_a_token_match_not_a_substring(tmp_path) -> None:
    """'no' inside 'Hanover' must not count as the answer being present."""
    runtime, _ = _ingest(tmp_path)
    q = QAQuestion(qid="yn", question="Was Marie of Hanover a queen?", answer="no", gold_idxs={0})
    vectors = unit_rows(np.asarray([_embed(paragraph_of(p)) for p in PASSAGES], dtype=np.float32))
    jobs = build_qa_jobs(runtime, _embed, [q], PASSAGES, vectors, arms=("passages",), passage_k=3)
    assert jobs[0].result.gold_in_context is False


def test_nearest_passages_ranks_by_cosine() -> None:
    vectors = unit_rows(np.asarray([[1, 0], [0, 1], [0.6, 0.8]], dtype=np.float32))
    assert nearest_passages(vectors, [0.0, 1.0], 2) == [1, 2]
    assert nearest_passages(vectors, [1.0, 0.0], 0) == []
    assert nearest_passages(vectors, [1.0, 0.0], 10) == [0, 2, 1]


def test_answers_are_broken_down_by_the_shape_of_the_gold() -> None:
    """One total hid a 20-point collapse on yes/no questions (PHX-1110)."""
    from theogony.mesh.eval.qa_answers import QAAnswerResult
    from theogony.mesh.eval.qa_mesh import answer_kind, summarise_by_kind

    assert answer_kind("No") == "yes_no"
    assert answer_kind("20 March 851") == "date"
    assert answer_kind("1961") == "date"
    assert answer_kind("Port of Spain") == "entity"
    assert answer_kind("Apollo 11") == "entity", "a number is not a year"

    rows = [
        QAAnswerResult(qid="a", arm="x", question="", gold="yes", answer="", em=1.0),
        QAAnswerResult(qid="b", arm="x", question="", gold="no", answer="", em=0.0),
        QAAnswerResult(qid="c", arm="x", question="", gold="Gmunden", answer="", em=1.0),
    ]
    table = summarise_by_kind(rows)
    assert table["yes_no"]["x"] == {
        "questions": 2.0,
        "exact_match": 0.5,
        "f1": 0.0,
        "gold_in_context": 0.0,
    }
    assert table["entity"]["x"]["exact_match"] == 1.0


def test_paired_comparison_and_sign_test() -> None:
    from theogony.mesh.eval.qa_answers import QAAnswerResult

    rows = []
    for i in range(10):
        rows.append(
            QAAnswerResult(qid=f"q{i}", arm="a", question="", gold="", answer="", em=1.0, f1=1.0)
        )
        rows.append(
            QAAnswerResult(
                qid=f"q{i}",
                arm="b",
                question="",
                gold="",
                answer="",
                em=float(i < 2),
                f1=float(i < 2),
            )
        )
    p = paired_qa(rows, arm="a", baseline="b")
    assert (p["em_better"], p["em_worse"], p["em_equal"]) == (8.0, 0.0, 2.0)
    assert p["p_em"] == pytest.approx(2 / 256)
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(5, 5) == pytest.approx(1.0)
    assert sign_test_p(10, 0) == pytest.approx(2 / 1024)


def test_the_sources_arm_lays_the_paragraphs_beside_the_constellation(tmp_path) -> None:
    """PHX-1114: the mesh keeps a reference to the paragraph, the benchmark
    keeps the text; the arm puts them back together for the seed-touching
    entities, and the yes/no sentence is one prompt line (PHX-1113)."""
    from theogony.mesh.eval.qa_mesh import (
        ALL_ARMS,
        EXTRA_ARMS,
        SourceIndex,
        seed_touching_entities,
    )

    runtime, _ = _ingest(tmp_path)
    index = SourceIndex.from_runtime(runtime)
    assert len(index.chunk_passage) == 3, "one chunk per passage, #p1..#p3 -> 0..2"
    assert set(index.chunk_passage.values()) == {0, 1, 2}
    marie = next(
        n for n in runtime.nodes.iter_consolidated() if n.tags and n.tags[0] == "Marie of Hanover"
    )
    assert index.passages_for([str(marie.id)], limit=5) == [0], "read from the first passage"
    assert index.passages_for(["nobody"], limit=5) == []

    q = QAQuestion(
        qid="q1",
        question="Who was the father of Marie of Hanover?",
        answer="George V",
        gold_idxs={0},
    )
    vectors = unit_rows(np.asarray([_embed(paragraph_of(p)) for p in PASSAGES], dtype=np.float32))
    jobs = build_qa_jobs(
        runtime,
        _embed,
        [q],
        PASSAGES,
        vectors,
        arms=EXTRA_ARMS,
        top_k=10,
        passage_k=2,
        source_index=index,
    )
    by_arm = {j.result.arm: j for j in jobs}
    typed_yn = by_arm["constellation_typed_yn"]
    assert typed_yn.system.endswith("answer yes or no.")
    assert (
        "Relations between them:" in typed_yn.prompt and "Source passages:" not in typed_yn.prompt
    )
    sources = by_arm["constellation_sources"]
    assert not sources.system.endswith("answer yes or no.")
    assert "Relations between them:" in sources.prompt
    assert "Source passages:\n[1] Marie of Hanover\n" in sources.prompt
    assert PASSAGES[0].text in sources.prompt, "the paragraph the seed was read from"
    assert sources.result.gold_in_context, "the ceiling is measured on the combined text"
    both = by_arm["constellation_sources_yn"]
    assert both.system.endswith("answer yes or no.") and "Source passages:" in both.prompt

    # the seeds come first, then what the seed-touching edges join them to
    from theogony.mesh.retrieval.retrieve import retrieve

    c = retrieve(runtime, _embed(q.question), query=q.question, top_k=10, record_firing=False)
    ordered = seed_touching_entities(c.constellation)
    assert ordered[: len(c.constellation.seed_node_ids)] == c.constellation.seed_node_ids
    assert len(ordered) == len(set(ordered))

    with pytest.raises(ValueError, match="unknown arm"):
        build_qa_jobs(runtime, _embed, [q], PASSAGES, vectors, arms=("vibes",))
    with pytest.raises(ValueError, match="SourceIndex"):
        build_qa_jobs(runtime, _embed, [q], PASSAGES, vectors, arms=("constellation_sources",))
    assert set(QA_ARMS) < set(ALL_ARMS)


def test_the_pairing_is_read_by_answer_kind() -> None:
    """PHX-1113's finish line: the yes/no questions, and the cost on the rest."""
    from theogony.mesh.eval.qa_answers import QAAnswerResult
    from theogony.mesh.eval.qa_mesh import paired_by_kind

    rows = []
    for qid, gold, a_em, b_em in (
        ("y1", "yes", 1.0, 0.0),
        ("y2", "no", 1.0, 0.0),
        ("e1", "Gmunden", 0.0, 1.0),
        ("d1", "1961", 1.0, 1.0),
    ):
        rows.append(QAAnswerResult(qid=qid, arm="a", question="", gold=gold, answer="", em=a_em))
        rows.append(QAAnswerResult(qid=qid, arm="b", question="", gold=gold, answer="", em=b_em))
    table = paired_by_kind(rows, arm="a", baseline="b")
    assert set(table) == {"entity", "yes_no", "date", "not_yes_no"}
    assert (table["yes_no"]["em_better"], table["yes_no"]["em_worse"]) == (2.0, 0.0)
    assert (table["not_yes_no"]["questions"], table["not_yes_no"]["em_worse"]) == (2.0, 1.0)
    assert table["date"]["em_equal"] == 1.0
