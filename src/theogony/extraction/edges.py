"""
Edge materialisation: convert :class:`ExtractedRelation` DTOs into
:class:`KnowledgeEdge` records using the resolver's ResolvedMention map.

The :class:`~theogony.extraction.relations.RelationExtractor` produces
LLM-extracted relations as DTOs that carry surface forms (subject_text,
object_text). The :class:`~theogony.extraction.resolve.EntityResolver`
produces :class:`~theogony.extraction.resolve.ResolvedMention` records
that carry the minted :class:`~theogony.core.model.KnowledgeNode` IDs.
This module bridges the two: subject/object surface forms are resolved
to node IDs, evidence_span is preserved verbatim, and the resulting
:class:`KnowledgeEdge` carries a sentence-scoped :class:`SourceRef`
so the Hover-Lupe can trace an edge back to the exact sentence that
justified it.

Three drop conditions are recorded for IngestRunReport (Plan §2.11.4):

- ``dropped_subject_unresolved`` — the LLM extracted a relation whose
  subject does not match any resolver-minted node. Common when NER
  caught a fragment the resolver failed (or vice versa); the edge
  cannot be created without both endpoints, so it is dropped.
- ``dropped_object_unresolved`` — same, for object.
- ``dropped_self_loop`` — Plan §2.11.4 lists "no edges with
  source_id == target_id" as an ingest-verdict criterion. We drop
  self-loops at materialisation time so they never reach the store.

OTHER-bucket relations (Plan §3.3) are kept; the IngestionPipeline
flags them downstream for human review.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.logging import get_logger
from theogony.core.model import KnowledgeEdge, SourceRef
from theogony.extraction.alias_matcher import fully_normalise
from theogony.extraction.relations import ExtractedRelation
from theogony.extraction.resolve import ResolvedMention
from theogony.extraction.sentence import Sentence

log = get_logger("extraction.edges")


class EdgeMaterialisation(BaseModel):
    """Result of materialising relations from one or more sentences.

    Returned by :func:`materialise_edges` so the IngestionPipeline can
    aggregate edge counts and drop reasons into the IngestRunReport
    without re-walking the relation list.
    """

    model_config = ConfigDict(extra="forbid")

    edges: list[KnowledgeEdge] = Field(default_factory=list)
    dropped_subject_unresolved: int = Field(default=0, ge=0)
    dropped_object_unresolved: int = Field(default=0, ge=0)
    dropped_self_loop: int = Field(default=0, ge=0)

    @property
    def dropped_total(self) -> int:
        return (
            self.dropped_subject_unresolved
            + self.dropped_object_unresolved
            + self.dropped_self_loop
        )


def build_resolved_lookup(
    resolved_mentions: Sequence[ResolvedMention],
) -> dict[str, str]:
    """Build a {fully_normalise(surface) → node_id} lookup.

    Iterates every Mention in every ResolvedMention so all surface
    variants of a deduplicated entity ("TIBET", "Tibet", "tibet")
    map to the same node ID. When two ResolvedMentions disagree on
    the node for the same normalised surface (e.g. "Apple" PERSON
    vs ORG), the last one wins and a warning is logged — this is a
    known limitation; the relation extractor cannot disambiguate
    cross-label collisions without seeing NER labels too.
    """
    out: dict[str, str] = {}
    for rm in resolved_mentions:
        node_id = rm.node.id
        for mention in rm.mentions:
            key = fully_normalise(mention.text)
            existing = out.get(key)
            if existing is not None and existing != node_id:
                log.warning(
                    "resolved-mention surface %r maps to two distinct node IDs "
                    "(%s vs %s); keeping last — relation extractor cannot "
                    "disambiguate this without NER labels at edge time",
                    mention.text,
                    existing,
                    node_id,
                )
            out[key] = node_id
    return out


def materialise_edges(
    *,
    relations: Sequence[ExtractedRelation],
    resolved_lookup: dict[str, str],
    book_source_ref: SourceRef,
    central_sentence: Sentence | None = None,
) -> EdgeMaterialisation:
    """Convert LLM-extracted relations into store-ready KnowledgeEdges.

    ``resolved_lookup`` is the global text → node_id map built once
    per ingest by :func:`build_resolved_lookup`. ``central_sentence``
    is optional but recommended: when provided, the resulting edges
    carry a sentence-scoped :class:`SourceRef` (location ``sentence:N``,
    snippet truncated at 200 chars) so the Hover-Lupe can show the
    exact sentence that justified the edge.

    Each dropped relation is logged at WARNING and counted in the
    returned :class:`EdgeMaterialisation`. The counts feed
    IngestRunReport's ``relations.dropped_*`` fields and contribute
    to the verdict heuristics (Plan §2.11.2).
    """
    if not relations:
        return EdgeMaterialisation()

    edges: list[KnowledgeEdge] = []
    dropped_s = 0
    dropped_o = 0
    dropped_loop = 0

    edge_source_ref = _edge_source_ref(book_source_ref, central_sentence)

    for rel in relations:
        s_key = fully_normalise(rel.subject_text)
        o_key = fully_normalise(rel.object_text)
        s_id = resolved_lookup.get(s_key)
        o_id = resolved_lookup.get(o_key)

        if s_id is None:
            log.debug(
                "drop relation: subject %r not resolved; type=%s",
                rel.subject_text,
                rel.relation_type,
            )
            dropped_s += 1
            continue
        if o_id is None:
            log.debug(
                "drop relation: object %r not resolved; type=%s",
                rel.object_text,
                rel.relation_type,
            )
            dropped_o += 1
            continue
        if s_id == o_id:
            # Plan §2.11.4: "no edges with source_id == target_id" is a
            # verdict criterion. Drop self-loops here so they never
            # reach the store.
            log.debug(
                "drop self-loop relation: %r %s %r",
                rel.subject_text,
                rel.relation_type,
                rel.object_text,
            )
            dropped_loop += 1
            continue

        edge = KnowledgeEdge(
            source_id=s_id,
            target_id=o_id,
            relation_type=rel.relation_type,
            confidence=rel.confidence,
            evidence_span=rel.evidence_span,
            source_ref=edge_source_ref,
            properties={
                "extracted_subject_text": rel.subject_text,
                "extracted_object_text": rel.object_text,
                "extraction_reasoning": rel.reasoning,
                "is_other_bucket": rel.is_other,
            },
        )
        edges.append(edge)

    return EdgeMaterialisation(
        edges=edges,
        dropped_subject_unresolved=dropped_s,
        dropped_object_unresolved=dropped_o,
        dropped_self_loop=dropped_loop,
    )


def _edge_source_ref(
    book_source_ref: SourceRef,
    central_sentence: Sentence | None,
) -> SourceRef | None:
    """Build a sentence-scoped SourceRef for an extracted edge.

    Returns ``None`` when no central_sentence is available (the edge
    is not store-rejected — Plan §9.5 makes source_ref optional —
    but downstream tooling loses the per-sentence trace).
    """
    if central_sentence is None:
        return None
    snippet = central_sentence.text[:200]
    return SourceRef(
        source_type=book_source_ref.source_type,
        url=book_source_ref.url,
        identifier=book_source_ref.identifier,
        location=f"sentence:{central_sentence.index}",
        snippet=snippet,
        language=book_source_ref.language,
    )


__all__ = [
    "EdgeMaterialisation",
    "build_resolved_lookup",
    "materialise_edges",
]
