"""Eager-linking pass — three-signal hierarchy for identity matching.

Per MESH_SUBSTRATE.md §"Why two tiers — and how identity actually gets committed":

- Signal 1: Q-ID match (strongest)
- Signal 2: description + structural context (nearly as strong)
- Signal 3: tag overlap + structural context (weaker, fast disambiguation)
- Path 2: entity-candidate creation when no signal fires

Scope cap S2: no label-text deduplication (that is S5). Identical mention
labels in different chunks each produce a candidate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from theogony.mesh.schemas import ConsolidatedNode, QIDTag
from theogony.mesh.storage.nodes import MeshNodeStore


class EagerLinker:
    """Three-signal eager-linking pass over incoming chunk entities."""

    def __init__(
        self,
        node_store: MeshNodeStore,
        *,
        frame_dim: int = 64,
        semantic_dim: int = 384,
    ) -> None:
        self._store = node_store
        self._frame_dim = frame_dim
        self._semantic_dim = semantic_dim

    def link_chunk_entities(
        self,
        *,
        chunk_entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """For each entity reference return linked Tier-1 id or create one.

        Each entry in *chunk_entities* must have:
            - ``qids``: list of QIDTag-like dicts (may be empty)
            - ``label``: str
            - ``tags``: list[str]
            - ``semantic_vector``: list[float]

        Returns list with same cardinality. Each result has:
            - ``node_id``: str
            - ``is_new``: bool
            - ``signal``: "qid" | "description" | "tag" | "emergent"
        """
        now = datetime.now(UTC)
        results: list[dict[str, Any]] = []

        for ref in chunk_entities:
            qids_raw = ref.get("qids", [])
            label = str(ref.get("label", ""))
            tags = list(ref.get("tags", []))
            sem_v = ref.get("semantic_vector", [0.0] * self._semantic_dim)

            matched_id: str | None = None
            matched_signal: str | None = None

            # Signal 1: Q-ID match
            for qr in qids_raw:
                qid = qr.get("qid", "") if isinstance(qr, dict) else str(qr)
                if not qid:
                    continue
                existing = self._find_by_qid(qid)
                if existing is not None:
                    matched_id = existing
                    matched_signal = "qid"
                    break

            if matched_id is not None:
                results.append({"node_id": matched_id, "is_new": False, "signal": matched_signal})
                continue

            # Signal 2: description-based (needs description_vector — not populated in S2)
            desc_v = ref.get("description_vector")
            if desc_v is not None and any(x != 0.0 for x in desc_v):
                candidate = self._find_by_description(desc_v, threshold=0.75)
                if candidate is not None:
                    matched_id = candidate
                    matched_signal = "description"

            if matched_id is not None:
                results.append({"node_id": matched_id, "is_new": False, "signal": matched_signal})
                continue

            # Signal 3: tag overlap
            if tags:
                candidate = self._find_by_tags(tags)
                if candidate is not None:
                    matched_id = candidate
                    matched_signal = "tag"

            if matched_id is not None:
                results.append({"node_id": matched_id, "is_new": False, "signal": matched_signal})
                continue

            # Path 2: emergent candidate
            candidate_node = ConsolidatedNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=sem_v,
                frame_vector=[0.0] * self._frame_dim,
                description=label if label else None,
                tags=tags,
                is_candidate=True,
                qids=[QIDTag.model_validate(q) for q in qids_raw] if qids_raw else [],
            )
            self._store.append_consolidated(candidate_node)
            results.append(
                {"node_id": str(candidate_node.id), "is_new": True, "signal": "emergent"}
            )

        return results

    def _find_by_qid(self, qid: str) -> str | None:
        """Scan consolidated_nodes for a node whose payload contains this QID."""
        try:
            rows = self._store.consolidated_table.search() \
                .limit(10_000) \
                .to_arrow().to_pylist()
            for r in rows:
                payload = ConsolidatedNode.model_validate_json(r["payload_json"])
                for q in payload.qids:
                    if q.qid == qid:
                        return str(payload.id)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _find_by_description(self, vector: list[float], threshold: float = 0.75) -> str | None:
        """Find a consolidated node whose description_vector is close to query."""
        try:
            rows = self._store.consolidated_table.search() \
                .limit(1_000) \
                .to_arrow().to_pylist()
            best_id: str | None = None
            best_score = 0.0
            for r in rows:
                payload = ConsolidatedNode.model_validate_json(r["payload_json"])
                if payload.description_vector is None:
                    continue
                score = _cosine_similarity(vector, payload.description_vector)
                if score > best_score:
                    best_score = score
                    best_id = str(payload.id)
            if best_id is not None and best_score >= threshold:
                return best_id
        except Exception:  # noqa: BLE001
            pass
        return None

    def _find_by_tags(self, tags: list[str]) -> str | None:
        """Find a consolidated node with the most overlapping tags."""
        try:
            rows = self._store.consolidated_table.search() \
                .limit(1_000) \
                .to_arrow().to_pylist()
            best_id: str | None = None
            best_overlap = 0
            tag_set = set(tags)
            for r in rows:
                payload = ConsolidatedNode.model_validate_json(r["payload_json"])
                overlap = len(tag_set & set(payload.tags))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_id = str(payload.id)
            if best_id is not None and best_overlap >= 2:
                return best_id
        except Exception:  # noqa: BLE001
            pass
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
