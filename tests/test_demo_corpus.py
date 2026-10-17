"""The bundled demo corpus and its recorded readings stay whole (PHX-1112).

`theogony mesh demo` replays `hesiod_theogony_readings.jsonl.gz` over
`hesiod_theogony.txt`. A paragraph the readings do not cover would replay as a
schema failure — a mesh with a silent hole — and a reading that no longer
validates against the reader's schema would do the same. Both are checked
here without an embedder, in well under a second.
"""

from __future__ import annotations

import re

from theogony.mesh.ingestion.reading_schemas import ParagraphReadingOutput
from theogony.mesh.ingestion.replay import (
    load_readings,
    load_readings_meta,
    paragraphs_of,
    reading_key,
    readings_for_text,
)
from theogony.seeds import DEMO_CORPUS, demo_corpus_path, demo_readings_path


def test_the_corpus_is_the_theogony_alone_without_gutenberg_apparatus() -> None:
    text = demo_corpus_path().read_text(encoding="utf-8")
    paragraphs = paragraphs_of(text)
    assert len(paragraphs) == 95
    assert paragraphs[0].startswith("(ll. 1-25) From the Heliconian Muses")
    assert paragraphs[-1].startswith("(ll. 1021-1022)")
    assert "Project Gutenberg" not in text
    assert "THE CATALOGUES OF WOMEN" not in text, "the next work in the volume is not included"
    # Evelyn-White's endnote markers were bare numbers in the Gutenberg text
    assert not re.search(r"(?<![\w(-])16[0-3]\d(?![\w)-])", text)
    assert DEMO_CORPUS.anchor.startswith("https://www.gutenberg.org/ebooks/348")
    assert "public domain" in DEMO_CORPUS.provenance.lower()


def test_every_paragraph_has_a_reading_that_the_reader_would_accept() -> None:
    text = demo_corpus_path().read_text(encoding="utf-8")
    readings = load_readings(demo_readings_path())
    by_paragraph = readings_for_text(text, readings)
    paragraphs = paragraphs_of(text)
    missing = [p[:60] for p in paragraphs if p not in by_paragraph]
    assert not missing, missing
    assert len(readings) == len(paragraphs), "no reading for a paragraph that is not in the text"
    concepts = relations = 0
    for paragraph in paragraphs:
        output = ParagraphReadingOutput.model_validate(by_paragraph[paragraph])
        assert output.concepts, paragraph[:60]
        concepts += len(output.concepts)
        relations += len(output.relations)
    assert concepts > 800 and relations > 800, (concepts, relations)
    assert {
        c.label
        for p in paragraphs
        for c in ParagraphReadingOutput.model_validate(by_paragraph[p]).concepts
    } >= {"Zeus", "Cronos", "Earth"}


def test_the_readings_say_what_recorded_them() -> None:
    meta = load_readings_meta(demo_readings_path())
    assert meta["paragraphs"] == 95 and meta["readings"] == 95
    assert meta["model_ids"], "every reading row names the model that answered it"
    assert sum(meta["model_ids"].values()) == 95
    assert meta["recorded_at"].startswith("2026-")
    assert "paragraph_prompt" in meta["prompt"], "recorded with the reader's own prompt"
    assert "reading_key" in meta["key"]


def test_the_key_is_the_stripped_paragraph() -> None:
    """The replay looks a paragraph up by the string the reader strips out of
    the text; the recorder must have hashed exactly that."""
    text = demo_corpus_path().read_text(encoding="utf-8")
    readings = load_readings(demo_readings_path())
    first = paragraphs_of(text)[0]
    assert reading_key(first) in readings
    assert reading_key(first + "\n") not in readings
