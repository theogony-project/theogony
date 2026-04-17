"""KnowledgeStore implementations.

Gen 1 ships :class:`InMemoryKnowledgeStore` (pure-Python, used by
tests and dev runs). :class:`Neo4jKnowledgeStore` arrives in Week 3.
Both implement the :class:`~theogony.core.store.KnowledgeStore`
protocol and pass the same parametrised contract suite.
"""

from theogony.stores.memory import InMemoryKnowledgeStore

__all__ = ["InMemoryKnowledgeStore"]
