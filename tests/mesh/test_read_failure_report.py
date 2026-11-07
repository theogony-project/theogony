"""PHX-1116: a read that raises still writes what it can, and a report that says so.

Contract 3 (AGENTS.md) asks a failed run for a structured failure report. The
reader had none: an exception mid-read left the buffered edges to die with the
reader instance and no IngestRunReport at all, so every caller got the
exception string and nothing else.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.config.settings import Settings
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.ingestion.vectorizer import MeshTextVectorizer
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.reporting.models import IngestRunReport

_HEDIN = {"label": "Sven Hedin", "entity_type": "person", "tags": ["explorer"]}
_PLATEAU = {
    "label": "Tibetan Plateau",
    "entity_type": "place",
    "tags": ["plateau", "asia"],
    "description": "High plateau in Central Asia",
}


def _reading(*concepts: dict) -> str:
    return json.dumps(
        {
            "concepts": [{"qids": [], **c} for c in concepts],
            "relations": [],
            "paragraph_concept": None,
        }
    )


_P1 = "Sven Hedin crossed the Tibetan Plateau."
_P2 = "Sven Hedin was born in Stockholm."
_P3 = "Sven Hedin mapped the Brahmaputra River."
_RESPONSES = {
    f"PARAGRAPH:\n{_P1}": _reading(
        {**_HEDIN, "description": "Swedish explorer known for expeditions in Central Asia"},
        _PLATEAU,
    ),
    f"PARAGRAPH:\n{_P2}": _reading(
        {**_HEDIN, "description": "Born in Stockholm in 1865"},
        _PLATEAU,
    ),
    f"PARAGRAPH:\n{_P3}": _reading(
        {**_HEDIN, "description": "Mapped the course of the Brahmaputra River"},
    ),
}
_TEXT = f"{_P1}\n\n{_P2}\n\n{_P3}"


def _reader(mesh_runtime: MeshRuntime, tmp_path: Path, **kwargs: object) -> MeshParagraphReader:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")  # type: ignore[call-arg]
    return MeshParagraphReader(
        mesh_runtime,
        llm=StubLLMProvider(responses=_RESPONSES),
        max_paragraphs=10,
        settings=settings,
        compact_every=0,
        **kwargs,  # type: ignore[arg-type]
    )


def _read(reader: MeshParagraphReader, tmp_path: Path) -> dict:
    return asyncio.run(
        reader.read_text(
            text=_TEXT,
            source_type="test",
            source_identifier="hedin",
            title="Hedin",
            anchor=str(tmp_path / "hedin.txt"),
        )
    )


def _reports(tmp_path: Path) -> list[IngestRunReport]:
    directory = tmp_path / "data" / "run_reports" / "ingest"
    return [
        IngestRunReport.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(directory.glob("*.json"))
    ]


def _audit_rows(mesh_runtime: MeshRuntime, action: str) -> list[dict]:
    rows = mesh_runtime.audit.list_recent(limit=1000)
    return [json.loads(r["payload_json"]) for r in rows if r["action"] == action]


def _nodes_in_store(mesh_runtime: MeshRuntime) -> int:
    return mesh_runtime.nodes.consolidated_count() + mesh_runtime.nodes.chunk_count()


def _fail_on_chunk_of(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make embedding the chunk of one paragraph raise — a failure that is not a
    buffer's own write."""
    original = MeshTextVectorizer.semantic

    async def semantic(self, value):  # type: ignore[no-untyped-def]
        if value == text:
            raise RuntimeError("embedder down")
        return await original(self, value)

    monkeypatch.setattr(MeshTextVectorizer, "semantic", semantic)


def test_a_read_whose_edge_write_raises_reports_failed_and_reraises(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(edges):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full")

    monkeypatch.setattr(mesh_runtime.edges, "append_edges", broken)
    reader = _reader(mesh_runtime, tmp_path)
    with pytest.raises(RuntimeError, match="disk full") as raised:
        _read(reader, tmp_path)

    [report] = _reports(tmp_path)
    assert report.status == "failed" and report.verdict == "failed"
    assert "RuntimeError: disk full" in report.verdict_reasoning
    assert "after the last paragraph" in report.verdict_reasoning
    assert "writing the buffered edges" in report.verdict_reasoning
    failed_stages = [s for s in report.stages if s.status == "failed"]
    assert [s.name for s in failed_stages] == ["stored"]
    assert "disk full" in (failed_stages[0].notes or "")
    # the numbers say what landed: every node, and none of the edges
    assert report.store.nodes_upserted == _nodes_in_store(mesh_runtime) > 0
    assert report.store.edges_upserted == 0
    assert not mesh_runtime.edges.load_all_edges()
    assert any("buffered edges not written" in a for a in report.anomalies), report.anomalies
    assert report.ner.total_mentions == 5
    # the caller can find the report from the exception and from the reader
    assert reader.failure_report is not None
    assert reader.failure_report.run_id == report.run_id
    assert any(report.run_id in note for note in getattr(raised.value, "__notes__", []))
    # the audit log holds the run, and the per-item rows staged before it
    [run] = _audit_rows(mesh_runtime, "mesh_ingest_run")
    assert run["status"] == "failed" and "disk full" in run["error"]
    assert report.audit_log_run_id is not None
    assert len(_audit_rows(mesh_runtime, "mesh_ingest_link_decision")) == 5


def test_a_failure_elsewhere_still_lands_the_edges_buffered_before_it(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paragraphs 1 and 2 were read completely; their edges were only buffered
    when paragraph 3 failed. They land, and the report's edge count is the
    store's."""
    _fail_on_chunk_of(_P3, monkeypatch)
    reader = _reader(mesh_runtime, tmp_path)
    with pytest.raises(RuntimeError, match="embedder down"):
        _read(reader, tmp_path)

    [report] = _reports(tmp_path)
    assert report.status == "failed"
    assert "at paragraph 3 of 3 (embedded)" in report.verdict_reasoning
    assert [s.name for s in report.stages if s.status == "failed"] == ["embedded"]
    edges = mesh_runtime.edges.load_all_edges()
    assert edges and report.store.edges_upserted == len(edges)
    assert report.store.nodes_upserted == _nodes_in_store(mesh_runtime)
    assert any("buffered edges written after the failure" in a for a in report.anomalies)
    # every edge points at a node the store holds: landing them dangles nothing
    node_ids = {str(n.id) for n in mesh_runtime.nodes.iter_consolidated()}
    node_ids |= {str(c.id) for c in mesh_runtime.nodes.iter_chunks()}
    assert all(str(e.source_id) in node_ids and str(e.target_id) in node_ids for e in edges)
    assert "2 paragraphs" in report.recommendations[0]


def test_a_failure_elsewhere_still_writes_the_pending_description_revisions(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_on_chunk_of(_P3, monkeypatch)
    reader = _reader(mesh_runtime, tmp_path, accrue_descriptions=True)
    with pytest.raises(RuntimeError, match="embedder down"):
        _read(reader, tmp_path)

    [report] = _reports(tmp_path)
    assert report.store.descriptions_revised == 1
    assert any("1 revised descriptions written after the failure" in a for a in report.anomalies)
    [hedin] = [
        n
        for n in mesh_runtime.nodes.iter_consolidated()
        if (n.description or "").startswith("Sven Hedin")
    ]
    assert hedin.description == (
        "Sven Hedin — Swedish explorer known for expeditions in Central Asia. "
        "Born in Stockholm in 1865"
    )


def test_the_buffer_whose_write_raised_is_not_written_a_second_time(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`append_edges` writes three tables in turn; a retry after a partial write
    would duplicate what landed. The failure path leaves that buffer alone, even
    when a second attempt would have succeeded."""
    calls: list[int] = []
    original = mesh_runtime.edges.append_edges

    def once_broken(edges):  # type: ignore[no-untyped-def]
        calls.append(len(edges))
        if len(calls) == 1:
            raise RuntimeError("transient")
        return original(edges)

    monkeypatch.setattr(mesh_runtime.edges, "append_edges", once_broken)
    with pytest.raises(RuntimeError, match="transient"):
        _read(_reader(mesh_runtime, tmp_path), tmp_path)
    assert len(calls) == 1
    assert not mesh_runtime.edges.load_all_edges()


def test_a_report_that_cannot_be_written_does_not_replace_the_reads_exception(
    mesh_runtime: MeshRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_on_chunk_of(_P3, monkeypatch)
    reader = _reader(mesh_runtime, tmp_path)

    def unwritable(report):  # type: ignore[no-untyped-def]
        raise OSError("read-only file system")

    monkeypatch.setattr(reader.report_writer, "write", unwritable)
    with pytest.raises(RuntimeError, match="embedder down") as raised:
        _read(reader, tmp_path)
    assert reader.failure_report is not None
    notes = getattr(raised.value, "__notes__", [])
    assert any("could not be written" in note for note in notes), notes


def test_a_completed_read_says_so_in_its_audit_row(
    mesh_runtime: MeshRuntime, tmp_path: Path
) -> None:
    reader = _reader(mesh_runtime, tmp_path)
    result = _read(reader, tmp_path)
    assert result["verdict"] != "failed" and reader.failure_report is None
    [run] = _audit_rows(mesh_runtime, "mesh_ingest_run")
    assert run["status"] == "completed"
    [report] = _reports(tmp_path)
    assert report.store.edges_upserted == len(mesh_runtime.edges.load_all_edges())
    assert all(s.status == "ok" for s in report.stages)


def test_an_audit_write_that_raises_keeps_its_rows_staged(
    mesh_runtime: MeshRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = mesh_runtime.audit
    audit.stage(action="probe", detail={"n": 1})
    audit.stage(action="probe", detail={"n": 2})
    original = audit._table.add
    calls: list[int] = []

    def once_broken(rows):  # type: ignore[no-untyped-def]
        calls.append(len(rows))
        if len(calls) == 1:
            raise RuntimeError("commit conflict")
        return original(rows)

    monkeypatch.setattr(audit._table, "add", once_broken)
    with pytest.raises(RuntimeError, match="commit conflict"):
        audit.flush()
    assert audit.pending() == 2, "the rows are not lost with the exception"
    assert audit.flush() == 2
    assert len(_audit_rows(mesh_runtime, "probe")) == 2
