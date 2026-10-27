"""Track D, step 1 (PHX-1118): a node's description accrues when the entity is read again.

Today a re-recognised entity gains a reference edge and a firing and keeps the
description of its first mention. With ``accrue_descriptions=True`` the reader
folds the later paragraph's description in — deterministically, bounded, with
provenance and an audit row — and writes the revised rows once per flush.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import (
    DESCRIPTION_MAX_CHARS,
    MeshParagraphReader,
    merge_description,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode
from theogony.reporting.models import StoreSummary

# --------------------------------------------------------------------------
# The merge rule, pure
# --------------------------------------------------------------------------


def test_merge_appends_a_new_sentence_and_keeps_the_standing_text_as_a_prefix() -> None:
    standing = "Zeus — King of the gods"
    merged = merge_description(standing, "Son of Cronos and Rhea.")
    assert merged == "Zeus — King of the gods. Son of Cronos and Rhea."
    assert merged.startswith(standing)
    assert (
        merge_description("Zeus — King of the gods.", "Son of Cronos and Rhea.")
        == "Zeus — King of the gods. Son of Cronos and Rhea."
    )


def test_merge_treats_case_whitespace_and_terminal_punctuation_as_the_same_sentence() -> None:
    standing = "Sven Hedin — Swedish explorer known for expeditions in Central Asia"
    assert (
        merge_description(standing, "swedish  explorer known for expeditions in central asia.")
        is None
    )
    assert merge_description("Zeus — King of the gods", "King of the gods") is None, (
        "the body of the head counts as present"
    )
    assert merge_description(standing, "") is None
    assert merge_description(standing, "   ") is None


def test_merge_stops_at_the_cap_on_a_sentence_boundary_and_never_shrinks() -> None:
    standing = "Entity — " + "x" * 400
    short, long_ = "A short fact.", "y" * 120 + "."
    # the long sentence would cross the cap: nothing is appended, and a shorter
    # sentence after it is not pulled forward
    assert merge_description(standing, f"{long_} {short}") is None
    merged = merge_description(standing, f"{short} {long_}")
    assert merged == f"{standing}. {short}"
    assert len(merged) <= DESCRIPTION_MAX_CHARS
    full = "Entity — " + "z" * (DESCRIPTION_MAX_CHARS - 5)
    assert len(full) >= DESCRIPTION_MAX_CHARS
    assert merge_description(full, "Anything new.") is None


def test_merge_is_deterministic_keeps_incoming_order_and_dedupes_within_the_body() -> None:
    body = "Second fact. First fact. Second fact."
    first = merge_description("Thing — one", body)
    assert first == merge_description("Thing — one", body)
    assert first == "Thing — one. Second fact. First fact."
    assert merge_description("", "Only a body.") == "Only a body."


# --------------------------------------------------------------------------
# The batched row update, on a live Lance table
# --------------------------------------------------------------------------


def _node(i: int, *, dim: int = 8, frame_dim: int = 4) -> ConsolidatedNode:
    now = datetime.now(UTC)
    vector = [float((i * 7 + k) % 11) / 11.0 for k in range(dim)]
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=vector,
        frame_vector=[0.0] * frame_dim,
        description_vector=vector,
        description=f"Node {i} — a thing",
        tags=[f"node {i}"],
    )


def test_update_consolidated_many_rewrites_rows_in_place_with_one_write(
    mesh_runtime: MeshRuntime,
) -> None:
    store = mesh_runtime.nodes
    nodes = [_node(i) for i in range(600)]
    store.append_consolidated_many(nodes)
    store.ensure_indices()
    count_before = store.consolidated_count()
    version_before = store.consolidated_table.version
    new_vector = [1.0] + [0.0] * 7
    revised = [
        n.model_copy(
            update={
                "description": f"{n.description}. Revised.",
                "description_vector": new_vector,
                "semantic_vector": new_vector,
                "description_source_chunks": [ULID()],
                "description_generated_at": datetime.now(UTC),
            }
        )
        for n in nodes[:50]
    ]
    store.update_consolidated_many(revised)
    assert store.consolidated_count() == count_before, "an update adds no rows"
    assert store.consolidated_table.version == version_before + 1, "one transaction for 50 rows"
    got = store.get_consolidated(str(revised[0].id))
    assert got is not None
    assert got.description == revised[0].description
    assert got.description_source_chunks == revised[0].description_source_chunks
    assert got.description_generated_at is not None
    assert got.description_vector == pytest.approx(new_vector)
    untouched = store.get_consolidated(str(nodes[-1].id))
    assert untouched is not None and untouched.description == nodes[-1].description
    ids = [str(n.id) for n in store.load_all_consolidated()]
    assert len(ids) == len(set(ids)) == count_before
    # an empty update is a no-op: no Lance version is written
    store.update_consolidated_many([])
    assert store.consolidated_table.version == version_before + 1


# --------------------------------------------------------------------------
# The reader: a second mention revises the node
# --------------------------------------------------------------------------

_HEDIN = {"label": "Sven Hedin", "entity_type": "person", "tags": ["explorer", "geographer"]}
_PLATEAU = {
    "label": "Tibetan Plateau",
    "entity_type": "place",
    "tags": ["plateau", "asia"],
    "description": "High plateau in Central Asia",
    "qids": [],
}


def _reading(*concepts: dict, relations: list | None = None) -> str:
    return json.dumps(
        {
            "concepts": [{"qids": [], **c} for c in concepts],
            "relations": relations or [],
            "paragraph_concept": None,
        }
    )


_P1 = "Sven Hedin crossed the Tibetan Plateau."
_P2 = "Sven Hedin was born in Stockholm."
_P3 = "Sven Hedin mapped the Brahmaputra River."
_RESPONSES = {
    f"PARAGRAPH:\n{_P1}": _reading(
        {**_HEDIN, "description": "Swedish explorer known for expeditions in Central Asia"},
        _PLATEAU,
    ),
    f"PARAGRAPH:\n{_P2}": _reading(
        {**_HEDIN, "description": "Born in Stockholm in 1865"},
        _PLATEAU,
    ),
    f"PARAGRAPH:\n{_P3}": _reading(
        {**_HEDIN, "description": "Mapped the course of the Brahmaputra River"},
        {
            "label": "Brahmaputra River",
            "entity_type": "place",
            "tags": ["river", "asia"],
            "description": "Major river flowing from the Tibetan Plateau",
        },
    ),
}
_TEXT = f"{_P1}\n\n{_P2}\n\n{_P3}"
_EXPECTED = (
    "Sven Hedin — Swedish explorer known for expeditions in Central Asia. "
    "Born in Stockholm in 1865. Mapped the course of the Brahmaputra River"
)


def _read(mesh_runtime: MeshRuntime, tmp_path: Path, **kwargs) -> tuple[dict, MeshParagraphReader]:
    reader = MeshParagraphReader(
        mesh_runtime, llm=StubLLMProvider(responses=_RESPONSES), max_paragraphs=10, **kwargs
    )
    result = asyncio.run(
        reader.read_text(
            text=_TEXT,
            source_type="test",
            source_identifier="hedin",
            title="Hedin",
            anchor=str(tmp_path / "hedin.txt"),
        )
    )
    return result, reader


def _hedin(mesh_runtime: MeshRuntime) -> ConsolidatedNode:
    nodes = [
        n
        for n in mesh_runtime.nodes.load_all_consolidated()
        if (n.description or "").startswith("Sven Hedin")
    ]
    assert len(nodes) == 1, [n.description for n in nodes]
    return nodes[0]


def _audit_rows(mesh_runtime: MeshRuntime, action: str) -> list[dict]:
    rows = mesh_runtime.audit.list_recent(limit=1000)
    return [json.loads(r["payload_json"]) for r in rows if r["action"] == action]


@pytest.mark.parametrize("compact_every", [0, 2])
def test_a_later_mention_extends_the_description_with_provenance_and_an_audit_row(
    mesh_runtime: MeshRuntime, tmp_path: Path, compact_every: int
) -> None:
    result, reader = _read(
        mesh_runtime, tmp_path, accrue_descriptions=True, compact_every=compact_every
    )
    assert result["descriptions_revised"] == 2
    hedin = _hedin(mesh_runtime)
    assert hedin.description == _EXPECTED
    chunks = {
        str(c.raw_text_ref).rsplit("#p", 1)[-1]: str(c.id) for c in mesh_runtime.nodes.iter_chunks()
    }
    assert [str(c) for c in hedin.description_source_chunks] == [chunks["2"], chunks["3"]]
    assert hedin.description_generated_at is not None
    expected_vector = asyncio.run(reader.vectorizer.description(_EXPECTED))
    assert hedin.description_vector == pytest.approx(expected_vector)
    assert hedin.semantic_vector == pytest.approx(expected_vector)
    # the plateau was mentioned twice with the same description: no revision
    plateau = next(
        n
        for n in mesh_runtime.nodes.load_all_consolidated()
        if (n.description or "").startswith("Tibetan Plateau")
    )
    assert plateau.description_source_chunks == [] and plateau.description_generated_at is None
    # one audit row per revision, from the same branch as the counter
    revisions = _audit_rows(mesh_runtime, "mesh_ingest_description_revised")
    assert sorted(r["paragraph"] for r in revisions) == [2, 3]
    assert {r["node_id"] for r in revisions} == {str(hedin.id)}
    assert revisions[0]["chars_after"] > revisions[0]["chars_before"]
    run = _audit_rows(mesh_runtime, "mesh_ingest_run")[0]
    assert run["accrue_descriptions"] is True and run["descriptions_revised"] == 2
    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert report["store"]["descriptions_revised"] == 2
    # the head did not move: the standing text is a byte-identical prefix ...
    assert hedin.description.startswith(
        "Sven Hedin — Swedish explorer known for expeditions in Central Asia"
    )
    # ... and the name still resolves through the label index (tag row)
    assert mesh_runtime.nodes.get_consolidated_by_label("Sven Hedin") is not None
    # consecutive rows for one node chain: each starts where the last ended
    by_paragraph = {r["paragraph"]: r for r in revisions}
    assert by_paragraph[3]["chars_before"] == by_paragraph[2]["chars_after"]


def test_with_accrual_off_the_write_path_is_todays(
    mesh_runtime: MeshRuntime, tmp_path: Path
) -> None:
    result, _ = _read(mesh_runtime, tmp_path)
    assert result["descriptions_revised"] == 0
    hedin = _hedin(mesh_runtime)
    assert (
        hedin.description == "Sven Hedin — Swedish explorer known for expeditions in Central Asia"
    )
    assert hedin.description_source_chunks == [] and hedin.description_generated_at is None
    assert _audit_rows(mesh_runtime, "mesh_ingest_description_revised") == []
    run = _audit_rows(mesh_runtime, "mesh_ingest_run")[0]
    assert run["accrue_descriptions"] is False and run["descriptions_revised"] == 0
    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert report["store"]["descriptions_revised"] == 0


def test_store_summary_carries_the_counter_with_a_safe_default() -> None:
    assert StoreSummary(nodes_upserted=1, edges_upserted=1).descriptions_revised == 0
    summary = StoreSummary(nodes_upserted=1, edges_upserted=1, descriptions_revised=3)
    assert StoreSummary.model_validate_json(summary.model_dump_json()).descriptions_revised == 3
    with pytest.raises(ValueError):
        StoreSummary(nodes_upserted=1, edges_upserted=1, descriptions_revised=-1)


def test_merge_does_not_split_initials_or_abbreviations_and_dedupes_whole_words() -> None:
    from theogony.mesh.ingestion.kadmos_v2 import _split_sentences

    assert _split_sentences("Born to J. R. R. Tolkien in 1917. He wrote.") == [
        "Born to J. R. R. Tolkien in 1917.",
        "He wrote.",
    ]
    assert _split_sentences("U.S. President. Served two terms.") == [
        "U.S. President.",
        "Served two terms.",
    ]
    assert _split_sentences("Dr. Smith arrived. St. John's hosted.") == [
        "Dr. Smith arrived.",
        "St. John's hosted.",
    ]
    merged = merge_description("Christopher Tolkien — editor", "Born to J. R. R. Tolkien in 1917.")
    assert merged == "Christopher Tolkien — editor. Born to J. R. R. Tolkien in 1917."
    # containment is by whole words: "Rome" is not inside "Romeo"
    assert merge_description("Play — Romeo and Juliet", "Rome.") == "Play — Romeo and Juliet. Rome."
    assert merge_description("City — Rome", "Rome.") is None
    # a closing quote after terminal punctuation is terminal
    assert (
        merge_description('Book — "A tale."', "Written in 1900.")
        == 'Book — "A tale." Written in 1900.'
    )


def test_the_compaction_boundary_flushes_the_pending_revision_before_the_next_paragraph(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_at_compaction: list[str] = []
    original = MeshRuntime.compact

    def spy(self: MeshRuntime, **kwargs):  # type: ignore[no-untyped-def]
        stored_at_compaction.append(_hedin(self).description or "")
        return original(self, **kwargs)

    monkeypatch.setattr(MeshRuntime, "compact", spy)
    _read(mesh_runtime, tmp_path, accrue_descriptions=True, compact_every=2)
    # the boundary falls before paragraph 3: the store holds p2's sentence, not yet p3's
    assert stored_at_compaction == [
        "Sven Hedin — Swedish explorer known for expeditions in Central Asia. "
        "Born in Stockholm in 1865"
    ]
    assert _hedin(mesh_runtime).description == _EXPECTED


def test_the_batch_threshold_flushes_mid_read_and_the_next_mention_builds_on_the_row(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from theogony.mesh.ingestion import kadmos_v2

    monkeypatch.setattr(kadmos_v2, "_REVISION_FLUSH_BATCH", 1)
    result, _ = _read(mesh_runtime, tmp_path, accrue_descriptions=True, compact_every=0)
    assert result["descriptions_revised"] == 2
    hedin = _hedin(mesh_runtime)
    assert hedin.description == _EXPECTED
    assert len(hedin.description_source_chunks) == 2


def test_a_qid_matched_node_keeps_earlier_revisions_across_a_flush(
    mesh_runtime: MeshRuntime, tmp_path: Path
) -> None:
    """The resolver hands a cached copy back on the Q-ID path without a store
    read; after a flush that copy must be the written row, or the next mention
    builds on the pre-revision text and the flush overwrites what was accrued
    (found by review)."""
    from theogony.mesh.schemas import QIDTag

    now = datetime.now(UTC)
    vector = [0.5] * 8
    seeded = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=vector,
        frame_vector=[0.0] * 4,
        description_vector=vector,
        description="Sven Hedin — Swedish explorer",
        tags=["sven hedin", "explorer"],
        qids=[QIDTag(qid="Q44114", confidence=1.0, attached_at=now)],
    )
    mesh_runtime.nodes.append_consolidated(seeded)
    hedin_q = {**_HEDIN, "qids": [{"qid": "Q44114", "confidence": 0.99}]}
    responses = {
        f"PARAGRAPH:\n{_P1}": _reading(
            {**hedin_q, "description": "Crossed the Tibetan Plateau in 1906"}, _PLATEAU
        ),
        f"PARAGRAPH:\n{_P2}": _reading(
            {**hedin_q, "description": "Born in Stockholm in 1865"}, _PLATEAU
        ),
        f"PARAGRAPH:\n{_P3}": _reading(
            {**hedin_q, "description": "Mapped the course of the Brahmaputra River"}
        ),
    }
    reader = MeshParagraphReader(
        mesh_runtime,
        llm=StubLLMProvider(responses=responses),
        max_paragraphs=10,
        accrue_descriptions=True,
        compact_every=2,
    )
    result = asyncio.run(
        reader.read_text(
            text=_TEXT,
            source_type="test",
            source_identifier="hedin-qid",
            title="Hedin",
            anchor=str(tmp_path / "hedin.txt"),
        )
    )
    revisions = _audit_rows(mesh_runtime, "mesh_ingest_description_revised")
    signals = {r["signal"] for r in revisions}
    assert signals == {"qid"}, signals
    assert result["descriptions_revised"] == 3
    node = mesh_runtime.nodes.get_consolidated(str(seeded.id))
    assert node is not None
    assert node.description == (
        "Sven Hedin — Swedish explorer. Crossed the Tibetan Plateau in 1906. "
        "Born in Stockholm in 1865. Mapped the course of the Brahmaputra River"
    )
    assert len(node.description_source_chunks) == 3


def test_merge_handles_quotes_acronyms_and_clause_punctuation() -> None:
    from theogony.mesh.ingestion.kadmos_v2 import _split_sentences

    assert _split_sentences('He said "Yes." Then left.') == ['He said "Yes."', "Then left."]
    assert _split_sentences("Earned a Ph.D. in physics. Taught.") == [
        "Earned a Ph.D. in physics.",
        "Taught.",
    ]
    # a quoted repeat of the standing text is not new
    assert merge_description("Zeus — King of the gods", '"King of the gods."') is None
    # clause punctuation at the end of the standing text is separation enough
    assert merge_description("Zeus — King of the gods,", "Son of Cronos.") == (
        "Zeus — King of the gods, Son of Cronos."
    )
    # a glued regnal unit whose parts are all present is not appended
    assert merge_description("Charles V — Emperor. He ruled.", "Charles V. He ruled.") is None


@pytest.mark.parametrize("where", ["end", "boundary", "threshold"])
def test_a_failing_flush_keeps_edges_and_audit_rows_and_records_the_failure(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """Honest failure: the embed call at flush time may raise; the edges and the
    staged audit rows land anyway, a row says the revisions never reached the
    store, and the exception surfaces."""
    from theogony.mesh.ingestion import kadmos_v2
    from theogony.mesh.ingestion.vectorizer import MeshTextVectorizer

    kwargs = {"end": {"compact_every": 0}, "boundary": {"compact_every": 2}}.get(where, {})
    if where == "threshold":
        monkeypatch.setattr(kadmos_v2, "_REVISION_FLUSH_BATCH", 1)

    async def flaky(self, texts):  # type: ignore[no-untyped-def]
        # the concepts of a paragraph are embedded through the same method; fail
        # only on a revised description (name head plus an appended sentence)
        if any(" — " in t and ". " in t for t in texts):
            raise RuntimeError("embedder down")
        return [[float(len(t) % 7)] * self.semantic_dim for t in texts]

    monkeypatch.setattr(MeshTextVectorizer, "description_many", flaky)
    with pytest.raises(RuntimeError, match="embedder down"):
        _read(mesh_runtime, tmp_path, accrue_descriptions=True, **kwargs)
    assert mesh_runtime.edges.load_all_edges(), "the buffered edges landed"
    assert _audit_rows(mesh_runtime, "mesh_ingest_link_decision"), "the staged rows landed"
    failed = _audit_rows(mesh_runtime, "mesh_ingest_description_flush_failed")
    assert len(failed) == 1 and failed[0]["pending"] >= 1
    assert "embedder down" in failed[0]["error"]
    hedin = _hedin(mesh_runtime)
    assert (
        hedin.description == "Sven Hedin — Swedish explorer known for expeditions in Central Asia"
    )
