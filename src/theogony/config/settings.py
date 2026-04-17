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
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "openai", "anthropic", "stub"]


class LLMSettings(BaseModel):
    """Selection and tuning of the active LLMProvider.

    The default is Gemini 2.5 Flash Lite per Plan §3.3a: it has the most
    generous free tier (zero-friction onboarding for new contributors),
    a 1 M context window (hedge for PID-2 hybrid extraction), and the
    cheapest per-token pricing of the three first-class providers.

    Switch providers without touching code via
    ``THEOGONY_LLM__PROVIDER=openai|anthropic|stub``.
    """

    provider: LLMProviderName = "gemini"
    model_id: str = "gemini-2.5-flash-lite"
    timeout_s: float = Field(default=30.0, gt=0.0)
    max_concurrency: int = Field(default=8, ge=1)


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
        description="Used by GeminiLLMProvider only when provider=openai.",
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
