"""Entity registry — deduplicates concepts by label across paragraphs.

Per MESH_SUBSTRATE.md §"Why two tiers — and how identity actually gets committed":
the same real-world entity should map to exactly one Tier-1 node, regardless
of how many paragraphs mention it.  This module provides a case-insensitive
label → node_id mapping that holds across a single ingestion run.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from theogony.mesh.schemas import ConsolidatedNode
from theogony.mesh.storage.nodes import MeshNodeStore

_STOP_WORDS = frozenset(
    {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are", "was", "were"}
)


def _normalize(label: str) -> str:
    """Lowercase, strip possessives and punctuation."""
    raw = label.lower().strip()
    # Strip possessive 's
    raw = re.sub(r"'s\b", "", raw)
    # Remove punctuation
    raw = re.sub(r"[^a-z0-9\s]", "", raw)
    return raw.strip()


def _tokens(label: str) -> set[str]:
    """Return significant tokens for matching."""
    return {t for t in _normalize(label).split() if t not in _STOP_WORDS and len(t) > 1}


class ConceptResolver:
    """Label-based entity registry that persists new entities to the mesh.

    Usage::

        resolver = ConceptResolver(mesh.nodes, semantic_dim=384, frame_dim=64)
        node_id = resolver.resolve("Tibet", tags=["gpe"])
        # same call again → same node_id; no second node created.
    """

    def __init__(
        self,
        node_store: MeshNodeStore,
        *,
        semantic_dim: int,
        frame_dim: int,
    ) -> None:
        self._store = node_store
        self._semantic_dim = semantic_dim
        self._frame_dim = frame_dim
        # In-memory registry: normalised label → node_id
        self._registry: dict[str, str] = {}
        # Boot: scan existing consolidated nodes
        self._bootstrap()

    def _bootstrap(self) -> None:
        """Pre-populate registry from already-stored consolidated nodes."""
        try:
            rows = self._store.consolidated_table.search().limit(10_000).to_arrow().to_pylist()
            for r in rows:
                payload = ConsolidatedNode.model_validate_json(r["payload_json"])
                if payload.description:
                    key = payload.description.lower().strip()
                    if key not in self._registry:
                        self._registry[key] = str(payload.id)
                    for tag in payload.tags:
                        tag_key = tag.lower().strip()
                        if tag_key not in self._registry:
                            self._registry[tag_key] = str(payload.id)
        except Exception:  # noqa: BLE001  — table might be empty; that is fine
            pass

    def resolve(
        self,
        label: str,
        *,
        tags: list[str] | None = None,
        entity_type: str = "concept",
    ) -> str:
        """Return the node id for *label* — with token-based fuzzy matching.

        Matches by:
        1. Exact label match (case-insensitive)
        2. Token overlap — if all words in the label appear in an existing
           description (or vice versa), they are the same entity.
        3. Tag match fallback.

        If nothing matches, create a new entity candidate.
        """
        key = _normalize(label)
        if not key:
            return ""

        # Direct hit
        if key in self._registry:
            return self._registry[key]

        # Token overlap: any common significant token = match
        # (LLM labels vary in wording but "Hedin" in any form is the same person)
        key_tokens = _tokens(label)
        for reg_key, reg_id in list(self._registry.items()):
            reg_tokens = _tokens(reg_key)
            if len(reg_tokens) > 6 or len(key_tokens) > 6:
                continue  # skip synthesis-length descriptors
            common = key_tokens & reg_tokens
            if common:
                self._registry[key] = reg_id
                return reg_id

        # Tag hit
        if tags:
            for t in tags:
                tkey = t.lower().strip()
                if tkey in self._registry:
                    self._registry[key] = self._registry[tkey]
                    return self._registry[tkey]

        # Miss — create a new entity candidate
        now = datetime.now(UTC)
        node = ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            consolidation_tier=1,
            is_candidate=True,
            semantic_vector=[0.0] * self._semantic_dim,
            frame_vector=[0.0] * self._frame_dim,
            description=label,
            tags=tags or [entity_type.lower()],
        )
        self._store.append_consolidated(node)
        nid = str(node.id)
        self._registry[key] = nid
        return nid

    def resolve_bulk(
        self,
        concepts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Resolve multiple concept references and return augmented entries.

        Each input dict may have ``label``, ``tags``, ``entity_type``, and
        optional ``description``.  Each output dict adds an ``id`` field.
        """
        results: list[dict[str, Any]] = []
        for c in concepts:
            label = str(c.get("label", ""))
            tags = list(c.get("tags", []))
            etype = str(c.get("entity_type", "concept"))
            nid = self.resolve(label, tags=tags, entity_type=etype)
            out = dict(c)
            out["id"] = nid
            results.append(out)
        return results
