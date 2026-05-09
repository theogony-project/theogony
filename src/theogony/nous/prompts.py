"""
Prompt builders for the Nous reading-step LLM call (nous_implementation_brief §2, E2).

Public API:
    ``build_reading_step_prompt(...)`` → str   (the user-turn prompt)
    ``READING_STEP_SYSTEM``            → str   (the system prompt, constant)
    ``READING_STEP_OUTPUT_SCHEMA``     → dict  (JSON schema for LLMProvider)

The JSON schema is hand-crafted (not auto-generated from Pydantic) to match
the ``LLMProvider.complete`` interface, following the same pattern as the
existing relation/topology extractors.  Field semantics live in the system
prompt; Pydantic validation of the parsed output happens in NousReader.

Chronicle codebook relation types (also surfaced in the brief):
    BINDS_TO, REINFORCES, CAUSED_BY, ABSTRACTION_OF, MODULATES, CONTRADICTS
"""

from __future__ import annotations

import json
from typing import Any

from theogony.nous.model import ChronicleHint, WorkingMemoryState

READING_STEP_SYSTEM = """\
You are a cognitive synthesis agent reading a Wikipedia article paragraph by paragraph.

At each step you receive:
- paragraph_text: the paragraph to read now
- working_memory: your active concept set (node ids → weights, pooled for context)
- chronicle_hints: top-5 kNN hits from an external knowledge store offered as context
- open_tensions: concept pairs currently in conflict that need resolution
- synthesis_opportunity: whether this is a good moment to synthesise

Your task:
1. Extract NEW concepts from the paragraph (entities, events, claims, ideas).
   - Each concept needs a label, node_type (one of: person, place, concept, event,
     claim, work, organization, time, quantity, source, finding, experiment, other),
     a short description, and an optional wikidata_id guess.
2. Extract EDGES between concepts (or between new and working-memory concepts).
   - Each edge needs source_label, target_label, relation_type, evidence_span,
     confidence (0.0–1.0), and an optional relation_codebook entry
     (BINDS_TO | REINFORCES | CAUSED_BY | ABSTRACTION_OF | MODULATES | CONTRADICTS).
3. Record which chronicle_hints you actually used in chronicle_hits_used (list of ids).
4. If synthesis_opportunity is true AND the paragraph is substantive, emit a
   synthesis_event that condenses the active concepts into a higher-level node.
   Include diagonal_edges to bind the synthesis to higher-level concepts if applicable.
   Set synthesis_event to null for low-density paragraphs (short, list-only, headers).
5. If you detect tension between the new paragraph and existing working memory,
   emit repair_events naming which concept to revise and why.
6. If a new concept's wikidata_id can be guessed or confirmed, emit a
   resolution_update.

You answer ONLY with JSON matching the supplied schema.
Never invent concepts that the paragraph does not support.
Do not copy chronicle hints verbatim into new_concepts — only reference them via
chronicle_hits_used if they strengthen or relate to concepts you are creating.
"""

# ---------------------------------------------------------------------------
# JSON output schema (manually crafted for LLMProvider compatibility)
# ---------------------------------------------------------------------------

READING_STEP_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "new_concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "node_type": {"type": "string"},
                    "description": {"type": "string"},
                    "wikidata_id": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "node_type", "confidence"],
            },
        },
        "new_edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_label": {"type": "string"},
                    "target_label": {"type": "string"},
                    "relation_type": {"type": "string"},
                    "relation_codebook": {"type": "string"},
                    "evidence_span": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "source_label",
                    "target_label",
                    "relation_type",
                    "evidence_span",
                    "confidence",
                ],
            },
        },
        "chronicle_hits_used": {
            "type": "array",
            "items": {"type": "string"},
        },
        "synthesis_event": {
            "type": ["object", "null"],
            "properties": {
                "label": {"type": "string"},
                "description": {"type": "string"},
                "basis_node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "diagonal_edges": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                },
                "synthesis_level": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["label", "basis_node_ids", "synthesis_level", "confidence"],
        },
        "repair_events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "revised_node_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "old_description": {"type": "string"},
                    "new_description": {"type": "string"},
                    "tension_source": {"type": "string"},
                },
                "required": ["revised_node_id", "reason", "tension_source"],
            },
        },
        "resolution_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "previous_tier": {"type": ["integer", "null"]},
                    "new_tier": {"type": "integer"},
                    "new_wikidata_id": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["node_id", "new_tier", "reason"],
            },
        },
    },
    "required": [
        "new_concepts",
        "new_edges",
        "chronicle_hits_used",
        "synthesis_event",
        "repair_events",
        "resolution_updates",
    ],
}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_reading_step_prompt(
    paragraph: str,
    working_memory: WorkingMemoryState,
    chronicle_hints: list[ChronicleHint],
    open_tensions: list[tuple[str, str]],
    synthesis_opportunity: bool,
) -> str:
    """Build the user-turn prompt for one reading step.

    Returns a deterministic JSON-wrapped string given fixed inputs — fully
    testable without a live LLM.

    Parameters
    ----------
    paragraph:
        The paragraph text to be read this step.
    working_memory:
        Current snapshot of active concepts (after decay applied).
    chronicle_hints:
        Top-N kNN Chronicle hits to offer as context.
    open_tensions:
        Currently unresolved (node_id, description) tension pairs.
    synthesis_opportunity:
        True when the reader is at a paragraph boundary and a synthesis
        would be appropriate.
    """
    wm_summary = _working_memory_summary(working_memory)
    hints_block = _chronicle_hints_block(chronicle_hints)
    tensions_block = _tensions_block(open_tensions)

    payload = {
        "paragraph_text": paragraph,
        "working_memory": wm_summary,
        "chronicle_hints": hints_block,
        "open_tensions": tensions_block,
        "synthesis_opportunity": synthesis_opportunity,
    }
    return json.dumps(payload, ensure_ascii=False)


def _working_memory_summary(wm: WorkingMemoryState) -> dict[str, Any]:
    """Compact representation of working memory for the prompt.

    We include only the top-10 concepts by weight — the LLM does not need
    the full 50-entry registry in the prompt; it needs the salient concepts.
    """
    top_concepts = sorted(wm.concepts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "step_index": wm.step_index,
        "top_concepts": [{"id": nid, "weight": round(w, 3)} for nid, w in top_concepts],
    }


def _chronicle_hints_block(hints: list[ChronicleHint]) -> list[dict[str, Any]]:
    """Serialise Chronicle hints for injection into the prompt."""
    return [
        {
            "id": h.id,
            "label": h.label,
            "similarity": round(h.similarity, 3),
            "source": h.source,
            **({"tension": True} if h.tension else {}),
        }
        for h in hints
    ]


def _tensions_block(tensions: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"node_id": node_id, "description": desc} for node_id, desc in tensions]
