"""
Bounded upsert of short text fragments into the Chronik.

Shared by :func:`theogony.mcp.server.tool_chronicle_append` and the Iris
Explorer ``POST /cockpit/api/chronicle-append`` so caps, validation, and
provenance stay identical.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from theogony.config.settings import Settings
from theogony.core.model import (
    EpistemicStatus,
    KnowledgeNode,
    Layer,
    NodeScores,
    NodeType,
    SourceRef,
)
from theogony.core.store import KnowledgeStore
from theogony.extraction.embedding import EmbeddingProvider
from theogony.reporting.models import new_run_id

log = logging.getLogger("theogony.chronicle.append")

AppendOrigin = Literal["pantheon_chronicle_append", "cockpit_explorer"]


def _source_type_for_origin(origin: AppendOrigin) -> str:
    return "mcp_agent" if origin == "pantheon_chronicle_append" else "cockpit_curator"


async def append_text_fragments(
    *,
    settings: Settings,
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    fragments: list[dict[str, Any]],
    context_note: str | None,
    origin: AppendOrigin,
) -> dict[str, Any]:
    """Validate, embed, and ``batch_upsert_nodes`` for one append call."""
    caps = settings.mcp_append
    if not caps.enabled:
        return {
            "error": (
                "chronicle append is disabled (set THEOGONY_MCP_APPEND__ENABLED=true to enable)."
            )
        }
    if not isinstance(fragments, list) or len(fragments) == 0:
        return {"error": "fragments must be a non-empty JSON array of {title, body} objects"}
    if len(fragments) > caps.max_fragments_per_call:
        return {
            "error": (
                f"too many fragments: got {len(fragments)}, max is {caps.max_fragments_per_call}"
            )
        }

    norm: list[tuple[str, str]] = []
    total_body = 0
    for i, raw in enumerate(fragments):
        if not isinstance(raw, dict):
            return {"error": f"fragments[{i}] must be an object with title and body strings"}
        title_raw = raw.get("title")
        body_raw = raw.get("body")
        if not isinstance(title_raw, str) or not isinstance(body_raw, str):
            return {"error": f"fragments[{i}].title and fragments[{i}].body must be strings"}
        title = title_raw.strip()
        body = body_raw.strip()
        if not title or not body:
            return {"error": f"fragments[{i}]: title and body must be non-empty after trimming"}
        if len(title) > caps.max_title_chars:
            return {"error": f"fragments[{i}].title exceeds max_title_chars={caps.max_title_chars}"}
        if len(body) > caps.max_body_chars_per_fragment:
            return {
                "error": (
                    f"fragments[{i}].body exceeds "
                    f"max_body_chars_per_fragment={caps.max_body_chars_per_fragment}"
                )
            }
        total_body += len(body)
        if total_body > caps.max_total_body_chars:
            return {
                "error": (
                    f"sum of body lengths ({total_body}) exceeds "
                    f"max_total_body_chars={caps.max_total_body_chars}"
                )
            }
        norm.append((title, body))

    note: str | None = None
    if context_note is not None:
        if not isinstance(context_note, str):
            return {"error": "context_note must be a string when provided"}
        note = context_note.strip()
        if len(note) > 4000:
            return {"error": "context_note exceeds 4000 characters"}

    texts = [f"{t}\n\n{b}" for t, b in norm]
    try:
        vectors = await embedder.embed_many(texts)
    except Exception as exc:  # pragma: no cover - embedder-specific
        log.exception("chronicle append: embed_many failed")
        return {"error": f"embedding failed: {exc}"}

    if len(vectors) != len(norm):
        return {"error": "embedder returned a different number of vectors than fragments"}

    dim_expected = settings.embedding.dim
    model_tag = getattr(embedder, "model_id", None) or f"{settings.embedding.model_id}@v1"
    stype = _source_type_for_origin(origin)

    nodes: list[KnowledgeNode] = []
    for (title, body), vec in zip(norm, vectors, strict=True):
        if len(vec) != dim_expected:
            return {
                "error": (
                    f"embedding dimension mismatch: got {len(vec)}, "
                    f"expected settings.embedding.dim={dim_expected}"
                )
            }
        frag_id = new_run_id()
        snippet = body if len(body) <= 400 else f"{body[:397]}..."
        ref = SourceRef(
            source_type=stype,
            identifier=frag_id,
            location=None,
            snippet=snippet,
        )
        props: dict[str, Any] = {"origin": origin}
        if note:
            props["context_note"] = note
        nodes.append(
            KnowledgeNode(
                label=title,
                description=body,
                node_type=NodeType.CONCEPT,
                epistemic_status=EpistemicStatus.HYPOTHESIZED,
                layer=Layer.EPHEMERA,
                source_ref=ref,
                scores=NodeScores(
                    confidence=0.35,
                    relevance=0.45,
                    connectivity=0.0,
                    freshness=1.0,
                ),
                embedding=list(vec),
                embedding_model_id=model_tag,
                embedding_dim=dim_expected,
                properties=props,
                resolution_tier=None,
            )
        )

    ids = await store.batch_upsert_nodes(nodes)
    log.info("chronicle append (%s): upserted %d node(s)", origin, len(ids))
    return {
        "upserted_node_ids": ids,
        "fragment_count": len(ids),
        "total_body_chars": total_body,
        "origin": origin,
    }
