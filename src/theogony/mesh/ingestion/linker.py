"""Eager-linking pass — three-signal hierarchy for identity matching.

Per MESH_SUBSTRATE.md §"Why two tiers — and how identity actually gets committed":

- Signal 1: Q-ID match (strongest)
- Signal 2: description + structural context (nearly as strong)
- Signal 3: tag overlap + structural context (weaker, fast disambiguation)
- Path 2: entity-candidate creation when no signal fires
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from theogony.mesh.schemas import ConsolidatedNode, QIDTag
from theogony.mesh.storage.nodes import MeshNodeStore


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Simple cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _default_vector(dim: int) -> list[float]:
    return [0.0] * dim


class EagerLinker:
    """Three-signal eager-linking pass over incoming chunks against existing Tier-1 nodes."""

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
        """For each entity reference in a chunk, return the linked Tier-1 node id or create one.

        Each entry in *chunk_entities* must have:
            - ``qids``: list of QIDTag-like dicts (may be empty)
            - ``label``: str (entity name / description for matching)
            - ``tags``: list of str
            - ``description_vector``: list[float] | None
            - ``semantic_vector``: list[float] (fallback when no description_vector)

        Returns a list with the same cardinality. Each result dict has:
            - ``node_id``: str (existing or freshly created Tier-1 id)
            - ``is_new``: bool
            - ``signal``: "qid" | "description" | "tag" | "emergent"
        """
        now = datetime.now(UTC)
        results: list[dict[str, Any]] = []

        for ref in chunk_entities:
            qids_raw = ref.get("qids", [])
            label = str(ref.get("label", ""))
            tags = list(ref.get("tags", []))
            desc_v = ref.get("description_vector")
            sem_v = ref.get("semantic_vector", _default_vector(self._semantic_dim))

            # Signal 1: Q-ID match
            matched_signal: str | None = None
            matched_node_id: str | None = None

            for qr in qids_raw:
                qid = qr.get("qid", "") if isinstance(qr, dict) else str(qr)
                if not qid:
                    continue
                # Scan existing consolidated nodes for a matching Q-ID.
                existing = self._find_by_qid(qid)
                if existing is not None:
                    matched_signal = "qid"
                    matched_node_id = existing
                    break

            if matched_node_id is not None:
                results.append(
                    {"node_id": matched_node_id, "is_new": False, "signal": matched_signal}
                )
                continue

            # Signal 2: description-based match
            if desc_v is not None and any(x != 0.0 for x in desc_v):
                candidate = self._find_by_description(desc_v, threshold=0.75)
                if candidate is not None:
                    matched_signal = "description"
                    matched_node_id = candidate

            if matched_node_id is not None:
                results.append(
                    {"node_id": matched_node_id, "is_new": False, "signal": matched_signal}
                )
                continue

            # Signal 3: tag overlap
            if tags:
                candidate = self._find_by_tags(tags)
                if candidate is not None:
                    matched_signal = "tag"
                    matched_node_id = candidate

            if matched_node_id is not None:
                results.append(
                    {"node_id": matched_node_id, "is_new": False, "signal": matched_signal}
                )
                continue

            # Path 2: create candidate
            from ulid import ULID

            candidate_node = ConsolidatedNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=sem_v,
                frame_vector=_default_vector(self._frame_dim),
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
        """Scan consolidated_nodes for a node whose payload contains this QID.

        Since Lance doesn't support JSON sub-field queries in the free tier,
        we load payloads for known ids (small initial corpus).  In production
        this would use a secondary index.
        """
        try:
            tbl = self._store.consolidated_table
            rows = tbl.search().limit(10_000).to_arrow().to_pylist()
            for r in rows:
                payload = ConsolidatedNode.model_validate_json(r["payload_json"])
                for q in payload.qids:
                    if q.qid == qid:
                        return str(payload.id)
        except Exception:  # noqa: BLE001 — read-only best-effort
            pass
        return None

    def _find_by_description(self, vector: list[float], threshold: float = 0.75) -> str | None:
        """Find a consolidated node whose description_vector is close to the query."""
        try:
            tbl = self._store.consolidated_table
            rows = tbl.search().limit(1_000).to_arrow().to_pylist()
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
        except Exception:  # noqa: BLE001 — read-only best-effort
            pass
        return None

    def _find_by_tags(self, tags: list[str]) -> str | None:
        """Find a consolidated node with the most overlapping tags."""
        try:
            tbl = self._store.consolidated_table
            rows = tbl.search().limit(1_000).to_arrow().to_pylist()
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
        except Exception:  # noqa: BLE001 — read-only best-effort
            pass
        return None
