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
    # past 1,023 discordant pairs float(2**n) overflowed; the exact ratio does not
    assert sign_test_p(600, 600) == pytest.approx(1.0)
    assert 0.0 <= sign_test_p(2000, 0) < 1e-300
    assert sign_test_p(1100, 1000) == pytest.approx(sign_test_p(1000, 1100))


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


def _typed_rows() -> list:
    from theogony.mesh.eval.qa_answers import QAAnswerResult

    rows = []
    for qid, qtype, a_em, b_em in (
        ("c1", "compositional", 1.0, 0.0),
        ("c2", "compositional", 1.0, 0.0),
        ("i1", "inference", 1.0, 1.0),
        ("m1", "comparison", 0.0, 1.0),
        ("u1", None, 1.0, 0.0),
    ):
        for arm, em in (("a", a_em), ("b", b_em)):
            rows.append(
                QAAnswerResult(
                    qid=qid,
                    arm=arm,
                    question="",
                    gold="x",
                    answer="",
                    em=em,
                    # arm a found the answer of the first compositional question only
                    gold_in_context=(arm, qid) == ("a", "c1"),
                    question_type=qtype,
                )
            )
    return rows


_POOLED = {
    "answer_unnamed": ("compositional", "inference"),
    "answer_named": ("comparison", "bridge_comparison"),
}


def test_answers_are_read_by_the_datasets_question_type() -> None:
    """One total averaged a gain where the question does not name its answer
    against a loss on plain comparisons (PHX-1127)."""
    from theogony.mesh.eval.qa_mesh import by_type_lines, summarise_by_type

    rows = _typed_rows()
    table = summarise_by_type(rows, pooled=_POOLED)
    # the types, most questions first, then the pools that hold any of them
    assert list(table) == [
        "compositional",
        "comparison",
        "inference",
        "answer_unnamed",
        "answer_named",
    ]
    assert table["answer_unnamed"]["a"] == {
        "questions": 3.0,
        "exact_match": 1.0,
        "f1": 0.0,
        "gold_in_context": pytest.approx(1 / 3),
        # what was found, and how much of the found was read out
        "exact_match_where_found": 1.0,
    }
    assert table["answer_unnamed"]["b"]["exact_match"] == pytest.approx(1 / 3)
    assert "exact_match_where_found" not in table["answer_unnamed"]["b"], (
        "an arm that found nothing has no rate at which it read, and zero would be one"
    )
    assert table["answer_named"]["a"]["exact_match"] == 0.0
    # the question the dataset gave no type is in no row, a pool included
    assert table["compositional"]["a"]["questions"] + table["inference"]["a"]["questions"] == 3.0
    assert set(summarise_by_type(rows)) == {"compositional", "comparison", "inference"}

    lines = by_type_lines(table, ["a", "b"])
    assert lines[0].split() == list(table), "one column per type and pool, named in full"
    assert lines[1].split() == ["questions", "2", "1", "1", "3", "1"]
    assert lines[2].split() == ["a", "100.0%", "0.0%", "100.0%", "100.0%", "0.0%"]
    # a dash where there is no figure: b found nothing, a only on compositional
    read = by_type_lines(table, ["a", "b", "absent"], metric="exact_match_where_found")
    assert read[2].split() == ["a", "100.0%", "-", "-", "100.0%", "-"]
    assert read[3].split() == ["b", "-", "-", "-", "-", "-"]
    assert read[4].split() == ["absent", "-", "-", "-", "-", "-"]
    # the count is the group's, not the first arm's: a is one row short here
    short = [r for r in rows if (r.arm, r.qid) != ("a", "c2")]
    assert by_type_lines(summarise_by_type(short), ["a", "b"])[1].split()[1] == "2"

    # a run without types has nothing to report, which is not a table of zeros
    assert summarise_by_type([r for r in rows if r.question_type is None]) == {}
    # a pool named like a type would put two sets of questions under one name
    with pytest.raises(ValueError, match="bears the name"):
        summarise_by_type(rows, pooled={"comparison": ("compositional",)})
    # ... refused also when this slice of the run happens to hold no such question
    no_inference = [r for r in rows if r.question_type != "inference"]
    with pytest.raises(ValueError, match="bears the name"):
        summarise_by_type(
            no_inference, pooled={"inference": ("compositional",), "rest": ("inference",)}
        )


def test_the_pairing_is_read_by_question_type() -> None:
    from theogony.mesh.eval.qa_mesh import paired_by_type

    rows = _typed_rows()
    table = paired_by_type(rows, arm="a", baseline="b", pooled=_POOLED)
    assert list(table) == [
        "compositional",
        "comparison",
        "inference",
        "answer_unnamed",
        "answer_named",
    ]
    unnamed = table["answer_unnamed"]
    assert (unnamed["em_better"], unnamed["em_worse"], unnamed["em_equal"]) == (2.0, 0.0, 1.0)
    assert (table["answer_named"]["em_better"], table["answer_named"]["em_worse"]) == (0.0, 1.0)
    assert table["answer_named"] == table["comparison"], "a pool of one type is that type"
    untyped = [r for r in rows if r.question_type is None]
    assert paired_by_type(untyped, arm="a", baseline="b", pooled=_POOLED) == {}
    # an arm that did not run pairs with nothing: no rows, rather than rows of zeros
    assert paired_by_type(rows, arm="a", baseline="absent", pooled=_POOLED) == {}


def test_the_pairing_is_split_by_which_arm_found_the_answer() -> None:
    """Two arms' reading rates are over different questions; where both found
    the answer they are over the same ones (PHX-1127)."""
    from theogony.mesh.eval.qa_answers import QAAnswerResult
    from theogony.mesh.eval.qa_mesh import paired_by_found

    rows = []
    for qid, a_found, b_found, a_em, b_em in (
        ("both1", True, True, 1.0, 1.0),
        ("both2", True, True, 0.0, 1.0),
        ("a1", True, False, 1.0, 0.0),
        ("a2", True, False, 1.0, 0.0),
        ("b1", False, True, 0.0, 1.0),
        ("none1", False, False, 0.0, 1.0),
        ("only_a_ran", True, False, 1.0, None),
    ):
        rows.append(
            QAAnswerResult(
                qid=qid, arm="a", question="", gold="x", answer="", em=a_em, gold_in_context=a_found
            )
        )
        if b_em is not None:
            rows.append(
                QAAnswerResult(
                    qid=qid,
                    arm="b",
                    question="",
                    gold="x",
                    answer="",
                    em=b_em,
                    gold_in_context=b_found,
                )
            )
    table = paired_by_found(rows, arm="a", baseline="b")
    assert list(table) == ["both", "arm_only", "baseline_only", "neither"]
    assert (table["both"]["questions"], table["both"]["em_worse"]) == (2.0, 1.0)
    assert (table["arm_only"]["em_better"], table["arm_only"]["em_worse"]) == (2.0, 0.0)
    assert (table["baseline_only"]["em_better"], table["baseline_only"]["em_worse"]) == (0.0, 1.0)
    # where neither material holds the answer, an arm scores from the model's own knowledge
    assert (table["neither"]["questions"], table["neither"]["em_worse"]) == (1.0, 1.0)
    assert sum(t["questions"] for t in table.values()) == 6.0, "the unpaired question is in no cell"
    # a cell nobody is in is left out, as a type nobody asked is
    found_by_a = [r for r in rows if r.qid in ("a1", "a2")]
    assert list(paired_by_found(found_by_a, arm="a", baseline="b")) == ["arm_only"]


def test_a_run_is_reported_by_type_in_one_place() -> None:
    """The harness writes this with a run and the script reads it out of a
    finished one; both through `by_type_report`, so the two cannot drift."""
    from theogony.mesh.eval.qa_mesh import by_type_report, pair_by_type_lines

    rows = _typed_rows()
    report = by_type_report(rows, pooled=_POOLED, pairs=(("a", "b"), ("a", "absent")))
    assert set(report) == {"by_type", "paired_by_type", "paired_in_pool"}
    assert list(report["paired_by_type"]) == ["a_vs_b"], "a pair needs both its arms"
    assert list(report["paired_by_type"]["a_vs_b"]) == list(report["by_type"])
    in_pool = report["paired_in_pool"]["a_vs_b"]
    assert list(in_pool) == ["answer_unnamed", "answer_named"], "the pools, not the single types"
    unnamed = in_pool["answer_unnamed"]
    # arm a found c1 only: the other two answers it has from somewhere else
    assert (
        unnamed["by_found"]["arm_only"]["questions"],
        unnamed["by_found"]["neither"]["questions"],
    ) == (1.0, 2.0)
    assert unnamed["by_kind"]["entity"]["questions"] == 3.0
    lines = pair_by_type_lines(report["paired_by_type"]["a_vs_b"], in_pool)
    assert lines[0].startswith("    by type: compositional 2/0 (p=0.5)")
    assert "    answer_unnamed, by where the answer stood: arm_only 1/0 · neither 1/0" in lines
    assert any(line.startswith("    answer_named, by answer kind: entity 0/1") for line in lines)

    untyped = [r for r in rows if r.question_type is None]
    assert by_type_report(untyped, pooled=_POOLED, pairs=(("a", "b"),)) == {
        "by_type": {},
        "paired_by_type": {},
        "paired_in_pool": {},
    }


def test_a_finished_run_is_read_back_with_its_question_types() -> None:
    """Runs written before PHX-1127 carry no type; the dataset file gives it."""
    from theogony.mesh.eval.qa_mesh import results_from_run

    run = {
        "answers": [
            {
                "qid": "q1",
                "arm": "passages",
                "question": "?",
                "gold": "x",
                "answer": "x",
                "em": 1.0,
                "f1": 1.0,
                "gold_in_context": True,
            },
            {
                "qid": "q2",
                "arm": "passages",
                "question": "?",
                "gold": "y",
                "answer": "",
                "em": 0.0,
                "f1": 0.0,
                "gold_in_context": False,
                "attached_passages": 2,
                "model": "m",
                "question_type": "inference",
            },
        ]
    }
    types = {"q1": "comparison", "q2": "comparison"}
    rows = results_from_run(run, question_types=types, arm_suffix="@a")
    assert [r.arm for r in rows] == ["passages@a", "passages@a"]
    assert rows[0].question_type == "comparison", "an older row takes it from the dataset"
    assert rows[1].question_type == "inference", "a row's own type is the one it was asked with"
    assert (rows[0].em, rows[0].gold_in_context) == (1.0, True)
    assert (rows[1].model, rows[1].attached_passages) == ("m", 2)
    assert [r.question_type for r in results_from_run(run)] == [None, "inference"]
    # ids are strings in the dataset's keys; a file that holds a number still joins
    numbered = {"answers": [{**run["answers"][0], "qid": 7}]}
    (row,) = results_from_run(numbered, question_types={"7": "bridge"})
    assert (row.qid, row.question_type) == ("7", "bridge")


def test_the_question_type_travels_from_the_question_to_its_answers(tmp_path) -> None:
    runtime, _ = _ingest(tmp_path)
    q = QAQuestion(
        qid="t",
        question="Who was the father of Marie of Hanover?",
        answer="George V of Hanover",
        gold_idxs={0},
        question_type="compositional",
    )
    vectors = unit_rows(np.asarray([_embed(paragraph_of(p)) for p in PASSAGES], dtype=np.float32))
    jobs = build_qa_jobs(
        runtime, _embed, [q], PASSAGES, vectors, arms=("closed_book", "passages"), passage_k=2
    )
    assert [j.result.question_type for j in jobs] == ["compositional", "compositional"]


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


# --------------------------------------------------------------------------
# PHX-1123: a measurement answers with the model it names, and says so
# --------------------------------------------------------------------------


class _AnsweredBy:
    """A provider that answers as another model would: what a fallback looks
    like from the harness."""

    model_id = "deepseek-chat|fallback:claude-sonnet-4-6"

    def __init__(self, model: str, *, fail: bool = False) -> None:
        self.model, self.fail = model, fail

    async def complete(self, prompt: str, **_: object):  # type: ignore[no-untyped-def]
        from theogony.agents.llm import LLMResult

        if self.fail:
            raise RuntimeError("402 Insufficient Balance")
        return LLMResult(text="George V of Hanover", model_id=self.model)


def _one_question() -> list[QAQuestion]:
    return [
        QAQuestion(
            qid="q1",
            question="Who was the father of Marie of Hanover?",
            answer="George V of Hanover",
            gold_idxs={0},
        )
    ]


def test_each_answer_records_the_model_that_gave_it(tmp_path, monkeypatch) -> None:
    from theogony.mesh.eval import qa_mesh
    from theogony.mesh.eval.qa_answers import models_that_answered

    runtime, _ = _ingest(tmp_path)
    vectors = unit_rows(np.asarray([_embed(paragraph_of(p)) for p in PASSAGES], dtype=np.float32))

    def run(llm):  # type: ignore[no-untyped-def]
        return asyncio.run(
            answer_qa_set(
                runtime, _embed, llm, _one_question(), PASSAGES, vectors,
                arms=("closed_book", "passages"), top_k=10, passage_k=2, concurrency=2,
            )
        )  # fmt: skip

    answered = run(_AnsweredBy("claude-sonnet-4-6"))
    assert {r.model for r in answered} == {"claude-sonnet-4-6"}
    assert models_that_answered(answered) == {"claude-sonnet-4-6": 2}

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr(qa_mesh.asyncio, "sleep", no_wait)
    failed = run(_AnsweredBy("deepseek-chat", fail=True))
    assert all(r.answer == "" and r.model is None for r in failed)
    assert models_that_answered(failed) == {"none": 2}


def _run_file(path, *, answered_by):  # type: ignore[no-untyped-def]
    run = {
        "model": "deepseek/deepseek-chat",
        "mesh": "m",
        "dataset": "2wikimultihopqa",
        "questions": 1,
        "top_k": 10,
        "passage_k": 5,
        "k_seeds": 1,
        "seed": 0,
        "answered_by": answered_by,
        "summary": {"passages": {"exact_match": 1.0, "f1": 1.0}},
        "answers": [
            {"qid": "q1", "arm": "passages", "question": "?", "gold": "x", "answer": "x",
             "em": 1.0, "f1": 1.0, "gold_in_context": True, "attached_passages": None}
        ],
    }  # fmt: skip
    path.write_text(json.dumps(run), encoding="utf-8")
    return path


def test_the_pairing_refuses_a_run_another_model_answered(tmp_path, monkeypatch, capsys) -> None:
    import importlib.util
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "scripts" / "mesh_qa_pair_runs.py"
    spec = importlib.util.spec_from_file_location("mesh_qa_pair_runs", script)
    assert spec is not None and spec.loader is not None
    pairing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pairing)
    clean = _run_file(tmp_path / "a.json", answered_by={"deepseek-chat": 1})
    mixed = _run_file(tmp_path / "b.json", answered_by={"deepseek-chat": 1, "claude-sonnet-4-6": 1})
    monkeypatch.setattr(sys, "argv", ["pair", "--a", str(clean), "--b", str(mixed)])
    with pytest.raises(SystemExit, match="answered by .*claude-sonnet-4-6"):
        pairing.main()
    older = _run_file(tmp_path / "c.json", answered_by=None)
    run = json.loads(older.read_text(encoding="utf-8"))
    del run["answered_by"]  # a run written before the record has no such key at all
    older.write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["pair", "--a", str(clean), "--b", str(older)])
    pairing.main()  # a run that predates the record cannot be checked, and is paired
    failed = _run_file(tmp_path / "d.json", answered_by={"deepseek-chat": 1, "none": 4})
    monkeypatch.setattr(sys, "argv", ["pair", "--a", str(clean), "--b", str(failed)])
    pairing.main()
    assert "4 calls of B failed" in capsys.readouterr().err
