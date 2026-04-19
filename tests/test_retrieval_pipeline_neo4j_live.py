"""
QueryPipeline live test against Neo4j (Plan §3.8 layer 5 + 6).

Mirrors the InMemory integration test
(``test_retrieval_pipeline.py``) against ``Neo4jKnowledgeStore`` via
testcontainers. Asserts the same end-to-end contract — answer text,
cited node ids, report status / verdict / counts — holds against the
production backend.

Gated on ``THEOGONY_TEST_NEO4J=1``. Joins the dedicated ``neo4j``
job in ``.github/workflows/ci.yml`` (no new job).
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from pydantic import SecretStr

from theogony.agents.llm import StubLLMProvider
from theogony.config.settings import Neo4jSettings, Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.memory.relevance import RelevanceTracker
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores import InMemoryKnowledgeStore, Neo4jKnowledgeStore

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_TEST_NEO4J") != "1",
    reason="Set THEOGONY_TEST_NEO4J=1 to run Neo4j retrieval live tests.",
)

_EMBEDDING_DIM = 384


class _ConstantEmbedder:
    """Production-shape embedder (384 dim) returning a fixed vector."""

    @property
    def model_id(self) -> str:
        return "constant-embedder@v1"

    @property
    def dim(self) -> int:
        return _EMBEDDING_DIM

    async def embed(self, text: str) -> list[float]:
        # Direction along axis 0; magnitude does not matter for cosine
        # ranking against the fixture nodes that share the same axis.
        return [1.0] + [0.0] * (_EMBEDDING_DIM - 1)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


@pytest.fixture(scope="session")
def neo4j_container() -> Any:
    try:
        from testcontainers.neo4j import Neo4jContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[neo4j] not installed: {exc}")
    container = Neo4jContainer("neo4j:5.18-community")
    container.start()
    yield container
    container.stop()


def _settings_from(container: Any) -> Neo4jSettings:
    return Neo4jSettings(
        uri=container.get_connection_url(),
        user=container.username,
        password=SecretStr(container.password),
        database="neo4j",
    )


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", location=loc, language="en")


def _hedin_tibet_fixture() -> tuple[KnowledgeNode, KnowledgeNode, KnowledgeEdge]:
    hedin = KnowledgeNode(
        label="Sven Hedin",
        node_type=NodeType.PERSON,
        source_ref=_src("loc:hedin"),
        embedding=[1.0] + [0.0] * (_EMBEDDING_DIM - 1),
        embedding_dim=_EMBEDDING_DIM,
        embedding_model_id="constant-embedder@v1",
        external_ids={"wikidata": "Q154759"},
    )
    hedin.scores.confidence = 0.9
    tibet = KnowledgeNode(
        label="Tibet",
        node_type=NodeType.PLACE,
        source_ref=_src("loc:tibet"),
        embedding=[0.9, 0.1] + [0.0] * (_EMBEDDING_DIM - 2),
        embedding_dim=_EMBEDDING_DIM,
        embedding_model_id="constant-embedder@v1",
        external_ids={"wikidata": "Q17269"},
    )
    tibet.scores.confidence = 0.8
    edge = KnowledgeEdge(
        source_id=hedin.id,
        target_id=tibet.id,
        relation_type="EXPLORED",
        evidence_span="Sven Hedin explored Tibet.",
    )
    return hedin, tibet, edge


@pytest_asyncio.fixture
async def neo4j_store(neo4j_container: Any) -> AsyncIterator[Neo4jKnowledgeStore]:
    settings = _settings_from(neo4j_container)
    async with Neo4jKnowledgeStore(settings, embedding_dim=_EMBEDDING_DIM) as store:
        async with store._session() as session:  # noqa: SLF001
            await session.run("MATCH (n) DETACH DELETE n")
        yield store


def _build_pipeline(store: Any, llm_response: str) -> QueryPipeline:
    return QueryPipeline(
        embedder=_ConstantEmbedder(),
        retriever=MultiHopRetriever(store),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(StubLLMProvider(default=llm_response)),
        relevance=RelevanceTracker(store),
        settings=Settings(),
        report_writer=None,
    )


# ---------------------------------------------------------------- end-to-end


class TestNeo4jPipelineEndToEnd:
    async def test_ask_against_neo4j_returns_cited_answer(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        hedin, tibet, edge = _hedin_tibet_fixture()
        await neo4j_store.upsert_node(hedin)
        await neo4j_store.upsert_node(tibet)
        await neo4j_store.upsert_edge(edge)
        llm_text = (
            f"Sven Hedin was a Swedish explorer [{hedin.id}] who explored Tibet [{tibet.id}]."
        )
        pipeline = _build_pipeline(neo4j_store, llm_text)
        result = await pipeline.ask("Wer war Sven Hedin?")
        assert "Sven Hedin" in result.answer.text
        assert hedin.id in result.answer.cited_node_ids
        assert tibet.id in result.answer.cited_node_ids
        assert result.report.status == "completed"
        assert result.report.verdict == "good"
        assert result.report.constellation_node_count >= 2
        assert result.report.constellation_edge_count >= 1
        assert result.report.citation_quality.cited_node_count == 2

    async def test_neo4j_counts_match_in_memory_for_same_fixture(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        # The retrieval contract is backend-agnostic. Same fixture +
        # same StubLLM script must produce the same counts on
        # InMemoryKnowledgeStore and Neo4jKnowledgeStore — that is the
        # E8 brief's "Done when ... same node + edge counts" criterion
        # for the retrieval pipeline.
        hedin, tibet, edge = _hedin_tibet_fixture()

        # InMemory leg
        in_memory = InMemoryKnowledgeStore()
        await in_memory.upsert_node(hedin)
        await in_memory.upsert_node(tibet)
        await in_memory.upsert_edge(edge)
        llm_text = f"Hedin [{hedin.id}] explored Tibet [{tibet.id}]."
        in_memory_pipeline = _build_pipeline(in_memory, llm_text)
        in_memory_result = await in_memory_pipeline.ask("query")

        # Neo4j leg
        await neo4j_store.upsert_node(hedin)
        await neo4j_store.upsert_node(tibet)
        await neo4j_store.upsert_edge(edge)
        neo4j_pipeline = _build_pipeline(neo4j_store, llm_text)
        neo4j_result = await neo4j_pipeline.ask("query")

        assert (
            in_memory_result.report.constellation_node_count
            == neo4j_result.report.constellation_node_count
        )
        assert (
            in_memory_result.report.constellation_edge_count
            == neo4j_result.report.constellation_edge_count
        )
        assert (
            in_memory_result.report.citation_quality.cited_node_count
            == neo4j_result.report.citation_quality.cited_node_count
        )
        assert in_memory_result.report.verdict == neo4j_result.report.verdict
        assert in_memory_result.answer.cited_node_ids == neo4j_result.answer.cited_node_ids


class TestNeo4jPipelineLatency:
    async def test_p95_under_2s_with_stub_llm(self, neo4j_store: Neo4jKnowledgeStore) -> None:
        # Plan §5 E8 success criterion is < 2 s p95 end-to-end. With
        # StubLLM the synthesis tail is ~0 ms, so this is a realistic
        # bound only for the embed + multi_hop + assemble + write-back
        # path. Real-LLM latency is recorded on the report and
        # downgraded by the verdict, not asserted here.
        hedin, tibet, edge = _hedin_tibet_fixture()
        await neo4j_store.upsert_node(hedin)
        await neo4j_store.upsert_node(tibet)
        await neo4j_store.upsert_edge(edge)
        pipeline = _build_pipeline(neo4j_store, f"Hedin [{hedin.id}] explored Tibet [{tibet.id}].")

        # 20 calls is enough for a stable p95 estimate without bloating
        # the suite — at < 2 s each the upper bound is < 40 s, in
        # practice ~5 s on local Docker.
        latencies: list[float] = []
        for _ in range(20):
            started = time.perf_counter()
            await pipeline.ask("query")
            latencies.append(time.perf_counter() - started)

        latencies.sort()
        p95 = latencies[int(0.95 * len(latencies))]
        assert p95 < 2.0, f"p95 latency {p95:.3f}s exceeds 2s budget"
