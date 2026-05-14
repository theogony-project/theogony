"""Paragraph-level LLM reading pipeline — MESH-native Kadmos v2 integration."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger
from theogony.mesh.ingestion.concept_resolver import ConceptResolver
from theogony.mesh.ingestion.reading_schemas import ParagraphReadingOutput
from theogony.mesh.ingestion.source_anchor import build_source_anchor_description
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge, SourceProvenance

log = get_logger("mesh.ingestion")

SYSTEM_PROMPT = """You are a careful reader.  Read the paragraph below and extract:

1. **concepts** — every distinct entity, person, place, date, idea, or object
   that the paragraph talks about.  Each concept needs a short label, an
   entity_type hint, discriminating tags, and a one-sentence description.

2. **relations** — how the concepts relate to each other.  One relation per
   directed edge, with a short verb/preposition as `relation_descriptor`
   (e.g. "discovered", "born_in", "practiced_at", "causes", "located_in",
   "succeeded", "wrote", "studied_at").  Every relation must reference exactly
   two concept labels from the `concepts` array.

3. **synthesis** — IF the paragraph expresses a coherent higher-level idea
   that unifies several concepts, summarise it as one synthesis with a label,
   description, and list of basis concept labels.  If the paragraph is purely
   a list or disconnected facts, set synthesis to null.

Output ONLY valid JSON matching the schema.  Do not add commentary."""


class MeshParagraphReader:
    """LLM-based paragraph reader that writes directly into the MESH.

    Reads a book paragraph by paragraph.  For each paragraph:
    1. LLM extracts concepts, relations, optional synthesis.
    2. ConceptResolver deduplicates by label (fuzzy token overlap).
    3. Writes ConsolidatedNodes + Edges + ChunkNode into the mesh.
    """

    def __init__(
        self,
        mesh: MeshRuntime,
        llm: LLMProvider,
        *,
        semantic_dim: int | None = None,
        frame_dim: int | None = None,
        max_paragraphs: int = 0,
    ) -> None:
        self.mesh = mesh
        self.llm = llm
        self.max_paragraphs = max_paragraphs
        self.semantic_dim = mesh.semantic_dim if semantic_dim is None else semantic_dim
        self.frame_dim = mesh.frame_dim if frame_dim is None else frame_dim
        self.resolver = ConceptResolver(
            mesh.nodes,
            semantic_dim=self.semantic_dim,
            frame_dim=self.frame_dim,
        )

    async def read_book(self, book_id: str) -> dict[str, Any]:
        """Fetch a Gutenberg book and read paragraphs with the LLM."""
        import httpx

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
                or next((v for k, v in formats.items() if "text/plain" in k), None)
            )
            if not text_url:
                raise ValueError(f"No plain-text format for book {book_id}")
            content_resp = await client.get(str(text_url), timeout=90)
            content_resp.raise_for_status()
            raw_text = content_resp.text

        return await self.read_text(
            text=raw_text,
            source_type="gutenberg",
            source_identifier=f"gutenberg_{book_id}",
            title=book_title,
            anchor=f"https://www.gutenberg.org/ebooks/{book_id}",
        )

    async def read_text(
        self,
        *,
        text: str,
        source_type: str = "text",
        source_identifier: str = "inline",
        title: str = "Untitled",
        anchor: str = "",
    ) -> dict[str, Any]:
        """Read a text paragraph by paragraph and write into the MESH."""
        started_at = time.monotonic()
        now = datetime.now(UTC)

        # 1. Source-anchor entity
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

        # 2. Split into paragraphs
        paragraphs = _split_paragraphs(text)
        if self.max_paragraphs > 0:
            paragraphs = paragraphs[: self.max_paragraphs]

        total_concepts = 0
        total_relations = 0
        total_syntheses = 0
        total_llm_calls = 0
        llm_cost_eur = 0.0

        # 3. Read each paragraph
        for i, para_text in enumerate(paragraphs):
            para_text = para_text.strip()
            if len(para_text) < 10:
                continue

            log.info(
                "reading paragraph %d/%d (%d chars)",
                i + 1,
                len(paragraphs),
                len(para_text),
            )

            output, cost = await self._read_paragraph(para_text)
            total_llm_calls += 1
            llm_cost_eur += cost

            # Resolve concepts (dedup by label)
            resolved = self.resolver.resolve_bulk([c.model_dump() for c in output.concepts])

            # Create ChunkNode for this paragraph
            src = SourceProvenance(
                source_type=source_type,
                source_identifier=source_identifier,
                extracted_at=now,
            )
            chunk = ChunkNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=[0.0] * self.semantic_dim,
                frame_vector=[0.0] * self.frame_dim,
                source=src,
                raw_text_ref=f"{source_identifier}#p{i}",
            )
            self.mesh.nodes.append_chunk(chunk)

            # Edge: chunk -> source-anchor
            self.mesh.edges.append_edge(
                Edge(
                    source_id=chunk.id,
                    target_id=sa_node.id,
                    weight=1.0,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="extraction",
                    relation_descriptor="extracted_from",
                    creation_context="paragraph_reader",
                )
            )

            # Edge: chunk -> each resolved concept
            for c in resolved:
                cid_str: object = c["id"]
                self.mesh.edges.append_edge(
                    Edge(
                        source_id=chunk.id,
                        target_id=cid_str,  # type: ignore[arg-type]
                        weight=0.9,
                        born_at=now,
                        last_fired_at=now,
                        relation_kind="co_occurrence",
                        relation_descriptor="mentions",
                        creation_context="paragraph_reader",
                    )
                )

            total_concepts += len(resolved)

            # Create edges for relations
            resolved_by_label: dict[str, str] = {c["label"]: c["id"] for c in resolved}
            for rel in output.relations:
                src_id_str = resolved_by_label.get(rel.source)
                tgt_id_str = resolved_by_label.get(rel.target)
                if src_id_str is None or tgt_id_str is None:
                    log.warning(
                        "relation %s->%s references unknown labels",
                        rel.source,
                        rel.target,
                    )
                    continue
                s_val: object = src_id_str
                t_val: object = tgt_id_str
                self.mesh.edges.append_edge(
                    Edge(
                        source_id=s_val,  # type: ignore[arg-type]
                        target_id=t_val,  # type: ignore[arg-type]
                        weight=1.0,
                        born_at=now,
                        last_fired_at=now,
                        relation_kind="semantic",
                        relation_descriptor=rel.relation_descriptor,
                        description=rel.rationale,
                        creation_context="paragraph_reader",
                    )
                )
                total_relations += 1

            # Create synthesis node if present
            if output.synthesis is not None:
                syn = output.synthesis
                syn_node = ConsolidatedNode(
                    id=ULID(),
                    born_at=now,
                    last_fired_at=now,
                    consolidation_tier=2,
                    semantic_vector=[0.0] * self.semantic_dim,
                    frame_vector=[0.0] * self.frame_dim,
                    description=syn.description,
                    tags=[source_type.lower(), "synthesis"],
                )
                self.mesh.nodes.append_consolidated(syn_node)
                self.mesh.edges.append_edge(
                    Edge(
                        source_id=chunk.id,
                        target_id=syn_node.id,
                        weight=0.8,
                        born_at=now,
                        last_fired_at=now,
                        relation_kind="hierarchy",
                        relation_descriptor="synthesises",
                        creation_context="paragraph_reader",
                    )
                )
                basis_ids = [
                    resolved_by_label.get(bl)
                    for bl in syn.basis_concepts
                    if bl in resolved_by_label
                ]
                for bid in basis_ids:
                    if bid:
                        b_val: object = bid
                        self.mesh.edges.append_edge(
                            Edge(
                                source_id=syn_node.id,
                                target_id=b_val,  # type: ignore[arg-type]
                                weight=1.0,
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="hierarchy",
                                relation_descriptor="abstracts_over",
                                creation_context="paragraph_reader",
                            )
                        )
                total_syntheses += 1

        elapsed = time.monotonic() - started_at
        return {
            "paragraphs": len(paragraphs),
            "concepts": total_concepts,
            "relations": total_relations,
            "syntheses": total_syntheses,
            "llm_calls": total_llm_calls,
            "llm_cost_eur": round(llm_cost_eur, 6),
            "elapsed_s": round(elapsed, 1),
            "source_anchor_id": str(sa_node.id),
        }

    async def _read_paragraph(self, text: str) -> tuple[ParagraphReadingOutput, float]:
        """Call the LLM to extract concepts + relations + synthesis."""
        user_prompt = f"PARAGRAPH:\n{text}\n\nExtract the concepts, relations, and synthesis."
        try:
            result = await self.llm.complete(
                prompt=user_prompt,
                system=SYSTEM_PROMPT,
                json_schema=ParagraphReadingOutput.model_json_schema(),
                temperature=0.1,
                timeout_s=45,
            )
            output = ParagraphReadingOutput.model_validate_json(result.text)
            in_tokens = len(user_prompt.split()) + len(SYSTEM_PROMPT.split())
            out_tokens = len(result.text.split())
            cost = (in_tokens * 0.15 + out_tokens * 0.60) / 1_000_000
            return output, cost
        except Exception as exc:
            log.warning("LLM paragraph reading failed: %s", exc)
            return ParagraphReadingOutput(), 0.0


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
