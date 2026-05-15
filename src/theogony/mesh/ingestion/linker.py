"""Three-signal eager linker for doctrine-conformant Tier-1 identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.ingestion.concept_resolver import ConceptResolver, _normalize
from theogony.mesh.schemas import ConsolidatedNode, Edge, QIDTag
from theogony.mesh.storage.edges import EdgeStore
from theogony.mesh.storage.nodes import MeshNodeStore


def _cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if a is None or b is None or not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / (na * nb))


@dataclass(frozen=True)
class LinkDecision:
    node: ConsolidatedNode
    signal: str
    is_new: bool
    score: float


class EagerLinker:
    """Q-ID, description+context, then tag+context matching."""

    def __init__(
        self,
        node_store: MeshNodeStore,
        edge_store: EdgeStore,
        *,
        semantic_dim: int,
        frame_dim: int,
        registry: ConceptResolver | None = None,
    ) -> None:
        self._store = node_store
        self._edge_store = edge_store
        self._semantic_dim = semantic_dim
        self._frame_dim = frame_dim
        self._registry = registry or ConceptResolver(node_store)
        self._adjacency: dict[str, set[str]] = {}
        self._bootstrap_adjacency()

    def _bootstrap_adjacency(self) -> None:
        for edge in self._edge_store.load_all_edges():
            self.remember_edge(edge)

    def remember_edge(self, edge: Edge) -> None:
        source_id = str(edge.source_id)
        target_id = str(edge.target_id)
        self._adjacency.setdefault(source_id, set()).add(target_id)
        self._adjacency.setdefault(target_id, set()).add(source_id)

    def _context_score(self, candidate_id: str, context_node_ids: set[str]) -> float:
        if not context_node_ids:
            return 0.0
        neighbours = self._adjacency.get(candidate_id, set())
        if not neighbours:
            return 0.0
        overlap = len(neighbours & context_node_ids)
        return overlap / max(1, len(context_node_ids))

    def _best_description_match(
        self,
        *,
        label: str,
        description_vector: list[float] | None,
        tags: list[str],
        context_node_ids: set[str],
    ) -> tuple[ConsolidatedNode | None, float]:
        best_node: ConsolidatedNode | None = None
        best_score = 0.0
        tag_set = {tag.lower().strip() for tag in tags}
        norm_label = _normalize(label)

        for candidate in self._registry.iter_nodes():
            if candidate.is_source_anchor:
                continue
            desc_score = _cosine_similarity(description_vector, candidate.description_vector)
            if desc_score <= 0.0:
                continue
            context_score = self._context_score(str(candidate.id), context_node_ids)
            tag_overlap = len(tag_set & {tag.lower().strip() for tag in candidate.tags})
            tag_score = tag_overlap / max(1, len(tag_set)) if tag_set else 0.0
            known_labels = self._registry.known_labels(str(candidate.id))
            label_score = 1.0 if norm_label in known_labels else 0.0
            score = desc_score + (0.20 * context_score) + (0.08 * tag_score) + (0.05 * label_score)
            if score > best_score:
                best_node = candidate
                best_score = score

        return best_node, best_score

    def _best_tag_match(
        self,
        *,
        label: str,
        tags: list[str],
        context_node_ids: set[str],
    ) -> tuple[ConsolidatedNode | None, float]:
        best_node: ConsolidatedNode | None = None
        best_score = 0.0
        tag_set = {tag.lower().strip() for tag in tags}

        for candidate in self._registry.iter_nodes():
            if candidate.is_source_anchor:
                continue
            candidate_tags = {tag.lower().strip() for tag in candidate.tags}
            overlap = len(tag_set & candidate_tags)
            if overlap <= 0:
                continue
            tag_score = overlap / max(len(tag_set), len(candidate_tags), 1)
            context_score = self._context_score(str(candidate.id), context_node_ids)
            token_score = self._registry.score_token_overlap(label, candidate)
            score = tag_score + (0.25 * context_score) + (0.15 * token_score)
            if score > best_score:
                best_node = candidate
                best_score = score

        return best_node, best_score

    def _create_candidate(
        self,
        *,
        label: str,
        description: str,
        tags: list[str],
        qids: list[QIDTag],
        semantic_vector: list[float],
        frame_vector: list[float],
        description_vector: list[float] | None,
    ) -> ConsolidatedNode:
        now = datetime.now(UTC)
        node = ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            consolidation_tier=1,
            is_candidate=True,
            semantic_vector=semantic_vector,
            frame_vector=frame_vector,
            description=description or label,
            description_vector=description_vector,
            tags=tags,
            qids=qids,
        )
        self._store.append_consolidated(node)
        self._registry.remember(node, aliases=[label, description], qids=qids)
        return node

    def link_reference(
        self,
        *,
        label: str,
        description: str,
        tags: list[str],
        qids: list[QIDTag],
        semantic_vector: list[float],
        frame_vector: list[float],
        description_vector: list[float] | None,
        context_node_ids: set[str] | None = None,
    ) -> LinkDecision:
        context_ids = set(context_node_ids or set())

        for qid_tag in qids:
            node = self._registry.get_by_qid(qid_tag.qid)
            if node is not None:
                self._registry.remember(node, aliases=[label, description], qids=qids)
                return LinkDecision(node=node, signal="qid", is_new=False, score=1.0)

        matched, score = self._best_description_match(
            label=label,
            description_vector=description_vector,
            tags=tags,
            context_node_ids=context_ids,
        )
        if matched is not None and score >= 0.72:
            self._registry.remember(matched, aliases=[label, description], qids=qids)
            return LinkDecision(node=matched, signal="description", is_new=False, score=score)

        matched, score = self._best_tag_match(
            label=label,
            tags=tags,
            context_node_ids=context_ids,
        )
        if matched is not None and score >= 0.55:
            self._registry.remember(matched, aliases=[label, description], qids=qids)
            return LinkDecision(node=matched, signal="tag", is_new=False, score=score)

        node = self._create_candidate(
            label=label,
            description=description,
            tags=tags,
            qids=qids,
            semantic_vector=semantic_vector,
            frame_vector=frame_vector,
            description_vector=description_vector,
        )
        return LinkDecision(node=node, signal="emergent", is_new=True, score=0.0)
