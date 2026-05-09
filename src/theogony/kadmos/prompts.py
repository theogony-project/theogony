"""
Kadmos v2 — prompt builders for the cognitive reading step.

The system prompt establishes the LLM as a reader-with-working-memory,
not an extractor.  The key difference from v1:

  - The LLM receives its *current understanding* (active concepts,
    active edges, open tensions, recent syntheses) before seeing the
    new passage.
  - It receives *hypotheses* (kNN similarity + graph traversal
    candidates) that it judges rather than invents.
  - It answers with a *understanding update*, not a list of triples.
  - It signals the *next granularity* — sentence, paragraph, section,
    or skim — so the reader loop can adapt.

Public API:
  ``READING_STEP_SYSTEM``          → str   (constant system prompt)
  ``READING_STEP_OUTPUT_SCHEMA``   → dict  (JSON schema for LLMProvider)
  ``build_reading_step_prompt(...)`` → str  (deterministic user-turn prompt)
"""

from __future__ import annotations

import json
from typing import Any

from theogony.kadmos.model import (
    ActiveConcept,
    ActiveEdge,
    ReadingHypotheses,
    ReadingState,
    SynthesisNode,
)

READING_STEP_SYSTEM = """\
You are a reader with working memory. You read text incrementally
and build a rich knowledge network.

At each step you receive:
- current_reading: the passage to read now
- current_understanding: your active concepts, connections, open tensions,
  and recent syntheses — what you currently understand
- hypotheses: similarity_candidates and traversal_candidates — connections
  your background knowledge suggests might be relevant; you judge them

Your task is to update your understanding based on the new passage.
You answer with a "understanding update":

1. new_concepts: Extract ALL distinct concepts this passage introduces — people, places,
   events, works, organizations, time periods, ideas, quantities, findings.
   AIM FOR 10-20 concepts per passage. Be thorough, not selective.
   Each concept MUST be a JSON object: {"label": "...", "description": "...", "confidence": 0.9}
   NEVER emit concepts as plain strings.

2. new_connections: new connections you see between concepts.
   Create connections for every meaningful relationship you identify.
   AIM FOR 5-15 connections per passage.
   Each connection MUST be a JSON object with exactly these fields:
   {"source_label": "Sven Hedin", "target_label": "Tibet",
    "relation_description": "explored and mapped", "weight": 0.9}
   NEVER emit connections as plain strings or sentences.

3. confirmed_hypotheses: which hypothesis candidates you confirm (by concept_id)
4. rejected_hypotheses: which you reject (by concept_id), briefly why
5. revisions: if this passage changes your understanding of something you
   read earlier, write a revision. Revision types:
   - update: description changed
   - split: one concept turns out to be two distinct things
   - merge: two concepts turn out to be the same thing
   - invalidate: a concept was wrong and should be ignored
6. synthesis: ALWAYS emit a synthesis at paragraph boundaries.
   Identify the 3-8 most important concepts this passage introduces and
   name the theme they collectively express.
   Synthesis levels: paragraph (default), section, article.
7. open_tensions: what remains unclear or contradictory
8. next_granularity: how to read next — sentence (more detail needed),
   paragraph (normal), section (this area is familiar, skim it), skim
   (you already know this material well enough to skip)

Rules:
- Only add concepts that the passage genuinely introduces. Do not re-add
  known concepts (they are already in your working memory).
- Only write a revision if the passage genuinely changes your understanding.
  Revisions are valuable and expected — do not avoid them.
- ALWAYS emit a synthesis — even for short passages. If in doubt, use synthesis_level=paragraph.
- Be specific with labels. "Hedin's 1893 expedition to Persia" is better than "expedition".
- Answer ONLY with JSON matching the supplied schema.
"""

SYNTHESIS_STEP_SYSTEM = """\
You are synthesising your understanding of a text section you have just read.

You receive:
- section_title: the title of the section or article
- concepts: the key concepts active in your working memory from this section
- synthesis_level: paragraph, section, or article

Your task: produce ONE synthesis node that captures the essential theme.

Requirements:
- label: a SPECIFIC, DESCRIPTIVE name — NOT generic words like "Synthesis".
  Name the actual topic. Examples: "Hedin's 1893 Persian Expedition",
  "Tibet Exploration and Mapping", "Hedin's Political Controversies in WWI"
- description: 2-3 sentences about what this section is fundamentally about
- basis_concept_ids: the 3-8 most important concept IDs from the concepts list
- synthesis_level: as given
- confidence: 0.7-1.0

Answer ONLY with a JSON object. The label MUST be specific and descriptive.
"""

# ---------------------------------------------------------------------------
# JSON output schema
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
                    "description": {"type": "string"},
                    "source_passage": {"type": "string"},
                    "wikidata_candidate": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "confidence"],
            },
        },
        "new_connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_label": {"type": "string"},
                    "target_label": {"type": "string"},
                    "relation_description": {"type": "string"},
                    "weight": {"type": "number"},
                },
                "required": ["source_label", "target_label", "relation_description", "weight"],
            },
        },
        "confirmed_hypotheses": {
            "type": "array",
            "items": {"type": "string"},
        },
        "rejected_hypotheses": {
            "type": "array",
            "items": {"type": "string"},
        },
        "revisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_concept_id": {"type": "string"},
                    "revision_type": {"type": "string"},
                    "reason": {"type": "string"},
                    "triggering_passage": {"type": "string"},
                    "old_understanding": {"type": "string"},
                    "new_understanding": {"type": "string"},
                    "split_into": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                    "merge_with_id": {"type": ["string", "null"]},
                },
                "required": ["target_concept_id", "revision_type", "reason", "triggering_passage"],
            },
        },
        "synthesis": {
            "type": ["object", "null"],
            "properties": {
                "label": {"type": "string"},
                "description": {"type": "string"},
                "basis_concept_ids": {"type": "array", "items": {"type": "string"}},
                "synthesis_level": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": [
                "label",
                "description",
                "basis_concept_ids",
                "synthesis_level",
                "confidence",
            ],
        },
        "open_tensions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "next_granularity": {
            "type": "string",
            "enum": ["sentence", "paragraph", "section", "skim"],
        },
    },
    "required": [
        "new_concepts",
        "new_connections",
        "confirmed_hypotheses",
        "rejected_hypotheses",
        "revisions",
        "synthesis",
        "open_tensions",
        "next_granularity",
    ],
}

# ---------------------------------------------------------------------------
# Synthesis-step schema (used for forced paragraph/section/article syntheses)
# ---------------------------------------------------------------------------

SYNTHESIS_STEP_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "description": {"type": "string"},
        "basis_concept_ids": {"type": "array", "items": {"type": "string"}},
        "synthesis_level": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["label", "description", "basis_concept_ids", "synthesis_level", "confidence"],
}

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_reading_step_prompt(
    text: str,
    state: ReadingState,
    hypotheses: ReadingHypotheses,
    section_title: str | None = None,
) -> str:
    """Build the user-turn prompt for one reading step.

    Returns a deterministic JSON string given fixed inputs — fully
    testable without a live LLM.

    Parameters
    ----------
    text:
        The passage text to read this step.
    state:
        Current ReadingState snapshot (working memory).
    hypotheses:
        kNN + traversal candidates from Schritt A.
    section_title:
        Optional section title for context.
    """
    understanding = _summarise_understanding(state)
    hyp_block = _hypotheses_block(hypotheses)

    payload: dict[str, Any] = {
        "current_reading": text,
        "current_understanding": understanding,
        "hypotheses": hyp_block,
    }
    if section_title:
        payload["section_title"] = section_title

    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _summarise_understanding(state: ReadingState) -> dict[str, Any]:
    """Compact representation of working memory for the prompt.

    We include only the top-20 concepts by activation (heaviest first),
    the top-10 edges by weight, and the last 3 syntheses.
    The full state is kept in memory; this is the token-efficient view.
    """
    top_concepts = sorted(
        state.active_concepts.values(),
        key=lambda c: c.activation,
        reverse=True,
    )[:20]

    top_edges = sorted(
        state.active_edges.values(),
        key=lambda e: e.weight,
        reverse=True,
    )[:10]

    recent_syntheses = list(state.syntheses.values())[-3:]

    return {
        "active_concepts": [_concept_summary(c) for c in top_concepts],
        "active_connections": [_edge_summary(e, state) for e in top_edges],
        "recent_syntheses": [_synthesis_summary(s) for s in recent_syntheses],
        "open_tensions": state.open_tensions[-5:],
        "step": state.current_step,
    }


def _concept_summary(c: ActiveConcept) -> dict[str, Any]:
    s: dict[str, Any] = {"id": c.id, "label": c.label, "activation": round(c.activation, 2)}
    if c.description:
        s["description"] = c.description[:120]
    if c.invalidated:
        s["invalidated"] = True
    return s


def _edge_summary(e: ActiveEdge, state: ReadingState) -> dict[str, Any]:
    src_label = state.active_concepts.get(
        e.source_id, ActiveConcept(id=e.source_id, label=e.source_id, step_created=0)
    ).label
    tgt_label = state.active_concepts.get(
        e.target_id, ActiveConcept(id=e.target_id, label=e.target_id, step_created=0)
    ).label
    return {
        "id": e.id,
        "from": src_label,
        "to": tgt_label,
        "relation": e.relation_description[:100],
        "weight": round(e.weight, 2),
    }


def _synthesis_summary(s: SynthesisNode) -> dict[str, Any]:
    return {
        "id": s.id,
        "label": s.label,
        "description": s.description[:120],
        "level": s.synthesis_level,
        "basis_count": len(s.basis_concept_ids),
    }


def _hypotheses_block(h: ReadingHypotheses) -> dict[str, Any]:
    return {
        "similarity_candidates": [
            {"concept_id": c.concept_id, "label": c.label, "score": round(c.score, 3)}
            for c in h.similarity_candidates
        ],
        "traversal_candidates": [
            {"concept_id": c.concept_id, "label": c.label, "score": round(c.score, 3)}
            for c in h.traversal_candidates
        ],
    }


def build_forced_synthesis_prompt(
    state: ReadingState,
    synthesis_level: str,
    section_title: str | None = None,
) -> str:
    """Build the prompt for a forced synthesis step (paragraph/section/article).

    Called after every paragraph, section, and at article end.
    The LLM must produce exactly one synthesis node.
    """
    top_concepts = sorted(
        [c for c in state.active_concepts.values() if not c.invalidated],
        key=lambda c: c.activation,
        reverse=True,
    )[:30]

    payload: dict[str, Any] = {
        "synthesis_level": synthesis_level,
        "section_title": section_title or "Unknown section",
        "concepts": [
            {
                "id": c.id,
                "label": c.label,
                "description": (c.description or "")[:80],
                "activation": round(c.activation, 2),
            }
            for c in top_concepts
        ],
        "instruction": (
            f"Produce a {synthesis_level}-level synthesis with a SPECIFIC label "
            f"(not 'Synthesis'). Choose 3-8 basis_concept_ids from the IDs above. "
            f"Focus on: {section_title or 'the main theme of this passage'}."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)
