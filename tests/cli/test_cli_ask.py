"""
``theogony ask`` CLI integration (Plan §3.8 layer 4 / E9 brief).

Asserts the command:
- exits 0 when the pipeline returns an answer with citations;
- renders the verdict-coloured Rich panel containing the [AKA-…] cite;
- exits non-zero with a red panel when the LLM provider is missing.

The test seeds an InMemoryKnowledgeStore with one Hedin/Tibet edge,
monkey-patches ``_open_store`` so the CLI uses the seeded store, and
swaps ``build_llm_from_settings`` for a StubLLMProvider that scripts
a citation. CliRunner captures stdout for assertion.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from theogony.agents.llm import StubLLMProvider
from theogony.cli import app
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.stores import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", location=loc, language="en")


def _build_seeded_store() -> tuple[InMemoryKnowledgeStore, str, str]:
    """Return a store pre-populated with two nodes + one edge.

    Returns the store + the two node ids so the test can compose the
    Stub LLM citation script.
    """
    store = InMemoryKnowledgeStore()
    hedin = KnowledgeNode(
        label="Sven Hedin",
        node_type=NodeType.PERSON,
        source_ref=_src("loc:hedin"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="test-embedder@v1",
    )
    hedin.scores.confidence = 0.9
    tibet = KnowledgeNode(
        label="Tibet",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:tibet"),
        embedding=[0.9, 0.1, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="test-embedder@v1",
    )
    edge = KnowledgeEdge(
        source_id=hedin.id,
        target_id=tibet.id,
        relation_type="EXPLORED",
        evidence_span="Sven Hedin explored Tibet.",
    )
    asyncio.run(store.upsert_node(hedin))
    asyncio.run(store.upsert_node(tibet))
    asyncio.run(store.upsert_edge(edge))
    return store, hedin.id, tibet.id


class _TinyEmbedder:
    """4-dim constant embedder that needs no model download."""

    @property
    def model_id(self) -> str:
        return "test-embedder@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def _patch_cli(
    monkeypatch: pytest.MonkeyPatch,
    store: InMemoryKnowledgeStore,
    llm: StubLLMProvider,
) -> None:
    """Swap _open_store for the seeded store, build_llm_from_settings for a
    StubLLM, and the embedder factory for a constant-axis _TinyEmbedder so
    no BGE-small download is needed in CI sandboxes without HF access."""
    import theogony.cli as cli_mod

    @asynccontextmanager
    async def _yield_seeded(*args: object, **kwargs: object) -> AsyncIterator[object]:
        yield store

    monkeypatch.setattr(cli_mod, "_open_store", _yield_seeded)
    monkeypatch.setattr(cli_mod, "build_llm_from_settings", lambda _settings: llm)
    monkeypatch.setattr(
        cli_mod,
        "LocalSentenceTransformerEmbedder",
        lambda **_kw: _TinyEmbedder(),
    )


def test_ask_renders_verdict_panel_with_citation(
    cli_runner: CliRunner,
    cli_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, hedin_id, tibet_id = _build_seeded_store()
    llm = StubLLMProvider(default=f"Sven Hedin explored Tibet [{hedin_id}] [{tibet_id}].")
    _patch_cli(monkeypatch, store, llm)

    result = cli_runner.invoke(
        app, ["ask", "Wer war Sven Hedin?", "--store", "memory", "--k", "10"]
    )
    assert result.exit_code == 0, result.stdout
    # Citation rendered.
    assert hedin_id in result.stdout
    assert tibet_id in result.stdout
    # Panel chrome.
    assert "Wer war Sven Hedin?" in result.stdout
    assert "Cited:" in result.stdout
    # Verdict label appears (one of the styles — exact verdict depends
    # on the synthesised tokens, but it must be present).
    assert any(v in result.stdout for v in ("good", "partial", "poor", "failed"))


def test_ask_missing_llm_exits_with_red_panel(
    cli_runner: CliRunner,
    cli_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When build_llm_from_settings raises (e.g. no API key), the
    CLI returns a clean red panel + exit code 1 — never a stack trace."""
    import theogony.cli as cli_mod

    def _explode(_settings: object) -> object:
        raise ValueError("no API key for provider 'openai'")

    monkeypatch.setattr(cli_mod, "build_llm_from_settings", _explode)
    result = cli_runner.invoke(app, ["ask", "anything", "--store", "memory"])
    assert result.exit_code == 1
    assert "LLM provider unavailable" in result.stdout
