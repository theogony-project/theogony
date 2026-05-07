"""
Topology Parser for the Neural Vector Mesh.

This module implements the "Synaptogenesis" (Write Path) described in Run 9.
It abandons rigid NLP pipelines (like spaCy NER) in favor of an LLM acting as a
"Topology Architect". The LLM extracts a fluid, multi-granular concept mesh
(from single words to abstract philosophies) and wires them together with
cognitive edge types.

This pipeline strictly adheres to the "Function-First" doctrine:
- Extreme growth velocity (no global database lookups during extraction).
- Emergent identity (every extraction gets a new UUID; duplicates are healed post-hoc).
- Append-only semantics.
"""

import hashlib
import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from theogony.agents.llm import STRUCTURED_LLM_MIN_TIMEOUT_S, LLMProvider
from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer, NodeType, SourceRef

# Dense JSON (100s of concepts + synapses) needs generous API timeouts.
_TOPOLOGY_LLM_TIMEOUT_S = STRUCTURED_LLM_MIN_TIMEOUT_S

# ---------------------------------------------------------------------------
# LLM Output Schemas (The Blueprint)
# ---------------------------------------------------------------------------


class ExtractedConcept(BaseModel):
    """A single fluid concept extracted by the LLM."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    local_id: str = Field(
        description="A temporary ID used only within this extraction chunk (e.g., 'c1')."
    )
    canonical_text: str = Field(
        alias="text", description="The normalized, canonical name of the extracted concept."
    )
    granularity: float | str = Field(
        default=0.5, description="0.0 (single word) to 1.0 (broad theme)."
    )
    abstraction: float | str = Field(
        default=0.5, description="0.0 (concrete entity) to 1.0 (abstract philosophy)."
    )
    is_implicit: bool = Field(
        default=False,
        description="True if the concept is not literally in the text but evoked by it.",
    )
    char_start: int | None = Field(
        default=None, description="Start character offset in the chunk (-1 or null if implicit)."
    )
    char_end: int | None = Field(
        default=None, description="End character offset in the chunk (-1 or null if implicit)."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Short anchor keywords or half-phrases (macro / partition passes).",
    )

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "label" in data and "text" not in data:
            data["text"] = data["label"]
        if "concept_name" in data and "text" not in data:
            data["text"] = data["concept_name"]
        if "name" in data and "text" not in data:
            data["text"] = data["name"]
        if "title" in data and "text" not in data:
            data["text"] = data["title"]
        return data


_RELATION_ALIASES: dict[str, str] = {
    "BINDS": "BINDS_TO",
    "BIND": "BINDS_TO",
    "REINFORCE": "REINFORCES",
    "CAUSE": "CAUSED_BY",
    "ABSTRACTION": "ABSTRACTION_OF",
    "MODULATE": "MODULATES",
    "CONTRADICT": "CONTRADICTS",
}

_ALLOWED_RELATIONS = frozenset(
    {"BINDS_TO", "REINFORCES", "CAUSED_BY", "ABSTRACTION_OF", "MODULATES", "CONTRADICTS"}
)


class ExtractedSynapse(BaseModel):
    """A cognitive edge connecting two concepts within the chunk."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    source: str = Field(alias="from", description="The local_id of the source concept.")
    target: str = Field(alias="to", description="The local_id of the target concept.")
    relation_type: str = Field(
        alias="type",
        description="Must be from the codebook: BINDS_TO, REINFORCES, CAUSED_BY, ABSTRACTION_OF, MODULATES, CONTRADICTS.",
    )
    weight: float = Field(ge=0.0, le=1.0, description="Initial synaptic weight (0.0 to 1.0).")

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "source_id" in data and "from" not in data:
            data["from"] = data["source_id"]
        if "source" in data and "from" not in data:
            data["from"] = data["source"]
        if "target_id" in data and "to" not in data:
            data["to"] = data["target_id"]
        if "target" in data and "to" not in data:
            data["to"] = data["target"]
        if "relation" in data and "type" not in data:
            data["type"] = data["relation"]
        if isinstance(data, dict) and "type" in data:
            raw = data["type"]
            if isinstance(raw, str):
                t = raw.strip().upper().replace(" ", "_").replace("-", "_")
                if t in _RELATION_ALIASES:
                    t = _RELATION_ALIASES[t]
                if t not in _ALLOWED_RELATIONS:
                    # Many validation failures are lowercase variants; coerce when obvious.
                    fix = raw.strip().upper().replace(" ", "_").replace("-", "_")
                    if fix in _ALLOWED_RELATIONS:
                        t = fix
                    elif fix in _RELATION_ALIASES:
                        t = _RELATION_ALIASES[fix]
                    else:
                        t = "BINDS_TO"
                data["type"] = t
        return data


class TopologicalBlueprint(BaseModel):
    """The complete JSON output expected from the LLM."""

    cognitive_analysis: str = Field(
        description="Brief Chain-of-Thought reasoning before extraction."
    )
    concepts: list[ExtractedConcept]
    synapses: list[ExtractedSynapse]


def _coerce_cognitive_analysis_field(raw: object) -> str:
    """LLMs sometimes omit this field, emit null, or use objects — schema requires a string."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()[:250]
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, ensure_ascii=False)[:250]
    return str(raw)[:250]


def _normalize_blueprint_concepts(obj: dict[str, Any]) -> None:
    """Map common LLM field names onto ``text`` so ExtractedConcept validates."""
    concepts = obj.get("concepts")
    if not isinstance(concepts, list):
        return
    for c in concepts:
        if not isinstance(c, dict):
            continue
        if c.get("text") not in (None, ""):
            continue
        for key in (
            "label",
            "name",
            "title",
            "canonical",
            "canonical_text",
            "concept",
            "concept_name",
            "string",
            "content",
            "summary",
            "description",
        ):
            val = c.get(key)
            if isinstance(val, str) and val.strip():
                c["text"] = val.strip()
                break
        if (
            c.get("text") in (None, "")
            and isinstance(c.get("local_id"), str)
            and c["local_id"].strip()
        ):
            # Last resort so validation succeeds; label merge post-hoc may collapse these.
            c["text"] = c["local_id"].strip()


def _normalize_blueprint_synapses(obj: dict[str, Any]) -> None:
    """Map ``source`` / ``target`` onto synapse ``from`` / ``to`` (codebook JSON)."""
    synapses = obj.get("synapses")
    if not isinstance(synapses, list):
        return
    for s in synapses:
        if not isinstance(s, dict):
            continue
        if s.get("from") in (None, "") and s.get("source") not in (None, ""):
            s["from"] = s["source"]
        if s.get("to") in (None, "") and s.get("target") not in (None, ""):
            s["to"] = s["target"]


def extract_topology_blueprint_dict_from_llm_text(raw: str) -> dict[str, Any]:
    """Parse the first JSON object from model output; strip ``` fences; tolerate trailing junk."""
    s = raw.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        s = "\n".join(lines).strip()

    brace = s.find("{")
    if brace < 0:
        raise ValueError("LLM output contains no JSON object")

    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(s[brace:])
    if not isinstance(obj, dict):
        raise ValueError("topology JSON root must be an object")

    obj["cognitive_analysis"] = _coerce_cognitive_analysis_field(obj.get("cognitive_analysis"))
    _normalize_blueprint_concepts(obj)
    _normalize_blueprint_synapses(obj)
    return obj


def full_density_chunk_targets(n_chars: int) -> tuple[int, int, int]:
    """Return (min_concepts, stretch_concepts, max_synapses) for ``density=full`` user prompt.

    Tunables trade node richness vs JSON size. Synapse ceiling allows meso-scale hub degree.
    """
    n = max(0, n_chars)
    # Aspirational ~38–48 concepts / 1000 chars before caps (multi-scale overlap).
    min_c = max(40, min(260, (n * 38) // 1000))
    stretch = max(min_c, min(320, (n * 48) // 1000))
    max_syn = min(2500, max(400, int(min_c * 7)))
    return min_c, stretch, max_syn


def hierarchical_macro_targets(n_chars: int) -> tuple[int, int, int, int]:
    """(macro_min, macro_max, min_peer_synapses, max_peer_synapses) for MACRO partition pass."""
    n = max(0, n_chars)
    lo = max(10, min(24, 10 + n // 3000))
    hi = max(lo + 4, min(34, 16 + n // 900))
    # Stay within one completion: huge synapse lists truncate mid-JSON.
    min_syn = max(72, min(520, n // 35))
    max_syn = min(800, max(min_syn + 80, hi * 20))
    return lo, hi, min_syn, max_syn


def subdivide_slice_targets(slice_len: int) -> tuple[int, int, int, int]:
    """(concept_min, concept_max, min_synapses, max_synapses) for one SUBDIVIDE LLM call."""
    L = max(1, slice_len)
    min_c = max(6, min(18, 5 + L // 1400))
    max_c = max(min_c + 2, min(24, 8 + L // 600))
    min_syn = max(28, min(180, min_c * 4, L // 180))
    max_syn = min(420, max(72, max_c * 12))
    if min_syn > max_syn:
        min_syn = max(24, max_syn // 2)
    return min_c, max_c, min_syn, max_syn


# ---------------------------------------------------------------------------
# The System Prompt
# ---------------------------------------------------------------------------

TOPOLOGY_ARCHITECT_PROMPT = """\
You are the Topology Architect for The Chronicle, an AI-Native Memory Fabric.
Your objective is to process unstructured raw text and synthesize a fluid, multi-dimensional cognitive topology.
You will output a strict JSON object representing the concepts and synapses (edges) extracted from the text.

Do not use rigid NLP methodologies. Mimic human cognitive memory by extracting concepts at ALL scales of granularity, creating overlapping distributed representations.

EXTRACTION DOCTRINE:

1. Multi-Scale Granularity: Extract concepts across all layers:
   - ATOMIC: Single entities, words, or actors (e.g., "Albert Einstein", "Neutron").
   - COMPOUND: Complete sentences, complex actions, or distinct ideas (e.g., "Einstein fled from the Nazis").
   - THEMATIC: Overarching philosophies, concepts, or categories (e.g., "Theoretical Physics", "Authoritarianism").

2. Fluid Interconnectivity: A concept is defined entirely by its connections. You must draw edges that connect ATOMIC entities to COMPOUND thoughts, and COMPOUND thoughts to THEMATIC concepts. Do not create isolated nodes.

3. Implicit Concepts ARE allowed. If reading the chunk plausibly evokes a higher-order concept that is NOT literally written (e.g., "Intellectual Exile"), emit it with char_start = -1, char_end = -1, and is_implicit = true.

4. Edge Codebook: Use ONLY the following relation types to connect nodes:
   - BINDS_TO: Connects adjacent/syntactic elements. (Weight: 0.8-1.0)
   - REINFORCES: Connects supporting evidence to a broader thought. (Weight: 0.7-1.0)
   - CAUSED_BY: Establishes chronological/causal dependency. (Weight: 0.6-0.9)
   - ABSTRACTION_OF: Links a specific granular entity/thought to a broad theme. (Weight: 0.5-0.8)
   - MODULATES: Connects contextual information that shades the meaning of a target. (Weight: 0.3-0.6)
   - CONTRADICTS: Indicates conflicting information or caveats. (Weight: 0.5-0.9)

5. Function-First Constraint: Generate simple local IDs (e.g., "c1", "c2") for `local_id`. Do NOT attempt to guess global IDs or perform external database lookups. Treat the text in complete isolation.

WORKFLOW:
Step 1: Write a brief `cognitive_analysis` identifying the core entities, the main narrative/action, and the overarching themes present in the chunk.
Step 2: Generate the `concepts` array across **all granularity bands** (see HIERARCHY / DEGREE addendum when present).
       Follow **CHUNK_TARGET** in the user message for minimum and stretch counts.
       Rich prose: target up to **roughly 35–55 concepts per 1000 characters** before caps — overlap across scales counts.
Step 3: Generate the `synapses` array within the CHUNK_TARGET synapse ceiling. Implement **horizontal** (peer) and **vertical**
       (subordinate / superordinate) wiring as described in the addendum; prioritize **meso-scale hub** connectivity.

You must respond ONLY with the exact JSON object defined by the schema.
"""

TOPOLOGY_DENSITY_FULL_ARTICLE = """
FULL-TEXT DENSITY ADDENDUM:
The input is a long segment (e.g. encyclopedic article or book chapter fragment).
For substantive prose, aim **roughly 35–55 concepts per 1000 characters** before the absolute cap (overlap across hierarchical levels is intended).

Output budget: one JSON response must stay **complete and parseable**. Hard cap **320 concepts** per response.
When the segment is long, **sample** across beginning / middle / end rather than only the opening lines.

**Never** truncate mid-string: shorten `cognitive_analysis`, drop lowest-value synapses, or omit marginal concepts **above** the CHUNK_TARGET minimum before you risk invalid JSON.

JSON DISCIPLINE (non-negotiable):
- Return a **single** JSON object. No markdown code fences, no text after the closing brace.
- `cognitive_analysis` may be at most **250 characters** (shorter is better).
- Every `concepts[].text` must be a **non-empty** string; escape double quotes as \\" inside text.
- Every `synapses[].type` must be one of: BINDS_TO, REINFORCES, CAUSED_BY, ABSTRACTION_OF, MODULATES, CONTRADICTS
  (UPPER_SNAKE_CASE).
- If you approach output limits: drop synapses that add least structure before trimming concepts **above** the CHUNK_TARGET minimum.

Minimum / stretch concept counts are in **CHUNK_TARGET**; absolute maximum **320 concepts** per response.
Ignore navigation boilerplate if present. Return only valid JSON for the schema.
"""

TOPOLOGY_HIERARCHY_DEGREE_ADDENDUM = """
HIERARCHY & MULTI-SCALE DEGREE (mandatory design intent):

Granularity bands (use the numeric `granularity` field on each concept; approximate ranges):
- **ATOMIC** (~0.00–0.35): fine-grained tokens — named entities, places, concrete facts, short phrases.
- **MESO** (~0.35–0.75): medium spans — events, motives, processes, paragraph-scale claims.
- **MACRO** (~0.75–1.00): themes, regimes, epochs, disciplines, moral frames.

Connectivity rules:
- **Vertical**: Every MESO hub should link **down** to several ATOMIC children and **up** to at least one MACRO parent where the text supports it
  (prefer ABSTRACTION_OF for generalisation, BINDS_TO for meronymy/part-whole when apt).
- **Horizontal**: Link each MESO concept to **peer** MESO and ATOMIC concepts that co-occur in the same passage (REINFORCES, MODULATES,
  CAUSED_BY, CONTRADICTS as appropriate).
- **Hub degree**: For MESO-scale concepts (the “middle” band), aim for **about 20–50 incident synapses each** when the passage is rich enough.
  If the chunk is short or sparse, scale down proportionally — but never collapse to a near-tree; preserve cross-links.

Use the CHUNK_TARGET synapse ceiling as a hard budget: spend it on **high-degree MESO hubs** and vertical stitching before adding redundant duplicates.
"""

TOPOLOGY_MACRO_PARTITION_PROMPT = """\
MACRO PARTITION PASS (top of hierarchy):
You partition the **entire** input text into the **inclusive concept count band** given in **MACRO_TARGET** below.
Each MACRO must:
- Cover a coherent slice of the passage with **char_start** and **char_end** as **0-based character offsets into the full input string** (end exclusive).
- Use **granularity** around **0.82–0.98** (broad themes / section-scale claims).
- Include **keywords**: 3–12 short anchor phrases or half-sentences (literal phrases drawn from or summarizing that slice).
- Overlap between neighbouring MACRO spans is allowed briefly for continuity (avoid huge duplication).

**Peer mesh (critical):** Draw **synapses only among these MACRO concepts** (no fine-grained entities here).
Meet **MACRO_TARGET** minimum and ceiling for **total** `synapses` in this JSON — this pass must be a **connected, high-degree** macro atlas (not a tree).
Use REINFORCES, MODULATES, CAUSED_BY, CONTRADICTS, BINDS_TO so that **most** MACRO nodes have **several** incident synapses to **other** MACRO nodes.

Do **not** invent fine-grained entities here — this pass is the atlas of the chunk only.

**JSON survival:** The object must be **complete and parseable**. If needed, stay under the synapse **max** rather than risking truncation.

Return only valid JSON matching the TopologicalBlueprint schema.
"""

TOPOLOGY_SUBDIVIDE_PROMPT = """\
SUBDIVIDE PASS (finer hierarchy inside a parent slice):
The user message contains **one contiguous text slice** (a substring of a larger chunk). Offsets in `concepts[].char_start` / `char_end` must be **relative to this slice** (0 = first character of the slice).

Emit the **inclusive concept count band** from **SUBDIVIDE_TARGET** below — enough concepts to **subdivide** this slice (MESO / ATOMIC mix).
- Prefer **granularity** roughly **0.15–0.75** for children.
- Pack **keywords** (2–10) per concept where helpful.

**Peer mesh (critical):** Meet **SUBDIVIDE_TARGET** for **minimum and maximum** total `synapses` among these child concepts.
Aim for **small-world** connectivity: each child should tie to **multiple** siblings (REINFORCES, MODULATES, CAUSED_BY, CONTRADICTS, BINDS_TO, ABSTRACTION_OF between peers where one subsumes another).
Sparse or near-tree outputs are **incorrect** for this pass.

**JSON survival (non-negotiable):** One response must be **complete, parseable JSON**. If the synapse budget risks truncation,
reduce concept count or synapse count — **never** leave an unclosed string or array. Prefer staying under **max** over hitting **min** if forced to choose.

Return only valid JSON matching the TopologicalBlueprint schema.
"""

# ---------------------------------------------------------------------------
# The Parser
# ---------------------------------------------------------------------------


class TopologyParser:
    """
    Orchestrates the Text-to-Topology pipeline.

    1. Sends raw text to the LLM (DeepSeek).
    2. Receives the Topological Blueprint (JSON).
    3. Translates local IDs to global emergent UUIDs.
    4. Instantiates KnowledgeNode and KnowledgeEdge Pydantic models.
    5. (Embeddings are assumed to be calculated asynchronously later).
    """

    def __init__(self, llm: LLMProvider, *, llm_timeout_s: float = _TOPOLOGY_LLM_TIMEOUT_S) -> None:
        self.llm = llm
        self._llm_timeout_s = llm_timeout_s

    def _normalize_for_hash(self, text: str) -> str:
        """Lowercase and collapse whitespace for the deterministic anchor hash."""
        return " ".join(text.lower().split())

    def mesh_from_blueprint(
        self,
        blueprint: TopologicalBlueprint,
        source_ref: SourceRef,
        extractor_run_id: str,
        *,
        hierarchy_hint: str | None = None,
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
        """Instantiate mesh nodes/edges from a validated TopologicalBlueprint."""
        nodes: list[KnowledgeNode] = []
        edges: list[KnowledgeEdge] = []
        local_to_global_id: dict[str, str] = {}

        for concept in blueprint.concepts:
            global_uuid = f"AKA-{uuid.uuid4().hex[:12]}"
            local_to_global_id[concept.local_id] = global_uuid

            anchor_hash = hashlib.sha256(
                self._normalize_for_hash(concept.canonical_text).encode()
            ).hexdigest()

            props: dict[str, Any] = {
                "granularity": concept.granularity,
                "abstraction": concept.abstraction,
                "is_implicit": concept.is_implicit,
                "char_start": concept.char_start,
                "char_end": concept.char_end,
                "anchor_hash": anchor_hash,
                "extractor_run_id": extractor_run_id,
                "keywords": list(concept.keywords) if concept.keywords else [],
            }
            if hierarchy_hint:
                props["hierarchy_pass"] = hierarchy_hint

            node = KnowledgeNode(
                id=global_uuid,
                label=concept.canonical_text,
                node_type=NodeType.CONCEPT,
                layer=Layer.EPHEMERA,
                source_ref=source_ref,
                properties=props,
            )
            nodes.append(node)

        for synapse in blueprint.synapses:
            source_global_id = local_to_global_id.get(synapse.source)
            target_global_id = local_to_global_id.get(synapse.target)

            if not source_global_id or not target_global_id:
                continue

            edge_props: dict[str, Any] = {"extractor_run_id": extractor_run_id}
            if hierarchy_hint:
                edge_props["hierarchy_pass"] = hierarchy_hint

            edge = KnowledgeEdge(
                source_id=source_global_id,
                target_id=target_global_id,
                relation_type=synapse.relation_type,
                weight=synapse.weight,
                source_ref=source_ref,
                properties=edge_props,
            )
            edges.append(edge)

        return nodes, edges

    async def parse_chunk(
        self,
        text_chunk: str,
        source_ref: SourceRef,
        extractor_run_id: str,
        *,
        density: Literal["summary", "full"] = "summary",
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
        """
        Parse a raw text chunk into a fluid mesh of nodes and edges.

        ``density="full"`` uses a higher target concept count for long article segments.
        """
        system = TOPOLOGY_ARCHITECT_PROMPT
        if density == "full":
            system = (
                TOPOLOGY_ARCHITECT_PROMPT
                + TOPOLOGY_DENSITY_FULL_ARTICLE
                + TOPOLOGY_HIERARCHY_DEGREE_ADDENDUM
            )
        # Large completions — hierarchy + hub degree needs room; truncation still possible at provider limits.
        max_out = 65536 if density == "full" else 8192
        temperature = 0.32 if density == "full" else 0.45

        user_prompt = "Extract the cognitive topology from the following text:\n\n" + text_chunk
        if density == "full":
            mn, st, mx_syn = full_density_chunk_targets(len(text_chunk))
            user_prompt += (
                "\n\n--- CHUNK_TARGET ---\n"
                f"Approximate chunk size: {len(text_chunk)} characters.\n"
                f"Concepts — minimum (unless the passage is trivially short): {mn}. "
                f"Stretch goal for dense prose: {st}.\n"
                f"Synapses — hard ceiling: {mx_syn} total (build MESO hubs with high incident degree per hierarchy addendum).\n"
                "If you must save JSON space: trim lowest-value synapses first; keep vertical links before ornamental parallels.\n"
            )

        # 1. Call the LLM (The Topology Architect)
        result = await self.llm.complete(
            prompt=user_prompt,
            system=system,
            json_schema=TopologicalBlueprint.model_json_schema(),
            temperature=temperature,
            timeout_s=self._llm_timeout_s,
            max_output_tokens=max_out,
        )

        try:
            blueprint_dict = extract_topology_blueprint_dict_from_llm_text(result.text or "")
            blueprint = TopologicalBlueprint.model_validate(blueprint_dict)
        except (json.JSONDecodeError, ValueError) as e:
            # Honest-Failure: If the LLM fails to produce valid JSON, we don't crash.
            # We would log this to a Dead-Letter Queue (DLQ) in a real pipeline.
            raise RuntimeError(f"Failed to parse LLM output into TopologicalBlueprint: {e}") from e

        return self.mesh_from_blueprint(
            blueprint, source_ref, extractor_run_id, hierarchy_hint="single_pass"
        )

    async def parse_macro_partition(
        self,
        text_chunk: str,
        source_ref: SourceRef,
        extractor_run_id: str,
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
        """Single LLM pass: partition full chunk into MACRO concepts with dense peer synapses."""
        lo, hi, min_syn, max_syn = hierarchical_macro_targets(len(text_chunk))
        system = (
            TOPOLOGY_ARCHITECT_PROMPT
            + TOPOLOGY_MACRO_PARTITION_PROMPT
            + TOPOLOGY_HIERARCHY_DEGREE_ADDENDUM
        )
        user_prompt = (
            "Partition the following text into MACRO concepts (see MACRO PARTITION instructions).\n\n"
            "--- MACRO_TARGET ---\n"
            f"Concept band: {lo}–{hi} MACRO concepts (inclusive).\n"
            f"Synapses (peer MACRO↔MACRO only): at least {min_syn} total, stay at or under {max_syn}.\n"
            f"Approximate chunk size: {len(text_chunk)} characters.\n\n" + text_chunk
        )
        result = await self.llm.complete(
            prompt=user_prompt,
            system=system,
            json_schema=TopologicalBlueprint.model_json_schema(),
            temperature=0.3,
            timeout_s=self._llm_timeout_s,
            max_output_tokens=32_768,
        )
        try:
            blueprint_dict = extract_topology_blueprint_dict_from_llm_text(result.text or "")
            blueprint = TopologicalBlueprint.model_validate(blueprint_dict)
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"MACRO partition: invalid TopologicalBlueprint: {e}") from e

        return self.mesh_from_blueprint(
            blueprint, source_ref, extractor_run_id, hierarchy_hint="macro"
        )

    async def parse_subdivide_slice(
        self,
        slice_text: str,
        source_ref: SourceRef,
        extractor_run_id: str,
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
        """One LLM pass: subdivide a substring slice into finer concepts (offsets relative to slice)."""
        slen = len(slice_text)
        c_lo, c_hi, s_lo, s_hi = subdivide_slice_targets(slen)
        system = (
            TOPOLOGY_ARCHITECT_PROMPT
            + TOPOLOGY_SUBDIVIDE_PROMPT
            + TOPOLOGY_HIERARCHY_DEGREE_ADDENDUM
        )
        user_prompt = (
            "Subdivide the following text slice (offsets are relative to this string):\n\n"
            "--- SUBDIVIDE_TARGET ---\n"
            f"Concept band: {c_lo}–{c_hi} concepts (inclusive).\n"
            f"Synapses (peer wiring among these child concepts): at least {s_lo} total, "
            f"stay at or under {s_hi}.\n"
            f"Slice length: {slen} characters.\n\n" + slice_text
        )
        result = await self.llm.complete(
            prompt=user_prompt,
            system=system,
            json_schema=TopologicalBlueprint.model_json_schema(),
            temperature=0.32,
            timeout_s=self._llm_timeout_s,
            max_output_tokens=32768,
        )
        try:
            blueprint_dict = extract_topology_blueprint_dict_from_llm_text(result.text or "")
            blueprint = TopologicalBlueprint.model_validate(blueprint_dict)
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"SUBDIVIDE pass: invalid TopologicalBlueprint: {e}") from e

        return self.mesh_from_blueprint(
            blueprint, source_ref, extractor_run_id, hierarchy_hint="subdivide"
        )
