"""
Smoke tests for the Theogony MCP server module.

Full end-to-end MCP testing requires a real Neo4j store, a real LLM
provider, and an MCP-protocol client driving stdio — beyond a unit
test budget. These tests verify the contract that holds without that
stack:

- the module imports cleanly when the ``mcp`` extra is installed
- the documented public API exists
- the tool descriptors match what the registered MCP server hands out
- ``build_server`` does not require live resources to construct
- ``tool_reports_*`` work against a temp directory of fake reports
- ``tool_node`` and ``tool_status`` short-circuit cleanly via fakes

Anything that needs a real LLM round-trip (``tool_ask``) is left to
the existing characterization layer (Plan §3.8 layer 6) and to live
``theogony mcp`` runs against a populated store.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

mcp_installed = importlib.util.find_spec("mcp") is not None
pytestmark = pytest.mark.skipif(
    not mcp_installed,
    reason='mcp extra not installed; install with `pip install -e ".[mcp]"`',
)


# --------------------------------------------------------------------------
# Fakes — deliberately minimal so the tools' shape is what's tested,
# not the full pipeline machinery.
# --------------------------------------------------------------------------


@dataclass
class _FakeSettings:
    """Subset of Settings the MCP tools actually read."""

    run_reports_dir: Path
    llm: Any
    embedding: Any


class _Bag:
    """Generic attribute holder for nested settings shape."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeStore:
    """Minimal KnowledgeStore stand-in — only the methods MCP tools call."""

    def __init__(self) -> None:
        self._nodes: dict[str, Any] = {}

    async def health(self) -> dict[str, Any]:
        return {"backend": "fake"}

    async def get_node(self, node_id: str) -> Any:
        return self._nodes.get(node_id)

    async def get_neighborhood(self, node_id: str, depth: int, min_weight: float) -> Any:
        from theogony.core.model import Constellation

        return Constellation(query=node_id, nodes=[], edges=[], suggested_sources=[], gaps=[])


def _make_resources(tmp_path: Path) -> Any:
    """Build a stub :class:`McpResources` for tool-shape tests.

    Pipeline-using tools (``tool_ask``) cannot be exercised against a
    stub — they need a real LLM + embedder + store — so they are not
    called in this file.
    """
    from theogony.mcp.server import McpResources

    settings = _FakeSettings(
        run_reports_dir=tmp_path / "run_reports",
        llm=_Bag(provider="stub", model_id="stub-llm"),
        embedding=_Bag(model_id="bge-small-en", dim=384),
    )
    return McpResources(
        settings=settings,  # type: ignore[arg-type]
        audit=None,  # type: ignore[arg-type]
        wd_cache=None,
        embedder=None,  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        store=_FakeStore(),  # type: ignore[arg-type]
        report_writer=None,  # type: ignore[arg-type]
        mcp_ask_blocked_message=None,
    )


def _write_report(tmp_path: Path, rtype: str, run_id: str, payload: dict[str, Any]) -> None:
    d = tmp_path / "run_reports" / rtype
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run_id}.json").write_text(json.dumps(payload), encoding="utf-8")


# --------------------------------------------------------------------------
# Module-level public API
# --------------------------------------------------------------------------


def test_module_imports_and_exports_public_api() -> None:
    from theogony.mcp import server

    for name in (
        "McpResources",
        "build_server",
        "open_resources",
        "serve_sse",
        "serve_stdio",
        "tool_ask",
        "tool_node",
        "tool_reports_list",
        "tool_reports_show",
        "tool_status",
    ):
        assert hasattr(server, name), f"missing public export: {name!r}"


def test_tool_descriptors_match_registered_tool_names() -> None:
    """The five Gen 1 read-side tools are all declared and consistent."""
    from theogony.mcp.server import _tool_descriptors

    descriptors = _tool_descriptors()
    names = {d["name"] for d in descriptors}
    expected = {
        "pantheon_ask",
        "pantheon_node",
        "pantheon_status",
        "pantheon_reports_list",
        "pantheon_reports_show",
    }
    assert names == expected
    for d in descriptors:
        assert d["inputSchema"]["type"] == "object"
        assert d["inputSchema"]["additionalProperties"] is False


def test_build_server_does_not_require_live_resources(tmp_path: Path) -> None:
    """``build_server`` must register handlers without touching the store/LLM.

    This catches API-shape regressions in the mcp SDK during upgrades.
    """
    from theogony.mcp.server import build_server

    server = build_server(_make_resources(tmp_path))
    # mcp.server.Server stores registered handlers internally; the
    # smoke is that build_server(...) does not raise during registration.
    assert server is not None
    assert getattr(server, "name", None) == "theogony"


# --------------------------------------------------------------------------
# Pure-function tools
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_status_returns_expected_shape(tmp_path: Path) -> None:
    from theogony import __version__
    from theogony.mcp.server import tool_status

    res = _make_resources(tmp_path)
    payload = await tool_status(res)
    assert payload["version"] == __version__
    assert payload["store"] == "fake"
    assert payload["llm_provider"] == "stub"
    assert payload["llm_model"] == "stub-llm"
    assert payload["embedding_model"] == "bge-small-en"
    assert payload["embedding_dim"] == 384
    assert payload["report_counts"] == {"ingest": 0, "query": 0, "oneiros": 0}


@pytest.mark.asyncio
async def test_tool_node_returns_error_for_unknown_id(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_node

    res = _make_resources(tmp_path)
    payload = await tool_node(res, node_id="AKA-does-not-exist")
    assert "error" in payload


def test_tool_reports_list_filters_and_orders(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_reports_list

    res = _make_resources(tmp_path)
    _write_report(
        tmp_path,
        "query",
        "01J0000000000000000000000A",
        {"run_id": "01J0000000000000000000000A", "report_type": "query", "verdict": "good"},
    )
    _write_report(
        tmp_path,
        "ingest",
        "01J0000000000000000000000B",
        {"run_id": "01J0000000000000000000000B", "report_type": "ingest", "verdict": "good"},
    )
    rows_all = tool_reports_list(res, last=10)
    assert len(rows_all) == 2
    assert rows_all[0]["run_id"] > rows_all[1]["run_id"]  # newest first

    rows_query = tool_reports_list(res, report_type="query", last=10)
    assert len(rows_query) == 1
    assert rows_query[0]["type"] == "query"


def test_tool_reports_show_supports_prefix_and_returns_error_for_missing(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_reports_show

    res = _make_resources(tmp_path)
    _write_report(
        tmp_path,
        "query",
        "01J0000000000000000000000A",
        {"run_id": "01J0000000000000000000000A", "verdict": "good"},
    )
    full = tool_reports_show(res, run_id="01J0000000000000000000000A")
    assert full["run_id"] == "01J0000000000000000000000A"

    prefix = tool_reports_show(res, run_id="01J0000000000000000000000")
    assert prefix["run_id"] == "01J0000000000000000000000A"

    missing = tool_reports_show(res, run_id="DOES-NOT-EXIST")
    assert "error" in missing


# --------------------------------------------------------------------------
# Lifespan smoke — verify open_resources is an async context manager
# without actually opening Neo4j / loading the embedder.
# --------------------------------------------------------------------------


def test_open_resources_is_async_context_manager() -> None:
    from theogony.mcp.server import open_resources

    cm = open_resources()
    assert isinstance(cm, AsyncIterator) or hasattr(cm, "__aenter__")
