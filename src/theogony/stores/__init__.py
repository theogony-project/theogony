"""KnowledgeStore implementations.

Gen 1 ships :class:`InMemoryKnowledgeStore` (pure-Python, default for
tests and dev runs). Production persistence evolves toward LanceDB /
tensor substrate per ``docs/TARGET_ARCHITECTURE.md`` — Neo4j was retired
(``docs/etappes/RETIREMENT_NEO4J_MULTIHOP.md``).
"""

from theogony.stores.memory import InMemoryKnowledgeStore

__all__ = ["InMemoryKnowledgeStore"]
