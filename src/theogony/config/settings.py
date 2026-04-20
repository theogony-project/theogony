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

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "openai", "anthropic", "stub"]


class LLMSettings(BaseModel):
    """Selection and tuning of the active LLMProvider.

    The default is **Anthropic ``claude-haiku-4-5-20251001``**: prepaid
    API credits and predictable billing are a better fit for day-to-day
    ingest / demo runs than Gemini's free-tier daily caps, and Claude
    Haiku 4.5 follows literary entity / relation extraction
    instructions (German names, transliteration, relation
    directionality) qualitatively cleaner than the OpenAI alternative
    at the same tier. OpenAI ``gpt-4o-mini`` and Gemini
    ``gemini-2.5-flash-lite`` remain first-class options (Plan §3.3a
    pricing table) via ``THEOGONY_LLM__PROVIDER=openai`` or
    ``THEOGONY_LLM__PROVIDER=gemini``.

    The PR #30 default ``claude-3-5-haiku-20241022`` was retired by
    Anthropic between SDK 0.30 (the original pin) and current accounts
    — the W5 validation run discovered it returns 404 on new keys.
    Haiku 4.5 is the spiritual successor at +25% list price.

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

    @model_validator(mode="after")
    def _default_model_id_for_provider(self) -> Self:
        if self.model_id.strip():
            return self
        defaults: dict[LLMProviderName, str] = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-haiku-4-5-20251001",
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
