"""MESH-native Kadmos v2 ingestion with dense paragraph topology."""

from __future__ import annotations

import contextlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

from ulid import ULID

from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.extraction.embedding import EmbeddingProvider
from theogony.mesh import frames
from theogony.mesh.ingestion.concept_resolver import ConceptResolver
from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.ingestion.reading_schemas import (
    LLMConcept,
    ParagraphReadingOutput,
    normalize_reading_payload,
)
from theogony.mesh.ingestion.source_anchor import (
    build_paragraph_anchor_title,
    build_source_anchor_node,
)
from theogony.mesh.ingestion.vectorizer import MeshTextVectorizer
from theogony.mesh.relation_pids import pid_for
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import (
    ChunkNode,
    ConsolidatedNode,
    Edge,
    PIDTag,
    QIDTag,
    SourceProvenance,
)
from theogony.reporting.models import (
    EmbeddingSummary,
    IngestRunReport,
    IngestStageName,
    IngestStageReport,
    NerSummary,
    QualityFlags,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
)
from theogony.reporting.verdict import ingest_verdict
from theogony.reporting.writer import RunReportWriter

log = get_logger("mesh.ingestion")

# Edges buffered before a Lance append (see MeshParagraphReader._append_edge).
_EDGE_FLUSH_BATCH = 512
#: Revisions of existing descriptions wait in memory, one per node, and land as
#: one write per flush: at the compaction boundary, at the end of the read, or
#: when this many nodes are pending (PHX-1118).
_REVISION_FLUSH_BATCH = 512
#: The doctrine's band for a Tier-1 description is 200-500 characters
#: (MESH_SUBSTRATE §"Field discipline", rule 4); accrual stops at its upper edge.
DESCRIPTION_MAX_CHARS = 500
_SENTENCE_BREAK = re.compile(r"(?<=[.!?][\"”’')\]])\s+|(?<=[.!?])\s+")
#: A part that ends on one of these did not end a sentence: an initial
#: ("William D."), a dotted acronym ("U.S.", "Ph.D.") or a common abbreviation.
#: Without this "J. R. R. Tolkien" splits into four sentences and the merge
#: dedupes the one-letter ones against the standing text — writing a wrong name
#: into the identity surface (found by review). The single-letter rule also
#: glues a regnal numeral to the next sentence ("Charles V. He ...", one unit);
#: the merge then dedupes such a unit by its parts, so the trade-off costs a cap
#: check on a pair, not a name.
_ABBREVIATION_TAIL = re.compile(
    r"(?:^|[\s(\[\"'])"
    r"(?:[A-Za-z]|(?:[A-Za-z]{1,2}\.)+[A-Za-z]{1,2}|Dr|Mr|Mrs|Ms|Jr|Sr|St|Mt|Ft|No|Nos|Co|Ltd|Corp|Bros"
    r"|Op|Vol|vol|pp|ed|eds|ca|fl|vs|e\.g|i\.e|approx"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    r"|Gen|Col|Capt|Lt|Sgt|Maj|Prof|Rev|Hon|Sen|Rep|Gov|Pres)\.$"
)

# Structural (`shares_entities_with`) neighbours kept per paragraph — PHX-1049.
# Linking every entity-sharing pair is O(P^2): on the founding mesh the lattice
# alone was 51% of all edges, and a full read grew ~33% slower per 100-paragraph
# batch because the pass writes two edges and an audit row per qualifying pair.
# The doctrine wants connectivity carried by shared *concepts*, not by a chunk
# quasi-clique, so each paragraph keeps only its strongest partners.
_MAX_STRUCTURAL_NEIGHBOURS = 12
_COMPACT_EVERY = 200  # paragraphs between workspace compactions during a read (PHX-1110)

# The user prompt a paragraph is read with, in one place: the reader sends it,
# the recorder (`scripts/record_demo_readings.py`) sends the identical string
# so what it records is what Kadmos would have read, and the replay provider
# (`mesh.ingestion.replay`) finds the paragraph between head and tail again.
PARAGRAPH_PROMPT_HEAD = "PARAGRAPH:\n"
PARAGRAPH_PROMPT_TAIL = "\n\nExtract the concepts, relations, and paragraph concept."


def paragraph_prompt(text: str) -> str:
    """The exact user prompt the reader sends for one paragraph."""
    return f"{PARAGRAPH_PROMPT_HEAD}{text}{PARAGRAPH_PROMPT_TAIL}"


SYSTEM_PROMPT = """You are Kadmos, the cognitive reader for a MESH substrate.

Read the paragraph below and output valid JSON for this schema:

1. concepts:
   - every distinct person, place, object, organization, date, event, or idea
   - the paragraph's central figure(s) — whoever the passage is ABOUT — MUST
     appear here as named concepts. Never leave the protagonist implicit or
     fold them into the paragraph_concept alone; a passage about a goddess's
     birth must yield the goddess herself as a concept.
   - when the text uses a variant or translated name (e.g. Roman "Venus" for
     Greek Aphrodite, "Jove" for Zeus), use the text's name as the label and
     add the canonical variant names as tags
   - include a discriminating description
   - include optional Wikidata Q-IDs only when you are confident; for figures
     known under multiple names, the Q-ID of the canonical identity

2. relations:
   - directed edges between concepts from this paragraph
   - use short relation_descriptor values like crossed, mapped, discovered, located_in
   - use relation_kind values like semantic, hierarchy, causal, temporal, attribute
   - use relation_kind "contradicts" when the paragraph itself sets one account
     against another ("some say X, but others say Y"), and "supersedes" when it
     says one account replaced an earlier one
   - each relation carries a stance (see 4); default "current_claim"

3. paragraph_concept:
   - optional single paragraph-level concept when the paragraph has a coherent unifying idea
   - the paragraph_concept never replaces the concepts it is about — its
     protagonists must still be listed in concepts
   - if absent, set paragraph_concept to null

4. stance:
   - a REQUIRED top-level string field, a sibling of "concepts" and
     "relations", not nested inside them
   - how the paragraph as a whole makes its claim; exactly one of:
     "definition"        timeless, what something IS
     "current_claim"     plainly asserted (use when unsure)
     "historical_claim"  what was held or done at some past time
     "refuted_claim"     the text denies something, or says it is wrong
     "hypothesis"        supposed, conditional, "if", "it may be"
     "observation"       a particular witnessed or reported event
     "direct_quote"      the paragraph is mainly someone speaking
     "disputed"          the text reports competing accounts of the same thing
     "superseded"        an account the text marks as replaced by a later one
   - judge the paragraph's own framing, not whether you believe it
   - each relation carries its own "stance" from the same list

The top level therefore has exactly four keys:

   {"concepts": [...], "relations": [...], "paragraph_concept": ..., "stance": "..."}

Output only valid JSON. Do not add commentary."""

_SIGNAL_TO_TIER = {
    "qid": 4,
    "description": 3,
    "tag": 2,
    "emergent": 1,
}


@dataclass
class _ParagraphUnit:
    paragraph_number: int
    paragraph_anchor_id: str
    chunk_id: str
    entity_ids: set[str]
    paragraph_concept_id: str | None
    local_node_ids: set[str]
    local_edge_count: int


@dataclass
class _ReadTally:
    """What one read has done so far: the numbers its IngestRunReport carries.

    One object rather than thirty locals so that a read which raises can still
    say what it wrote (PHX-1116). The success path and the failure path build
    the report from the same counts.
    """

    acquired_duration_s: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_monotonic: float = field(default_factory=time.monotonic)
    #: Where the read is, for a failure report: the paragraph being read
    #: (1-based; 0 before the first, ``paragraphs_total + 1`` once the
    #: cross-paragraph pass runs) and the stage it is in.
    paragraph: int = 0
    paragraphs_total: int = 0
    stage: IngestStageName = "cleaned"
    word_count: int = 0
    sentence_count: int = 0
    cleaned_duration_s: float = 0.0
    sentencized_duration_s: float = 0.0
    nodes_upserted: int = 0
    firing_passes: int = 0
    descriptions_revised: int = 0
    #: Re-mentions whose description did not accrue because the mention did not
    #: call the node by its name (PHX-1121).
    descriptions_declined_unnamed: int = 0
    edges_upserted: int = 0
    nodes_embedded: int = 0
    total_mentions: int = 0
    total_relations_attempted: int = 0
    total_relations_written: int = 0
    relation_drop_count: int = 0
    total_llm_calls: int = 0
    total_llm_cost_eur: float = 0.0
    llm_failure_count: int = 0
    llm_schema_failures: int = 0
    signal_counts: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in _SIGNAL_TO_TIER}
    )
    qid_claims_dropped: int = 0
    paragraph_units: list[_ParagraphUnit] = field(default_factory=list)
    paragraph_anchor_count: int = 0
    paragraph_concept_count: int = 0
    paragraph_concept_node_ids: set[str] = field(default_factory=set)
    llm_duration_s: float = 0.0
    relation_stage_duration_s: float = 0.0
    resolve_stage_duration_s: float = 0.0
    embed_stage_duration_s: float = 0.0
    store_stage_duration_s: float = 0.0
    cross_pass_link_count: int = 0
    #: What stances the read actually produced — the histogram is the only way
    #: to see whether the model used the vocabulary or defaulted everything to
    #: one value (PHX-1107).
    stance_counts: dict[str, int] = field(default_factory=dict)
    contradiction_edge_count: int = 0
    #: Basis labels the paragraph concepts named; a basis label that resolves to
    #: no concept is a drop, so it belongs in the drop rate's denominator too.
    basis_attempted: int = 0
    #: Rows the store held when the read began. A failure report counts what
    #: landed from the store itself: a write that raises part-way (three tables
    #: per edge batch, three per node) leaves the read's own counters short.
    store_before: dict[str, int] | None = None
    source_anchor_written: bool = False
    #: The paragraph a compaction boundary follows, while its flush runs.
    boundary: int | None = None
    #: The success path's mesh_ingest_run row, once it is written.
    run_row_id: str | None = None


def _error_text(exc: BaseException) -> str:
    """``Type: message``, even for an exception whose ``__str__`` raises."""
    try:
        return f"{type(exc).__name__}: {exc}"
    except Exception:  # noqa: BLE001 - the type is still worth reporting
        return type(exc).__name__


#: What a buffer flush was writing when it raised, for the failure report.
_BUFFER_NAMES = {
    "edges": "the buffered edges",
    "revisions": "the pending description revisions",
    "audit": "the staged audit rows",
}


class MeshParagraphReader:
    """Paragraph reader that writes a dense, auditable local mesh per paragraph."""

    def __init__(
        self,
        mesh: MeshRuntime,
        llm: LLMProvider,
        *,
        semantic_dim: int | None = None,
        frame_dim: int | None = None,
        max_paragraphs: int = 0,
        settings: Settings | None = None,
        max_structural_neighbours: int = _MAX_STRUCTURAL_NEIGHBOURS,
        compact_every: int = _COMPACT_EVERY,
        embedder: EmbeddingProvider | None = None,
        connectivity_metrics: bool = True,
        accrue_descriptions: bool = False,
        accrue_unnamed: bool = False,
        revise_identity_vector: bool = True,
    ) -> None:
        self.mesh = mesh
        self.llm = llm
        # When a paragraph mentions an entity the substrate already holds, fold
        # the paragraph's description of it into the node (PHX-1118, track D
        # step 1). Off by default: the two arms of the measurement are built
        # from the same code, and the demo and mesh_append keep today's path.
        self.accrue_descriptions = accrue_descriptions
        # Accrual only from a mention that calls the node by its name (PHX-1121);
        # True restores PHX-1118's arm, where any re-mention accrued.
        self.accrue_unnamed = accrue_unnamed
        # Whether a revision re-embeds the identity vector too. The linker matches
        # a mention against `description_vector`; retrieval seeds on
        # `semantic_vector`. False leaves the identity vector as the node was
        # created — its text is the revised description's own prefix — so the
        # linker never sees accrued text, while retrieval and the rendered
        # description do. In 85 of the 334 losses the PHX-1120 judges agree on,
        # only the right node had accrued text when the mention left it (drift;
        # the condition held in 65 of the 129 gains too: where it was possible,
        # not where it acted) (PHX-1121).
        self.revise_identity_vector = revise_identity_vector
        # The connectivity pass loads every edge and every consolidated node and
        # walks the graph once per read — right for a corpus, wrong for a path
        # that reads one paragraph per call (mesh_append over MCP), where it
        # would be the one-transaction-per-item cost this substrate keeps paying.
        self.connectivity_metrics = connectivity_metrics
        self.settings = settings or Settings()
        self.max_paragraphs = max_paragraphs
        # Compact the workspace every N paragraphs (0 = never). Every node is
        # its own Lance fragment until something compacts, and every vector
        # search — two per concept, for identity — scans all of them, so a
        # long read slows down as it goes: 0.55 s per paragraph at the start of
        # a 6,119-paragraph corpus, over 6 s by paragraph 400 (PHX-1110). The
        # tick compacts, but a read does not tick. Same cost the version pile-up
        # had on appends (PHX-1060), on the read side.
        self.compact_every = compact_every
        self.max_structural_neighbours = max_structural_neighbours
        self.semantic_dim = mesh.semantic_dim if semantic_dim is None else semantic_dim
        self.frame_dim = mesh.frame_dim if frame_dim is None else frame_dim
        self.registry = ConceptResolver(mesh.nodes)
        self.linker = EagerLinker(
            mesh.nodes,
            mesh.edges,
            semantic_dim=self.semantic_dim,
            frame_dim=self.frame_dim,
            registry=self.registry,
        )
        self.vectorizer = MeshTextVectorizer(
            semantic_dim=self.semantic_dim,
            frame_dim=self.frame_dim,
            settings=self.settings,
            embedder=embedder,
        )
        self.report_writer = RunReportWriter(self.settings.run_reports_dir)
        #: The IngestRunReport of the last read that raised, or None, and where
        #: it was written — None with ``failure_report_error`` set when writing
        #: it raised too. The exception carries a note saying which; these are
        #: for a caller that hands the run id on, as `mesh_append` does
        #: (PHX-1116).
        self.failure_report: IngestRunReport | None = None
        self.failure_report_path: Path | None = None
        self.failure_report_error: str | None = None
        # The buffers whose own write raised, with the first error each: the
        # failure path does not write them a second time. `append_edges` writes
        # three tables in turn, so a retry after a partial write would duplicate
        # the rows that landed, and a retry of the revision flush would call the
        # embedder again. First failure wins: a later one must not unmark it.
        self._flush_failures: dict[str, str] = {}
        self._pending_edges: list[Edge] = []
        # Revised copies of existing nodes, by id, so a node mentioned twice in
        # one flush window builds on its pending copy, not on the stored row.
        self._pending_revisions: dict[str, ConsolidatedNode] = {}
        # Frames of the nodes this run has written, so `_append_edge` can fill
        # `frame_consistency` from the endpoints it just created. The doctrine
        # defines the field as 'how well the edge's endpoints share a frame'
        # and PHX-1095 measured it at exactly 1.0 on all 94,490 edges of the
        # founding mesh — 'a missing pass, not missing data'. This is the pass.
        # Bounded by one read: entity frames are neutral and chunk frames are
        # one per paragraph, so the map is at most nodes-written large.
        self._frames: dict[str, list[float]] = {}

    async def read_book(self, book_id: str) -> dict[str, Any]:
        import httpx

        acquired_started = time.monotonic()
        async with httpx.AsyncClient(follow_redirects=True) as client:
            meta_resp = await client.get(f"https://gutendex.com/books/{book_id}", timeout=15)
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            book_title = meta.get("title", f"Project Gutenberg Book {book_id}")
            formats = meta.get("formats", {})
            text_url = (
                formats.get("text/plain; charset=utf-8")
                or formats.get("text/plain")
                or formats.get("text/plain; charset=us-ascii")
                or next((value for key, value in formats.items() if "text/plain" in key), None)
            )
            if not text_url:
                raise ValueError(f"No plain-text format for book {book_id}")
            content_resp = await client.get(str(text_url), timeout=90)
            content_resp.raise_for_status()
            raw_text = content_resp.text
        acquired_duration_s = time.monotonic() - acquired_started

        return await self.read_text(
            text=raw_text,
            source_type="gutenberg",
            source_identifier=f"gutenberg_{book_id}",
            title=book_title,
            anchor=f"https://www.gutenberg.org/ebooks/{book_id}",
            acquired_duration_s=acquired_duration_s,
        )

    async def read_text(
        self,
        *,
        text: str,
        source_type: str = "text",
        source_identifier: str = "inline",
        title: str = "Untitled",
        anchor: str = "",
        acquired_duration_s: float = 0.0,
    ) -> dict[str, Any]:
        """Read ``text`` into the mesh and write the run's IngestRunReport.

        A read that raises reports too (AGENTS.md contract 3, PHX-1116): the
        buffers the failure did not come from are written, an IngestRunReport
        with status and verdict ``failed`` says what landed and what did not,
        :attr:`failure_report` holds it, a note on the exception names it, and
        the exception propagates unchanged.
        """
        tally = _ReadTally(acquired_duration_s=acquired_duration_s)
        self.failure_report = None
        self.failure_report_path = None
        self.failure_report_error = None
        self._flush_failures = {}
        try:
            return await self._read(
                tally,
                text=text,
                source_type=source_type,
                source_identifier=source_identifier,
                title=title,
                anchor=anchor,
            )
        except Exception as exc:
            await self._report_failure(
                tally, exc, source_type=source_type, source_identifier=source_identifier
            )
            raise

    async def _read(
        self,
        tally: _ReadTally,
        *,
        text: str,
        source_type: str,
        source_identifier: str,
        title: str,
        anchor: str,
    ) -> dict[str, Any]:
        tally.store_before = self._store_counts()
        source_anchor = anchor or source_identifier

        cleaned_started = time.monotonic()
        paragraphs = _split_paragraphs(text)
        if self.max_paragraphs > 0:
            paragraphs = paragraphs[: self.max_paragraphs]
        tally.paragraphs_total = len(paragraphs)
        tally.cleaned_duration_s = time.monotonic() - cleaned_started

        tally.stage = "sentencized"
        sentencized_started = time.monotonic()
        tally.sentence_count = _count_sentences(" ".join(paragraphs))
        tally.sentencized_duration_s = time.monotonic() - sentencized_started
        tally.word_count = len(re.findall(r"\w+", " ".join(paragraphs)))

        entity_source_links: set[tuple[str, str]] = set()

        tally.stage = "embedded"
        text_anchor_description = f"{source_type}: {title} ({source_anchor})"
        text_anchor_semantic = await self.vectorizer.semantic(text_anchor_description)
        # A source anchor asserts nothing; it is where claims came from. The
        # zero frame is neutral by construction and is never attenuated by
        # routing, which is what a container should be (PHX-1107).
        text_anchor_frame = frames.neutral_frame(self.frame_dim)
        text_anchor_description_vector = await self.vectorizer.description(text_anchor_description)
        tally.nodes_embedded += 1
        text_anchor_node = build_source_anchor_node(
            source_type=source_type,
            title=title,
            anchor=source_anchor,
            semantic_vector=text_anchor_semantic,
            frame_vector=text_anchor_frame,
            description_vector=text_anchor_description_vector,
            tags=[source_type.lower(), "source_anchor", "text"],
        )
        tally.stage = "stored"
        self.mesh.nodes.append_consolidated(text_anchor_node)
        tally.source_anchor_written = True
        self.registry.remember(text_anchor_node)
        tally.nodes_upserted += 1
        self._append_audit(
            "mesh_ingest_source_anchor_created",
            {
                "node_id": str(text_anchor_node.id),
                "source_type": source_type,
                "source_identifier": source_identifier,
            },
        )

        for paragraph_index, paragraph_text in enumerate(paragraphs, start=1):
            paragraph_text = paragraph_text.strip()
            if len(paragraph_text) < 10:
                continue
            tally.paragraph = paragraph_index
            if (
                self.compact_every > 0
                and paragraph_index > 1
                and (paragraph_index - 1) % self.compact_every == 0
            ):
                tally.stage = "stored"
                tally.boundary = paragraph_index - 1
                self._flush_edges()
                try:
                    revised_rows = await self._flush_revisions()
                finally:
                    # Same order as the end of the read: a failing embed must not
                    # take the window's staged audit rows with it.
                    self._flush_audit()
                pruned = self.mesh.compact()
                tally.boundary = None
                log.info(
                    "compacted the workspace after %d paragraphs: %s (descriptions revised: %d)",
                    paragraph_index - 1,
                    pruned,
                    revised_rows,
                )

            log.info(
                "reading paragraph %d/%d (%d chars)",
                paragraph_index,
                len(paragraphs),
                len(paragraph_text),
            )

            tally.stage = "mentions_extracted"
            paragraph_result, llm_meta = await self._read_paragraph(paragraph_text)
            # The stance this paragraph makes its claim in. A failed reading
            # leaves the paragraph without one, and the default claims least.
            paragraph_stance = frames.normalise_stance(
                paragraph_result.stance if paragraph_result is not None else None
            )
            tally.stance_counts[paragraph_stance] = tally.stance_counts.get(paragraph_stance, 0) + 1
            tally.total_llm_calls += 1
            tally.total_llm_cost_eur += llm_meta["cost_eur"]
            tally.llm_duration_s += llm_meta["duration_s"]
            tally.llm_failure_count += int(llm_meta["failed"])
            tally.llm_schema_failures += int(llm_meta["schema_failed"])

            tally.stage = "embedded"
            embed_started = time.monotonic()
            paragraph_anchor_title = build_paragraph_anchor_title(
                title=title,
                paragraph_number=paragraph_index,
            )
            paragraph_anchor_identifier = f"{source_identifier}#p{paragraph_index}"
            paragraph_anchor_semantic = await self.vectorizer.semantic(paragraph_anchor_title)
            paragraph_anchor_frame = frames.neutral_frame(self.frame_dim)
            paragraph_anchor_description_vector = await self.vectorizer.description(
                f"{source_type} paragraph: {paragraph_anchor_title} ({paragraph_anchor_identifier})"
            )
            chunk_semantic = await self.vectorizer.semantic(paragraph_text)
            # The chunk is the observation, so the chunk is where the stance
            # lives. Until PHX-1107 this was a salted hash of the paragraph
            # text: 4,977 distinct vectors carrying no epistemic content, which
            # frame routing could only mask by (PHX-1095). The reading's own
            # stance is the reading's own, which has already arrived above.
            chunk_frame = frames.frame_vector(paragraph_stance, dim=self.frame_dim)
            tally.nodes_embedded += 2
            tally.embed_stage_duration_s += time.monotonic() - embed_started

            tally.stage = "stored"
            store_started = time.monotonic()
            paragraph_anchor = build_source_anchor_node(
                source_type=f"{source_type} paragraph",
                title=paragraph_anchor_title,
                anchor=paragraph_anchor_identifier,
                semantic_vector=paragraph_anchor_semantic,
                frame_vector=paragraph_anchor_frame,
                description_vector=paragraph_anchor_description_vector,
                tags=[source_type.lower(), "source_anchor", "paragraph"],
            )
            self.mesh.nodes.append_consolidated(paragraph_anchor)
            self.registry.remember(paragraph_anchor)
            tally.nodes_upserted += 1
            tally.paragraph_anchor_count += 1

            now = datetime.now(UTC)
            chunk = ChunkNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=chunk_semantic,
                frame_vector=chunk_frame,
                source=SourceProvenance(
                    source_type=source_type,
                    source_identifier=source_identifier,
                    extracted_at=now,
                ),
                raw_text_ref=paragraph_anchor_identifier,
            )
            self.mesh.nodes.append_chunk(chunk)
            self._remember_frame(str(chunk.id), chunk_frame)
            tally.nodes_upserted += 1
            self._append_edge(
                Edge(
                    source_id=chunk.id,
                    target_id=paragraph_anchor.id,
                    weight=1.0,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="extraction",
                    relation_descriptor="extracted_from",
                    creation_context="kadmos_extraction",
                )
            )
            tally.edges_upserted += 1
            self._append_edge(
                Edge(
                    source_id=paragraph_anchor.id,
                    target_id=text_anchor_node.id,
                    weight=0.9,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="hierarchy",
                    relation_descriptor="is_section_of",
                    creation_context="kadmos_source_hierarchy",
                )
            )
            tally.edges_upserted += 1
            tally.store_stage_duration_s += time.monotonic() - store_started

            resolved_by_label: dict[str, ConsolidatedNode] = {}
            resolved_entity_ids: set[str] = set()
            # Nodes this paragraph referenced that the substrate already had.
            # `MESH_SUBSTRATE.md` §"Second worked example" states the rule
            # outright: "Each new chunk attaches a *new* reference edge to the
            # *existing* Thomas Addison node — `fired_total` and `fired_recent`
            # increment, the node accumulates evidence." Doctrine's firing signal
            # therefore has two sources, and this is the one that carries the
            # "breadth of incoming references" half of the tier-promotion gate
            # (PHX-1101).
            referenced_existing: set[str] = set()
            local_node_ids = {
                str(text_anchor_node.id),
                str(paragraph_anchor.id),
                str(chunk.id),
            }
            local_edge_count = 2

            if paragraph_result is not None:
                tally.total_mentions += len(paragraph_result.concepts)

                tally.stage = "mentions_resolved"
                resolve_started = time.monotonic()
                concept_vectors = await self._vectorize_concepts(paragraph_result.concepts)
                tally.nodes_embedded += len(paragraph_result.concepts)

                for concept, (semantic_vector, frame_vector, description_vector) in zip(
                    paragraph_result.concepts,
                    concept_vectors,
                    strict=False,
                ):
                    qids = [
                        QIDTag(
                            qid=qid.qid,
                            confidence=qid.confidence,
                            attached_at=datetime.now(UTC),
                        )
                        for qid in concept.qids
                    ]
                    decision = self.linker.link_reference(
                        label=concept.label,
                        description=_entity_description(concept.label, concept.description),
                        tags=_concept_tags(concept),
                        qids=qids,
                        semantic_vector=semantic_vector,
                        frame_vector=frame_vector,
                        description_vector=description_vector,
                        context_node_ids=resolved_entity_ids,
                        # The reading model asserts these; nothing corroborates
                        # them. They may still find a node the wikidata5m seed
                        # put there, but they must not be written (PHX-1063).
                        qids_are_authoritative=False,
                    )
                    tally.qid_claims_dropped += len(qids)
                    tally.signal_counts[decision.signal] += 1
                    resolved_by_label[concept.label] = decision.node
                    resolved_entity_ids.add(str(decision.node.id))
                    local_node_ids.add(str(decision.node.id))
                    if decision.is_new:
                        tally.nodes_upserted += 1
                    else:
                        referenced_existing.add(str(decision.node.id))
                        if self.accrue_descriptions and not (
                            self.accrue_unnamed or names_node(concept.label, decision.node)
                        ):
                            # The link stands; its text does not reach the node. A
                            # mention that calls a node by another name is the
                            # linker's guess, and accruing on a wrong guess writes one
                            # entity's description into another's, where a later
                            # mention of the first finds it: that was possible in 180
                            # of the 334 losses the PHX-1120 judges agree on, and 44%
                            # of the PHX-1118 revisions came from such mentions
                            # (PHX-1121).
                            tally.descriptions_declined_unnamed += 1
                        elif self.accrue_descriptions:
                            standing = self._pending_revisions.get(
                                str(decision.node.id), decision.node
                            )
                            chars_before = len(standing.description or "")
                            revised = self._accrue_description(
                                decision.node,
                                concept.description,
                                chunk_id=chunk.id,
                                now=now,
                            )
                            if revised is not None:
                                tally.descriptions_revised += 1
                                self._stage_audit(
                                    "mesh_ingest_description_revised",
                                    {
                                        "node_id": str(revised.id),
                                        "chunk_id": str(chunk.id),
                                        "label": concept.label,
                                        "signal": decision.signal,
                                        "paragraph": paragraph_index,
                                        "source_identifier": source_identifier,
                                        "chars_before": chars_before,
                                        "chars_after": len(revised.description or ""),
                                        "sources": len(revised.description_source_chunks),
                                    },
                                )
                                if len(self._pending_revisions) >= _REVISION_FLUSH_BATCH:
                                    self._flush_edges()
                                    try:
                                        await self._flush_revisions()
                                    finally:
                                        self._flush_audit()
                    self._stage_audit(
                        "mesh_ingest_link_decision",
                        {
                            "label": concept.label,
                            "node_id": str(decision.node.id),
                            "signal": decision.signal,
                            "score": round(decision.score, 4),
                            # Kept as a claim so it can be corroborated later.
                            "qid_claims": [q.qid for q in qids],
                            "paragraph": paragraph_index,
                            "source_identifier": source_identifier,
                        },
                    )

                    self._append_edge(
                        Edge(
                            source_id=chunk.id,
                            target_id=decision.node.id,
                            weight=0.95,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="co_occurrence",
                            relation_descriptor="mentions",
                            creation_context="kadmos_mentions",
                        )
                    )
                    tally.edges_upserted += 1
                    local_edge_count += 1

                    source_key = (str(decision.node.id), str(text_anchor_node.id))
                    if source_key not in entity_source_links:
                        self._append_edge(
                            Edge(
                                source_id=decision.node.id,
                                target_id=text_anchor_node.id,
                                weight=0.45,
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="attribution",
                                relation_descriptor="appears_in_source",
                                creation_context="kadmos_source_attribution",
                            )
                        )
                        entity_source_links.add(source_key)
                        tally.edges_upserted += 1
                        local_edge_count += 1

                tally.resolve_stage_duration_s += time.monotonic() - resolve_started

                tally.stage = "relations_extracted"
                relation_started = time.monotonic()
                tally.total_relations_attempted += len(paragraph_result.relations)
                for relation in paragraph_result.relations:
                    source_node = resolved_by_label.get(relation.source)
                    target_node = resolved_by_label.get(relation.target)
                    if source_node is None or target_node is None:
                        tally.relation_drop_count += 1
                        continue
                    self._append_edge(
                        Edge(
                            source_id=source_node.id,
                            target_id=target_node.id,
                            weight=1.0,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind=relation.relation_kind,
                            relation_descriptor=relation.relation_descriptor,
                            description=relation.rationale,
                            # The Wikidata property naming this relation, when one
                            # reads the same way ours does. Curated and verified,
                            # never asked of the model — it confabulated 127 of 130
                            # Q-IDs on this corpus (PHX-1063, PHX-1072).
                            pids=(
                                [PIDTag(pid=pid, confidence=1.0, attached_at=now)]
                                if (pid := pid_for(relation.relation_descriptor))
                                else []
                            ),
                            creation_context="kadmos_relation",
                        )
                    )
                    tally.edges_upserted += 1
                    tally.total_relations_written += 1
                    if frames.is_contradiction_kind(relation.relation_kind):
                        tally.contradiction_edge_count += 1
                    local_edge_count += 1

                for left_id, right_id in combinations(sorted(resolved_entity_ids), 2):
                    left_node = self.registry.get_by_id(left_id)
                    right_node = self.registry.get_by_id(right_id)
                    if left_node is None or right_node is None:
                        continue
                    node_pairs = (
                        (left_node, right_node),
                        (right_node, left_node),
                    )
                    for source_node, target_node in node_pairs:
                        self._append_edge(
                            Edge(
                                source_id=source_node.id,
                                target_id=target_node.id,
                                weight=0.35,
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="co_occurrence",
                                relation_descriptor="co_mentions_in_paragraph",
                                creation_context="kadmos_paragraph_density",
                            )
                        )
                        tally.edges_upserted += 1
                        local_edge_count += 1

                paragraph_concept_id: str | None = None
                if paragraph_result.paragraph_concept is not None:
                    paragraph_concept = paragraph_result.paragraph_concept
                    concept_description = paragraph_concept.description or paragraph_concept.label
                    semantic_vector = await self.vectorizer.semantic(concept_description)
                    # The paragraph concept is the paragraph's claim in one node,
                    # so it carries the paragraph's stance.
                    frame_vector = frames.frame_vector(paragraph_stance, dim=self.frame_dim)
                    description_vector = await self.vectorizer.description(concept_description)
                    tally.nodes_embedded += 1
                    decision = self.linker.link_reference(
                        label=paragraph_concept.label,
                        description=concept_description,
                        tags=list(paragraph_concept.tags) + ["paragraph_concept"],
                        qids=[],
                        semantic_vector=semantic_vector,
                        frame_vector=frame_vector,
                        description_vector=description_vector,
                        context_node_ids=resolved_entity_ids,
                    )
                    paragraph_concept_id = str(decision.node.id)
                    if decision.is_new:
                        # Only when this run created it: a concept the linker
                        # resolved onto an existing node keeps that node's frame,
                        # and claiming otherwise would score consistency against a
                        # vector the substrate does not hold.
                        self._remember_frame(paragraph_concept_id, frame_vector)
                    local_node_ids.add(paragraph_concept_id)
                    tally.paragraph_concept_node_ids.add(paragraph_concept_id)
                    if decision.is_new:
                        tally.nodes_upserted += 1
                    else:
                        referenced_existing.add(str(decision.node.id))
                    tally.paragraph_concept_count += 1

                    self._append_edge(
                        Edge(
                            source_id=paragraph_anchor.id,
                            target_id=decision.node.id,
                            weight=0.8,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="hierarchy",
                            relation_descriptor="has_paragraph_concept",
                            creation_context="kadmos_paragraph_concept",
                        )
                    )
                    self._append_edge(
                        Edge(
                            source_id=chunk.id,
                            target_id=decision.node.id,
                            weight=0.7,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="hierarchy",
                            relation_descriptor="summarised_as",
                            creation_context="kadmos_paragraph_concept",
                        )
                    )
                    tally.edges_upserted += 2
                    local_edge_count += 2

                    tally.basis_attempted += len(paragraph_concept.basis_concepts)
                    for basis_label in paragraph_concept.basis_concepts:
                        basis_node = resolved_by_label.get(basis_label)
                        if basis_node is None:
                            tally.relation_drop_count += 1
                            continue
                        self._append_edge(
                            Edge(
                                source_id=decision.node.id,
                                target_id=basis_node.id,
                                weight=0.85,
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="hierarchy",
                                relation_descriptor="abstracts_over",
                                creation_context="kadmos_paragraph_concept",
                            )
                        )
                        tally.edges_upserted += 1
                        local_edge_count += 1
                tally.relation_stage_duration_s += time.monotonic() - relation_started
            else:
                paragraph_concept_id = None

            # One row per paragraph, because the paragraph is the activation
            # context doctrine counts — "many distinct activation contexts", not
            # many mentions in one. Buffered like the query-path firings and
            # folded in by the tick; ingestion writes nodes directly but this is
            # a counter update on rows it is not otherwise rewriting.
            if referenced_existing:
                tally.firing_passes += 1
                self.mesh.firings.append_firing(referenced_existing)

            tally.paragraph_units.append(
                _ParagraphUnit(
                    paragraph_number=paragraph_index,
                    paragraph_anchor_id=str(paragraph_anchor.id),
                    chunk_id=str(chunk.id),
                    entity_ids=resolved_entity_ids,
                    paragraph_concept_id=paragraph_concept_id,
                    local_node_ids=local_node_ids,
                    local_edge_count=local_edge_count,
                )
            )

        tally.paragraph = tally.paragraphs_total + 1
        tally.stage = "relations_extracted"
        cross_started = time.monotonic()
        structural_pairs, structural_dropped = _select_structural_pairs(
            tally.paragraph_units, max_neighbours=self.max_structural_neighbours
        )
        if structural_dropped:
            # Doctrine: destruction is permitted under audit, never silently. The
            # capped pairs are recorded so a mesh can always account for the links
            # it chose not to make.
            self._append_audit(
                "mesh_ingest_structural_lattice_capped",
                {
                    "kept_pairs": len(structural_pairs),
                    "dropped_pairs": structural_dropped,
                    "max_neighbours": self.max_structural_neighbours,
                },
            )
        for left_unit, right_unit, shared_count in structural_pairs:
            weight = min(0.25 + (0.10 * shared_count), 0.70)
            for source_id, target_id in (
                (left_unit.paragraph_anchor_id, right_unit.paragraph_anchor_id),
                (right_unit.paragraph_anchor_id, left_unit.paragraph_anchor_id),
            ):
                self._append_edge(
                    Edge(
                        source_id=source_id,  # type: ignore[arg-type]
                        target_id=target_id,  # type: ignore[arg-type]
                        weight=weight,
                        born_at=datetime.now(UTC),
                        last_fired_at=datetime.now(UTC),
                        relation_kind="co_occurrence",
                        relation_descriptor="shares_entities_with",
                        creation_context="kadmos_cross_paragraph",
                    )
                )
                tally.edges_upserted += 1
            tally.cross_pass_link_count += 2
            self._append_audit(
                "mesh_ingest_cross_paragraph_link",
                {
                    "left_paragraph": left_unit.paragraph_number,
                    "right_paragraph": right_unit.paragraph_number,
                    "shared_entity_count": shared_count,
                },
            )

            if (
                left_unit.paragraph_concept_id is not None
                and right_unit.paragraph_concept_id is not None
                and left_unit.paragraph_concept_id != right_unit.paragraph_concept_id
            ):
                self._append_edge(
                    Edge(
                        source_id=left_unit.paragraph_concept_id,  # type: ignore[arg-type]
                        target_id=right_unit.paragraph_concept_id,  # type: ignore[arg-type]
                        weight=min(weight, 0.55),
                        born_at=datetime.now(UTC),
                        last_fired_at=datetime.now(UTC),
                        relation_kind="semantic",
                        relation_descriptor="develops_across_paragraphs",
                        creation_context="kadmos_cross_paragraph",
                    )
                )
                tally.edges_upserted += 1
                tally.cross_pass_link_count += 1

        tally.relation_stage_duration_s += time.monotonic() - cross_started

        # Connectivity metrics read the edge and node tables — the buffers must
        # land first. Edges need no model and go first; the revisions may call
        # the embedder, so the staged audit rows are flushed in `finally`, and an
        # embed call failing at flush time cannot take them with it. If one does
        # fail, `read_text` writes the run's failure report (PHX-1116).
        tally.stage = "stored"
        self._flush_edges()
        try:
            await self._flush_revisions()
        finally:
            self._flush_audit()

        metrics: dict[str, float | int] = {}
        anomalies: list[str] = []
        recommendations: list[str] = []
        if self.connectivity_metrics:
            metrics = self._compute_connectivity_metrics(tally.paragraph_units)
            anomalies, recommendations = self._build_connectivity_observations(
                metrics,
                tally.cross_pass_link_count,
            )
        status: Literal["completed", "partial", "failed", "aborted"] = (
            "completed" if tally.llm_failure_count == 0 else "partial"
        )

        _, quality_flags = _resolution_and_quality(tally)
        verdict, reasoning = ingest_verdict(
            status=status,
            parse_error_rate=quality_flags.parse_error_rate,
            low_tier_ratio=quality_flags.low_tier_ratio,
            anomalies=anomalies,
            thresholds=self.settings.report.thresholds.ingest,
        )

        audit_run_id = self._append_audit(
            "mesh_ingest_run",
            {
                "status": status,
                "paragraphs": len(tally.paragraph_units),
                "mentions": tally.total_mentions,
                "relations_written": tally.total_relations_written,
                "cross_paragraph_links": tally.cross_pass_link_count,
                "metrics": metrics,
                # A workspace does not say which arm built it; the run does.
                "accrue_descriptions": self.accrue_descriptions,
                "accrue_unnamed": self.accrue_unnamed,
                "revise_identity_vector": self.revise_identity_vector,
                "descriptions_revised": tally.descriptions_revised,
                "descriptions_declined_unnamed": tally.descriptions_declined_unnamed,
            },
        )
        tally.run_row_id = audit_run_id

        report = self._ingest_report(
            tally,
            status=status,
            verdict=verdict,
            reasoning=reasoning,
            anomalies=anomalies,
            recommendations=recommendations,
            audit_run_id=audit_run_id,
            source_type=source_type,
            source_identifier=source_identifier,
        )
        report_path = self.report_writer.write(report)

        elapsed = time.monotonic() - tally.started_monotonic
        return {
            "paragraphs": len(tally.paragraph_units),
            "concepts": tally.total_mentions,
            "relations": tally.total_relations_written,
            "paragraph_concepts": tally.paragraph_concept_count,
            "paragraph_concept_nodes": len(tally.paragraph_concept_node_ids),
            # Paragraphs that referenced a node the substrate already had. Zero
            # would mean every reference minted a fresh node — the fragmentation
            # PHX-1097 had to clean up after the fact (PHX-1101).
            "firing_passes": tally.firing_passes,
            # Revisions of existing descriptions, one per mention that added
            # text, so a node read three times can count twice (PHX-1118);
            # 0 when accrual is off.
            "descriptions_revised": tally.descriptions_revised,
            # Re-mentions whose text did not accrue: the mention named the node
            # otherwise (PHX-1121); 0 when accrual is off or `accrue_unnamed`.
            "descriptions_declined_unnamed": tally.descriptions_declined_unnamed,
            # What stances the read produced, and how many relations the text
            # itself framed as a disagreement. A histogram with one key would
            # mean the vocabulary reached the model and the model ignored it
            # (PHX-1107).
            "stances": dict(sorted(tally.stance_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "contradiction_edges": tally.contradiction_edge_count,
            "llm_calls": tally.total_llm_calls,
            "llm_cost_eur": round(tally.total_llm_cost_eur, 6),
            "elapsed_s": round(elapsed, 1),
            "source_anchor_id": str(text_anchor_node.id),
            "paragraph_anchor_count": tally.paragraph_anchor_count,
            "cross_paragraph_links": tally.cross_pass_link_count,
            "connectivity": metrics,
            "report_run_id": report.run_id,
            "report_path": str(report_path),
            "verdict": report.verdict,
        }

    async def _vectorize_concepts(
        self,
        concepts: list[LLMConcept],
    ) -> list[tuple[list[float], list[float], list[float]]]:
        # Same text the node will carry, so the stored description and the
        # vector that matches against it cannot drift apart.
        descriptions = [_entity_description(c.label, c.description) for c in concepts]
        labels = [concept.label for concept in concepts]
        semantic_vectors = await self.vectorizer.semantic_many(descriptions)
        # An entity holds no stance — 'Zeus' is neither asserted nor denied.
        # The claims about it live on the chunks that reference it, and those
        # carry the frames. `MESH_RETRIEVAL` has consolidated nodes inherit the
        # dominant frame of their chunks; that pass is built —
        # `runtime.frame_promotion.run_frame_promotion` (PHX-1107), run after a
        # read — but as of 2026-10-25 no read, tick, CLI or MCP path calls it,
        # so entities leave the reader neutral rather than carrying a guess and
        # take a stance only when an operator runs it. Frame routing sees them
        # only from then on (docs/etappes/contradiction.md, "The Routing Only
        # Works Once Entities Carry a Stance").
        frame_vectors = [frames.neutral_frame(self.frame_dim) for _ in labels]
        description_vectors = await self.vectorizer.description_many(descriptions)
        return list(zip(semantic_vectors, frame_vectors, description_vectors, strict=False))

    async def _read_paragraph(
        self,
        text: str,
    ) -> tuple[ParagraphReadingOutput | None, dict[str, Any]]:
        user_prompt = paragraph_prompt(text)
        started = time.monotonic()
        try:
            result = await self.llm.complete(
                prompt=user_prompt,
                system=SYSTEM_PROMPT,
                json_schema=ParagraphReadingOutput.model_json_schema(),
                temperature=0.1,
                timeout_s=45,
            )
            # Providers differ in how strictly they honour a JSON schema. DeepSeek
            # returns name/wikidata_id/subject/object, which failed validation
            # outright — every paragraph became a schema failure and ingestion
            # produced nothing but source anchors. Normalising known aliases first
            # keeps a good extraction that merely disagrees on spelling; anything
            # structurally unusable still fails validation below.
            payload = normalize_reading_payload(json.loads(result.text))
            output = ParagraphReadingOutput.model_validate(payload)
            return output, {
                "cost_eur": result.cost_eur,
                "duration_s": time.monotonic() - started,
                "failed": False,
                "schema_failed": False,
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM paragraph reading failed: %s", exc)
            return None, {
                "cost_eur": 0.0,
                "duration_s": time.monotonic() - started,
                "failed": True,
                "schema_failed": True,
            }

    def _remember_frame(self, node_id: str, frame: list[float]) -> None:
        """Record a node's frame so edges touching it can score consistency."""
        self._frames[str(node_id)] = frame

    def _append_edge(self, edge: Edge) -> None:
        """Buffer an edge; the batch is flushed by :meth:`_flush_edges`.

        Each Lance append is a transaction whose cost grows with the table, so
        per-edge writes dominated ingestion: measured at 119 ms/edge on a
        27.8k-edge mesh (~21 s for one paragraph's ~180 edges) versus 0.01 s for
        the same edges appended as one batch — a ~2000x difference, and the real
        reason a full read collapsed (PHX-1050, and the cost attributed to
        PHX-1047). `append_edge` is literally `append_edges([edge])`, so batching
        changes throughput and nothing else.

        The linker is told about each edge immediately: its adjacency is in-memory
        and feeds context scoring during this same run, so it must not wait for
        the flush.

        `frame_consistency` is filled here rather than at each of the dozen
        construction sites, from the frames this run recorded. Where an endpoint
        is an entity or a source anchor the frame is neutral and the cosine is
        1.0 by definition, so the field only carries information on edges
        between two claim-bearing nodes — structural edges between paragraphs,
        which is exactly where an inconsistency is worth knowing about.
        """
        if edge.frame_consistency == 1.0:
            left = self._frames.get(str(edge.source_id))
            right = self._frames.get(str(edge.target_id))
            if left is not None and right is not None:
                edge.frame_consistency = max(0.0, frames.frame_cosine(left, right))
        if edge.valid_from is None:
            # When the substrate came to hold this. `valid_to` stays None until
            # something supersedes it (PANTHEON_VISION Non-Negotiable 3).
            edge.valid_from = edge.born_at
        self._pending_edges.append(edge)
        self.linker.remember_edge(edge)
        # Bounded so a book-length read neither holds every edge in memory nor
        # loses a whole run's writes to one crash. The batch is what matters, not
        # its exactness: 512 appends in one transaction is already ~2000x cheaper
        # than 512 transactions.
        if len(self._pending_edges) >= _EDGE_FLUSH_BATCH:
            self._flush_edges()

    def _flush_edges(self) -> None:
        """Write the buffered edges as one Lance append."""
        if not self._pending_edges:
            return
        try:
            self.mesh.edges.append_edges(self._pending_edges)
        except Exception as exc:
            self._flush_failures.setdefault("edges", _error_text(exc))
            raise
        self._pending_edges = []

    def _flush_audit(self) -> None:
        """Write the staged audit rows; remember a failure for the report."""
        try:
            self.mesh.audit.flush()
        except Exception as exc:
            self._flush_failures.setdefault("audit", _error_text(exc))
            raise

    def _store_counts(self) -> dict[str, int]:
        """Rows in the tables a read adds to — three metadata reads, no scan."""
        return {
            "consolidated": self.mesh.nodes.consolidated_count(),
            "chunks": self.mesh.nodes.chunk_count(),
            "edges": self.mesh.edges.count_rows(),
        }

    def _accrue_description(
        self,
        node: ConsolidatedNode,
        body: str,
        *,
        chunk_id: ULID,
        now: datetime,
    ) -> ConsolidatedNode | None:
        """Fold a later mention's description into ``node``; None when nothing new.

        The revision is kept in memory (by node id, so a second mention in the
        same window builds on it) and written by :meth:`_flush_revisions`. The
        vector is not touched here: all pending descriptions are embedded in one
        call at flush time.
        """
        # Nothing rewrites a consolidated row during a read except this flush:
        # merge_identity_evidence writes only authoritative Q-IDs, and read_text
        # offers none; firings go to the sidecar and are folded by the tick. The
        # resolver's cached copy is not reliable inside a window — a candidate
        # search for a later concept re-remembers the stored, pre-revision row —
        # so the merge base always comes from `_pending_revisions`; the cache is
        # brought back to the written row in `_flush_revisions`.
        base = self._pending_revisions.get(str(node.id), node)
        merged = merge_description(base.description or "", body)
        if merged is None:
            return None
        sources = base.description_source_chunks
        if chunk_id not in sources:
            # Two concepts of one paragraph may resolve to one node; one chunk, once.
            sources = [*sources, chunk_id]
        revised = base.model_copy(
            update={
                "description": merged,
                "description_source_chunks": sources,
                "description_generated_at": now,
            }
        )
        self._pending_revisions[str(revised.id)] = revised
        return revised

    async def _flush_revisions(self) -> int:
        """Embed every pending revision in one call and rewrite the rows in one write.

        Both vectors follow the text: the reader creates an entity node with
        ``semantic_vector`` and ``description_vector`` from the same string, and
        the consolidation pass sets both when it regenerates a description.
        """
        if not self._pending_revisions:
            return 0
        nodes = list(self._pending_revisions.values())
        embed_started = time.monotonic()
        try:
            vectors = await self.vectorizer.description_many([n.description or "" for n in nodes])
            embed_s = time.monotonic() - embed_started
            revised = [
                node.model_copy(
                    update=(
                        {"description_vector": vector, "semantic_vector": vector}
                        if self.revise_identity_vector
                        else {"semantic_vector": vector}
                    )
                )
                for node, vector in zip(nodes, vectors, strict=True)
            ]
            write_started = time.monotonic()
            self.mesh.nodes.update_consolidated_many(revised)
        except Exception as exc:
            self._flush_failures.setdefault("revisions", _error_text(exc))
            # The description_revised rows for these nodes are already staged and
            # the caller's audit flush writes them; say that the rows they
            # describe never reached the store, then let the failure surface
            # (honest failure, AGENTS.md contract 3).
            self._append_audit(
                "mesh_ingest_description_flush_failed",
                {
                    "node_ids": [str(n.id) for n in nodes],
                    "pending": len(nodes),
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            raise
        for node in revised:
            # The resolver hands cached copies back on the Q-ID path without a
            # store read; keep them at the row just written, or the next mention
            # would build on the pre-revision text and overwrite this one.
            self.registry.refresh(node)
        log.info(
            "revised %d descriptions: embedded in %.2f s, written in %.0f ms",
            len(revised),
            embed_s,
            (time.monotonic() - write_started) * 1000,
        )
        self._pending_revisions = {}
        return len(revised)

    def _ingest_report(
        self,
        tally: _ReadTally,
        *,
        status: Literal["completed", "partial", "failed", "aborted"],
        verdict: Literal["good", "partial", "poor", "failed", "completed"],
        reasoning: str,
        anomalies: list[str],
        recommendations: list[str],
        audit_run_id: str | None,
        source_type: str,
        source_identifier: str,
        failed_stage: IngestStageName | None = None,
        failure_note: str | None = None,
        landed: dict[str, int] | None = None,
        edges_unwritten: int = 0,
        tolerant: bool = False,
    ) -> IngestRunReport:
        """The run's IngestRunReport from its tally — one builder for both paths.

        ``landed`` is what the store gained, counted from its tables, and stands
        in for the read's own node and edge counters when given; ``tolerant``
        lets the failure path build a report even if a summary cannot be
        computed from the tally.
        """
        try:
            resolution, quality_flags = _resolution_and_quality(tally)
        except Exception as quality_exc:
            if not tolerant:
                raise
            resolution, quality_flags = ResolutionSummary(), QualityFlags()
            anomalies = [
                *anomalies,
                "the resolution and quality summary could not be computed "
                f"({_error_text(quality_exc)}); defaults stand in",
            ]
        durations: list[tuple[IngestStageName, float]] = [
            ("acquired", tally.acquired_duration_s),
            ("cleaned", tally.cleaned_duration_s),
            ("sentencized", tally.sentencized_duration_s),
            ("mentions_extracted", tally.llm_duration_s),
            ("mentions_resolved", tally.resolve_stage_duration_s),
            ("relations_extracted", tally.relation_stage_duration_s),
            ("embedded", tally.embed_stage_duration_s),
            ("stored", tally.store_stage_duration_s),
        ]
        stages = [
            IngestStageReport(
                name=name,
                duration_s=max(0.0, duration),
                status="failed" if name == failed_stage else "ok",
                notes=failure_note if name == failed_stage else None,
            )
            for name, duration in durations
        ]
        finished_at = datetime.now(UTC)
        return IngestRunReport(
            started_at=tally.started_at,
            finished_at=finished_at,
            duration_s=max(0.0, finished_at.timestamp() - tally.started_at.timestamp()),
            status=status,
            verdict=verdict,
            verdict_reasoning=reasoning,
            anomalies=anomalies,
            recommendations=recommendations,
            audit_log_run_id=audit_run_id,
            source_type=source_type,
            source_identifier=source_identifier,
            word_count=tally.word_count,
            sentence_count=tally.sentence_count,
            chapter_count=None,
            stages=stages,
            ner=NerSummary(
                total_mentions=tally.total_mentions,
                by_type={},
            ),
            resolution=resolution,
            relations=RelationSummary(
                attempted=tally.total_relations_attempted,
                parsed_ok=tally.total_relations_written,
                dropped_schema_violation=tally.llm_schema_failures,
                dropped_evidence_span_violation=tally.relation_drop_count,
                llm_cost_eur=round(tally.total_llm_cost_eur, 6),
            ),
            embedding=EmbeddingSummary(
                nodes_embedded=tally.nodes_embedded,
                embedding_model_id=self.vectorizer.semantic_model_id,
                duration_s=max(0.0, tally.embed_stage_duration_s),
            ),
            store=StoreSummary(
                nodes_upserted=(
                    landed["consolidated"] + landed["chunks"]
                    if landed is not None
                    else tally.nodes_upserted
                ),
                # An edge counts once it is in the store; without a count from
                # the store, a buffer whose write raised is subtracted instead.
                edges_upserted=(
                    landed["edges"]
                    if landed is not None
                    else max(0, tally.edges_upserted - edges_unwritten)
                ),
                idempotent_skips=0,
                descriptions_revised=tally.descriptions_revised,
            ),
            quality_flags=quality_flags,
        )

    async def _report_failure(
        self,
        tally: _ReadTally,
        exc: Exception,
        *,
        source_type: str,
        source_identifier: str,
    ) -> None:
        """Write what the failure left writable, then a report that says what landed.

        Never raises: the read's own exception is what the caller must see, so
        anything going wrong here is logged and noted on that exception instead.
        """
        try:
            error = _error_text(exc)
            failures = dict(self._flush_failures)
            anomalies: list[str] = []
            # Edges first: they need no model, and every buffered edge points at
            # nodes the read has already written, so landing them leaves no
            # dangling endpoint and gives the nodes of the paragraphs read so far
            # their edges. Not retried when their own write raised.
            if "edges" not in failures and self._pending_edges:
                pending = len(self._pending_edges)
                try:
                    self._flush_edges()
                    anomalies.append(f"{pending} buffered edges written after the failure")
                except Exception as flush_exc:  # noqa: BLE001 - reported, not raised
                    anomalies.append(
                        f"{pending} buffered edges could not be written after the failure: "
                        f"{_error_text(flush_exc)}"
                    )
            # The staged audit rows next, before the revisions change any node:
            # one table add, which keeps its rows when it raises, so trying it
            # again cannot duplicate them — even when it was the write that raised.
            self._try_flush_audit()
            # The revisions may call the embedder; a failing one records its own
            # mesh_ingest_description_flush_failed row.
            if "revisions" not in failures and self._pending_revisions:
                pending = len(self._pending_revisions)
                try:
                    await self._flush_revisions()
                    anomalies.append(f"{pending} revised descriptions written after the failure")
                except Exception as flush_exc:  # noqa: BLE001 - reported, not raised
                    anomalies.append(
                        f"{pending} revised descriptions could not be written after the "
                        f"failure: {_error_text(flush_exc)}"
                    )
            if "edges" in failures and self._pending_edges:
                anomalies.append(
                    f"{len(self._pending_edges)} buffered edges not written: their write "
                    f"raised ({failures['edges']}); append_edges writes three tables in "
                    "turn, and the edge count below is the store's, so any that landed in "
                    "the first are counted"
                )
            if "revisions" in failures and self._pending_revisions:
                anomalies.append(
                    f"{len(self._pending_revisions)} revised descriptions not written: their "
                    f"write raised ({failures['revisions']}); "
                    "mesh_ingest_description_flush_failed names the nodes"
                )

            if tally.boundary is not None:
                where = (
                    f"at the compaction boundary after paragraph {tally.boundary} "
                    f"of {tally.paragraphs_total}"
                )
            elif tally.paragraph == 0:
                where = "before the first paragraph"
            elif tally.paragraph > tally.paragraphs_total:
                where = "after the last paragraph"
            else:
                where = f"at paragraph {tally.paragraph} of {tally.paragraphs_total}"
            first = next(iter(failures), None)
            writing = f", writing {_BUFFER_NAMES[first]}" if first else ""
            reasoning = f"read raised {error} {where} ({tally.stage}{writing})"

            # The run's own row: a failed run, or — when the success path had
            # already written its completed row and only the report failed — a
            # row that says so and points at it, so one read is one run.
            if tally.run_row_id is None:
                action, detail = (
                    "mesh_ingest_run",
                    {
                        "status": "failed",
                        "error": error[:2000],
                        "stage": tally.stage,
                        "paragraph": tally.paragraph,
                        "paragraphs": len(tally.paragraph_units),
                        "mentions": tally.total_mentions,
                        "relations_buffered": tally.total_relations_written,
                        # the arm that wrote the partial workspace, as the success
                        # row names it (PHX-1118, PHX-1121)
                        "accrue_descriptions": self.accrue_descriptions,
                        "accrue_unnamed": self.accrue_unnamed,
                        "revise_identity_vector": self.revise_identity_vector,
                        "descriptions_revised": tally.descriptions_revised,
                        "descriptions_declined_unnamed": tally.descriptions_declined_unnamed,
                    },
                )
            else:
                action, detail = (
                    "mesh_ingest_report_failed",
                    {"run_row": tally.run_row_id, "error": error[:2000]},
                )
            row_id: str | None = None
            # A `stage` that raises (its batch was full and the write failed)
            # keeps the row staged; the flush below tries it again.
            with contextlib.suppress(Exception):
                row_id = self.mesh.audit.stage(action=action, detail=detail)
            audit_error = self._try_flush_audit()
            staged_left = self.mesh.audit.pending()
            if staged_left:
                anomalies.append(
                    f"{staged_left} audit rows could not be written ({audit_error}); they are "
                    "held only in this process's memory and are lost when it exits"
                )
            elif "audit" in failures:
                anomalies.append(
                    f"the staged audit rows' first write raised ({failures['audit']}); a "
                    "second attempt wrote them"
                )
            audit_run_id = tally.run_row_id or (row_id if not staged_left else None)

            landed: dict[str, int] | None = None
            if tally.store_before is not None:
                try:
                    after = self._store_counts()
                    landed = {key: after[key] - tally.store_before[key] for key in after}
                except Exception as count_exc:  # noqa: BLE001 - reported, not raised
                    anomalies.append(
                        "the store could not be counted after the failure "
                        f"({_error_text(count_exc)}); the node and edge counts are the read's own"
                    )
            if landed is not None and not any(landed.values()):
                recommendations = [
                    "Nothing of this read reached the workspace; the text can be read again "
                    "as it is."
                ]
            else:
                nodes = (landed["consolidated"] + landed["chunks"]) if landed else None
                held = (
                    f"{nodes} node{'s' if nodes != 1 else ''} and {landed['edges']} "
                    f"edge{'s' if landed['edges'] != 1 else ''}"
                    if landed is not None and nodes is not None
                    else "part"
                )
                parts = "the source anchor and " if tally.source_anchor_written else ""
                recommendations = [
                    f"At the failure the workspace held {held} of this read: {parts}"
                    f"{tally.paragraph_anchor_count} paragraph anchors with their chunks. "
                    "Reading the same text again writes a second source anchor and a second "
                    "chunk for every paragraph that had landed."
                ]
            report = self._ingest_report(
                tally,
                status="failed",
                verdict="failed",
                reasoning=reasoning,
                anomalies=anomalies,
                recommendations=recommendations,
                audit_run_id=audit_run_id,
                source_type=source_type,
                source_identifier=source_identifier,
                failed_stage=tally.stage,
                failure_note=error[:500],
                landed=landed,
                edges_unwritten=len(self._pending_edges),
                tolerant=True,
            )
            self.failure_report = report
            try:
                path = self.report_writer.write(report)
            except Exception as write_exc:  # noqa: BLE001 - reported, not raised
                self.failure_report_error = _error_text(write_exc)
                log.error("the failure report of a read could not be written: %s", write_exc)
                exc.add_note(
                    f"IngestRunReport {report.run_id} (status failed) could not be written: "
                    f"{self.failure_report_error}"
                )
            else:
                self.failure_report_path = path
                exc.add_note(f"IngestRunReport {report.run_id} (status failed): {path}")
        except Exception:  # noqa: BLE001 - must not replace the read's own exception
            log.exception("the failure report of a read could not be built")

    def _try_flush_audit(self) -> str | None:
        """Flush the staged audit rows; the error text if it raised, else None."""
        try:
            self._flush_audit()
        except Exception as audit_exc:  # noqa: BLE001 - the caller reports it
            return _error_text(audit_exc)
        return None

    def _append_audit(self, action: str, detail: dict[str, Any]) -> str:
        # A direct append that raises leaves its row staged (MeshAuditLog.append),
        # so the failure path's flush takes it with the rest; it marks no buffer.
        return self.mesh.audit.append(action=action, detail=detail)

    def _stage_audit(self, action: str, detail: dict[str, Any]) -> str:
        """Stamp a per-item audit row now, write it with the batch.

        Only the hot path uses this. The run-level entries keep writing straight
        through, so a crash mid-paragraph still leaves a record of what the run
        was. Measured at 269.8 ms per unbatched write inside a real ingest —
        the largest single term in the resolution stage (PHX-1061).
        """
        try:
            return self.mesh.audit.stage(action=action, detail=detail)
        except Exception as exc:
            # `stage` writes the batch itself once it is full.
            self._flush_failures.setdefault("audit", _error_text(exc))
            raise

    def _compute_connectivity_metrics(
        self,
        paragraph_units: list[_ParagraphUnit],
    ) -> dict[str, float | int]:
        edges = self.mesh.edges.load_all_edges()
        adjacency: dict[str, set[str]] = {}
        node_ids: set[str] = set()
        for edge in edges:
            source_id = str(edge.source_id)
            target_id = str(edge.target_id)
            node_ids.add(source_id)
            node_ids.add(target_id)
            adjacency.setdefault(source_id, set()).add(target_id)
            adjacency.setdefault(target_id, set()).add(source_id)

        components: list[set[str]] = []
        unvisited = set(node_ids)
        while unvisited:
            start = unvisited.pop()
            stack = [start]
            component = {start}
            while stack:
                current = stack.pop()
                for neighbour in adjacency.get(current, set()):
                    if neighbour in unvisited:
                        unvisited.remove(neighbour)
                        component.add(neighbour)
                        stack.append(neighbour)
            components.append(component)

        largest_component_ratio = 0.0
        if components and node_ids:
            largest_component_ratio = len(max(components, key=len)) / len(node_ids)

        consolidated_ids = {str(node.id) for node in self.mesh.nodes.load_all_consolidated()}
        isolated_consolidated_nodes = sum(
            1 for node_id in consolidated_ids if not adjacency.get(node_id)
        )
        paragraph_degrees = []
        for unit in paragraph_units:
            local_degree_sum = sum(
                len(adjacency.get(node_id, set()) & unit.local_node_ids)
                for node_id in unit.local_node_ids
            )
            paragraph_degrees.append(local_degree_sum / max(1, len(unit.local_node_ids)))

        return {
            "largest_connected_component_ratio": round(largest_component_ratio, 4),
            "edge_to_node_ratio": round(len(edges) / max(1, len(node_ids)), 4),
            "paragraph_local_average_degree": round(
                sum(paragraph_degrees) / max(1, len(paragraph_degrees)),
                4,
            ),
            "isolated_consolidated_nodes": isolated_consolidated_nodes,
        }

    def _build_connectivity_observations(
        self,
        metrics: dict[str, float | int],
        cross_paragraph_links: int,
    ) -> tuple[list[str], list[str]]:
        anomalies: list[str] = []
        recommendations: list[str] = []
        if float(metrics["largest_connected_component_ratio"]) < 0.75:
            anomalies.append("graph_fragmented")
            recommendations.append(
                "Inspect paragraph co-mention density and cross-paragraph linking thresholds."
            )
        if int(metrics["isolated_consolidated_nodes"]) > 3:
            anomalies.append("isolated_consolidated_nodes")
            recommendations.append(
                "Review concept extraction and source-anchor attachment for orphan nodes."
            )
        if cross_paragraph_links == 0:
            anomalies.append("no_cross_paragraph_links")
            recommendations.append(
                "Use a longer source or lower cross-paragraph overlap thresholds for smoke checks."
            )
        return anomalies, recommendations


def name_key(text: str) -> str:
    """A name compared as a name: case, accents, punctuation and a possessive "'s"
    do not count; letters of every script do."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    kept = "".join(ch for ch in folded if not unicodedata.combining(ch))
    kept = re.sub(r"['’]s\b", "", kept)
    return " ".join(re.sub(r"[^\w\s]", " ", kept).split())


def names_node(label: str, node: ConsolidatedNode) -> bool:
    """Whether a mention calls ``node`` by its name — the condition for its text to accrue.

    The name is the label the node was created with, which the reader puts first
    in its tags; a node without tags is named by the head of its description.
    Equal under :func:`name_key`, not overlapping: "Spain" does not name "Spanish
    Empire", "France" does not name "Rhône" whose tags say it lies in France, and
    "Hugh of Italy" does not name "Hugh, King of Italy" — the price of the rule,
    paid in accrual a variant does not get, never in a link (PHX-1121).
    """
    name = node.tags[0] if node.tags else (node.description or "").split(" — ", 1)[0]
    key = name_key(label)
    return bool(key) and key == name_key(name)


def _resolution_and_quality(tally: _ReadTally) -> tuple[ResolutionSummary, QualityFlags]:
    """The resolution summary and quality flags a read's tally implies."""
    resolution = ResolutionSummary(
        qid_claims_dropped=tally.qid_claims_dropped,
        tier_counts={
            _SIGNAL_TO_TIER[signal]: count
            for signal, count in tally.signal_counts.items()
            if count > 0
        },
    )
    # Drops are relations and basis labels that resolved to no concept; both
    # belong in the denominator, or a reading with unresolved basis labels and
    # few relations rates above 1 and the report cannot be built (PHX-1116).
    parse_error_rate = tally.relation_drop_count / max(
        1,
        tally.total_relations_attempted + tally.basis_attempted + tally.llm_failure_count,
    )
    quality_flags = QualityFlags(
        low_tier_ratio=resolution.low_tier_ratio,
        schema_violation_rate=tally.llm_schema_failures / max(1, tally.total_llm_calls),
        parse_error_rate=parse_error_rate,
    )
    return resolution, quality_flags


def _entity_description(label: str, description: str) -> str:
    """Compose the doctrine's Tier-1 description: name **plus** discriminators.

    MESH_SUBSTRATE §"Tier-1+ — Consolidated Node" specifies `description` as
    "short discriminating text — for entities: name + key discriminators". The
    reading model returns those two apart: a label ("Zeus") and a bare
    discriminator ("King of the gods, god of the sky and thunder, son of
    Cronos"). Storing only the discriminator throws the identity away.

    Measured before this change: 8 of 8 concepts lost their name on the way in.
    No node in a 6,816-node Theogony mesh was called Cronus, three distinct
    nymphs all read "A nymph whose name derives from a land over which she
    presides", and eight separate nodes described Zeus as son of Cronos without
    any of them saying Zeus. Identity matching, deduplication and name queries
    all ran on text that had had the name removed (PHX-1065).

    The name goes at the head so every mention of one entity shares a prefix —
    that is what makes two descriptions of the same figure land near each other
    under `description_vector`, which is the identity-matching surface.
    """
    name = (label or "").strip()
    body = (description or "").strip()
    if not name:
        return body
    if not body:
        return name
    if body.lower().startswith(name.lower()):
        return body
    return f"{name} — {body}"


def merge_description(standing: str, body: str) -> str | None:
    """Fold a later mention's description into the standing one, deterministically.

    ``standing`` is the node's description as stored (name at the head, see
    :func:`_entity_description`); ``body`` is the new mention's bare
    description from the reading model. The head never moves — the label index,
    the resolver's aliases and the PHX-1051 naming guard all key on it — so the
    standing text stays a byte-identical prefix of the result. Each sentence of
    ``body`` not already present (compared case-folded, whitespace-collapsed and
    without terminal punctuation; the body of the head counts as present) is
    appended in order while the result stays within :data:`DESCRIPTION_MAX_CHARS`;
    a sentence that would cross the cap stops the merge at the sentence
    boundary. Returns None when nothing was added: a None is not a revision.
    """
    standing = (standing or "").strip()
    if len(standing) >= DESCRIPTION_MAX_CHARS:
        return None
    result = standing
    seen = _comparable(result)
    for sentence in _split_sentences(body or ""):
        parts = [p for p in (_comparable(x) for x in _SENTENCE_BREAK.split(sentence)) if p]
        if not parts or all(_contains(seen, part) for part in parts):
            continue
        tail = result.rstrip("\"”’')]")
        if not result:
            candidate = sentence
        elif tail and tail[-1] in ".!?…,;:":
            candidate = f"{result} {sentence}"
        else:
            candidate = f"{result}. {sentence}"
        if len(candidate) > DESCRIPTION_MAX_CHARS:
            break
        result = candidate
        seen = _comparable(result)
    return result if result != standing else None


def _split_sentences(text: str) -> list[str]:
    """The sentences of ``text``, whitespace-collapsed; an abbreviation never ends one."""
    out: list[str] = []
    for part in _SENTENCE_BREAK.split(text.strip()):
        part = re.sub(r"\s+", " ", part).strip()
        if not part:
            continue
        if out and _ABBREVIATION_TAIL.search(out[-1]):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out


def _comparable(text: str) -> str:
    """Case-folded, whitespace-collapsed, without wrapping quotes or terminal punctuation."""
    text = re.sub(r"\s+", " ", text.casefold()).strip()
    return text.strip("\"“”‘’'").rstrip(".!?…").strip("\"“”‘’' ")


def _contains(haystack: str, key: str) -> bool:
    """Whether ``key`` occurs in ``haystack`` as whole words, not inside a word."""
    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", haystack) is not None


def _concept_tags(concept: LLMConcept) -> list[str]:
    """Tags for a concept, with its name first.

    The label is a discriminating feature and belongs in the keyword cloud; it
    is also what makes the node findable by name, since the label index is built
    from description plus tags. Without it, `find_consolidated_by_labels("Zeus")`
    could only match nodes whose *description text* happened to contain the word.
    """
    tags = [concept.label.strip()] if concept.label and concept.label.strip() else []
    for tag in dict.fromkeys(concept.tags):
        if tag and tag not in tags:
            tags.append(tag)
    if concept.entity_type and concept.entity_type not in tags:
        tags.append(concept.entity_type)
    return tags or ["concept"]


def _select_structural_pairs(
    units: list[_ParagraphUnit], *, max_neighbours: int
) -> tuple[list[tuple[_ParagraphUnit, _ParagraphUnit, int]], int]:
    """Keep each paragraph's strongest entity-sharing partners (PHX-1049).

    Returns ``(kept_pairs, dropped_count)`` where each kept pair carries its
    shared-entity count, so the caller still weights edges by overlap strength.

    Selection is **union, not intersection**: a pair survives if *either*
    endpoint ranks it in its top ``max_neighbours``. That is what preserves the
    property the lattice was there for — the founding mesh is one connected
    component with no isolated nodes — because a paragraph with few partners
    keeps all of them even when its partners are individually popular.

    ``max_neighbours <= 0`` disables the cap and restores the previous
    all-pairs behaviour, which the A/B in PHX-1049 needs as its control arm.
    """
    scored: list[tuple[int, int, int]] = []
    for left_index, right_index in combinations(range(len(units)), 2):
        shared = units[left_index].entity_ids & units[right_index].entity_ids
        if shared:
            scored.append((left_index, right_index, len(shared)))

    if max_neighbours <= 0 or not scored:
        return [(units[i], units[j], n) for i, j, n in scored], 0

    partners: dict[int, list[tuple[int, int]]] = {}
    for left_index, right_index, count in scored:
        partners.setdefault(left_index, []).append((count, right_index))
        partners.setdefault(right_index, []).append((count, left_index))

    keep: set[tuple[int, int]] = set()
    for index, candidates in partners.items():
        # Strongest overlap first; index breaks ties so the choice is deterministic.
        candidates.sort(key=lambda item: (-item[0], item[1]))
        for _count, other in candidates[:max_neighbours]:
            keep.add((min(index, other), max(index, other)))

    kept = [(units[i], units[j], n) for i, j, n in scored if (i, j) in keep]
    return kept, len(scored) - len(kept)


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs, stripping Gutenberg boilerplate."""
    start_markers = [
        "*** START OF THE PROJECT GUTENBERG EBOOK",
        "*** START OF THIS PROJECT GUTENBERG EBOOK",
    ]
    end_markers = [
        "*** END OF THE PROJECT GUTENBERG EBOOK",
        "*** END OF THIS PROJECT GUTENBERG EBOOK",
    ]
    for marker in start_markers:
        idx = text.find(marker)
        if idx >= 0:
            nl = text.find("\n", idx)
            if nl >= 0:
                text = text[nl + 1 :]
            break
    for marker in end_markers:
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
            break

    import re

    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def _count_sentences(text: str) -> int:
    return len(_split_sentences(text))
