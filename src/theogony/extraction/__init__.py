"""Extraction pipeline — turns raw text into knowledge atoms.

Gen 1 stages (Plan §2.5), in pipeline order:

    RawContent → TextCleaner → Sentencizer → NerExtractor →
        EntityResolver → RelationExtractor → Embedder → KnowledgeStore

E1: TextCleaner, Sentencizer, NerExtractor.
E2: EntityResolver Stages 1-3 (deterministic Wikidata alignment) plus
    its supporting modules WikidataClient, AliasMatcher, wikidata_types.
E3: BookContextExtractor + Stage 4 LLM disambiguation + Tier 2/1
    minting (extends EntityResolver; opt-in via constructor llm arg).
    Stage 5 (Detective Mode) and RelationExtractor remain deferred to E4.

The Embedder lives here too (Plan §2.3) — it shares the lifecycle of
the extraction pipeline at runtime.
"""

from theogony.extraction.alias_matcher import (
    AliasMatchStrength,
    best_match,
    fully_normalise,
    is_match,
)
from theogony.extraction.book_context import (
    DEFAULT_MAX_OPENING_CHARS,
    BookContext,
    BookContextExtractor,
)
from theogony.extraction.clean import CleanedContent, TextCleaner
from theogony.extraction.embedding import (
    EmbeddingProvider,
    LocalSentenceTransformerEmbedder,
)
from theogony.extraction.ner import DEFAULT_NER_MODEL, Mention, NerExtractor
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
    "TIER_0_CONFIDENCE",
    "TIER_1_CONFIDENCE",
    "TIER_2_CONFIDENCE",
    "TIER_3_CONFIDENCE",
    "TIER_4_CONFIDENCE",
    "AliasMatchStrength",
    "BioFacts",
    "BookContext",
    "BookContextExtractor",
    "CleanedContent",
    "EmbeddingProvider",
    "EntityResolver",
    "LocalSentenceTransformerEmbedder",
    "Mention",
    "NerExtractor",
    "ResolvedMention",
    "Sentence",
    "Sentencizer",
    "TextCleaner",
    "WikidataCandidate",
    "WikidataClient",
    "acceptable_wikidata_types",
    "best_match",
    "fully_normalise",
    "is_match",
    "is_resolvable",
    "node_type_for_ner_label",
]
