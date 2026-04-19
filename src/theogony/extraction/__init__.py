"""Extraction pipeline — turns raw text into knowledge atoms.

Gen 1 stages (Plan §2.5), in pipeline order:

    RawContent → TextCleaner → Sentencizer → NerExtractor →
        EntityResolver → RelationExtractor → Embedder → KnowledgeStore

Etappe E1 (this module so far): TextCleaner, Sentencizer, NerExtractor.
The Embedder lives here too (Plan §2.3) — it shares the lifecycle of
the extraction pipeline at runtime.
"""

from theogony.extraction.clean import CleanedContent, TextCleaner
from theogony.extraction.embedding import (
    EmbeddingProvider,
    LocalSentenceTransformerEmbedder,
)

__all__ = [
    "CleanedContent",
    "EmbeddingProvider",
    "LocalSentenceTransformerEmbedder",
    "TextCleaner",
]
