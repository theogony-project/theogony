"""
Deterministic extractors that turn :class:`ParsedDocument` instances
into Chronik nodes and edges.

Five extractors, each with a single responsibility:

1. :func:`extract_document_nodes`  — one ``concept`` node per .md file
2. :func:`extract_section_nodes`   — one ``concept`` node per H1/H2
3. :func:`extract_glossary_concepts` — one ``concept`` node per glossary
   term (special handling of ``docs/GLOSSARY.md``)
4. :func:`extract_link_edges`      — Markdown ``[text](href)`` →
   ``LINKS_TO`` edges between sections / documents
5. :func:`extract_mention_edges`   — full-text occurrence of glossary
   terms inside section bodies → ``MENTIONS`` edges

All extractors are pure: same input → same output. The Chronicle dump
is therefore byte-stable for a given snapshot of the docs (modulo the
``accessed_at`` timestamp, which the dump-writer fills last).

A node's description is the first :data:`SNIPPET_MAX_CHARS` of its section
followed by the section's **status notes** (:func:`status_notes`): the dated
italic sentences the documents append beneath a sentence that was measured,
the ``> **Status`` banners at the head of a document (historical, superseded,
or a dated status line; in use since 2026-05-13) and the etappes' bold
``**Status:** <date> ...`` lines.
Without them the self-description served the sentence a document had marked as
a target as if it were a state (PHX-1117).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from theogony.core.model import (
    EdgeType,
    EpistemicStatus,
    KnowledgeEdge,
    KnowledgeForm,
    KnowledgeNode,
    Layer,
    NodeScores,
    NodeType,
    SourceRef,
)
from theogony.docs_ingest.markdown_parser import (
    ParsedDocument,
    ParsedSection,
)

#: ``source_type`` for every node and edge produced by this pipeline.
#: Distinguishes docs-ingest provenance from extraction-pipeline
#: provenance (``gutenberg``, ``web``, ``wikidata``).
SOURCE_TYPE = "theogony_repo"

#: Default GitHub blob URL the document/section nodes link back to.
#: Override at the pipeline level for forks.
DEFAULT_REPO_BASE_URL = "https://github.com/theogony-project/theogony/blob/main"

#: Length cap on the ``snippet`` field of a SourceRef. Keeps the
#: chronicle dump readable when grep-inspected.
SNIPPET_MAX_CHARS = 240

#: A status note is carried into the description whole, up to this many
#: characters, and a section contributes at most :data:`NOTES_MAX` of them.
#: Each is introduced by :data:`STATUS_NOTE_PREFIX`, which is also where the
#: embedding text stops (see ``pipeline._embedding_text_for``).
NOTE_MAX_CHARS = 600
NOTES_MAX = 4
STATUS_NOTE_PREFIX = "Status note: "

#: A note is recognised by its date. The dated italic sentence
#: (``*Measured 2026-08-31 (...): ...*``, ``*Status 2026-10-25: ...*``) is the
#: documents' convention since 2026-09-07; the ``> **Status ...**`` blockquote at
#: the head of a document predates it; the bold ``**Status:** <date>`` line is
#: the etappe template's. Undated emphasis is prose and stays out.
_NOTE_DATE_RE = re.compile(r"\b20\d\d-\d\d(?:-\d\d)?\b")
_NOTE_MIN_CHARS = 40
_STATUS_BLOCKQUOTE_RE = re.compile(r"^>\s*\*\*Status[^\n]*(?:\n>[^\n]*)*", re.MULTILINE)
_STATUS_LINE_RE = re.compile(r"^\*\*Status\b[^\n]*$", re.MULTILINE)
_CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")


# --------------------------------------------------------------------------
# Extractor outputs are returned as plain lists; an aggregate dataclass
# below keeps the pipeline orchestration tidy.
# --------------------------------------------------------------------------


@dataclass
class ExtractedChronicle:
    """Aggregate result of running all extractors over a repo snapshot."""

    nodes: list[KnowledgeNode] = field(default_factory=list)
    edges: list[KnowledgeEdge] = field(default_factory=list)


# --------------------------------------------------------------------------
# 1. Documents
# --------------------------------------------------------------------------


def extract_document_nodes(
    parsed_docs: Iterable[ParsedDocument],
    *,
    repo_base_url: str = DEFAULT_REPO_BASE_URL,
) -> list[KnowledgeNode]:
    """One node per parsed Markdown file.

    The node's label is the document title (first H1, or filename if
    none); the description is the first section's snippet followed by its
    status notes (:func:`describe`). The id is deterministic from
    (``SOURCE_TYPE``, rel_path, ``"document"``, title).
    """
    nodes: list[KnowledgeNode] = []
    for doc in parsed_docs:
        first_body = doc.sections[0].body_text if doc.sections else ""
        snippet = _truncate(_collapse_whitespace(first_body), SNIPPET_MAX_CHARS)
        description = describe(first_body)
        source_ref = SourceRef(
            source_type=SOURCE_TYPE,
            url=f"{repo_base_url}/{doc.rel_path}",
            identifier=doc.rel_path,
            location="document",
            snippet=snippet or None,
        )
        nodes.append(
            KnowledgeNode(
                embedding=[],
                node_type=NodeType.CONCEPT,
                knowledge_form=KnowledgeForm.STRUCTURAL,
                epistemic_status=EpistemicStatus.OBSERVED,
                label=doc.title,
                description=description,
                layer=Layer.MNEME,
                source_ref=source_ref,
                scores=NodeScores(confidence=0.95, relevance=0.5),
                properties={"doc_role": "document", "rel_path": doc.rel_path},
            )
        )
    return nodes


# --------------------------------------------------------------------------
# 2. Sections
# --------------------------------------------------------------------------


def extract_section_nodes(
    parsed_docs: Iterable[ParsedDocument],
    *,
    repo_base_url: str = DEFAULT_REPO_BASE_URL,
) -> list[KnowledgeNode]:
    """One node per H1/H2 section.

    The node's label is the heading text; the description is a truncated
    snippet of the section body followed by the section's status notes
    (:func:`describe`). The id is deterministic from (``SOURCE_TYPE``,
    rel_path, ``L<start>-L<end>``, heading).
    """
    nodes: list[KnowledgeNode] = []
    for doc in parsed_docs:
        for section in doc.sections:
            location = _section_location(section)
            url = f"{repo_base_url}/{doc.rel_path}#{section.anchor}" if section.anchor else None
            snippet = _truncate(_collapse_whitespace(section.body_text), SNIPPET_MAX_CHARS)
            description = describe(section.body_text)
            source_ref = SourceRef(
                source_type=SOURCE_TYPE,
                url=url,
                identifier=doc.rel_path,
                location=location,
                snippet=snippet or None,
            )
            nodes.append(
                KnowledgeNode(
                    embedding=[],
                    node_type=NodeType.CONCEPT,
                    knowledge_form=KnowledgeForm.STRUCTURAL,
                    epistemic_status=EpistemicStatus.OBSERVED,
                    label=section.heading,
                    description=description,
                    layer=Layer.MNEME,
                    source_ref=source_ref,
                    scores=NodeScores(confidence=0.95, relevance=0.5),
                    properties={
                        "doc_role": "section",
                        "rel_path": doc.rel_path,
                        "anchor": section.anchor,
                        "level": section.level,
                    },
                )
            )
    return nodes


# --------------------------------------------------------------------------
# 3. Glossary concepts
# --------------------------------------------------------------------------


_GLOSSARY_REL_PATH = "docs/GLOSSARY.md"

# A glossary entry looks like:
#
#     **Theogony**
#     The overall project, …
#
# or:
#
#     **Pantheon agents**
#     The ensemble of specialized agents…
#
# We treat **bold-only paragraphs** that appear inside the glossary
# document as canonical term headings; the paragraph immediately
# following is the definition.
_BOLD_TERM_RE = re.compile(r"^\*\*([^*\n]+?)\*\*\s*$")


def extract_glossary_concepts(
    parsed_docs: Iterable[ParsedDocument],
    *,
    repo_base_url: str = DEFAULT_REPO_BASE_URL,
) -> list[KnowledgeNode]:
    """Extract canonical concept nodes from ``docs/GLOSSARY.md``.

    Pattern: a paragraph containing only ``**Term**`` is the
    definition heading; the next non-empty line(s) up to the following
    blank line is the definition body. Both go into a ``concept`` node
    with stable id (``SOURCE_TYPE``, ``docs/GLOSSARY.md``,
    ``concept:<slug>``, term).

    Returns an empty list when no glossary document is present.
    """
    nodes: list[KnowledgeNode] = []
    for doc in parsed_docs:
        if doc.rel_path != _GLOSSARY_REL_PATH:
            continue
        for section in doc.sections:
            for term, definition in _iter_glossary_entries(section.body_text):
                slug = _slugify(term)
                source_ref = SourceRef(
                    source_type=SOURCE_TYPE,
                    url=f"{repo_base_url}/{doc.rel_path}#{section.anchor}",
                    identifier=doc.rel_path,
                    location=f"concept:{slug}",
                    snippet=_truncate(definition, SNIPPET_MAX_CHARS),
                )
                nodes.append(
                    KnowledgeNode(
                        embedding=[],
                        node_type=NodeType.CONCEPT,
                        knowledge_form=KnowledgeForm.STRUCTURAL,
                        epistemic_status=EpistemicStatus.OBSERVED,
                        label=term,
                        description=definition,
                        layer=Layer.MNEME,
                        source_ref=source_ref,
                        scores=NodeScores(confidence=1.0, relevance=0.6),
                        properties={
                            "doc_role": "glossary_concept",
                            "rel_path": doc.rel_path,
                            "section": section.heading,
                            "slug": slug,
                        },
                    )
                )
    return nodes


def _iter_glossary_entries(body_text: str) -> Iterable[tuple[str, str]]:
    """Yield ``(term, definition)`` pairs from a glossary section body.

    State machine: scan lines; when a line matches ``**Term**``, the
    next non-empty contiguous block is the definition. Stop reading
    the definition at the first blank line, the next ``**Term**``
    line, or end of text.
    """
    lines = body_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = _BOLD_TERM_RE.match(line)
        if not match:
            i += 1
            continue
        term = match.group(1).strip()
        # Collect definition: skip blank lines after the term, then
        # take consecutive non-empty lines.
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        def_lines: list[str] = []
        while j < len(lines):
            next_line = lines[j].strip()
            if not next_line:
                break
            if _BOLD_TERM_RE.match(next_line):
                break
            def_lines.append(next_line)
            j += 1
        definition = " ".join(def_lines).strip()
        if definition:
            yield term, definition
        i = j


# --------------------------------------------------------------------------
# 4. Link edges (PART_OF + LINKS_TO)
# --------------------------------------------------------------------------


def extract_part_of_edges(
    documents_by_rel_path: dict[str, KnowledgeNode],
    sections_by_rel_path: dict[str, list[tuple[ParsedSection, KnowledgeNode]]],
) -> list[KnowledgeEdge]:
    """One ``PART_OF`` edge per (section → document) pair."""
    edges: list[KnowledgeEdge] = []
    for rel_path, sections in sections_by_rel_path.items():
        doc_node = documents_by_rel_path.get(rel_path)
        if doc_node is None:
            continue
        for _section, sec_node in sections:
            edges.append(
                KnowledgeEdge(
                    source_id=sec_node.id,
                    target_id=doc_node.id,
                    relation_type="PART_OF",
                    weight=0.9,
                    confidence=1.0,
                    bidirectional=False,
                    epistemic_type=EdgeType.EXTRACTION,
                    source_ref=sec_node.source_ref,
                )
            )
    return edges


def extract_link_edges(
    parsed_docs: Iterable[ParsedDocument],
    sections_by_rel_path: dict[str, list[tuple[ParsedSection, KnowledgeNode]]],
    documents_by_rel_path: dict[str, KnowledgeNode],
) -> list[KnowledgeEdge]:
    """Resolve ``[text](href)`` links into ``LINKS_TO`` edges.

    Strategy:

    - Skip absolute URLs (``http://``, ``https://``), mailto, anchors
      that target only ``#anchor`` without a path (already implicit).
    - For relative ``./other.md`` or ``../docs/X.md``: try to land on
      the section node matching ``#anchor``; fall back to the document
      node when no section anchor is given or no match is found.
    - The source node for an edge is the *section* the link appeared
      in (preferred) or the document (fallback).
    """
    rel_to_sections: dict[str, dict[str, KnowledgeNode]] = {}
    for rel_path, pairs in sections_by_rel_path.items():
        rel_to_sections[rel_path] = {sec.anchor: node for sec, node in pairs}

    edges: list[KnowledgeEdge] = []
    for doc in parsed_docs:
        for section in doc.sections:
            section_node = _find_section_node(sections_by_rel_path, doc.rel_path, section)
            doc_node = documents_by_rel_path.get(doc.rel_path)
            origin_node = section_node or doc_node
            if origin_node is None:
                continue
            for link in section.links:
                target_node = _resolve_link_target(
                    href=link.href,
                    origin_rel_path=doc.rel_path,
                    rel_to_sections=rel_to_sections,
                    documents_by_rel_path=documents_by_rel_path,
                )
                if target_node is None:
                    continue
                if target_node.id == origin_node.id:
                    continue
                edges.append(
                    KnowledgeEdge(
                        source_id=origin_node.id,
                        target_id=target_node.id,
                        relation_type="LINKS_TO",
                        weight=0.7,
                        confidence=1.0,
                        bidirectional=False,
                        epistemic_type=EdgeType.EXTRACTION,
                        source_ref=origin_node.source_ref,
                        evidence_span=link.text,
                    )
                )
    return edges


def _find_section_node(
    sections_by_rel_path: dict[str, list[tuple[ParsedSection, KnowledgeNode]]],
    rel_path: str,
    section: ParsedSection,
) -> KnowledgeNode | None:
    for sec, node in sections_by_rel_path.get(rel_path, []):
        if sec.line_start == section.line_start and sec.heading == section.heading:
            return node
    return None


def _resolve_link_target(
    *,
    href: str,
    origin_rel_path: str,
    rel_to_sections: dict[str, dict[str, KnowledgeNode]],
    documents_by_rel_path: dict[str, KnowledgeNode],
) -> KnowledgeNode | None:
    """Resolve a relative Markdown link to a node, or ``None`` when out of scope."""
    if not href or href.startswith(("http://", "https://", "mailto:", "#")):
        return None

    # Split off ``#anchor`` if present.
    path_part, _, anchor = href.partition("#")
    target_rel = _normalise_relative_path(origin_rel_path, path_part)
    if target_rel is None:
        return None

    if anchor:
        sec_map = rel_to_sections.get(target_rel)
        if sec_map and anchor in sec_map:
            return sec_map[anchor]
    return documents_by_rel_path.get(target_rel)


def _normalise_relative_path(origin_rel_path: str, path_part: str) -> str | None:
    """Resolve a relative href against the originating document's directory.

    Returns the normalised ``rel_path`` of the target file, or ``None``
    when the link escapes the repo root or fails normalisation.
    """
    from posixpath import normpath

    # Strip any leading "./".
    while path_part.startswith("./"):
        path_part = path_part[2:]

    if not path_part:
        # Pure ``#anchor`` link with no path — same document as origin.
        return origin_rel_path

    # Resolve against the originating document's directory.
    parent = origin_rel_path.rsplit("/", 1)[0] if "/" in origin_rel_path else ""
    joined = (
        path_part
        if path_part.startswith("/")
        else (f"{parent}/{path_part}" if parent else path_part)
    )
    normalised = normpath(joined.lstrip("/"))
    if normalised.startswith(".."):
        return None
    if not normalised.endswith(".md"):
        return None
    return normalised


# --------------------------------------------------------------------------
# 5. Mention edges
# --------------------------------------------------------------------------


def extract_mention_edges(
    parsed_docs: Iterable[ParsedDocument],
    glossary_concepts: list[KnowledgeNode],
    sections_by_rel_path: dict[str, list[tuple[ParsedSection, KnowledgeNode]]],
) -> list[KnowledgeEdge]:
    """Wire ``MENTIONS`` edges from sections to glossary concepts.

    Strategy: for each glossary concept's label, scan every section's
    body for a case-insensitive whole-word occurrence and emit one
    ``MENTIONS`` edge per (section, concept) pair.

    Skips:

    - the glossary section that defines the term (avoids self-link)
    - terms shorter than 4 characters (too noisy: "AI" matches "rain"
      etc. via word-boundary regex; keep the threshold conservative)
    - duplicate (section, concept) combinations
    """
    if not glossary_concepts:
        return []

    concepts_by_label = {c.label: c for c in glossary_concepts if len(c.label) >= 4}
    if not concepts_by_label:
        return []

    # Pre-compile one regex per term for word-boundary matching.
    patterns = {label: re.compile(rf"(?i)\b{re.escape(label)}\b") for label in concepts_by_label}

    edges: list[KnowledgeEdge] = []
    seen: set[tuple[str, str]] = set()

    for doc in parsed_docs:
        sections = sections_by_rel_path.get(doc.rel_path, [])
        for section, sec_node in sections:
            body = section.body_text
            for label, concept_node in concepts_by_label.items():
                # Don't link a glossary entry's own defining section
                # back to itself.
                if (
                    sec_node.properties.get("rel_path") == _GLOSSARY_REL_PATH
                    and label.lower() == section.heading.lower()
                ):
                    continue
                if not patterns[label].search(body):
                    continue
                key = (sec_node.id, concept_node.id)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    KnowledgeEdge(
                        source_id=sec_node.id,
                        target_id=concept_node.id,
                        relation_type="MENTIONS",
                        weight=0.5,
                        confidence=0.85,
                        bidirectional=False,
                        epistemic_type=EdgeType.EXTRACTION,
                        source_ref=sec_node.source_ref,
                        evidence_span=label,
                    )
                )
    return edges


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _section_location(section: ParsedSection) -> str:
    """Format a SourceRef.location string for a section."""
    end = section.line_end - 1 if section.line_end is not None else section.line_start
    return f"L{section.line_start}-L{end}"


_WHITESPACE_RE = re.compile(r"\s+")


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _emphasis_spans(text: str) -> list[str]:
    """The single-star emphasis spans of a Markdown text, in order.

    Bold-aware (a ``*`` next to another ``*`` is bold, not emphasis) and
    flanking-aware (an opener is followed by a non-space, a closer preceded
    by one), so a ``* bullet`` never opens a span and ``**bold**`` inside a
    note never closes it. A nested single-star emphasis does close it: a
    note is written with ``**bold**``, not ``*em*``, inside. A span does not
    cross a blank line (spaces on it or not), and an opener that finds no
    closer before one takes every later opener of that paragraph with it
    (their closers would have been found), so a paragraph of stray stars
    scans in one pass.
    """
    spans: list[str] = []
    n = len(text)

    def single(k: int) -> bool:
        return (
            text[k] == "*" and (k + 1 >= n or text[k + 1] != "*") and (k == 0 or text[k - 1] != "*")
        )

    i = 0
    while i < n:
        if single(i) and i + 1 < n and not text[i + 1].isspace():
            j = i + 1
            closed = False
            while j < n:
                if single(j) and not text[j - 1].isspace():
                    spans.append(text[i + 1 : j])
                    closed = True
                    break
                if text[j] == "\n" and _BLANK_LINE_RE.match(text, j):
                    break
                j += 1
            i = j + 1 if closed else j
            continue
        i += 1
    return spans


def _plain_blockquotes(text: str) -> str:
    """The text with the ``> `` marks of its status blockquotes removed."""
    return _STATUS_BLOCKQUOTE_RE.sub(
        lambda m: " ".join(line.lstrip("> ").strip() for line in m.group(0).split("\n")), text
    )


def _bare(text: str) -> str:
    """A note or snippet without its emphasis marks and truncation mark, for comparison."""
    return text.rstrip("…").lstrip("*")


def status_notes(body_text: str) -> list[str]:
    """The status notes of a section body, whitespace-collapsed and capped.

    Three shapes count. A ``> **Status ...**`` blockquote is one note (the
    banner at the head of a document: historical, superseded, or a dated
    status line). A bold ``**Status:** ...`` line that carries a date is one
    note (the etappes' status line beneath the abstract). Every single-star
    emphasis span of at least :data:`_NOTE_MIN_CHARS` that carries a date is
    one note — unless it opens with the date, which is an etappe's dateline
    (``*2026-09-01. data/mesh-founding ...*``), not a status. Nothing inside
    a code span or a fence counts. Each note is cut at :data:`NOTE_MAX_CHARS`;
    a note contained in an earlier one is dropped; at most :data:`NOTES_MAX`
    are kept, in order.
    """
    masked = _CODE_RE.sub(lambda m: m.group(0).replace("*", "\x00").replace(">", "\x01"), body_text)
    found: list[str] = []
    for match in _STATUS_BLOCKQUOTE_RE.finditer(masked):
        found.append(" ".join(line.lstrip("> ").strip() for line in match.group(0).split("\n")))
    rest = _STATUS_BLOCKQUOTE_RE.sub("", masked)
    for match in _STATUS_LINE_RE.finditer(rest):
        if _NOTE_DATE_RE.search(match.group(0)):
            found.append(match.group(0))
    for span in _emphasis_spans(rest):
        if (
            len(span) >= _NOTE_MIN_CHARS
            and _NOTE_DATE_RE.search(span)
            and not _NOTE_DATE_RE.match(span.lstrip())
        ):
            found.append(span)
    notes: list[str] = []
    for raw in found:
        raw = raw.replace("\x00", "*").replace("\x01", ">")
        note = _truncate(_collapse_whitespace(raw), NOTE_MAX_CHARS)
        if note and not any(note in kept for kept in notes):
            notes.append(note)
        if len(notes) >= NOTES_MAX:
            break
    return notes


def describe(body_text: str) -> str | None:
    """A node's description: the snippet, then each status note on its own line.

    The snippet is the first :data:`SNIPPET_MAX_CHARS` of the body with the
    marks of its status blockquotes removed — what the dump carried before
    PHX-1117, give or take the marks. A section that opens with a note longer
    than the snippet carries the note once (cut at :data:`NOTE_MAX_CHARS` like
    any note) in place of the snippet; a snippet whose cut runs through a note
    stops before it; a note already inside the snippet is not repeated. The
    parts are whitespace-collapsed, so the newline between them is the one
    boundary the embedding text can rely on.
    """
    notes = status_notes(body_text)
    snippet = _truncate(_collapse_whitespace(_plain_blockquotes(body_text)), SNIPPET_MAX_CHARS)
    for note in notes:
        if snippet and _bare(note).startswith(_bare(snippet)):
            snippet = ""  # the section opens with this note; it is carried below
            break
        if snippet.endswith("…"):
            head = snippet[:-1]
            at = head.find(_bare(note)[:24])
            if at > 0 and _bare(note).startswith(_bare(head[at:])):
                snippet = head[:at].rstrip(" *")  # the cut ran through this note
                break
    parts = [snippet] if snippet else []
    parts.extend(f"{STATUS_NOTE_PREFIX}{note}" for note in notes if note not in snippet)
    return "\n".join(parts) or None


_NON_ALNUM = re.compile(r"[^\w\- ]+")


def _slugify(text: str) -> str:
    s = _NON_ALNUM.sub("", text.lower())
    s = re.sub(r"\s+", "-", s).strip("-")
    return s


__all__ = [
    "DEFAULT_REPO_BASE_URL",
    "ExtractedChronicle",
    "NOTES_MAX",
    "NOTE_MAX_CHARS",
    "SNIPPET_MAX_CHARS",
    "SOURCE_TYPE",
    "STATUS_NOTE_PREFIX",
    "describe",
    "extract_document_nodes",
    "extract_glossary_concepts",
    "extract_link_edges",
    "extract_mention_edges",
    "extract_part_of_edges",
    "extract_section_nodes",
    "status_notes",
]
