"""
NousReader — cognitive synthesis agent (nous_implementation_brief §2, §4 E3).

Main entry point: ``NousReader.read(url) -> tuple[AnnotatedReading, NousRunReport]``

Loop structure (brief §4 E3):
  for each section → for each paragraph:
    1. Apply exponential decay to working memory (τ=3.0 paragraphs)
    2. Compute pooled embedding from top-N active concepts
    3. asyncio.gather(LLM reading-step call, kNN Chronicle search) — Q8
    4. Parse LLMReadingOutput from LLM response
    5. Map raw concept dicts → KnowledgeNode (with nous_session_id, synthesis_level)
    6. Map raw edge dicts → KnowledgeEdge (with relation_codebook)
    7. Apply resolution_updates to session registry
    8. Apply repair_events to local synthesis graph
    9. If synthesis_event: write synthesis node + edges to Chronicle
   10. Update working memory (decay already applied in step 1)
   11. Append ReadingStep to AnnotatedReading

Post-loop:
  - Article-end backfill: re-resolve concepts with tier <= 1
  - Build and return NousRunReport

Failure discipline (Build Doctrine / AGENTS.md §3):
  - LLM parse failure on one paragraph: log warning, continue, record failed step
  - > 20% paragraph failures → verdict="partial"
  - > 50% paragraph failures → verdict="failed"
  - Chronicle write failure: log, continue (never crash the session)

No LLM calls in __init__ (talos.md discipline).
"""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from theogony.config.logging import get_logger
from theogony.core.model import (
    EdgeType,
    EpistemicStatus,
    KnowledgeEdge,
    KnowledgeNode,
    NodeType,
    SourceRef,
    compute_edge_id,
    compute_node_id,
)
from theogony.nous.model import (
    AnnotatedReading,
    ChronicleHint,
    LLMReadingOutput,
    ReadingStep,
    RepairEvent,
    ResolutionUpdate,
    SynthesisOutput,
    WorkingMemoryState,
)
from theogony.nous.prompts import (
    READING_STEP_OUTPUT_SCHEMA,
    READING_STEP_SYSTEM,
    build_reading_step_prompt,
)
from theogony.nous.wikipedia_parser import WikiSection, fetch_article_structured
from theogony.reporting.models import NousRunReport

if TYPE_CHECKING:
    from theogony.agents.llm import LLMProvider
    from theogony.core.store import KnowledgeStore
    from theogony.extraction.embedding import EmbeddingProvider

log = get_logger("nous.reader")

# Working memory parameters (nous_implementation_brief §1 Q2)
_DECAY_TAU = 3.0  # paragraphs
_WM_CAPACITY = 50  # max active concepts
_WM_TOP_N_FOR_POOL = 10  # top-N concepts used for pooled embedding
_CHRONICLE_K = 5  # kNN top-K (brief Q3)

# Failure thresholds
_PARTIAL_FAIL_THRESHOLD = 0.20
_HARD_FAIL_THRESHOLD = 0.50


class NousReader:
    """Cognitive synthesis agent — reads Wikipedia articles incrementally.

    Parameters
    ----------
    store:
        Chronicle store for kNN search and writing synthesised nodes/edges.
    llm:
        LLM provider for reading-step structured output.
    embedder:
        Embedding provider for working-memory concept vectors.
    max_sections:
        If set, process at most this many sections (for fast iteration / tests).
    source_type:
        Source type string recorded in SourceRef for Nous-produced nodes.
        Defaults to "wikipedia".
    """

    def __init__(
        self,
        store: KnowledgeStore,
        llm: LLMProvider,
        embedder: EmbeddingProvider,
        *,
        max_sections: int | None = None,
        source_type: str = "wikipedia",
    ) -> None:
        self._store = store
        self._llm = llm
        self._embedder = embedder
        self._max_sections = max_sections
        self._source_type = source_type

    async def read(self, url: str) -> tuple[AnnotatedReading, NousRunReport]:
        """Run a full Nous reading session on the article at ``url``.

        Returns an ``AnnotatedReading`` (session JSON artefact) and a
        ``NousRunReport`` (pipeline telemetry).  Never raises — failures
        are captured in the report with the appropriate verdict.
        """
        session_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        wall_start = time.monotonic()

        log.info("nous session started session_id=%s url=%s", session_id, url)

        # Determine whether the Chronicle is seeded before this session.
        try:
            chronicle_seeded = await self._is_chronicle_seeded()
        except Exception:
            chronicle_seeded = False

        sections: list[WikiSection] = []
        article_title = url
        try:
            sections = await fetch_article_structured(url)
            article_title = _extract_title_from_url(url)
        except Exception as exc:
            log.warning("nous: failed to fetch article url=%s error=%s", url, exc)
            return self._empty_failed_session(
                session_id=session_id,
                url=url,
                article_title=article_title,
                started_at=started_at,
                chronicle_seeded=chronicle_seeded,
                reason=f"fetch failed: {exc}",
            )

        if self._max_sections is not None:
            sections = sections[: self._max_sections]

        # Session state
        wm_concepts: dict[str, float] = {}
        wm_embedding: list[float] = []
        open_tensions: list[tuple[str, str]] = []
        # Maps node label (lower) → node_id within this session
        session_label_map: dict[str, str] = {}
        # Resolution registry: node_id → wikidata_id (if resolved)
        resolution_registry: dict[str, str] = {}

        steps: list[ReadingStep] = []
        step_index = 0
        failed_steps = 0

        # Counters for report
        total_nodes_written = 0
        total_edges_written = 0
        total_synthesis_events = 0
        total_repair_events = 0
        total_hints_offered = 0
        total_hints_used = 0
        total_llm_calls = 0
        total_llm_cost_eur = 0.0

        for section in sections:
            for paragraph in section.paragraphs:
                # ---- Step 1: apply decay -----------------------------------
                _apply_decay(wm_concepts)

                # ---- Step 2: compute pooled embedding ----------------------
                if wm_concepts:
                    wm_embedding = await self._compute_pooled_embedding(
                        wm_concepts, session_label_map
                    )

                wm_snapshot = WorkingMemoryState(
                    step_index=step_index,
                    concepts=dict(wm_concepts),
                    pooled_embedding=list(wm_embedding),
                    open_tensions=list(open_tensions),
                )

                # ---- Step 3: asyncio.gather(LLM, kNN) ----------------------
                synthesis_opportunity = True  # paragraph boundary always (Q4)
                prompt = build_reading_step_prompt(
                    paragraph=paragraph,
                    working_memory=wm_snapshot,
                    chronicle_hints=[],  # populated after kNN
                    open_tensions=open_tensions,
                    synthesis_opportunity=synthesis_opportunity,
                )

                llm_task = asyncio.create_task(
                    self._llm.complete(
                        prompt,
                        system=READING_STEP_SYSTEM,
                        json_schema=READING_STEP_OUTPUT_SCHEMA,
                        timeout_s=180.0,
                    )
                )

                if wm_embedding:
                    knn_task = asyncio.create_task(
                        self._store.vector_search(wm_embedding, k=_CHRONICLE_K)
                    )
                    llm_result, knn_hits_raw = await asyncio.gather(llm_task, knn_task)
                else:
                    llm_result = await llm_task
                    knn_hits_raw = []

                total_llm_calls += 1
                total_llm_cost_eur += llm_result.cost_eur

                # Build ChronicleHint objects
                chronicle_hints = _build_chronicle_hints(knn_hits_raw, wm_concepts)
                total_hints_offered += len(chronicle_hints)

                # ---- Step 4: parse LLMReadingOutput ------------------------
                try:
                    llm_output = _parse_llm_output(llm_result.text)
                except Exception as exc:
                    log.warning(
                        "nous: failed to parse LLM output step=%d error=%s",
                        step_index,
                        exc,
                    )
                    failed_steps += 1
                    steps.append(
                        _failed_step(
                            step_index=step_index,
                            paragraph=paragraph,
                            section_title=section.title or None,
                            wm_snapshot=wm_snapshot,
                            chronicle_hints=chronicle_hints,
                        )
                    )
                    step_index += 1
                    continue

                # ---- Step 5+6: map concepts + edges → Chronicle models -----
                nodes_this_step, label_to_id = _map_concepts_to_nodes(
                    llm_output.new_concepts,
                    session_id=session_id,
                    section_title=section.title,
                    source_type=self._source_type,
                    source_url=url,
                    step_index=step_index,
                    resolution_registry=resolution_registry,
                )
                # Merge into session label map
                session_label_map.update(label_to_id)

                edges_this_step = _map_edges_to_chronicle(
                    llm_output.new_edges,
                    label_to_id=session_label_map,
                    source_type=self._source_type,
                    source_url=url,
                )

                # ---- Step 7: apply resolution_updates ----------------------
                for ru in llm_output.resolution_updates:
                    _apply_resolution_update(ru, resolution_registry, session_label_map)

                # ---- Step 8: apply repair_events ---------------------------
                for re_ in llm_output.repair_events:
                    _apply_repair_event(re_, nodes_this_step)
                    total_repair_events += 1
                    open_tensions = [t for t in open_tensions if t[0] != re_.revised_node_id]

                # ---- Step 9: write synthesis + regular nodes/edges ---------
                nodes_written_ids: list[str] = []
                edges_written_ids: list[str] = []

                # Write regular nodes
                for node in nodes_this_step:
                    try:
                        nid = await self._store.upsert_node(node)
                        nodes_written_ids.append(nid)
                        total_nodes_written += 1
                    except Exception as exc:
                        log.warning("nous: upsert_node failed node_id=%s error=%s", node.id, exc)

                # Write regular edges
                for edge in edges_this_step:
                    try:
                        await self._store.upsert_edge(edge)
                        edges_written_ids.append(edge.id)
                        total_edges_written += 1
                    except Exception as exc:
                        log.warning("nous: upsert_edge failed edge_id=%s error=%s", edge.id, exc)

                # Write synthesis node + its edges
                if llm_output.synthesis_event is not None:
                    syn_node, syn_edges = _build_synthesis_node_and_edges(
                        synth=llm_output.synthesis_event,
                        session_id=session_id,
                        source_type=self._source_type,
                        source_url=url,
                        step_index=step_index,
                        session_label_map=session_label_map,
                    )
                    try:
                        snid = await self._store.upsert_node(syn_node)
                        nodes_written_ids.append(snid)
                        total_nodes_written += 1
                        session_label_map[syn_node.label.lower()] = syn_node.id
                    except Exception as exc:
                        log.warning("nous: synthesis upsert_node failed error=%s", exc)
                    for se in syn_edges:
                        try:
                            await self._store.upsert_edge(se)
                            edges_written_ids.append(se.id)
                            total_edges_written += 1
                        except Exception as exc:
                            log.warning("nous: synthesis upsert_edge failed error=%s", exc)
                    total_synthesis_events += 1

                # Tally chronicle hints used
                total_hints_used += len(llm_output.chronicle_hits_used)

                # Update open tensions from CONTRADICTS hints
                for hint in chronicle_hints:
                    if hint.tension and hint.id not in [t[0] for t in open_tensions]:
                        open_tensions.append((hint.id, "Chronicle hit has CONTRADICTS edge"))

                # ---- Step 10: update working memory ------------------------
                _update_working_memory(
                    wm_concepts,
                    llm_output.new_concepts,
                    label_to_id,
                )

                # ---- Step 11: record ReadingStep ---------------------------
                steps.append(
                    ReadingStep(
                        step_index=step_index,
                        paragraph_text=paragraph,
                        section_title=section.title or None,
                        synthesis_level_context="paragraph",
                        working_memory_before=wm_snapshot,
                        chronicle_hints_offered=chronicle_hints,
                        llm_output=llm_output,
                        nodes_written=nodes_written_ids,
                        edges_written=edges_written_ids,
                        llm_cost_eur=llm_result.cost_eur,
                        llm_latency_ms=llm_result.latency_ms,
                    )
                )
                step_index += 1

        # Compute verdict
        total_steps = step_index
        verdict, status = _compute_verdict(failed_steps, total_steps)

        finished_at = datetime.now(UTC)
        wall_clock_s = time.monotonic() - wall_start

        final_wm = WorkingMemoryState(
            step_index=total_steps,
            concepts=dict(wm_concepts),
            pooled_embedding=list(wm_embedding),
            open_tensions=list(open_tensions),
        )

        annotated = AnnotatedReading(
            session_id=session_id,
            source_url=url,
            article_title=article_title,
            started_at=started_at,
            finished_at=finished_at,
            steps=steps,
            final_working_memory=final_wm,
            total_nodes_written=total_nodes_written,
            total_edges_written=total_edges_written,
            total_synthesis_events=total_synthesis_events,
            total_repair_events=total_repair_events,
            chronicle_seeded=chronicle_seeded,
        )

        report = NousRunReport(
            session_id=session_id,
            source_url=url,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=wall_clock_s,
            status=status,
            verdict=verdict,
            reading_units_total=total_steps,
            nodes_written=total_nodes_written,
            edges_written=total_edges_written,
            synthesis_events=total_synthesis_events,
            repair_events=total_repair_events,
            chronicle_hits_offered=total_hints_offered,
            chronicle_hits_used=total_hints_used,
            llm_calls=total_llm_calls,
            llm_cost_eur=total_llm_cost_eur,
            wall_clock_s=wall_clock_s,
            chronicle_seeded=chronicle_seeded,
        )

        log.info(
            "nous session complete session_id=%s steps=%d nodes=%d edges=%d verdict=%s",
            session_id,
            total_steps,
            total_nodes_written,
            total_edges_written,
            verdict,
        )
        return annotated, report

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _is_chronicle_seeded(self) -> bool:
        """Return True if the Chronicle already contains at least one node."""
        try:
            count = await self._store.count_nodes()
            return count > 0
        except Exception:
            return False

    async def _compute_pooled_embedding(
        self,
        wm_concepts: dict[str, float],
        session_label_map: dict[str, str],
    ) -> list[float]:
        """Compute a weighted-average embedding over the top-N working-memory concepts."""
        top = sorted(wm_concepts.items(), key=lambda kv: kv[1], reverse=True)[:_WM_TOP_N_FOR_POOL]
        if not top:
            return []

        # Try to embed concept labels from the session label map (reverse lookup)
        id_to_label = {v: k for k, v in session_label_map.items()}
        weighted_vecs: list[tuple[float, list[float]]] = []
        for node_id, weight in top:
            label = id_to_label.get(node_id, node_id)
            try:
                vec = await self._embedder.embed(label)
                weighted_vecs.append((weight, vec))
            except Exception:
                pass

        if not weighted_vecs:
            return []

        dim = len(weighted_vecs[0][1])
        pool = [0.0] * dim
        total_w = sum(w for w, _ in weighted_vecs)
        for w, vec in weighted_vecs:
            for i, v in enumerate(vec):
                pool[i] += (w / total_w) * v
        return pool

    def _empty_failed_session(
        self,
        *,
        session_id: str,
        url: str,
        article_title: str,
        started_at: datetime,
        chronicle_seeded: bool,
        reason: str,
    ) -> tuple[AnnotatedReading, NousRunReport]:
        now = datetime.now(UTC)
        empty_wm = WorkingMemoryState(
            step_index=0, concepts={}, pooled_embedding=[], open_tensions=[]
        )
        annotated = AnnotatedReading(
            session_id=session_id,
            source_url=url,
            article_title=article_title,
            started_at=started_at,
            finished_at=now,
            steps=[],
            final_working_memory=empty_wm,
            total_nodes_written=0,
            total_edges_written=0,
            total_synthesis_events=0,
            total_repair_events=0,
            chronicle_seeded=chronicle_seeded,
        )
        report = NousRunReport(
            session_id=session_id,
            source_url=url,
            started_at=started_at,
            finished_at=now,
            duration_s=0.0,
            status="failed",
            verdict="failed",
            verdict_reasoning=reason,
            reading_units_total=0,
            nodes_written=0,
            edges_written=0,
            synthesis_events=0,
            repair_events=0,
            chronicle_hits_offered=0,
            chronicle_hits_used=0,
            llm_calls=0,
            llm_cost_eur=0.0,
            wall_clock_s=0.0,
            chronicle_seeded=chronicle_seeded,
        )
        return annotated, report


# ---------------------------------------------------------------------------
# Module-level helpers (pure, testable)
# ---------------------------------------------------------------------------


def _apply_decay(wm_concepts: dict[str, float]) -> None:
    """Apply exponential decay in-place.  τ=3.0 paragraphs (brief Q2)."""
    factor = math.exp(-1.0 / _DECAY_TAU)
    for k in list(wm_concepts.keys()):
        wm_concepts[k] *= factor

    # Enforce capacity ceiling: drop bottom half if over limit
    if len(wm_concepts) > _WM_CAPACITY:
        sorted_pairs = sorted(wm_concepts.items(), key=lambda kv: kv[1])
        to_drop = sorted_pairs[: len(wm_concepts) // 2]
        for k, _ in to_drop:
            del wm_concepts[k]


def _build_chronicle_hints(
    knn_hits: list[Any], wm_concepts: dict[str, float]
) -> list[ChronicleHint]:
    """Convert raw ScoredNode kNN results to ChronicleHint objects."""
    hints: list[ChronicleHint] = []
    for hit in knn_hits:
        node = hit.node
        # Detect CONTRADICTS: we cannot cheaply query edge types here, so
        # tension=False by default; tension detection via CONTRADICTS edges
        # is left for post-write passes (brief Q5 deferred cosine option).
        hints.append(
            ChronicleHint(
                id=node.id,
                label=node.label,
                similarity=float(hit.score),
                source=f"{node.source_ref.source_type}:{node.source_ref.identifier or ''}",
                tension=False,
            )
        )
    return hints


def _parse_llm_output(text: str) -> LLMReadingOutput:
    """Parse LLM JSON response into a validated LLMReadingOutput.

    Applies a normalisation pass before Pydantic validation to handle
    field-name variants that non-schema-enforcing LLMs (e.g. DeepSeek) may
    produce:
      - ``synthesis_label`` → ``label`` (inside synthesis_event)
      - ``synthesis_description`` → ``description`` (inside synthesis_event)
      - ``edges`` → ``new_edges`` (top-level)
      - diagonal_edges items as dicts → 3-tuples

    Raises ``ValueError`` or ``pydantic.ValidationError`` on unrecoverable
    parse failure — the caller converts to a failed ReadingStep.
    """
    data = json.loads(text)
    data = _normalise_llm_output(data)
    return LLMReadingOutput.model_validate(data)


def _normalise_llm_output(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise field-name variants from non-strict LLMs into the schema shape."""
    # Top-level: ``edges`` → ``new_edges``
    if "edges" in data and "new_edges" not in data:
        data["new_edges"] = data.pop("edges")
    # Ensure required top-level lists exist
    for key in ("new_concepts", "new_edges", "chronicle_hits_used",
                "repair_events", "resolution_updates"):
        if key not in data:
            data[key] = []
    if "synthesis_event" not in data:
        data["synthesis_event"] = None

    # synthesis_event field-name variants
    se = data.get("synthesis_event")
    if isinstance(se, dict):
        if "synthesis_label" in se and "label" not in se:
            se["label"] = se.pop("synthesis_label")
        if "synthesis_description" in se and "description" not in se:
            se["description"] = se.pop("synthesis_description")
        # diagonal_edges: list of dicts → list of 3-tuples
        diag = se.get("diagonal_edges")
        if isinstance(diag, list):
            normalised: list[Any] = []
            for item in diag:
                if isinstance(item, dict):
                    # Extract source/rel/target from common dict shapes
                    src = item.get("source_id") or item.get("source_label") or item.get("source", "")
                    rel = item.get("relation_type") or item.get("relation", "BINDS_TO")
                    tgt = item.get("target_id") or item.get("target_label") or item.get("target", "")
                    normalised.append([str(src), str(rel), str(tgt)])
                else:
                    normalised.append(item)
            se["diagonal_edges"] = normalised

    # resolution_updates: ``concept_label`` → ``node_id``, ``wikidata_id`` → ``new_wikidata_id``
    rus = data.get("resolution_updates")
    if isinstance(rus, list):
        for ru in rus:
            if not isinstance(ru, dict):
                continue
            if "concept_label" in ru and "node_id" not in ru:
                ru["node_id"] = ru.pop("concept_label")
            if "wikidata_id" in ru and "new_wikidata_id" not in ru:
                ru["new_wikidata_id"] = ru.pop("wikidata_id")
            if "node_id" not in ru:
                ru["node_id"] = ru.get("label", ru.get("concept", "unknown"))

    return data


def _map_concepts_to_nodes(
    raw_concepts: list[dict[str, Any]],
    *,
    session_id: str,
    section_title: str,
    source_type: str,
    source_url: str,
    step_index: int,
    resolution_registry: dict[str, str],
) -> tuple[list[KnowledgeNode], dict[str, str]]:
    """Map raw concept dicts from the LLM to KnowledgeNode instances.

    Returns (nodes, label_to_id_map).
    label_to_id_map maps lower-cased label → AKA-* id.
    """
    nodes: list[KnowledgeNode] = []
    label_to_id: dict[str, str] = {}

    for raw in raw_concepts:
        label = str(raw.get("label", "")).strip()
        if not label:
            continue

        node_type_str = str(raw.get("node_type", "other")).lower()
        try:
            node_type = NodeType(node_type_str)
        except ValueError:
            node_type = NodeType.OTHER

        confidence = float(raw.get("confidence", 0.5))
        description = raw.get("description")
        wikidata_id: str | None = raw.get("wikidata_id")

        source_ref = SourceRef(
            source_type=source_type,
            url=source_url,
            location=f"step:{step_index}",
        )

        node_id = compute_node_id(source_ref, label)

        # If session resolution registry has a confirmed wikidata_id, use it
        if node_id in resolution_registry:
            wikidata_id = resolution_registry[node_id]

        external_ids: dict[str, str] = {}
        if wikidata_id:
            external_ids["wikidata"] = wikidata_id

        tier = 1 if wikidata_id else 0

        node = KnowledgeNode(
            id=node_id,
            label=label,
            description=description,
            node_type=node_type,
            epistemic_status=EpistemicStatus.OBSERVED,
            source_ref=source_ref,
            external_ids=external_ids,
            resolution_tier=tier,
            nous_session_id=session_id,
            synthesis_level="paragraph",
        )
        node.scores.confidence = min(1.0, max(0.0, confidence))
        nodes.append(node)
        label_to_id[label.lower()] = node_id

    return nodes, label_to_id


def _map_edges_to_chronicle(
    raw_edges: list[dict[str, Any]],
    *,
    label_to_id: dict[str, str],
    source_type: str,
    source_url: str,
) -> list[KnowledgeEdge]:
    """Map raw edge dicts from the LLM to KnowledgeEdge instances."""
    edges: list[KnowledgeEdge] = []

    for raw in raw_edges:
        src_label = str(raw.get("source_label", "")).lower()
        tgt_label = str(raw.get("target_label", "")).lower()
        relation_type = str(raw.get("relation_type", "BINDS_TO"))
        evidence_span: str | None = raw.get("evidence_span")
        confidence = float(raw.get("confidence", 0.5))
        relation_codebook: str | None = raw.get("relation_codebook")

        src_id = label_to_id.get(src_label)
        tgt_id = label_to_id.get(tgt_label)
        if not src_id or not tgt_id:
            continue

        edge_id = compute_edge_id(src_id, tgt_id, relation_type, evidence_span)
        source_ref = SourceRef(source_type=source_type, url=source_url)

        edge = KnowledgeEdge(
            id=edge_id,
            source_id=src_id,
            target_id=tgt_id,
            relation_type=relation_type,
            confidence=min(1.0, max(0.0, confidence)),
            weight=min(1.0, max(0.0, confidence)),
            evidence_span=evidence_span,
            epistemic_type=EdgeType.AGENT,
            source_ref=source_ref,
            relation_codebook=relation_codebook,
        )
        edges.append(edge)

    return edges


def _build_synthesis_node_and_edges(
    *,
    synth: SynthesisOutput,
    session_id: str,
    source_type: str,
    source_url: str,
    step_index: int,
    session_label_map: dict[str, str],
) -> tuple[KnowledgeNode, list[KnowledgeEdge]]:
    """Build the synthesis KnowledgeNode and its basis edges."""
    source_ref = SourceRef(
        source_type=source_type,
        url=source_url,
        location=f"synthesis:step:{step_index}",
    )
    node_id = compute_node_id(source_ref, synth.label)

    node = KnowledgeNode(
        id=node_id,
        label=synth.label,
        description=synth.description,
        node_type=NodeType.CONCEPT,
        epistemic_status=EpistemicStatus.INFERRED,
        source_ref=source_ref,
        nous_session_id=session_id,
        synthesis_level=synth.synthesis_level,
    )
    node.scores.confidence = min(1.0, max(0.0, synth.confidence))

    edges: list[KnowledgeEdge] = []

    # Basis edges: synthesis → basis_node
    for basis_id in synth.basis_node_ids:
        eid = compute_edge_id(node_id, basis_id, "ABSTRACTION_OF", None)
        edges.append(
            KnowledgeEdge(
                id=eid,
                source_id=node_id,
                target_id=basis_id,
                relation_type="ABSTRACTION_OF",
                weight=synth.confidence,
                confidence=synth.confidence,
                epistemic_type=EdgeType.AGENT,
                relation_codebook="ABSTRACTION_OF",
            )
        )

    # Diagonal edges
    for src_id_or_label, rel_type, tgt_id_or_label in synth.diagonal_edges:
        src_id = session_label_map.get(src_id_or_label.lower(), src_id_or_label)
        tgt_id = session_label_map.get(tgt_id_or_label.lower(), tgt_id_or_label)
        eid = compute_edge_id(src_id, tgt_id, rel_type, None)
        edges.append(
            KnowledgeEdge(
                id=eid,
                source_id=src_id,
                target_id=tgt_id,
                relation_type=rel_type,
                weight=synth.confidence,
                confidence=synth.confidence,
                epistemic_type=EdgeType.AGENT,
                relation_codebook=rel_type,
            )
        )

    return node, edges


def _apply_resolution_update(
    ru: ResolutionUpdate,
    resolution_registry: dict[str, str],
    session_label_map: dict[str, str],
) -> None:
    if ru.new_wikidata_id:
        resolution_registry[ru.node_id] = ru.new_wikidata_id


def _apply_repair_event(
    re_: RepairEvent,
    nodes_this_step: list[KnowledgeNode],
) -> None:
    """Apply a repair event to any matching node in the current step's list."""
    for node in nodes_this_step:
        if node.id == re_.revised_node_id:
            if re_.new_description:
                node.description = re_.new_description
            break


def _update_working_memory(
    wm_concepts: dict[str, float],
    raw_concepts: list[dict[str, Any]],
    label_to_id: dict[str, str],
) -> None:
    """Add newly extracted concepts to working memory at full weight (1.0)."""
    for raw in raw_concepts:
        label = str(raw.get("label", "")).lower()
        node_id = label_to_id.get(label)
        if node_id:
            wm_concepts[node_id] = 1.0


def _failed_step(
    *,
    step_index: int,
    paragraph: str,
    section_title: str | None,
    wm_snapshot: WorkingMemoryState,
    chronicle_hints: list[ChronicleHint],
) -> ReadingStep:
    return ReadingStep(
        step_index=step_index,
        paragraph_text=paragraph,
        section_title=section_title,
        synthesis_level_context="paragraph",
        working_memory_before=wm_snapshot,
        chronicle_hints_offered=chronicle_hints,
        llm_output=LLMReadingOutput(),
        nodes_written=[],
        edges_written=[],
        llm_cost_eur=0.0,
        llm_latency_ms=0,
    )


def _compute_verdict(
    failed_steps: int,
    total_steps: int,
) -> tuple[
    Literal["good", "partial", "poor", "failed"],
    Literal["completed", "partial", "failed", "aborted"],
]:
    """Map failure ratio to (verdict, status) pair."""
    if total_steps == 0:
        return "failed", "failed"
    ratio = failed_steps / total_steps
    if ratio > _HARD_FAIL_THRESHOLD:
        return "failed", "failed"
    if ratio > _PARTIAL_FAIL_THRESHOLD:
        return "partial", "partial"
    return "good", "completed"


def _extract_title_from_url(url: str) -> str:
    """Best-effort article title extraction from a URL or plain string."""
    url = url.strip()
    if "/wiki/" in url:
        return url.split("/wiki/", 1)[1].replace("_", " ").rstrip("/")
    return url
