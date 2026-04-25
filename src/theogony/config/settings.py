"""
Typed runtime configuration for Theogony.

All knobs the system needs at startup live here. Values are loaded, in order,
from constructor kwargs, then process environment, then `.env` in the
working directory. Secret material is held in `pydantic.SecretStr` so it
never appears in `repr(settings)` or in default log records.

The only hard rule from PHILOSOPHY.md and the implementation plan §3.6:
**a Settings instance is never logged whole, and secret fields use
SecretStr.** Both are enforced here at the schema level.

Environment-variable conventions
--------------------------------
Most settings are namespaced behind the ``THEOGONY_`` prefix; nested
sub-settings use ``__`` as separator (pydantic-settings default).

Examples::

    THEOGONY_LOG_LEVEL=DEBUG
    THEOGONY_LLM__PROVIDER=openai
    THEOGONY_LLM__MODEL_ID=gpt-4o-mini
    THEOGONY_NEO4J__PASSWORD=changeme

API keys are special: they are read from canonical, **un-prefixed** names
because that is what the surrounding ecosystem (Google AI Studio,
OpenAI, Anthropic) writes into developer environments by default::

    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    GEMINI_API_KEY=...
    GOOGLE_API_KEY=...
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "openai", "anthropic", "stub"]


class LLMSettings(BaseModel):
    """Selection and tuning of the active LLMProvider.

    The default is **Anthropic ``claude-sonnet-4-6``** (Claude Sonnet
    4.6): prepaid API credits and predictable billing are a better fit
    for day-to-day ingest / demo runs than Gemini's free-tier daily
    caps. OpenAI ``gpt-4o-mini`` and Gemini ``gemini-2.5-flash-lite``
    remain first-class options (Plan §3.3a pricing table) via
    ``THEOGONY_LLM__PROVIDER=openai`` or ``THEOGONY_LLM__PROVIDER=gemini``.

    The PR #30 default ``claude-3-5-haiku-20241022`` was retired by
    Anthropic; W5 moved the stack to Haiku 4.5, then the default was
    raised to Sonnet 4.6 for extraction quality. Override with
    ``THEOGONY_LLM__MODEL_ID`` (e.g. ``claude-haiku-4-5-20251001``) when
    you want a cheaper tier.

    Switch providers without touching code via
    ``THEOGONY_LLM__PROVIDER=gemini|openai|anthropic|stub`` (and set the
    matching API key: ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, or
    ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``).

    ``model_id`` defaults per ``provider`` when left empty (e.g. env
    sets only ``THEOGONY_LLM__PROVIDER=gemini``).
    """

    provider: LLMProviderName = "anthropic"
    model_id: str = Field(
        default="",
        description="Model name for the active provider; empty → sensible default.",
    )
    timeout_s: float = Field(default=30.0, gt=0.0)
    max_concurrency: int = Field(default=8, ge=1)
    offline_top_n_citations: int = Field(
        default=6,
        ge=1,
        le=50,
        description="Top-N constellation nodes cited by OfflineAnswerSynthesizer (stub provider).",
    )

    @model_validator(mode="after")
    def _default_model_id_for_provider(self) -> Self:
        if self.model_id.strip():
            return self
        defaults: dict[LLMProviderName, str] = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-sonnet-4-6",
            "gemini": "gemini-2.5-flash-lite",
            "stub": "stub-llm",
        }
        object.__setattr__(self, "model_id", defaults[self.provider])
        return self


class EmbeddingSettings(BaseModel):
    """Embedding model identity, recorded on every node per Plan §9.3.

    Default is BGE-small-en-v1.5 (Plan §3.2): 33 MB, 384-dim, runs on
    CPU at hundreds of sentences/second, no network dependency.
    """

    model_id: str = "BAAI/bge-small-en-v1.5"
    dim: int = Field(default=384, ge=1)


class Neo4jSettings(BaseModel):
    """Connection parameters for the Gen 1 KnowledgeStore backend.

    Defaults target a local docker-compose Neo4j with the well-known
    development password. Production deployments override the password
    via environment variables.
    """

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: SecretStr = SecretStr("neo4j")
    database: str = "neo4j"


class EdgePheromoneSettings(BaseModel):
    """Tunables for :class:`~theogony.memory.pheromone_decay_phase.PheromoneDecayPhase`."""

    model_config = ConfigDict(extra="forbid")

    decay_horizon_days: float = Field(default=30.0, ge=0.0)
    decay_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    decay_epsilon: float = Field(default=0.001, ge=0.0, le=1.0)


class MorpheusSettings(BaseModel):
    """Morpheus associator (PHX-0059 Phase 1 / W4)."""

    model_config = ConfigDict(extra="forbid")

    batch_size: int = Field(default=50, ge=1, le=500)
    proposals_per_node_cap: int = Field(default=5, ge=1, le=50)
    embedding_band_low: float = Field(default=0.6, ge=0.0, le=1.0)
    embedding_band_high: float = Field(default=0.9, ge=0.0, le=1.0)
    candidate_isolation_max_edges: int = Field(default=5, ge=0)
    cluster_scope: Literal["within_only", "within_and_cross"] = "within_and_cross"

    @model_validator(mode="after")
    def _embedding_band_order(self) -> Self:
        if self.embedding_band_low > self.embedding_band_high:
            raise ValueError("embedding_band_low must be <= embedding_band_high")
        return self


class DepthBandSettings(BaseModel):
    """Depth-band ladder (PHX-0059 Phase 1 / W4)."""

    model_config = ConfigDict(extra="forbid")

    pheromone_bonus_weight: float = Field(default=0.5, ge=0.0, le=2.0)


class OneirosSettings(BaseModel):
    """Runtime tunables for the :class:`OneirosWorker` (Plan §4.3, §5 E8.5).

    The defaults match the chosen formulas inlined in the worker
    (Plan §5 E8.5 lifecycle math). Operators tune via
    ``THEOGONY_ONEIROS__*`` env vars; PHX-0009 governs whether the
    defaults are revisited empirically.

    ``max_nodes_per_tick`` is **deliberately omitted** (Q9
    refinement): the ≤ 2000-node Gen 1 demo target makes per-tick
    batching irrelevant; "I anticipate scale" is the §3.1
    anti-pattern. File a fresh PHX if EPHEMERA crosses ~50 K with
    measured tick latency.
    """

    tick_interval_s: float = Field(default=60.0, ge=0.01)
    promote_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    degrade_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    degrade_min_idle_days: float = Field(default=7.0, ge=0.0)
    connectivity_full_credit_edges: int = Field(default=20, ge=1)
    freshness_horizon_days: float = Field(default=30.0, ge=1.0)
    enabled_phases: list[str] = Field(
        default_factory=lambda: [
            "snapshot_ephemera",
            "count_neighbors",
            "recompute_scores",
            "write_scores",
            "promote",
            "degrade_mneme",
        ],
        description=(
            "Ordered list of TickPhase names to run per tick. Default = "
            "all six built-in phases in their canonical order. Operators "
            "can disable phases (e.g. omit 'promote' for read-only test "
            "deployments) or reorder. Future phases from PHX-0057/0058/"
            "0059/0060 are added via custom phase_registry injection "
            "(e.g. blind_spot_aggregation, PHX-0058)."
        ),
    )
    edge_pheromone: EdgePheromoneSettings = Field(default_factory=EdgePheromoneSettings)


class ApiSettings(BaseModel):
    """HTTP API server defaults (advertised URLs, cockpit banner)."""

    model_config = ConfigDict(extra="forbid")

    port: int = Field(default=8000, ge=1, le=65535)


class CockpitSettings(BaseModel):
    """Iris cockpit (PHX-0074 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True)
    bind_host: str = Field(default="127.0.0.1")
    bind_port: int | None = Field(default=None)
    public: bool = Field(default=False)
    sample_only: bool = Field(default=False)
    sample_top_n_nodes: int = Field(default=20, ge=1, le=200)
    sample_recent_n_reports: int = Field(default=50, ge=1, le=500)
    manifest_path: Path = Field(default=Path("cockpit/manifest.md"))
    manifest_git_commit: bool = Field(default=False)
    auth_provider: Literal["none", "oidc", "github", "basic", "password_file"] = "none"
    status_sse_interval_s: float = Field(default=5.0, ge=5.0, le=300.0)
    sse_max_concurrent_clients: int = Field(default=50, ge=1, le=10_000)
    cluster_drill_max_members: int = Field(default=50, ge=1, le=500)

    @model_validator(mode="after")
    def _cockpit_public_auth_rules(self) -> Self:
        if self.auth_provider != "none":
            raise NotImplementedError(
                "cockpit auth is Phase 2 only — set THEOGONY_COCKPIT__AUTH_PROVIDER=none "
                "or see PHX-0074 (Iris)."
            )
        if self.public and self.bind_host != "0.0.0.0":
            raise ValueError(
                "cockpit.public=True requires cockpit.bind_host='0.0.0.0' — "
                "public exposure without binding all interfaces is a configuration error."
            )
        return self


class McpAppendSettings(BaseModel):
    """Bounded MCP tool ``pantheon_chronicle_append`` (agent-curated growth).

    Writes ``KnowledgeNode`` rows with ``source_type=mcp_agent`` and
    ``epistemic_status=hypothesized``. There is **no auth** in Gen 1 —
    rely on ``HostedSettings`` rate limits, tight size caps, and
    ``enabled=false`` on untrusted public surfaces.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True)
    max_fragments_per_call: int = Field(default=8, ge=1, le=50)
    max_title_chars: int = Field(default=240, ge=8, le=500)
    max_body_chars_per_fragment: int = Field(default=8_000, ge=128, le=50_000)
    max_total_body_chars: int = Field(default=32_000, ge=512, le=500_000)


class HostedSettings(BaseModel):
    """Tunables for the HTTP/SSE MCP hosted transport (PHX-0066 Phase 1).

    Rate limits apply to ``/sse`` and ``/messages/`` only; ``/health`` is
    excluded. Set ``rate_limit_per_hour`` to ``0`` to disable limiting
    entirely.
    """

    model_config = ConfigDict(extra="forbid")

    rate_limit_per_hour: int = Field(default=60, ge=0)
    rate_limit_per_day: int = Field(default=1000, ge=0)
    rate_limit_bypass_token: SecretStr | None = None


class WikidataCacheSettings(BaseModel):
    """Persistent Wikidata cache toggle (W6, PR #33).

    The cache lives at ``settings.data_dir / "wikidata_cache.sqlite"``
    by default. The W6 brief asks for one boolean knob and one default
    path — no TTL matrix, no admin CLI, no warmup jobs. Set
    ``THEOGONY_WIKIDATA_CACHE__ENABLED=false`` to bypass it for one
    test run when you need to measure cold-cache numbers.
    """

    enabled: bool = Field(
        default=True,
        description=(
            "Whether the IngestionPipeline wires a persistent "
            "WikidataCache into its WikidataClient. Disable to "
            "measure cold-cache behaviour."
        ),
    )


class StoreSettings(BaseModel):
    """Storage-layer tuning that is *backend-agnostic*.

    Knobs here apply to every :class:`~theogony.core.store.KnowledgeStore`
    implementation; backend-specific tuning (Neo4j connection, future
    DuckDB pragmas, …) lives in dedicated subgroups (``Neo4jSettings``).

    PHX-0046: ``batch_size`` chooses how many nodes / edges the
    IngestionPipeline hands to ``KnowledgeStore.batch_upsert_*`` per
    UNWIND round-trip. 200 is the sweet spot per the Neo4j driver
    documentation: small enough that one batch fits comfortably in
    Bolt's default frame and large enough that the per-round-trip
    overhead amortises to near zero.
    """

    batch_size: int = Field(default=200, ge=1)


class IngestVerdictThresholds(BaseModel):
    """Cut-points for ``IngestRunReport.verdict`` per Plan §2.11.2.

    Tuneable via env vars (e.g. ``THEOGONY_REPORT__THRESHOLDS__INGEST__POOR_PARSE_ERROR_RATE``)
    so a future Reviewer agent can adjust them empirically without
    code changes. The defaults match the plan exactly.
    """

    poor_parse_error_rate: float = Field(default=0.20, ge=0.0, le=1.0)
    partial_parse_error_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    poor_low_tier_ratio: float = Field(default=0.60, ge=0.0, le=1.0)
    partial_low_tier_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    poor_anomaly_count: int = Field(default=3, ge=0)


class QueryVerdictThresholds(BaseModel):
    """Cut-points for ``QueryRunReport.verdict`` per Plan §2.11.2."""

    poor_latency_ms: int = Field(default=10_000, ge=0)
    partial_latency_ms: int = Field(default=5_000, ge=0)
    good_high_conf_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    partial_gaps_count: int = Field(default=3, ge=0)


class OneirosVerdictThresholds(BaseModel):
    """Cut-points for ``OneirosTickReport.verdict`` per Plan §2.11.2."""

    poor_median_vitality_shift: float = Field(default=-0.05)


class AnomalyThresholds(BaseModel):
    """Cut-points for the four named anomaly rules per Plan §2.11.2.

    The plan lists ``stage_slow``, ``cost_spike``, ``wikidata_failure_burst``,
    ``embedding_skew``. Per-stage baseline durations live alongside, so
    a new contributor can adjust them when measured behaviour drifts.
    """

    stage_slow_multiplier: float = Field(default=2.0, gt=0.0)
    cost_spike_multiplier: float = Field(default=1.5, gt=0.0)
    cost_spike_min_history: int = Field(default=5, ge=0)
    wikidata_failure_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    embedding_skew_stddev_multiplier: float = Field(default=3.0, gt=0.0)


class IngestStageBaselines(BaseModel):
    """Baseline per-stage durations (seconds) used by the ``stage_slow`` rule.

    Defaults match Plan §4.1 v3 figures for the "Seven Years in Tibet"
    workload. They are deliberately high enough that ordinary variance
    does not trigger anomalies; the rule fires only on genuinely slow
    stages.
    """

    acquired: float = Field(default=2.0, gt=0.0)
    cleaned: float = Field(default=5.0, gt=0.0)
    sentencized: float = Field(default=5.0, gt=0.0)
    mentions_extracted: float = Field(default=30.0, gt=0.0)
    mentions_resolved: float = Field(default=90.0, gt=0.0)
    relations_extracted: float = Field(default=180.0, gt=0.0)
    embedded: float = Field(default=30.0, gt=0.0)
    stored: float = Field(default=10.0, gt=0.0)


class VerdictThresholds(BaseModel):
    """Verdict thresholds for all three RunReport types (Plan §2.11.2)."""

    ingest: IngestVerdictThresholds = Field(default_factory=IngestVerdictThresholds)
    query: QueryVerdictThresholds = Field(default_factory=QueryVerdictThresholds)
    oneiros: OneirosVerdictThresholds = Field(default_factory=OneirosVerdictThresholds)


class ReportSettings(BaseModel):
    """Reporting configuration (Plan §2.11).

    The ``thresholds`` group is referenced by every ``_finalize_report``
    hook and by ``reporting/anomaly.py``. Centralising them here means
    there is one place a future Reviewer agent (PHX-0035) can write to
    when it discovers the heuristic anchors are mis-calibrated.
    """

    thresholds: VerdictThresholds = Field(default_factory=VerdictThresholds)
    anomaly: AnomalyThresholds = Field(default_factory=AnomalyThresholds)
    stage_baselines: IngestStageBaselines = Field(default_factory=IngestStageBaselines)
    oneiros_tick_retention: int = Field(
        default=100,
        ge=1,
        description=(
            "Maximum number of OneirosTickReport JSON files to keep on disk. "
            "Plan §5 Week 3: cap retention at 100 most recent ticks to "
            "prevent disk bloat — the audit log is the long-term record."
        ),
    )


class RelevanceSettings(BaseModel):
    """Post-query write-back tunables (Plan §4.3 + PHX-0057 edge pheromone)."""

    model_config = ConfigDict(extra="forbid")

    relevance_delta: float = Field(default=0.05, ge=0.0, le=1.0)
    edge_pheromone_delta: float = Field(default=0.015, ge=0.0, le=1.0)


class ChronicleEntryPlannerSettings(BaseModel):
    """LLM proposes several vector-search strings before retrieval (Explorer / ask)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        description=(
            "When true and QueryPipeline receives a non-stub entry_planner_llm, "
            "the model outputs multiple search_queries that are embedded separately "
            "and merged — the raw user question is not the only retrieval anchor. "
            "Set false (env THEOGONY_RETRIEVAL__CHRONICLE_ENTRY_PLANNER__ENABLED=false) "
            "to embed only the user question."
        ),
    )
    max_sub_queries: int = Field(default=4, ge=1, le=8)
    max_chars_per_sub_query: int = Field(default=240, ge=32, le=400)
    max_planner_tokens: int = Field(default=600, ge=128, le=2000)


class ChronicleThinkingSettings(BaseModel):
    """Optional post-retrieval refinement rounds (LLM sees constellation, proposes new searches)."""

    model_config = ConfigDict(extra="forbid")

    max_rounds: int = Field(
        default=0,
        ge=0,
        le=8,
        description=(
            "Max extra thinking rounds after the first retrieve+assemble+synthesize when "
            "``thinking_max`` is not passed explicitly to ``QueryPipeline.ask`` (0=off). "
            "The Explorer defaults ``thinking_max`` to 2 in the request body instead."
        ),
    )
    max_planner_tokens: int = Field(default=640, ge=128, le=2000)


class RetrievalSettings(BaseModel):
    """Tunables for the retrieval stack (PHX-0056 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    strategy: Literal["fixed_depth", "edge_product", "cluster_narrow"] = "fixed_depth"
    edge_product_min_path_product: float | None = Field(default=None, ge=0.0, le=1.0)
    edge_product_top_n_paths: int | None = Field(default=None, ge=1, le=200)
    cluster_narrow_inner_strategy: Literal["fixed_depth", "edge_product"] = "fixed_depth"
    cluster_narrow_top_n_clusters: int = Field(default=3, ge=1, le=20)
    chronicle_entry_planner: ChronicleEntryPlannerSettings = Field(
        default_factory=ChronicleEntryPlannerSettings,
    )
    chronicle_thinking: ChronicleThinkingSettings = Field(
        default_factory=ChronicleThinkingSettings,
    )


class ClusteringSettings(BaseModel):
    """Tunables for the clustering stack (PHX-0060 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["auto", "hdbscan", "kmeans"] = "auto"
    recluster_interval_days: float = Field(default=30.0, ge=0.0)
    min_cluster_size: int = Field(default=5, ge=2)
    min_corpus_size: int = Field(default=20, ge=2)
    corpus_size_kmeans_threshold: int = Field(default=100_000, ge=1_000)
    identity_jaccard_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    new_node_assignment: Literal["nearest_centroid", "skip"] = "nearest_centroid"


class StubThresholds(BaseModel):
    """Per-query stub-detection thresholds (CURIOSITY.md §Stub Detection; W3)."""

    model_config = ConfigDict(extra="forbid")

    min_node_count: int = Field(default=3, ge=0)
    min_edge_density: float = Field(default=0.5, ge=0.0)
    min_mean_vitality: float = Field(default=0.3, ge=0.0, le=1.0)
    min_distinct_source_types: int = Field(default=2, ge=0)
    min_mean_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    min_named_entities_resolved_ratio: float = Field(default=0.5, ge=0.0, le=1.0)


class GrowthBridgeSettings(BaseModel):
    """Couple verdict + user request to acquisition triggers (Wave 2 W10)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    min_cited_for_no_research: int = Field(default=3, ge=0, le=20)
    max_triggers_per_query: int = Field(default=1, ge=1, le=5)


class ArgusSettings(BaseModel):
    """Argus acquisition agent (Living Demo W7-B, PHX-0037 slice 2)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    search_limit: int = Field(default=5, ge=1, le=25)
    min_candidate_score: float = Field(default=0.3, ge=0.0, le=1.0)


class ResearchPlannerSettings(BaseModel):
    """LLM-driven research planner (Living Demo W11)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_search_calls: int = Field(default=3, ge=0, le=10)
    max_total_tokens: int = Field(default=4000, ge=500, le=20000)
    max_steps_per_plan: int = Field(default=3, ge=0, le=5)


class EvaluatorSettings(BaseModel):
    """LLM-driven research evaluator (Living Demo W11)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_total_tokens: int = Field(default=2000, ge=200, le=10000)


class AtheneSettings(BaseModel):
    """Post-hoc verification worker (Living Demo W14)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    sample_rate: float = Field(default=0.02, ge=0.0, le=1.0)
    min_entries_per_pass: int = Field(default=1, ge=0, le=100)
    max_entries_per_pass: int = Field(default=50, ge=1, le=500)
    low_resolution_ratio_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    schema_violation_rate_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    parse_error_rate_threshold: float = Field(default=0.1, ge=0.0, le=1.0)


class ChronosSettings(BaseModel):
    """Chronos recycler (Living Demo W15)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_entries_per_pass: int = Field(default=100, ge=1, le=1000)
    min_severity_for_demotion: Literal["medium", "high", "critical"] = "medium"
    confidence_demote_delta: float = Field(default=0.1, ge=0.0, le=1.0)
    negative_edge_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    negative_edge_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    hard_delete_enabled: bool = False


class NemesisSettings(BaseModel):
    """Nemesis structural auditor (Living Demo W16)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_findings_per_pass: int = Field(default=50, ge=1, le=500)
    high_confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    low_evidence_source_count: int = Field(default=1, ge=0, le=10)
    contradiction_confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    contradiction_weight_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    autobahn_pheromone_delta_threshold: float = Field(default=0.25, ge=0.0, le=1.0)


class ErisSettings(BaseModel):
    """Eris red-team harness (Living Demo W16)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_probes_per_campaign: int = Field(default=10, ge=1, le=100)
    fixture_mode_required: bool = True


class CuriositySettings(BaseModel):
    """Stub detection + blind-spot aggregation (PHX-0058 Phase 1 / W3)."""

    model_config = ConfigDict(extra="forbid")

    stub_thresholds: StubThresholds = Field(default_factory=StubThresholds)
    window_days: float = Field(default=30.0, ge=0.0)
    min_hits: int = Field(default=3, ge=2)
    aggregation_interval_s: float = Field(default=86400.0, ge=0.0)
    growth_bridge: GrowthBridgeSettings = Field(default_factory=GrowthBridgeSettings)
    argus: ArgusSettings = Field(default_factory=ArgusSettings)
    research_planner: ResearchPlannerSettings = Field(default_factory=ResearchPlannerSettings)
    evaluator: EvaluatorSettings = Field(default_factory=EvaluatorSettings)
    athene: AtheneSettings = Field(default_factory=AtheneSettings)
    chronos: ChronosSettings = Field(default_factory=ChronosSettings)
    nemesis: NemesisSettings = Field(default_factory=NemesisSettings)
    eris: ErisSettings = Field(default_factory=ErisSettings)


class MnemosyneSettings(BaseModel):
    """Mnemosyne meta-cognitive auditor (PHX-0071 Phase 1 / W5)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True)
    classifier_mode: Literal["heuristic_only", "heuristic_with_llm_fallback"] = (
        "heuristic_with_llm_fallback"
    )
    window_days: float = Field(default=14.0, ge=1.0)
    min_observations: int = Field(default=3, ge=2)
    aggregation_interval_s: float = Field(default=86400.0, ge=0.0)
    max_llm_classifications_per_hour: int = Field(default=30, ge=0)
    llm_classification_max_cost_eur: float = Field(default=0.001, ge=0.0)


class Settings(BaseSettings):
    """Top-level Theogony settings.

    Construction order, highest precedence first:
        1. explicit constructor kwargs
        2. process environment variables
        3. ``.env`` in the working directory
        4. field defaults
    """

    openai_api_key: SecretStr | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
        description="Used by OpenAILLMProvider when provider=openai.",
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        alias="ANTHROPIC_API_KEY",
        description="Used by AnthropicLLMProvider only when provider=anthropic.",
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        alias="GEMINI_API_KEY",
        description=(
            "Preferred Google AI Studio key for Gemini. Falls back to "
            "GOOGLE_API_KEY (also read) if unset."
        ),
    )
    google_api_key: SecretStr | None = Field(
        default=None,
        alias="GOOGLE_API_KEY",
        description="Alternative Google AI Studio key, read alongside GEMINI_API_KEY.",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    store: StoreSettings = Field(default_factory=StoreSettings)
    oneiros: OneirosSettings = Field(default_factory=OneirosSettings)
    report: ReportSettings = Field(default_factory=ReportSettings)
    wikidata_cache: WikidataCacheSettings = Field(default_factory=WikidataCacheSettings)
    mcp_append: McpAppendSettings = Field(default_factory=McpAppendSettings)
    hosted: HostedSettings = Field(default_factory=HostedSettings)
    relevance: RelevanceSettings = Field(default_factory=RelevanceSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    clustering: ClusteringSettings = Field(default_factory=ClusteringSettings)
    curiosity: CuriositySettings = Field(default_factory=CuriositySettings)
    mnemosyne: MnemosyneSettings = Field(default_factory=MnemosyneSettings)
    morpheus: MorpheusSettings = Field(default_factory=MorpheusSettings)
    depth_band: DepthBandSettings = Field(default_factory=DepthBandSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    cockpit: CockpitSettings = Field(default_factory=CockpitSettings)

    data_dir: Path = Field(
        default=Path("data"),
        description=(
            "Root directory for SQLite databases, run-report JSON, "
            "ingest checkpoints, and other system-owned artefacts."
        ),
    )
    log_level: str = Field(
        default="INFO",
        description="Python logging level name; consumed by config.logging.setup_logging.",
    )

    @property
    def run_reports_dir(self) -> Path:
        """Where :class:`~theogony.reporting.writer.RunReportWriter` writes JSON.

        Layout (Plan §2.11.3): ``{data_dir}/run_reports/{ingest|query|oneiros}/{run_id}.json``.
        """
        return self.data_dir / "run_reports"

    @property
    def wikidata_cache_path(self) -> Path:
        """Default on-disk location for the persistent Wikidata cache.

        W6 (PR #33): one file per ``data_dir``. Removing the file is the
        documented "invalidate the cache" lever; there is no admin
        command intentionally.
        """
        return self.data_dir / "wikidata_cache.sqlite"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="THEOGONY_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    def active_llm_api_key(self) -> SecretStr | None:
        """Return the API key required by the currently selected provider.

        Centralises the only place in the codebase where the
        provider-name → key mapping is encoded, so individual provider
        modules do not need to re-implement the fallback rules.
        """
        match self.llm.provider:
            case "openai":
                return self.openai_api_key
            case "anthropic":
                return self.anthropic_api_key
            case "gemini":
                return self.gemini_api_key or self.google_api_key
            case "stub":
                return None
