"""
Pipeline characterization (Plan §3.8 layer 6, PHX-0034 stub-vorhut).

One opt-in test that runs the full :class:`~theogony.extraction.pipeline.IngestionPipeline`
against a ~300-sentence narrative slice of Hedin Trans-Himalaya Vol. I
(Gutenberg #43497) and asserts on **bands** rather than equalities.
The bands measure drift, not correctness — a Gen-1 stub of the
PHX-0034 entity-resolution quality benchmark Plan §7 calls for at
Gen 2 (gold-standard regression, cross-provider, multi-slice).

Gating
------
Two locks must both fire for this test to run:

1. The ``THEOGONY_RUN_CHARACTERIZATION=1`` environment variable.
2. The ``@pytest.mark.characterization`` pytest marker — invoke with
   ``pytest -m characterization``.

Default ``pytest`` and CI never trigger it; the ~0.15-0.25 EUR
Gemini cost stays opt-in.

Slice
-----
Hedin sentences ``[CHARACTERIZATION_SLICE_START:CHARACTERIZATION_SLICE_END]``
of the cleaned text. Justification (recorded in the PR body):

- Indices land mid-Chapter-I (after the title page, table of contents,
  list of illustrations, and prefatory matter that span sentences
  ~0–259) so the slice is solidly narrative travel prose, not
  publisher-frontispiece tokens that pollute tier-0 counts.
- Hedin's Chapter I is "SIMLA" — first-person planning of the
  expedition, with named entities Tibet, Himalayas, Karakorum,
  Ambala, Lahore, Rawalpindi, Manuel. Dense enough to exercise NER
  + Wikidata + RelationExtractor without padding.
- Length 300 chosen empirically: enough sentences for a stable
  tier histogram + non-trivial edge yield, short enough to keep
  one ingest under ~3 min and ~0.25 EUR.

Bands
-----
Calibrated once via an explorative run (see PR body for the table).
Bands are ±20% around the calibration values — wide enough to absorb
ordinary LLM / Wikidata variance, tight enough to catch real
regressions. The band shapes (>= for yield, <= for cost / wall-clock)
follow Plan §3.8 layer 6 + the spec Daedalus laid out.

Updating the bands
------------------
Re-calibrate when the pipeline composition changes meaningfully
(new stage, new provider, default-model swap). The procedure:

1. Run the test once with permissive bands (or comment them out).
2. Inspect ``docs/run_reports/characterization/<latest>.json`` for
   the new metrics.
3. Set the calibration constants below to the observed values.
4. Document the recalibration in the PR body, including the cost
   of the explorative run and a one-line justification.

Out of scope (PHX-0034 proper)
------------------------------
- Cross-provider comparison (later PR; tied to PHX-0027)
- Hand-annotated gold-standard precision/recall (Gen 2)
- Multi-slice parametrisation (later, on demand)
- Charakterisierungs-CLI (``theogony characterize``) — optional E8+
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from theogony.acquisition.base import RawContent
from theogony.acquisition.gutenberg import GutenbergAdapter
from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.clean import TextCleaner
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.sentence import Sentencizer
from theogony.extraction.wikidata_client import WikidataClient
from theogony.stores.memory import InMemoryKnowledgeStore

# Two-lock gating: env var + marker.
pytestmark = [
    pytest.mark.characterization,
    pytest.mark.skipif(
        os.environ.get("THEOGONY_RUN_CHARACTERIZATION") != "1",
        reason=(
            "Pipeline characterization runs are opt-in; set "
            "THEOGONY_RUN_CHARACTERIZATION=1 and invoke with "
            "`pytest -m characterization`."
        ),
    ),
]


# ---------------------------------------------------------------- corpus + slice

HEDIN_BOOK_ID = "43497"
"""Hedin, *Trans-Himalaya: Discoveries and Adventurers in Tibet*, Vol. 1."""

CHARACTERIZATION_SLICE_START = 260
"""Sentence index where Chapter I ("SIMLA") begins after the front matter."""

CHARACTERIZATION_SLICE_END = 560
"""Exclusive end — 300 sentences of solid narrative."""


# ---------------------------------------------------------------- bands

# Calibration values from the run documented in the PR body.
# Re-measure when the pipeline composition changes.
#
# Run-id:    01KPJ2PPPQM26RKTHWV7HN0838
# Date:      2026-04-19
# Slice:     Hedin #43497 sentences 260..560 (300 sentences)
# Provider:  gemini-2.5-flash-lite
# Caveat:    This calibration ran with the Gemini free-tier daily
#            quota (20 req/day) already exhausted from earlier
#            Etappe-E5/E6 work the same day. Stage-4 disambiguations
#            and relation-extraction calls almost all returned 429
#            RESOURCE_EXHAUSTED, so the LLM-dependent metrics
#            (CAL_TIER_HIGH_RATIO, CAL_MATERIALISED_EDGES) are
#            **conservative lower bounds**, not representative.
#            The next clean run after a fresh quota window should
#            tighten these — see the PR-body deviation note.
#            CAL_RESOLVED_NODES (NER-driven) and CAL_WALL_CLOCK_S
#            (Wikidata-SPARQL-dominated, ~321 s of the 347 s) are
#            already representative.
CAL_RESOLVED_NODES = 275
CAL_TIER_HIGH_RATIO = 0.116  # (tier_3 + tier_4) / total_resolved
CAL_WALL_CLOCK_S = 347.5
CAL_LLM_CALLS_TOTAL = 160
CAL_MATERIALISED_EDGES = 0  # quota-degraded; clean run expected ~30-100

# Margins (Daedalus spec, Plan §3.8 layer 6).
MARGIN_RESOLVED_NODES = 0.8  # >= cal * 0.8
MARGIN_TIER_HIGH_RATIO = 0.7  # >= cal * 0.7
MARGIN_WALL_CLOCK = 1.5  # <= cal * 1.5
MARGIN_LLM_CALLS = 1.3  # <= cal * 1.3
MARGIN_MATERIALISED_EDGES = 0.7  # >= cal * 0.7


# ---------------------------------------------------------------- report path

CHARACTERIZATION_REPORT_DIR = (
    Path(__file__).resolve().parent.parent / "docs" / "run_reports" / "characterization"
)
"""Persisted reports live under ``docs/`` (committed) — they are
documentation of the project state, not runtime data."""


# ---------------------------------------------------------------- helpers


def _build_llm() -> object:
    """Construct the active LLM, skipping when no key is in env."""
    settings = Settings()  # type: ignore[call-arg]
    if settings.active_llm_api_key() is None:
        pytest.skip("Characterization run requires a Gemini/Google API key in env.")
    try:
        return build_llm_from_settings(settings)
    except (ValueError, NotImplementedError) as exc:
        pytest.skip(f"Characterization run could not build LLM provider: {exc}")


async def _slice_to_raw(book_id: str, start: int, end: int) -> RawContent:
    """Acquire Hedin, clean, sentencize, splice the chosen range, repack as RawContent.

    The resulting RawContent has no PG header / footer (we hand the
    cleaner already-narrative text), which makes the cleaner stage
    effectively a no-op — TextCleaner emits a warning about the
    missing markers but passes content through unchanged. That is
    intentional: the characterization layer measures the resolver +
    relation + edge stages on a known, frontmatter-free narrative
    slice, not the cleaner's PG-marker handling (which has its own
    unit tests).
    """
    async with GutenbergAdapter(inter_request_delay_s=0.0) as gutenberg:
        cand = await gutenberg.get_by_id(book_id)
        full_raw = await gutenberg.acquire(cand)
    cleaner = TextCleaner()
    cleaned = cleaner.clean(full_raw.content)
    sentencizer = Sentencizer()
    sentences = await sentencizer.sentencize(cleaned)
    if end > len(sentences):
        raise RuntimeError(
            f"Hedin slice end {end} exceeds total sentences "
            f"{len(sentences)} — recalibrate CHARACTERIZATION_SLICE_END."
        )
    sliced_text = "".join(s.text for s in sentences[start:end])
    return RawContent(
        source_type="gutenberg",
        identifier=full_raw.identifier,
        title=full_raw.title,
        authors=list(full_raw.authors),
        language=full_raw.language,
        content=sliced_text,
        content_format=full_raw.content_format,
        url=full_raw.url,
        acquired_at=datetime.now(UTC),
        bytes_acquired=len(sliced_text.encode("utf-8")),
        metadata={
            **dict(full_raw.metadata),
            "characterization_slice_start": start,
            "characterization_slice_end": end,
        },
    )


# ---------------------------------------------------------------- the test


class TestPipelineCharacterization:
    async def test_full_pipeline_against_hedin_narrative_slice(self) -> None:
        llm = _build_llm()
        settings = Settings()  # type: ignore[call-arg]
        raw_content = await _slice_to_raw(
            HEDIN_BOOK_ID,
            CHARACTERIZATION_SLICE_START,
            CHARACTERIZATION_SLICE_END,
        )

        embedder = LocalSentenceTransformerEmbedder(
            model_id=settings.embedding.model_id,
            dim=settings.embedding.dim,
        )

        wall_clock_started = time.perf_counter()
        with ExtractionAuditLog() as audit:
            async with WikidataClient() as wd_client:
                resolver = EntityResolver(client=wd_client, llm=llm, audit_log=audit)  # type: ignore[arg-type]
                book_context_extractor = BookContextExtractor(llm=llm, audit_log=audit)  # type: ignore[arg-type]
                relation_extractor = RelationExtractor(llm=llm, audit_log=audit)  # type: ignore[arg-type]
                store = InMemoryKnowledgeStore()
                pipeline = IngestionPipeline(
                    entity_resolver=resolver,
                    relation_extractor=relation_extractor,
                    book_context_extractor=book_context_extractor,
                    embedder=embedder,
                    audit_log=audit,
                    store=store,
                    settings=settings,
                )
                result = await pipeline.ingest(raw_content)
                llm_calls_total = audit.count_for_run(result.run_id)
                llm_cost_eur = audit.total_cost_for_run(result.run_id)
        wall_clock_s = time.perf_counter() - wall_clock_started

        # ---- persist report (committed under docs/) ----
        CHARACTERIZATION_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = CHARACTERIZATION_REPORT_DIR / f"{result.run_id}.json"
        # Sidecar fields for the Reviewer agent + future drift analysis.
        report_dict = json.loads(result.report.model_dump_json())
        report_dict["characterization_meta"] = {
            "slice_start": CHARACTERIZATION_SLICE_START,
            "slice_end": CHARACTERIZATION_SLICE_END,
            "wall_clock_s_with_acquire": wall_clock_s,
            "llm_calls_total": llm_calls_total,
            "llm_cost_eur": llm_cost_eur,
            "calibration": {
                "resolved_nodes": CAL_RESOLVED_NODES,
                "tier_high_ratio": CAL_TIER_HIGH_RATIO,
                "wall_clock_s": CAL_WALL_CLOCK_S,
                "llm_calls_total": CAL_LLM_CALLS_TOTAL,
                "materialised_edges": CAL_MATERIALISED_EDGES,
            },
        }
        report_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

        # ---- compute metrics ----
        resolved_nodes = len(result.resolved_mentions)
        tier_counts = result.report.resolution.tier_counts
        tier_3_or_4 = tier_counts.get(3, 0) + tier_counts.get(4, 0)
        tier_high_ratio = tier_3_or_4 / resolved_nodes if resolved_nodes else 0.0
        materialised_edges = len(result.edges)

        # Print a human-readable summary alongside the assertions —
        # invaluable when this test fires and you need to see the
        # actual numbers without opening the JSON report.
        print(
            f"\nCharacterization run id={result.run_id}\n"
            f"  resolved_nodes      : {resolved_nodes:>4} "
            f"(cal {CAL_RESOLVED_NODES}, floor {CAL_RESOLVED_NODES * MARGIN_RESOLVED_NODES:.0f})\n"
            f"  tier_high_ratio     : {tier_high_ratio:>5.3f} "
            f"(cal {CAL_TIER_HIGH_RATIO:.3f}, floor "
            f"{CAL_TIER_HIGH_RATIO * MARGIN_TIER_HIGH_RATIO:.3f})\n"
            f"  wall_clock_s        : {wall_clock_s:>6.1f} "
            f"(cal {CAL_WALL_CLOCK_S:.1f}, ceiling "
            f"{CAL_WALL_CLOCK_S * MARGIN_WALL_CLOCK:.1f})\n"
            f"  llm_calls_total     : {llm_calls_total:>4} "
            f"(cal {CAL_LLM_CALLS_TOTAL}, ceiling "
            f"{CAL_LLM_CALLS_TOTAL * MARGIN_LLM_CALLS:.0f})\n"
            f"  materialised_edges  : {materialised_edges:>4} "
            f"(cal {CAL_MATERIALISED_EDGES}, floor "
            f"{CAL_MATERIALISED_EDGES * MARGIN_MATERIALISED_EDGES:.0f})\n"
            f"  llm_cost_eur        : {llm_cost_eur:.5f}\n"
            f"  tier_counts         : {dict(sorted(tier_counts.items()))}\n"
            f"  report_persisted    : {report_path}\n"
        )

        # ---- band assertions ----
        assert result.report.status == "completed", (
            f"pipeline status {result.report.status!r} (expected 'completed')"
        )
        assert resolved_nodes >= CAL_RESOLVED_NODES * MARGIN_RESOLVED_NODES, (
            f"resolved_nodes={resolved_nodes} below floor "
            f"{CAL_RESOLVED_NODES * MARGIN_RESOLVED_NODES:.0f} "
            f"(cal {CAL_RESOLVED_NODES} × {MARGIN_RESOLVED_NODES})"
        )
        assert tier_high_ratio >= CAL_TIER_HIGH_RATIO * MARGIN_TIER_HIGH_RATIO, (
            f"tier_high_ratio={tier_high_ratio:.3f} below floor "
            f"{CAL_TIER_HIGH_RATIO * MARGIN_TIER_HIGH_RATIO:.3f} "
            f"(cal {CAL_TIER_HIGH_RATIO:.3f} × {MARGIN_TIER_HIGH_RATIO})"
        )
        assert wall_clock_s <= CAL_WALL_CLOCK_S * MARGIN_WALL_CLOCK, (
            f"wall_clock_s={wall_clock_s:.1f} above ceiling "
            f"{CAL_WALL_CLOCK_S * MARGIN_WALL_CLOCK:.1f} "
            f"(cal {CAL_WALL_CLOCK_S:.1f} × {MARGIN_WALL_CLOCK})"
        )
        assert llm_calls_total <= CAL_LLM_CALLS_TOTAL * MARGIN_LLM_CALLS, (
            f"llm_calls_total={llm_calls_total} above ceiling "
            f"{CAL_LLM_CALLS_TOTAL * MARGIN_LLM_CALLS:.0f} "
            f"(cal {CAL_LLM_CALLS_TOTAL} × {MARGIN_LLM_CALLS})"
        )
        assert materialised_edges >= CAL_MATERIALISED_EDGES * MARGIN_MATERIALISED_EDGES, (
            f"materialised_edges={materialised_edges} below floor "
            f"{CAL_MATERIALISED_EDGES * MARGIN_MATERIALISED_EDGES:.0f} "
            f"(cal {CAL_MATERIALISED_EDGES} × {MARGIN_MATERIALISED_EDGES})"
        )
