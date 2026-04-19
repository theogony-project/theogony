"""
AnswerSynthesizer unit tests (Plan §3.8 layer 5).

Asserts the synthesizer:
- builds the user prompt from the slim Constellation (no embeddings);
- calls ``LLMProvider.complete`` exactly once with system + user prompts;
- parses ``[AKA-…]`` citations from the LLM response;
- tolerates ``[**AKA-…**]`` markdown emphasis around ids (Gemini-quirk
  defensive accept);
- drops citations that are not in the supplied Constellation and logs
  a WARNING;
- populates ``Answer.synthesis`` from the LLMResult token / cost /
  latency fields;
- writes one audit-log row per call when ``audit_log`` + ``audit_run_id``
  are provided (matches the BookContextExtractor / RelationExtractor
  pattern Plan §8 / PHX-0038 explicitly tracks).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.core.model import (
    Constellation,
    ConstellationEdge,
    ConstellationNode,
    Layer,
    NodeType,
    SourceRef,
)
from theogony.extraction.audit import ExtractionAuditLog
from theogony.retrieval.synthesize import Answer, AnswerSynthesizer


def _slim_node(node_id: str, label: str) -> ConstellationNode:
    return ConstellationNode(
        id=node_id,
        label=label,
        node_type=NodeType.PERSON,
        layer=Layer.EPHEMERA,
        confidence=0.9,
        source_ref=SourceRef(source_type="gutenberg", identifier="43497", location=f"loc:{label}"),
    )


def _two_node_constellation(query: str = "Wer war Sven Hedin?") -> Constellation:
    a = _slim_node("AKA-1c73fabddadd", "Hedin")
    b = _slim_node("AKA-70ab05c124ee", "Tibet")
    edge = ConstellationEdge(
        source_id=a.id, target_id=b.id, relation_type="REACHED", weight=0.8, confidence=0.9
    )
    return Constellation(
        query=query,
        nodes=[a, b],
        edges=[edge],
        suggested_sources=[a.source_ref],
        path="fast",
    )


# ---------------------------------------------------------------- citations


class TestCitationParser:
    def test_extracts_simple_aka_ids(self) -> None:
        text = "Hedin reached Lhasa [AKA-1c73fabddadd] in 1907 [AKA-70ab05c124ee]."
        result = AnswerSynthesizer._extract_citations(text)
        assert result == ["AKA-1c73fabddadd", "AKA-70ab05c124ee"]

    def test_dedupes_repeated_ids_preserving_first_occurrence_order(self) -> None:
        text = "X [AKA-aaa111aaa111]. Y [AKA-bbb222bbb222]. Z [AKA-aaa111aaa111]."
        assert AnswerSynthesizer._extract_citations(text) == [
            "AKA-aaa111aaa111",
            "AKA-bbb222bbb222",
        ]

    def test_tolerates_markdown_emphasis_around_id(self) -> None:
        # Gemini occasionally renders [AKA-…] as [**AKA-…**]. Both must parse.
        text = "Hedin [**AKA-1c73fabddadd**] explored [*AKA-70ab05c124ee*]."
        result = AnswerSynthesizer._extract_citations(text)
        assert "AKA-1c73fabddadd" in result
        assert "AKA-70ab05c124ee" in result

    def test_ignores_non_aka_brackets(self) -> None:
        text = "Some [bracketed] text and [AKA-1c73fabddadd] real cite."
        assert AnswerSynthesizer._extract_citations(text) == ["AKA-1c73fabddadd"]


# ---------------------------------------------------------------- synthesize


class TestSynthesizeBasics:
    @pytest.fixture
    def synthesizer(self) -> AnswerSynthesizer:
        # The default prompt path resolves to the repo's prompts/ dir.
        # Exists because we ship it in the same PR.
        return AnswerSynthesizer(StubLLMProvider(default="placeholder"))

    async def test_returns_answer_with_text_and_citations(self) -> None:
        constellation = _two_node_constellation()
        llm = StubLLMProvider(
            default=("Sven Hedin reached Tibet in disguise [AKA-1c73fabddadd] [AKA-70ab05c124ee].")
        )
        synth = AnswerSynthesizer(llm)
        answer = await synth.synthesize(constellation)
        assert isinstance(answer, Answer)
        assert "Hedin" in answer.text
        assert answer.cited_node_ids == ["AKA-1c73fabddadd", "AKA-70ab05c124ee"]

    async def test_passes_system_prompt_and_constellation_to_llm(self) -> None:
        constellation = _two_node_constellation()
        llm = StubLLMProvider(default="…")
        synth = AnswerSynthesizer(llm)
        await synth.synthesize(constellation)
        assert len(llm.calls) == 1
        call = llm.calls[0]
        # System prompt: loaded from prompts/answer_synthesizer.md.
        assert call["system"] is not None
        assert "AnswerSynthesizer" in call["system"]
        assert "AKA-" in call["system"]
        # User prompt: the slim Constellation rendered as JSON, plus the query.
        assert "Wer war Sven Hedin?" in call["prompt"]
        assert "AKA-1c73fabddadd" in call["prompt"]  # id appears so LLM can cite it
        # No json_schema constraint (E8 brief: plain-text completion).
        assert call["json_schema"] is None

    async def test_synthesis_breakdown_carries_token_costs(self) -> None:
        constellation = _two_node_constellation()
        llm = StubLLMProvider(default="Answer with [AKA-1c73fabddadd] cite.")
        synth = AnswerSynthesizer(llm)
        answer = await synth.synthesize(constellation)
        # StubLLMProvider counts words for input/output_tokens.
        assert answer.synthesis.input_tokens > 0
        assert answer.synthesis.output_tokens > 0
        assert answer.synthesis.cost_eur == 0.0


# ---------------------------------------------------------------- hallucination


class TestHallucinatedCitationsDropped:
    async def test_drops_hallucinated_id_and_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        constellation = _two_node_constellation()
        # The LLM cites a real id and a fabricated one.
        llm = StubLLMProvider(default=("Hedin [AKA-1c73fabddadd] climbed K2 [AKA-deadbeefdead]."))
        synth = AnswerSynthesizer(llm)
        with caplog.at_level(logging.WARNING, logger="theogony.retrieval.synthesize"):
            answer = await synth.synthesize(constellation)
        assert answer.cited_node_ids == ["AKA-1c73fabddadd"]
        assert any("AKA-deadbeefdead" in rec.message for rec in caplog.records)

    async def test_only_hallucination_yields_empty_cited_list(self) -> None:
        constellation = _two_node_constellation()
        llm = StubLLMProvider(default="All wrong [AKA-deadbeefdead] [AKA-cafebabecafe].")
        synth = AnswerSynthesizer(llm)
        answer = await synth.synthesize(constellation)
        assert answer.cited_node_ids == []
        # Text is preserved — the prose may still be useful even with bad cites;
        # the report's CitationQuality will record cited_node_count=0 and the
        # query verdict will downgrade accordingly.
        assert "All wrong" in answer.text


# ---------------------------------------------------------------- audit log


class TestAuditLogWiring:
    async def test_records_one_row_per_call_when_audit_configured(self) -> None:
        constellation = _two_node_constellation()
        llm = StubLLMProvider(default="Answer [AKA-1c73fabddadd].")
        with ExtractionAuditLog() as audit:
            synth = AnswerSynthesizer(llm, audit_log=audit, audit_run_id="run-1")
            await synth.synthesize(constellation)
            await synth.synthesize(constellation, run_id="run-2")
            rows = audit.query_all()
        assert [r.run_id for r in rows] == ["run-1", "run-2"]
        # Every row tagged with the synthesis stage so the Reviewer agent
        # can grep the audit DB by stage.
        assert all(r.stage == "answer_synthesis" for r in rows)

    async def test_no_audit_when_audit_log_absent(self) -> None:
        constellation = _two_node_constellation()
        llm = StubLLMProvider(default="Answer [AKA-1c73fabddadd].")
        synth = AnswerSynthesizer(llm, audit_log=None, audit_run_id="ignored")
        # Should not raise — audit_log absence silences the recording.
        await synth.synthesize(constellation)

    async def test_hallucinated_citation_marks_row_with_parse_error(self) -> None:
        constellation = _two_node_constellation()
        llm = StubLLMProvider(default="Bad cite [AKA-deadbeefdead].")
        with ExtractionAuditLog() as audit:
            synth = AnswerSynthesizer(llm, audit_log=audit, audit_run_id="run-h")
            await synth.synthesize(constellation)
            rows = audit.query_for_run("run-h")
        assert len(rows) == 1
        assert rows[0].parse_error == "hallucinated_citations"


# ---------------------------------------------------------------- prompt loading


class TestPromptLoading:
    def test_missing_prompt_raises_file_not_found(self, tmp_path: pytest.TempPathFactory) -> None:
        bogus = tmp_path / "nope.md"  # type: ignore[attr-defined]
        with pytest.raises(FileNotFoundError, match="answer_synthesizer"):
            AnswerSynthesizer(StubLLMProvider(), prompt_path=bogus)

    def test_default_prompt_path_resolves_to_repo_prompts_dir(self) -> None:
        synth = AnswerSynthesizer(StubLLMProvider())
        assert synth._prompt_path.name == "answer_synthesizer.md"
        assert synth._prompt_path.exists()


# ---------------------------------------------------------------- transport error


class TestTransportError:
    async def test_transport_failure_returns_empty_answer_and_audits(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class _BoomLLM:
            model_id = "boom-llm"

            async def complete(
                self, prompt: str, **kwargs: object
            ) -> object:  # pragma: no cover - exercised via raise
                raise RuntimeError("transport down")

        constellation = _two_node_constellation()
        with ExtractionAuditLog() as audit:
            synth = AnswerSynthesizer(
                _BoomLLM(),  # type: ignore[arg-type]
                audit_log=audit,
                audit_run_id="run-boom",
            )
            with caplog.at_level(logging.WARNING, logger="theogony.retrieval.synthesize"):
                answer = await synth.synthesize(constellation)
            rows = audit.query_for_run("run-boom")
        # Honest failure: empty answer, no fabricated citations, and the
        # audit row tagged with a transport_error parse_error.
        assert answer.text == ""
        assert answer.cited_node_ids == []
        assert len(rows) == 1
        assert rows[0].parse_error is not None
        assert rows[0].parse_error.startswith("transport_error")
        # And we logged the failure for human eyes.
        assert any("synthesis LLM call failed" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------- insufficiency


class TestInsufficientConstellation:
    async def test_includes_sufficiency_note_in_user_prompt(self) -> None:
        # 1 node + 0 edges → not sufficient (Constellation.is_sufficient).
        sole = _slim_node("AKA-1c73fabddadd", "Hedin")
        constellation = Constellation(
            query="What did Hedin discover in Mars?",
            nodes=[sole],
            edges=[],
            suggested_sources=[sole.source_ref],
            retrieved_at=datetime.now(UTC),
            path="fast",
        )
        llm = StubLLMProvider(default="(LLM honest insufficiency response)")
        synth = AnswerSynthesizer(llm)
        await synth.synthesize(constellation)
        user_prompt = llm.calls[0]["prompt"]
        assert "below the sufficiency threshold" in user_prompt
