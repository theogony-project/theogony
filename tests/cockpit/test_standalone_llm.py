"""Standalone cockpit loads LLM from the same env as the full app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from theogony.agents.llm import StubLLMProvider
from theogony.cockpit.standalone_app import _standalone_llm, _standalone_settings, app
from theogony.config.settings import EmbeddingSettings, LLMSettings, Settings

_SEED_EMB = EmbeddingSettings(dim=384, model_id="BAAI/bge-small-en-v1.5")


def test_standalone_settings_pins_seed_embedding_dim() -> None:
    s = _standalone_settings()
    assert s.embedding.dim == 384
    assert "bge-small" in s.embedding.model_id.lower()


def test_standalone_llm_falls_back_when_anthropic_key_missing() -> None:
    s = Settings(
        anthropic_api_key=None,  # type: ignore[arg-type]
        llm=LLMSettings(provider="anthropic"),
        embedding=_SEED_EMB,
    )
    llm = _standalone_llm(s)
    assert isinstance(llm, StubLLMProvider)


def test_standalone_llm_accepts_explicit_stub_provider() -> None:
    s = Settings(
        llm=LLMSettings(provider="stub"),
        embedding=_SEED_EMB,
    )
    llm = _standalone_llm(s)
    assert isinstance(llm, StubLLMProvider)


class _FakeLiveLLM:
    model_id = "claude-sonnet-4-6"


def test_explorer_page_context_stub_llm_instance() -> None:
    from theogony.cockpit.explorer import explorer_page_context

    s = Settings(llm=LLMSettings(provider="anthropic", model_id="claude-sonnet-4-6"))
    ctx = explorer_page_context(s, StubLLMProvider(model_id="stub-llm"))
    assert ctx["explorer_llm_stub"] is True


def test_explorer_page_context_non_stub_llm() -> None:
    from theogony.cockpit.explorer import explorer_page_context

    s = Settings(llm=LLMSettings(provider="anthropic", model_id="claude-sonnet-4-6"))
    ctx = explorer_page_context(s, _FakeLiveLLM())
    assert ctx["explorer_llm_stub"] is False
    assert "anthropic" in ctx["explorer_llm_label"]
    assert "claude-sonnet-4-6" in ctx["explorer_llm_label"]


def test_cockpit_standalone_health_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEOGONY_COCKPIT__KNOWLEDGE_STORE", "memory")
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "cockpit"
    assert payload["store"] == "memory"
