"""KnowledgeStore implementations.

Gen 1 ships :class:`InMemoryKnowledgeStore` (pure-Python, default for
tests and dev runs) and :class:`Neo4jKnowledgeStore` (production
backend, Plan §3.1a + E7 brief). Both implement the
:class:`~theogony.core.store.KnowledgeStore` protocol and pass the
same parametrised contract suite (``tests/test_store_contract.py``).

The Neo4j backend lazy-imports the ``neo4j`` driver only when the
class is constructed, so importing this module on a system without
the driver still works (helpful for the Stub-LLM-only test path).
"""

from theogony.stores.memory import InMemoryKnowledgeStore
from theogony.stores.neo4j_store import Neo4jKnowledgeStore

__all__ = ["InMemoryKnowledgeStore", "Neo4jKnowledgeStore"]
