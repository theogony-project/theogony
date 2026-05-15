"""Bootstrap cache for eager-linking over existing consolidated nodes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from theogony.mesh.schemas import ConsolidatedNode, QIDTag
from theogony.mesh.storage.nodes import MeshNodeStore

_STOP_WORDS = frozenset(
    {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are", "was", "were"}
)


def _normalize(label: str) -> str:
    raw = label.lower().strip()
    raw = re.sub(r"'s\b", "", raw)
    raw = re.sub(r"[^a-z0-9\s]", "", raw)
    return raw.strip()


def _tokens(label: str) -> set[str]:
    return {t for t in _normalize(label).split() if t not in _STOP_WORDS and len(t) > 1}


@dataclass
class CachedConcept:
    node: ConsolidatedNode
    labels: set[str] = field(default_factory=set)
    qids: set[str] = field(default_factory=set)


class ConceptResolver:
    """In-memory cache of consolidated-node aliases and Q-IDs for one ingest run."""

    def __init__(self, node_store: MeshNodeStore) -> None:
        self._store = node_store
        self._nodes_by_id: dict[str, CachedConcept] = {}
        self._label_to_id: dict[str, str] = {}
        self._qid_to_id: dict[str, str] = {}
        self._bootstrap()

    def _bootstrap(self) -> None:
        try:
            for node in self._store.load_all_consolidated():
                self.remember(node)
        except Exception:  # noqa: BLE001
            pass

    def remember(
        self,
        node: ConsolidatedNode,
        *,
        aliases: list[str] | None = None,
        qids: list[QIDTag] | None = None,
    ) -> None:
        node_id = str(node.id)
        cached = self._nodes_by_id.get(node_id)
        if cached is None:
            cached = CachedConcept(node=node)
            self._nodes_by_id[node_id] = cached
        else:
            cached.node = node

        alias_values = list(aliases or [])
        if node.description:
            alias_values.append(node.description)
        alias_values.extend(node.tags)

        for alias in alias_values:
            norm = _normalize(alias)
            if not norm:
                continue
            cached.labels.add(norm)
            self._label_to_id.setdefault(norm, node_id)

        qid_values = list(qids or []) + list(node.qids)
        for qid_tag in qid_values:
            cached.qids.add(qid_tag.qid)
            self._qid_to_id.setdefault(qid_tag.qid, node_id)

    def get_by_id(self, node_id: str) -> ConsolidatedNode | None:
        cached = self._nodes_by_id.get(node_id)
        return cached.node if cached is not None else None

    def get_by_label(self, label: str) -> ConsolidatedNode | None:
        node_id = self._label_to_id.get(_normalize(label))
        return self.get_by_id(node_id) if node_id is not None else None

    def get_by_qid(self, qid: str) -> ConsolidatedNode | None:
        node_id = self._qid_to_id.get(qid)
        return self.get_by_id(node_id) if node_id is not None else None

    def iter_nodes(self) -> list[ConsolidatedNode]:
        return [cached.node for cached in self._nodes_by_id.values()]

    def known_labels(self, node_id: str) -> set[str]:
        cached = self._nodes_by_id.get(node_id)
        return set(cached.labels) if cached is not None else set()

    def score_token_overlap(self, label: str, node: ConsolidatedNode) -> float:
        query_tokens = _tokens(label)
        if not query_tokens:
            return 0.0
        best = 0.0
        for alias in self.known_labels(str(node.id)):
            alias_tokens = _tokens(alias)
            if not alias_tokens:
                continue
            overlap = len(query_tokens & alias_tokens) / max(len(query_tokens), len(alias_tokens))
            best = max(best, overlap)
        return best
