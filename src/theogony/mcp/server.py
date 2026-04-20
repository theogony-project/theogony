"""
Theogony MCP server — Model Context Protocol surface (Gen 1, read-side).

Exposes the Chronik's most distinctive primitives as MCP tools so any
MCP-compatible host (Claude Desktop, Cursor, ChatGPT Desktop, Codex,
or any other MCP client) can ask, explore, and inspect Theogony
without a custom integration.

Tools (Gen 1, read-side surface)
--------------------------------

- ``pantheon_ask``           — cited answer with verdict + Constellation
- ``pantheon_node``          — Hover-Lupe: node + depth-1 neighborhood
- ``pantheon_status``        — current configuration + report counts
- ``pantheon_reports_list``  — recent run reports across types
- ``pantheon_reports_show``  — one report's full JSON

Lifespan and ownership
----------------------

Mirrors :func:`theogony.api.app.lifespan` (Plan §4.4): one owner per
``settings`` / ``audit`` / ``wd_cache`` / ``embedder`` / ``llm`` /
``store`` / ``report_writer``. The OneirosWorker is intentionally not
started here — MCP sessions can be very short (seconds), and the
worker is most useful when the store outlives a single session
(``theogony serve`` remains the long-lived process).

Why not include ``pantheon_ingest_*`` yet
-----------------------------------------

A bounded ingest is 5–20 min wall-clock; most MCP hosts time out tool
calls in ~30 s. The right shape (background ingest with status polled
via reports) is a Gen-2 follow-up, not part of this first cut.

Transport
---------

stdio only for now — the universal transport for desktop MCP hosts.
``server.create_initialization_options()`` carries name/version so a
host can render "Theogony" in its tool palette unambiguously.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from theogony import __version__
from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger, setup_logging
from theogony.config.settings import Settings
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores.neo4j_store import Neo4jKnowledgeStore

if TYPE_CHECKING:  # pragma: no cover
    pass

log = get_logger("mcp.server")


_INSTALL_HINT = (
    'Theogony MCP server requires the `mcp` extra. Install with: pip install -e ".[mcp]"'
)


@dataclass
class McpResources:
    """Long-lived resources owned by the MCP lifespan.

    Mirrors ``app.state`` from :func:`theogony.api.app.lifespan`: one
    owner per Settings / audit log / Wikidata cache / embedder / LLM /
    Neo4j store / report writer. Held for the duration of one
    ``serve_stdio`` invocation; cleanly torn down on stdio EOF or
    SIGTERM.
    """

    settings: Settings
    audit: ExtractionAuditLog
    wd_cache: WikidataCache | None
    embedder: LocalSentenceTransformerEmbedder
    llm: LLMProvider
    store: Neo4jKnowledgeStore
    report_writer: RunReportWriter


@contextlib.asynccontextmanager
async def open_resources() -> AsyncIterator[McpResources]:
    """Open all long-lived resources for the MCP server.

    Startup ordering: settings → logging → audit (sync open) →
    Wikidata cache (sync, optional) → embedder warm-up → LLM factory
    → Neo4j store (async open) → report writer.

    Shutdown reverses the order. Each teardown is wrapped in
    ``contextlib.suppress(Exception)`` so a failure in one cleanup does
    not block the others; the lifecycle log captures completion either
    way.
    """
    settings = Settings()
    setup_logging(settings)

    audit = ExtractionAuditLog(settings.data_dir / "audit.sqlite")
    audit.__enter__()

    wd_cache: WikidataCache | None = None
    if settings.wikidata_cache.enabled:
        wd_cache = WikidataCache(settings.wikidata_cache_path)
        wd_cache.__enter__()

    embedder = LocalSentenceTransformerEmbedder(
        model_id=settings.embedding.model_id,
        dim=settings.embedding.dim,
    )
    # Eager warm-up so the first tool call is honest about latency.
    await embedder.embed("warmup")

    llm = build_llm_from_settings(settings)

    store = Neo4jKnowledgeStore(settings.neo4j, embedding_dim=embedder.dim)
    await store.__aenter__()

    report_writer = RunReportWriter(settings.run_reports_dir)

    log.info(
        "mcp lifespan: startup complete (store=neo4j embedding_dim=%d)",
        settings.embedding.dim,
    )
    try:
        yield McpResources(
            settings=settings,
            audit=audit,
            wd_cache=wd_cache,
            embedder=embedder,
            llm=llm,
            store=store,
            report_writer=report_writer,
        )
    finally:
        with contextlib.suppress(Exception):
            await store.__aexit__(None, None, None)
        if hasattr(llm, "aclose"):
            with contextlib.suppress(Exception):
                await llm.aclose()
        if wd_cache is not None:
            with contextlib.suppress(Exception):
                wd_cache.__exit__(None, None, None)
        with contextlib.suppress(Exception):
            audit.__exit__(None, None, None)
        log.info("mcp lifespan: shutdown complete")


# --------------------------------------------------------------------------
# Tool implementations (separated from server registration so they're
# independently unit-testable with a stub McpResources)
# --------------------------------------------------------------------------


def _build_query_pipeline(res: McpResources) -> QueryPipeline:
    return QueryPipeline(
        embedder=res.embedder,
        retriever=MultiHopRetriever(res.store),
        assembler=ConstellationAssembler(res.store),
        synthesizer=AnswerSynthesizer(res.llm, audit_log=res.audit),
        relevance=RelevanceTracker(res.store),
        settings=res.settings,
        report_writer=res.report_writer,
    )


def _count_reports(res: McpResources, rtype: str) -> int:
    d = res.settings.run_reports_dir / rtype
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file() and p.suffix == ".json")


async def tool_ask(res: McpResources, *, q: str, k: int = 10, hops: int = 2) -> dict[str, Any]:
    """Run :func:`pantheon_ask` and return the JSON-serialisable payload."""
    pipeline = _build_query_pipeline(res)
    result = await pipeline.ask(q, layer=None, k=k, hops=hops)
    return {
        "answer": result.answer.text,
        "cited_node_ids": list(result.answer.cited_node_ids),
        "verdict": result.report.verdict,
        "verdict_reasoning": result.report.verdict_reasoning,
        "run_id": result.report.run_id,
        "constellation": {
            "query": result.constellation.query,
            "nodes": [n.model_dump(mode="json") for n in result.constellation.nodes],
            "edges": [e.model_dump(mode="json") for e in result.constellation.edges],
            "gaps": list(result.constellation.gaps),
            "path": result.constellation.path,
        },
        "synthesis": {
            "input_tokens": result.report.synthesis.input_tokens,
            "output_tokens": result.report.synthesis.output_tokens,
            "cost_eur": result.report.synthesis.cost_eur,
            "latency_ms": result.report.synthesis.latency_ms,
        },
    }


async def tool_node(res: McpResources, *, node_id: str) -> dict[str, Any]:
    """Run :func:`pantheon_node` and return the JSON-serialisable payload."""
    record = await res.store.get_node(node_id)
    if record is None:
        return {"error": f"no node with id {node_id!r}"}
    neighborhood = await res.store.get_neighborhood(node_id, depth=1, min_weight=0.3)
    return {
        "node": {
            "id": record.id,
            "label": record.label,
            "node_type": record.node_type.value,
            "external_ids": dict(record.external_ids),
            "resolution_tier": record.resolution_tier,
            "scores": {
                "confidence": record.scores.confidence,
                "relevance": record.scores.relevance,
                "connectivity": record.scores.connectivity,
                "freshness": record.scores.freshness,
            },
            "source": {
                "source_type": record.source_ref.source_type,
                "identifier": record.source_ref.identifier,
                "location": record.source_ref.location,
            },
        },
        "neighborhood": {
            "nodes": [n.model_dump(mode="json") for n in neighborhood.nodes],
            "edges": [e.model_dump(mode="json") for e in neighborhood.edges],
        },
    }


async def tool_status(res: McpResources) -> dict[str, Any]:
    """Run :func:`pantheon_status` and return the JSON-serialisable payload."""
    health = await res.store.health()
    return {
        "version": __version__,
        "store": str(health.get("backend", "unknown")),
        "llm_provider": res.settings.llm.provider,
        "llm_model": res.settings.llm.model_id,
        "embedding_model": res.settings.embedding.model_id,
        "embedding_dim": res.settings.embedding.dim,
        "report_counts": {
            rtype: _count_reports(res, rtype) for rtype in ("ingest", "query", "oneiros")
        },
    }


def tool_reports_list(
    res: McpResources, *, report_type: str = "", last: int = 20
) -> list[dict[str, Any]]:
    """Run :func:`pantheon_reports_list` and return the row list."""
    types_to_scan = [report_type] if report_type else ["ingest", "query", "oneiros"]
    rows: list[dict[str, Any]] = []
    for rtype in types_to_scan:
        d = res.settings.run_reports_dir / rtype
        if not d.exists():
            continue
        for path in sorted(
            (p for p in d.iterdir() if p.is_file() and p.suffix == ".json"),
            key=lambda p: p.stem,
            reverse=True,
        ):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows.append(
                {
                    "run_id": payload.get("run_id", path.stem),
                    "type": payload.get("report_type", rtype),
                    "verdict": payload.get("verdict", "?"),
                    "status": payload.get("status", "?"),
                    "duration_s": payload.get("duration_s", 0.0),
                }
            )
    rows.sort(key=lambda r: r["run_id"], reverse=True)
    return rows[:last]


def tool_reports_show(res: McpResources, *, run_id: str) -> dict[str, Any]:
    """Run :func:`pantheon_reports_show` and return the report JSON or an error."""
    for rtype in ("ingest", "query", "oneiros"):
        d = res.settings.run_reports_dir / rtype
        if not d.exists():
            continue
        exact = d / f"{run_id}.json"
        if exact.exists():
            payload: dict[str, Any] = json.loads(exact.read_text(encoding="utf-8"))
            return payload
        # Prefix match within this directory
        for p in d.iterdir():
            if p.is_file() and p.suffix == ".json" and p.stem.startswith(run_id):
                prefix_payload: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
                return prefix_payload
    return {"error": f"no report found for run_id={run_id!r}"}


# --------------------------------------------------------------------------
# Tool descriptors — single source of truth for ``tools/list``
# --------------------------------------------------------------------------


def _tool_descriptors() -> list[dict[str, Any]]:
    """Return the JSON-Schema tool descriptors registered with MCP.

    Kept module-private so the mcp SDK import stays inside
    :func:`build_server` (and the descriptors stay testable without
    pulling the SDK).
    """
    return [
        {
            "name": "pantheon_ask",
            "description": (
                "Ask the Chronik a question. Returns a cited, verdict-anchored "
                "answer with the slim Constellation that produced it. Every "
                "cited node id can be passed to `pantheon_node` for a Hover-Lupe "
                "expansion. Use this whenever you want grounded, inspectable "
                "knowledge instead of unverified model recall."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "The natural-language question.",
                        "minLength": 1,
                        "maxLength": 2000,
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of seed nodes (default 10, max 50).",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
                    },
                    "hops": {
                        "type": "integer",
                        "description": "Graph expansion depth (default 2, max 4).",
                        "minimum": 0,
                        "maximum": 4,
                        "default": 2,
                    },
                },
                "required": ["q"],
                "additionalProperties": False,
            },
        },
        {
            "name": "pantheon_node",
            "description": (
                "Hover-Lupe: fetch a node and its depth-1 neighborhood. Use "
                "this to recursively explore an entity returned by "
                "`pantheon_ask` — every neighbor's id can itself be passed "
                "back to `pantheon_node`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": (
                            "An AKA-… node id, typically from `pantheon_ask` cited_node_ids."
                        ),
                        "minLength": 1,
                    },
                },
                "required": ["node_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "pantheon_status",
            "description": (
                "Return Theogony's current configuration and report counts. "
                "Useful to confirm which model, store backend, embedding "
                "model, and corpus the Chronik is currently configured "
                "against."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "pantheon_reports_list",
            "description": (
                "List recent run reports (ingest, query, oneiros). The "
                "Chronik's honest retrospective surface — every answer it "
                "produced, every ingest it ran, every Oneiros tick."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "description": (
                            "Filter by type. One of 'ingest', 'query', 'oneiros'. "
                            "Empty string = all types."
                        ),
                        "enum": ["", "ingest", "query", "oneiros"],
                        "default": "",
                    },
                    "last": {
                        "type": "integer",
                        "description": "Maximum reports to return, newest first.",
                        "minimum": 1,
                        "maximum": 200,
                        "default": 20,
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "pantheon_reports_show",
            "description": (
                "Return a single run report's full JSON. The run_id can be a "
                "full ULID or a unique prefix."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "A run_id (full ULID or unique prefix).",
                        "minLength": 1,
                    },
                },
                "required": ["run_id"],
                "additionalProperties": False,
            },
        },
    ]


# --------------------------------------------------------------------------
# Server build + transport
# --------------------------------------------------------------------------


def build_server(res: McpResources) -> Any:
    """Build the MCP ``Server`` with all Theogony tools registered.

    Returns an ``mcp.server.Server`` instance. The ``mcp`` SDK is
    imported lazily so the rest of theogony works without the optional
    ``mcp`` extra installed.
    """
    try:
        import mcp.types as types
        from mcp.server import Server
    except ImportError as exc:  # pragma: no cover - guard exercised only without extra
        raise RuntimeError(_INSTALL_HINT) from exc

    server = Server("theogony")
    descriptors = _tool_descriptors()

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def _list_tools() -> list[Any]:
        return [
            types.Tool(
                name=d["name"],
                description=d["description"],
                inputSchema=d["inputSchema"],
            )
            for d in descriptors
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        payload: Any
        if name == "pantheon_ask":
            payload = await tool_ask(
                res,
                q=arguments["q"],
                k=int(arguments.get("k", 10)),
                hops=int(arguments.get("hops", 2)),
            )
        elif name == "pantheon_node":
            payload = await tool_node(res, node_id=arguments["node_id"])
        elif name == "pantheon_status":
            payload = await tool_status(res)
        elif name == "pantheon_reports_list":
            payload = tool_reports_list(
                res,
                report_type=arguments.get("report_type", "") or "",
                last=int(arguments.get("last", 20)),
            )
        elif name == "pantheon_reports_show":
            payload = tool_reports_show(res, run_id=arguments["run_id"])
        else:
            raise ValueError(f"unknown tool: {name}")
        return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]

    return server


async def serve_stdio() -> None:
    """Open resources, build the server, and run it over stdio.

    The single async entry point. Used by ``theogony mcp`` and any
    other callsite that wants to host Pantheon over the MCP stdio
    transport. Requires the ``mcp`` extra; on its absence raises
    ``RuntimeError`` with an install hint.
    """
    try:
        from mcp.server.stdio import stdio_server
    except ImportError as exc:  # pragma: no cover - guard exercised only without extra
        raise RuntimeError(_INSTALL_HINT) from exc

    async with open_resources() as res:
        server = build_server(res)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )


__all__ = [
    "McpResources",
    "build_server",
    "open_resources",
    "serve_stdio",
    "tool_ask",
    "tool_node",
    "tool_reports_list",
    "tool_reports_show",
    "tool_status",
]
