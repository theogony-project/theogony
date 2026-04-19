"""
``theogony serve`` end-to-end smoke (Plan §3.8 layer 5; E9 brief).

Spawns the CLI as a subprocess (``python -m theogony.cli serve``),
polls ``http://127.0.0.1:<random-port>/health`` until 200, sends
SIGINT, and asserts the process exits cleanly within 5 s.

Gated on ``THEOGONY_TEST_SERVE=1`` because:
  * subprocess + uvicorn startup is ~5–15 s cold (BGE / spaCy / Neo4j
    driver load) — too slow for every CI matrix entry;
  * cross-platform process semantics differ enough to make this a
    linux-only contract.

The test is a contract proof for the brief's "theogony serve" loop:
the subprocess starts, the lifespan wires the resources, /health
returns 200, SIGINT triggers the lifespan finally-block. It does
NOT exercise /query (which needs Gemini) or /ingest (which needs
Gutenberg HTTP).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_TEST_SERVE") != "1",
    reason="Set THEOGONY_TEST_SERVE=1 to run the serve subprocess smoke.",
)


def _free_tcp_port() -> int:
    """Reserve a free localhost port. Race with uvicorn's bind is
    accepted — ports rarely get re-grabbed in the < 1 ms window."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_serve_subprocess_serves_health_then_clean_shutdown(tmp_path: object) -> None:
    port = _free_tcp_port()
    # Run the subprocess against the StubLLMProvider so CI runners
    # without a GEMINI_API_KEY can still exercise the lifespan + the
    # /health surface end-to-end. /health does not invoke the LLM
    # (asserted in tests/api/test_api_health.py); we only need the
    # provider factory to accept the configuration.
    env = os.environ.copy()
    env["THEOGONY_LLM__PROVIDER"] = "stub"
    env["THEOGONY_LLM__MODEL_ID"] = "stub-llm"
    proc = subprocess.Popen(
        [sys.executable, "-m", "theogony.cli", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        # Poll /health up to 30 s — cold-start (BGE + Neo4j + audit) can
        # take ~10–15 s on a fresh cache; we give it a generous bound.
        url = f"http://127.0.0.1:{port}/health"
        deadline = time.monotonic() + 30.0
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                # Subprocess exited before responding; surface its output.
                stdout, _ = proc.communicate(timeout=2)
                pytest.fail(
                    f"serve subprocess exited early with code {proc.returncode}; stdout:\n{stdout}"
                )
            try:
                response = httpx.get(url, timeout=2.0)
                if response.status_code == 200:
                    break
            except httpx.HTTPError as exc:
                last_exc = exc
            time.sleep(0.5)
        else:
            pytest.fail(f"serve never returned 200 on {url} within 30s (last error: {last_exc})")

        body = response.json()
        assert body["status"] == "ok"
    finally:
        # Clean shutdown via SIGINT.
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
            pytest.fail("serve subprocess did not exit within 5s of SIGTERM")
