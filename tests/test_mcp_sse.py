"""Integration test for MCP HTTP/SSE transport (PHX-0066 Phase 1).

Gated behind ``THEOGONY_TEST_SSE=1`` because startup loads the embedder
and the bundled ``pantheon_self`` seed (~5 s on a warm laptop).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import time
from contextlib import suppress
from pathlib import Path

import httpx
import pytest

mcp_installed = importlib.util.find_spec("mcp") is not None
pytestmark = [
    pytest.mark.skipif(not mcp_installed, reason="mcp extra not installed"),
    pytest.mark.skipif(
        os.environ.get("THEOGONY_TEST_SSE") != "1",
        reason="set THEOGONY_TEST_SSE=1 to run the slow SSE integration test",
    ),
    pytest.mark.asyncio,
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "tgdata"
    d.mkdir()
    monkeypatch.setenv("THEOGONY_DATA_DIR", str(d))
    return d


async def _wait_health(url: str, timeout_s: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_s
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                r = await client.get(url, timeout=2.0)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    return
            except (httpx.HTTPError, ValueError, KeyError):
                pass
            await asyncio.sleep(0.4)
    raise RuntimeError(f"health check never succeeded for {url}")


async def test_sse_tools_list_end_to_end(isolated_data_dir: Path) -> None:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    from theogony.mcp.server import serve_sse
    from theogony.seeds import pantheon_self_dump_path

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    task = asyncio.create_task(
        serve_sse(host="127.0.0.1", port=port, seed_path=pantheon_self_dump_path()),
        name="mcp-sse-server",
    )
    try:
        await _wait_health(f"{base}/health")
        async with sse_client(f"{base}/sse", timeout=30.0, sse_read_timeout=120.0) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {t.name for t in listed.tools}
                assert names == {
                    "pantheon_ask",
                    "pantheon_node",
                    "pantheon_status",
                    "pantheon_reports_list",
                    "pantheon_reports_show",
                }
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
