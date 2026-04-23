"""SSE status channel for Iris cockpit (PHX-0074)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from starlette.responses import StreamingResponse

from theogony.cockpit.aggregations import compute_status_snapshot
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.reporting.writer import RunReportWriter


def sse_tick_interval_s(settings: Settings) -> float:
    return max(5.0, min(300.0, float(settings.cockpit.status_sse_interval_s)))


async def _status_event_stream(
    store: KnowledgeStore,
    writer: RunReportWriter,
    settings: Settings,
) -> AsyncIterator[bytes]:
    interval = sse_tick_interval_s(settings)
    while True:
        snap = await compute_status_snapshot(store, writer, settings, uptime_s=0)
        payload = {
            "node_count": snap.node_count,
            "edge_count": snap.edge_count,
            "queries_24h": snap.activity_24h.get("query", 0),
            "verdict_mix": snap.verdict_mix_24h,
        }
        line = f"event: status_tick\r\ndata: {json.dumps(payload, separators=(',', ':'))}\r\n\r\n"
        yield line.encode("utf-8")
        await asyncio.sleep(interval)


def status_sse_response(
    store: KnowledgeStore,
    writer: RunReportWriter,
    settings: Settings,
) -> StreamingResponse:
    return StreamingResponse(
        _status_event_stream(store, writer, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
