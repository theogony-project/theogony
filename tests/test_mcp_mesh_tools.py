"""The mesh behind the MCP surface (PHX-1112, piece 1).

Until this existed the MCP server spoke only to the Generation-1 store, and an
agent arriving over MCP could not reach the substrate where every measurement
since July lives. These tests pin the contract of `mesh_ask` / `mesh_status`
against a mesh the PHX-1110 replay builds in a second — no LLM anywhere, not
even a stub — and drive the two tools through a real protocol session.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from theogony.mesh.eval.qa_mesh import ingest_cached_readings, reading_key
from theogony.mesh.eval.qa_retrieval import QAPassage
from theogony.mesh.runtime.oneiros_tick import MeshRuntime, mesh_workspace_exists
from theogony.reporting.writer import RunReportWriter

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason='mcp extra not installed; install with `pip install -e ".[mcp]"`',
)

DIM = 8

PASSAGES = [
    QAPassage(
        idx=0,
        title="Marie of Hanover",
        text="Marie of Hanover was the daughter of George V of Hanover. She died in Gmunden.",
    ),
    QAPassage(
        idx=1,
        title="George V of Hanover",
        text="George V of Hanover was the last King of Hanover and the son of Ernest Augustus.",
    ),
]


def _reading(*concepts: tuple[str, str], relations: list[tuple[str, str, str]]) -> dict:
    return {
        "concepts": [
            {"label": label, "entity_type": "person", "tags": [], "description": desc, "qids": []}
            for label, desc in concepts
        ],
        "relations": [
            {
                "source": s,
                "target": t,
                "relation_descriptor": d,
                "relation_kind": "hierarchy",
                "rationale": "",
            }
            for s, d, t in relations
        ],
        "paragraph_concept": None,
    }


READINGS = {
    reading_key(PASSAGES[0].text): _reading(
        ("Marie of Hanover", "Daughter of George V of Hanover; died in Gmunden."),
        ("George V of Hanover", "King of Hanover, father of Marie."),
        relations=[("Marie of Hanover", "daughter of", "George V of Hanover")],
    ),
    reading_key(PASSAGES[1].text): _reading(
        ("George V of Hanover", "Last King of Hanover, son of Ernest Augustus."),
        ("Ernest Augustus", "King of Hanover, father of George V."),
        relations=[("George V of Hanover", "son of", "Ernest Augustus")],
    ),
}


class _HashEmbedder:
    """Deterministic 8-d vectors (crc32, not the per-process `hash()`); the
    retrieval finds its seeds by name anyway."""

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim
        self.model_id = f"hash@{dim}"

    async def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            rng = np.random.default_rng(zlib.crc32(text.lower().split()[0].encode("utf-8")))
            out.append(list(rng.standard_normal(self.dim).astype(np.float32)))
        return out


@dataclass
class _Settings:
    data_dir: Path
    run_reports_dir: Path
    llm: Any
    embedding: Any


class _Bag:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeStore:
    async def health(self) -> dict[str, Any]:
        return {"backend": "fake"}


async def _mesh_async(tmp_path: Path) -> MeshRuntime:
    runtime = MeshRuntime(tmp_path / "mesh", semantic_dim=DIM, frame_dim=DIM)
    await ingest_cached_readings(runtime, PASSAGES, READINGS, source_identifier="test")
    return runtime


def _mesh(tmp_path: Path) -> MeshRuntime:
    return asyncio.run(_mesh_async(tmp_path))


def _resources(tmp_path: Path, *, mesh: MeshRuntime | None, embedder: Any = None) -> Any:
    from theogony.mcp.server import McpResources

    settings = _Settings(
        data_dir=tmp_path / "data",
        run_reports_dir=tmp_path / "data" / "run_reports",
        llm=_Bag(provider="stub", model_id="stub-llm"),
        embedding=_Bag(model_id="hash", dim=DIM),
    )
    return McpResources(
        settings=settings,  # type: ignore[arg-type]
        audit=None,  # type: ignore[arg-type]
        wd_cache=None,
        embedder=embedder or _HashEmbedder(),
        llm=None,  # type: ignore[arg-type]
        store=_FakeStore(),  # type: ignore[arg-type]
        report_writer=RunReportWriter(settings.run_reports_dir),
        mesh=mesh,
    )


def test_a_workspace_is_recognised_without_being_created(tmp_path: Path) -> None:
    """`MeshRuntime.open` initialises an empty mesh at any path; a server that
    only wants to know whether there is one must not do that."""
    assert mesh_workspace_exists(tmp_path / "nowhere") is False
    assert not (tmp_path / "nowhere").exists()
    runtime = _mesh(tmp_path)
    assert mesh_workspace_exists(runtime.root) is True


def test_mesh_status_counts_the_open_workspace(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_mesh_status

    runtime = _mesh(tmp_path)
    payload = tool_mesh_status(_resources(tmp_path, mesh=runtime))
    assert "error" not in payload
    assert payload["mesh_root"] == str(runtime.root)
    assert payload["chunk_nodes"] == 2
    assert payload["consolidated_nodes"] >= 3  # three entities plus anchors
    assert payload["mesh_edges"] > 0
    assert payload["tick_count"] == 0 and payload["last_tick_at"] is None
    assert payload["semantic_dim"] == DIM and payload["frame_dim"] == DIM
    assert payload["embedder"] == {"model_id": f"hash@{DIM}", "dim": DIM, "matches_workspace": True}
    assert "contradiction" in payload["frame_profiles"]
    assert payload["llm_on_path"] is False


def test_without_a_workspace_both_tools_say_how_to_get_one(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_mesh_ask, tool_mesh_status, tool_status

    res = _resources(tmp_path, mesh=None)
    status = tool_mesh_status(res)
    assert "error" in status
    assert "theogony mesh" in status["error"] and "--mesh-root" in status["error"]
    asked = asyncio.run(tool_mesh_ask(res, q="Who was Marie of Hanover?"))
    assert "error" in asked and "--mesh-root" in asked["error"]
    # and the Gen-1 status tool says so up front
    gen1 = asyncio.run(tool_status(res))
    assert gen1["mesh"] == {"available": False, "root": None}


def test_mesh_ask_returns_the_constellation_and_the_measured_rendering(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_mesh_ask, tool_status

    runtime = _mesh(tmp_path)
    res = _resources(tmp_path, mesh=runtime)
    payload = asyncio.run(tool_mesh_ask(res, q="Who was the father of Marie of Hanover?"))
    assert "error" not in payload, payload
    c = payload["constellation"]
    names = {n["name"] for n in c["nodes"]}
    assert any("Marie of Hanover" in n for n in names), names
    assert any("George V" in n for n in names), names
    assert c["seed_node_ids"], "the name anchor seeded the entity the question names"
    assert c["edges"], "the typed relation reached the working set"
    descriptors = {e["relation_descriptor"] for e in c["edges"]}
    assert "daughter of" in descriptors
    # the rendering is the one the benchmark measured: entities, then the typed
    # relations touching a seed, structural descriptors left out
    material = payload["material"]
    assert material.startswith("Entities:\n- ")
    assert "Relations between them:" in material and "daughter of" in material
    assert "co_mentions_in_paragraph" not in material and "appears_in_source" not in material
    assert payload["material_typed_only"] is True
    assert payload["frame_profile"] == "any" and c["frame_routed"] is False
    assert payload["verdict"] in {"good", "partial"}
    assert payload["nodes_fired"] == len(c["nodes"]), "the query recorded its firing (PHX-1101)"
    assert "no language model" in payload["note"]
    # the Gen-1 status tool points at the workspace
    gen1 = asyncio.run(tool_status(res))
    assert gen1["mesh"] == {"available": True, "root": str(runtime.root)}
    # every mesh query writes its report, as the CLI does (contract 2)
    reports = list((tmp_path / "data" / "run_reports" / "mesh_query").glob("*.json"))
    assert len(reports) == 1
    written = json.loads(reports[0].read_text(encoding="utf-8"))
    assert written["run_id"] == payload["run_id"]
    assert written["query"] == "Who was the father of Marie of Hanover?"
    assert written["constellation_node_count"] == len(c["nodes"])
    assert "via mcp" in written["verdict_reasoning"]


def test_an_initialised_but_empty_workspace_is_served_with_a_poor_verdict(tmp_path: Path) -> None:
    """`MeshRuntime.open` on the default root leaves a workspace with tables and
    no rows; `mesh_workspace_exists` accepts it and the server opens it. Over
    it the honest answer is a structured "poor" report — not an error, which
    would misdescribe the state, and not an invented constellation."""
    from theogony.mcp.server import tool_mesh_ask, tool_mesh_status

    empty = MeshRuntime.open(tmp_path / "empty", semantic_dim=DIM, frame_dim=DIM)
    assert mesh_workspace_exists(empty.root)
    res = _resources(tmp_path, mesh=empty)
    assert tool_mesh_status(res)["consolidated_nodes"] == 0
    payload = asyncio.run(tool_mesh_ask(res, q="Who was Marie of Hanover?"))
    assert "error" not in payload
    assert payload["verdict"] == "poor" and payload["constellation"]["nodes"] == []
    assert payload["material"] == "Entities:"


def test_the_declared_bounds_are_enforced_not_just_declared(tmp_path: Path) -> None:
    """mcp 2.x validates the request envelope, not a tool's inputSchema."""
    from theogony.mcp.server import _tool_descriptors, tool_mesh_ask

    res = _resources(tmp_path, mesh=_mesh(tmp_path))
    declared = next(d for d in _tool_descriptors() if d["name"] == "mesh_ask")
    maximum = declared["inputSchema"]["properties"]["top_k"]["maximum"]
    for bad in (0, -1, maximum + 1):
        payload = asyncio.run(tool_mesh_ask(res, q="Who was Marie of Hanover?", top_k=bad))
        assert "error" in payload and "top_k" in payload["error"], bad
    blank = asyncio.run(tool_mesh_ask(res, q="   "))
    assert "error" in blank and "q" in blank["error"]
    one = asyncio.run(tool_mesh_ask(res, q="Who was Marie of Hanover?", top_k=1))
    assert "error" not in one
    content = [n for n in one["constellation"]["nodes"] if not n["is_source_anchor"]]
    assert len(content) == 1, "top_k bounds the content nodes; anchors ride along for provenance"


def test_typed_only_false_reproduces_the_pre_1110_rendering(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_mesh_ask

    res = _resources(tmp_path, mesh=_mesh(tmp_path))
    full = asyncio.run(
        tool_mesh_ask(res, q="Who was the father of Marie of Hanover?", typed_only=False)
    )
    assert "error" not in full
    assert full["material_typed_only"] is False
    assert "co_mentions_in_paragraph" in full["material"] or "appears_in_source" in full["material"]


def test_frame_profiles_route_or_are_refused(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_mesh_ask

    res = _resources(tmp_path, mesh=_mesh(tmp_path))
    routed = asyncio.run(
        tool_mesh_ask(res, q="Who was Marie of Hanover?", frame_profile="contradiction")
    )
    assert "error" not in routed, routed
    assert routed["constellation"]["frame_routed"] is True
    assert routed["frame_profile"] == "contradiction"
    bad = asyncio.run(tool_mesh_ask(res, q="Who was Marie of Hanover?", frame_profile="vibes"))
    assert "error" in bad and "frame_profile" in bad["error"]


def test_a_query_vector_in_the_wrong_space_is_refused_not_answered(tmp_path: Path) -> None:
    """A 384-d embedder against an 8-d workspace would find nothing and say
    nothing; the dimension check turns that silence into an error."""
    from theogony.mcp.server import tool_mesh_ask, tool_mesh_status

    res = _resources(tmp_path, mesh=_mesh(tmp_path), embedder=_HashEmbedder(dim=384))
    status = tool_mesh_status(res)
    assert status["embedder"]["matches_workspace"] is False
    asked = asyncio.run(tool_mesh_ask(res, q="Who was Marie of Hanover?"))
    assert "error" in asked and "384" in asked["error"] and "8-dimensional" in asked["error"]


def test_the_descriptors_offer_both_tools_and_say_no_llm_is_involved() -> None:
    from theogony.mcp.server import _tool_descriptors

    by_name = {d["name"]: d for d in _tool_descriptors()}
    assert {"mesh_ask", "mesh_status"} <= set(by_name)
    ask = by_name["mesh_ask"]
    assert "No language model" in ask["description"]
    props = ask["inputSchema"]["properties"]
    assert props["top_k"]["default"] == 50 and props["top_k"]["maximum"] == 200
    assert "contradiction" in props["frame_profile"]["enum"]
    assert props["typed_only"]["default"] is True
    assert ask["inputSchema"]["required"] == ["q"]


@pytest.mark.asyncio
async def test_the_mesh_answers_a_real_protocol_round_trip(tmp_path: Path) -> None:
    """Through an MCP client session, not a direct call: the acceptance of
    PHX-1112 piece 1 is a protocol round trip against a replayed mesh."""
    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    from theogony.mcp.server import build_server

    runtime = await _mesh_async(tmp_path)  # inside the running loop, so no asyncio.run
    server = build_server(_resources(tmp_path, mesh=runtime))

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams

        async with anyio.create_task_group() as tg:

            async def _run_server() -> None:
                await server.run(server_read, server_write, server.create_initialization_options())

            tg.start_soon(_run_server)

            async with ClientSession(client_read, client_write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {"mesh_ask", "mesh_status"} <= names

                status = await session.call_tool("mesh_status", {})
                assert status.is_error is not True
                status_payload = json.loads(status.content[0].text)  # type: ignore[union-attr]
                assert status_payload["consolidated_nodes"] >= 3

                asked = await session.call_tool(
                    "mesh_ask", {"q": "Who was the father of Marie of Hanover?", "top_k": 10}
                )
                assert asked.is_error is not True
                payload = json.loads(asked.content[0].text)  # type: ignore[union-attr]
                assert payload["constellation"]["nodes"]
                assert "daughter of" in payload["material"]

                # non-default arguments reach the tool through the dispatcher
                pinned = await session.call_tool(
                    "mesh_ask",
                    {
                        "q": "Who was the father of Marie of Hanover?",
                        "top_k": 1,
                        "typed_only": False,
                        "frame_profile": "what_is",
                    },
                )
                assert pinned.is_error is not True
                pinned_payload = json.loads(pinned.content[0].text)  # type: ignore[union-attr]
                content = [
                    n for n in pinned_payload["constellation"]["nodes"] if not n["is_source_anchor"]
                ]
                assert len(content) == 1
                assert pinned_payload["material_typed_only"] is False
                assert pinned_payload["frame_profile"] == "what_is"
                assert pinned_payload["constellation"]["frame_routed"] is True

                refused = await session.call_tool(
                    "mesh_ask", {"q": "anything", "frame_profile": "vibes"}
                )
                assert refused.is_error is True

            tg.cancel_scope.cancel()


@pytest.mark.asyncio
async def test_open_resources_refuses_a_mesh_root_that_holds_no_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Honest failure before the handshake, not an apology on every call."""
    import logging

    from theogony.mcp.server import open_resources

    monkeypatch.setenv("THEOGONY_DATA_DIR", str(tmp_path / "data"))
    # `open_resources` configures the project logger (a stderr handler, and
    # `propagate = False`). Left in place, every later test that captures a
    # warning through `caplog` sees nothing — found as an order-dependent
    # failure in tests/test_research_executor.py. Restore what we found.
    project_logger = logging.getLogger("theogony")
    monkeypatch.setattr(project_logger, "propagate", project_logger.propagate)
    monkeypatch.setattr(project_logger, "handlers", list(project_logger.handlers))
    monkeypatch.setattr(project_logger, "level", project_logger.level)
    with pytest.raises(RuntimeError, match="no mesh workspace"):
        async with open_resources(seed_path=None, mesh_root=tmp_path / "nothing-here"):
            pass  # pragma: no cover - the context must not open
    assert not (tmp_path / "nothing-here").exists(), "and nothing was created"

    # A workspace this server could not query is refused the same way, before
    # the handshake, rather than failing every mesh_ask of the session.
    odd = MeshRuntime.open(tmp_path / "odd", semantic_dim=DIM, frame_dim=DIM)
    assert odd.semantic_dim != 384, "the configured embedder is 384-dimensional"
    with pytest.raises(RuntimeError, match="dimensional vectors"):
        async with open_resources(seed_path=None, mesh_root=odd.root):
            pass  # pragma: no cover - the context must not open
