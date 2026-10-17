"""The bundled self-description is current and carries the measurement record (PHX-1112, piece 3).

`pantheon_self.jsonl.gz` was written on 2026-04-20, before the mesh existed and
before every measurement since; asked what the project had measured, it cited
sections of the Gen-1 implementation plan. These tests pin that the shipped dump
is regenerated from the current documents, that the measurement record is in
it, and that the question is answered from that record.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from theogony.seeds import pantheon_self_dump_path

ACCEPTANCE_QUESTION = "What has this project measured, and with what result?"


def _rows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with gzip.open(pantheon_self_dump_path(), "rt", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        rows = [json.loads(line) for line in handle if line.strip()]
    return header, rows


def test_the_dump_was_written_after_the_mesh_existed() -> None:
    header, rows = _rows()
    assert header["written_at"] >= "2026-10", header["written_at"]
    nodes = [r for r in rows if r.get("kind") == "node"]
    assert header["node_count"] == len(nodes)
    assert header["node_count"] > 600, "the April dump had 278 nodes"
    ids = [r["data"]["id"] for r in nodes]
    assert len(set(ids)) == len(ids), "two documents produced one id; the store keeps only one"


def test_the_dump_covers_exactly_the_documents_the_walker_admits() -> None:
    """Scope drift is caught here: a new etappe, or a renamed document, without a
    regeneration fails this test. Content drift inside a document — a heading
    edited after the last regeneration — is not caught; the dump is a snapshot
    and nothing regenerates it on a document change."""
    from theogony.docs_ingest.regenerate import _find_repo_root
    from theogony.docs_ingest.repo_walker import walk_repo

    _, rows = _rows()
    in_dump = {
        _source_of(r)
        for r in rows
        if r.get("kind") == "node" and r["data"]["source_ref"].get("location") == "document"
    }
    walked = {f.rel_path for f in walk_repo(_find_repo_root())}
    assert in_dump == walked, {"only in dump": in_dump - walked, "only walked": walked - in_dump}


def _source_of(row: dict[str, Any]) -> str:
    """A dump row is ``{"kind": ..., "data": {...}}``; the document is in the SourceRef."""
    data = row.get("data", row)
    return str((data.get("source_ref") or {}).get("identifier", ""))


def test_the_measurement_record_is_in_the_dump() -> None:
    _, rows = _rows()
    sources = {_source_of(r) for r in rows if r.get("kind") == "node"}
    etappes = {s for s in sources if "docs/etappes/" in s}
    assert any("qa_constellation.md" in s for s in etappes), sorted(etappes)[:5]
    assert any("mesh_over_mcp.md" in s for s in etappes)
    assert not any("_brief" in s for s in etappes), "sprint briefs state plans as facts"
    assert not any("demo_log.md" in s for s in etappes)


@pytest.mark.asyncio
async def test_asked_what_was_measured_the_self_description_answers_from_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the Gen-1 read path an arriving agent uses — no key, the
    bundled dump, the real embedder — the cited sources include an etappe."""
    from theogony.agents.factory import build_llm_or_offline
    from theogony.config.settings import LLMSettings, Settings
    from theogony.core.model import KnowledgeEdge, KnowledgeNode
    from theogony.docs_ingest.dump import read_dump
    from theogony.extraction.audit import ExtractionAuditLog
    from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
    from theogony.mcp.server import McpResources, tool_ask
    from theogony.reporting.writer import RunReportWriter
    from theogony.stores.memory import InMemoryKnowledgeStore

    # As tests/test_keyless_entrance.py builds it: the shipped default provider,
    # no key for anyone, no fallback — whatever the developer's shell exports.
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        OPENAI_API_KEY=None,
        ANTHROPIC_API_KEY=None,
        GEMINI_API_KEY=None,
        GOOGLE_API_KEY=None,
        llm=LLMSettings(provider="openai", fallback_provider=None),
    )
    store = InMemoryKnowledgeStore()
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])
    llm, reason = build_llm_or_offline(settings)
    audit = ExtractionAuditLog(tmp_path / "audit.sqlite")
    audit.__enter__()
    try:
        res = McpResources(
            settings=settings,
            audit=audit,
            wd_cache=None,
            embedder=LocalSentenceTransformerEmbedder(
                model_id=settings.embedding.model_id, dim=settings.embedding.dim
            ),
            llm=llm,
            store=store,
            report_writer=RunReportWriter(tmp_path / "reports"),
            llm_unavailable_reason=reason,
        )
        payload = await tool_ask(res, q=ACCEPTANCE_QUESTION, k=8, hops=2, synthesize=False)
    finally:
        audit.__exit__(None, None, None)
    assert "error" not in payload
    sources = [_source_of(n) for n in payload["constellation"]["nodes"]]
    assert any("docs/etappes/" in s for s in sources), sources
