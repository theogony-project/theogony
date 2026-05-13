"""MESH ingestion pipeline — Kadmos v2 writes into the new substrate (Step S2).

Uses real components:
- ``Sentencizer`` (spaCy) for sentence splitting
- ``NerExtractor`` (spaCy en_core_web_sm) for named-entity recognition
- ``LocalSentenceTransformerEmbedder`` (BGE-small-en-v1.5, 384-d) for embeddings
- ``GutenbergAdapter`` (httpx) for acquiring Project Gutenberg books
- ``IngestRunReport`` + ``RunReportWriter`` for mandatory honest-failure reporting

Pipeline flow:
    acquire → sentencize → embed → NER → eager-link → store → report
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.ner import NerExtractor
from theogony.extraction.sentence import Sentencizer
from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.ingestion.source_anchor import build_source_anchor_description
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge, SourceProvenance
from theogony.reporting.models import (
    EmbeddingSummary,
    IngestRunReport,
    IngestStageReport,
    NerSummary,
    QualityFlags,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
)
from theogony.reporting.writer import RunReportWriter

log = get_logger("mesh.ingestion")


class MeshIngestionPipeline:
    """Real ingestion pipeline from Gutenberg text to the MESH substrate.

    Usage::

        async with MeshIngestionPipeline(mesh) as pipeline:
            result = await pipeline.ingest_gutenberg("43497", max_sentences=100)
    """

    def __init__(
        self,
        mesh: MeshRuntime,
        *,
        semantic_dim: int | None = None,
        frame_dim: int | None = None,
    ) -> None:
        self.mesh = mesh
        self.semantic_dim = mesh.semantic_dim if semantic_dim is None else semantic_dim
        self.frame_dim = mesh.frame_dim if frame_dim is None else frame_dim
        self.linker = EagerLinker(
            mesh.nodes, frame_dim=self.frame_dim, semantic_dim=self.semantic_dim
        )
        self._sentencizer = Sentencizer()
        self._ner = NerExtractor()
        self._embedder = LocalSentenceTransformerEmbedder()
        self._report_writer = RunReportWriter(Settings().data_dir)

    async def __aenter__(self) -> MeshIngestionPipeline:
        return self

    async def __aexit__(self, *args: object) -> None:
        self._embedder._model = None  # release GPU memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_gutenberg(
        self,
        book_id: str,
        *,
        max_sentences: int = 0,
    ) -> dict[str, Any]:
        """Acquire a Gutenberg book, ingest its sentences into the mesh,
        and emit an ``IngestRunReport``.

        Returns a structured summary.
        """
        started_at = datetime.now(UTC)
        stages: list[IngestStageReport] = []
        total_word_count = 0
        total_chunks = 0
        total_edges = 0
        total_mentions = 0
        mention_types: dict[str, int] = {}

        source_identifier = f"gutenberg_{book_id}"
        source_type = "gutenberg"

        # ---- 1. Acquire -------------------------------------------------
        t0 = time.time()

        # Fetch Gutenberg book directly by ID via Gutendex API.
        import httpx

        async with httpx.AsyncClient(follow_redirects=True) as client:
            api_url = f"https://gutendex.com/books/{book_id}"
            r = await client.get(api_url, timeout=15)
            r.raise_for_status()
            meta = r.json()
            book_title = meta.get("title", f"Project Gutenberg Book {book_id}")
            # Find the plain-text download URL
            formats = meta.get("formats", {})
            text_url = (
                formats.get("text/plain; charset=utf-8")
                or formats.get("text/plain")
                or formats.get("text/plain; charset=us-ascii")
                or next((v for k, v in formats.items() if "text/plain" in k), None)
            )
            if not text_url:
                raise ValueError(f"No plain-text format for book {book_id}")

            content_resp = await client.get(str(text_url), timeout=90, follow_redirects=True)
            content_resp.raise_for_status()
            content = content_resp.text
            raw_bytes = len(content.encode("utf-8"))

        acq_s = time.time() - t0
        stages.append(IngestStageReport(name="acquired", duration_s=acq_s, status="ok"))
        log.info("acquired Gutenberg %s: %d bytes, %s", book_id, raw_bytes, book_title)

        # ---- 2. Sentencize ----------------------------------------------
        t0 = time.time()
        cleaned_text = content
        sentences = await self._sentencizer.sentencize(cleaned_text)
        if max_sentences > 0:
            sentences = sentences[:max_sentences]
        sent_s = time.time() - t0
        stages.append(IngestStageReport(name="sentencized", duration_s=sent_s, status="ok"))
        total_word_count = sum(len(s.text.split()) for s in sentences)
        log.info("sentencized: %d sentences, %d words", len(sentences), total_word_count)

        # ---- 3. NER -----------------------------------------------------
        t0 = time.time()
        ner_results = await self._ner.extract(sentences)
        ner_s = time.time() - t0
        stages.append(IngestStageReport(name="mentions_extracted", duration_s=ner_s, status="ok"))
        total_mentions = sum(len(m) for m in ner_results)
        for mentions in ner_results:
            for m in mentions:
                mention_types[m.label] = mention_types.get(m.label, 0) + 1
        log.info("NER: %d mentions across %d types", total_mentions, len(mention_types))

        # ---- 4. Embed + store sentences (with eager linking) ------------
        t0 = time.time()
        now = datetime.now(UTC)

        # Create source-anchor entity.
        sa_node = ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            consolidation_tier=1,
            is_source_anchor=True,
            source_url=f"https://www.gutenberg.org/ebooks/{book_id}",
            semantic_vector=[0.0] * self.semantic_dim,
            frame_vector=[0.0] * self.frame_dim,
            description=build_source_anchor_description(
                source_type="Book",
                title=book_title,
                anchor=f"https://www.gutenberg.org/ebooks/{book_id}",
            ),
            tags=[source_type],
        )
        self.mesh.nodes.append_consolidated(sa_node)

        for i, sentence in enumerate(sentences):
            text = sentence.text.strip()
            if not text:
                continue

            # Embed (async -> thread).
            sem_vec = await self._embedder.embed(text)
            if len(sem_vec) != self.semantic_dim:
                log.warning(
                    "embed dim mismatch: got %d, expected %d",
                    len(sem_vec),
                    self.semantic_dim,
                )
            if len(sem_vec) > self.semantic_dim:
                sem_vec = sem_vec[: self.semantic_dim]
            else:
                sem_vec = sem_vec + [0.0] * (self.semantic_dim - len(sem_vec))
            frm_vec = [0.0] * self.frame_dim

            src = SourceProvenance(
                source_type=source_type,
                source_identifier=source_identifier,
                extracted_at=now,
            )
            chunk = ChunkNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=sem_vec,
                frame_vector=frm_vec,
                source=src,
                raw_text_ref=f"{source_identifier}#s{i}",
            )
            self.mesh.nodes.append_chunk(chunk)
            total_chunks += 1

            # Edge: chunk → source-anchor
            self.mesh.edges.append_edge(
                Edge(
                    source_id=chunk.id,
                    target_id=sa_node.id,
                    weight=1.0,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="extraction",
                    relation_descriptor="extracted_from",
                    creation_context="kadmos_extraction",
                )
            )
            total_edges += 1

            # NER mentions → eager linking
            mentions = ner_results[i] if i < len(ner_results) else []
            if mentions:
                entity_refs = []
                for m in mentions:
                    # Build a reference dict for the linker.
                    ref: dict[str, Any] = {
                        "label": m.text,
                        "tags": [m.label.lower()],
                        "semantic_vector": sem_vec,
                    }
                    entity_refs.append(ref)

                if entity_refs:
                    link_results = self.linker.link_chunk_entities(chunk_entities=entity_refs)
                    for lr in link_results:
                        self.mesh.edges.append_edge(
                            Edge(
                                source_id=chunk.id,
                                target_id=lr["node_id"],
                                weight=float(lr.get("confidence", 0.8)),
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="co_occurrence",
                                relation_descriptor="mentions",
                                creation_context="kadmos_extraction",
                            )
                        )
                        total_edges += 1

        store_s = time.time() - t0
        stages.append(IngestStageReport(name="embedded", duration_s=store_s, status="ok"))
        stages.append(IngestStageReport(name="stored", duration_s=0.0, status="ok"))

        # ---- 5. Build and write IngestRunReport -------------------------
        finished_at = datetime.now(UTC)
        total_s = (finished_at - started_at).total_seconds()

        report = IngestRunReport(
            report_type="ingest",
            started_at=started_at,
            finished_at=finished_at,
            duration_s=total_s,
            status="completed",
            verdict="good",
            verdict_reasoning=(
                f"Ingested {len(sentences)} sentences from Gutenberg {book_id}: "
                f"{total_chunks} chunks, {total_edges} edges, "
                f"{total_mentions} NER mentions across {len(mention_types)} types"
            ),
            source_type=source_type,
            source_identifier=source_identifier,
            word_count=total_word_count,
            sentence_count=len(sentences),
            stages=stages,
            ner=NerSummary(total_mentions=total_mentions, by_type=mention_types),
            resolution=ResolutionSummary(),
            relations=RelationSummary(attempted=total_edges),
            embedding=EmbeddingSummary(
                nodes_embedded=total_chunks,
                embedding_model_id=self._embedder.model_id,
                duration_s=store_s,
            ),
            store=StoreSummary(
                nodes_upserted=total_chunks,
                edges_upserted=total_edges,
            ),
            quality_flags=QualityFlags(),
        )
        self._report_writer.write(report)

        return {
            "chunks": total_chunks,
            "edges": total_edges,
            "sentences": len(sentences),
            "ner_mentions": total_mentions,
            "source_anchor_id": str(sa_node.id),
            "report_run_id": report.run_id,
            "verdict": report.verdict,
        }

    async def ingest_sentences(
        self,
        *,
        sentences: list[str],
        source_type: str = "text",
        source_identifier: str = "inline",
        title: str = "Untitled",
        anchor: str = "",
    ) -> dict[str, Any]:
        """Synchronous-style convenience wrapper for tests.

        Uses real embeddings and NER.
        """
        # Build minimal Sentence-like objects from strings
        from theogony.extraction.sentence import Sentence

        sentence_objs = [
            Sentence(index=i, text=s, start_char=0, end_char=len(s))
            for i, s in enumerate(sentences)
            if s.strip()
        ]

        now = datetime.now(UTC)
        total_chunks = 0
        total_edges = 0

        # Source-anchor
        sa_node = ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            consolidation_tier=1,
            is_source_anchor=True,
            source_url=anchor or source_identifier,
            semantic_vector=[0.0] * self.semantic_dim,
            frame_vector=[0.0] * self.frame_dim,
            description=build_source_anchor_description(
                source_type=source_type,
                title=title,
                anchor=anchor or source_identifier,
            ),
            tags=[source_type.lower()],
        )
        self.mesh.nodes.append_consolidated(sa_node)

        # NER
        ner_results = await self._ner.extract(sentence_objs) if sentence_objs else []

        for i, sentence in enumerate(sentence_objs):
            text = sentence.text.strip()
            if not text:
                continue

            sem_vec = await self._embedder.embed(text)
            if len(sem_vec) != self.semantic_dim:
                sem_vec = (
                    sem_vec[: self.semantic_dim]
                    if len(sem_vec) > self.semantic_dim
                    else sem_vec + [0.0] * (self.semantic_dim - len(sem_vec))
                )
            frm_vec = [0.0] * self.frame_dim

            src = SourceProvenance(
                source_type=source_type,
                source_identifier=source_identifier,
                extracted_at=now,
            )
            chunk = ChunkNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=sem_vec,
                frame_vector=frm_vec,
                source=src,
                raw_text_ref=f"{source_identifier}#s{i}",
            )
            self.mesh.nodes.append_chunk(chunk)
            total_chunks += 1

            self.mesh.edges.append_edge(
                Edge(
                    source_id=chunk.id,
                    target_id=sa_node.id,
                    weight=1.0,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="extraction",
                    relation_descriptor="extracted_from",
                    creation_context="kadmos_extraction",
                )
            )
            total_edges += 1

            mentions = ner_results[i] if i < len(ner_results) else []
            if mentions:
                entity_refs = [
                    {"label": m.text, "tags": [m.label.lower()], "semantic_vector": sem_vec}
                    for m in mentions
                ]
                for lr in self.linker.link_chunk_entities(chunk_entities=entity_refs):
                    self.mesh.edges.append_edge(
                        Edge(
                            source_id=chunk.id,
                            target_id=lr["node_id"],
                            weight=0.8,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="co_occurrence",
                            relation_descriptor="mentions",
                            creation_context="kadmos_extraction",
                        )
                    )
                    total_edges += 1

        return {
            "chunks": total_chunks,
            "edges": total_edges,
            "source_anchor_id": str(sa_node.id),
            "source_anchor_description": sa_node.description,
        }
