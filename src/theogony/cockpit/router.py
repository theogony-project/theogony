"""FastAPI router for the Iris cockpit (PHX-0074)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from html import escape
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from markdown_it import MarkdownIt
from starlette.responses import PlainTextResponse
from starlette.templating import Jinja2Templates

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.chronicle.append_fragments import append_text_fragments
from theogony.cockpit.aggregations import (
    build_hover_lupe_payload,
    compute_status_snapshot,
    list_clusters_summary,
    list_recent_reports,
    search_nodes,
)
from theogony.cockpit.dependencies import (
    get_authenticated_user,
    get_embedder,
    get_report_writer,
    get_settings,
    get_store_readonly,
    require_cockpit_access,
)
from theogony.cockpit.explorer import (
    _build_pipeline,
    explorer_page_context,
    run_explorer_query,
    stream_explorer_ask_sse,
)
from theogony.cockpit.growth_stream import stream_growth_run, stream_research_request_run
from theogony.cockpit.manifest import ManifestRepository, _default_manifest_markdown
from theogony.cockpit.sample_mode import (
    cluster_drill_member_cap,
    effective_cluster_list_limit,
    effective_report_limit,
    effective_search_limit,
)
from theogony.cockpit.sse import status_sse_response
from theogony.config.settings import Settings
from theogony.core.model import (
    ConstellationEdge,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
    NodeType,
)
from theogony.core.store import KnowledgeStore
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.verification_pool import VerificationPool, VerificationPoolStatusDTO
from theogony.extraction.embedding import EmbeddingProvider
from theogony.reporting.models import QueryRunReport
from theogony.reporting.writer import RunReportWriter

_PKG = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_PKG / "templates"))

_MAX_MANIFEST_BYTES = 64 * 1024

REPORT_TABS = (
    ("query", "Queries"),
    ("ingest", "Ingests"),
    ("oneiros", "Oneiros"),
    ("clustering", "Clustering"),
    ("blindspot", "Blindspots"),
    ("mnemosyne", "Mnemosyne"),
)


def build_cockpit_router() -> APIRouter:
    router = APIRouter(
        prefix="/cockpit",
        tags=["cockpit"],
        dependencies=[Depends(require_cockpit_access)],
    )

    @router.get("/", response_class=HTMLResponse, name="cockpit_status")
    async def status_panel(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
        _user: Annotated[object | None, Depends(get_authenticated_user)],
    ) -> HTMLResponse:
        started = getattr(request.app.state, "cockpit_started_monotonic", None)
        uptime_s = int(time.monotonic() - float(started)) if started is not None else 0
        snap = await compute_status_snapshot(store, writer, settings, uptime_s=uptime_s)
        limit = effective_cluster_list_limit(settings)
        clusters = await list_clusters_summary(store, limit=limit)
        return templates.TemplateResponse(
            request,
            "status.html",
            {
                "snap": snap,
                "clusters": clusters,
                "settings": settings,
                "sample_only": settings.cockpit.sample_only,
            },
        )

    @router.get("/browser", response_class=HTMLResponse)
    async def browser_page(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        _user: Annotated[object | None, Depends(get_authenticated_user)],
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "browser.html",
            {"settings": settings},
        )

    @router.get("/browser/search", response_class=HTMLResponse)
    async def search_fragment(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
        settings: Annotated[Settings, Depends(get_settings)],
        q: str = "",
        node_type: str | None = None,
        layer: str | None = None,
    ) -> HTMLResponse:
        nt = NodeType(node_type) if node_type else None
        ly = Layer(layer) if layer else None
        limit = effective_search_limit(settings)
        results = await search_nodes(
            store,
            embedder,
            query=q,
            limit=limit,
            node_type=nt,
            layer=ly,
        )
        return templates.TemplateResponse(
            request,
            "partials/_search_results.html",
            {"request": request, "results": results},
        )

    @router.get("/browser/node/{node_id}", response_class=HTMLResponse)
    async def node_detail(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        settings: Annotated[Settings, Depends(get_settings)],
        node_id: str,
    ) -> HTMLResponse:
        node = await store.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="node not found")
        hover = await build_hover_lupe_payload(store, center_id=node_id)
        return templates.TemplateResponse(
            request,
            "partials/_node_card.html",
            {
                "request": request,
                "node": node,
                "hover_lupe_data": hover,
                "settings": settings,
            },
        )

    @router.get("/clusters", response_class=HTMLResponse)
    async def clusters_page(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> HTMLResponse:
        limit = effective_cluster_list_limit(settings)
        clusters = await list_clusters_summary(store, limit=limit)
        return templates.TemplateResponse(
            request,
            "clusters.html",
            {"clusters": clusters, "settings": settings},
        )

    @router.get("/clusters/{cluster_id}", response_class=HTMLResponse)
    async def cluster_detail(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        settings: Annotated[Settings, Depends(get_settings)],
        cluster_id: str,
    ) -> HTMLResponse:
        summaries = await store.list_clusters()
        summary = next((s for s in summaries if s.cluster_id == cluster_id), None)
        if summary is None:
            raise HTTPException(status_code=404, detail="cluster not found")
        cap = cluster_drill_member_cap(settings)
        member_ids: list[str] = []
        async for mid in store.get_cluster_members(cluster_id):
            member_ids.append(mid)
            if len(member_ids) >= cap:
                break
        nodes: list[KnowledgeNode] = []
        for mid in member_ids:
            n = await store.get_node(mid)
            if n is not None:
                nodes.append(n)
        member_set = set(member_ids)
        seen_edge: set[str] = set()
        intra: list[dict[str, object]] = []
        cross: list[dict[str, object]] = []

        def _add_edge(e: KnowledgeEdge | ConstellationEdge) -> None:
            eid = (
                getattr(e, "id", None)
                or getattr(e, "edge_id", None)
                or f"{e.source_id}:{e.relation_type}:{e.target_id}"
            )
            if eid in seen_edge:
                return
            seen_edge.add(eid)
            w = max(0.0, min(1.0, e.weight + e.pheromone_delta))
            row = {
                "id": eid,
                "source": e.source_id,
                "target": e.target_id,
                "weight": w,
                "relation_type": e.relation_type,
            }
            src_in = e.source_id in member_set
            tgt_in = e.target_id in member_set
            if src_in and tgt_in:
                intra.append(row)
            elif src_in or tgt_in:
                cross.append(row)

        for mid in member_ids:
            hood = await store.get_neighborhood(mid, depth=1, min_weight=0.0)
            for e in hood.edges:
                _add_edge(e)
        graph_payload: dict[str, object] = {
            "nodes": [
                {"id": n.id, "label": n.label, "node_type": n.node_type.value} for n in nodes
            ],
            "intra": intra,
            "cross": cross,
        }
        return templates.TemplateResponse(
            request,
            "partials/_cluster_detail.html",
            {
                "request": request,
                "summary": summary,
                "nodes": nodes,
                "graph_payload": graph_payload,
                "settings": settings,
            },
        )

    @router.get("/reports", response_class=HTMLResponse)
    async def reports_page(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "reports.html",
            {"report_tabs": REPORT_TABS, "settings": settings},
        )

    @router.get("/reports/{report_type}", response_class=HTMLResponse)
    async def reports_table(
        request: Request,
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
        report_type: str,
        verdict: str | None = None,
    ) -> HTMLResponse:
        if report_type not in {t[0] for t in REPORT_TABS}:
            raise HTTPException(status_code=404, detail="unknown report type")
        limit = effective_report_limit(settings)
        rows = await list_recent_reports(
            writer,
            report_type,
            limit=limit,
            verdict_filter=verdict,
        )
        return templates.TemplateResponse(
            request,
            "partials/_report_row.html",
            {"request": request, "rows": rows, "report_type": report_type},
        )

    @router.get("/reports/{report_type}/{run_id}", response_class=HTMLResponse)
    async def report_detail(
        request: Request,
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
        report_type: str,
        run_id: str,
    ) -> HTMLResponse:
        d = writer.directory_for(report_type)
        path = d / f"{run_id}.json"
        if not path.is_file():
            for p in d.iterdir():
                if p.is_file() and p.suffix == ".json" and p.stem.startswith(run_id):
                    path = p
                    break
        if not path.is_file():
            raise HTTPException(status_code=404, detail="report not found")
        body = path.read_text(encoding="utf-8")
        return templates.TemplateResponse(
            request,
            "partials/_report_full.html",
            {"request": request, "json_body": body},
        )

    @router.get("/manifest", response_class=HTMLResponse)
    async def manifest_get(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> HTMLResponse:
        repo = ManifestRepository(settings)
        content = repo.read()
        history = repo.list_history()
        return templates.TemplateResponse(
            request,
            "manifest.html",
            {
                "request": request,
                "content": content,
                "history": history,
                "sample_only": settings.cockpit.sample_only,
            },
        )

    @router.post("/manifest/preview", response_class=HTMLResponse)
    async def manifest_preview(
        request: Request,
        content: Annotated[str, Form()] = "",
    ) -> HTMLResponse:
        md = MarkdownIt()
        html = md.render(content)
        return HTMLResponse(f'<div class="prose prose-invert max-w-none">{html}</div>')

    @router.get("/manifest/history/{timestamp}", response_class=HTMLResponse)
    async def manifest_history_fragment(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        timestamp: str,
    ) -> HTMLResponse:
        repo = ManifestRepository(settings)
        try:
            text = repo.read_snapshot(timestamp)
        except OSError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        safe = escape(text)
        return HTMLResponse(
            f'<textarea id="manifest-textarea" name="content" '
            f'class="w-full h-96 font-mono bg-slate-800 border border-slate-700 rounded p-2 '
            f'maxlength="{_MAX_MANIFEST_BYTES}">{safe}</textarea>'
        )

    @router.post("/manifest", response_class=HTMLResponse)
    async def manifest_save(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        content: Annotated[str | None, Form()] = None,
    ) -> HTMLResponse:
        if settings.cockpit.sample_only:
            raise HTTPException(status_code=403, detail="sample-only mode")
        body = content if content is not None else ""
        if body == "":
            body = _default_manifest_markdown()
        try:
            body.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HTTPException(status_code=400, detail="invalid utf-8") from exc
        if len(body.encode("utf-8")) > _MAX_MANIFEST_BYTES:
            raise HTTPException(status_code=413, detail="manifest too large")
        repo = ManifestRepository(settings)
        try:
            repo.save(body)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return HTMLResponse('<span class="text-emerald-400">Saved.</span>')

    @router.get("/explorer", response_class=HTMLResponse, name="cockpit_explorer")
    async def explorer_page(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        _user: Annotated[object | None, Depends(get_authenticated_user)],
    ) -> HTMLResponse:
        llm = getattr(request.app.state, "llm", None)
        ctx = explorer_page_context(settings, llm)
        raw_growth = (request.query_params.get("growth") or "").strip().lower()
        growth_enabled = raw_growth in ("on", "true", "1")
        return templates.TemplateResponse(
            request,
            "explorer.html",
            {"settings": settings, "growth_enabled": growth_enabled, **ctx},
        )

    @router.post("/api/ask", response_class=JSONResponse)
    async def explorer_ask(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        query = str(body.get("q") or body.get("query") or "")
        try:
            k = int(body.get("k", 10))
            hops = int(body.get("hops", 2))
            thinking_max = int(body.get("thinking_max", 2))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"k/hops/thinking_max not int: {exc}",
            ) from exc
        raw_cs = body.get("conversation_summary")
        if raw_cs is not None and not isinstance(raw_cs, str):
            raise HTTPException(
                status_code=400,
                detail="conversation_summary must be a string or null",
            )
        raw_cm = body.get("conversation_messages")
        if raw_cm is not None and not isinstance(raw_cm, list):
            raise HTTPException(
                status_code=400,
                detail="conversation_messages must be an array or null",
            )
        llm = getattr(request.app.state, "llm", None)
        audit = getattr(request.app.state, "audit", None)
        payload = await run_explorer_query(
            settings=settings,
            store=store,
            embedder=embedder,
            llm=llm,
            audit=audit,
            report_writer=writer,
            query=query,
            k=k,
            hops=hops,
            thinking_max=thinking_max,
            conversation_summary=raw_cs,
            conversation_messages=raw_cm,
        )
        return JSONResponse(payload)

    @router.post("/api/ask-stream")
    async def explorer_ask_stream(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> StreamingResponse:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        query = str(body.get("q") or body.get("query") or "")
        try:
            k = int(body.get("k", 10))
            hops = int(body.get("hops", 2))
            thinking_max = int(body.get("thinking_max", 2))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"k/hops/thinking_max not int: {exc}",
            ) from exc
        raw_cs = body.get("conversation_summary")
        if raw_cs is not None and not isinstance(raw_cs, str):
            raise HTTPException(
                status_code=400,
                detail="conversation_summary must be a string or null",
            )
        raw_cm = body.get("conversation_messages")
        if raw_cm is not None and not isinstance(raw_cm, list):
            raise HTTPException(
                status_code=400,
                detail="conversation_messages must be an array or null",
            )
        llm = getattr(request.app.state, "llm", None)
        audit = getattr(request.app.state, "audit", None)

        async def gen() -> AsyncIterator[bytes]:
            async for chunk in stream_explorer_ask_sse(
                settings=settings,
                store=store,
                embedder=embedder,
                llm=llm,
                audit=audit,
                report_writer=writer,
                query=query,
                k=k,
                hops=hops,
                thinking_max=thinking_max,
                conversation_summary=raw_cs,
                conversation_messages=raw_cm,
            ):
                yield chunk

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/api/growth-stream")
    async def explorer_growth_stream(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> StreamingResponse:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        if body.get("growth") is not True:
            raise HTTPException(
                status_code=400,
                detail="use /cockpit/api/ask-stream when growth is not requested",
            )
        query = str(body.get("q") or body.get("query") or "")
        try:
            k = int(body.get("k", 10))
            hops = int(body.get("hops", 2))
            thinking_max = int(body.get("thinking_max", 2))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"k/hops/thinking_max not int: {exc}",
            ) from exc
        raw_cs = body.get("conversation_summary")
        if raw_cs is not None and not isinstance(raw_cs, str):
            raise HTTPException(
                status_code=400,
                detail="conversation_summary must be a string or null",
            )
        raw_cm = body.get("conversation_messages")
        if raw_cm is not None and not isinstance(raw_cm, list):
            raise HTTPException(
                status_code=400,
                detail="conversation_messages must be an array or null",
            )
        llm = getattr(request.app.state, "llm", None)
        audit = getattr(request.app.state, "audit", None)

        async def gen() -> AsyncIterator[bytes]:
            async for chunk in stream_growth_run(
                settings=settings,
                store=store,
                embedder=embedder,
                llm=llm,
                audit=audit,
                report_writer=writer,
                query=query,
                k=k,
                hops=hops,
                thinking_max=thinking_max,
                conversation_summary=raw_cs,
                conversation_messages=raw_cm,
            ):
                yield chunk

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/api/research-request", response_class=JSONResponse)
    async def explorer_research_request(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> JSONResponse:
        """Emit a CuriosityTrigger with explicit_user_request=True for the named completed run."""
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        run_id = str(body.get("run_id") or "").strip()
        query = str(body.get("query") or "").strip()
        if not run_id or not query:
            raise HTTPException(status_code=400, detail="run_id and query are required")
        qpath = writer.directory_for("query") / f"{run_id}.json"
        if not qpath.is_file():
            raise HTTPException(status_code=404, detail="query run not found")
        try:
            report = QueryRunReport.model_validate_json(qpath.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid query report: {exc}") from exc
        if report.query.strip() != query:
            raise HTTPException(status_code=400, detail="query does not match saved run")
        if report.stub_verdict is None or report.region_descriptor is None:
            raise HTTPException(
                status_code=422,
                detail="query run is missing stub_verdict or region_descriptor",
            )
        raw_llm = getattr(request.app.state, "llm", None)
        llm: LLMProvider
        if raw_llm is not None:
            llm = raw_llm
        else:
            try:
                llm = build_llm_from_settings(settings)
            except (ValueError, NotImplementedError):
                llm = StubLLMProvider(model_id=settings.llm.model_id or "stub-llm")
        audit = getattr(request.app.state, "audit", None)
        pipeline = _build_pipeline(
            settings=settings,
            store=store,
            embedder=embedder,
            llm=llm,
            audit=audit,
            report_writer=writer,
            growth_bridge=GrowthBridge(settings.curiosity.growth_bridge),
        )
        trigger = await pipeline.emit_user_research_request(
            origin_query=query,
            origin_query_run_id=run_id,
            answer_verdict=report.verdict,
            cited_node_count=report.citation_quality.cited_node_count,
            stub_verdict=report.stub_verdict,
            region_descriptor=report.region_descriptor,
        )
        return JSONResponse({"trigger_id": trigger.trigger_id if trigger else None})

    @router.get("/api/verification-pool", response_class=JSONResponse)
    async def verification_pool_status(
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> JSONResponse:
        pool = VerificationPool(settings)
        entries = pool.entries()
        recent = sorted(entries, key=lambda e: e.acquired_at, reverse=True)[:10]
        dto = VerificationPoolStatusDTO(stats=pool.stats(), recent_entries=recent)
        return JSONResponse(dto.model_dump(mode="json"))

    @router.get("/api/research-request-stream/{trigger_id}")
    async def explorer_research_request_stream(
        trigger_id: str,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            async for chunk in stream_research_request_run(
                settings=settings,
                store=store,
                report_writer=writer,
                trigger_id=trigger_id,
            ):
                yield chunk

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/api/chronicle-append", response_class=JSONResponse)
    async def explorer_chronicle_append(
        request: Request,
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> JSONResponse:
        if settings.cockpit.sample_only:
            raise HTTPException(
                status_code=403,
                detail="chronicle append is disabled in cockpit sample-only mode",
            )
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        fragments = body.get("fragments")
        if not isinstance(fragments, list):
            fragments = []
        context_note = body.get("context_note")
        if context_note is not None and not isinstance(context_note, str):
            raise HTTPException(status_code=400, detail="context_note must be a string")
        payload = await append_text_fragments(
            settings=settings,
            store=store,
            embedder=embedder,
            fragments=fragments,
            context_note=context_note,
            origin="cockpit_explorer",
        )
        return JSONResponse(payload)

    @router.get("/sse/status")
    async def sse_status(
        store: Annotated[KnowledgeStore, Depends(get_store_readonly)],
        writer: Annotated[RunReportWriter, Depends(get_report_writer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> Response:
        return status_sse_response(store, writer, settings)

    @router.get("/healthz", response_class=PlainTextResponse)
    async def cockpit_health() -> str:
        return "ok"

    return router


def mount_cockpit(app: object, settings: Settings) -> None:
    """Mount static files + cockpit router on ``app``."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    if not isinstance(app, FastAPI):
        raise TypeError("mount_cockpit expects a FastAPI app")
    static_dir = _PKG / "static"
    app.mount(
        "/cockpit/static",
        StaticFiles(directory=str(static_dir)),
        name="cockpit_static",
    )
    app.state.cockpit_started_monotonic = time.monotonic()
    app.include_router(cockpit_router)


cockpit_router = build_cockpit_router()
