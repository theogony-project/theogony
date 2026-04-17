"""Tests for theogony.config.settings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from theogony.config.settings import (
    EmbeddingSettings,
    LLMSettings,
    Neo4jSettings,
    Settings,
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
    def test_default_llm_provider_is_gemini_2_5_flash_lite(self) -> None:
        s = Settings()
        assert s.llm.provider == "gemini"
        assert s.llm.model_id == "gemini-2.5-flash-lite"

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
        monkeypatch.setenv("THEOGONY_LLM__MODEL_ID", "claude-3-5-haiku")
        monkeypatch.setenv("THEOGONY_NEO4J__PASSWORD", "from-env")
        monkeypatch.setenv("THEOGONY_LOG_LEVEL", "DEBUG")
        s = Settings()
        assert s.llm.provider == "anthropic"
        assert s.llm.model_id == "claude-3-5-haiku"
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
