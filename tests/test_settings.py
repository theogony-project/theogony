"""Tests for theogony.config.settings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from theogony.config.settings import (
    AnomalyThresholds,
    ChronicleEntryPlannerSettings,
    EmbeddingSettings,
    IngestStageBaselines,
    IngestVerdictThresholds,
    LLMSettings,
    Neo4jSettings,
    OneirosVerdictThresholds,
    QueryVerdictThresholds,
    ReportSettings,
    Settings,
    VerdictThresholds,
)


@pytest.fixture(autouse=True)
def _isolate_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Run every test from a clean cwd with no Theogony-related env vars set.

    Prevents the developer's real `.env` or shell environment (which may
    legitimately contain real API keys, per the project mandate) from
    leaking into the test process.
    """
    monkeypatch.chdir(tmp_path)
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    for name in [n for n in os.environ if n.startswith("THEOGONY_")]:
        monkeypatch.delenv(name, raising=False)


class TestSettingsDefaults:
    def test_default_llm_is_openai_gpt4o_mini_with_anthropic_fallback(self) -> None:
        s = Settings()
        assert s.llm.provider == "openai"
        assert s.llm.model_id == "gpt-4o-mini"
        assert s.llm.fallback_provider == "anthropic"
        assert s.llm.fallback_model_id == ""
        assert s.llm.resolved_fallback_model_id() == "claude-sonnet-4-6"

    def test_anthropic_primary_drops_default_fallback(self) -> None:
        s = Settings(llm=LLMSettings(provider="anthropic"))  # type: ignore[arg-type]
        assert s.llm.provider == "anthropic"
        assert s.llm.fallback_provider is None

    def test_default_embedding_is_bge_small(self) -> None:
        s = Settings()
        assert s.embedding.model_id == "BAAI/bge-small-en-v1.5"
        assert s.embedding.dim == 384

    def test_default_neo4j_targets_localhost(self) -> None:
        s = Settings()
        assert s.neo4j.uri == "bolt://localhost:7687"
        assert s.neo4j.user == "neo4j"
        assert isinstance(s.neo4j.password, SecretStr)

    def test_default_data_dir_is_data(self) -> None:
        assert Settings().data_dir == Path("data")

    def test_default_chronicle_entry_planner_enabled(self) -> None:
        assert Settings().retrieval.chronicle_entry_planner.enabled is True
        assert ChronicleEntryPlannerSettings().enabled is True

    def test_default_cockpit_demo_resolve_bound(self) -> None:
        s = Settings()
        assert s.cockpit.demo_ingest_max_resolve_mentions == 120

    def test_no_api_keys_set_by_default(self) -> None:
        s = Settings()
        assert s.openai_api_key is None
        assert s.anthropic_api_key is None
        assert s.gemini_api_key is None
        assert s.google_api_key is None


class TestSettingsFromKwargs:
    def test_kwargs_override_defaults(self) -> None:
        s = Settings(
            llm=LLMSettings(provider="openai", model_id="gpt-4o-mini"),
            embedding=EmbeddingSettings(model_id="text-embedding-3-small", dim=1536),
        )
        assert s.llm.provider == "openai"
        assert s.llm.model_id == "gpt-4o-mini"
        assert s.embedding.dim == 1536

    def test_secret_kwargs_are_wrapped(self) -> None:
        s = Settings(openai_api_key="sk-test-not-real")  # type: ignore[arg-type]
        assert isinstance(s.openai_api_key, SecretStr)
        assert s.openai_api_key.get_secret_value() == "sk-test-not-real"


class TestSettingsFromEnv:
    def test_api_keys_load_from_unprefixed_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
        monkeypatch.setenv("GEMINI_API_KEY", "g-gemini")
        monkeypatch.setenv("GOOGLE_API_KEY", "g-google")
        s = Settings()
        assert s.openai_api_key is not None
        assert s.openai_api_key.get_secret_value() == "sk-openai"
        assert s.anthropic_api_key is not None
        assert s.anthropic_api_key.get_secret_value() == "sk-anthropic"
        assert s.gemini_api_key is not None
        assert s.gemini_api_key.get_secret_value() == "g-gemini"
        assert s.google_api_key is not None
        assert s.google_api_key.get_secret_value() == "g-google"

    def test_nested_settings_use_double_underscore(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THEOGONY_LLM__PROVIDER", "anthropic")
        monkeypatch.setenv("THEOGONY_LLM__MODEL_ID", "claude-haiku-4-5")
        monkeypatch.setenv("THEOGONY_NEO4J__PASSWORD", "from-env")
        monkeypatch.setenv("THEOGONY_LOG_LEVEL", "DEBUG")
        s = Settings()
        assert s.llm.provider == "anthropic"
        assert s.llm.model_id == "claude-haiku-4-5"
        assert s.neo4j.password.get_secret_value() == "from-env"
        assert s.log_level == "DEBUG"

    def test_dotenv_file_is_loaded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "OPENAI_API_KEY=from-dotenv\nTHEOGONY_LOG_LEVEL=WARNING\n",
            encoding="utf-8",
        )
        s = Settings()
        assert s.openai_api_key is not None
        assert s.openai_api_key.get_secret_value() == "from-dotenv"
        assert s.log_level == "WARNING"


class TestSecretsNeverLeak:
    def test_repr_does_not_reveal_api_key(self) -> None:
        s = Settings(openai_api_key="sk-DO-NOT-LEAK")  # type: ignore[arg-type]
        assert "sk-DO-NOT-LEAK" not in repr(s)
        assert "sk-DO-NOT-LEAK" not in str(s)

    def test_repr_does_not_reveal_neo4j_password(self) -> None:
        s = Settings(neo4j=Neo4jSettings(password=SecretStr("super-secret-pw")))
        assert "super-secret-pw" not in repr(s)
        assert "super-secret-pw" not in str(s)

    def test_model_dump_redacts_secrets_by_default(self) -> None:
        s = Settings(openai_api_key="sk-DO-NOT-LEAK")  # type: ignore[arg-type]
        dumped = s.model_dump()
        assert "sk-DO-NOT-LEAK" not in repr(dumped)


class TestActiveLLMApiKey:
    def test_returns_openai_when_provider_is_openai(self) -> None:
        s = Settings(
            openai_api_key="sk-o",  # type: ignore[arg-type]
            llm=LLMSettings(provider="openai"),
        )
        key = s.active_llm_api_key()
        assert key is not None
        assert key.get_secret_value() == "sk-o"

    def test_returns_anthropic_when_provider_is_anthropic(self) -> None:
        s = Settings(
            anthropic_api_key="sk-a",  # type: ignore[arg-type]
            llm=LLMSettings(provider="anthropic"),
        )
        key = s.active_llm_api_key()
        assert key is not None
        assert key.get_secret_value() == "sk-a"

    def test_returns_gemini_for_gemini_provider(self) -> None:
        s = Settings(
            gemini_api_key="g-gemini",  # type: ignore[arg-type]
            llm=LLMSettings(provider="gemini"),
        )
        key = s.active_llm_api_key()
        assert key is not None
        assert key.get_secret_value() == "g-gemini"

    def test_falls_back_to_google_api_key_for_gemini_provider(self) -> None:
        s = Settings(
            google_api_key="g-google",  # type: ignore[arg-type]
            llm=LLMSettings(provider="gemini"),
        )
        key = s.active_llm_api_key()
        assert key is not None
        assert key.get_secret_value() == "g-google"

    def test_prefers_gemini_over_google_when_both_set(self) -> None:
        s = Settings(
            gemini_api_key="g-preferred",  # type: ignore[arg-type]
            google_api_key="g-fallback",  # type: ignore[arg-type]
            llm=LLMSettings(provider="gemini"),
        )
        key = s.active_llm_api_key()
        assert key is not None
        assert key.get_secret_value() == "g-preferred"

    def test_returns_none_for_stub_provider(self) -> None:
        s = Settings(
            openai_api_key="sk-o",  # type: ignore[arg-type]
            llm=LLMSettings(provider="stub"),
        )
        assert s.active_llm_api_key() is None


class TestSettingsValidation:
    def test_invalid_provider_rejected(self) -> None:
        with pytest.raises(ValueError):
            LLMSettings(provider="hallucinated")  # type: ignore[arg-type]

    def test_negative_timeout_rejected(self) -> None:
        with pytest.raises(ValueError):
            LLMSettings(timeout_s=-1.0)

    def test_zero_dim_rejected(self) -> None:
        with pytest.raises(ValueError):
            EmbeddingSettings(dim=0)


class TestReportSettings:
    def test_defaults_match_plan_2_11_2(self) -> None:
        rs = ReportSettings()
        assert rs.thresholds.ingest.poor_parse_error_rate == 0.20
        assert rs.thresholds.ingest.partial_parse_error_rate == 0.05
        assert rs.thresholds.ingest.poor_low_tier_ratio == 0.60
        assert rs.thresholds.ingest.partial_low_tier_ratio == 0.30
        assert rs.thresholds.ingest.poor_anomaly_count == 3
        assert rs.thresholds.query.poor_latency_ms == 10_000
        assert rs.thresholds.query.partial_latency_ms == 5_000
        assert rs.thresholds.query.good_high_conf_ratio == 0.5
        assert rs.thresholds.query.partial_gaps_count == 3
        assert rs.thresholds.oneiros.poor_median_vitality_shift == -0.05

    def test_anomaly_defaults_match_plan(self) -> None:
        a = ReportSettings().anomaly
        assert a.stage_slow_multiplier == 2.0
        assert a.cost_spike_multiplier == 1.5
        assert a.cost_spike_min_history == 5
        assert a.wikidata_failure_rate == 0.10
        assert a.embedding_skew_stddev_multiplier == 3.0

    def test_stage_baselines_match_plan_4_1(self) -> None:
        b = ReportSettings().stage_baselines
        assert b.acquired == 2.0
        assert b.relations_extracted == 180.0  # ~2.5 min from §4.1
        assert b.mentions_resolved == 90.0  # 60-90s from §4.1 v3

    def test_oneiros_tick_retention_default(self) -> None:
        assert ReportSettings().oneiros_tick_retention == 100

    def test_thresholds_overridable_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THEOGONY_REPORT__THRESHOLDS__INGEST__POOR_PARSE_ERROR_RATE", "0.50")
        monkeypatch.setenv("THEOGONY_REPORT__ANOMALY__STAGE_SLOW_MULTIPLIER", "3.0")
        s = Settings()
        assert s.report.thresholds.ingest.poor_parse_error_rate == 0.50
        assert s.report.anomaly.stage_slow_multiplier == 3.0

    def test_invalid_threshold_rejected(self) -> None:
        with pytest.raises(ValueError):
            IngestVerdictThresholds(poor_parse_error_rate=1.5)
        with pytest.raises(ValueError):
            QueryVerdictThresholds(poor_latency_ms=-1)
        with pytest.raises(ValueError):
            AnomalyThresholds(stage_slow_multiplier=0.0)
        with pytest.raises(ValueError):
            IngestStageBaselines(acquired=0.0)


class TestRunReportsDir:
    def test_default_run_reports_dir(self) -> None:
        s = Settings()
        assert s.run_reports_dir == s.data_dir / "run_reports"

    def test_run_reports_dir_follows_data_dir_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pathlib import Path

        monkeypatch.setenv("THEOGONY_DATA_DIR", "/tmp/theogony-test")
        s = Settings()
        assert s.run_reports_dir == Path("/tmp/theogony-test/run_reports")


class TestThresholdsRoundTrip:
    """The full thresholds tree must survive model_dump → model_validate."""

    def test_round_trip_preserves_all_values(self) -> None:
        original = ReportSettings(
            thresholds=VerdictThresholds(
                ingest=IngestVerdictThresholds(poor_parse_error_rate=0.42),
                oneiros=OneirosVerdictThresholds(poor_median_vitality_shift=-0.10),
            ),
        )
        dumped = original.model_dump()
        restored = ReportSettings.model_validate(dumped)
        assert restored.thresholds.ingest.poor_parse_error_rate == 0.42
        assert restored.thresholds.oneiros.poor_median_vitality_shift == -0.10
