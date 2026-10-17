#!/usr/bin/env python
"""Drive `theogony mcp` over stdio the way an MCP host does, and fail loudly.

    python scripts/mcp_probe.py [theogony-executable] [working-directory]

Part of the fresh-clone probe (`scripts/fresh_clone_probe.sh`, PHX-1111). It
checks what no unit test can see from inside a configured environment:

    the server completes its handshake without any API key
    nothing but JSON-RPC reaches stdout          (a log line there is a broken frame)
    `pantheon_ask` returns a constellation       (retrieval needs no language model)
    `synthesize: false` returns the structure alone
    an unknown node id comes back as a tool error, not as a successful apology
    `mesh_status` / `mesh_ask` are offered; with a workspace open, `mesh_ask`
        returns nodes, edges and the measured rendering (PHX-1112); without one,
        both say so as a tool error that names the way to get a workspace

Exit code 0 only if all of that holds.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class _FrameErrors(logging.Handler):
    """Counts the lines the client could not parse as JSON-RPC."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "Failed to parse JSONRPC" in record.getMessage():
            self.count += 1


def _payload(result: Any) -> dict[str, Any]:
    text = " ".join(getattr(c, "text", "") for c in result.content)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}
    return loaded if isinstance(loaded, dict) else {"_raw": loaded}


def _is_error(result: Any) -> bool:
    return bool(getattr(result, "is_error", getattr(result, "isError", False)))


async def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "theogony"
    cwd = sys.argv[2] if len(sys.argv) > 2 else None
    frames = _FrameErrors()
    logging.getLogger().addHandler(frames)
    logging.getLogger("mcp").addHandler(frames)

    failures: list[str] = []
    started = time.perf_counter()
    params = StdioServerParameters(command=command, args=["mcp"], cwd=cwd)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await asyncio.wait_for(session.initialize(), timeout=180)
        print(f"handshake        {time.perf_counter() - started:5.1f} s")

        tools = {t.name for t in (await session.list_tools()).tools}
        print(f"tools            {sorted(tools)}")
        if "pantheon_ask" not in tools:
            failures.append("pantheon_ask is not offered")

        status = _payload(await session.call_tool("pantheon_status", {}))
        print(
            f"status           llm_available={status.get('llm_available')} "
            f"answer_mode={status.get('answer_mode')} store={status.get('store')}"
        )

        question = {"q": "What is the Chronik?"}
        t = time.perf_counter()
        asked = await session.call_tool("pantheon_ask", question)
        answer = _payload(asked)
        nodes = len(answer.get("constellation", {}).get("nodes", []))
        print(
            f"pantheon_ask     {time.perf_counter() - t:5.1f} s  "
            f"answer_mode={answer.get('answer_mode')} "
            f"nodes={nodes} cited={len(answer.get('cited_node_ids', []))}"
        )
        if _is_error(asked) or nodes == 0:
            failures.append(f"pantheon_ask returned no constellation: {str(answer)[:200]}")

        bare = _payload(await session.call_tool("pantheon_ask", {**question, "synthesize": False}))
        print(
            f"synthesize=false answer={bare.get('answer')!r} answer_mode={bare.get('answer_mode')}"
        )
        if bare.get("answer") is not None or bare.get("answer_mode") != "none":
            failures.append("synthesize=false still returned an answer")

        missing = await session.call_tool("pantheon_node", {"node_id": "AKA-NOPE"})
        print(f"unknown node     is_error={_is_error(missing)}")
        if not _is_error(missing):
            failures.append("an unknown node id was reported as a successful call")

        # The mesh, where the measured work lives (PHX-1112). Three states, not
        # two: no workspace open; one open that holds no nodes (an initialised
        # default root is a workspace); one with content.
        if not {"mesh_ask", "mesh_status"} <= tools:
            failures.append("mesh_ask / mesh_status are not offered")
        else:
            available = bool(status.get("mesh", {}).get("available"))
            mesh_status = await session.call_tool("mesh_status", {})
            mesh_payload = _payload(mesh_status)
            if not available:
                print(f"mesh_status      no workspace open: is_error={_is_error(mesh_status)}")
                if not _is_error(mesh_status) or "theogony mesh" not in str(mesh_payload):
                    failures.append(
                        "without a workspace, mesh_status must fail and say how to get one"
                    )
                asked_mesh = await session.call_tool("mesh_ask", {"q": "Who is Cronos?"})
                if not _is_error(asked_mesh):
                    failures.append("without a workspace, mesh_ask was reported as a success")
            else:
                nodes_in_mesh = int(mesh_payload.get("consolidated_nodes") or 0)
                embedder = mesh_payload.get("embedder", {})
                print(
                    f"mesh_status      nodes={nodes_in_mesh} "
                    f"edges={mesh_payload.get('mesh_edges')} "
                    f"ticks={mesh_payload.get('tick_count')} "
                    f"embedder_matches={embedder.get('matches_workspace')}"
                )
                if _is_error(mesh_status):
                    failures.append(f"mesh_status failed: {str(mesh_payload)[:200]}")
                t = time.perf_counter()
                asked_mesh = await session.call_tool(
                    "mesh_ask", {"q": "Who are the children of Cronos?"}
                )
                mesh_answer = _payload(asked_mesh)
                c = mesh_answer.get("constellation", {})
                material = mesh_answer.get("material") or ""
                _, _, relations = material.partition("Relations between them:")
                print(
                    f"mesh_ask         {time.perf_counter() - t:5.1f} s  "
                    f"verdict={mesh_answer.get('verdict')} "
                    f"nodes={len(c.get('nodes', []))} edges={len(c.get('edges', []))} "
                    f"relations_shown={relations.count(chr(10) + '- ')} "
                    f"run_id={str(mesh_answer.get('run_id'))[:8]}"
                )
                if _is_error(asked_mesh):
                    failures.append(
                        f"mesh_ask failed on an open workspace: {str(mesh_answer)[:200]}"
                    )
                elif nodes_in_mesh == 0:
                    # Honest failure has a shape: a structured "poor" report, not an
                    # error and not an invented constellation.
                    if mesh_answer.get("verdict") != "poor" or c.get("nodes"):
                        failures.append(
                            "over an empty workspace mesh_ask must report verdict=poor "
                            f"with no nodes: {str(mesh_answer)[:200]}"
                        )
                elif not c.get("nodes"):
                    failures.append(f"mesh_ask returned no constellation: {str(mesh_answer)[:200]}")
                elif not c.get("edges"):
                    failures.append("mesh_ask returned nodes but no edges")
                elif "Entities:" not in material:
                    failures.append("mesh_ask returned no rendered material")

    print(f"stdout frames    {frames.count} line(s) the client could not parse as JSON-RPC")
    if frames.count:
        failures.append(f"{frames.count} non-protocol line(s) on stdout")

    for failure in failures:
        print(f"FAIL  {failure}")
    print("ok" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
