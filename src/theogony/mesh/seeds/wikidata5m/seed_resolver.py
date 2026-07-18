"""Memory-safe Q-ID → node-id map for the wikidata5m bulk seed path.

``ConceptResolver`` caches full ``ConsolidatedNode`` objects (including two
1024-d vectors as Python lists). At seed scale that grows to tens of GB and
OOMs the reference MacBook near 100k nodes (PHX-1030).

The seed importer only needs Q-ID identity and ULID endpoints for edges —
vectors already live in Lance. This resolver stores ``qid → node_id`` only.
"""

from __future__ import annotations

from ulid import ULID

from theogony.mesh.storage.nodes import MeshNodeStore


class SeedConceptResolver:
    """Q-ID → node_id cache without retaining node payloads or vectors."""

    def __init__(self, node_store: MeshNodeStore) -> None:
        self._store = node_store
        self._qid_to_id: dict[str, str] = {}

    def remember(self, qid: str, node_id: str | ULID) -> None:
        self._qid_to_id.setdefault(qid, str(node_id))

    def has_qid(self, qid: str) -> bool:
        return self.get_node_id(qid) is not None

    def get_node_id(self, qid: str) -> str | None:
        cached = self._qid_to_id.get(qid)
        if cached is not None:
            return cached
        node_id = self._store.get_consolidated_id_by_qid(qid)
        if node_id is None:
            return None
        self._qid_to_id[qid] = node_id
        return node_id

    def get_ulid(self, qid: str) -> ULID | None:
        node_id = self.get_node_id(qid)
        if node_id is None:
            return None
        return ULID.from_str(node_id)

    def known_qids(self) -> set[str]:
        return set(self._qid_to_id)

    def cached_count(self) -> int:
        return len(self._qid_to_id)
