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

``stdio`` is the default — universal for desktop MCP hosts. ``sse``
(HTTP + Server-Sent Events) is available for hosted deployments; see
:func:`serve_sse` and ``hosted/README.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from theogony import __version__
from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.config.logging import get_logger, setup_logging
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.stub_detector import StubDetector
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.memory.edge_pheromone import EdgePheromoneTracker
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.models import OneirosTickReport
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesizer_factory import build_synthesizer
from theogony.stores.memory import InMemoryKnowledgeStore
from theogony.stores.neo4j_store import Neo4jKnowledgeStore

if TYPE_CHECKING:  # pragma: no cover
    pass

log = get_logger("mcp.server")


_INSTALL_HINT = (
    'Theogony MCP server requires the `mcp` extra. Install with: pip install -e ".[mcp]"'
)

_MCP_ASK_NO_LLM_KEY = (
    "this hosted instance does not have an LLM key configured; you can run a "
    "local install with your own key, or wait for PHX-0066 Phase 2 which will "
    "support per-call key pass-through"
)


@dataclass
class McpResources:
    """Long-lived resources owned by the MCP lifespan.

    Mirrors ``app.state`` from :func:`theogony.api.app.lifespan`: one
    owner per Settings / audit log / Wikidata cache / embedder / LLM /
    store / report writer. Held for the duration of one transport
    session; cleanly torn down on disconnect or SIGTERM.

    When ``mcp_ask_blocked_message`` is set (seeded in-memory mode without a
    usable API key for the configured non-stub LLM provider),
    :func:`tool_ask` returns that message instead of calling the query
    pipeline.
    """

    settings: Settings
    audit: ExtractionAuditLog
    wd_cache: WikidataCache | None
    embedder: LocalSentenceTransformerEmbedder
    llm: LLMProvider
    store: KnowledgeStore
    report_writer: RunReportWriter
    mcp_ask_blocked_message: str | None = None


@contextlib.asynccontextmanager
async def open_resources(*, seed_path: Path | None = None) -> AsyncIterator[McpResources]:
    """Open all long-lived resources for the MCP server.

    When ``seed_path`` is set, the dump is loaded into an in-memory store
    before traffic is accepted. When ``seed_path`` is ``None``, Neo4j
    is opened as in the original Gen 1 MCP path.

    Startup ordering: settings → logging → audit (sync open) →
    Wikidata cache (sync, optional) → embedder warm-up → LLM factory
    → store → report writer.

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
    await embedder.embed("warmup")

    mcp_ask_blocked_message: str | None = None
    store: KnowledgeStore
    llm: LLMProvider

    if seed_path is not None:
        from theogony.core.model import KnowledgeEdge, KnowledgeNode
        from theogony.docs_ingest.dump import DumpError, read_dump

        store = InMemoryKnowledgeStore()
        try:
            _, nodes, edges = read_dump(seed_path)
        except DumpError as exc:
            log.error("mcp seed load failed: %s", exc)
            raise RuntimeError(f"could not read chronicle dump: {exc}") from exc
        node_objs = [n for n in nodes if isinstance(n, KnowledgeNode)]
        edge_objs = [e for e in edges if isinstance(e, KnowledgeEdge)]
        await store.batch_upsert_nodes(node_objs)
        await store.batch_upsert_edges(edge_objs)
        log.info(
            "mcp lifespan: seeded in-memory store (%d nodes, %d edges)",
            len(node_objs),
            len(edge_objs),
        )
        try:
            llm = build_llm_from_settings(settings)
        except (ValueError, NotImplementedError):
            llm = StubLLMProvider(model_id=settings.llm.model_id or "stub-llm")
            if settings.llm.provider != "stub":
                mcp_ask_blocked_message = _MCP_ASK_NO_LLM_KEY
    else:
        llm = build_llm_from_settings(settings)
        neo = Neo4jKnowledgeStore(settings.neo4j, embedding_dim=embedder.dim)
        await neo.__aenter__()
        store = neo

    report_writer = RunReportWriter(settings.run_reports_dir)

    h = await store.health()
    log.info(
        "mcp lifespan: startup complete (store=%s embedding_dim=%d)",
        h.get("backend"),
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
            mcp_ask_blocked_message=mcp_ask_blocked_message,
        )
    finally:
        with contextlib.suppress(Exception):
            if isinstance(store, Neo4jKnowledgeStore):
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
    settings = res.settings
    mnemosyne = build_mnemosyne_classifier(settings, res.llm)
    return QueryPipeline(
        embedder=res.embedder,
        retriever=MultiHopRetriever(
            res.store,
            strategy=build_retrieval_strategy(res.store, settings),
        ),
        assembler=ConstellationAssembler(res.store),
        synthesizer=build_synthesizer(settings, res.llm, audit_log=res.audit),
        relevance=RelevanceTracker(
            res.store,
            relevance_delta=settings.relevance.relevance_delta,
        ),
        settings=settings,
        report_writer=res.report_writer,
        edge_pheromone=EdgePheromoneTracker(
            res.store,
            delta=settings.relevance.edge_pheromone_delta,
        ),
        stub_detector=StubDetector(settings.curiosity.stub_thresholds),
        mnemosyne=mnemosyne,
    )


def _count_reports(res: McpResources, rtype: str) -> int:
    d = res.settings.run_reports_dir / rtype
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file() and p.suffix == ".json")


def _parse_pheromone_mode(
    raw: str | None,
) -> Literal["follow", "ignore", "invert"]:
    if raw is None or raw == "":
        return "follow"
    if raw in ("follow", "ignore", "invert"):
        return cast(Literal["follow", "ignore", "invert"], raw)
    raise ValueError(f"pheromone_mode must be one of follow, ignore, invert; got {raw!r}")


async def tool_ask(
    res: McpResources,
    *,
    q: str,
    k: int = 10,
    hops: int = 2,
    pheromone_mode: str | None = None,
) -> dict[str, Any]:
    """Run :func:`pantheon_ask` and return the JSON-serialisable payload."""
    if res.mcp_ask_blocked_message is not None:
        return {"error": res.mcp_ask_blocked_message}
    try:
        mode = _parse_pheromone_mode(pheromone_mode)
    except ValueError as exc:
        return {"error": str(exc)}
    pipeline = _build_query_pipeline(res)
    result = await pipeline.ask(q, layer=None, k=k, hops=hops, pheromone_mode=mode)
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


def _morpheus_proposals_recent(settings: Settings) -> int:
    """Edges proposed in the latest Oneiros tick with a Morpheus block (W4)."""
    writer = RunReportWriter(settings.run_reports_dir)
    latest = writer.most_recent("oneiros")
    if not isinstance(latest, OneirosTickReport) or latest.morpheus is None:
        return 0
    return latest.morpheus.edges_proposed


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
        "morpheus_proposals_recent": _morpheus_proposals_recent(res.settings),
        "report_counts": {
            rtype: _count_reports(res, rtype)
            for rtype in ("ingest", "query", "oneiros", "clustering", "blindspot", "mnemosyne")
        },
    }


def tool_reports_list(
    res: McpResources, *, report_type: str = "", last: int = 20
) -> list[dict[str, Any]]:
    """Run :func:`pantheon_reports_list` and return the row list."""
    types_to_scan = (
        [report_type]
        if report_type
        else ["ingest", "query", "oneiros", "clustering", "blindspot", "mnemosyne"]
    )
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
    for rtype in ("ingest", "query", "oneiros", "clustering", "blindspot", "mnemosyne"):
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
                    "pheromone_mode": {
                        "type": "string",
                        "description": (
                            "How edge pheromone deltas affect traversal weights: "
                            "`follow` (default), `ignore`, or `invert`."
                        ),
                        "enum": ["follow", "ignore", "invert"],
                        "default": "follow",
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
                "List recent run reports (ingest, query, oneiros, clustering, "
                "blindspot, mnemosyne). "
                "The Chronik's honest retrospective surface — every answer it "
                "produced, every ingest it ran, every Oneiros tick, clustering "
                "and blind-spot / Mnemosyne aggregation passes."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "description": (
                            "Filter by type. One of 'ingest', 'query', 'oneiros', "
                            "'clustering', 'blindspot', 'mnemosyne'. Empty string = all types."
                        ),
                        "enum": [
                            "",
                            "ingest",
                            "query",
                            "oneiros",
                            "clustering",
                            "blindspot",
                            "mnemosyne",
                        ],
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
            raw_mode = arguments.get("pheromone_mode")
            mode_arg = None if raw_mode is None else str(raw_mode)
            payload = await tool_ask(
                res,
                q=arguments["q"],
                k=int(arguments.get("k", 10)),
                hops=int(arguments.get("hops", 2)),
                pheromone_mode=mode_arg,
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


@dataclass
class _SseHostingState:
    """Mutable process state for the HTTP/SSE MCP app."""

    resources: McpResources | None = None
    mcp_server: Any = None
    sse_transport: Any = None
    started_perf: float = 0.0
    last_query_at: datetime | None = None


@dataclass
class _IpRateBucket:
    hour_start: float
    hour_count: int
    day_start: float
    day_count: int


def _client_ip_from_scope(scope: dict[str, Any]) -> str:
    raw = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    xff = raw.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    client = scope.get("client")
    if isinstance(client, tuple) and client and client[0]:
        return str(client[0])
    return "unknown"


class _HostedRateLimitMiddleware:
    """Per-IP rolling windows (hour + day) on /sse and /messages only."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._buckets: dict[str, _IpRateBucket] = {}
        self._lock = asyncio.Lock()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == "/health" or not (path == "/sse" or path.startswith("/messages")):
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        request = Request(scope, receive)
        state: _SseHostingState | None = getattr(request.app.state, "theogony_sse", None)
        if state is None or state.resources is None:
            await self.app(scope, receive, send)
            return
        settings = state.resources.settings
        hosted = settings.hosted
        if hosted.rate_limit_per_hour <= 0:
            await self.app(scope, receive, self._wrap_send_for_last_query(scope, state, send))
            return

        bypass = hosted.rate_limit_bypass_token
        if bypass is not None:
            hdr = request.headers.get("x-theogony-ratelimit-bypass", "")
            secret = bypass.get_secret_value()
            try:
                bypass_ok = bool(hdr) and hmac.compare_digest(hdr, secret)
            except (TypeError, ValueError):
                bypass_ok = False
            if bypass_ok:
                await self.app(scope, receive, self._wrap_send_for_last_query(scope, state, send))
                return

        ip = _client_ip_from_scope(scope)
        now = time.time()
        async with self._lock:
            b = self._buckets.get(ip)
            if b is None:
                b = _IpRateBucket(hour_start=now, hour_count=0, day_start=now, day_count=0)
                self._buckets[ip] = b
            if now - b.hour_start >= 3600.0:
                b.hour_start, b.hour_count = now, 0
            if now - b.day_start >= 86400.0:
                b.day_start, b.day_count = now, 0
            if (
                b.hour_count >= hosted.rate_limit_per_hour
                or b.day_count >= hosted.rate_limit_per_day
            ):
                from starlette.responses import JSONResponse

                reset_h = int(3600.0 - (now - b.hour_start))
                body = {
                    "error": "rate limit exceeded",
                    "limit_per_hour": hosted.rate_limit_per_hour,
                    "limit_per_day": hosted.rate_limit_per_day,
                    "retry_after_seconds": max(reset_h, 1),
                }
                resp = JSONResponse(body, status_code=429)
                await resp(scope, receive, send)
                return
            b.hour_count += 1
            b.day_count += 1

        await self.app(scope, receive, self._wrap_send_for_last_query(scope, state, send))

    def _wrap_send_for_last_query(
        self, scope: dict[str, Any], state: _SseHostingState, send: Any
    ) -> Any:
        method = scope.get("method", "")
        path = scope.get("path", "")

        async def wrapped(message: dict[str, Any]) -> None:
            if (
                message.get("type") == "http.response.start"
                and method == "POST"
                and path.startswith("/messages")
            ):
                status = message.get("status", 500)
                if isinstance(status, int) and status == 202:
                    state.last_query_at = datetime.now(UTC)
            await send(message)

        return wrapped


async def serve_stdio(*, seed_path: Path | None = None) -> None:
    """Open resources, build the server, and run it over stdio.

    Used by ``theogony mcp`` and any other callsite that wants to host
    Pantheon over the MCP stdio transport. Requires the ``mcp`` extra;
    on its absence raises ``RuntimeError`` with an install hint.
    """
    try:
        from mcp.server.stdio import stdio_server
    except ImportError as exc:  # pragma: no cover - guard exercised only without extra
        raise RuntimeError(_INSTALL_HINT) from exc

    async with open_resources(seed_path=seed_path) as res:
        server = build_server(res)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )


async def serve_sse(*, host: str, port: int, seed_path: Path | None) -> None:
    """Run the MCP server over HTTP + SSE (Starlette + uvicorn).

    Lazily imports ``mcp.server.sse``, Starlette, and uvicorn so the core
    package stays importable without the ``mcp`` extra.
    """
    try:
        import uvicorn
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse, Response
        from starlette.routing import Mount, Route
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(_INSTALL_HINT) from exc

    async def health(request: Request) -> JSONResponse:
        st: _SseHostingState = request.app.state.theogony_sse
        res = st.resources
        assert res is not None
        h = await res.store.health()
        backend = str(h.get("backend", "unknown"))
        store_label = "memory" if backend == "in_memory" else backend
        raw_nodes = h.get("nodes", 0)
        raw_edges = h.get("edges", 0)
        nodes = int(raw_nodes) if isinstance(raw_nodes, (int, float)) else 0
        edges = int(raw_edges) if isinstance(raw_edges, (int, float)) else 0
        uptime = time.perf_counter() - st.started_perf
        last_q = st.last_query_at
        last_s = None if last_q is None else last_q.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {
            "status": "ok",
            "version": __version__,
            "store": store_label,
            "embedding_model": f"{res.settings.embedding.model_id}@v1",
            "embedding_dim": res.settings.embedding.dim,
            "node_count": nodes,
            "edge_count": edges,
            "uptime_seconds": round(uptime, 1),
            "last_query_at": last_s,
        }
        return JSONResponse(payload)

    async def handle_sse(request: Request) -> Response:
        st: _SseHostingState = request.app.state.theogony_sse
        assert st.sse_transport is not None and st.mcp_server is not None
        async with st.sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await st.mcp_server.run(
                read_stream,
                write_stream,
                st.mcp_server.create_initialization_options(),
            )
        return Response()

    sse = SseServerTransport("/messages/")

    # Build the cockpit FastAPI sub-app (PHX-0074, W6) so the hosted
    # container can serve /cockpit alongside /sse + /messages/. The
    # cockpit and the MCP server share the SAME store + report_writer
    # + embedder + LLM — one set of resources, two surfaces.
    #
    # Construction here uses placeholder state; the lifespan below
    # populates the real resources before any request is served. This
    # split is necessary because Starlette routes (Mount) are immutable
    # after Starlette() is constructed, but our resources are loaded
    # inside the lifespan via open_resources().
    settings_preview = Settings()
    cockpit_subapp: object | None = None
    if settings_preview.cockpit.enabled:
        from fastapi import FastAPI as _FastAPI

        from theogony.cockpit import mount_cockpit

        cockpit_subapp = _FastAPI(title="Theogony Cockpit (mounted on MCP host)")
        cockpit_subapp.state.settings = settings_preview
        cockpit_subapp.state.audit = None
        cockpit_subapp.state.embedder = None
        cockpit_subapp.state.llm = None
        cockpit_subapp.state.store = None
        cockpit_subapp.state.report_writer = None
        cockpit_subapp.state.stub_detector = None
        cockpit_subapp.state.mnemosyne_classifier = None
        cockpit_subapp.state.oneiros = None
        cockpit_subapp.state.oneiros_task = None
        mount_cockpit(cockpit_subapp, settings_preview)

    @contextlib.asynccontextmanager
    async def sse_lifespan_outer(app: Starlette) -> AsyncIterator[None]:
        async with open_resources(seed_path=seed_path) as res:
            st = _SseHostingState()
            st.resources = res
            st.mcp_server = build_server(res)
            st.started_perf = time.perf_counter()
            st.last_query_at = None
            st.sse_transport = sse
            app.state.theogony_sse = st
            if cockpit_subapp is not None and res.settings.cockpit.enabled:
                from theogony.agents.mnemosyne_classifier import (
                    build_mnemosyne_classifier,
                )
                from theogony.curiosity.stub_detector import StubDetector

                cockpit_subapp.state.settings = res.settings
                cockpit_subapp.state.audit = res.audit
                cockpit_subapp.state.embedder = res.embedder
                cockpit_subapp.state.llm = res.llm
                cockpit_subapp.state.store = res.store
                cockpit_subapp.state.report_writer = res.report_writer
                cockpit_subapp.state.stub_detector = StubDetector(
                    res.settings.curiosity.stub_thresholds,
                )
                cockpit_subapp.state.mnemosyne_classifier = build_mnemosyne_classifier(
                    res.settings, res.llm,
                )
                log.info("mcp sse: cockpit mounted at http://%s:%s/cockpit/", host, port)
            log.info("mcp sse: listening on http://%s:%s", host, port)
            yield

    routes = [
        Route("/health", endpoint=health, methods=["GET"]),
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ]
    if cockpit_subapp is not None:
        # Mount at root (empty prefix) — the cockpit's APIRouter already
        # carries prefix="/cockpit", so Starlette must NOT strip a prefix
        # before forwarding. /health, /sse, /messages/ are matched first
        # (Starlette tries routes in order); the cockpit catches the
        # rest, which in practice only includes /cockpit/* and the
        # static-asset paths it owns.
        routes.append(Mount("/", app=cockpit_subapp))

    from starlette.middleware import Middleware

    app = Starlette(
        routes=routes,
        lifespan=sse_lifespan_outer,
        middleware=[Middleware(_HostedRateLimitMiddleware)],
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


__all__ = [
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
]
