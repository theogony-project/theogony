"""Unit tests for MCP ``pantheon_chronicle_append`` (bounded Chronik growth)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from theogony.config.settings import McpAppendSettings, Settings
from theogony.mcp.server import McpResources, tool_chronicle_append
from theogony.stores.memory import InMemoryKnowledgeStore

mcp_installed = importlib.util.find_spec("mcp") is not None
pytestmark = pytest.mark.skipif(
    not mcp_installed,
    reason='mcp extra not installed; install with `pip install -e ".[mcp]"`',
)


class _FixtureEmbedder:
    """Deterministic tiny vectors matching Settings.embedding.dim (384)."""

    model_id = "fixture-embedder@v1"

    def __init__(self, *, dim: int = 384) -> None:
        self._dim = dim

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i, _ in enumerate(texts):
            v = [0.0] * self._dim
            v[0] = float(i + 1) * 0.01
            out.append(v)
        return out


def _resources(tmp_path: Path, **settings_kw: object) -> McpResources:
    settings = Settings(data_dir=tmp_path, **settings_kw)
    return McpResources(
        settings=settings,
        audit=None,  # type: ignore[arg-type]
        wd_cache=None,
        embedder=_FixtureEmbedder(dim=settings.embedding.dim),
        llm=None,  # type: ignore[arg-type]
        store=InMemoryKnowledgeStore(),
        report_writer=None,  # type: ignore[arg-type]
        mcp_ask_blocked_message=None,
    )


@pytest.mark.asyncio
async def test_chronicle_append_upserts_in_memory(tmp_path: Path) -> None:
    res = _resources(tmp_path)
    payload = await tool_chronicle_append(
        res,
        fragments=[
            {"title": "  Alpha note ", "body": "  body one  "},
            {"title": "Beta", "body": "second"},
        ],
        context_note="  session ctx  ",
    )
    assert "error" not in payload
    assert payload["fragment_count"] == 2
    ids = payload["upserted_node_ids"]
    assert len(ids) == 2

    n0 = await res.store.get_node(ids[0])
    n1 = await res.store.get_node(ids[1])
    assert n0 is not None and n1 is not None
    assert n0.label == "Alpha note"
    assert n0.description == "body one"
    assert n0.source_ref.source_type == "mcp_agent"
    assert n0.properties.get("context_note") == "session ctx"
    assert n1.label == "Beta"
    assert n1.properties.get("context_note") == "session ctx"


@pytest.mark.asyncio
async def test_chronicle_append_disabled(tmp_path: Path) -> None:
    res = _resources(tmp_path, mcp_append=McpAppendSettings(enabled=False))
    payload = await tool_chronicle_append(
        res,
        fragments=[{"title": "x", "body": "y"}],
    )
    assert "error" in payload


@pytest.mark.asyncio
async def test_chronicle_append_rejects_too_many_fragments(tmp_path: Path) -> None:
    res = _resources(tmp_path, mcp_append=McpAppendSettings(max_fragments_per_call=2))
    payload = await tool_chronicle_append(
        res,
        fragments=[
            {"title": "a", "body": "1"},
            {"title": "b", "body": "2"},
            {"title": "c", "body": "3"},
        ],
    )
    assert "error" in payload
    assert "too many" in payload["error"]


@pytest.mark.asyncio
async def test_chronicle_append_rejects_oversized_total(tmp_path: Path) -> None:
    res = _resources(
        tmp_path,
        mcp_append=McpAppendSettings(
            max_fragments_per_call=5,
            max_body_chars_per_fragment=400,
            max_total_body_chars=520,
        ),
    )
    payload = await tool_chronicle_append(
        res,
        fragments=[
            {"title": "a", "body": "x" * 280},
            {"title": "b", "body": "y" * 280},
        ],
    )
    assert "error" in payload
    assert "max_total_body_chars" in payload["error"]


@pytest.mark.asyncio
async def test_chronicle_append_no_embedder(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    res = McpResources(
        settings=settings,
        audit=None,  # type: ignore[arg-type]
        wd_cache=None,
        embedder=None,  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        store=InMemoryKnowledgeStore(),
        report_writer=None,  # type: ignore[arg-type]
        mcp_ask_blocked_message=None,
    )
    payload = await tool_chronicle_append(
        res,
        fragments=[{"title": "x", "body": "y"}],
    )
    assert payload.get("error") == "no embedder configured on this MCP session"
