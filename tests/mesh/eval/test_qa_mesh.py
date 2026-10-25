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
    ALL_ARMS,
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
        text=(
            "George V of Hanover was the last King of Hanover and the son of Ernest Augustus, "
            "who died in 1851."
        ),
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
    """One fixed vector per first word, the same in every process.

    `hash()` is salted per process, so a vector drawn from it changes with
    PYTHONHASHSEED, and with it the nearest node, the first seed and the order
    of the attached paragraphs: before this used sha256, the sources test below
    failed under PYTHONHASHSEED 3, 4, 8, 10, 11 and 12 among 0-15, and twice in CI. The
    nodes carry the vectorizer's own sha256 projection, not this one, so which
    node the kNN seeds is an accident of the two functions, fixed across
    processes; for the Marie question it is Marie herself, whom the name anchor
    would seed regardless.
    """
    word = text.lower().split()[0]
    seed = int.from_bytes(hashlib.sha256(word.encode("utf-8")).digest()[:4], "little")
    rng = np.random.default_rng(seed)
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
            runtime,
            _embed,
            llm,
            questions,
            PASSAGES,
            vectors,
            arms=ALL_ARMS,
            top_k=10,
            passage_k=2,
            concurrency=2,
        )
    )
    assert len(results) == len(ALL_ARMS) * 2, "the SourceIndex is built by the run when needed"
    attached = [r.attached_passages for r in results if r.arm == "constellation_sources"]
    assert all(a is not None and a >= 1 for a in attached), attached
    assert all(r.attached_passages is None for r in results if r.arm == "constellation_typed")
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
    assert any("Source passages:" in p for p in prompts), "the sources arms lay paragraphs beside"
    assert by[("q1", "closed_book")].gold_in_context is False
    summary = summarise_qa_answers(results)
    assert set(summary) == set(ALL_ARMS)
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
    by_name = {
        n.tags[0]: str(n.id)
        for n in runtime.nodes.iter_consolidated()
        if n.tags and not n.is_source_anchor
    }
    marie, george, ernest = (
        by_name["Marie of Hanover"],
        by_name["George V of Hanover"],
        by_name["Ernest Augustus"],
    )
    assert index.passages_for([marie], limit=5) == [0], "read from the first passage"
    assert index.passages_for(["nobody"], limit=5) == []
    # the paragraph that mentions several of the entities comes first: George is
    # read from both passages, and the one he shares with Ernest wins the budget
    assert index.passages_for([george, ernest], limit=1) == [1]
    assert index.passages_for([george, marie], limit=1) == [0]
    assert index.passages_for([marie, george, ernest], limit=5) == [0, 1], "each passage once"
    index.check_passages(PASSAGES)
    with pytest.raises(ValueError, match="not the same corpus"):
        index.check_passages(PASSAGES[:1])
    from theogony.mesh.runtime.oneiros_tick import MeshRuntime as _Runtime

    with pytest.raises(ValueError, match="SourceIndex is empty"):
        SourceIndex.from_runtime(_Runtime(tmp_path / "unread", semantic_dim=8, frame_dim=8))

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
    # Marie's paragraph first, then the one her edge joins her to; the ranking
    # is pinned on its own above, this pins that the arm follows it
    from theogony.mesh.retrieval.retrieve import retrieve

    c = retrieve(runtime, _embed(q.question), query=q.question, top_k=10, record_firing=False)
    assert index.passages_for(seed_touching_entities(c.constellation), limit=2) == [0, 1]
    assert "Source passages:\n[1] Marie of Hanover\n" in sources.prompt
    assert "\n[2] George V of Hanover\n" in sources.prompt
    assert PASSAGES[0].text in sources.prompt, "the paragraph the question's entity was read from"
    assert "appears_in_source" not in sources.prompt, "typed rendering, no structural descriptors"
    assert sources.result.gold_in_context, "the ceiling is measured on the combined text"
    assert sources.result.attached_passages == 2
    one = build_qa_jobs(
        runtime,
        _embed,
        [q],
        PASSAGES,
        vectors,
        arms=("constellation_sources",),
        top_k=10,
        passage_k=1,
        source_index=index,
    )[0]
    assert one.result.attached_passages == 1, "passage_k is the budget"
    assert "[1] Marie of Hanover" in one.prompt and "[2]" not in one.prompt

    # a gold that stands only in a source paragraph separates the two ceilings
    # (the question names a two-token entity, which the name anchor finds; a
    # four-token name like "George V of Hanover" is beyond its three-token span)
    died = QAQuestion(
        qid="q3", question="When did Ernest Augustus die?", answer="1851", gold_idxs={1}
    )
    died_jobs = build_qa_jobs(
        runtime,
        _embed,
        [died],
        PASSAGES,
        vectors,
        arms=("constellation_typed", "constellation_sources"),
        top_k=10,
        passage_k=2,
        source_index=index,
    )
    ceilings = {j.result.arm: j.result.gold_in_context for j in died_jobs}
    assert ceilings == {"constellation_typed": False, "constellation_sources": True}
    # Ernest is the seed, and the paragraph that joins him to George outranks
    # corpus order: the one place in this fixture where the ranking is visible
    died_sources = next(j for j in died_jobs if j.result.arm == "constellation_sources")
    assert "Source passages:\n[1] George V of Hanover\n" in died_sources.prompt
    assert "\n[2] Marie of Hanover\n" in died_sources.prompt
    both = by_arm["constellation_sources_yn"]
    assert both.system.endswith("answer yes or no.") and "Source passages:" in both.prompt

    # the seeds come first, then what the seed-touching edges join them to
    assert c.constellation.seed_node_ids == c.seed_node_ids, (
        "the Constellation keeps the seeds in the order retrieval ranked them, not a set's"
    )
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


def test_the_harness_passes_the_accrual_switch_to_the_reader(tmp_path) -> None:
    """PHX-1118: both arms of the measurement are built through this helper."""
    off = MeshRuntime(tmp_path / "off", semantic_dim=8, frame_dim=8)
    off_report = asyncio.run(ingest_cached_readings(off, PASSAGES, READINGS))
    assert off_report.report["descriptions_revised"] == 0
    on = MeshRuntime(tmp_path / "on", semantic_dim=8, frame_dim=8)
    on_report = asyncio.run(
        ingest_cached_readings(on, PASSAGES, READINGS, accrue_descriptions=True)
    )
    assert on_report.report["descriptions_revised"] >= 1
    george = next(
        n
        for n in on.nodes.load_all_consolidated()
        if (n.description or "").startswith("George V of Hanover")
    )
    assert (
        "father of Marie" in george.description and "son of Ernest Augustus" in george.description
    )
    assert len(george.description_source_chunks) == 1
