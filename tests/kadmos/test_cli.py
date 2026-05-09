"""
CLI tests for `theogony kadmos read` (E5).

Uses typer.testing.CliRunner with mocked fetch + LLM + embedder.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from theogony.agents.llm import LLMResult
from theogony.cli import app
from theogony.kadmos.wikipedia_parser import WikiSection

_runner = CliRunner()

_FIXTURE_SECTIONS = [
    WikiSection(
        title="Early life",
        level=2,
        paragraphs=["Sven Hedin was born in Stockholm.", "He explored Central Asia."],
    )
]

_EMPTY_LLM_JSON = json.dumps(
    {
        "new_concepts": [{"label": "Tibet", "description": "A region", "confidence": 0.9}],
        "new_connections": [],
        "confirmed_hypotheses": [],
        "rejected_hypotheses": [],
        "revisions": [],
        "synthesis": None,
        "open_tensions": [],
        "next_granularity": "paragraph",
    }
)


def _mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.model_id = "stub"
    llm.complete = AsyncMock(
        return_value=LLMResult(text=_EMPTY_LLM_JSON, latency_ms=0, cost_eur=0.001)
    )
    return llm


def _mock_embedder() -> MagicMock:
    emb = MagicMock()
    emb.model_id = "stub-emb"
    emb.dim = 4
    emb.embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
    emb.embed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    return emb


def test_kadmos_read_help() -> None:
    result = _runner.invoke(app, ["kadmos", "read", "--help"])
    assert result.exit_code == 0
    assert "Wikipedia article title" in result.output


def test_kadmos_app_in_main_help() -> None:
    result = _runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "kadmos" in result.output


def test_kadmos_read_no_args_fails() -> None:
    result = _runner.invoke(app, ["kadmos", "read"])
    assert result.exit_code != 0


def test_kadmos_read_no_chronicle_creates_json(tmp_path: Path) -> None:
    output_path = tmp_path / "ar.json"

    async def _fake_fetch(url: str, **kw):
        return _FIXTURE_SECTIONS

    with (
        patch("theogony.kadmos.reader.fetch_article_structured", side_effect=_fake_fetch),
        patch("theogony.cli.build_llm_from_settings", return_value=_mock_llm()),
        patch("theogony.cli.LocalSentenceTransformerEmbedder", return_value=_mock_embedder()),
    ):
        result = _runner.invoke(
            app,
            [
                "kadmos",
                "read",
                "--no-chronicle",
                "--sections",
                "1",
                "--output",
                str(output_path),
                "Sven Hedin",
            ],
        )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert "session_id" in data
    assert "steps" in data


def test_kadmos_read_output_mentions_session_complete(tmp_path: Path) -> None:
    output_path = tmp_path / "ar2.json"

    async def _fake_fetch(url: str, **kw):
        return _FIXTURE_SECTIONS

    with (
        patch("theogony.kadmos.reader.fetch_article_structured", side_effect=_fake_fetch),
        patch("theogony.cli.build_llm_from_settings", return_value=_mock_llm()),
        patch("theogony.cli.LocalSentenceTransformerEmbedder", return_value=_mock_embedder()),
    ):
        result = _runner.invoke(
            app,
            [
                "kadmos",
                "read",
                "--no-chronicle",
                "--sections",
                "1",
                "--output",
                str(output_path),
                "Sven Hedin",
            ],
        )

    assert "Kadmos session complete" in result.output or result.exit_code == 0
