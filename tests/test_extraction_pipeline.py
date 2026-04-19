"""Unit tests for :class:`IngestionPipeline` (Plan §2.5)."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from theogony.acquisition.base import RawContent
from theogony.agents.llm import StubLLMProvider
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.pipeline import IngestionPipeline, IngestionResult
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_client import BioFacts, WikidataCandidate

# ---------------------------------------------------------------- fakes


class FakeWikidataResponses(BaseModel):
    search: dict[tuple[str, str], list[WikidataCandidate]] = {}
    aliases: dict[str, dict[str, list[str]]] = {}
    types: dict[str, set[str]] = {}
    bio_facts: dict[str, BioFacts] = {}


class FakeWikidataClient:
    """In-memory stub for the resolver — same shape as test_extraction_resolve_stage4."""

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


class InMemoryStore:
    """Tiny KnowledgeStore stub: collects upserts into lists for assertions."""

    def __init__(self) -> None:
        self.nodes: list[KnowledgeNode] = []
        self.edges: list[KnowledgeEdge] = []

    async def upsert_node(self, node: KnowledgeNode) -> str:
        self.nodes.append(node)
        return node.id

    async def upsert_edge(self, edge: KnowledgeEdge) -> None:
        self.edges.append(edge)


# ---------------------------------------------------------------- raw content fixture


_HEDIN_TEXT = (
    "*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n"
    "Sven Hedin reached Lhasa in 1907.\n"
    "Sven Hedin met the Dalai Lama there.\n"
    "Aufschnaiter was nowhere nearby.\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\n"
)


def _hedin_raw() -> RawContent:
    return RawContent(
        source_type="gutenberg",
        identifier="944",
        title="Test Book",
        authors=["Hedin, Sven"],
        language="en",
        content=_HEDIN_TEXT,
        content_format="text/plain; charset=utf-8",
        bytes_acquired=len(_HEDIN_TEXT.encode("utf-8")),
    )


# ---------------------------------------------------------------- responses


def _hedin_responses() -> FakeWikidataResponses:
    """Fake Wikidata responses for "Sven Hedin", "Lhasa", "Aufschnaiter".

    Sven Hedin → Tier 4 (EXACT in en+de).
    Lhasa     → Tier 3 (CASE+ in en+de).
    Aufschnaiter → Tier 0 (no candidates from search).
    """
    cand = WikidataCandidate
    return FakeWikidataResponses(
        search={
            ("Sven Hedin", "en"): [cand(qid="Q154759", label="Sven Hedin", language="en")],
            ("Sven Hedin", "de"): [cand(qid="Q154759", label="Sven Hedin", language="de")],
            ("Sven Hedin", "fr"): [],
            ("Sven Hedin", "it"): [],
            ("Lhasa", "en"): [cand(qid="Q5869", label="Lhasa", language="en")],
            ("Lhasa", "de"): [cand(qid="Q5869", label="Lhasa", language="de")],
            ("Lhasa", "fr"): [],
            ("Lhasa", "it"): [],
            ("Dalai Lama", "en"): [cand(qid="Q4757", label="Dalai Lama", language="en")],
            ("Dalai Lama", "de"): [cand(qid="Q4757", label="Dalai Lama", language="de")],
            ("Dalai Lama", "fr"): [],
            ("Dalai Lama", "it"): [],
        },
        aliases={
            "Q154759": {
                "en": ["Sven Hedin"],
                "de": ["Sven Hedin"],
                "fr": [],
                "it": [],
            },
            "Q5869": {
                "en": ["Lhasa"],
                "de": ["Lhasa"],
                "fr": [],
                "it": [],
            },
            "Q4757": {
                "en": ["Dalai Lama"],
                "de": ["Dalai Lama"],
                "fr": [],
                "it": [],
            },
        },
        types={
            "Q154759": {"Q5"},
            "Q5869": {"Q486972"},
            "Q4757": {"Q5"},
        },
    )


def _scripted_relations(rels: list[dict[str, object]]) -> str:
    return json.dumps({"relations": rels})


# ---------------------------------------------------------------- happy path


class TestIngestHappyPath:
    async def test_full_pipeline_produces_nodes_edges_and_report(self) -> None:
        client = FakeWikidataClient(_hedin_responses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        # Two relations expected from sentences 0 and 1; sentence 2
        # has only one entity (Aufschnaiter) so no relation extracted.
        rel_llm = StubLLMProvider(default=_scripted_relations([]))
        # Override per-sentence: sent_idx 0 yields REACHED, sent_idx 1 yields MET.
        rel_llm.add_response(
            'Extract relations from this sentence:\n"Sven Hedin reached Lhasa in 1907."',
            _scripted_relations(
                [
                    {
                        "subject": "Sven Hedin",
                        "object": "Lhasa",
                        "relation_type": "REACHED",
                        "evidence_span": "Sven Hedin reached Lhasa",
                        "confidence": 0.92,
                    }
                ]
            ),
        )
        rel_llm.add_response(
            'Extract relations from this sentence:\n"Sven Hedin met the Dalai Lama there."',
            _scripted_relations(
                [
                    {
                        "subject": "Sven Hedin",
                        "object": "Dalai Lama",
                        "relation_type": "MET",
                        "evidence_span": "Sven Hedin met the Dalai Lama",
                        "confidence": 0.88,
                    }
                ]
            ),
        )
        rel_extractor = RelationExtractor(llm=rel_llm)

        pipeline = IngestionPipeline(
            entity_resolver=resolver,
            relation_extractor=rel_extractor,
        )
        result = await pipeline.ingest(_hedin_raw())

        # ---- shape ----
        assert isinstance(result, IngestionResult)
        assert result.run_id
        assert result.report.run_id == result.run_id
        assert result.report.report_type == "ingest"
        assert result.report.status == "completed"
        assert result.report.source_type == "gutenberg"
        assert result.report.source_identifier == "944"

        # ---- nodes ----
        # spaCy en_core_web_sm reliably extracts "Sven Hedin", "Lhasa",
        # "Aufschnaiter", and "1907"; "Dalai Lama" is sometimes split
        # (we don't pin the test on its presence to keep it stable
        # across spaCy releases).
        labels = {rm.node.label for rm in result.resolved_mentions}
        assert "Sven Hedin" in labels
        assert "Lhasa" in labels
        # Aufschnaiter goes through Tier 0 honest-failure path
        # (no candidates from the fake Wikidata client).
        assert "Aufschnaiter" in labels
        aufs = next(rm for rm in result.resolved_mentions if rm.node.label == "Aufschnaiter")
        assert aufs.tier == 0
        assert aufs.node.manual_resolution_needed is True

        # ---- edges ----
        # At minimum the REACHED edge from sentence 0 (Sven Hedin →
        # Lhasa) must be present. "Sven Hedin met Dalai Lama" depends
        # on NER picking up Dalai Lama, which we do not pin.
        assert len(result.edges) >= 1
        edge_types = {e.relation_type for e in result.edges}
        assert "REACHED" in edge_types
        # Each edge carries the central-sentence SourceRef.
        for edge in result.edges:
            assert edge.source_ref is not None
            assert edge.source_ref.location is not None
            assert edge.source_ref.location.startswith("sentence:")
            assert edge.source_ref.identifier == "944"

        # ---- report stages ----
        stage_names = [s.name for s in result.report.stages]
        # Plan §2.11.1 stage sequence — every stage present.
        for required in (
            "acquired",
            "cleaned",
            "sentencized",
            "mentions_extracted",
            "mentions_resolved",
            "relations_extracted",
            "embedded",  # placeholder, status="skipped" in E5
            "stored",  # status="ok" with empty store summary when no store
        ):
            assert required in stage_names, f"stage {required} missing from report"
        # Embedded stage runs unconditionally now (E6) — without an
        # embedder configured it completes ok with nodes_embedded=0.
        embed_stage = next(s for s in result.report.stages if s.name == "embedded")
        assert embed_stage.status == "ok"
        assert result.report.embedding.nodes_embedded == 0
        assert result.report.embedding.embedding_model_id == "(not configured)"

        # ---- summaries ----
        assert result.report.ner.total_mentions >= 4  # Hedin × 2 + Lhasa + Dalai + Aufs
        assert result.report.ner.by_type.get("PERSON", 0) >= 1
        # Tier counts include 4 (Hedin), 3 (Lhasa, Dalai), 0 (Aufs).
        tier_counts = result.report.resolution.tier_counts
        assert tier_counts.get(0, 0) >= 1  # Aufschnaiter
        assert sum(tier_counts.values()) == len(result.resolved_mentions)
        # Manual-resolution-needed count tracks Tier 0 nodes.
        assert result.report.resolution.manual_resolution_needed >= 1

        # ---- relation summary ----
        assert result.report.relations.attempted >= 1
        assert result.report.relations.parsed_ok >= 1

        # ---- verdict ----
        # No stage failed → status="completed" → not "failed" verdict.
        # The fake Wikidata coverage is thin (most NER mentions land
        # at Tier 0), so the verdict heuristic legitimately says
        # "poor" or "partial" on this fixture. Real-data ingest with
        # full Wikidata reaches "good" — see the live smoke test.
        assert result.report.verdict in ("good", "partial", "poor")
        assert result.report.verdict != "failed"


# ---------------------------------------------------------------- store wiring


class TestStoreWiring:
    async def test_with_store_upserts_every_node_and_edge(self) -> None:
        client = FakeWikidataClient(_hedin_responses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        rel_llm = StubLLMProvider(default=_scripted_relations([]))
        rel_llm.add_response(
            'Extract relations from this sentence:\n"Sven Hedin reached Lhasa in 1907."',
            _scripted_relations(
                [
                    {
                        "subject": "Sven Hedin",
                        "object": "Lhasa",
                        "relation_type": "REACHED",
                        "evidence_span": "Sven Hedin reached Lhasa",
                        "confidence": 0.9,
                    }
                ]
            ),
        )
        store = InMemoryStore()
        pipeline = IngestionPipeline(
            entity_resolver=resolver,
            relation_extractor=RelationExtractor(llm=rel_llm),
            store=store,  # type: ignore[arg-type]
        )

        result = await pipeline.ingest(_hedin_raw())

        # Every resolved node + every edge upserted.
        assert len(store.nodes) == len(result.resolved_mentions)
        assert len(store.edges) == len(result.edges)
        # StoreSummary fields populated.
        assert result.report.store.nodes_upserted == len(store.nodes)
        assert result.report.store.edges_upserted == len(store.edges)


# ---------------------------------------------------------------- audit wiring


class TestAuditWiring:
    async def test_audit_log_records_every_llm_call_under_run_id(self) -> None:
        client = FakeWikidataClient(_hedin_responses())
        rel_llm = StubLLMProvider(default=_scripted_relations([]))
        with ExtractionAuditLog() as audit:
            resolver = EntityResolver(client=client, audit_log=audit)  # type: ignore[arg-type]
            rel_extractor = RelationExtractor(llm=rel_llm, audit_log=audit)
            pipeline = IngestionPipeline(
                entity_resolver=resolver,
                relation_extractor=rel_extractor,
                audit_log=audit,
            )
            result = await pipeline.ingest(_hedin_raw())
            rows = audit.query_for_run(result.run_id)

        # All rows belong to the same run_id (the pipeline-generated
        # ULID, not anything passed by the caller).
        assert all(r.run_id == result.run_id for r in rows)
        # Every row carries an extraction-stage tag.
        valid_stages = {"relation_extraction", "stage4_disambiguation", "book_context"}
        assert all(r.stage in valid_stages for r in rows)
        # The report cross-references the audit run id.
        assert result.report.audit_log_run_id == result.run_id


# ---------------------------------------------------------------- book context


class TestBookContext:
    async def test_book_context_extractor_runs_first_and_pushed_into_resolver(self) -> None:
        client = FakeWikidataClient(_hedin_responses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        bc_llm = StubLLMProvider(
            default=json.dumps(
                {
                    "time_period": "1907",
                    "places": ["Tibet"],
                    "people_descriptors": ["Swedish geographer"],
                    "summary": "Trans-Himalaya expedition.",
                }
            )
        )
        bc_extractor = BookContextExtractor(llm=bc_llm)
        pipeline = IngestionPipeline(
            entity_resolver=resolver,
            book_context_extractor=bc_extractor,
        )

        result = await pipeline.ingest(_hedin_raw())

        assert result.book_context is not None
        assert result.book_context.time_period == "1907"
        assert "Tibet" in result.book_context.places
        # Resolver has the context attached for subsequent Stage 4 calls.
        assert resolver.book_context is not None
        assert resolver.book_context.time_period == "1907"


# ---------------------------------------------------------------- failure paths


class TestEmbedder:
    """Embedder stage stamps every minted node with model identity."""

    async def test_embedder_writes_vectors_to_every_node(self) -> None:
        client = FakeWikidataClient(_hedin_responses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        embedder = _FakeEmbedder(dim=4)
        pipeline = IngestionPipeline(
            entity_resolver=resolver,
            embedder=embedder,
        )
        result = await pipeline.ingest(_hedin_raw())

        # Every resolved node carries the embedder's identity + a vector.
        assert len(result.resolved_mentions) >= 1
        for rm in result.resolved_mentions:
            assert rm.node.embedding_model_id == embedder.model_id
            assert rm.node.embedding_dim == 4
            assert len(rm.node.embedding) == 4

        # Report summary populated.
        assert result.report.embedding.nodes_embedded == len(result.resolved_mentions)
        assert result.report.embedding.embedding_model_id == embedder.model_id
        assert result.report.embedding.duration_s >= 0.0

    async def test_embedder_called_once_with_label_batch(self) -> None:
        # Plan §2.3: embed_many is the batched API; pipeline must use
        # it (not N × embed) to keep ingest cheap on large books.
        client = FakeWikidataClient(_hedin_responses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        embedder = _FakeEmbedder(dim=2)
        pipeline = IngestionPipeline(entity_resolver=resolver, embedder=embedder)
        await pipeline.ingest(_hedin_raw())
        assert embedder.embed_many_calls == 1
        assert embedder.embed_calls == 0


class _FakeEmbedder:
    """Trivial embedder that returns deterministic vectors of the given dim."""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim
        self.embed_calls = 0
        self.embed_many_calls = 0

    @property
    def model_id(self) -> str:
        return "fake-embedder@v1"

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, text: str) -> list[float]:
        self.embed_calls += 1
        return [float(i) / max(len(text), 1) for i in range(self._dim)]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.embed_many_calls += 1
        return [[float(i) / max(len(t), 1) for i in range(self._dim)] for t in texts]


class TestRelationExtractorOptional:
    async def test_no_relation_extractor_yields_empty_edges_and_skipped_stage(self) -> None:
        client = FakeWikidataClient(_hedin_responses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        # No relation_extractor passed.
        pipeline = IngestionPipeline(entity_resolver=resolver)
        result = await pipeline.ingest(_hedin_raw())
        assert result.edges == []
        rel_stage = next(s for s in result.report.stages if s.name == "relations_extracted")
        assert rel_stage.status == "skipped"


# ---------------------------------------------------------------- determinism


class TestDeterminism:
    async def test_two_runs_produce_same_node_ids_and_edge_ids(self) -> None:
        # Plan §9.5 / OQ-7: re-running ingest against the same source
        # must mint the same KnowledgeNode + KnowledgeEdge IDs (so
        # KnowledgeStore.upsert_* is a true no-op on retry).
        rel_response = _scripted_relations(
            [
                {
                    "subject": "Sven Hedin",
                    "object": "Lhasa",
                    "relation_type": "REACHED",
                    "evidence_span": "Sven Hedin reached Lhasa",
                    "confidence": 0.9,
                }
            ]
        )

        async def run_once() -> IngestionResult:
            client = FakeWikidataClient(_hedin_responses())
            resolver = EntityResolver(client=client)  # type: ignore[arg-type]
            llm = StubLLMProvider(default=_scripted_relations([]))
            llm.add_response(
                'Extract relations from this sentence:\n"Sven Hedin reached Lhasa in 1907."',
                rel_response,
            )
            rel_extractor = RelationExtractor(llm=llm)
            pipeline = IngestionPipeline(
                entity_resolver=resolver,
                relation_extractor=rel_extractor,
            )
            return await pipeline.ingest(_hedin_raw())

        a = await run_once()
        b = await run_once()

        node_ids_a = sorted(rm.node.id for rm in a.resolved_mentions)
        node_ids_b = sorted(rm.node.id for rm in b.resolved_mentions)
        assert node_ids_a == node_ids_b

        edge_ids_a = sorted(e.id for e in a.edges)
        edge_ids_b = sorted(e.id for e in b.edges)
        assert edge_ids_a == edge_ids_b

        # The run_id (ULID) is fresh per call — that is correct,
        # ULIDs are time-stamped.
        assert a.run_id != b.run_id


# ---------------------------------------------------------------- ner_sentence_limit


class TestSentenceLimit:
    async def test_ner_sentence_limit_clips_processed_sentences(self) -> None:
        client = FakeWikidataClient(_hedin_responses())
        resolver = EntityResolver(client=client)  # type: ignore[arg-type]
        pipeline = IngestionPipeline(
            entity_resolver=resolver,
            ner_sentence_limit=1,  # only the first sentence runs through NER + resolve
        )
        result = await pipeline.ingest(_hedin_raw())
        # Only mentions from sentence 0 (Sven Hedin + Lhasa) reach the
        # resolver. Aufschnaiter (sentence 2) and Dalai Lama (sentence 1)
        # are absent.
        labels = {rm.node.label for rm in result.resolved_mentions}
        assert "Sven Hedin" in labels
        # NER on the slice may pick up "Lhasa" or "1907" (DATE) — the
        # contract is just "limit was respected".
        assert "Aufschnaiter" not in labels
        assert "Dalai Lama" not in labels


# ---------------------------------------------------------------- IngestionResult DTO


class TestIngestionResultDTO:
    def test_extra_fields_forbidden(self) -> None:
        # Construct a minimal valid IngestionResult with a placeholder report.
        from datetime import UTC, datetime

        from theogony.reporting.models import (
            EmbeddingSummary,
            IngestRunReport,
            QualityFlags,
            RelationSummary,
            ResolutionSummary,
            StoreSummary,
            new_run_id,
        )

        rid = new_run_id()
        now = datetime.now(UTC)
        report = IngestRunReport(
            run_id=rid,
            started_at=now,
            finished_at=now,
            duration_s=0.0,
            status="completed",
            verdict="good",
            verdict_reasoning="",
            ingest_run_id=rid,
            source_type="gutenberg",
            source_identifier="x",
            word_count=0,
            sentence_count=0,
            ner=__import__("theogony.reporting.models", fromlist=["NerSummary"]).NerSummary(
                total_mentions=0
            ),
            resolution=ResolutionSummary(),
            relations=RelationSummary(),
            embedding=EmbeddingSummary(nodes_embedded=0, embedding_model_id="x", duration_s=0.0),
            store=StoreSummary(nodes_upserted=0, edges_upserted=0),
            quality_flags=QualityFlags(),
        )
        with pytest.raises(ValueError):
            IngestionResult(  # type: ignore[call-arg]
                run_id=rid,
                report=report,
                bogus="x",
            )
