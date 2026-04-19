# E8 — Retrieval stack (multi_hop → constellation → synthesize → pipeline)

Brief from Hesiod to Talos, 2026-04-19. Companion to Plan §2.6, §4.2, §9.1; Plan §5 v5 splits Week 3 into E7 → E8 → E9.

## What this etappe does

Closes the read half of the Plan §1 demo loop. After E8, a `QueryPipeline.ask("…")` call against a Neo4j store (loaded from one E6/E7 ingest) returns a `Constellation` plus a synthesised, citation-anchored answer. E9 will wrap this in HTTP + CLI; this brief stays inside `retrieval/` and `memory/relevance.py`.

The four retrieval components are tightly coupled by the synthesizer prompt — its expected input shape *is* the `Constellation` slim DTO. They ship as one PR.

## Scope decision: OneirosWorker is OUT of E8

Plan §5 v5 lists `OneirosWorker._finalize_report() populated; one OneirosTickReport per tick. Cap retention at 100 most recent ticks.` under E8 deliverables. Hesiod is deferring the worker (and its report-finalisation hook) to a separate post-E8 etappe. Reasons:

- E8 already carries four production modules + the bridge into Memory (`RelevanceTracker`). Adding a long-running asyncio worker with its own tick-loop, its own test idiom (fast clock, sleep mocking), its own `OneirosTickReport` plumbing, and its own retention-cap policy crosses the etappe-size threshold Daedalus drew at "tight composition".
- The Plan §1 demo loop closes with `QueryPipeline.ask` returning a cited answer. The worker is the write-back side of §4.3 and is *not* on the demo critical path.
- `RelevanceTracker.bump(node_id)` is the only Memory-layer surface the retrieval pipeline needs in E8; it is a small synchronous wrapper around `KnowledgeStore.update_scores` and does not justify pulling the worker forward.

Talos: if you disagree on size grounds (i.e. you've started building and the four modules are noticeably smaller than expected), escalate before opening the PR. Otherwise, treat the worker as a separate brief that lands after E8 merges.

## Files

```
src/theogony/retrieval/__init__.py             EDIT  re-export public API
src/theogony/retrieval/multi_hop.py            NEW   MultiHopRetriever
src/theogony/retrieval/constellation.py        NEW   ConstellationAssembler
src/theogony/retrieval/synthesize.py           NEW   AnswerSynthesizer + Answer DTO
src/theogony/retrieval/pipeline.py             NEW   QueryPipeline + _finalize_report
src/theogony/memory/__init__.py                EDIT  re-export RelevanceTracker
src/theogony/memory/relevance.py               NEW   RelevanceTracker (post-answer bump)
tests/test_retrieval_multi_hop.py              NEW   unit against InMemoryKnowledgeStore
tests/test_retrieval_constellation.py          NEW   unit + syrupy snapshot on structure
tests/test_retrieval_synthesize.py             NEW   StubLLMProvider deterministic citations
tests/test_retrieval_pipeline.py               NEW   end-to-end against InMemory + StubLLM
tests/test_retrieval_pipeline_neo4j_live.py    NEW   testcontainers, gated on THEOGONY_TEST_NEO4J=1
tests/test_relevance_tracker.py                NEW   unit; bump idempotency + score updates
prompts/answer_synthesizer.md                  NEW   verbatim system prompt + citation grammar
```

`core/store.py`, `core/model.py`, `reporting/models.py`, `reporting/writer.py`, `reporting/verdict.py`, `agents/llm.py` are **not edited**. The Protocol surface (`multi_hop_search`, `traverse`, `get_neighborhood`, `update_scores`, `get_node`), the slim DTOs (`ConstellationNode`, `ConstellationEdge`, `Constellation`), and the report scaffolding (`QueryRunReport`, `MultiHopBreakdown`, `SynthesisBreakdown`, `CitationQuality`, `RunReportWriter`, verdict heuristics) all already exist. E8 only fills in the components that consume them.

## Classes & APIs

### `MultiHopRetriever` — `retrieval/multi_hop.py`

Thin orchestration layer over `KnowledgeStore.multi_hop_search`. The store does the work; the retriever owns the parameter discipline (k, hops, min_weight, layer) and the dedup/re-rank policy, and emits the `MultiHopBreakdown` observation the pipeline writes onto the report.

```python
class MultiHopRetriever:
    def __init__(self, store: KnowledgeStore) -> None: ...

    async def retrieve(
        self,
        query_embedding: list[float],
        *,
        k: int = 10,
        hops: int = 2,
        min_weight: float = 0.3,
        layer: Layer | None = None,
    ) -> MultiHopResult:
        """Returns scored nodes plus per-hop instrumentation."""
```

`MultiHopResult` is a small Pydantic dataclass (`scored_nodes: list[ScoredNode]`, `seed_count: int`, `nodes_per_hop: list[int]`, `duplicates_removed: int`, `duration_ms: int`) that maps cleanly onto `MultiHopBreakdown`. Define it inside `retrieval/multi_hop.py`; do **not** put it in `core/model.py` (it is a pipeline-internal observation, not a domain object).

Defaults match Plan §4.2 (k=10, hops=2). Do not override Plan §2.6's `min_weight=0.3`.

### `ConstellationAssembler` — `retrieval/constellation.py`

Takes the `MultiHopResult` and turns it into a `Constellation`. Responsibilities, in order:

1. Project each `ScoredNode.node` to `ConstellationNode.from_knowledge_node(node)`.
2. Collect edges among the retrieved nodes via `KnowledgeStore.get_neighborhood` for each seed (depth=1 is sufficient — multi_hop already discovered the broader topology). Project to `ConstellationEdge.from_knowledge_edge(edge)`. Dedupe by `(source_id, target_id, relation_type)`.
3. Identify gaps: a node referenced by an edge but not in the retrieved node set is a gap; a query embedding with similarity < 0.3 to the top-1 node is a "no strong match" gap. Two gap kinds for Gen 1 (Plan §9.1 `gaps: list[str]`); document both verbatim in the assembler docstring.
4. Populate `suggested_sources` from each node's `source_ref` (deduped on `(source_type, identifier)`).
5. Set `path="fast"` (Plan §9.1; "slow" is reserved for Gen 2 reasoning loops).

```python
class ConstellationAssembler:
    def __init__(self, store: KnowledgeStore) -> None: ...

    async def assemble(
        self,
        query: str,
        retrieval_result: MultiHopResult,
        query_embedding: list[float] | None = None,  # for the "no strong match" gap
    ) -> Constellation: ...
```

The assembler does not call the LLM and does not embed the query. It is pure store + DTO.

### `AnswerSynthesizer` — `retrieval/synthesize.py`

The single LLM-using component in E8. Takes a `Constellation`, builds a prompt, calls `LLMProvider.complete`, parses the structured response, returns an `Answer`.

```python
class Answer(BaseModel):
    text: str
    cited_node_ids: list[str] = Field(default_factory=list)
    raw_llm_response: str  # for debugging + audit log
    synthesis: SynthesisBreakdown  # ready to drop into QueryRunReport
```

```python
class AnswerSynthesizer:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        audit_log: ExtractionAuditLog | None = None,
        audit_run_id: str | None = None,
    ) -> None: ...

    async def synthesize(
        self,
        constellation: Constellation,
        *,
        max_output_tokens: int | None = 600,
        temperature: float = 0.0,
    ) -> Answer: ...
```

**Audit-log wiring.** Use the same `_maybe_audit(...)` pattern Talos already established in `BookContextExtractor`, `EntityResolver` Stage 4, and `RelationExtractor`. This is the **fourth** call site of the constructor-injection pattern — Plan §8 / PHX-0038 explicitly tracks this; the trigger to refactor into an `AuditingLLMProvider` wrapper is "site seven", so we stay with the explicit pattern.

**Prompt discipline (binding for E8).** Ship the system prompt as a separate file at `prompts/answer_synthesizer.md`. Load it at construction time (one `Path.read_text()` call cached on the instance). The prompt MUST instruct the LLM to:

- Answer using only information present in the supplied constellation.
- Cite every factual claim by appending the node id in square brackets, e.g. `Heinrich Harrer reached Lhasa in January 1946 [AKA-abc123].`
- Use exactly that bracket grammar — `[AKA-…]` — so the citation parser is a single regex (`\[(AKA-[a-f0-9]+)\]`).
- Not invent node ids. Not paraphrase ids.
- If the constellation is insufficient (`Constellation.is_sufficient` returns False), say so explicitly rather than fabricating.

The synthesizer constructs the user-facing prompt by serialising the `Constellation` as JSON (Pydantic's `model_dump_json(indent=2)` is fine — slim DTOs already exclude embeddings). Do **not** include the raw `KnowledgeNode` records in the prompt; that is the entire point of §9.1.

**JSON schema enforcement.** Keep the LLM call simple: plain-text response, no `json_schema=`. The structured output discipline lives in the prompt + the post-parse citation extraction. Justification: every provider (Gemini, OpenAI, Anthropic, Stub) handles plain-text completion; structured citation parsing is a five-line regex that we own. Forcing JSON would cap the answer at JSON-grammar tokens for marginal robustness gain.

**Citation parser.** A single function `_extract_citations(text: str) -> list[str]` that returns the deduplicated, source-order-preserving list of `AKA-…` ids found in the answer. Exposed on the synthesizer for testability.

**`Answer.cited_node_ids` invariant.** Every id returned MUST be present in `constellation.nodes`. If the LLM cites an id that is not in the constellation (hallucination or paraphrase), drop it from `cited_node_ids` and log a WARNING. Document this in the synthesize-method docstring; the test suite asserts it.

### `QueryPipeline` — `retrieval/pipeline.py`

Orchestrates the three components, plus the embedder for the query, plus `RelevanceTracker` for the post-answer write-back. Emits a `QueryRunReport` via `_finalize_report()` at the end of every `ask` call.

```python
class QueryPipeline:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        retriever: MultiHopRetriever,
        assembler: ConstellationAssembler,
        synthesizer: AnswerSynthesizer,
        relevance: RelevanceTracker,
        report_writer: RunReportWriter | None = None,
    ) -> None: ...

    async def ask(
        self,
        query: str,
        *,
        layer: Layer | None = None,
        k: int = 10,
        hops: int = 2,
    ) -> QueryResult:
        """Run the full query loop, write a report, return answer + constellation."""
```

```python
class QueryResult(BaseModel):
    answer: Answer
    constellation: Constellation
    report: QueryRunReport
    report_path: Path | None = None  # set if report_writer was provided
```

**`_finalize_report`.** Composes `QueryRunReport` from observations accumulated during the call:
- header (`run_id` ULID, `started_at`, `duration_s`, `theogony_version`, `git_commit_hash`)
- `query`, `query_length_chars`, `embedding_duration_ms`
- `multi_hop` from the retriever's `MultiHopResult`
- `constellation_node_count`, `constellation_edge_count`, `suggested_source_count`, `gaps_identified` from the assembler's `Constellation`
- `synthesis` from the synthesizer's `Answer.synthesis`
- `citation_quality`: count `cited_node_count`, then for each cited id look up the corresponding `ConstellationNode`, count `citations_with_high_confidence_source` where `node.confidence >= 0.7`, and `citations_aka_only` where `node.source_ref.source_type == "unknown"`
- `verdict`: call `theogony.reporting.verdict.verdict_for_query(report)` (verdict module already exists; if a query-specific verdict heuristic is missing, add one to `verdict.py` mirroring the ingest pattern — `good` if cited >= 1 and gaps low; `partial` if some gaps; `poor` if 0 cited; `inconclusive` if `Constellation.is_sufficient` is False)

If `report_writer` is None, the pipeline still returns the report on `QueryResult.report` but does not persist it. CI tests use this mode; CLI/API will pass a writer.

**Latency budget (Plan §4.2).** Embed query <50 ms; multi_hop ~100–500 ms on Neo4j; assemble <100 ms; synthesize ~1.5–3 s. p95 target is < 2 s end-to-end on the demo machine (excludes synthesis token-generation tail) — but the Plan §5 E8 success criterion is < 2 s p95 *total*, so the target is tighter against StubLLM (where synthesis is 0 ms) and necessarily looser against real Gemini. Document both numbers in the pipeline docstring.

### `RelevanceTracker` — `memory/relevance.py`

The bridge from "the user got an answer" to "the chronicle remembers it was useful". Plan §4.3 write-back loop: for each cited node id, bump `last_accessed=now()` and `relevance += δ` (capped at 1.0). Default δ = 0.05; expose as a constructor argument.

```python
class RelevanceTracker:
    def __init__(
        self,
        store: KnowledgeStore,
        *,
        relevance_delta: float = 0.05,
    ) -> None: ...

    async def bump(self, node_id: str) -> None: ...
    async def bump_all(self, node_ids: Iterable[str]) -> None: ...
```

`bump` reads the current scores via `store.get_node` and writes back via `store.update_scores`. This costs two Bolt round-trips per cited node. Acceptable for Gen 1 demo cardinality (≤ 10 cited nodes per answer). PHX-0048 (single-roundtrip update_scores) supersedes this once landed; until then, the two-roundtrip pattern matches what the Neo4j store already does internally for vitality denormalisation.

The pipeline calls `await relevance.bump_all(answer.cited_node_ids)` after `_finalize_report` — i.e. after the report captures pre-bump confidence/relevance values, so the report reflects the constellation as the user saw it, not the post-bump state.

## Tests

Six new test files. The pattern mirrors what Talos already established in E5/E6/E7: unit tests against in-memory stores + StubLLM, plus one live test against testcontainers Neo4j, gated on `THEOGONY_TEST_NEO4J=1`.

| File | Layer (§3.8) | What it asserts |
|---|---|---|
| `test_retrieval_multi_hop.py` | 5 unit | Retriever wraps `store.multi_hop_search` correctly; passes through k/hops/min_weight; `MultiHopBreakdown` numbers reflect store calls. |
| `test_retrieval_constellation.py` | 5 unit + 6 snapshot | Assembler projects to slim DTOs; edge dedup; gap identification (both kinds); `path="fast"`. Snapshot via `syrupy` on the `Constellation` *structure* (ids, types, source_refs) — never on LLM-synthesised prose. |
| `test_retrieval_synthesize.py` | 5 unit | StubLLM with scripted responses; citation regex parses `[AKA-…]`; hallucinated ids are dropped + WARNING logged; `Answer.synthesis` populated from `LLMResult`; audit-log row written when `audit_log=` is wired. |
| `test_retrieval_pipeline.py` | 5 integration | Full ask loop against `InMemoryKnowledgeStore` + StubLLM. Asserts: report file path returned when writer provided; report-less path returns `QueryResult.report_path is None`; `RelevanceTracker.bump_all` called for every cited id; cited ids' `last_accessed` advances + `relevance` ticks up. |
| `test_retrieval_pipeline_neo4j_live.py` | 5 + 6 live | Same flow against `Neo4jKnowledgeStore` via testcontainers. Asserts: same counts as InMemory on the same fixture; verdict matches; latency p95 < 2 s with StubLLM (excludes real-LLM tail). |
| `test_relevance_tracker.py` | 5 unit | `bump` increments correctly, caps at 1.0, advances `last_accessed`; `bump_all` is idempotent on repeated ids; nonexistent node id is a no-op (no exception). |

CI gating: the live test joins the existing `neo4j` job in `.github/workflows/ci.yml` (no new job).

## Scope boundaries (do not touch)

- **OneirosWorker** — separate post-E8 etappe (see scope decision above).
- **API + CLI** — E9 (`/query`, `theogony ask`, `theogony resolve`).
- **Detective Mode** — separate etappe, conditional on PHX-0041.
- **Phoenix import/export** — Gen 2.
- **`AuditingLLMProvider` wrapper** — PHX-0038, trigger condition is "site seven"; AnswerSynthesizer is site four. Stay with explicit constructor injection.
- **`update_scores` single-roundtrip optimisation** — PHX-0048 deferred; do **not** anticipate it in `RelevanceTracker`.
- **`batch_upsert_*`** — PHX-0046; not relevant on the read path.
- **Cypher query-plan audit** — PHX-0042; explicitly scheduled to run *after* E8 lands so retrieval queries are profiled in their settled form.
- **Vitality formula edits** — Plan §9 deliberately leaves vitality refactor-vulnerable; do not freeze it.
- **"Slow path" reasoning** — `Constellation.path="slow"` is reserved for Gen 2; do not implement.

## Plan deviations to escalate (not anticipated, but if encountered)

- If `KnowledgeStore.multi_hop_search` returns nodes whose `embedding` field is empty (the E7 `vector_search` exclusion of embedding-less nodes is correct, but the traverse expansion can pick them up): document the behaviour and decide whether the assembler keeps them (they have `source_ref` and are citable) or drops them. Default: keep them. Escalate if you find a contrary plan reference.
- If the prompt discipline forces an awkward citation format on Gemini specifically (Gemini sometimes rewrites `[AKA-abc123]` to `[**AKA-abc123**]` markdown): adjust the regex to tolerate emphasis markers, document the deviation in the PR body. Do **not** start a Daedalus round; this is the same kind of "real-LLM brittleness" deviation Talos already escalated correctly in E4 (Gemini schema limits) and E6 (rate-limit graceful degradation).
- If the four-component composition turns out smaller than expected and you have headroom for `OneirosWorker` without breaking the size budget, propose it as an addendum in the PR body — do **not** silently expand scope.

## Done when

- `pytest tests/ -q` green; new tests added all pass.
- `THEOGONY_TEST_NEO4J=1 pytest tests/test_retrieval_pipeline_neo4j_live.py -v` green against testcontainers.
- `ruff check src/ tests/`, `ruff format --check src/ tests/`, `mypy --strict src/theogony` all green.
- One end-to-end smoke against the E6/E7 ingest you already produced: `theogony ingest 43497 --sentences 50 --relations 10` (already run for E7's "Done when") into a Neo4j store, then a Python REPL or smoke script calling `QueryPipeline.ask("Wer war Sven Hedin?")` returns an `Answer.text` with at least one `[AKA-…]` citation that resolves to a node in the constellation. Capture the smoke output in the PR body.
- `data/run_reports/query/<ulid>.json` written for the smoke; verdict, multi_hop, synthesis, citation_quality fields all populated.
- PR body documents: deliverables vs Plan §5 E8 success criteria, scope decision on OneirosWorker (above), prompt-discipline rationale, latency-budget caveat (StubLLM vs real LLM).

## Next after E8

E9 = API + CLI surface (`/query`, `/node/{id}`, `/health`, `theogony ask`, `theogony node`, `theogony serve`, `theogony resolve [<mention>] [--list]`, `theogony reports list/show`). The retrieval contract you ship in this PR is the E9 brief's foundation; freezing `QueryResult` and `Answer` shapes here means E9 can be drafted against them without surprise.
