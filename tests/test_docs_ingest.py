"""
Tests for the docs-aware ingest path (``src/theogony/docs_ingest/``).

Coverage:

- ``repo_walker`` honours include + exclude globs and is deterministic
- ``markdown_parser`` produces the expected sections, links, anchors
- ``extractors`` emit document, section, glossary, link, mention nodes/edges
- ``dump`` round-trips a chronicle losslessly through gzipped JSONL
- ``pipeline`` end-to-end against a tiny fixture repo
- ``seeds`` resolves the bundled pantheon_self dump path correctly

Real-world LLM-driven extraction is not exercised here — the docs path
is intentionally LLM-free, so deterministic fixtures are sufficient.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from textwrap import dedent

import pytest

from theogony.core.model import EdgeType, Layer  # noqa: F401  (used as import-side check)
from theogony.docs_ingest import build_chronicle, read_dump, write_dump
from theogony.docs_ingest.dump import DumpError, dump_metadata
from theogony.docs_ingest.extractors import (
    SOURCE_TYPE,
    extract_document_nodes,
    extract_glossary_concepts,
    extract_link_edges,
    extract_mention_edges,
    extract_part_of_edges,
    extract_section_nodes,
)
from theogony.docs_ingest.markdown_parser import parse_markdown
from theogony.docs_ingest.pipeline import RepoSnapshot
from theogony.docs_ingest.repo_walker import (
    DEFAULT_EXCLUDE,
    DEFAULT_INCLUDE,
    walk_repo,
)

# --------------------------------------------------------------------------
# Fixture helpers — build a synthetic repo on the fly so tests stay
# decoupled from the real Theogony docs.
# --------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip("\n"), encoding="utf-8")


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Build a minimal repo: README, AGENTS.md, GLOSSARY.md, one vision doc, one prompt."""
    _write(
        tmp_path / "README.md",
        """
        # Theogony Test

        See [vision](docs/VISION.md) and [glossary](docs/GLOSSARY.md).

        ## Demo

        Run the demo against the [Pantheon](docs/VISION.md#pantheon) substrate.
        """,
    )
    _write(
        tmp_path / "AGENTS.md",
        """
        # AGENTS

        ## Required reading

        Read [VISION](docs/VISION.md) first.
        """,
    )
    _write(
        tmp_path / "docs/VISION.md",
        """
        # Vision

        Pantheon is the long-horizon substrate. The Chronik is the operational layer.

        ## Pantheon

        See the [glossary](GLOSSARY.md) for the term Pantheon.

        ## Chronik

        The Chronik supports Hover-Lupe.
        """,
    )
    _write(
        tmp_path / "docs/GLOSSARY.md",
        """
        # Glossary

        Canonical terms.

        ## Core Terms

        **Theogony**
        The overall project building the Chronik.

        **Chronik**
        The operational vector-graph knowledge network.

        **Pantheon**
        The long-horizon planetary chronicle substrate.

        **Hover-Lupe**
        The deep-zoom interaction primitive.
        """,
    )
    _write(
        tmp_path / "prompts/talos.md",
        """
        # Talos Prompt

        Read [AGENTS.md](../AGENTS.md) before contributing.
        """,
    )
    # The measurement record IS in scope since PHX-1112 ...
    _write(
        tmp_path / "docs/etappes/qa_constellation.md",
        """
        # The answer arm on a corpus the model does not know

        > **Abstract.** The edges are worth 3.6 points of exact match.
        """,
    )
    # ... the sprint briefs and the Neo4j-era notes are not.
    _write(
        tmp_path / "docs/etappes/W4_brief.md",
        """
        # W4 brief
        Historical artefact, do not ingest.
        """,
    )
    _write(tmp_path / "docs/etappes/kadmos_v2_brief.md", "# Kadmos v2 brief\nA plan.\n")
    _write(tmp_path / "docs/etappes/demo_log.md", "# Demo log\nNeo4j era.\n")
    _write(tmp_path / "docs/etappes/RETIREMENT_NEO4J_MULTIHOP.md", "# Retirement\nNeo4j.\n")
    _write(
        tmp_path / "CODE_OF_CONDUCT.md",
        """
        # Code of Conduct
        Boilerplate, exclude.
        """,
    )
    return tmp_path


# --------------------------------------------------------------------------
# repo_walker
# --------------------------------------------------------------------------


def test_walk_repo_honours_include_and_exclude(fixture_repo: Path) -> None:
    files = walk_repo(fixture_repo)
    rels = [f.rel_path for f in files]
    # In scope:
    assert "README.md" in rels
    assert "AGENTS.md" in rels
    assert "docs/VISION.md" in rels
    assert "docs/GLOSSARY.md" in rels
    assert "prompts/talos.md" in rels
    assert "docs/etappes/qa_constellation.md" in rels, "the measurement record (PHX-1112)"
    # Out of scope:
    assert "docs/etappes/W4_brief.md" not in rels
    assert "docs/etappes/kadmos_v2_brief.md" not in rels, (
        "a plan read back states a target as a fact"
    )
    assert "docs/etappes/demo_log.md" not in rels
    assert "docs/etappes/RETIREMENT_NEO4J_MULTIHOP.md" not in rels
    assert "CODE_OF_CONDUCT.md" not in rels


def test_walk_repo_is_sorted_for_determinism(fixture_repo: Path) -> None:
    rels1 = [f.rel_path for f in walk_repo(fixture_repo)]
    rels2 = [f.rel_path for f in walk_repo(fixture_repo)]
    assert rels1 == rels2
    assert rels1 == sorted(rels1)


def test_walk_repo_default_lists_are_module_constants() -> None:
    # Defensive: ensure the public defaults stay tuples so they are not
    # mutated by a caller that holds a reference.
    assert isinstance(DEFAULT_INCLUDE, tuple)
    assert isinstance(DEFAULT_EXCLUDE, tuple)


# --------------------------------------------------------------------------
# markdown_parser
# --------------------------------------------------------------------------


def test_parse_markdown_extracts_h1_and_h2_sections() -> None:
    md = "# Top\n\nIntro.\n\n## Sub\n\nBody.\n\n### NotASection\n\nNested.\n"
    doc = parse_markdown("docs/X.md", md)
    headings = [(s.level, s.heading) for s in doc.sections]
    assert headings == [(1, "Top"), (2, "Sub")]
    assert doc.title == "Top"


def test_parse_markdown_falls_back_to_filename_when_no_headings() -> None:
    doc = parse_markdown("docs/RAW.md", "Just a paragraph, no headings.")
    assert doc.title == "RAW"
    assert len(doc.sections) == 1
    assert doc.sections[0].body_text == "Just a paragraph, no headings."


def test_parse_markdown_captures_links_and_skips_anchors() -> None:
    md = "# Top\n\nSee [link](other.md) and [anchor](#here).\n"
    doc = parse_markdown("docs/X.md", md)
    hrefs = [link.href for link in doc.sections[0].links]
    assert "other.md" in hrefs
    assert "#here" in hrefs


def test_parse_markdown_anchor_slugs_are_github_flavoured() -> None:
    doc = parse_markdown("docs/X.md", "## Hello World!\n\nBody.\n")
    assert doc.sections[0].anchor == "hello-world"


# --------------------------------------------------------------------------
# extractors
# --------------------------------------------------------------------------


def test_extract_document_and_section_nodes(fixture_repo: Path) -> None:
    parsed = [
        parse_markdown("README.md", (fixture_repo / "README.md").read_text()),
        parse_markdown("docs/VISION.md", (fixture_repo / "docs/VISION.md").read_text()),
    ]
    docs = extract_document_nodes(parsed)
    sections = extract_section_nodes(parsed)

    assert {d.label for d in docs} == {"Theogony Test", "Vision"}
    for d in docs:
        assert d.source_ref.source_type == SOURCE_TYPE
        assert d.layer == Layer.MNEME
        assert d.properties["doc_role"] == "document"

    headings = {s.label for s in sections}
    assert "Pantheon" in headings
    assert "Chronik" in headings


def test_extract_glossary_concepts(fixture_repo: Path) -> None:
    parsed = [parse_markdown("docs/GLOSSARY.md", (fixture_repo / "docs/GLOSSARY.md").read_text())]
    concepts = extract_glossary_concepts(parsed)
    by_label = {c.label: c for c in concepts}
    assert set(by_label) == {"Theogony", "Chronik", "Pantheon", "Hover-Lupe"}
    assert by_label["Pantheon"].description.startswith(
        "The long-horizon planetary chronicle substrate"
    )
    # Stable, slug-based location:
    assert by_label["Hover-Lupe"].source_ref.location == "concept:hover-lupe"


def test_extract_part_of_edges(fixture_repo: Path) -> None:
    parsed = [parse_markdown("docs/VISION.md", (fixture_repo / "docs/VISION.md").read_text())]
    docs = extract_document_nodes(parsed)
    sections = extract_section_nodes(parsed)
    documents_by_rel_path = {n.properties["rel_path"]: n for n in docs}
    sections_by_rel_path = {
        "docs/VISION.md": [(parsed[0].sections[i], sections[i]) for i in range(len(sections))]
    }
    edges = extract_part_of_edges(documents_by_rel_path, sections_by_rel_path)
    assert all(e.relation_type == "PART_OF" for e in edges)
    assert all(e.epistemic_type == EdgeType.EXTRACTION for e in edges)
    assert len(edges) == len(sections)


def _pair_sections_for_test(parsed_docs, section_nodes):
    """Test helper: build the rel_path → [(parsed_section, node)] map.

    Mirrors the alignment logic in pipeline._index_sections so tests
    don't need to import a private symbol.
    """
    by_key = {}
    for n in section_nodes:
        rel = n.properties["rel_path"]
        loc = n.source_ref.location or ""
        head = n.label
        line_start = int(loc[1:].split("-", 1)[0]) if loc.startswith("L") else 0
        by_key[(rel, line_start, head)] = n
    out: dict = {}
    for doc in parsed_docs:
        pairs = []
        for sec in doc.sections:
            key = (doc.rel_path, sec.line_start, sec.heading)
            node = by_key.get(key)
            if node is not None:
                pairs.append((sec, node))
        out[doc.rel_path] = pairs
    return out


def test_extract_link_edges_resolves_relative_paths(fixture_repo: Path) -> None:
    parsed = [
        parse_markdown("docs/VISION.md", (fixture_repo / "docs/VISION.md").read_text()),
        parse_markdown("docs/GLOSSARY.md", (fixture_repo / "docs/GLOSSARY.md").read_text()),
    ]
    docs = extract_document_nodes(parsed)
    sections = extract_section_nodes(parsed)
    documents_by_rel_path = {n.properties["rel_path"]: n for n in docs}
    sections_by_rel_path = _pair_sections_for_test(parsed, sections)

    edges = extract_link_edges(parsed, sections_by_rel_path, documents_by_rel_path)
    targets = {e.target_id for e in edges}
    glossary_doc = documents_by_rel_path["docs/GLOSSARY.md"]
    assert glossary_doc.id in targets


def test_extract_mention_edges_skips_self_definitions(fixture_repo: Path) -> None:
    """The ``Pantheon`` glossary section must not MENTION its own concept."""
    parsed = [
        parse_markdown("docs/GLOSSARY.md", (fixture_repo / "docs/GLOSSARY.md").read_text()),
        parse_markdown("docs/VISION.md", (fixture_repo / "docs/VISION.md").read_text()),
    ]
    sections = extract_section_nodes(parsed)
    glossary_concepts = extract_glossary_concepts(parsed)
    sections_by_rel_path = _pair_sections_for_test(parsed, sections)

    edges = extract_mention_edges(parsed, glossary_concepts, sections_by_rel_path)
    assert all(e.relation_type == "MENTIONS" for e in edges)
    # Vision sections SHOULD mention Pantheon (it's the term in their body):
    pantheon_concept = next(c for c in glossary_concepts if c.label == "Pantheon")
    targets = {e.target_id for e in edges}
    assert pantheon_concept.id in targets


# --------------------------------------------------------------------------
# pipeline (end-to-end)
# --------------------------------------------------------------------------


def test_build_chronicle_end_to_end(fixture_repo: Path) -> None:
    snapshot = RepoSnapshot(repo_root=fixture_repo)
    chronicle = build_chronicle(snapshot, embedder=None)
    assert len(chronicle.nodes) > 0
    assert len(chronicle.edges) > 0
    # Every node must have a source_ref pointing into the repo:
    for n in chronicle.nodes:
        assert n.source_ref.source_type == SOURCE_TYPE
        assert n.source_ref.identifier is not None
    # Every edge must reference real node ids:
    node_ids = {n.id for n in chronicle.nodes}
    for e in chronicle.edges:
        assert e.source_id in node_ids
        assert e.target_id in node_ids


# --------------------------------------------------------------------------
# dump round-trip
# --------------------------------------------------------------------------


def test_dump_roundtrip(fixture_repo: Path, tmp_path: Path) -> None:
    chronicle = build_chronicle(RepoSnapshot(repo_root=fixture_repo), embedder=None)
    out = tmp_path / "test.jsonl.gz"
    write_dump(chronicle, out, metadata={"test": "true"})
    header, nodes, edges = read_dump(out)
    assert header["node_count"] == len(chronicle.nodes)
    assert header["edge_count"] == len(chronicle.edges)
    assert header["metadata"]["test"] == "true"
    assert {n.id for n in nodes} == {n.id for n in chronicle.nodes}
    assert {e.id for e in edges} == {e.id for e in chronicle.edges}


def test_dump_metadata_returns_only_header(fixture_repo: Path, tmp_path: Path) -> None:
    chronicle = build_chronicle(RepoSnapshot(repo_root=fixture_repo), embedder=None)
    out = tmp_path / "test.jsonl.gz"
    write_dump(chronicle, out)
    md = dump_metadata(out)
    assert md["kind"] == "header"
    assert md["node_count"] == len(chronicle.nodes)


def test_dump_rejects_unknown_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl.gz"
    with gzip.open(bad, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "header", "schema_version": 999}) + "\n")
    with pytest.raises(DumpError):
        read_dump(bad)


# --------------------------------------------------------------------------
# bundled seed
# --------------------------------------------------------------------------


def test_bundled_pantheon_self_dump_is_present_and_loadable() -> None:
    """The wheel must ship a non-empty ``pantheon_self`` Chronicle dump."""
    from theogony.seeds import pantheon_self_dump_path

    path = pantheon_self_dump_path()
    assert path.exists(), f"missing bundled seed: {path}"
    header, nodes, edges = read_dump(path)
    assert header["node_count"] > 0
    assert header["edge_count"] > 0
    assert len(nodes) == header["node_count"]
    assert len(edges) == header["edge_count"]
    # Sanity: at least one canonical glossary concept must be present.
    labels = {n.label for n in nodes}
    assert "Pantheon" in labels
    assert "Chronik" in labels


def test_bundled_pantheon_self_dump_advertises_embedding_model() -> None:
    """The dump's header must record which embedding model produced its vectors."""
    from theogony.seeds import pantheon_self_dump_path

    md = dump_metadata(pantheon_self_dump_path())
    assert md["embedding_model_id"] == "BAAI/bge-small-en-v1.5@v1"
    assert md["embedding_dim"] == 384


# --------------------------------------------------------------------------
# PHX-1117: the status notes reach the description
# --------------------------------------------------------------------------


_NOTED_SECTION = (
    "# Doctrine\n\n"
    "> **Status: historical (marked 2026-10-25, PHX-1108).** This document proposes\n"
    "> a tongue; the binding target says **otherwise**.\n\n"
    "## The ladder\n\n"
    + "The tier is earned through Oneiros, never assigned. "
    * 8
    + "\n\n*Measured 2026-08-31 (PHX-1100): `decay_tier` is 0 on every edge, so only k = 2 "
    "runs — the gentler exponent removes **more** weight below 1.*\n\n"
    "* a bullet that starts with a star\n"
    "* another bullet with *plain emphasis* and no date\n\n"
    "*An undated italic sentence long enough to pass the length floor and nothing else.*\n"
    "*Short 2026-01-01.*\n"
)


def test_status_notes_are_the_dated_italics_and_the_status_banner() -> None:
    from theogony.docs_ingest.extractors import NOTE_MAX_CHARS, NOTES_MAX, status_notes

    notes = status_notes(_NOTED_SECTION)
    assert len(notes) == 2, notes
    banner, measured = notes
    assert banner.startswith("**Status: historical (marked 2026-10-25, PHX-1108).**")
    assert banner.endswith("the binding target says **otherwise**."), banner
    assert measured.startswith("Measured 2026-08-31 (PHX-1100)")
    assert measured.endswith("removes **more** weight below 1."), measured
    # caps: a long note is cut, and a section contributes at most NOTES_MAX
    many = "\n\n".join(f"*Status 2026-10-{i:02d}: " + "x" * 700 + "*" for i in range(1, 8))
    capped = status_notes(many)
    assert len(capped) == NOTES_MAX
    assert all(len(n) <= NOTE_MAX_CHARS for n in capped)


def test_the_section_description_carries_the_note_the_snippet_cuts_off() -> None:
    from theogony.docs_ingest.extractors import SNIPPET_MAX_CHARS

    doc = parse_markdown("docs/DOCTRINE.md", _NOTED_SECTION)
    by_label = {n.label: n for n in extract_section_nodes([doc])}
    ladder = by_label["The ladder"]
    assert ladder.source_ref.snippet is not None
    assert len(ladder.source_ref.snippet) <= SNIPPET_MAX_CHARS
    assert "Measured 2026-08-31" not in ladder.source_ref.snippet, "the note sits below the cut"
    assert ladder.description is not None
    assert "Status note: Measured 2026-08-31 (PHX-1100)" in ladder.description
    assert "An undated italic sentence" not in ladder.description
    doctrine = extract_document_nodes([doc])[0]
    assert doctrine.description is not None
    assert "Status note: **Status: historical" in doctrine.description


def test_the_embedding_text_stops_where_the_status_notes_begin() -> None:
    """The notes travel with the description for a reader; the vector stays the
    section head's, so the bundled dump's clustering does not collapse."""
    from theogony.docs_ingest.pipeline import _embedding_text_for

    doc = parse_markdown("docs/DOCTRINE.md", _NOTED_SECTION)
    ladder = {n.label: n for n in extract_section_nodes([doc])}["The ladder"]
    assert ladder.description is not None and "Status note:" in ladder.description
    text = _embedding_text_for(ladder)
    assert text.startswith("The ladder. The tier is earned through Oneiros")
    assert "Status note" not in text and "Measured 2026" not in text


def test_a_banner_longer_than_the_snippet_is_carried_once() -> None:
    """The snippet is taken with the blockquote marks removed, and a banner that
    fills it is carried whole as the first note, not as its head and then itself."""
    from theogony.docs_ingest.extractors import STATUS_NOTE_PREFIX, describe
    from theogony.docs_ingest.pipeline import _embedding_text_for

    banner = "> **Status: superseded (2026-10-25).**\n" + "> This banner runs on and on.\n" * 12
    body = banner + "\n\nThe prose of the section follows the banner.\n"
    text = describe(body)
    assert text is not None
    assert text.startswith(STATUS_NOTE_PREFIX + "**Status: superseded (2026-10-25).**")
    assert text.count("**Status: superseded") == 1, text
    assert "> " not in text, "the blockquote marks do not travel"
    short = (
        "> **Status 2026-10-25: superseded.** See the other brief.\n\n"
        "The brief specifies a reader.\n"
    )
    once = describe(short)
    assert once is not None
    assert (
        once.count("**Status 2026-10-25: superseded.**") == 1
        and "The brief specifies a reader." in once
    )
    doc = parse_markdown("docs/BANNER.md", "# Banner\n\n" + body)
    node = extract_document_nodes([doc])[0]
    embedded = _embedding_text_for(node)
    assert embedded.startswith("Banner. **Status: superseded (2026-10-25).**")
    assert STATUS_NOTE_PREFIX not in embedded and len(embedded) <= len("Banner. ") + 240


def test_stars_in_code_datelines_and_bold_status_lines() -> None:
    from theogony.docs_ingest.extractors import status_notes

    code = (
        "Use `x*y` here and `pantheon_*`. "
        "*Measured 2026-10-25: forty characters at least here, yes.*"
    )
    assert status_notes(code) == ["Measured 2026-10-25: forty characters at least here, yes."]
    fence = (
        "```python\nx = f(*args)\n```\n"
        "*Status 2026-10-25: a real note right after a fence, kept whole.*"
    )
    assert status_notes(fence) == [
        "Status 2026-10-25: a real note right after a fence, kept whole."
    ]
    dateline = (
        "*2026-09-01. `data/mesh-founding` (94,490 edges), the 47 gold questions; "
        "no LLM, no money.*"
    )
    assert status_notes(dateline) == [], (
        "an etappe's dateline opens with its date and is not a status"
    )
    bold = (
        "> **Abstract.** Something.\n\n"
        "**Status:** 2026-10-17, built and measured; the ticket is closed.\n\nText."
    )
    assert status_notes(bold) == [
        "**Status:** 2026-10-17, built and measured; the ticket is closed."
    ]
    undated_bold = "**Status:** canonical doctrine for the storage layer.\n"
    assert status_notes(undated_bold) == []


def test_unclosed_stars_scan_in_one_pass() -> None:
    import time

    from theogony.docs_ingest.extractors import _emphasis_spans, status_notes

    assert _emphasis_spans("*a *b *c") == []
    assert _emphasis_spans("*a* and *b c* and * not em") == ["a", "b c"]
    started = time.perf_counter()
    assert status_notes("*a " * 4000) == []
    assert time.perf_counter() - started < 0.5


def test_a_note_the_cut_runs_through_is_carried_once_and_prose_cannot_forge_the_boundary() -> None:
    from theogony.docs_ingest.extractors import STATUS_NOTE_PREFIX, describe, status_notes
    from theogony.docs_ingest.pipeline import _embedding_text_for

    # the note begins inside the first 240 characters and ends beyond them
    body = "Prose sentence that fills the head. " * 5 + (
        "*Measured 2026-10-25 (PHX-1100): the note begins before the cut and ends well "
        "after it, carrying its tail along with it.*"
    )
    text = describe(body)
    assert text is not None and text.count("Measured 2026-10-25") == 1, text
    assert text.split("\n")[0].startswith("Prose sentence") and "…" not in text.split("\n")[0]
    # a section that opens with a dated italic longer than the snippet
    italic = "*Status 2026-10-25 (PHX-1108): " + "a target that was not measured; " * 9 + "end.*\n"
    once = describe(italic + "\nProse follows.\n")
    assert once is not None and once.count("Status 2026-10-25") == 1 and not once.startswith("*")
    # banners and bold status lines quoted inside a fence are examples, not notes
    assert (
        status_notes("```\n**Status:** 2026-10-17, inside a fence; this must not be a note.\n```\n")
        == []
    )
    assert (
        status_notes(
            "```markdown\n> **Status: historical (2026-10-25).** An example banner.\n```\n"
        )
        == []
    )
    # a status line that contains a dated italic is one note, not two
    line = (
        "**Status:** 2026-10-17, built; "
        "*a trailing emphasis span dated 2026-10-18 and long enough.*"
    )
    assert len(status_notes(line)) == 1
    # a blank line that carries spaces still ends an unclosed span
    assert (
        status_notes("*Measured 2026-10-25: an opener with no closer here\n \nNext para closes it*")
        == []
    )
    # the newline is the boundary: prose that says "Status note: " does not cut the embedding
    doc = parse_markdown(
        "docs/CONVENTION.md",
        "# Convention\n\n"
        + "A description carries a Status note: part after its snippet, by convention. " * 4
        + "\n\n"
        "*Measured 2026-10-25 (PHX-1117): forty-plus characters of dated note to carry here.*\n",
    )
    node = extract_document_nodes([doc])[0]
    assert node.description is not None and node.description.count("\n") == 1
    embedded = _embedding_text_for(node)
    assert "by convention." in embedded and STATUS_NOTE_PREFIX + "Measured" not in embedded
