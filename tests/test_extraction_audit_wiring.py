"""Audit-log wiring tests for the three LLM-using extractors.

These verify that BookContextExtractor, EntityResolver Stage 4, and
RelationExtractor each write one ExtractionAuditLog row per LLM call
when configured with both ``audit_log`` and ``audit_run_id`` (or a
per-call ``run_id`` kwarg).

Backward-compat is verified by the existing extractor tests — those
do not pass an audit_log and still pass.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from theogony.acquisition.base import RawContent
from theogony.agents.llm import StubLLMProvider
from theogony.core.model import SourceRef
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.ner import Mention
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.sentence import Sentence
from theogony.extraction.wikidata_client import BioFacts, WikidataCandidate

# ---------------------------------------------------------------- shared


def _book_source_ref() -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="944", language="en")


def _hedin_raw() -> RawContent:
    return RawContent(
        source_type="gutenberg",
        identifier="944",
        title="Seven Years in Tibet",
        authors=["Harrer, Heinrich"],
        language="en",
        content="...",
        content_format="text/plain; charset=utf-8",
        bytes_acquired=10,
    )


def _mention(text: str, label: str, *, sentence_index: int = 0, offset: int = 0) -> Mention:
    return Mention(
        text=text,
        label=label,
        sentence_index=sentence_index,
        start_char_in_sentence=offset,
        end_char_in_sentence=offset + len(text),
        start_char_in_source=offset,
        end_char_in_source=offset + len(text),
    )


def _sentence(idx: int, text: str) -> Sentence:
    return Sentence(index=idx, text=text, start_char=0, end_char=len(text))


# ---------------------------------------------------------------- BookContext


class TestBookContextAudit:
    async def test_records_one_row_per_extract_call(self) -> None:
        scripted = json.dumps(
            {
                "time_period": "1939-1951",
                "places": ["Tibet"],
                "people_descriptors": ["Austrian mountaineer"],
                "summary": "...",
            }
        )
        llm = StubLLMProvider(default=scripted, model_id="stub-llm")
        with ExtractionAuditLog() as audit:
            extractor = BookContextExtractor(
                llm=llm,
                audit_log=audit,
                audit_run_id="run-X",
            )
            await extractor.extract(
                raw_content=_hedin_raw(),
                opening_sentences=[_sentence(0, "Some text.")],
            )

            rows = audit.query_for_run("run-X")
        assert len(rows) == 1
        row = rows[0]
        assert row.stage == "book_context"
        assert row.sentence_index is None
        assert row.model_id == "stub-llm"
        assert row.parse_error is None
        assert "Some text." in row.prompt or "Tibet" in row.response

    async def test_records_json_decode_parse_error_on_bad_response(self) -> None:
        llm = StubLLMProvider(default="not JSON at all", model_id="stub-llm")
        with ExtractionAuditLog() as audit:
            extractor = BookContextExtractor(
                llm=llm,
                audit_log=audit,
                audit_run_id="run-X",
            )
            ctx = await extractor.extract(
                raw_content=_hedin_raw(),
                opening_sentences=[_sentence(0, "x")],
            )
            rows = audit.query_for_run("run-X")
        assert len(rows) == 1
        # Honest-failure stayed honest: empty BookContext returned.
        assert ctx.time_period is None
        # Audit row tagged with the right parse_error bucket.
        assert rows[0].parse_error == "json_decode"

    async def test_per_call_run_id_overrides_constructor(self) -> None:
        llm = StubLLMProvider(default=json.dumps({"summary": ""}), model_id="stub-llm")
        with ExtractionAuditLog() as audit:
            extractor = BookContextExtractor(
                llm=llm,
                audit_log=audit,
                audit_run_id="constructor-default",
            )
            await extractor.extract(
                raw_content=_hedin_raw(),
                opening_sentences=[_sentence(0, "x")],
                run_id="explicit-call",
            )
            rows = audit.query_for_run("explicit-call")
            other = audit.query_for_run("constructor-default")
        assert len(rows) == 1
        assert other == []

    async def test_no_audit_when_log_absent(self) -> None:
        llm = StubLLMProvider(default=json.dumps({"summary": ""}))
        # No audit_log passed — extractor must not crash and must not
        # produce any side effect.
        extractor = BookContextExtractor(llm=llm, audit_run_id="ignored")
        ctx = await extractor.extract(
            raw_content=_hedin_raw(),
            opening_sentences=[_sentence(0, "x")],
        )
        assert ctx.derived_from_book == "gutenberg:944"


# ---------------------------------------------------------------- RelationExtractor


class TestRelationExtractorAudit:
    async def test_records_one_row_per_sentence_call(self) -> None:
        scripted = json.dumps(
            {
                "relations": [
                    {
                        "subject": "Harrer",
                        "object": "Lhasa",
                        "relation_type": "REACHED",
                        "evidence_span": "Harrer reached Lhasa",
                        "confidence": 0.9,
                    }
                ]
            }
        )
        llm = StubLLMProvider(default=scripted, model_id="stub-llm")
        with ExtractionAuditLog() as audit:
            extractor = RelationExtractor(
                llm=llm,
                audit_log=audit,
                audit_run_id="run-Y",
            )
            sent = _sentence(7, "Harrer reached Lhasa.")
            await extractor.extract(
                central_sentence=sent,
                mentions=[_mention("Harrer", "PERSON"), _mention("Lhasa", "GPE")],
            )

            rows = audit.query_for_run("run-Y")
        assert len(rows) == 1
        assert rows[0].stage == "relation_extraction"
        assert rows[0].sentence_index == 7
        assert rows[0].parse_error is None

    async def test_no_audit_row_when_short_circuit(self) -> None:
        # Fewer than 2 mentions → no LLM call → no audit row.
        llm = StubLLMProvider(default="{}", model_id="stub-llm")
        with ExtractionAuditLog() as audit:
            extractor = RelationExtractor(
                llm=llm,
                audit_log=audit,
                audit_run_id="run-Z",
            )
            await extractor.extract(
                central_sentence=_sentence(0, "Just one entity here: Tibet."),
                mentions=[_mention("Tibet", "GPE")],
            )
            assert audit.count_for_run("run-Z") == 0

    async def test_records_relations_not_list_parse_error(self) -> None:
        llm = StubLLMProvider(
            default=json.dumps({"relations": "not-a-list"}),
            model_id="stub-llm",
        )
        with ExtractionAuditLog() as audit:
            extractor = RelationExtractor(
                llm=llm,
                audit_log=audit,
                audit_run_id="run-Y",
            )
            await extractor.extract(
                central_sentence=_sentence(0, "Harrer met Aufschnaiter."),
                mentions=[
                    _mention("Harrer", "PERSON"),
                    _mention("Aufschnaiter", "PERSON"),
                ],
            )
            rows = audit.query_for_run("run-Y")
        assert len(rows) == 1
        assert rows[0].parse_error == "relations_not_list"


# ---------------------------------------------------------------- EntityResolver Stage 4


class FakeWikidataResponses(BaseModel):
    search: dict[tuple[str, str], list[WikidataCandidate]] = {}
    aliases: dict[str, dict[str, list[str]]] = {}
    types: dict[str, set[str]] = {}
    bio_facts: dict[str, BioFacts] = {}


class FakeWikidataClient:
    def __init__(self, responses: FakeWikidataResponses) -> None:
        self.responses = responses

    async def search_multi_language(self, mention, *, languages, limit=10):  # type: ignore[no-untyped-def]
        return {lang: list(self.responses.search.get((mention, lang), [])) for lang in languages}

    async def fetch_labels_aliases(self, qids, *, languages):  # type: ignore[no-untyped-def]
        out: dict[str, dict[str, list[str]]] = {}
        for qid in qids:
            qid_aliases = self.responses.aliases.get(qid, {})
            out[qid] = {lang: list(qid_aliases.get(lang, [])) for lang in languages}
        return out

    async def fetch_types(self, qids):  # type: ignore[no-untyped-def]
        return {qid: set(self.responses.types.get(qid, set())) for qid in qids}

    async def fetch_bio_facts(self, qids, *, language="en"):  # type: ignore[no-untyped-def]
        return {qid: self.responses.bio_facts.get(qid, BioFacts(qid=qid)) for qid in qids}


class TestStage4Audit:
    async def test_records_one_row_per_stage4_call(self) -> None:
        # Two ambiguous survivors → triggers Stage 4 → LLM call.
        responses = FakeWikidataResponses(
            search={
                ("Aufschnaiter", "en"): [WikidataCandidate(qid="Q123", label="A", language="en")],
                ("Aufschnaiter", "de"): [WikidataCandidate(qid="Q789", label="B", language="de")],
                ("Aufschnaiter", "fr"): [],
                ("Aufschnaiter", "it"): [],
            },
            aliases={
                "Q123": {"en": ["Aufschnaiter"]},
                "Q789": {"de": ["Aufschnaiter"]},
            },
            types={"Q123": {"Q5"}, "Q789": {"Q5"}},
            bio_facts={
                "Q123": BioFacts(qid="Q123", birth_date="1899", occupations=["mountaineer"]),
                "Q789": BioFacts(qid="Q789", birth_date="1950", occupations=["footballer"]),
            },
        )
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(
            default=json.dumps({"chosen": "Q123", "confidence": 0.9, "reasoning": "..."}),
            model_id="stub-llm",
        )
        with ExtractionAuditLog() as audit:
            resolver = EntityResolver(
                client=client,  # type: ignore[arg-type]
                llm=llm,
                audit_log=audit,
                audit_run_id="run-S4",
            )
            m = _mention("Aufschnaiter", "PERSON", sentence_index=12)
            await resolver.resolve(m, source_ref=_book_source_ref())
            rows = audit.query_for_run("run-S4")
        assert len(rows) == 1
        assert rows[0].stage == "stage4_disambiguation"
        # sentence_index threaded through from the mention.
        assert rows[0].sentence_index == 12
        assert rows[0].parse_error is None

    async def test_no_audit_row_when_tier_4_short_circuits_stage4(self) -> None:
        # Unique survivor with EXACT in 2 langs → Tier 4, no Stage 4
        # call → no audit row.
        cand_en = WikidataCandidate(qid="Q1", label="Sven Hedin", language="en")
        cand_de = WikidataCandidate(qid="Q1", label="Sven Hedin", language="de")
        responses = FakeWikidataResponses(
            search={
                ("Sven Hedin", "en"): [cand_en],
                ("Sven Hedin", "de"): [cand_de],
                ("Sven Hedin", "fr"): [],
                ("Sven Hedin", "it"): [],
            },
            aliases={
                "Q1": {
                    "en": ["Sven Hedin"],
                    "de": ["Sven Hedin"],
                    "fr": [],
                    "it": [],
                }
            },
            types={"Q1": {"Q5"}},
        )
        client = FakeWikidataClient(responses)
        llm = StubLLMProvider(default=json.dumps({"chosen": "X", "confidence": 1, "reasoning": ""}))
        with ExtractionAuditLog() as audit:
            resolver = EntityResolver(
                client=client,  # type: ignore[arg-type]
                llm=llm,
                audit_log=audit,
                audit_run_id="run-T4",
            )
            await resolver.resolve(
                _mention("Sven Hedin", "PERSON"),
                source_ref=_book_source_ref(),
            )
            assert audit.count_for_run("run-T4") == 0


# ---------------------------------------------------------------- E2E one-extractor smoke


class TestEndToEndOneExtractor:
    """Sanity: with all three audit-wired extractors using the same
    audit_log + run_id, every LLM call writes exactly one row and the
    rows can be filtered by stage."""

    async def test_query_by_stage_separates_extractor_origins(self) -> None:
        llm_book = StubLLMProvider(default=json.dumps({"summary": "x"}), model_id="stub-llm")
        llm_rel = StubLLMProvider(default=json.dumps({"relations": []}), model_id="stub-llm")

        with ExtractionAuditLog() as audit:
            book_extractor = BookContextExtractor(
                llm=llm_book, audit_log=audit, audit_run_id="run-E2E"
            )
            rel_extractor = RelationExtractor(llm=llm_rel, audit_log=audit, audit_run_id="run-E2E")

            await book_extractor.extract(
                raw_content=_hedin_raw(),
                opening_sentences=[_sentence(0, "x")],
            )
            await rel_extractor.extract(
                central_sentence=_sentence(0, "Harrer met Aufschnaiter."),
                mentions=[
                    _mention("Harrer", "PERSON"),
                    _mention("Aufschnaiter", "PERSON"),
                ],
            )

            rows = audit.query_for_run("run-E2E")
        stages = [r.stage for r in rows]
        assert sorted(stages) == ["book_context", "relation_extraction"]
