"""Extraction pipeline — turns raw text into knowledge atoms.

Gen 1 stages (Plan §2.5), in pipeline order:

    RawContent → TextCleaner → Sentencizer → NerExtractor →
        BookContextExtractor (optional) →
        EntityResolver → RelationExtractor →
        edge materialisation → Embedder → KnowledgeStore

E1: TextCleaner, Sentencizer, NerExtractor.
E2: EntityResolver Stages 1-3 + supporting modules.
E3: BookContextExtractor + Stage 4 LLM disambiguation + Tier 2/1.
E4: RelationExtractor (fixed vocabulary, PID-2 safeguards).
E5: ExtractionAuditLog (SQLite) + edge materialisation +
    IngestionPipeline orchestrator. Stage 5 (WikidataDetective) and
    the Embedder are deferred to later etappes.

The Embedder lives here too (Plan §2.3) — it shares the lifecycle of
the extraction pipeline at runtime.
"""

from theogony.extraction.alias_matcher import (
    AliasMatchStrength,
    best_match,
    fully_normalise,
    is_match,
)
from theogony.extraction.audit import AuditRecord, ExtractionAuditLog
from theogony.extraction.book_context import (
    DEFAULT_MAX_OPENING_CHARS,
    BookContext,
    BookContextExtractor,
)
from theogony.extraction.clean import CleanedContent, TextCleaner
from theogony.extraction.edges import (
    EdgeMaterialisation,
    build_resolved_lookup,
    materialise_edges,
)
from theogony.extraction.embedding import (
    EmbeddingProvider,
    LocalSentenceTransformerEmbedder,
)
from theogony.extraction.ner import DEFAULT_NER_MODEL, Mention, NerExtractor
from theogony.extraction.pipeline import IngestionPipeline, IngestionResult
from theogony.extraction.relation_types import (
    RELATION_TYPE_TO_WIKIDATA,
    RELATION_TYPES,
    RELATION_TYPES_LIST,
    RelationType,
    is_known_relation_type,
    normalise_relation_type,
)
from theogony.extraction.relations import ExtractedRelation, RelationExtractor
from theogony.extraction.resolve import (
    DEFAULT_LANGUAGES,
    DEFAULT_WBSEARCH_LIMIT,
    TIER_0_CONFIDENCE,
    TIER_1_CONFIDENCE,
    TIER_2_CONFIDENCE,
    TIER_3_CONFIDENCE,
    TIER_4_CONFIDENCE,
    EntityResolver,
    ResolvedMention,
)
from theogony.extraction.sentence import Sentence, Sentencizer
from theogony.extraction.wikidata_client import BioFacts, WikidataCandidate, WikidataClient
from theogony.extraction.wikidata_types import (
    acceptable_wikidata_types,
    is_resolvable,
    node_type_for_ner_label,
)

__all__ = [
    "DEFAULT_LANGUAGES",
    "DEFAULT_MAX_OPENING_CHARS",
    "DEFAULT_NER_MODEL",
    "DEFAULT_WBSEARCH_LIMIT",
    "RELATION_TYPE_TO_WIKIDATA",
    "RELATION_TYPES",
    "RELATION_TYPES_LIST",
    "TIER_0_CONFIDENCE",
    "TIER_1_CONFIDENCE",
    "TIER_2_CONFIDENCE",
    "TIER_3_CONFIDENCE",
    "TIER_4_CONFIDENCE",
    "AliasMatchStrength",
    "AuditRecord",
    "BioFacts",
    "BookContext",
    "BookContextExtractor",
    "CleanedContent",
    "EdgeMaterialisation",
    "EmbeddingProvider",
    "EntityResolver",
    "ExtractedRelation",
    "ExtractionAuditLog",
    "IngestionPipeline",
    "IngestionResult",
    "LocalSentenceTransformerEmbedder",
    "Mention",
    "NerExtractor",
    "RelationExtractor",
    "RelationType",
    "ResolvedMention",
    "Sentence",
    "Sentencizer",
    "TextCleaner",
    "WikidataCandidate",
    "WikidataClient",
    "acceptable_wikidata_types",
    "best_match",
    "build_resolved_lookup",
    "fully_normalise",
    "is_known_relation_type",
    "is_match",
    "is_resolvable",
    "materialise_edges",
    "node_type_for_ner_label",
    "normalise_relation_type",
]
