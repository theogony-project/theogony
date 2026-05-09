"""
Kadmos v2 — KadmosReader: the cognitive reading loop.

Architecture (TARGET_ARCHITECTURE.md / kadmos_v2_brief.md):

  KadmosReader.read(url) → (AnnotatedReading, KadmosRunReport)

The loop per reading unit (paragraph by default):

  Schritt A — Hypothesis generation (parallel, no LLM):
    1. kNN similarity search over local LanceDB session net
    2. Graph traversal from active concept ids

  Schritt B — LLM reading step:
    asyncio.gather(LLM call, kNN search) — Q8 from brief

  Schritt C — Apply LLM output to ReadingState:
    - Add new concepts + their embeddings
    - Add new edges + their embeddings (Q7: embed the description sentence)
    - Apply revisions (update/split/merge/invalidate)
    - Synthesise if LLM requested it
    - Decay working memory activation
    - Compress if over capacity (Q2)

  Schritt D — Write to LanceDB session net

Post-loop:
  - Build AnnotatedReading + KadmosRunReport
  (Implicit kNN edges are not produced here; reserve similarity wiring for
  Chronik mesh integration, not the Kadmos translation layer.)

Failure discipline (AGENTS.md §3 / BUILD_DOCTRINE.md):
  - LLM parse failure on one step → log, mark parse_failed=True, continue
  - > 20% step failures → verdict="partial"
  - > 50% step failures → verdict="failed"
  - Never raises; always returns a report
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from theogony.config.logging import get_logger
from theogony.kadmos.model import (
    ActiveConcept,
    ActiveEdge,
    AnnotatedReading,
    LLMReadingOutput,
    LLMSynthesisOutput,
    ReadingHypotheses,
    ReadingState,
    ReadingStep,
    RevisionRecord,
    RevisionRequest,
    SynthesisNode,
)
from theogony.kadmos.prompts import (
    READING_STEP_OUTPUT_SCHEMA,
    READING_STEP_SYSTEM,
    build_reading_step_prompt,
)
from theogony.kadmos.reading_state import (
    WM_DECAY_FACTOR,
    ReadingStateStore,
    new_concept_id,
    new_edge_id,
    new_synthesis_id,
)
from theogony.kadmos.wikipedia_parser import WikiSection, fetch_article_structured
from theogony.reporting.models import KadmosRunReport

if TYPE_CHECKING:
    from theogony.agents.llm import LLMProvider
    from theogony.extraction.embedding import EmbeddingProvider

log = get_logger("kadmos.reader")

# Failure thresholds
_PARTIAL_THRESHOLD = 0.20
_HARD_FAIL_THRESHOLD = 0.50

# Large structured reading updates (many concepts/edges) need a generous
# completion budget so providers (especially Gemini) do not truncate JSON.
_READING_MAX_OUTPUT_TOKENS = 16384
_SYNTHESIS_MAX_OUTPUT_TOKENS = 8192


class KadmosReader:
    """Cognitive reading agent — reads Wikipedia articles with working memory.

    Parameters
    ----------
    llm:
        LLM provider for reading-step structured output.
    embedder:
        Embedding provider for concepts, edges, and synthesis nodes.
    max_sections:
        If set, process at most this many sections.
    db_path:
        Directory for the LanceDB session database.  None = tmp dir.
    source_type:
        Source type string recorded in AnnotatedReading.
    """

    def __init__(
        self,
        llm: LLMProvider,
        embedder: EmbeddingProvider,
        *,
        max_sections: int | None = None,
        db_path: str | None = None,
        source_type: str = "wikipedia",
    ) -> None:
        self._llm = llm
        self._embedder = embedder
        self._max_sections = max_sections
        self._db_path = db_path
        self._source_type = source_type

    async def read(self, url: str) -> tuple[AnnotatedReading, KadmosRunReport]:
        """Run a full cognitive reading session on the article at ``url``.

        Returns (AnnotatedReading, KadmosRunReport).  Never raises.
        """
        session_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        wall_start = time.monotonic()

        log.info("kadmos session started session_id=%s url=%s", session_id, url)

        article_title = _title_from_url(url)
        sections: list[WikiSection] = []
        try:
            sections = await fetch_article_structured(url)
            if sections:
                article_title = _title_from_url(url)
        except Exception as exc:
            log.warning("kadmos: fetch failed url=%s error=%s", url, exc)
            return self._empty_failed(
                session_id=session_id,
                url=url,
                article_title=article_title,
                started_at=started_at,
                reason=f"fetch failed: {exc}",
            )

        if self._max_sections is not None:
            sections = sections[: self._max_sections]

        # Open LanceDB session store
        store = ReadingStateStore(
            session_id=session_id,
            embedding_dim=self._embedder.dim,
            db_path=self._db_path,
        )

        # Live working memory
        state = ReadingState(session_id=session_id)

        steps: list[ReadingStep] = []
        failed_steps = 0
        total_llm_cost = 0.0
        total_llm_calls = 0

        for section in sections:
            # compress at section boundary only if WM is very full
            if len(state.active_concepts) > 100:
                await self._compress_working_memory(state, store, step=state.current_step)

            for paragraph in section.paragraphs:
                # ---- Schritt A: hypothesis generation (parallel, no LLM) ----
                hypotheses = await self._generate_hypotheses(state, store)

                wm_size_before = len(state.active_concepts)

                # ---- Schritt B: LLM reading step + kNN search (parallel) ----
                prompt = build_reading_step_prompt(
                    text=paragraph,
                    state=state,
                    hypotheses=hypotheses,
                    section_title=section.title or None,
                )

                # kNN for the next step is already computed in hypotheses;
                # we gather LLM call concurrently with a fresh kNN using
                # the current pooled embedding.
                pooled_emb = _pool_active_embeddings(state)

                llm_task = asyncio.create_task(
                    self._llm.complete(
                        prompt,
                        system=READING_STEP_SYSTEM,
                        json_schema=READING_STEP_OUTPUT_SCHEMA,
                        max_output_tokens=_READING_MAX_OUTPUT_TOKENS,
                        timeout_s=180.0,
                    )
                )

                if pooled_emb and int(store._concepts_tbl.count_rows()) > 0:
                    knn_task = asyncio.create_task(
                        asyncio.to_thread(store.similarity_candidates, pooled_emb, 5)
                    )
                    llm_result, _extra_knn = await asyncio.gather(llm_task, knn_task)
                else:
                    llm_result = await llm_task

                total_llm_calls += 1
                total_llm_cost += llm_result.cost_eur

                # ---- Parse LLM output ----
                try:
                    llm_output = _parse_llm_output(llm_result.text)
                except Exception as exc:
                    log.warning(
                        "kadmos: LLM parse failed step=%d error=%s", state.current_step, exc
                    )
                    failed_steps += 1
                    steps.append(
                        ReadingStep(
                            step_index=state.current_step,
                            granularity=state.current_granularity,
                            text=paragraph,
                            section_title=section.title or None,
                            hypotheses=hypotheses,
                            llm_output=LLMReadingOutput(),
                            wm_size_before=wm_size_before,
                            wm_size_after=wm_size_before,
                            llm_cost_eur=llm_result.cost_eur,
                            llm_latency_ms=llm_result.latency_ms,
                            parse_failed=True,
                        )
                    )
                    state.current_step += 1
                    continue

                # ---- Schritt C: Apply LLM output to ReadingState ----
                (
                    added_concepts,
                    added_edges,
                    revised_ids,
                    synthesis_id,
                ) = await self._apply_llm_output(
                    llm_output=llm_output,
                    state=state,
                    store=store,
                    paragraph=paragraph,
                    step=state.current_step,
                )

                # Decay all activations (except newly added ones)
                _decay_working_memory(state, added_concept_ids=set(added_concepts))

                # Q2: compress if over capacity
                if len(state.active_concepts) > 200:
                    await self._compress_working_memory(state, store, step=state.current_step)

                # Update granularity for next step
                state.current_granularity = llm_output.next_granularity

                # Update open tensions
                state.open_tensions = list(llm_output.open_tensions)

                # ---- Forced paragraph synthesis ----
                if len(state.active_concepts) >= 3:
                    try:
                        syn_cost = await self._force_synthesis(
                            state,
                            store,
                            synthesis_level="paragraph",
                            section_title=section.title or None,
                        )
                        total_llm_cost += syn_cost
                        total_llm_calls += 1
                    except Exception as exc:
                        log.warning("kadmos: forced paragraph synthesis failed: %s", exc)

                wm_size_after = len(state.active_concepts)

                steps.append(
                    ReadingStep(
                        step_index=state.current_step,
                        granularity=state.current_granularity,
                        text=paragraph,
                        section_title=section.title or None,
                        hypotheses=hypotheses,
                        llm_output=llm_output,
                        concepts_added=added_concepts,
                        edges_added=added_edges,
                        revisions_applied=revised_ids,
                        synthesis_created=synthesis_id,
                        wm_size_before=wm_size_before,
                        wm_size_after=wm_size_after,
                        llm_cost_eur=llm_result.cost_eur,
                        llm_latency_ms=llm_result.latency_ms,
                    )
                )
                state.current_step += 1

            # ---- Forced section synthesis ----
            if len(state.active_concepts) >= 5:
                try:
                    syn_cost = await self._force_synthesis(
                        state,
                        store,
                        synthesis_level="section",
                        section_title=section.title or None,
                    )
                    total_llm_cost += syn_cost
                    total_llm_calls += 1
                except Exception as exc:
                    log.warning("kadmos: forced section synthesis failed: %s", exc)

        # ---- Article synthesis ----
        if len(state.active_concepts) >= 10:
            try:
                syn_cost = await self._force_synthesis(
                    state,
                    store,
                    synthesis_level="article",
                    section_title=None,
                )
                total_llm_cost += syn_cost
                total_llm_calls += 1
            except Exception as exc:
                log.warning("kadmos: forced article synthesis failed: %s", exc)

        # ---- Build output ----
        total_steps = len(steps)
        verdict, status = _compute_verdict(failed_steps, total_steps)
        finished_at = datetime.now(UTC)
        wall_clock_s = time.monotonic() - wall_start

        total_revisions = sum(len(s.revisions_applied) for s in steps)
        total_syntheses = sum(1 for s in steps if s.synthesis_created)

        annotated = AnnotatedReading(
            session_id=session_id,
            source_url=url,
            article_title=article_title,
            started_at=started_at,
            finished_at=finished_at,
            steps=steps,
            final_active_concepts=list(state.active_concepts.values()),
            final_syntheses=list(state.syntheses.values()),
            total_concepts=store.concept_count(),
            total_edges=store.edge_count(implicit=False),
            total_syntheses=total_syntheses,
            total_revisions=total_revisions,
            total_llm_calls=total_llm_calls,
            total_llm_cost_eur=total_llm_cost,
            reading_units_total=total_steps,
        )

        report = KadmosRunReport(
            session_id=session_id,
            source_url=url,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=wall_clock_s,
            status=status,
            verdict=verdict,
            reading_units_total=total_steps,
            total_concepts=annotated.total_concepts,
            total_edges=annotated.total_edges,
            total_edges_implicit=0,
            total_syntheses=total_syntheses,
            total_revisions=total_revisions,
            total_llm_calls=total_llm_calls,
            total_llm_cost_eur=total_llm_cost,
            wall_clock_s=wall_clock_s,
            lancedb_path=str(store.db_path),
        )

        log.info(
            "kadmos session complete session_id=%s steps=%d concepts=%d edges=%d verdict=%s",
            session_id,
            total_steps,
            annotated.total_concepts,
            annotated.total_edges,
            verdict,
        )
        return annotated, report

    # -------------------------------------------------------------------------
    # Schritt A: hypothesis generation
    # -------------------------------------------------------------------------

    async def _generate_hypotheses(
        self, state: ReadingState, store: ReadingStateStore
    ) -> ReadingHypotheses:
        """Run kNN + traversal in parallel (both cheap, no LLM)."""
        if not state.active_concepts:
            return ReadingHypotheses()

        pooled = _pool_active_embeddings(state)
        active_ids = list(state.active_concepts.keys())

        if pooled:
            sim_task = asyncio.create_task(
                asyncio.to_thread(store.similarity_candidates, pooled, 5)
            )
            trav_task = asyncio.create_task(
                asyncio.to_thread(store.traversal_candidates, active_ids, 3)
            )
            sim_candidates, trav_candidates = await asyncio.gather(sim_task, trav_task)
        else:
            sim_candidates = store.similarity_candidates(pooled or [0.0] * self._embedder.dim, 5)
            trav_candidates = store.traversal_candidates(active_ids, 3)

        # Exclude concepts already in active working memory
        active_set = set(active_ids)
        sim_candidates = [c for c in sim_candidates if c.concept_id not in active_set]
        trav_candidates = [c for c in trav_candidates if c.concept_id not in active_set]

        return ReadingHypotheses(
            similarity_candidates=sim_candidates,
            traversal_candidates=trav_candidates,
        )

    # -------------------------------------------------------------------------
    # Schritt C: apply LLM output
    # -------------------------------------------------------------------------

    async def _apply_llm_output(
        self,
        llm_output: LLMReadingOutput,
        state: ReadingState,
        store: ReadingStateStore,
        paragraph: str,
        step: int,
    ) -> tuple[list[str], list[str], list[str], str | None]:
        """Apply all LLM output to the ReadingState and LanceDB store.

        Returns (added_concept_ids, added_edge_ids, revised_ids, synthesis_id).
        """
        added_concepts: list[str] = []
        added_edges: list[str] = []
        revised_ids: list[str] = []
        synthesis_id: str | None = None

        # Build a label → concept_id lookup from current WM
        label_map = {c.label.lower(): c.id for c in state.active_concepts.values()}

        # ---- New concepts ----
        embed_tasks = [
            self._embedder.embed(nc.label + (" " + nc.description if nc.description else ""))
            for nc in llm_output.new_concepts
        ]
        if embed_tasks:
            embeddings = await asyncio.gather(*embed_tasks)
        else:
            embeddings = []

        for nc, emb in zip(llm_output.new_concepts, embeddings, strict=True):
            cid = new_concept_id()
            concept = ActiveConcept(
                id=cid,
                label=nc.label,
                description=nc.description,
                activation=1.0,
                step_created=step,
                source_passage=nc.source_passage or paragraph[:120],
                wikidata_candidate=nc.wikidata_candidate,
            )
            state.active_concepts[cid] = concept
            label_map[nc.label.lower()] = cid
            try:
                store.add_concept(concept, list(emb), step=step)
                added_concepts.append(cid)
            except Exception as exc:
                log.warning("kadmos: add_concept failed %s", exc)

        # ---- New edges ----
        for ne in llm_output.new_connections:
            src_id = label_map.get(ne.source_label.lower())
            tgt_id = label_map.get(ne.target_label.lower())
            if not src_id or not tgt_id:
                continue
            eid = new_edge_id()
            edge = ActiveEdge(
                id=eid,
                source_id=src_id,
                target_id=tgt_id,
                source_label=ne.source_label,
                target_label=ne.target_label,
                relation_description=ne.relation_description,
                weight=ne.weight,
                step_created=step,
            )
            state.active_edges[eid] = edge
            try:
                edge_emb = await self._embedder.embed(ne.relation_description)
                store.add_edge(edge, list(edge_emb), step=step)
                added_edges.append(eid)
            except Exception as exc:
                log.warning("kadmos: add_edge failed %s", exc)

        # ---- Revisions ----
        for rev in llm_output.revisions:
            revised = await self._apply_revision(rev, state, store, step=step)
            if revised:
                revised_ids.append(rev.target_concept_id)

        # ---- Synthesis ----
        if llm_output.synthesis is not None:
            synthesis_id = await self._apply_synthesis(
                llm_output.synthesis, state, store, label_map, step=step
            )

        return added_concepts, added_edges, revised_ids, synthesis_id

    async def _apply_revision(
        self,
        rev: RevisionRequest,
        state: ReadingState,
        store: ReadingStateStore,
        step: int,
    ) -> bool:
        """Apply one revision to working memory and store. Returns True if applied."""
        concept = state.active_concepts.get(rev.target_concept_id)
        if concept is None:
            # Also check syntheses
            synth = state.syntheses.get(rev.target_concept_id)
            if synth is None:
                log.debug(
                    "kadmos: revision target %s not in WM, skipping",
                    rev.target_concept_id,
                )
                return False
            # Simple description update on synthesis
            if rev.new_understanding:
                synth.description = rev.new_understanding
            return True

        rr = RevisionRecord(
            step_index=step,
            revision_type=rev.revision_type,
            reason=rev.reason,
            triggering_passage=rev.triggering_passage,
            old_understanding=rev.old_understanding or concept.description,
            new_understanding=rev.new_understanding,
        )
        concept.revision_history.append(rr)

        if rev.revision_type == "invalidate":
            concept.invalidated = True
            del state.active_concepts[concept.id]
        elif rev.revision_type == "update":
            if rev.new_understanding:
                concept.description = rev.new_understanding
        elif rev.revision_type == "split":
            # Create two new concepts from the split
            concept.invalidated = True
            del state.active_concepts[concept.id]
            for new_def in rev.split_into or []:
                new_label = str(new_def.get("label", ""))
                if not new_label:
                    continue
                new_cid = new_concept_id()
                new_c = ActiveConcept(
                    id=new_cid,
                    label=new_label,
                    description=str(new_def.get("description", "")),
                    activation=concept.activation,
                    step_created=step,
                )
                state.active_concepts[new_cid] = new_c
                try:
                    emb = await self._embedder.embed(new_label)
                    store.add_concept(new_c, list(emb), step=step)
                except Exception as exc:
                    log.warning("kadmos: split new concept embed failed %s", exc)
        elif rev.revision_type == "merge":
            other_id = rev.merge_with_id
            if other_id and other_id in state.active_concepts:
                other = state.active_concepts[other_id]
                merged_label = f"{concept.label} / {other.label}"
                merged_cid = new_concept_id()
                merged = ActiveConcept(
                    id=merged_cid,
                    label=merged_label,
                    description=rev.new_understanding or concept.description,
                    activation=max(concept.activation, other.activation),
                    step_created=step,
                )
                concept.invalidated = True
                other.invalidated = True
                del state.active_concepts[concept.id]
                del state.active_concepts[other_id]
                state.active_concepts[merged_cid] = merged
                try:
                    emb = await self._embedder.embed(merged_label)
                    store.add_concept(merged, list(emb), step=step)
                except Exception as exc:
                    log.warning("kadmos: merge concept embed failed %s", exc)

        # Write revision to store
        try:
            emb = await self._embedder.embed(concept.label)
            store.revise_concept(concept, list(emb), rr, step=step)
        except Exception as exc:
            log.warning("kadmos: revise_concept store write failed %s", exc)

        return True

    async def _apply_synthesis(
        self,
        synth: LLMSynthesisOutput,
        state: ReadingState,
        store: ReadingStateStore,
        label_map: dict[str, str],
        step: int,
    ) -> str | None:
        sid = new_synthesis_id()
        synthesis = SynthesisNode(
            id=sid,
            label=synth.label,
            description=synth.description,
            basis_concept_ids=synth.basis_concept_ids,
            synthesis_level=synth.synthesis_level,
            step_created=step,
            confidence=synth.confidence,
        )
        state.syntheses[sid] = synthesis
        try:
            emb = await self._embedder.embed(synth.label + " " + synth.description)
            store.add_synthesis_as_concept(synthesis, list(emb), step=step)
        except Exception as exc:
            log.warning("kadmos: synthesis embed/write failed %s", exc)
        return sid

    async def _force_synthesis(
        self,
        state: ReadingState,
        store: ReadingStateStore,
        synthesis_level: str,
        section_title: str | None,
    ) -> float:
        """Force a synthesis LLM call and write the result.

        Returns the LLM cost in EUR.
        Called after every paragraph (level=paragraph),
        after every section (level=section), and at article end (level=article).
        """
        from theogony.kadmos.prompts import (
            SYNTHESIS_STEP_OUTPUT_SCHEMA,
            SYNTHESIS_STEP_SYSTEM,
            build_forced_synthesis_prompt,
        )

        prompt = build_forced_synthesis_prompt(state, synthesis_level, section_title)
        result = await self._llm.complete(
            prompt,
            system=SYNTHESIS_STEP_SYSTEM,
            json_schema=SYNTHESIS_STEP_OUTPUT_SCHEMA,
            max_output_tokens=_SYNTHESIS_MAX_OUTPUT_TOKENS,
            timeout_s=60.0,
        )

        try:
            data = json.loads(result.text)
            # Normalise field aliases
            if "level" in data and "synthesis_level" not in data:
                data["synthesis_level"] = data.pop("level")
            if "synthesis_level" not in data:
                data["synthesis_level"] = synthesis_level
            if "label" not in data:
                data["label"] = section_title or f"{synthesis_level} synthesis"
            if "description" not in data:
                data["description"] = data.get("summary", "")
            if "basis_concept_ids" not in data:
                data["basis_concept_ids"] = data.get("concepts", [])
            if "confidence" not in data:
                data["confidence"] = 0.75

            synth = LLMSynthesisOutput(**data)
            # Use empty label_map — basis_concept_ids are already concept IDs
            await self._apply_synthesis(synth, state, store, label_map={}, step=state.current_step)
            log.debug("kadmos: forced %s synthesis: %s", synthesis_level, synth.label)
        except Exception as exc:
            log.warning(
                "kadmos: forced synthesis parse failed level=%s error=%s",
                synthesis_level,
                exc,
            )

        return result.cost_eur

    async def _compress_working_memory(
        self, state: ReadingState, store: ReadingStateStore, step: int
    ) -> None:
        """Compress the bottom half of WM into a compression synthesis."""
        if len(state.active_concepts) < 10:
            return

        sorted_concepts = sorted(state.active_concepts.values(), key=lambda c: c.activation)
        to_compress = sorted_concepts[: len(sorted_concepts) // 2]
        if not to_compress:
            return

        labels = [c.label for c in to_compress]
        compression_label = f"Compression at step {step}"
        compression_desc = "Compressed: " + ", ".join(labels[:10])

        sid = new_synthesis_id()
        synthesis = SynthesisNode(
            id=sid,
            label=compression_label,
            description=compression_desc,
            basis_concept_ids=[c.id for c in to_compress],
            synthesis_level="paragraph",
            step_created=step,
            confidence=0.5,
        )
        state.syntheses[sid] = synthesis

        try:
            emb = await self._embedder.embed(compression_desc)
            store.add_synthesis_as_concept(synthesis, list(emb), step=step)
        except Exception as exc:
            log.warning("kadmos: compression synthesis embed failed %s", exc)

        for c in to_compress:
            del state.active_concepts[c.id]

        log.debug("kadmos: compressed %d concepts into synthesis", len(to_compress))

    def _empty_failed(
        self,
        *,
        session_id: str,
        url: str,
        article_title: str,
        started_at: datetime,
        reason: str,
    ) -> tuple[AnnotatedReading, KadmosRunReport]:
        now = datetime.now(UTC)
        annotated = AnnotatedReading(
            session_id=session_id,
            source_url=url,
            article_title=article_title,
            started_at=started_at,
            finished_at=now,
            total_concepts=0,
            total_edges=0,
            total_syntheses=0,
            total_revisions=0,
            total_llm_calls=0,
            total_llm_cost_eur=0.0,
            reading_units_total=0,
        )
        report = KadmosRunReport(
            session_id=session_id,
            source_url=url,
            started_at=started_at,
            finished_at=now,
            duration_s=0.0,
            status="failed",
            verdict="failed",
            verdict_reasoning=reason,
            reading_units_total=0,
            total_concepts=0,
            total_edges=0,
            total_edges_implicit=0,
            total_syntheses=0,
            total_revisions=0,
            total_llm_calls=0,
            total_llm_cost_eur=0.0,
            wall_clock_s=0.0,
        )
        return annotated, report


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_llm_output(text: str) -> LLMReadingOutput:
    """Parse and validate LLM JSON response.

    Applies a normalisation pass before Pydantic validation to handle
    field variants from non-schema-enforcing LLMs (e.g. DeepSeek):
    - new_concepts as list of strings → list of {"label": str}
    - new_connections as list of strings → dropped (no structure to recover)
    - new_connections as list of dicts → kept if parseable
    """
    data = json.loads(text)
    data = _normalise_llm_output(data)
    return LLMReadingOutput.model_validate(data)


def _normalise_llm_output(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise LLM output variants before Pydantic validation."""
    # Ensure required top-level lists exist
    for key in (
        "new_concepts",
        "new_connections",
        "confirmed_hypotheses",
        "rejected_hypotheses",
        "revisions",
        "open_tensions",
        "next_granularity",
    ):
        if key not in data:
            if key == "next_granularity":
                data[key] = "paragraph"
            else:
                data[key] = []
    if "synthesis" not in data:
        data["synthesis"] = None

    # synthesis: normalise field aliases
    syn = data.get("synthesis")
    if isinstance(syn, dict):
        if "level" in syn and "synthesis_level" not in syn:
            syn["synthesis_level"] = syn.pop("level")
        if "synthesis_level" not in syn:
            syn["synthesis_level"] = "paragraph"
        if "label" not in syn:
            syn["label"] = syn.get("title") or syn.get("name") or syn.get("summary", "Synthesis")
        if "description" not in syn:
            syn["description"] = syn.get("content") or syn.get("text", "")
        if "basis_concept_ids" not in syn:
            syn["basis_concept_ids"] = syn.get("concepts") or syn.get("basis") or []
        if "confidence" not in syn:
            syn["confidence"] = 0.7

    # new_concepts: list of strings → list of dicts
    concepts = data.get("new_concepts", [])
    if isinstance(concepts, list):
        normalised = []
        for c in concepts:
            if isinstance(c, str):
                normalised.append({"label": c})
            elif isinstance(c, dict):
                normalised.append(c)
        data["new_concepts"] = normalised

    # new_connections: list of strings → drop; list of dicts → normalise field names
    connections = data.get("new_connections", [])
    if isinstance(connections, list):
        normalised_edges = []
        for e in connections:
            if isinstance(e, dict):
                # DeepSeek field aliases for source/target
                if "source" in e and "source_label" not in e:
                    e["source_label"] = e.pop("source")
                if "target" in e and "target_label" not in e:
                    e["target_label"] = e.pop("target")
                if "source_id" in e and "source_label" not in e:
                    e["source_label"] = e.pop("source_id")
                if "target_id" in e and "target_label" not in e:
                    e["target_label"] = e.pop("target_id")
                if "description" in e and "relation_description" not in e:
                    e["relation_description"] = e.pop("description")
                if "relation" in e and "relation_description" not in e:
                    e["relation_description"] = e.pop("relation")
                if "source_label" in e and "target_label" in e:
                    normalised_edges.append(e)
            # strings without source/target are dropped
        data["new_connections"] = normalised_edges

    # confirmed_hypotheses / rejected_hypotheses: dicts → extract concept_id
    for key in ("confirmed_hypotheses", "rejected_hypotheses"):
        items = data.get(key, [])
        if isinstance(items, list):
            normalised_items = []
            for item in items:
                if isinstance(item, str):
                    normalised_items.append(item)
                elif isinstance(item, dict):
                    cid = item.get("concept_id") or item.get("id") or item.get("label", "")
                    if cid:
                        normalised_items.append(str(cid))
            data[key] = normalised_items

    # revisions: normalise if present
    revisions = data.get("revisions", [])
    if isinstance(revisions, list):
        normalised_revisions = []
        for r in revisions:
            if isinstance(r, dict):
                # DeepSeek field aliases
                if "type" in r and "revision_type" not in r:
                    r["revision_type"] = r.pop("type")
                if "concept_id" in r and "target_concept_id" not in r:
                    r["target_concept_id"] = r.pop("concept_id")
                if "target_concept_id" not in r:
                    r["target_concept_id"] = r.get("id", r.get("concept", "unknown"))
                normalised_revisions.append(r)
        data["revisions"] = normalised_revisions

    return data


def _pool_active_embeddings(state: ReadingState) -> list[float] | None:
    """Return the concept ID of the most-active concept (for query embedding).

    We can't pool embeddings here — they live in LanceDB, not in memory.
    Instead we return None to signal "use the embedder directly on the
    paragraph text" in the reader loop.

    This is a deliberate simplification: the actual query vector is
    computed by the kNN search from the LanceDB side, which uses the
    stored embeddings.  The reader uses the paragraph text embedding
    as the query for the gather step.
    """
    return None


def _decay_working_memory(state: ReadingState, added_concept_ids: set[str]) -> None:
    """Apply exponential decay to all active concepts not just added."""
    for cid, concept in state.active_concepts.items():
        if cid not in added_concept_ids:
            concept.activation *= WM_DECAY_FACTOR
            if concept.activation < 0.01:
                concept.activation = 0.01


def _compute_verdict(
    failed_steps: int,
    total_steps: int,
) -> tuple[
    Literal["good", "partial", "poor", "failed"],
    Literal["completed", "partial", "failed", "aborted"],
]:
    if total_steps == 0:
        return "failed", "failed"
    ratio = failed_steps / total_steps
    if ratio > _HARD_FAIL_THRESHOLD:
        return "failed", "failed"
    if ratio > _PARTIAL_THRESHOLD:
        return "partial", "partial"
    return "good", "completed"


def _title_from_url(url: str) -> str:
    url = url.strip()
    if "/wiki/" in url:
        return url.split("/wiki/", 1)[1].replace("_", " ").rstrip("/")
    return url
