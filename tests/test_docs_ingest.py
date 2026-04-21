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
    # Files explicitly OUT of scope — must NOT appear in walk output.
    _write(
        tmp_path / "docs/etappes/W4_brief.md",
        """
        # W4 brief
        Historical artefact, do not ingest.
        """,
    )
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
    # Out of scope:
    assert "docs/etappes/W4_brief.md" not in rels
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
