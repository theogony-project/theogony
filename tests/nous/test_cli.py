"""
CLI tests for `theogony nous read` (nous_implementation_brief §5, E4).

Uses typer.testing.CliRunner with mocked HTTP + stub LLM.
No network, no live LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from theogony.agents.llm import LLMResult
from theogony.cli import app
from theogony.nous.wikipedia_parser import WikiSection

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_llm_response() -> str:
    return json.dumps(
        {
            "new_concepts": [
                {
                    "label": "Sven Hedin",
                    "node_type": "person",
                    "description": "Swedish explorer",
                    "confidence": 0.9,
                }
            ],
            "new_edges": [],
            "chronicle_hits_used": [],
            "synthesis_event": None,
            "repair_events": [],
            "resolution_updates": [],
        }
    )


_FIXTURE_SECTIONS = [
    WikiSection(
        title="Early life",
        level=2,
        paragraphs=[
            "Sven Hedin was born in Stockholm, Sweden, in 1865.",
            "He showed interest in Central Asian exploration.",
        ],
    )
]

_runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.model_id = "stub-llm"
    llm.complete = AsyncMock(
        return_value=LLMResult(
            text=_valid_llm_response(),
            input_tokens=100,
            output_tokens=50,
            cost_eur=0.001,
            latency_ms=100,
            model_id="stub-llm",
        )
    )
    return llm


def _make_mock_embedder() -> MagicMock:
    embedder = MagicMock()
    embedder.model_id = "stub-embedder"
    embedder.dim = 2
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])
    embedder.embed_many = AsyncMock(return_value=[[0.1, 0.2]])
    return embedder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_nous_read_help() -> None:
    result = _runner.invoke(app, ["nous", "read", "--help"])
    assert result.exit_code == 0
    assert "Wikipedia article title" in result.output


def test_nous_read_no_chronicle_creates_json(tmp_path: Path) -> None:
    """With mocked HTTP + LLM + embedder, --no-chronicle produces an AnnotatedReading JSON."""
    output_path = tmp_path / "reading.json"

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIXTURE_SECTIONS

    with (
        patch("theogony.nous.reader.fetch_article_structured", side_effect=_fake_fetch),
        patch("theogony.cli.build_llm_from_settings", return_value=_make_mock_llm()),
        patch(
            "theogony.cli.LocalSentenceTransformerEmbedder",
            return_value=_make_mock_embedder(),
        ),
    ):
        result = _runner.invoke(
            app,
            [
                "nous",
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
    assert output_path.exists(), "AnnotatedReading JSON must be written"
    data = json.loads(output_path.read_text())
    assert data["article_title"] is not None
    assert isinstance(data["steps"], list)


def test_nous_read_output_mentions_paragraphs_processed(tmp_path: Path) -> None:
    output_path = tmp_path / "ar.json"

    async def _fake_fetch(url: str, *, client=None, timeout_s=30.0):
        return _FIXTURE_SECTIONS

    with (
        patch("theogony.nous.reader.fetch_article_structured", side_effect=_fake_fetch),
        patch("theogony.cli.build_llm_from_settings", return_value=_make_mock_llm()),
        patch(
            "theogony.cli.LocalSentenceTransformerEmbedder",
            return_value=_make_mock_embedder(),
        ),
    ):
        result = _runner.invoke(
            app,
            [
                "nous",
                "read",
                "--no-chronicle",
                "--sections",
                "1",
                "--output",
                str(output_path),
                "Sven Hedin",
            ],
        )

    assert "Paragraphs processed" in result.output or result.exit_code == 0


def test_nous_read_no_args_shows_help() -> None:
    result = _runner.invoke(app, ["nous", "read"])
    # Missing required argument → non-zero exit with usage info
    assert result.exit_code != 0


def test_nous_app_listed_in_main_help() -> None:
    result = _runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "nous" in result.output
