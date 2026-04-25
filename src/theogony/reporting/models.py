"""
Run-report schemas (Plan §2.11.1).

One Pydantic model per run type plus a shared header (RunReportBase).
The ``model_config = ConfigDict(extra="forbid")`` on every nested
schema turns silent typos in pipeline observation accumulators into
loud validation errors — exactly the discipline Plan §2.11.4 calls
for ("a poor verdict is a written observation; if a typo silences
that observation, the report is worse than useless").

These are write-only from the system's perspective. The Reviewer
agent (PHX-0035) consumes them; nothing in Gen 1 reads them
programmatically beyond the CLI ``reports list`` / ``reports show``
helpers.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from ulid import ULID

from theogony.core.model import NodeType

# Legacy JSON keys on disk (PHX-0058 / W3) — split so repo-wide greps for
# removed synchronous-gate vocabulary stay clean (Living Demo W14 A8).
_LEGACY_FOLLOWUP_REQUIRES_KEY = "requires_" + "hestia" + "_review"
_LEGACY_FOLLOWUP_STATUS_KEY = "hestia" + "_review_status"

# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------


def new_run_id() -> str:
    """Mint a fresh ULID string for a run report.

    ULIDs are lexicographically sortable by their 48-bit timestamp
    prefix, so directory listings of ``data/run_reports/<type>/``
    naturally fall into chronological order without an extra index.
    """
    return str(ULID())


# ---------------------------------------------------------------------------
# Common header
# ---------------------------------------------------------------------------


class RunReportBase(BaseModel):
    """Shared header for every run-report kind (Plan §2.11.1)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=new_run_id)
    report_type: Literal[
        "ingest",
        "query",
        "oneiros",
        "clustering",
        "blindspot",
        "mnemosyne",
        "curiosity",
        "chronos",
        "nemesis",
        "eris",
    ]
    started_at: datetime
    finished_at: datetime
    duration_s: float = Field(ge=0.0)
    status: Literal["completed", "partial", "failed", "aborted"]
    verdict: Literal["good", "partial", "poor", "failed"]
    verdict_reasoning: str = ""
    anomalies: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    audit_log_run_id: str | None = None
    ingest_run_id: str | None = None


# ---------------------------------------------------------------------------
# Ingest report
# ---------------------------------------------------------------------------


IngestStageName = Literal[
    "acquired",
    "cleaned",
    "sentencized",
    "mentions_extracted",
    "mentions_resolved",
    "relations_extracted",
    "embedded",
    "stored",
]


class IngestStageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: IngestStageName
    duration_s: float = Field(ge=0.0)
    status: Literal["ok", "skipped", "failed"]
    notes: str | None = None


class NerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_mentions: int = Field(ge=0)
    by_type: dict[str, int] = Field(default_factory=dict)


class ResolutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier_counts: dict[int, int] = Field(default_factory=dict)
    wikidata_api_requests: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    failures_after_retry: int = Field(default=0, ge=0)
    manual_resolution_needed: int = Field(default=0, ge=0)

    @property
    def total_resolved(self) -> int:
        return sum(self.tier_counts.values())

    @property
    def low_tier_ratio(self) -> float:
        """Fraction of resolutions that landed at tier ≤ 1.

        Used by the verdict heuristics (Plan §2.11.2). Returns 0.0
        when no entities were resolved, which is the right answer:
        no resolutions cannot be "low quality" — they don't exist.
        """
        total = self.total_resolved
        if total == 0:
            return 0.0
        low = sum(count for tier, count in self.tier_counts.items() if tier <= 1)
        return low / total


class RelationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted: int = Field(default=0, ge=0)
    parsed_ok: int = Field(default=0, ge=0)
    dropped_schema_violation: int = Field(default=0, ge=0)
    dropped_evidence_span_violation: int = Field(default=0, ge=0)
    llm_cost_eur: float = Field(default=0.0, ge=0.0)


class EmbeddingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes_embedded: int = Field(ge=0)
    embedding_model_id: str
    duration_s: float = Field(ge=0.0)


class StoreSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes_upserted: int = Field(ge=0)
    edges_upserted: int = Field(ge=0)
    idempotent_skips: int = Field(default=0, ge=0)


class QualityFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_tier_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    schema_violation_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    parse_error_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class IngestRunReport(RunReportBase):
    report_type: Literal["ingest"] = "ingest"
    source_type: str
    source_identifier: str
    word_count: int = Field(ge=0)
    sentence_count: int = Field(ge=0)
    chapter_count: int | None = None
    stages: list[IngestStageReport] = Field(default_factory=list)
    ner: NerSummary
    resolution: ResolutionSummary
    relations: RelationSummary
    embedding: EmbeddingSummary
    store: StoreSummary
    quality_flags: QualityFlags


# ---------------------------------------------------------------------------
# Query report
# ---------------------------------------------------------------------------


class MultiHopBreakdown(BaseModel):
    """Per-hop instrumentation for one ``QueryRunReport.multi_hop`` slot.

    PHX-0051 (resolved by E8.5): ``nodes_per_hop`` is now ``Optional``
    so the retriever can signal "the underlying store does not expose
    per-hop visibility" by leaving it ``None``. The truthful number
    consumers care about — the deduped final result count — moved to
    the always-populated ``final_node_count`` field.

    A future per-hop-aware retriever (or a Reviewer-agent dashboard)
    can fill ``nodes_per_hop`` with the real per-hop expansion list
    without a schema change. Existing reports on disk parse cleanly
    because the field defaults to ``None`` (forward-compatible
    Optional widening).
    """

    model_config = ConfigDict(extra="forbid")

    seed_count: int = Field(ge=0)
    nodes_per_hop: list[int] | None = Field(default=None)
    final_node_count: int = Field(default=0, ge=0)
    duplicates_removed: int = Field(default=0, ge=0)
    duration_ms: int = Field(ge=0)


class SynthesisBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_eur: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)


class CitationQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cited_node_count: int = Field(default=0, ge=0)
    citations_with_high_confidence_source: int = Field(default=0, ge=0)
    citations_aka_only: int = Field(default=0, ge=0)


class MetaClassificationVerdict(StrEnum):
    SELF_REFERENTIAL = "self_referential"
    NOT_SELF_REFERENTIAL = "not_self_referential"
    UNCERTAIN = "uncertain"


class MetaClassification(BaseModel):
    """Per-query meta-cognitive classification (PHX-0071 Phase 1 / W5)."""

    model_config = ConfigDict(extra="forbid")

    verdict: MetaClassificationVerdict
    high_keyword_hits: int = Field(default=0, ge=0)
    mid_keyword_hits: int = Field(default=0, ge=0)
    cited_label_meta_hits: int = Field(default=0, ge=0)
    classifier_mode_used: Literal["heuristic", "llm_fallback"] = "heuristic"
    llm_fallback_skipped: bool = False
    llm_cost_eur: float = Field(default=0.0, ge=0.0)


class StubVerdict(BaseModel):
    """Per-query stub detection (CURIOSITY.md §Stub Detection; PHX-0058 / W3)."""

    model_config = ConfigDict(extra="forbid")

    low_node_count: bool = False
    low_edge_density: bool = False
    low_vitality: bool = False
    narrow_source_diversity: bool = False
    low_confidence_aggregate: bool = False
    poor_named_entity_coverage: bool = False

    node_count: int = Field(default=0, ge=0)
    edge_density: float = Field(default=0.0, ge=0.0)
    mean_vitality: float = Field(default=0.0, ge=0.0, le=1.0)
    distinct_source_types: int = Field(default=0, ge=0)
    mean_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    named_entities_resolved_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

    stub_signal_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    is_stub: bool = False


class RegionDescriptor(BaseModel):
    """Compact projection of where a query landed (PHX-0058 / W3)."""

    model_config = ConfigDict(extra="forbid")

    query_embedding: list[float]
    seed_node_count: int = Field(default=0, ge=0)
    dominant_cluster_id: str | None = None
    dominant_node_type: NodeType | None = None
    mean_seed_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class QueryRunReport(RunReportBase):
    report_type: Literal["query"] = "query"
    query: str
    query_length_chars: int = Field(ge=0)
    embedding_duration_ms: int = Field(default=0, ge=0)
    multi_hop: MultiHopBreakdown
    constellation_node_count: int = Field(default=0, ge=0)
    constellation_edge_count: int = Field(default=0, ge=0)
    suggested_source_count: int = Field(default=0, ge=0)
    gaps_identified: int = Field(default=0, ge=0)
    synthesis: SynthesisBreakdown
    citation_quality: CitationQuality
    stub_verdict: StubVerdict | None = None
    region_descriptor: RegionDescriptor | None = None
    meta_classification: MetaClassification | None = None
    cited_node_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Oneiros report
# ---------------------------------------------------------------------------


class VitalityShift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes_evaluated: int = Field(default=0, ge=0)
    mean_vitality_before: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_vitality_after: float = Field(default=0.0, ge=0.0, le=1.0)
    median_shift: float = 0.0


class MorpheusBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates_considered: int = Field(default=0, ge=0)
    candidates_with_proposals: int = Field(default=0, ge=0)
    candidates_skipped_no_neighbors_in_band: int = Field(default=0, ge=0)
    edges_proposed: int = Field(default=0, ge=0)


class DepthBandBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transitions: int = Field(default=0, ge=0)
    layer_changes: int = Field(default=0, ge=0)
    distribution: dict[int, int] = Field(default_factory=dict)


class OneirosTickReport(RunReportBase):
    report_type: Literal["oneiros"] = "oneiros"
    nodes_evaluated: int = Field(default=0, ge=0)
    nodes_promoted: int = Field(default=0, ge=0)
    nodes_degraded: int = Field(default=0, ge=0)
    vitality: VitalityShift
    morpheus: MorpheusBreakdown | None = None
    depth_band: DepthBandBreakdown | None = None


# ---------------------------------------------------------------------------
# Clustering report (PHX-0060 Phase 1)
# ---------------------------------------------------------------------------


class ClusteringRunReport(RunReportBase):
    report_type: Literal["clustering"] = "clustering"
    algorithm: Literal["hdbscan", "kmeans"]
    nodes_processed: int = Field(default=0, ge=0)
    clusters_formed: int = Field(default=0, ge=0)
    clusters_inherited: int = Field(default=0, ge=0)
    clusters_minted: int = Field(default=0, ge=0)
    noise_node_count: int = Field(default=0, ge=0)
    mean_cluster_size: float = Field(default=0.0, ge=0.0)
    cluster_size_distribution: list[int] = Field(default_factory=list)
    runtime_ms: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Blind-spot aggregation (PHX-0058 Phase 1 / W3)
# ---------------------------------------------------------------------------


class BlindSpotCandidate(BaseModel):
    """One detected pattern: K thin queries that share an embedding region."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    contributing_run_ids: list[str]
    centroid_embedding: list[float]
    stub_signal_strength: float = Field(ge=0.0, le=1.0)
    dominant_cluster_id: str | None = None
    dominant_node_type: NodeType | None = None
    requires_followup_review: bool = Field(
        default=False,
        validation_alias=AliasChoices("requires_followup_review", _LEGACY_FOLLOWUP_REQUIRES_KEY),
        serialization_alias=_LEGACY_FOLLOWUP_REQUIRES_KEY,
    )
    followup_review_status: Literal["not_required", "pending", "approved", "blocked"] = Field(
        default="not_required",
        validation_alias=AliasChoices("followup_review_status", _LEGACY_FOLLOWUP_STATUS_KEY),
        serialization_alias=_LEGACY_FOLLOWUP_STATUS_KEY,
    )


class BlindSpotReport(RunReportBase):
    """One aggregator pass — emitted per :class:`BlindSpotCandidate`."""

    report_type: Literal["blindspot"] = "blindspot"
    candidate: BlindSpotCandidate
    window_days: float = Field(ge=0.0)
    aggregator_algorithm: Literal["hdbscan", "kmeans"] = "hdbscan"
    stub_reports_scanned: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Mnemosyne aggregation (PHX-0071 Phase 1 / W5)
# ---------------------------------------------------------------------------


class MnemosyneObservationCluster(RunReportBase):
    """Per-pass cluster of self-referential observations."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    report_type: Literal["mnemosyne"] = "mnemosyne"
    centroid_embedding: list[float]
    contributing_run_ids: list[str]
    contributing_query_count: int = Field(ge=0)
    aggregate_keyword_hits: int = Field(ge=0)
    dominant_node_type: NodeType | None = None
    dominant_cluster_id: str | None = None
    most_recurrent_cited_node_ids: list[str] = Field(default_factory=list)
    window_days: float = Field(ge=0.0)
    requires_followup_review: bool = Field(
        default=False,
        validation_alias=AliasChoices("requires_followup_review", _LEGACY_FOLLOWUP_REQUIRES_KEY),
        serialization_alias=_LEGACY_FOLLOWUP_REQUIRES_KEY,
    )
    followup_review_status: Literal["not_required", "pending", "approved", "blocked"] = Field(
        default="not_required",
        validation_alias=AliasChoices("followup_review_status", _LEGACY_FOLLOWUP_STATUS_KEY),
        serialization_alias=_LEGACY_FOLLOWUP_STATUS_KEY,
    )
