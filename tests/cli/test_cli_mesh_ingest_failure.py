"""`theogony mesh ingest` after a read that raises (PHX-1116).

The command names the failure report and exits 1, and prints the exception as
text: a message with "[...]" in it — a path, a pydantic error's
"[type=...]" — is not Rich markup (found by review).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from theogony.cli import app


def test_a_failed_ingest_names_its_report_and_prints_the_error_as_text(
    cli_runner: CliRunner,
    cli_data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader

    async def boom(self, tally, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full at [/data/mesh_ws/lance] [type=less_than_equal]")

    monkeypatch.setattr(MeshParagraphReader, "_read", boom)
    monkeypatch.setenv("THEOGONY_LLM__PROVIDER", "stub")
    text = tmp_path / "hedin.txt"
    text.write_text("Sven Hedin crossed the Tibetan Plateau.", encoding="utf-8")
    result = cli_runner.invoke(
        app,
        [
            "mesh",
            "ingest",
            str(text),
            "--text-file",
            "--anchor",
            "test",
            "--root",
            str(tmp_path / "mesh_ws"),
        ],
    )
    assert result.exit_code == 1, result.output
    out = " ".join(result.output.split())
    assert "[/data/mesh_ws/lance]" in out and "[type=less_than_equal]" in out
    assert "report:" in out and "(status failed)" in out
    assert list((cli_data_dir / "run_reports" / "ingest").glob("*.json"))
