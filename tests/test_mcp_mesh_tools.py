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
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from theogony.config.settings import (
    EmbeddingSettings,
    LLMSettings,
    McpAppendSettings,
    Settings,
)
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


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Real settings, rooted in tmp_path: the reader behind mesh_append reads
    more of them than a stub would care to fake."""
    kwargs: dict[str, Any] = {
        "data_dir": tmp_path / "data",
        "llm": LLMSettings(provider="stub", model_id="stub-llm", fallback_provider=None),
        "embedding": EmbeddingSettings(model_id="hash", dim=DIM),
        "mcp_append": McpAppendSettings(enabled=True),
    }
    kwargs.update(overrides)
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


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

    settings = _settings(tmp_path)
    return McpResources(
        settings=settings,
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


READING_LAKE = {
    "concepts": [
        {
            "label": "Lake Traunsee",
            "entity_type": "place",
            "tags": ["lake"],
            "description": "A lake in Upper Austria beside the town of Gmunden.",
        },
        {
            "label": "Gmunden",
            "entity_type": "place",
            "tags": [],
            "description": "A town in Austria.",
        },
    ],
    "relations": [
        {
            "source": "Lake Traunsee",
            "target": "Gmunden",
            "relation_descriptor": "lies_beside",
            "relation_kind": "semantic",
            "stance": "current_claim",
            "rationale": "the paragraph says so",
        }
    ],
    "paragraph_concept": None,
    "stance": "current_claim",
}
LAKE_TEXT = "Lake Traunsee lies beside the town of Gmunden in Austria."


def test_mesh_append_writes_the_callers_reading_through_the_shipped_reader(tmp_path: Path) -> None:
    """The agent is the reader: its reading replays through MeshParagraphReader,
    lands in the workspace, and the next mesh_ask can reach it."""
    from theogony.mcp.server import tool_mesh_append, tool_mesh_ask, tool_mesh_status

    runtime = _mesh(tmp_path)
    res = _resources(tmp_path, mesh=runtime)
    before = tool_mesh_status(res)
    payload = asyncio.run(
        tool_mesh_append(
            res,
            text=LAKE_TEXT,
            reading=READING_LAKE,
            title="A note on the Traunsee",
            anchor="https://example.org/traunsee",
        )
    )
    assert "error" not in payload, payload
    assert payload["written"]["paragraphs"] == 1
    assert payload["written"]["concepts"] == 2 and payload["written"]["relations"] == 1
    assert payload["source_identifier"].startswith("mcp_agent:")
    assert payload["run_id"] and payload["verdict"]
    assert "no server-side" in payload["note"].lower() or "Nothing judged" in payload["note"]
    after = tool_mesh_status(res)
    assert after["consolidated_nodes"] > before["consolidated_nodes"]
    assert after["mesh_edges"] > before["mesh_edges"]
    # provenance: the source anchor says who wrote it and where it came from
    anchors = [n for n in runtime.nodes.iter_consolidated() if n.is_source_anchor]
    assert any(
        "mcp_agent" in (a.description or "") and "example.org/traunsee" in (a.description or "")
        for a in anchors
    )
    # the write persisted: a fresh runtime over the same directory sees it, and
    # retrieval reaches the new entity by name
    reopened = MeshRuntime.open(runtime.root)
    names = {
        n.tags[0] for n in reopened.nodes.iter_consolidated() if n.tags and not n.is_source_anchor
    }
    assert "Lake Traunsee" in names
    asked = asyncio.run(tool_mesh_ask(res, q="What lies beside Gmunden? Lake Traunsee"))
    assert "error" not in asked
    assert any("Traunsee" in n["name"] for n in asked["constellation"]["nodes"])
    assert "lies_beside" in asked["material"]
    # a run report was written for the ingest, as for any read (contract 2)
    assert list((tmp_path / "data" / "run_reports" / "ingest").glob("*.json"))


def test_mesh_append_refuses_what_the_reader_would_refuse(tmp_path: Path) -> None:
    from theogony.mcp.server import tool_mesh_append

    runtime = _mesh(tmp_path)
    res = _resources(tmp_path, mesh=runtime)
    before = runtime.nodes.consolidated_count()
    short = asyncio.run(tool_mesh_append(res, text="Hi.", reading=READING_LAKE))
    assert "error" in short and "one paragraph" in short["error"]
    # what the reader would split, the tool refuses — a literal blank line, one
    # that holds a space or a tab, CRLF, and pieces too short for the reader
    for text in (
        LAKE_TEXT + "\n\nAnother paragraph follows here.",
        LAKE_TEXT + "\n \nAnother paragraph follows here.",
        LAKE_TEXT + "\n\t\nAnother paragraph follows here.",
        LAKE_TEXT + "\r\n\r\nAnother paragraph follows here.",
        LAKE_TEXT + "\n \nOk.",
        "Hi there.\n \nBye now.",
    ):
        two = asyncio.run(tool_mesh_append(res, text=text, reading=READING_LAKE))
        assert "error" in two and "one paragraph" in two["error"], text
    # the caps the descriptor promises are kept here as well
    long_title = asyncio.run(
        tool_mesh_append(res, text=LAKE_TEXT, reading=READING_LAKE, title="t" * 241)
    )
    assert "error" in long_title and "title" in long_title["error"]
    long_anchor = asyncio.run(
        tool_mesh_append(res, text=LAKE_TEXT, reading=READING_LAKE, anchor="a" * 501)
    )
    assert "error" in long_anchor and "anchor" in long_anchor["error"]
    many = {
        "concepts": [{"label": f"c{i}", "description": "x"} for i in range(101)],
        "relations": [],
    }
    too_many = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading=many))
    assert "error" in too_many and "101 concepts" in too_many["error"]
    # a relation that names an endpoint the reading does not declare is refused,
    # not dropped on the floor by the reader
    dangling = {
        "concepts": READING_LAKE["concepts"],
        "relations": [
            {
                "source": "Lake Traunsee",
                "target": "Salzkammergut",
                "relation_descriptor": "lies_in",
            }
        ],
    }
    loose = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading=dangling))
    assert "error" in loose and "Salzkammergut" in loose["error"]
    bad = asyncio.run(
        tool_mesh_append(res, text=LAKE_TEXT, reading={"concepts": [{"label": "A", "tags": "x"}]})
    )
    assert "error" in bad and "schema" in bad["error"]
    not_a_list = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading={"concepts": "x"}))
    assert "error" in not_a_list and "no concept" in not_a_list["error"]
    empty = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading={"concepts": []}))
    assert "error" in empty and "no concept" in empty["error"]
    assert runtime.nodes.consolidated_count() == before, "nothing refused was written"
    res = _resources(tmp_path, mesh=runtime)
    res.settings = _settings(tmp_path, mcp_append=McpAppendSettings(enabled=False))
    off = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading=READING_LAKE))
    assert "error" in off and "disabled" in off["error"]
    none = asyncio.run(
        tool_mesh_append(_resources(tmp_path, mesh=None), text=LAKE_TEXT, reading=READING_LAKE)
    )
    assert "error" in none and "--mesh-root" in none["error"]


@pytest.mark.asyncio
async def test_mesh_append_answers_a_protocol_round_trip(tmp_path: Path) -> None:
    import anyio
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    from theogony.mcp.server import build_server

    runtime = await _mesh_async(tmp_path)
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
                assert "mesh_append" in names
                written = await session.call_tool(
                    "mesh_append", {"text": LAKE_TEXT, "reading": READING_LAKE}
                )
                assert written.is_error is not True
                payload = json.loads(written.content[0].text)  # type: ignore[union-attr]
                assert payload["written"]["concepts"] == 2
                refused = await session.call_tool("mesh_append", {"text": "x", "reading": {}})
                assert refused.is_error is True
            tg.cancel_scope.cancel()


def test_a_read_that_applies_nothing_is_an_error_not_a_quiet_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the reader cannot use the reading — here forced by a provider that
    answers nothing — the call fails, names what did land, and the run report
    is there to read."""
    from theogony.agents.llm import LLMResult
    from theogony.mcp.server import tool_mesh_append
    from theogony.mesh.ingestion.replay import ReplayReadingProvider

    runtime = _mesh(tmp_path)
    res = _resources(tmp_path, mesh=runtime)

    async def nothing(self, prompt, *, system=None, **_):  # type: ignore[no-untyped-def]
        self.misses.append(prompt[:40])
        return LLMResult(text="", model_id="mcp-agent")

    monkeypatch.setattr(ReplayReadingProvider, "complete", nothing)
    payload = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading=READING_LAKE))
    assert "error" in payload and "applied none" in payload["error"]
    assert payload["written"]["concepts"] == 0 and payload["run_id"]
    assert payload["verdict"] == "failed"


def test_appends_compact_the_workspace_every_fifty_and_skip_the_corpus_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from theogony.mcp import server as mcp_server
    from theogony.mcp.server import tool_mesh_append
    from theogony.mesh.ingestion import kadmos_v2

    runtime = _mesh(tmp_path)
    res = _resources(tmp_path, mesh=runtime)
    compactions: list[int] = []
    monkeypatch.setattr(runtime, "compact", lambda **_: compactions.append(1) or {})
    walked: list[int] = []
    original = kadmos_v2.MeshParagraphReader._compute_connectivity_metrics

    def spy(self, units):  # type: ignore[no-untyped-def]
        walked.append(1)
        return original(self, units)

    monkeypatch.setattr(kadmos_v2.MeshParagraphReader, "_compute_connectivity_metrics", spy)
    res.mesh_appends = mcp_server._MESH_APPEND_COMPACT_EVERY - 1
    payload = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading=READING_LAKE))
    assert "error" not in payload
    assert compactions == [1], "the fiftieth append compacts"
    assert walked == [], "one paragraph does not walk the whole graph"
    assert res.mesh_appends == mcp_server._MESH_APPEND_COMPACT_EVERY


def test_a_second_mention_merges_with_the_entity_already_there(tmp_path: Path) -> None:
    """Identity resolution is the reader's, so a second paragraph about the same
    lake does not mint a second lake."""
    from theogony.mcp.server import tool_mesh_append

    runtime = _mesh(tmp_path)
    res = _resources(tmp_path, mesh=runtime)
    first = asyncio.run(tool_mesh_append(res, text=LAKE_TEXT, reading=READING_LAKE))
    assert "error" not in first
    second = asyncio.run(
        tool_mesh_append(
            res,
            text="Lake Traunsee is the deepest lake of Upper Austria.",
            reading={
                "concepts": [
                    {
                        "label": "Lake Traunsee",
                        "entity_type": "place",
                        "description": "The deepest lake of Upper Austria.",
                    },
                    {"label": "Upper Austria", "entity_type": "place", "description": "A state."},
                ],
                "relations": [
                    {
                        "source": "Lake Traunsee",
                        "target": "Upper Austria",
                        "relation_descriptor": "located_in",
                    }
                ],
            },
        )
    )
    assert "error" not in second, second
    lakes = [
        n
        for n in runtime.nodes.iter_consolidated()
        if n.tags and n.tags[0] == "Lake Traunsee" and not n.is_source_anchor
    ]
    assert len(lakes) == 1, "one lake, two paragraphs"
