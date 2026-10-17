"""Rebuilding a mesh from recorded readings — the shipped path (PHX-1112).

The replay provider was built for the 2Wiki answer arm (PHX-1110) and lived in
the evaluation module; `theogony mesh demo` made it a path an arriving agent
takes, so it moved to `mesh.ingestion.replay`. What these tests pin: the
recorder and the reader send the identical prompt, a readings file round-trips
through gzip with its meta row, a plain text replays through the shipped reader
with the key taken from the stripped paragraph, and a paragraph without a
reading is a miss on the record rather than a paragraph with no concepts.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

from theogony.mesh.eval import qa_mesh
from theogony.mesh.ingestion.kadmos_v2 import SYSTEM_PROMPT, paragraph_prompt
from theogony.mesh.ingestion.replay import (
    MIN_PARAGRAPH_CHARS,
    ReplayReadingProvider,
    load_readings,
    load_readings_meta,
    paragraphs_of,
    reading_key,
    readings_for_text,
    replay_text,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

TEXT = """Marie of Hanover was the daughter of George V of Hanover.
She died in Gmunden.

George V of Hanover was the last King of Hanover and the son of Ernest Augustus.

Short.

Lake Traunsee lies beside the town of Gmunden in Austria.
"""


def _reading(*concepts: tuple[str, str], relations: list[tuple[str, str, str]]) -> dict:
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


def _readings() -> dict[str, dict]:
    marie, george, _lake = paragraphs_of(TEXT)
    return {
        reading_key(marie): _reading(
            ("Marie of Hanover", "Daughter of George V of Hanover; died in Gmunden."),
            ("George V of Hanover", "King of Hanover, father of Marie."),
            relations=[("Marie of Hanover", "daughter of", "George V of Hanover")],
        ),
        reading_key(george): _reading(
            ("George V of Hanover", "Last King of Hanover, son of Ernest Augustus."),
            ("Ernest Augustus", "King of Hanover, father of George V."),
            relations=[("George V of Hanover", "son of", "Ernest Augustus")],
        ),
        # the lake has no reading: the replay must report it, not invent one
    }


def test_the_recorder_and_the_reader_send_one_prompt() -> None:
    """What the recorder stores is what Kadmos would have read only if the two
    prompts are the same string; the replay finds the paragraph again under it."""
    paragraph = "Marie of Hanover was the daughter of George V of Hanover.\nShe died in Gmunden."
    prompt = paragraph_prompt(paragraph)
    assert prompt.startswith("PARAGRAPH:\n") and prompt.endswith(
        "\n\nExtract the concepts, relations, and paragraph concept."
    )
    assert ReplayReadingProvider.paragraph_in(prompt) == paragraph
    assert ReplayReadingProvider.paragraph_in("something else") is None
    assert "Kadmos" in SYSTEM_PROMPT


def test_paragraphs_are_the_readers_paragraphs() -> None:
    """Stripped, blank-line separated, nothing under the reader's cut-off — and
    capped in the reader's order, before the filter, so a heading inside the
    first N costs a slot exactly as it does on a live read."""
    paragraphs = paragraphs_of(TEXT)
    assert len(paragraphs) == 3 and all(len(p) >= MIN_PARAGRAPH_CHARS for p in paragraphs)
    assert paragraphs[0].startswith("Marie of Hanover") and "\n" in paragraphs[0]
    assert "Short." not in paragraphs
    assert len(paragraphs_of(TEXT, max_paragraphs=3)) == 2, "the third raw paragraph is 'Short.'"
    assert len(paragraphs_of(TEXT, max_paragraphs=4)) == 3


def test_readings_are_rekeyed_by_paragraph_and_empty_ones_dropped() -> None:
    readings = _readings()
    readings[reading_key(paragraphs_of(TEXT)[2])] = {}  # a failed recording
    by_paragraph = readings_for_text(TEXT, readings)
    assert set(by_paragraph) == set(paragraphs_of(TEXT)[:2])


def test_a_readings_file_round_trips_through_gzip_with_its_meta_row(tmp_path: Path) -> None:
    path = tmp_path / "readings.jsonl.gz"
    meta = {"title": "t", "model_ids": {"m": 2}}
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"meta": meta}) + "\n")
        for key, reading in _readings().items():
            fh.write(json.dumps({"key": key, "model_id": "m", "reading": reading}) + "\n")
        fh.write("not json\n")
        fh.write(json.dumps({"key": "empty", "reading": None}) + "\n")
    loaded = load_readings(path)
    assert set(loaded) == set(_readings()) | {"empty"}
    assert loaded["empty"] == {}
    assert load_readings_meta(path) == meta
    plain = tmp_path / "readings.jsonl"
    plain.write_text(json.dumps({"key": "k", "reading": {"concepts": []}}) + "\n")
    assert load_readings(plain) == {"k": {"concepts": []}}
    assert load_readings_meta(plain) == {}


def test_a_text_replays_through_the_shipped_reader(tmp_path: Path) -> None:
    runtime = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=8)
    calls: list[int] = []
    result = asyncio.run(
        replay_text(
            runtime,
            TEXT,
            _readings(),
            source_type="text",
            source_identifier="hanover",
            title="Hanover",
            anchor="hanover",
            on_call=calls.append,
        )
    )
    assert (result.paragraphs, result.hits, result.misses) == (3, 2, 1)
    assert calls == [1, 2, 3]
    capped = asyncio.run(
        replay_text(
            MeshRuntime(tmp_path / "capped", semantic_dim=8, frame_dim=8),
            TEXT,
            _readings(),
            source_type="text",
            source_identifier="hanover",
            title="Hanover",
            anchor="hanover",
            max_paragraphs=3,
        )
    )
    assert (capped.paragraphs, capped.hits, capped.misses) == (2, 2, 0), (
        "counted from what the reader read: the cap took 'Short.' and the reader skipped it"
    )
    assert runtime.nodes.chunk_count() == 3, "one chunk per paragraph, the unreadable one included"
    names = {
        n.tags[0] for n in runtime.nodes.iter_consolidated() if n.tags and not n.is_source_anchor
    }
    assert {"Marie of Hanover", "George V of Hanover", "Ernest Augustus"} <= names
    assert any(e.relation_descriptor == "daughter of" for e in runtime.edges.load_all_edges())
    assert result.report["llm_calls"] == 3 and result.report["llm_cost_eur"] == 0.0
    anchors = [n for n in runtime.nodes.iter_consolidated() if n.is_source_anchor]
    assert any("Hanover" in (a.description or "") for a in anchors)


def test_the_harness_still_imports_the_replay_from_where_phx_1110_left_it() -> None:
    """Scripts and the 2Wiki harness import these names from `qa_mesh`."""
    assert qa_mesh.ReplayReadingProvider is ReplayReadingProvider
    assert qa_mesh.reading_key is reading_key
    assert qa_mesh.load_readings is load_readings
    assert qa_mesh.ReplayIngestReport.__name__ == "ReplayReport"
