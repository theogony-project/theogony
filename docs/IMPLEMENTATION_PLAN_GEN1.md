# Implementation Plan — Generation 1

Architect: Daedalus  
Mandate: [`prompts/daedalus.md`](../prompts/daedalus.md)  
Status: **Draft v4 — Hesiod Review Round 2 (Run Reports)**  
Date: 2026-04-17

This document translates the existing vision (`README.md`, `VISION.md`, `PHILOSOPHY.md`, `ARCHITECTURE.md`, `DEEP_TECH_VISION.md`, `CHRONESE.md`, `METIS.md`, `HESTIA.md`, `HIVE.md`, `COGNITIVE_ARCHITECTURE.md`, `OPERATIVE_KNOWLEDGE.md`, `PHOENIX_BACKLOG.md`) into a concrete, buildable plan for the first four weeks of work.

It deliberately under-builds. Generation 1 must reach one demonstrable moment, not the full vision. Anything not necessary for that moment is deferred to a Phoenix Backlog ticket.

**Changes since v3 (2026-04-17, Hesiod review round 2 continued — Run Reports):**
- New §2.11 — `Reporting` component group: three Pydantic schemas (`IngestRunReport`, `QueryRunReport`, `OneirosTickReport`), `RunReportWriter`, self-verdict heuristics with explicit default thresholds.
- §2.5, §2.6, §2.7 — every pipeline gains a `_finalize_report()` hook that builds the appropriate report at end-of-run and hands it to the writer.
- §2.8, §3.7 — CLI gains `theogony reports list` and `theogony reports show <run_id>`.
- §5 — ~1 day of `RunReport` work distributed across all four weeks (S each); does not displace existing scope.
- §7 — new PHX-0035 (Reviewer Agent that consumes RunReports). **Note on numbering:** Hesiod's review round 2 (Run Reports) suggested filing this as PHX-0032, but PHX-0032 was already taken in v3 (Cross-Language Coreference). To preserve ID stability for any external reference to v3 tickets, the Reviewer-Agent ticket is filed as PHX-0035. The original Hesiod proposal text is preserved verbatim in the ticket description.

**Changes since v2 (2026-04-17, Hesiod review round 2):**
- §3.4 — Wikidata strategy substantially deepened: multi-language (`en`, `de`, `fr`, `it`) parallel `wbsearchentities` with candidate intersection; biographical-fact disambiguation (P569, P570, P106, P19, P937); five-tier confidence model; opt-in Detective Mode for high-stakes cases; honest-failure path with `manual_resolution_needed` flag.
- §2.5 — `EntityResolver` upgraded from M to L; new sub-component `WikidataDetective` for the deeper reasoning pass.
- §4.1 — ingest timing re-estimated (entity resolution rises from ~30–45 s to ~60–90 s; total still ~5–6 min, under Hesiod's target).
- §6 — OQ-6 explicitly answered: stays deferred, with reasoning. The five-tier confidence model + Detective Mode + `manual_resolution_needed` already provide Athene-light specifically for Wikidata alignment.
- §9.5 — edge-ID disambiguator clarified: it does **not** include `llm_model_id` or `prompt_template_id`. Re-extraction with a different model that produces the same `(source, relation, target, evidence_span)` is correctly idempotent; provenance of which models produced an edge lives in the `ExtractionAuditLog`.
- §9.6 — new data-model change: `KnowledgeNode.manual_resolution_needed: bool` and `resolution_tier: int`.
- §3a, PID-2 — `expand_window` prompt mechanics specified concretely (structured prompt with explicit `Previous`/`Central`/`Next` sections; schema enforces `evidence_span ⊆ central sentence`).
- §7 — three new PHX tickets (PHX-0032 to PHX-0034) for deferred Wikidata work.

**Changes since v1 (2026-04-17, Hesiod review round 1):**
- §3.3 — explicit three-way comparison of LLM providers (GPT-4o-mini, Gemini 2.5 Flash Lite, Claude Haiku 3.5) with verified 2026 pricing; default switched to Gemini 2.5 Flash Lite.
- §2.5, §4.1 — Wikidata strategy promoted from "mitigation" to standard: pre-fetching after NER, parallelisation via `wbsearchentities` (higher rate limit than SPARQL), targeting under 6 min per book.
- §3.5 — softer close on the framework decision: Gen 2 must reopen the question with empirical evidence.
- §2.5 — `ExtractionAuditLog` added as a first-class component.
- §6 — new OQ-7 (resumable ingest) with a minimal Gen 1 recommendation.
- §2.8, §4.4 — `serve` lifecycle specified (FastAPI `lifespan`, signal handling, in-flight cancellation).
- §5 (Week 1) — install/test timing corrected: ~10 min cold (model downloads), under 30 s warm.
- New §3a — "Pre-Implementation Decisions" containing PID-1 (atom granularity, ex OQ-1) and PID-2 (sentence vs. document-level extraction, ex OQ-5), each resolved heuristically with explicit reasoning. These cannot wait for Week 4 — they constrain the data model and pipeline shape.

---

## 1. Executive Summary

**What Generation 1 is.**  
A single-machine, single-tenant pipeline that ingests one English book from Project Gutenberg, extracts entities and typed relations, stores them as a vector-graph in Neo4j, and answers natural-language questions by assembling a Constellation and synthesizing an answer with a hosted LLM. Every entity in every answer cites its source.

**What Generation 1 is not.**  
- Not multi-tenant. No Lethe Vaults, no Hades, no access control.
- Not multi-source. Only Gutenberg in scope; web search and Wikidata appear only as supporting tools, not as a sustained acquisition stream.
- Not multi-language. Only English.
- Not multi-modal. Only text.
- Not Pantheon-as-personas. The mythological agent names are useful conceptual handles, but Gen 1 contains exactly three runtime workers: an ingestion pipeline, a query pipeline, and one background worker that approximates Oneiros at the smallest possible scale.
- Not a Phoenix process. No distillation, no rebirth.
- Not a multi-embedding fabric. One embedding per node.
- Not Chronese as a separate language. Chronese is realized as Pydantic models for assertion frames (already partially present); no compiler, no separate runtime.
- Not Metis. Documented role only, no code.
- Not Hestia as a runtime. Schema and prompt templates only.

**Success looks like:** the demonstration moment below works on a developer laptop, with `~300 EUR/month` of hosted services unspent, in front of a critical observer, end-to-end, with clear citations.

**The single demonstration moment (end of Week 4).**

```
$ theogony serve &
$ theogony ingest 944
[10–15 min: download, clean, extract, embed, store]

$ theogony ask "Welche Ethnien beschreibt Heinrich Harrer in seinen Erlebnissen, und auf welchen Wegen begegnet er ihnen?"
[under 5 s]

Answer:
  Heinrich Harrer beschreibt … [Tibeter, Khampas, …]
  Er begegnet ihnen während seiner Wanderung von … nach Lhasa.
  Quellen: [Q806463 Uttarkashi], [AKA-…], [AKA-…]

$ theogony node Q806463
Uttarkashi (place)
  layer: mneme        confidence: 0.78        connectivity: 0.41
  source: Gutenberg:944, chapter 3, offset 18433–18601
  edges:
    REACHED_BY → AKA-… (Heinrich Harrer)        weight 0.72
    LOCATED_IN → Q1499  (Uttarakhand)            weight 0.95
    NEAR        → AKA-…                          weight 0.43
```

This single sequence proves: acquisition works, extraction produces structured knowledge, the store performs combined vector+graph retrieval, the agent synthesizes citation-anchored answers, and the Hover-Lupe is real (you can step into any cited entity).

If we can run this against an audience and the answer is plausibly grounded in the book, Generation 1 is done.

---

## 2. Component Inventory

The repository already contains: `core/model.py`, `core/store.py`, `core/vitality.py`, and tests. Everything else listed below is to be built. Sizes: **S** (≤ ½ day), **M** (1–3 days), **L** (4+ days).

### 2.1 Configuration and bootstrap

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `Settings` | `config/settings.py` | `pydantic-settings` | every other module | Unit: load from `.env` and from kwargs | S |
| `.env.example` | repo root | — | humans | — | S |
| Logging setup | `config/logging.py` | `rich` | every other module | Smoke test: handler installed | S |

### 2.2 Storage

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `InMemoryKnowledgeStore` | `stores/memory.py` | `core.model` | tests, dev runs | Shared protocol-conformance suite | M |
| `Neo4jKnowledgeStore` | `stores/neo4j_store.py` | `neo4j>=5.18`, `core.model` | API, retrieval | Same suite, marked `integration`, `testcontainers-python` for CI | L |
| Protocol-conformance suite | `tests/store_contract.py` | `core.store` | both stores | Parametrised over all stores | M |

The two stores must pass the same test file. This is the single most important architectural lever in Gen 1 — it lets us develop the upper layers against `InMemory` while Neo4j is being wired up, and it forces us to hold the protocol honest from day one.

### 2.3 LLM and embeddings

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `EmbeddingProvider` (Protocol) | `extraction/embedding.py` | — | extraction, retrieval | — | S |
| `LocalSentenceTransformerEmbedder` (BGE-small-en-v1.5, 384 dim) | `extraction/embedding.py` | `sentence-transformers` | default | Unit: cached output deterministic; integration: actual encode | M |
| `OpenAIEmbedder` (optional) | `extraction/embedding_openai.py` | `openai` (extra) | optional | Unit with `respx`-mocked HTTP | S |
| `LLMProvider` (Protocol) | `agents/llm.py` | — | extraction, retrieval, agents | — | S |
| `GeminiLLMProvider` (default — see §3.3a) | `agents/llm_gemini.py` | `google-genai` (extra) | default | Unit with mocked client; live test gated by env var | M |
| `OpenAILLMProvider` (alternative) | `agents/llm_openai.py` | `openai` (extra) | optional | Unit with mocked client; live test gated by env var | M |
| `AnthropicLLMProvider` (alternative) | `agents/llm_anthropic.py` | `anthropic` (extra) | optional | Unit with mocked client; live test gated by env var | M |
| `StubLLMProvider` (deterministic, scripted responses) | `agents/llm_stub.py` | — | tests | Unit | S |

The embedding model identifier is recorded on every node as a first-class field (`embedding_model_id`, see §9.3). This satisfies PHX-0005 (Embedding Model Independence) at the data-model level.

### 2.4 Acquisition

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `AcquisitionAdapter` (Protocol) | `acquisition/base.py` | — | ingestion | — | S |
| `RawContent` (Pydantic) | `acquisition/base.py` | `pydantic` | ingestion | Unit | S |
| `GutenbergAdapter` | `acquisition/gutenberg.py` | `httpx`, Gutendex API | ingestion | Unit with `respx`; integration test pulls one tiny public domain text | M |

No web crawler in Gen 1. No Wikidata acquisition adapter — Wikidata is used only by entity resolution (§2.5).

### 2.5 Extraction pipeline

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `TextCleaner` (strips Project Gutenberg header/footer) | `extraction/clean.py` | — | pipeline | Unit on real PG samples | S |
| `Sentencizer` (spaCy `en_core_web_sm`) | `extraction/sentence.py` | `spacy` | pipeline | Unit | S |
| `NerExtractor` (spaCy NER) | `extraction/ner.py` | `spacy` | pipeline | Unit on fixtures | M |
| `EntityResolver` (multi-language `wbsearchentities`, alias matching, type-pass filter, biographical-fact disambiguation, five-tier confidence model, `manual_resolution_needed` honest failure — see §3.4) | `extraction/resolve.py` | `httpx`, `sqlite3`, `LLMProvider`, `BookContextExtractor` | pipeline | Unit with `respx`; integration with live Wikidata gated by env var; golden-file tests for tier assignment on fixture mentions | **L** (was M) |
| `WikidataDetective` (opt-in deeper reasoning pass for low-confidence cases — Stage 5 of §3.4) | `extraction/detective.py` | `EntityResolver`, `httpx` (Wikipedia first-paragraph fetch), `LLMProvider` | CLI `--detective`, `EntityResolver` callback | Unit on fixture cases; integration test gated | M |
| `BookContextExtractor` (one-shot LLM call to summarise period/places/protagonists from book metadata + opening chapter) | `extraction/book_context.py` | `LLMProvider` | `EntityResolver` | Unit with `StubLLMProvider`; one integration test against Tibet book | S |
| `RelationExtractor` (LLM with strict JSON schema; supports `expand_window` per PID-2) | `extraction/relations.py` | `LLMProvider`, `ExtractionAuditLog` | pipeline | Unit with `StubLLMProvider`; golden-file tests | M |
| `ExtractionAuditLog` (append-only SQLite, write-only from pipeline, read by debug tooling) | `extraction/audit.py` | `sqlite3` | `RelationExtractor`, `EntityResolver` (LLM disambiguation calls) | Unit: pipeline writes one row per LLM call; round-trip parse | S |
| `IngestRunStore` (SQLite table tracking per-source ingestion progress; supports OQ-7 resume) | `extraction/ingest_run.py` | `sqlite3` | `IngestionPipeline`, CLI | Unit: stage transitions; resume after simulated crash | S |
| `IngestionPipeline` (orchestrates all of the above per book; accumulates per-stage observations and emits an `IngestRunReport` via `_finalize_report()` — see §2.11) | `extraction/pipeline.py` | everything in `extraction/`, `acquisition/`, `reporting/` | CLI, API | Unit on tiny fixture; integration end-to-end on small sample; report assertions in the smoke test | L |

**`ExtractionAuditLog` — what and where.** A single SQLite database at `data/extraction_audit.sqlite` (path overridable in `Settings`). One table `extraction_calls`, append-only, indexed on `run_id` and `created_at`. Per row:

- `id` (autoincrement)
- `run_id` (FK to the `IngestRun` row introduced for OQ-7, §6)
- `created_at` (UTC timestamp)
- `call_type` (`relation_extraction` | `entity_disambiguation`)
- `llm_provider`, `llm_model_id`, `prompt_template_id`
- `input_text` (the source sentence, or the disambiguation context)
- `input_payload_json` (the full JSON that was sent to the provider, including system prompt, schema, and parameters)
- `raw_response_text` (the full provider response before any parsing)
- `parsed_output_json` (the validated Pydantic model, serialised; `null` if validation failed)
- `parse_error` (text of any validation exception)
- `resulting_node_ids` (JSON list, populated after upsert)
- `resulting_edge_ids` (JSON list, populated after upsert)
- `cost_usd` (estimated, from token counts × provider price table)
- `latency_ms`

This makes every extracted edge traceable back to its prompt and response, satisfies the "logged verbatim" promise of §3.3, and gives Athene-style verification a complete data set to operate on when it eventually exists. The log is *not* truncated automatically; rotation to a `data/extraction_audit/{year-month}.sqlite` archive is a Gen 2 concern (PHX-0028, see §7).

**Test strategy.** A unit test ingests three sentences through `IngestionPipeline` with `StubLLMProvider`, then asserts:
1. exactly one row per LLM call exists,
2. `parsed_output_json` round-trips through the relevant Pydantic model,
3. `resulting_edge_ids` matches the IDs returned by the store mock.

**What is not in scope.** No log analytics, no dashboard, no anomaly detection. The log is read by humans with `sqlite3` or by future agents (Athene); Gen 1 ships only the write side and the schema.

### 2.6 Retrieval

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `MultiHopRetriever` (vector → traverse → re-rank → dedupe) | `retrieval/multi_hop.py` | `KnowledgeStore` | constellation assembler | Unit against `InMemoryKnowledgeStore` | M |
| `ConstellationAssembler` | `retrieval/constellation.py` | retriever, store | API, CLI | Unit; snapshot tests with `syrupy` | M |
| `AnswerSynthesizer` (LLM call, structured prompt, citation parser) | `retrieval/synthesize.py` | `LLMProvider`, `Constellation` | API, CLI | Unit with `StubLLMProvider` | M |
| `QueryPipeline` (orchestrates the three above; emits a `QueryRunReport` via `_finalize_report()` — see §2.11) | `retrieval/pipeline.py` | retriever, assembler, synthesizer, `reporting/` | API, CLI | Unit | S |

### 2.7 Memory and lifecycle

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `OneirosWorker` (background asyncio task: re-score, promote, light association; emits one `OneirosTickReport` per tick via `_finalize_report()` — see §2.11) | `memory/oneiros.py` | `KnowledgeStore`, `vitality`, `reporting/` | API runtime | Unit with `InMemoryKnowledgeStore`, fast clock | M |
| `RelevanceTracker` (records access, bumps relevance/freshness) | `memory/relevance.py` | `KnowledgeStore` | retrieval pipeline | Unit | S |

Oneiros in Gen 1 is one loop, every 60 s, doing three things: recompute connectivity, recompute vitality, promote what passes the threshold. No semantic association beyond the trivial co-occurrence already produced by extraction. PHX-0004 (Crystallized Inference) and the genuinely associative behavior described in `DEEP_TECH_VISION.md` are deferred.

### 2.8 API and CLI

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| FastAPI app with `lifespan` (see §4.4) | `api/app.py` | `fastapi`, all pipelines | uvicorn | TestClient + lifespan unit test | M |
| `/ingest`, `/query`, `/node/{id}`, `/health` | `api/routes/*.py` | pipelines | clients | TestClient | M |
| Typer CLI (`ingest`, `ask`, `node`, `status`, `serve`, `resolve`, `reports list`, `reports show`, `--resume`, `--restart`, `--detective`) | `cli.py` | pipelines, `reporting/` | humans | CliRunner | M |

### 2.9 Phoenix and Hestia (documented only in Gen 1)

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `PhoenixTicket` (Pydantic; mirrors YAML schema) | `phoenix/ticket.py` | `pydantic`, `pyyaml` | tooling, future automation | Unit: round-trip parse | S |
| `HestiaReview` (Pydantic) | `agents/hestia.py` | `pydantic` | humans | Unit | S |
| Two prompt profiles | `prompts/hestia_sentinel.md`, `prompts/hestia_auditor.md` | — | humans | — | S |

Hestia in Gen 1 is text and a schema. There is no automated invocation. This is consistent with `HESTIA.md` §"Realistic Build Path / Generation 1".

### 2.10 Tests

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| Existing model/vitality tests | `tests/test_model.py` | — | CI | already present | — |
| Store contract suite | `tests/test_store_contract.py` | both store impls | CI | parametrised | M |
| Extraction tests | `tests/test_extraction*.py` | fixtures | CI | unit + small integration | M |
| Retrieval tests | `tests/test_retrieval*.py` | `InMemoryKnowledgeStore` fixtures | CI | unit + snapshot | M |
| Reporting tests | `tests/test_reporting.py` | `RunReport*`, fixture pipeline observations | CI | unit (verdict heuristics, JSON round-trip, atomic write) | S |
| API tests | `tests/test_api.py` | `httpx.AsyncClient` | CI | unit | S |
| End-to-end happy path | `tests/test_e2e_smoke.py` | tiny fixture book | CI (slow marker) | integration: also asserts a `RunReport` was written | M |

### 2.11 Reporting

The `ExtractionAuditLog` (§2.5) records every LLM call. The `IngestRunStore` (§2.5) records stage transitions. Stdlib `logging` records ad-hoc events. None of these is a *retrospective* — a structured, machine-readable summary of "what happened in this run, was it good, what should change". `Reporting` fills that gap with one Pydantic schema per run type and a single writer.

The reports are **write-only from the system's perspective**. Reading and analysing them is the job of a future Reviewer agent (PHX-0035, see §7). Gen 1 ships only the writer.

| Component | Module | Depends on | Depended on by | Test strategy | Size |
|---|---|---|---|---|---|
| `IngestRunReport` (Pydantic) | `reporting/models.py` | `pydantic` | `IngestionPipeline._finalize_report` | Unit: round-trip JSON, schema stability | S |
| `QueryRunReport` (Pydantic) | `reporting/models.py` | `pydantic` | `QueryPipeline._finalize_report` | Unit: round-trip JSON, schema stability | S |
| `OneirosTickReport` (Pydantic) | `reporting/models.py` | `pydantic` | `OneirosWorker._finalize_report` | Unit: round-trip JSON, schema stability | S |
| `RunReportWriter` (atomic JSON writer) | `reporting/writer.py` | `pydantic`, stdlib `os.replace` | three pipelines | Unit: atomic write under simulated mid-write crash; partial files never appear at final path | S |
| `IngestionPipeline._finalize_report` | `extraction/pipeline.py` | `IngestRunReport`, `RunReportWriter`, observation accumulators on the pipeline | report consumers | Unit: synthetic stage observations → expected verdict | S |
| `QueryPipeline._finalize_report` | `retrieval/pipeline.py` | `QueryRunReport`, `RunReportWriter` | report consumers | Unit | S |
| `OneirosWorker._finalize_report` | `memory/oneiros.py` | `OneirosTickReport`, `RunReportWriter` | report consumers | Unit | S |

#### 2.11.1 Schemas

All three reports share a common header. Defined once in `reporting/models.py` as `RunReportBase`:

```python
class RunReportBase(BaseModel):
    run_id: str                            # ULID; same as IngestRun.run_id when applicable
    report_type: Literal["ingest", "query", "oneiros"]
    started_at: datetime
    finished_at: datetime
    duration_s: float                      # finished_at - started_at, computed
    status: Literal["completed", "partial", "failed", "aborted"]
    verdict: Literal["good", "partial", "poor", "failed"]
    verdict_reasoning: str                 # short text; thresholds that fired
    anomalies: list[str] = []              # human-readable strings
    recommendations: list[str] = []        # free-text; consumed by Reviewer agent
    audit_log_run_id: str | None = None    # FK to ExtractionAuditLog.run_id
    ingest_run_id: str | None = None       # FK to IngestRunStore.run_id (ingest only)
```

**`IngestRunReport`** extends with:

```python
class IngestStageReport(BaseModel):
    name: Literal["acquired","cleaned","sentencized","mentions_extracted",
                  "mentions_resolved","relations_extracted","embedded","stored"]
    duration_s: float
    status: Literal["ok","skipped","failed"]
    notes: str | None = None

class NerSummary(BaseModel):
    total_mentions: int
    by_type: dict[str, int]                # {"PERSON": 412, "GPE": 178, ...}

class ResolutionSummary(BaseModel):
    tier_counts: dict[int, int]            # {4: 134, 3: 89, 2: 47, 1: 22, 0: 18}
    wikidata_api_requests: int
    cache_hits: int
    failures_after_retry: int
    manual_resolution_needed: int

class RelationSummary(BaseModel):
    attempted: int
    parsed_ok: int
    dropped_schema_violation: int
    dropped_evidence_span_violation: int
    llm_cost_eur: float

class EmbeddingSummary(BaseModel):
    nodes_embedded: int
    embedding_model_id: str
    duration_s: float

class StoreSummary(BaseModel):
    nodes_upserted: int
    edges_upserted: int
    idempotent_skips: int

class QualityFlags(BaseModel):
    low_tier_ratio: float                  # tier ≤ 1 / total resolved
    schema_violation_rate: float
    parse_error_rate: float

class IngestRunReport(RunReportBase):
    report_type: Literal["ingest"] = "ingest"
    source_type: str
    source_identifier: str
    word_count: int
    sentence_count: int
    chapter_count: int | None = None
    stages: list[IngestStageReport]
    ner: NerSummary
    resolution: ResolutionSummary
    relations: RelationSummary
    embedding: EmbeddingSummary
    store: StoreSummary
    quality_flags: QualityFlags
```

**`QueryRunReport`** extends with:

```python
class MultiHopBreakdown(BaseModel):
    seed_count: int
    nodes_per_hop: list[int]               # [seeds, hop1, hop2, ...]
    duplicates_removed: int
    duration_ms: int

class SynthesisBreakdown(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_eur: float
    latency_ms: int

class CitationQuality(BaseModel):
    cited_node_count: int
    citations_with_high_confidence_source: int    # source_ref present, resolution_tier ≥ 3
    citations_aka_only: int                        # tier 0 or no resolution_tier

class QueryRunReport(RunReportBase):
    report_type: Literal["query"] = "query"
    query: str
    query_length_chars: int
    embedding_duration_ms: int
    multi_hop: MultiHopBreakdown
    constellation_node_count: int
    constellation_edge_count: int
    suggested_source_count: int
    gaps_identified: int
    synthesis: SynthesisBreakdown
    citation_quality: CitationQuality
```

**`OneirosTickReport`** extends with:

```python
class VitalityShift(BaseModel):
    nodes_evaluated: int
    mean_vitality_before: float
    mean_vitality_after: float
    median_shift: float

class OneirosTickReport(RunReportBase):
    report_type: Literal["oneiros"] = "oneiros"
    nodes_evaluated: int
    nodes_promoted: int                    # EPHEMERA → MNEME
    nodes_degraded: int                    # MNEME → EPHEMERA or candidate for archival
    vitality: VitalityShift
    duration_s: float
```

#### 2.11.2 Self-verdict heuristics

Each `_finalize_report()` computes its own `verdict` from concrete observations. The thresholds below are **defaults** — every threshold lives in `Settings` under `report.thresholds.*` so a future Reviewer agent (or a human) can tune them based on measured behaviour.

**`IngestRunReport.verdict`** is computed in this order:

| Verdict | Triggered when |
|---|---|
| `failed` | `status != "completed"` |
| `poor` | `quality_flags.parse_error_rate > 0.20` OR `quality_flags.low_tier_ratio > 0.60` OR `len(anomalies) ≥ 3` |
| `partial` | `0.05 < parse_error_rate ≤ 0.20` OR `0.30 < low_tier_ratio ≤ 0.60` OR `0 < len(anomalies) < 3` |
| `good` | none of the above; all stages `ok`, `parse_error_rate ≤ 0.05`, `low_tier_ratio ≤ 0.30`, `anomalies == []` |

`anomalies` are detected by simple, named rules in `reporting/anomaly.py`:

- `stage_slow`: a stage took > 2× a baseline duration recorded in `Settings` (defaults baseline values per stage from §4.1 v3 figures).
- `cost_spike`: total LLM cost exceeded 1.5× the rolling-median of the last 5 ingests (skipped if fewer than 5 prior runs exist; in Gen 1 with the demo book this rarely fires).
- `wikidata_failure_burst`: > 10 % of `wbsearchentities` calls failed after retry.
- `embedding_skew`: the standard deviation of embedding-batch latency > 3× its mean (signals a runaway batch).

**`QueryRunReport.verdict`** is computed in this order:

| Verdict | Triggered when |
|---|---|
| `failed` | synthesis returned no answer or raised |
| `poor` | `citation_quality.citations_with_high_confidence_source == 0` AND `cited_node_count > 0` (every citation is AKA-only — answer is technically grounded but not anchored to canonical entities) OR `synthesis.latency_ms > 10_000` |
| `partial` | `0 < citations_with_high_confidence_source < 0.5 × cited_node_count` OR `5_000 < latency_ms ≤ 10_000` OR `gaps_identified ≥ 3` |
| `good` | `citations_with_high_confidence_source ≥ 0.5 × cited_node_count` AND `latency_ms ≤ 5_000` AND `gaps_identified < 3` |

**`OneirosTickReport.verdict`** is computed in this order:

| Verdict | Triggered when |
|---|---|
| `failed` | tick raised before completion |
| `poor` | `nodes_evaluated == 0` (worker is starving) OR `vitality.median_shift < -0.05` (system is losing trust on average — consolidation is moving the wrong way) |
| `partial` | `nodes_promoted == 0 AND nodes_degraded == 0` (worker did work but moved nothing — possibly threshold drift) |
| `good` | `nodes_evaluated > 0` AND no `poor` or `partial` triggers |

`verdict_reasoning` is a one-line concatenation of the rules that fired, e.g. `"low_tier_ratio=0.41 (>0.30 partial-threshold); 1 anomaly: stage_slow:relations_extracted=4.2x baseline"`. This is the field the Reviewer agent reads first when triaging.

#### 2.11.3 Storage layout

```
data/run_reports/
  ingest/
    01HK3M…ULID.json
    01HK3M…ULID.json
  query/
    01HK3M…ULID.json
  oneiros/
    01HK3M…ULID.json
```

`RunReportWriter.write(report)` writes to `data/run_reports/{type}/{run_id}.json.tmp` then `os.replace()`s to the final path — atomic on every POSIX filesystem. `model_dump_json(indent=2)` produces a human-readable artefact that `cat` and `jq` both handle.

#### 2.11.4 What this is deliberately not

- **No analytics dashboard.** Reports are JSON files; humans use `jq`, agents use `json.load`.
- **No anomaly detection beyond the simple rules above.** A real anomaly detector compares distributions across runs; that is the Reviewer agent's job.
- **No comparison across runs.** Each report stands alone. Cross-run synthesis is the Reviewer agent's job.
- **No web UI.** Out of scope for Gen 1 (genesis log §10: agent-first, GUI irrelevant).
- **No automatic action on bad verdicts.** A `poor` verdict does not abort the run, does not retry, does not page anyone. It is a written observation. Human reads it. Future Reviewer agent files a Phoenix ticket. That is enough.

---

## 3. Critical Decisions

For each decision: **Advocate** (strongest case for the proposal), **Skeptic** (strongest objections to it), **Counterview** (the strongest honest case for the alternative), **Recommendation**.

### 3.1 KnowledgeStore backend

**Proposal: Neo4j 5.x Community Edition for Gen 1, behind the existing `KnowledgeStore` Protocol; an `InMemoryKnowledgeStore` in parallel for tests and rapid development.**

**Advocate.**  
Neo4j 5.11+ has native vector indexes (HNSW) that can be combined with graph traversal in a single Cypher query. That is exactly the operation `multi_hop_search` requires. The Bolt driver is Apache 2.0 (no license issue at the application level). Operationally it is a single container with a well-known footprint. Cypher is declarative and inspectable. Aura Free supports up to 50 k nodes / 175 k relationships, more than enough for a single book demo, at zero cost.

**Skeptic.**  
The Community Edition of the Neo4j *server* is GPLv3. We do not embed it; we communicate over the wire, so this is fine for an Apache 2.0 codebase, but distribution in any "all-in-one" image must keep the boundary explicit. The vector index is good but not state-of-the-art relative to LanceDB/Qdrant. Single-instance scaling is bounded; clustering requires Enterprise. Neo4j is JVM-based: 2–4 GB RAM minimum, slow cold start, more operational weight than embedded options. Cypher is a learning surface. We pay for capability we will not use in Gen 1 (full ACID, multi-database, role-based auth).

**Counterview.**  
A hybrid stack of *embedded* components — LanceDB (vectors) + Kuzu (graph), or SQLite + `sqlite-vec` + `apache-age`-style extension — would have zero operational overhead, run inside the Python process, and remove an entire deployment moving part. LanceDB's ANN performance is superb. For a single-book demo on a laptop, an embedded stack would arguably be lighter and faster.

The honest weakness of Neo4j: we lock the architecture to a model where *the store* knows how to combine vector + graph. If we ever want to do something more exotic (signed-edge propagation, hyperedges, activation diffusion — all called for in `DEEP_TECH_VISION.md`), Neo4j is not where that lives. We will rebuild that layer regardless. So the question becomes: do we need Neo4j's Cypher convenience *now*, or can we tolerate an extra hop in Python orchestration to get embedded simplicity?

**Recommendation.**  
**Neo4j 5.x for Gen 1, but only after `InMemoryKnowledgeStore` is implemented and the contract suite is green.** Reasons in order of weight:

1. The protocol is already designed with Neo4j-ish semantics in mind (`multi_hop_search` is hard to implement in pure embedded code without inventing an in-process query planner). Re-deriving that protocol against an embedded backend now would cost more than it saves.
2. The architecture document and the existing prompt material name Neo4j as the Gen 1 choice. Reversing that without empirical pressure is itself a cost.
3. Neo4j Aura Free or local Docker keeps the financial cost at zero.
4. Behind the Protocol, this is fully reversible. Migrating to an embedded stack in Gen 2 costs one new `KnowledgeStore` implementation plus a Phoenix re-import. PHX-0001 already records this as a deferred concern.

What is given up: roughly 1–2 days of Cypher learning, ~3 GB of RAM on the dev machine, and a deployment dependency for users.

What we must do regardless: implement `InMemoryKnowledgeStore` first. Without it, the upper layers cannot be developed in parallel and CI cannot run without a Neo4j container in every job.

### 3.2 Embedding strategy

**Proposal: BGE-small-en-v1.5 (384 dim) via `sentence-transformers`, local, default. OpenAI `text-embedding-3-small` (1536 dim) available behind the same Protocol as an opt-in. The embedding model identifier is stored on every node.**

**Advocate.**  
BGE-small is 33 MB, runs at hundreds of sentences per second on a laptop CPU, scores well on MTEB, and produces 384-dimensional vectors that compress nicely in Neo4j's HNSW index (storage and query both benefit). Local means no rate limits, no network failures, no data leaves the machine. 384 dimensions is plenty for a single-book corpus.

**Skeptic.**  
BGE-small is English-only at top quality. If we ever ingest German Humboldt or French Polo (the genesis log mentions historical travel literature broadly), we need a multilingual model. The hard rule of "embedding model independence" (PHX-0005, marked critical/Gen 1) is delivered at the data-model level (we record the model id), but in practice migrating between embedding spaces still requires re-embedding everything, which is the Phoenix process — and Phoenix is out of Gen 1.

**Counterview.**  
OpenAI `text-embedding-3-small` is 1536 dim, multilingual, and roughly $0.02 per million tokens. For a single book of ~80 k tokens, that is fractions of a cent. The latency penalty (~100 ms per request, batchable) is negligible at our scale. We could use the API model, get higher quality and multilingual support, and skip the local-model dependency entirely.

**Recommendation.**  
**BGE-small-en-v1.5 as default. OpenAI embedder as optional. Single English book in scope.** The cost argument for OpenAI is real but small. The control argument for local is larger: in CI, on a laptop, on a plane, the system must work without an API key. The first user must be able to clone, install, ingest, and query within minutes, with no account anywhere. That is worth one English-only constraint.

What is given up: multilingual quality, slightly higher recall (gte-large or `text-embedding-3-large` would score 5–8 points higher on MTEB).

### 3.3 Extraction pipeline

**Proposal: spaCy for sentence segmentation and NER (local, free); a hosted LLM (default Gemini 2.5 Flash Lite, with GPT-4o-mini and Claude Haiku 3.5 selectable behind the `LLMProvider` Protocol) for relation extraction with strict JSON schema; Wikidata `wbsearchentities` for entity resolution with a local SQLite cache.**

**Advocate.**  
This split puts each task on the cheapest tool that does it well. NER is a solved problem at our scale; spaCy `en_core_web_sm` is fast and adequate for a first cut, with `en_core_web_trf` (440 MB) available as an upgrade. Relation extraction over historical prose with arbitrary, non-Wikidata-native predicates is the place where LLMs earn their keep. Wikidata is the largest open canonical entity store in existence, and free.

**Skeptic.**  
spaCy NER on 19th- and 20th-century prose has known weaknesses with archaic spellings, transliterated place names ("Uttar Kashi" vs. "Uttarkashi"), and historical geography. We will see misclassifications. Relation extraction by LLM is the most expensive and least reproducible step. Hallucination is the dominant risk: an LLM will happily invent a `BORN_IN` relation between two entities that are merely co-mentioned. This corrupts the Chronik in ways that are exactly contrary to PHILOSOPHY §3 ("Verification Over Authority").

**Counterview.**  
A purely local pipeline — spaCy for everything plus REBEL (a 1.6 GB pre-trained relation extractor) — would eliminate the hallucination risk and the LLM cost. REBEL's relation vocabulary is fixed and Wikidata-compatible, which has a side benefit: extracted relations align by construction with the canonical relation types we use elsewhere. The downsides are: lower recall on relations REBEL was not trained on (which for travel literature is many of them), a 1.6 GB local model that bloats CI and developer machines, and a large step backward in expressive power.

A pure-LLM pipeline (one prompt does NER + relations + resolution in a single call) would be conceptually cleanest but maximizes cost and gives the LLM the most rope to invent. It is also harder to test, since the failure modes blend.

**Recommendation.**  
**Tiered as proposed.** Every LLM-extracted relation must be:
1. constrained by a fixed vocabulary of relation types (start with ~20 hand-picked types relevant to travel/biography: `LOCATED_IN`, `TRAVELED_TO`, `MET`, `BORN_IN`, `MEMBER_OF`, `INFLUENCED_BY`, etc., plus a free-text `OTHER` bucket flagged for review),
2. emitted with an explicit confidence and an evidence span (the substring of the source sentence that justifies the relation),
3. logged verbatim in the `ExtractionAuditLog` (§2.5), so any extracted edge can be traced back to its prompt and response.

Where the LLM sees no relation in the fixed vocabulary, it returns `null`, not `OTHER`. Validation is a Pydantic model.

What is given up: coverage of long-tail relations; we will miss things. Acceptable for Gen 1 — the goal is correct, not complete.

Wikidata strategy is now `wbsearchentities` (HTTP GET with a much higher rate limit than the SPARQL public endpoint), pre-fetched in batch immediately after NER, with parallelisation and a SQLite cache. Detailed mechanics in §4.1 and the `EntityResolver` row of §2.5. Self-hosted Wikidata for sustained multi-book ingest is deferred to PHX-0024 (see §7).

#### 3.3a LLM provider comparison (the default)

The genesis log and the four-week budget force a concrete choice for Gen 1. Three plausible candidates exist. All three support strict JSON Schema output, all three have async Python SDKs, and all three are commercially priced. The table compares them against the workload from §4.1: ~3 000 LLM calls per book, ~200 input + ~50 output tokens per call → **~600 k input + ~150 k output per book**.

Prices verified 2026-04-17 from each vendor's public pricing page. Per-EUR figures use 1 USD ≈ 0.93 EUR.

| Property | GPT-4o-mini (OpenAI) | Gemini 2.5 Flash Lite (Google) | Claude Haiku 3.5 (Anthropic) |
|---|---|---|---|
| Input price (USD / 1 M) | 0.15 | **0.10** | 0.80 |
| Output price (USD / 1 M) | 0.60 | **0.40** | 4.00 |
| Cost per book (this workload) | ~$0.18 (~0.17 EUR) | ~$0.12 (~0.11 EUR) | ~$1.08 (~1.00 EUR) |
| Cost for 25 dev iterations | ~$4.50 (~4.20 EUR) | ~$3.00 (~2.80 EUR) | ~$27.00 (~25 EUR) |
| Context window | 128 k | **1 M** | 200 k |
| JSON Schema enforcement | `response_format` w/ Pydantic — most mature | `response_schema` w/ Pydantic — solid, slightly newer | tool-use as JSON output — workable but indirect |
| Free tier sufficient for early dev? | very limited | **yes (generous daily quota)** | no |
| SDK maturity | highest (`openai`) | medium (`google-genai`, recently revised) | high (`anthropic`) |
| Historical API stability | high | lower — Google deprecated Gemini 1.0/1.5/2.0 in ~18 months | high |
| EU compliance posture | OpenAI Europe + Zero Data Retention | Vertex AI EU regions | EU regions, ZDR available |
| Latency (subjective, p50, our payload) | ~1.5 s | ~1 s | ~2.5 s |

**Skeptic on Gemini 2.5 Flash Lite (the proposed default).**  
Google's deprecation cadence is real. Between mid-2024 and early 2026 Gemini went through 1.0, 1.5, 1.5 Flash 8B, 2.0, 2.0 Flash, 2.0 Flash Lite, and 2.5 — every one of those had migration notes. The `google-genai` SDK was revised in 2025. JSON-Schema adherence in Gemini has been measurably noisier than in OpenAI's `response_format` on some independent benchmarks, particularly around enums and required fields. None of this is fatal, but it adds friction during the four weeks where friction is most expensive.

**Counterview: GPT-4o-mini as the safer default.**  
At our volume the cost difference between Gemini and GPT-4o-mini is **1.40 EUR over 25 iterations**. That is not a budget argument; it is rounding error. The OpenAI SDK is the most mature, `response_format` with Pydantic is the most reliable structured-output path in the Python ecosystem in 2026, and OpenAI has not deprecated a model out from under us in this generation. For a single-developer four-week sprint, "fewer surprises" is worth more than 1.40 EUR.

**Counterview: Claude Haiku 3.5 as the quality default.**  
Haiku has the best record for adhering exactly to a structured schema and for refusing to extract relations that the evidence does not support — both relevant to our hallucination-suppression goal. The cost (~25 EUR over 25 iterations) is still inside budget. If the dominant Gen 1 risk is bad extracted edges, paying 5–8× for higher fidelity is defensible.

**Recommendation: Gemini 2.5 Flash Lite as default, with GPT-4o-mini and Claude Haiku 3.5 first-class alternatives behind the `LLMProvider` Protocol.**

The decisive factors, in order:

1. **Free tier removes the contributor onboarding friction.** A new contributor can clone the repo and run `theogony ingest` against the fixture without a credit card. None of the other two offer this.
2. **1 M context window is a hedge for PID-2** (sentence vs. document-level extraction, §3a). If we later switch to paragraph-level or chapter-level extraction, Gemini does not constrain us; GPT-4o-mini at 128 k starts to.
3. **Cost scales better past Gen 1.** The savings are noise at 25 iterations; they are real at 2 500 books in Gen 2.
4. **JSON-Schema quality is good enough for our fixed-vocabulary use case.** Where Gemini struggles is in open-ended schemas with many enums; ours has ~20 relation types and a closed set of node types. Tight schema, tight prompt, tight tests.

What is given up:

- **API stability margin.** We pin `google-genai` versions hard, write integration tests that exercise the JSON path, and accept a non-trivial chance of one mid-sprint SDK upgrade.
- **Marginal output quality vs. Haiku** on edge cases where the LLM should refuse rather than guess. Mitigation: the `evidence_span` field (§9.4) makes refusal observable post-hoc, and the `ExtractionAuditLog` (§2.5) makes it auditable.

The decision is reversible by env-var: `THEOGONY_LLM_PROVIDER=openai` swaps to GPT-4o-mini, `=anthropic` to Haiku. The contract suite for `LLMProvider` runs against all three (the latter two gated on optional API keys, allowed to be skipped in CI). If Gemini's JSON adherence proves untrustworthy on real Tibet-book extractions in Week 2, we switch defaults before Week 3 — the cost of switching is one config change, not a re-architecture.

A PHX ticket records that Gen 2 must re-evaluate this with empirical data on extraction quality (PHX-0027, see §7).

### 3.4 Wikidata alignment strategy

**A wrong Q-ID is worse than no Q-ID.** It pretends to provenance the system does not have. It misroutes the Hover-Lupe — a user clicking "Aufschnaiter" expecting Peter Aufschnaiter (Harrer's Tibet companion) but landing on a different person of the same surname is a data-integrity failure that contradicts PHILOSOPHY §3 ("Verification Over Authority"). For historical travel literature this risk is acute: many of Harrer's named persons are stub or absent in English Wikipedia, transliterated Tibetan and Indian place names are inconsistent across editions, and `wbsearchentities` ranking favours modern, populous entities over the historical correct match.

The v2 strategy (top-3 candidates → spaCy-type filter → LLM with sentence context) underestimates this. It will resolve "Aufschnaiter" to *some* Aufschnaiter, "Tibet" to the modern Tibet Autonomous Region, and "Lhasa" probably correctly but with low confidence margin against alternatives. v3 deepens the strategy at the cost of one component-size step (M → L in §2.5) and ~30 s additional ingest time.

**Five-stage pipeline.**

1. **Multi-language candidate gathering.** For each unique mention surface form, issue `wbsearchentities` queries in parallel for `language ∈ {en, de, fr, it}` (configurable; defaults chosen because they cover ~90 % of European-language travel literature in Project Gutenberg, plus German is decisive for an Austrian author like Aufschnaiter). Each language returns up to 10 candidates. The **intersection of Q-ID sets across languages** is a strong signal — an entity that surfaces under all four languages is highly likely to be canonical. The **union** is the broader candidate set for further filtering.

2. **Spelling normalisation and alias matching.** For each candidate Q, fetch its labels and aliases (`labels` + `aliases` fields, all four languages). Match the source mention against this combined alias set with exact match first, then case-folded, then whitespace-collapsed, then Unicode-normalised (NFKD without combining marks — handles "Uttar Kashi" ↔ "Uttarkashi", "Kämpa" ↔ "Khampa"). This reduces fuzzy-match noise that `wbsearchentities` ranking introduces.

3. **Type-pass filter.** For each remaining candidate, fetch `P31` (instance-of) via SPARQL in batch (one query per ~50 candidates: `VALUES ?q { Q1 Q2 Q3 ... } ?q wdt:P31 ?type`). Filter by the spaCy-NER tag mapped to acceptable Wikidata types (`PERSON → Q5`, `GPE → Q486972 ∪ Q515 ∪ Q6256 ∪ Q3024240`, `ORG → Q43229`, etc., with a documented mapping table in `extraction/wikidata_types.py`). Multiple acceptable types are OK — the filter excludes obvious mismatches (a `PERSON` mention resolving to a `Q486972 town`).

4. **Biographical-fact disambiguation.** When more than one candidate survives Stage 3, this is where v2 stopped and just asked the LLM. v3 instead **fetches a small biographical fingerprint** for each surviving candidate via one batched SPARQL query:

    | Property | Meaning | Why it disambiguates |
    |---|---|---|
    | `P569` | date of birth | "Aufschnaiter" born 1899 vs. another Aufschnaiter born 1950 |
    | `P570` | date of death | Period must overlap with the book's narrative time |
    | `P106` | occupation | Mountaineer/engineer/explorer vs. footballer of the same name |
    | `P19` | place of birth | German-Austrian space vs. Swiss vs. unrelated |
    | `P937` | work location | Tibet/India vs. unrelated |

    The book itself provides context: "Seven Years in Tibet" is set 1939–1951, in Tibet/India/Nepal, with German-speaking Austrian protagonists. We extract this context once at ingest start (a small structured prompt against the book's metadata + opening pages: "What time period is this book set in? What places? What kinds of people are central?"). The result is a `BookContext` Pydantic model passed into every disambiguation.

    The LLM is then asked the disambiguation with full evidence:

    ```text
    Mention: "Aufschnaiter"
    Source sentence: "After many days of climbing, Aufschnaiter and I reached..."
    Source: Gutenberg #944 ("Seven Years in Tibet"), set 1939-1951, in Tibet/India,
            German-speaking Austrian protagonists.

    Candidate Q-IDs with biographical facts:
      Q1: Q123456 — Peter Aufschnaiter
          born 1899 (Kitzbühel, AT), died 1973
          occupation: mountaineer, engineer, agronomist
          worked in: Tibet, Nepal
      Q2: Q789012 — Hans Aufschnaiter
          born 1950 (Munich, DE), died (alive)
          occupation: footballer
          worked in: Germany

    Which Q-ID best matches this mention, given the source context?
    Respond with one of:
      {"chosen": "Q123456", "confidence": 0.0–1.0, "reasoning": "..."}
      {"chosen": null, "confidence": 0.0–1.0, "reasoning": "..."}
    ```

    With this evidence, even a small model (Gemini 2.5 Flash Lite) reliably picks the right one.

5. **Detective Mode (opt-in, deeper reasoning).** For mentions the standard pipeline cannot resolve confidently (no candidate exceeds 0.6, or all are filtered out, or the mention surfaces in a high-stakes context flagged by the user), an opt-in `WikidataDetective` performs a deeper pass:

    - Fetches `P31`, `P735` (given name), `P734` (family name), `P31`, `P361` (part of), and `P527` (has part) for the top 5 candidates.
    - Fetches Wikipedia article first paragraph for each candidate (one HTTP call per candidate; cached).
    - Issues a longer-context LLM prompt asking specifically: "Given this surrounding paragraph from the source book, this list of Wikipedia first-paragraphs, these biographical fingerprints, which Q-ID is the correct match, or is none of them?"
    - Cost per Detective Mode call: ~5–10 cents (longer prompt, more candidates, Wikipedia round-trips). Time: ~5–10 s.

    Detective Mode is invoked: (a) when standard resolution returns confidence < 0.6 *and* the mention occurs ≥ 3 times in the book (signal that this entity matters), (b) on explicit `theogony ingest --detective <id>` flag, (c) on per-mention manual review trigger via CLI (`theogony resolve <mention>`).

**Five-tier confidence model.** Every resolved entity carries a `resolution_tier` integer 0–4 plus the existing `scores.confidence` float. The tier is recorded for audit and for downstream agents to weight evidence. Confidence values are heuristic anchors, not measured priors:

| Tier | Path | Confidence |
|---|---|---|
| 4 | Exact alias match in ≥ 2 languages, type-filter passes, unique candidate after Stages 1–3 | **0.90** |
| 3 | Type-filter passes but multiple candidates; disambiguated by alias + frequency, no LLM | **0.75** |
| 2 | LLM disambiguation **with** biographical facts and book context (Stage 4) | **0.65** |
| 1 | LLM disambiguation with sentence context only (no bio facts available, e.g. all candidates are stubs) | **0.55** |
| 0 | No Wikidata match — minted as `AKA-…` only | **0.50** |

Tiers 4 and 3 are eligible for promotion to Mneme (default `confidence_threshold = 0.65`). Tiers 0–2 require additional corroboration to be promoted. This is consistent with PHILOSOPHY §3 ("degrees of trust, computed from evidence") — a wrong Q-ID assigned at tier 1 is much cheaper to revise than one assigned at tier 4 because it never accumulates Mneme-level authority on its own.

**Honest failure.** When no candidate exceeds confidence 0.5 *and* Detective Mode is either disabled or also fails, the entity is recorded as:

```python
KnowledgeNode(
    id="AKA-…",                              # deterministic, see §9.5
    label="Aufschnaiter",
    external_ids={},                          # empty — no claim of Wikidata identity
    manual_resolution_needed=True,            # new field, see §9.6
    resolution_tier=0,
    scores=NodeScores(confidence=0.5, ...),   # neutral; no false certainty
    properties={
        "wikidata_search_attempted": True,
        "wikidata_candidates_considered": [...Q-IDs...],
        "wikidata_failure_reason": "all candidates failed type-filter",
    },
)
```

A new CLI command `theogony resolve` lists nodes with `manual_resolution_needed=True`, allows a human to pick a Q-ID, and updates the node. This is the explicit "future review will address them without polluting the graph" path Hesiod called for.

**Advocate (revised).**  
This pipeline burns ~10–15 s more per book than the v2 version, but reduces the wrong-Q-ID rate substantially on exactly the failure modes Hesiod identified — historical figures, transliterated names, stub-Wikipedia entities. Multi-language lookup catches the canonical Q for non-English entities (Aufschnaiter is Q-listed primarily under German). Bio-fact disambiguation gives the LLM enough evidence to refuse confidently. The five-tier model and `manual_resolution_needed` flag mean the graph never silently lies — every alignment is honest about its strength.

**Skeptic.**  
This is more code, more tests, and one more place where a network call can fail. SPARQL for bio-fact fetching reintroduces the very rate limit we tried to avoid in v2. Detective Mode is genuinely expensive (5–10 cents × dozens of cases per book = ~1–3 EUR per detective-mode book, on top of base extraction). The five-tier model is heuristic: the confidence numbers are guesses until measured.

**Counterview.**  
A radically simpler alternative: **no automatic Wikidata alignment at all in Gen 1**. Mint `AKA-…` for every mention, record the search candidates as `properties.wikidata_candidates`, ship the `theogony resolve` command, and let a human assign Q-IDs as the chronicle grows. This makes the system honest by default and treats Wikidata alignment as a human-in-the-loop activity — appropriate for a 4-week demo where the operator is also the developer.

**Recommendation.**  
**Implement the five-stage pipeline as proposed; do not adopt the radical counterview.** Reasons:

1. The whole point of Wikidata alignment is cross-source convergence (§3.4 v1 reasoning still holds). A demo where every entity is `AKA-…` cannot show that the same Heinrich Harrer would resolve from a hypothetical second source — and that demonstration is the point of the system, not a Gen 2 stretch goal.
2. The cost of getting it more right with bio-fact disambiguation is bounded (~1.5 days of work, ~10 s per book) and the cost of getting it wrong is unbounded (corrupted graph, broken Hover-Lupe, undermined trust).
3. The five-tier model is a *floor* of honesty. We may get the heuristic confidences subtly wrong, but they cannot be more wrong than v2's "0.7 for everything LLM-touched".

**SPARQL-rate-limit mitigation.** Bio-fact queries are batched: one SPARQL `VALUES { Q1 Q2 ... }` query for up to 50 candidates returns all five properties in one round trip. For 500 unique mentions with type-filter survival rate ~50 %, we expect ~5–10 SPARQL calls per book — comfortably inside the 60-req/min limit even before back-off.

**Detective Mode is opt-in.** The default `theogony ingest <id>` runs Stages 1–4 and tiers 4–0 via the standard path; Detective Mode (Stage 5) only runs with `--detective` or on per-mention re-resolution. This keeps the median ingest cheap.

**What is given up.**
- Speed: ~+10–15 s per book vs. v2.
- Cost: ~+0.01 EUR per book in extra LLM calls for Stage 4 (negligible). Detective Mode adds ~1–3 EUR if used.
- One additional moving part (SPARQL for bio facts) with one additional failure mode (rate-limit at high concurrency).

PHX tickets newly filed: PHX-0032 (cross-language entity coreference at scale), PHX-0033 (pre-curated Wikidata subset for travel literature to remove SPARQL dependency), PHX-0034 (entity-resolution quality benchmark). All target Gen 2.

### 3.5 Agent orchestration mechanism

**Proposal: Pure asyncio with `TaskGroup` (Python 3.11+). A simple in-memory `TaskLedger` (dict + `asyncio.Queue`) and an `EventBus` (topic → list of subscribers). No agent framework.**

**Advocate.**  
Gen 1 has three runtime workers: ingestion, query, Oneiros. They are async functions. They do not need a framework. asyncio is in the standard library, observable, debuggable, and the entire Python ecosystem already speaks it. `TaskGroup` gives structured concurrency with proper exception propagation. Adding LangGraph/CrewAI/AutoGen brings opinionated abstractions that obscure the data flow we are trying to reason about.

**Skeptic.**  
We will eventually want retries, circuit breakers, persistence of in-flight tasks, and DAG-style orchestration for the Pantheon. Building that ourselves is a tax. Frameworks have already paid that tax.

**Counterview.**  
LangGraph's stateful graph orchestration would map well to the Constellation-assembly process. CrewAI's role-based agents map well to the eventual Pantheon. Adopting one now means we don't pay a migration tax later.

**Recommendation.**  
**Plain asyncio for Gen 1.** The workload does not justify a framework. Frameworks impose vocabulary, ergonomics, and runtime that we would have to teach every contributor. We cannot evaluate which framework would actually serve the Pantheon until we have built enough of it to know what its real coordination patterns are. Adopting one now is choice-by-anxiety.

What is given up: free retries, free queue persistence. Mitigation: a 30-line `retry_with_backoff` helper, and the `TaskLedger` is just a dict — if it dies on restart, Gen 1 just re-queues from the CLI/API.

**Gen 2 must reopen this question.** By the time we have multiple ingestion strategies, real Oneiros workers running concurrently with operator queries, Hestia escalations interleaving with Phoenix planning, and prompt genomes resolving at task time, the actual coordination patterns of the Pantheon will be visible. At that point — and only at that point — we can compare what a framework would save us against what it would impose. The decision should be data-driven, not absent. PHX-0026 (Pantheon-as-Personas Refactor, §7) is the natural moment to revisit; the orchestration choice belongs in the same conversation.

### 3.6 Configuration and secret management

**Proposal: `pydantic-settings` for all configuration. `.env` for local development. Environment variables in production. Secrets never logged. No Vault/SecretManager integration in Gen 1.**

**Advocate.**  
`pydantic-settings` is a thin layer on the Pydantic we already use for data models. It handles env vars, `.env`, defaults, and validation in one place, with full type checking and docstrings. Secrets in env vars is the canonical 12-factor approach.

**Skeptic.**  
A real product uses a secret manager. Hardcoding env-var loading means we will have to refactor.

**Counterview.**  
For Gen 1 with one developer and a demo, anything more than `.env` is overhead.

**Recommendation.**  
**As proposed.** Add a `.env.example` with all keys and dummy values; `.env` is in `.gitignore` already. The only hard rule: a `Settings` instance is never logged whole. Secrets fields use `SecretStr`.

### 3.7 CLI design

**Proposal: Typer (already a dependency). Seven commands (one with two sub-commands).**

```text
theogony status                    health, layer sizes, configured providers
theogony ingest <id|url> [--detective] [--resume] [--restart]
                                   acquire → extract → store
theogony ask <question>            query → constellation → synthesized answer with citations
theogony node <id>                 show one node with its neighborhood (the Hover-Lupe)
theogony resolve [<mention>] [--list]
                                   review nodes with manual_resolution_needed=true;
                                   --list shows pending; <mention> opens an interactive
                                   resolution session that can call WikidataDetective
                                   and write back the chosen Q-ID
theogony reports list [--type=ingest|query|oneiros] [--last=N]
                                   list recent RunReports with run_id, type, verdict,
                                   duration; default last=20 across all types
theogony reports show <run_id>     pretty-print the JSON report for one run; if not
                                   found, list close matches by prefix
theogony serve [--host=...] [--port=...]   FastAPI via uvicorn
```

**Advocate.**  
These five commands cover the demonstration moment exactly. Typer gives clean help, autocompletion, and Pydantic-friendly type parsing.

**Skeptic.**  
`status` is operational, not user-facing. We do not need it for the demo.

**Counterview.**  
Click would be functionally equivalent and arguably more standard. Typer adds a layer.

**Recommendation.**  
**As proposed.** `status` is included because the first contributor cloning the repo will run it before doing anything else and they need to see what works and what does not. Typer over Click because Pydantic is already pervasive.

The CLI module satisfies the existing `pyproject.toml` declaration `theogony = "theogony.cli:app"` which currently points at nothing — that is a small but real defect.

### 3.8 Test strategy

**Proposal: Six layers, in this order of priority.**

1. **Pure unit tests** for `core/model.py`, `core/vitality.py`, embedding/LLM stubs, individual extractors. Fast, no I/O.
2. **Store contract suite** in `tests/test_store_contract.py`, parametrised with each `KnowledgeStore` implementation; `Neo4jKnowledgeStore` runs only when `TESTCONTAINERS_NEO4J=1` (default in CI, optional locally).
3. **Pipeline integration tests** with `StubLLMProvider` and a tiny fixture text (~20 sentences crafted to exercise NER, Wikidata alignment, relation extraction, and constellation assembly).
4. **API tests** with `httpx.AsyncClient` against an in-process FastAPI app, using `InMemoryKnowledgeStore`.
5. **End-to-end smoke** that ingests the small fixture, queries it, asserts the answer mentions the expected entities, marked `slow` and excluded from the default `pytest` run, included in CI under a separate job.
6. **Pipeline characterization** (added Etappe E7, see PHX-0034 stub-vorhut): one opt-in test that runs the full IngestionPipeline against a larger real-corpus slice (~300 narrative sentences, frontmatter-free) and asserts on **bands** rather than equalities — tier distribution, edge yield, wall-clock, LLM call count, materialised edge count. Calibrated once; bands are ±20% around the calibration. Gated by both `THEOGONY_RUN_CHARACTERIZATION=1` env var and the `@pytest.mark.characterization` marker so default `pytest` and CI never pay the ~0.15–0.25 EUR Gemini cost per run. Persisted JSON reports live under `docs/run_reports/characterization/<ulid>.json` (committed — they are documentation of the project's state, not runtime data). One slice, one test, no parametrisation: YAGNI until measurement says otherwise. Cross-provider comparison, gold-standard regression, and multi-slice runs are deferred.

**Tools.** `pytest`, `pytest-asyncio` (already configured), `respx` for HTTP mocking, `syrupy` for snapshot testing of Constellations, `testcontainers-python` for Neo4j, `hypothesis` for property tests on vitality math.

**Tooling not added.** Coverage gate (no minimum threshold in Gen 1; counterproductive to add before there is enough code to be meaningful). Mutation testing.

**Advocate.**  
Layered tests catch different failure modes at the right granularity. The store contract suite is the most important architectural test in the project: it forces every store to behave identically, which is the only thing that makes the protocol an actual contract rather than aspirational documentation.

**Skeptic.**  
testcontainers in CI adds 30–60 s to every PR. Snapshot tests on LLM-mediated outputs are fragile; they will fail spuriously when prompts change.

**Counterview.**  
Skip Neo4j integration in CI; rely on manual integration testing. Skip snapshot tests; assert structural properties of Constellations only.

**Recommendation.**  
**As proposed.** The 30 s in CI is worth the protection against silent backend regressions. Snapshot tests are restricted to the Constellation *structure* (node ids, edge shape, source refs) and not to LLM-synthesized prose; the synthesizer's tests use `StubLLMProvider` with deterministic scripted responses.

---

## 3a. Pre-Implementation Decisions

Two questions in v1 were filed as Open Questions to be resolved by Week 4 experiments. On review, both turned out to be data-model and pipeline-shape decisions: deferring them would leave the schema half-defined and the extraction pipeline unimplementable. They are resolved here, heuristically and explicitly, with the experiments that would later validate or overturn the choices.

These are not as carefully analysed as the §3 decisions. They are the cheapest defensible answers given current evidence, locked in to unblock implementation.

### PID-1: Atom granularity (sentence-level)

**Question.** Should a `KnowledgeNode` correspond to a sentence-scope mention, a clause, or a paragraph? This shapes `SourceRef.location`, the unit at which `RelationExtractor` operates, and the density of the resulting graph.

**Resolution: sentence-level mentions, sentence-level relations, sentence-level source spans.**

**Why.**
1. **Source anchoring is unambiguous at the sentence level.** A sentence has a clear start and end; a clause has fuzzy boundaries that depend on the parser; a paragraph spans multiple ideas.
2. **Sentences are the natural unit for spaCy.** The sentencizer is robust; clause segmentation in English is genuinely hard.
3. **Multi-sentence semantic structures emerge as edges, not as nodes.** "Harrer met the Marchese in Italy. They later traveled to India together" produces two nodes for Harrer/Marchese with a `MET` edge from sentence 1 and a `TRAVELED_TO` edge from sentence 2. The cross-sentence relation is captured by the *graph*, not by a giant paragraph node.
4. **Vitality is meaningful.** A sentence-scoped fact has a single source span, a single confidence, a single epistemic status. A paragraph-scoped fact aggregates over multiple, less interpretable.

**What is given up.**
- Information that exists *only* across sentences and *only* as a single proposition (rare in narrative; commoner in scientific argumentation). For Gen 1 we do not target scientific argumentation.
- The ability to search at "topic" granularity directly — that emerges from clusters in `cluster_id`, which is a Gen 2 concern.

**What would change the decision.**  
A measured loss of >20 % of "obvious" relations on the Tibet book due to sentence-boundary effects. Experiment: re-extract one chapter at paragraph granularity, count the relations the paragraph version captures that the sentence version misses, divided by total true relations from a hand-annotated reference. If the loss is large, switch to a hybrid — sentence-level by default, with a separate "cross-sentence" pass after embedding.

**Recorded in PHX-0030 (target Gen 2): atom-granularity ablation on multiple text genres** — narrative, scientific, normative, structural — to find whether one granularity fits all or whether `KnowledgeForm` should drive granularity selection.

### PID-2: Sentence-level vs. document-level relation extraction (sentence-level, with hybrid hook)

**Question.** Does `RelationExtractor` see one sentence at a time, or larger chunks (paragraph, chapter, whole book)?

**Resolution: one sentence per LLM call, with the *evidence span* allowed to widen across sentence boundaries when necessary.**

**Why.**
1. **Cost and parallelism.** Sentence-level extraction parallelises trivially across the full book at concurrency 8 (~2.5 min as in §4.1). Document-level extraction serialises by chapter and forces the model to find relations across hundreds of sentences in one prompt — slower, more expensive, more prone to drift.
2. **Hallucination control.** The smaller the input window, the smaller the surface on which the LLM can confabulate. Sentence-level is the most defensive default.
3. **Audit log granularity.** One audit log row per sentence is interpretable. One row per chapter with N relations is a debugging nightmare.
4. **Schema simplicity.** A sentence-scoped extraction has a clean shape: `subject ∈ mentions(sentence), object ∈ mentions(sentence), evidence_span ⊆ sentence`. A document-scoped extraction needs cross-sentence reference resolution, which is a research problem.

**The hybrid hook.** `RelationExtractor` accepts an `expand_window` parameter that, when set, includes the previous and next sentence as *context* in the prompt. The relation must still be extracted *about* the central sentence, and the `evidence_span` must still be a substring of the central sentence. This handles co-reference cases like "He reached the city" → previous sentence establishes "he" = Harrer. Default off in Gen 1; trivially flippable in Week 4 if quality demands.

**How the LLM knows which sentence is the central one.** Hesiod asked specifically. The mechanism is a structured prompt with three explicit named sections, not free-form prose. Concretely:

```text
You are extracting relations from one specific sentence. Two adjacent
sentences are provided ONLY for resolving pronouns and references. You
MUST NOT extract a relation whose evidence span lies outside the central
sentence.

PREVIOUS SENTENCE (context only — do not extract from this):
"He had been wandering for weeks, exhausted and hungry."

CENTRAL SENTENCE (extract relations FROM HERE):
"Harrer reached Uttarkashi at midnight."

NEXT SENTENCE (context only — do not extract from this):
"There he met the Marchese for the first time."

Return a JSON list of relations following the schema. For each relation,
the `evidence_span` field MUST be a substring of the CENTRAL SENTENCE
(not the previous or next).
```

Three reinforcing safeguards make this robust:

1. **Structural clarity in the prompt.** Three labelled sections with `(context only)` vs. `(extract from here)` annotations are unambiguous. We do not rely on the model inferring centrality from position.
2. **Schema enforcement.** The Pydantic model for an extracted relation contains `evidence_span: str`. After parsing, the pipeline asserts `evidence_span in central_sentence_text` (substring check, after the same Unicode normalisation used in §3.4 alias matching). On failure, the relation is **dropped** and the violation is recorded in `ExtractionAuditLog` with `parse_error = "evidence_span outside central sentence"`. This catches drift even when the prompt fails to constrain the model.
3. **Audit-log signal.** A spike in `parse_error = "evidence_span outside central sentence"` is the signal to either tighten the prompt or disable `expand_window`. The existence of this signal makes the experiment cheap to run and cheap to roll back.

When `expand_window=False` (Gen 1 default), the prompt is single-sentence:

```text
Extract relations from this sentence:
"Harrer reached Uttarkashi at midnight."

Return a JSON list following the schema. The `evidence_span` for each
relation MUST be a substring of the sentence above.
```

The same substring assertion applies. The single-sentence path is what we ship in Week 2; the expanded path is implementable in ~4 hours and can be enabled by config flag in Week 4 if PID-2 measurement justifies it.

**What is given up.**
- Relations that genuinely span sentences and have no individual sentence that justifies them on its own. Example: "Harrer met the Marchese. The two of them later traveled to India." → the `TRAVELED_TO` from Harrer to India is justified by sentence 2 alone (with co-reference); a relation like `MET` between Harrer and the Marchese in *Italy* requires both sentences. Neither is currently captured cleanly without the hybrid hook.
- Discourse-level structure (causality, contrast, narrative arcs) that only emerges at paragraph scale.

**What would change the decision.**  
If a hand-annotated reference shows >30 % of relations require cross-sentence context, flip `expand_window` on by default for Gen 1.1, and file a Gen 2 ticket for proper document-scoped extraction with co-reference resolution.

**Recorded in PHX-0031 (target Gen 2): document-level extraction with co-reference resolution and discourse parsing.**

These two decisions together define: one node per (sentence, mention), one edge per (sentence, relation), one audit row per LLM call, one source span per sentence. The data model is now closed for Gen 1. Implementation can begin.

---

## 4. Data Flow Diagrams

### 4.1 Ingest flow

```text
                                                                    ┌──────────────┐
CLI/API: theogony ingest 944                                        │  Wikidata    │
        │                                                           │  SPARQL +    │
        ▼                                                           │  search API  │
┌──────────────────┐    ┌──────────────────┐   ┌──────────────────┐ └──────┬───────┘
│ IngestionPipeline│───▶│ GutenbergAdapter │──▶│   RawContent     │        │
└────────┬─────────┘    └──────────────────┘   └────────┬─────────┘        │
         │                                              │                  │
         │              ┌──────────────────┐            ▼                  │
         │              │  TextCleaner     │◀───────────┘                  │
         │              └────────┬─────────┘                               │
         │                       │ CleanedContent                          │
         │              ┌────────▼─────────┐                               │
         │              │  Sentencizer     │                               │
         │              └────────┬─────────┘                               │
         │                       │ list[Sentence]                          │
         │              ┌────────▼─────────┐                               │
         │              │  NerExtractor    │                               │
         │              └────────┬─────────┘                               │
         │                       │ list[Mention]                           │
         │              ┌────────▼─────────┐                               │
         │              │ EntityResolver   │◀──────────────────────────────┘
         │              └────────┬─────────┘
         │                       │ list[ResolvedEntity]   (Q-id or AKA-id)
         │              ┌────────▼─────────┐    ┌──────────────────┐
         │              │RelationExtractor │───▶│  LLMProvider     │
         │              └────────┬─────────┘    └──────────────────┘
         │                       │ list[ExtractedRelation]
         │              ┌────────▼─────────┐    ┌──────────────────┐
         │              │   Embedder       │───▶│  embedding model │
         │              └────────┬─────────┘    └──────────────────┘
         │                       │ KnowledgeNode + KnowledgeEdge (in EPHEMERA)
         │              ┌────────▼─────────┐
         └─────────────▶│  KnowledgeStore  │ (Neo4j)
                        └──────────────────┘
```

Concrete numbers for "Seven Years in Tibet" (Gutenberg #944, ~110 k words), v3 (after §3.4 v3 deeper Wikidata pipeline):

- Acquisition: 1 HTTPS request, ~2 s
- Cleaning + sentencizing: ~5 s (local)
- NER on ~5 000 sentences: ~30 s (spaCy CPU)
- **BookContextExtractor:** one LLM call against book metadata + first chapter, ~2 s.
- **Entity resolution (v3, deeper pipeline per §3.4):**
  - Unique-mention deduplication: ~500 distinct strings.
  - Stage 1 multi-language `wbsearchentities` (4 languages × 500 mentions, parallelised at concurrency 8 across the 2 000-call cross-product): ~25 s API time.
  - Stage 2 alias matching: local, <1 s.
  - Stage 3 type-pass SPARQL (batched, ~10 queries of 50 candidates each): ~15 s.
  - Stage 4 bio-fact disambiguation SPARQL (batched, ~5 queries): ~10 s; LLM disambiguation for ~50 cases (10 % of mentions remain ambiguous after Stage 3) at concurrency 8: ~10 s and ~0.01 EUR.
  - Stage 5 Detective Mode: **off by default**; not in default ingest timing.
  - **Total entity resolution: ~60–90 s.** Up from ~30–45 s in v2; still well below v1's 8 min.
- Relation extraction: ~3 000 sentences with mentions × LLM call. With concurrency 8 against Gemini 2.5 Flash Lite (p50 ~1 s with parallelism amortising): **~2.5 min, ~0.12 EUR**.
- Embedding: ~2 000 nodes × BGE-small batch 64: ~30 s
- Store writes: ~2 000 node upserts + ~3 000 edge upserts in batches of 500: ~10 s in Neo4j

**Total: ~5–6 min wall-clock, ~0.13 EUR per book** (default ingest, no Detective Mode). With Detective Mode on for the ~5 % low-confidence cases (~25 mentions, ~7 s and ~$0.05 each): **~+3 min and ~+1.30 EUR**. Both well under Hesiod's 6-min target for the default path; explicit opt-in required for the deeper case.

Caveats:
- The 150 ms / `wbsearchentities` request assumes a warm DNS and a non-throttled endpoint. On a cold morning from EU to Wikimedia datacentre, the first 20 requests can be 500 ms each. The retry/backoff in §3.4 handles `503/429`.
- The four-language cross-product is 2 000 requests; Wikimedia tolerates this with `User-Agent` and `maxlag=5`. In practice the per-language cache hit rate after the first language is ~30 % (the same Q-ID surfaces under multiple languages), so effective request count is closer to ~1 400.
- Bio-fact SPARQL is the new external dependency. Worst case under rate-limit pressure: ingest stretches to ~7 min. Still acceptable; flag as a watch item for the demo run.
- The 25-iteration cost across all extraction is now ~3.25 EUR (default) or ~36 EUR (with Detective Mode every run, which would be unusual). Both inside the development budget headroom.

### 4.2 Query flow

```text
CLI/API: theogony ask "Welche Ethnien beschreibt Harrer..."
        │
        ▼
┌──────────────────┐
│  QueryPipeline   │
└────────┬─────────┘
         │
         │  ┌──────────────────┐
         ├─▶│   Embedder       │  → query_embedding (384 dim)
         │  └──────────────────┘
         │
         │  ┌──────────────────┐                       ┌─────────────┐
         ├─▶│ MultiHopRetriever├──────multi_hop_search▶│ Knowledge   │
         │  │                  │◀─────list[ScoredNode]─│   Store     │
         │  └──────────────────┘                       └─────────────┘
         │           │ k=10 seeds, hops=2, min_weight=0.3
         │           │ → ~30–60 nodes after dedup
         │           ▼
         │  ┌──────────────────┐
         ├─▶│  Constellation   │  collects edges between hits, source refs,
         │  │   Assembler      │  marks weak/missing as gaps
         │  └────────┬─────────┘
         │           │
         │           ▼
         │       Constellation
         │           │
         │  ┌────────▼─────────┐    ┌──────────────────┐
         └─▶│AnswerSynthesizer │───▶│  LLMProvider     │
            └────────┬─────────┘    └──────────────────┘
                     │
                     ▼
        ┌─────────────────────────────┐
        │ Answer + Constellation +    │
        │ list of cited node ids      │
        └─────────────────────────────┘
                     │
                     ▼
              RelevanceTracker
                     │
                     ▼
        bumps last_accessed, relevance,
        triggers OneirosWorker re-eval on next tick
```

Latency target: under 5 seconds end-to-end on the demo machine.

- Embed query: <50 ms (BGE-small, single sentence)
- Multi-hop search in Neo4j (vector + 2-hop traverse): ~100–500 ms for our scale
- Constellation assembly (edge enrichment, gap detection): <100 ms
- LLM synthesis (Gemini 2.5 Flash Lite default, ~1500 input + 500 output tokens): ~1.5–3 s p50, comfortably inside the 5 s target with headroom

### 4.3 Write-back

The genesis log emphasises that the system must improve with use. In Gen 1 the loop is minimal but real:

```text
After AnswerSynthesizer returns:
  for node_id in answer.cited_node_ids:
    RelevanceTracker.bump(node_id)   # last_accessed = now, relevance += δ

Every 60 s (OneirosWorker):
  for node in store.export_layer(EPHEMERA):
    recompute(connectivity)              # from edge count
    recompute(freshness)                 # time-decay
    recompute(vitality)                  # weighted sum
    if promotion_ready(node):
      store.promote(node.id)             # EPHEMERA → MNEME

  for node in store.export_layer(MNEME):
    if node.vitality < dynamic_threshold():
      store.degrade(node.id)
```

There is no inference (PHX-0004), no association beyond what extraction produced, no contradiction detection, no Athene.

What this proves: the lifecycle exists, the layer transitions work, vitality matters. That is enough for Gen 1. Anything more is YAGNI.

### 4.4 `serve` lifecycle

`theogony serve` runs `uvicorn` against `api.app:app`. The FastAPI `lifespan` context manager owns the lifetimes of every long-lived resource. Concretely:

```text
startup (in lifespan, before first request is accepted):
  settings = Settings()                              # validates env
  store    = await build_store(settings)             # opens Neo4j driver pool
  embedder = build_embedder(settings)                # loads BGE-small into RAM
  llm      = build_llm_provider(settings)            # opens HTTP client
  audit    = open_audit_log(settings)
  oneiros  = OneirosWorker(store, settings)
  app.state.{store, embedder, llm, audit, oneiros}
  app.state.oneiros_task = asyncio.create_task(oneiros.run())

  yield

shutdown (lifespan exit, triggered by SIGTERM/SIGINT/SIGHUP via uvicorn):
  app.state.oneiros_task.cancel()
  await asyncio.wait({app.state.oneiros_task}, timeout=5.0)   # graceful

  # in-flight requests: cancelled by uvicorn after timeout_graceful_shutdown
  # in-flight LLM calls inside cancelled requests: each provider client is
  # invoked via `async with asyncio.timeout(settings.llm_timeout_s)` (default 30 s),
  # so cancellation propagates and the provider HTTP client closes its sockets

  await app.state.store.close()                      # releases Neo4j pool
  await app.state.llm.aclose()
  app.state.audit.close()
```

**Signals.** `uvicorn` translates `SIGTERM` and `SIGINT` into `lifespan` shutdown. The CLI invokes `uvicorn.Server.serve()` directly (no `run()` wrapper) so that `Ctrl-C` in the terminal triggers the same path. The shutdown grace period defaults to 10 s (`uvicorn --timeout-graceful-shutdown 10`); long enough for in-flight queries to complete or be cleanly cancelled.

**In-flight LLM calls.** Every provider call inside `RelationExtractor`, `EntityResolver` (LLM disambiguation), and `AnswerSynthesizer` is wrapped in `asyncio.timeout(settings.llm_timeout_s)`. On request cancellation (client disconnect or shutdown), the timeout context is exited cleanly, the underlying HTTP client receives `aclose()`, and no zombie sockets remain. Failed requests are logged but do not block shutdown.

**OneirosWorker shutdown.** The worker's main loop is structured as:

```python
while True:
    try:
        await self._tick()
    except asyncio.CancelledError:
        break
    await asyncio.sleep(self.tick_interval_s)
```

This guarantees the worker stops between ticks and never inside the middle of a Cypher transaction.

**Test.** A unit test mounts `app` via `httpx.AsyncClient`, makes one slow `/query` call (with `StubLLMProvider` configured to delay 200 ms), then calls the lifespan exit, then asserts that the response either completes or surfaces a clean `asyncio.CancelledError` rather than hanging.

---

## 5. Milestone Plan

Four weekly milestones. Each is independently demonstrable to a critical observer. The Week 4 demonstration is the demonstration moment from §1.

### Week 1 — Foundation

**Goal:** the project builds, tests run green on CI, configuration loads from `.env`, the in-memory store passes the protocol contract, the embedding and LLM providers work behind their interfaces, the CLI shell exists.

**Deliverables.**
- `config/settings.py` with `pydantic-settings` and `.env.example`.
- `stores/memory.py` — `InMemoryKnowledgeStore` implementing the full `KnowledgeStore` Protocol.
- `tests/test_store_contract.py` — parametrised contract suite, passing for `InMemoryKnowledgeStore`.
- `extraction/embedding.py` — `EmbeddingProvider` Protocol + `LocalSentenceTransformerEmbedder` (BGE-small).
- `agents/llm.py`, `agents/llm_gemini.py` (default), `agents/llm_stub.py` — `LLMProvider` Protocol + two implementations. `agents/llm_openai.py` and `agents/llm_anthropic.py` follow as stretch goals if time permits in Week 1.
- `reporting/models.py` — three Pydantic schemas (`IngestRunReport`, `QueryRunReport`, `OneirosTickReport`) plus `RunReportBase`. (S, §2.11)
- `reporting/writer.py` — `RunReportWriter` with atomic JSON write. (S, §2.11)
- `cli.py` — Typer skeleton with `status` working.
- CI updated to install `[dev]` extras only (sentence-transformers + spaCy on every CI run is slow; cache aggressively).

**Success criteria (verifiable).**
- `pytest tests/` returns green; new tests cover store contract and embedding round-trip.
- `theogony status` prints provider configuration, embedding model id, store backend.
- A fresh clone followed by `pip install -e ".[dev]"`, `python -m spacy download en_core_web_sm`, then a first `pytest` completes in **under ~10 min on a developer laptop with a reasonable network connection**. Subsequent `pytest` runs (warm pip cache, spaCy model already downloaded, BGE-small weights cached) complete in **under 30 s**. The first-run cost is dominated by sentence-transformers fetching ~33 MB of BGE-small weights from Hugging Face on first import, the spaCy model download (~12 MB), and pip resolving the dependency tree against PyPI.

**Risks.**
- spaCy / sentence-transformers model downloads on first install. Mitigation: lazy load, document the explicit `python -m spacy download en_core_web_sm` step in the README quickstart, and pre-warm in CI by caching `~/.cache/huggingface` and the spaCy model directory between jobs.
- Hugging Face Hub being unreachable (rate limits, regional issues). Mitigation: document the `HF_HOME` env var so contributors can point at a local mirror, and ensure all model loads degrade with a clear error message rather than a stack trace.

### Week 2 — Ingest path

**Goal:** ingest a small fixture text end-to-end into `InMemoryKnowledgeStore`, with full provenance, the v3 §3.4 multi-stage Wikidata alignment, and honest-failure handling.

**Deliverables.**
- `acquisition/base.py`, `acquisition/gutenberg.py`.
- `extraction/{clean,sentence,ner,resolve,relations,book_context,detective,audit,ingest_run,pipeline}.py`.
- `extraction/wikidata_types.py` — the spaCy-NER-tag → Wikidata-type mapping table (§3.4 Stage 3).
- `IngestionPipeline._finalize_report()` populated from accumulated stage observations; emits `IngestRunReport` JSON to `data/run_reports/ingest/`. (S, §2.11)
- `reporting/anomaly.py` — the four anomaly rules from §2.11.2 (`stage_slow`, `cost_spike`, `wikidata_failure_burst`, `embedding_skew`). (S, §2.11)
- A small fixture: ~30 sentences of public-domain prose containing 4–5 known entities, deliberately including: at least one entity that needs multi-language disambiguation (e.g. a German-named person), one whose top `wbsearchentities` candidate is wrong (so Stage 4 has to override), one with no Wikidata match at all (so the honest-failure path is exercised).
- `theogony ingest <id>` working against `InMemoryKnowledgeStore`.
- `theogony resolve --list` working: shows fixture nodes flagged `manual_resolution_needed=true`.

**Success criteria.**
- `theogony ingest <fixture-id>` in <60 s produces ≥ 20 nodes, ≥ 10 edges, every node carries a `SourceRef`, every Wikidata-aligned node carries a `resolution_tier`, at least 1 node carries `manual_resolution_needed=true`, no untyped nodes, no edges with `source_id == target_id`, `evidence_span` present and substring-validated on every edge.
- Integration test exercises every tier (4, 3, 2, 1, 0) at least once on the fixture.
- The `ExtractionAuditLog` contains one row per LLM call.

**Risks.**
- Wikidata SPARQL endpoint flakiness. Mitigation: cache, retry with exponential backoff, golden-fixture tests do not hit network.
- LLM API key unavailable for some contributors. Mitigation: `StubLLMProvider` with scripted responses keyed to fixture sentences; `ingest` can run with stub for development.
- Detective Mode is a new component touching multiple subsystems (Wikipedia HTTP, longer LLM prompts). Mitigation: build it last in Week 2 with `--detective` opt-in; if it slips to Week 3, the default ingest still works and Hesiod can verify the demonstration moment without it.

### Week 3 — Retrieval and Neo4j

**Goal:** the same ingest works against Neo4j, queries return Constellations, the CLI synthesizes answers.

**Deliverables.**
- `stores/neo4j_store.py` — `Neo4jKnowledgeStore`, full Protocol, contract suite green.
- `retrieval/multi_hop.py`, `retrieval/constellation.py`, `retrieval/synthesize.py`, `retrieval/pipeline.py`.
- `api/app.py` with `/ingest`, `/query`, `/node/{id}`, `/health`.
- `QueryPipeline._finalize_report()` populated; emits `QueryRunReport` JSON to `data/run_reports/query/`. (S, §2.11)
- `OneirosWorker._finalize_report()` populated; emits one `OneirosTickReport` per tick to `data/run_reports/oneiros/`. Cap retention at 100 most recent ticks via `RunReportWriter` to prevent disk bloat (the audit log is the long-term record). (S, §2.11)
- `theogony ask`, `theogony node`, `theogony serve` working.
- `testcontainers-python` integration in CI for Neo4j tests (with caching; should add ~60 s to CI).

**Success criteria.**
- The Week 2 fixture, ingested into Neo4j via `theogony ingest`, answers a known question with a Constellation containing the expected entities.
- The contract suite passes for `Neo4jKnowledgeStore`.
- `curl -X POST localhost:8000/query -d '{"q":"..."}'` returns JSON with answer + constellation.
- Query latency p95 < 2 s on the fixture.
- A `QueryRunReport` JSON file exists for every `theogony ask` invocation; an `OneirosTickReport` exists for at least the most recent worker tick.

**Risks.**
- Neo4j vector index quirks with our embedding dimensions. Mitigation: build the index once at first use; warm-up step in `theogony status`.
- Cypher mistakes in `multi_hop_search`. Mitigation: contract suite + a small set of hand-crafted Cypher unit tests with golden fixture data.

### Week 4 — Demonstration

**Goal:** ingest "Seven Years in Tibet" in full, run the demonstration moment from §1 reliably, ship documentation.

**Deliverables.**
- Full ingest of Gutenberg #944.
- `memory/oneiros.py` and `memory/relevance.py` — minimal worker active in `theogony serve`.
- `agents/hestia.py` — `HestiaReview` Pydantic schema.
- `prompts/hestia_sentinel.md`, `prompts/hestia_auditor.md`.
- `prompts/daedalus.md` already exists; we leave it.
- `theogony reports list` and `theogony reports show <run_id>` working end-to-end against the report directories. (S, §2.11)
- README quickstart updated to reflect the demo sequence.
- `docs/IMPLEMENTATION_PLAN_GEN1.md` (this document) updated with what actually shipped.
- Phoenix Backlog tickets filed for every deferral (see §7).
- A 5-minute screen recording of the demo, archived.

**Success criteria — the demonstration moment.**
1. Cold start: `docker compose up neo4j` (or local Neo4j), `theogony serve &`.
2. `theogony ingest 944` completes in under 10 minutes (default path; under 15 min with `--detective`), costs under 0.20 EUR in API calls (default; under 1.50 EUR with `--detective`).
3. After ingest, the store contains roughly 1 500–2 500 nodes and 2 500–4 000 edges. Resolution-tier distribution is reported by `theogony status` and shows a non-trivial number of tier-0 nodes (the system is honest about what it could not align).
4. The query in §1 returns a coherent answer in under 5 s, with at least 3 cited nodes whose source refs point to verifiable passages of the book.
5. `theogony node <id>` for any cited node shows its neighborhood; the user can step into a connected node and continue exploration (Hover-Lupe). The node display shows `resolution_tier` and `external_ids`, so the user can see whether this node is canonically anchored or AKA-only.
6. `theogony resolve --list` shows a non-empty list of nodes pending manual resolution; `theogony resolve <mention>` for one of them allows interactive Q-ID assignment (or running `--detective` against it).
7. The system survives 10 consecutive queries without crash, without leaking embeddings into the LLM context, and with Neo4j RAM stable under 4 GB.
8. `theogony reports list` shows one `IngestRunReport`, ten `QueryRunReport`s, and a recent `OneirosTickReport`, each with a `verdict` and `verdict_reasoning`. `theogony reports show <ingest-run-id>` pretty-prints the JSON; the demo audience can read the system's own self-assessment of the ingest. (This proves the agent-readable retrospective layer exists and works, which is the prerequisite for the future Reviewer agent.)

If this demo runs in front of a critical observer and they walk away saying "I see what this is", Generation 1 is done.

---

## 6. Open Questions

These cannot be decided without prototyping. Each is paired with the experiment that would resolve it.

**Note on numbering.** v1 contained OQ-1 (atom granularity) and OQ-5 (sentence vs. document-level extraction). Both turned out to constrain the data model and pipeline shape too tightly to defer. They have been moved to §3a (Pre-Implementation Decisions) as PID-1 and PID-2 and resolved heuristically with explicit reasoning. The remaining OQ numbers (2, 3, 4, 6) are kept stable for reference; OQ-1 and OQ-5 simply do not appear here. OQ-7 is new in v2.

### OQ-2: Aggressiveness of Oneiros

How often should the worker tick? Every 10 s, 60 s, 5 min? More frequent = faster promotion + more compute. With one book and ~2 000 nodes, the question is small. With many books it is not.

**Experiment (deferred to Gen 2):** track promotion lag distribution and CPU as a function of tick interval. Tune for p95 promotion lag < 5 min at 10 % CPU.

### OQ-3: Embedding dimensionality

384 (BGE-small) vs. 1024 (gte-large) vs. 1536 (OpenAI 3-small). Higher dimensions buy ~5–10 points on retrieval benchmarks at the cost of 4× storage and 2–4× index time.

**Experiment (Gen 1 stretch goal):** ingest the fixture book with both BGE-small and gte-large; run 10 fixed queries against each; compare top-k overlap and human-rated answer quality.  
**Decision:** if gte-large produces meaningfully better Constellations, switch default. PHX-0005 already records that the model id is a per-node property, so a future re-embedding is supported by design.

### OQ-4: LLM provider lock-in vs. pluggability cost

Resolved partially in v2 §3.3a (default Gemini 2.5 Flash Lite, three providers behind `LLMProvider`). The remaining open question is empirical: **which provider produces the highest fraction of relations that survive Athene-style verification**, once Athene exists? That is a Gen 2 measurement.

**Experiment (Gen 2):** on a fixed corpus, run extraction with each provider; verify each extracted relation with a second-pass LLM call against the source sentence; compare survival rates. Cost: ~3× single-pass extraction.

### OQ-6: Hallucination detection in extracted relations

Even with strict JSON schema and evidence-span requirements, LLMs invent. We have no automated detector for "this relation is not actually supported by this evidence span".

**Status (re-examined in v3 round 2): stays deferred to Gen 2 for relation extraction. Partially addressed in Gen 1 *specifically for Wikidata alignment* by §3.4's five-tier confidence model + Detective Mode + `manual_resolution_needed` flag.**

Hesiod asked whether OQ-6 should partially move to Gen 1 specifically for Wikidata alignment, since a wrong Q-ID is exactly the silent corruption Athene exists to prevent. The answer is: **the work has already been done — under a different name.**

The §3.4 v3 pipeline is structurally an Athene-light specialised for entity resolution:

| Athene's role | Where §3.4 v3 already does it |
|---|---|
| Verify a claim against evidence | Stage 4 LLM disambiguation requires biographical facts that match the source context; the schema forbids "yes" without `chosen` and `confidence` fields |
| Score confidence | Five-tier `resolution_tier` with explicit numeric anchors per tier |
| Detect bias | Multi-language candidate gathering reduces English-Wikipedia bias toward modern entities |
| Refuse when evidence is weak | `chosen: null` is a first-class outcome; surfaces as `manual_resolution_needed=true` |
| Leave a paper trail | Every disambiguation call is in `ExtractionAuditLog` (§2.5); every node carries its tier and properties record candidates considered |

Promoting this to a separate `WikidataVerifier` agent class would be redundant in Gen 1: it would do the same SPARQL fetches, the same LLM call, and arrive at the same `(Q-ID | null, confidence, reasoning)` triple. Naming it Athene would communicate intent better, but it would also commit us to building the agent-class machinery that §7 explicitly defers (PHX-0026).

**Why the relation-extraction half stays deferred.** Verifying every extracted relation with a second LLM call is qualitatively different work:

- **Cost.** Relation extraction is ~3 000 LLM calls per book. A verification pass roughly doubles this — from ~0.12 EUR to ~0.24 EUR per book. Inside budget, but a real cost.
- **Schema.** Relation verification needs a different prompt structure ("does this evidence span justify this relation?" rather than "extract relations"), a different parser, and its own audit trail. That is a non-trivial additional component for Gen 1.
- **Risk asymmetry is different.** A wrong Q-ID corrupts the *identity* layer of the chronicle — every future ingest mentioning the same entity will compound the error. A wrong relation corrupts a single edge — destructive but local. Wikidata alignment errors are leveraged; relation errors are not. This is why the entity-resolution work is justified now and the relation-verification work is not.
- **The `evidence_span` field (§9.4) is itself a hallucination-detection lever** that does not require a second LLM call. Any reviewer (human or future Athene) can inspect a relation and the cited substring side by side. That is enough discipline for Gen 1.

**What changes the answer.** If a Gen 1 measurement (e.g. hand-annotating a chapter and checking extracted-relation precision) finds extraction precision below ~0.85, that is the trigger to bring relation verification forward to Gen 1.5 rather than waiting for Gen 2. PHX-0027 (LLM provider re-evaluation) is the right ticket to bundle this measurement with.

**Experiment (Gen 2 unless triggered earlier):** stand up the relation-extraction half of Athene as a second LLM call: "does the evidence span justify this relation?" yes/no with reasoning. Cost: ~doubles relation extraction. Reduces hallucination rate by an unknown amount; needs measurement. The `ExtractionAuditLog` (§2.5) gives Athene the full data set it needs.

### OQ-7: Resumable ingest

A 4–5-min ingest from §4.1 is short, but Murphy's Law applies: a crash at minute 4 of an LLM-extraction loop must not require restarting from minute 0. Three sub-questions need answers before we write the pipeline:

1. **At what granularity do we checkpoint?**
2. **Where is progress persisted?**
3. **How do we make individual operations safe to re-run?**

**Recommendation for Gen 1 (minimal, ship-able).**

*Granularity: stage-level.* Eight stages, each commits a checkpoint atomically:
`acquired → cleaned → sentencized → mentions_extracted → mentions_resolved → relations_extracted → embedded → stored`.
Per-sentence checkpointing is overkill for Gen 1 — restarting one stage costs at most ~30 s. Per-chapter is too coarse — many stages are global (NER over all sentences, embedding batches across the whole book).

*Persistence: a `data/ingest_runs.sqlite` database.* One table `ingest_runs` (run_id PK, source_type, source_identifier, llm_provider, llm_model_id, embedding_model_id, started_at, updated_at, last_completed_stage, status enum: `running | completed | failed | aborted`). Same SQLite engine as `ExtractionAuditLog` — could even share the file; kept separate for clarity. The `run_id` is the FK that the audit log already uses (§2.5).

*Idempotence: deterministic node and edge IDs.* In v1, `KnowledgeNode.id` defaulted to `AKA-{uuid4().hex[:12]}`, which makes every re-run produce different IDs and thus duplicates on retry. **Change for v2 (recorded in §9.5): node IDs are deterministic** — `AKA-` + first 12 hex chars of `sha256(f"{source_type}:{source_identifier}:{location}:{normalised_label}")`. Edge IDs are deterministic over `(source_id, target_id, relation_type)` plus a disambiguator if the same triple appears in different evidence spans. `KnowledgeStore.upsert_node` becomes truly idempotent: re-ingesting the same sentence is a no-op.

*Resume protocol.*
- `theogony ingest <id>` on a source with an existing `running` or `failed` run: prompt the user with `Resume? [Y/n]`. With `--resume` flag: skip prompt and resume. With `--restart`: mark old run as `aborted`, start new.
- Resuming reads `last_completed_stage`, sets the pipeline cursor, runs only the remaining stages. The interrupted stage runs from scratch; idempotent upserts absorb the duplicates.
- On normal completion: `status = completed`, `last_completed_stage = stored`.

**What this does not solve.** A crash mid-stage in the LLM-relation step still re-runs every sentence in that stage on resume — the LLM is called again for every sentence the first run already processed. Cost: ~1.50 EUR worst case (one full re-extraction). Acceptable. Per-sentence resume inside a stage is recorded as a Gen 2 concern (PHX-0029, §7).

**Test strategy.** A unit test runs `IngestionPipeline` against `InMemoryKnowledgeStore` with `StubLLMProvider`, simulates a `KeyboardInterrupt` after `mentions_resolved`, calls resume, and asserts: (1) stages 1–5 are not re-executed (mock counters), (2) the final node and edge sets are identical to a clean run, (3) the audit log contains rows from both runs.

**Component impact.** This adds an `IngestRunStore` (very thin) to §2.5 and a small `--resume` / `--restart` surface to the CLI in §2.8. Both are sized **S**.

---

## 7. What We Are Deliberately NOT Building in Gen 1

For each deferred capability, the Phoenix Backlog ticket that records it. Where no existing ticket covers the deferral, I propose a new one.

| Deferred capability | Existing PHX ticket | Action |
|---|---|---|
| Lethe Vaults, multi-tenancy, Hades | none | **File PHX-0021: Lethe Vaults & Hades** (target Gen 2) |
| Phoenix process (export/distill/rebuild) | implied in `ARCHITECTURE.md`; no ticket | **File PHX-0022: Phoenix Process Implementation** (target Gen 2) |
| Activation Engine / spreading activation | implied in `DEEP_TECH_VISION.md`; no ticket | **File PHX-0023: Activation Engine** (target Gen 2–3) |
| Self-hosted Wikidata mirror | none | **File PHX-0024: Self-hosted Wikidata Subset for Bulk Ingest** (target Gen 2) |
| Source Lake / Chronicle Ledger (append-only) | implied in `DEEP_TECH_VISION.md`; no ticket | **File PHX-0025: Source Lake and Chronicle Ledger** (target Gen 2) |
| Multi-Embedding Fabric | PHX-0002 | covered |
| Federated Chronik | PHX-0003 | covered |
| Crystallized Inference | PHX-0004 | covered |
| Embedding model independence (full re-embedding) | PHX-0005 | partially delivered (model-id stored); migration tooling deferred |
| Federated Compute | PHX-0006 | covered |
| Scientific Workbench | PHX-0007 | covered |
| Multi-Language Knowledge Bridging | PHX-0008 | covered |
| Vitality function tuning | PHX-0009 | partially delivered (defaults are heuristic); empirical tuning deferred |
| Physical Library Acquisition | PHX-0010 | covered |
| Knowledge Condensation at Scale | PHX-0011 | covered |
| Cost Accounting and Credit System | PHX-0012 | covered |
| Chronese as standalone language | PHX-0013 | covered |
| Metis advisory runtime | PHX-0014 | covered |
| Fast/Slow Cognition + Opposition Protocol | PHX-0015 | covered |
| Non-Chronological Knowledge Topologies | PHX-0016 | covered |
| Sensorium / multimodal acquisition | PHX-0017 | covered |
| Hardware co-design | PHX-0018 | covered |
| Hestia full runtime | PHX-0019 | partially delivered (schema + prompts only) |
| Operative Knowledge | PHX-0020 | covered |

**The Pantheon as personas.** No `Argus`, `Jason`, `Iris`, `Prometheus`, `Athene`, `Chronos`, `Morpheus`, `Hades`, `Helios`, `Zeus`, `Metis`, `Kalypso`, `Poseidon`, `Hermes` runtime classes in Gen 1. The functional substrate is named directly: `IngestionPipeline`, `QueryPipeline`, `OneirosWorker`. The mythological names remain canonical in documentation (`GLOSSARY.md`, `ARCHITECTURE.md`); they describe roles a future Pantheon will fill, not classes that need to exist now. **This is a deliberate anti-overengineering decision**, justified by HIVE.md §"Promotor Principle": the agent classes are about *expression* of behavior, and Gen 1 has only one expression of each function.

A Phoenix ticket records the migration: **PHX-0026: Pantheon-as-Personas Refactor** (target Gen 2). When we have ≥ 3 ingestion strategies, ≥ 2 query patterns, and a real reason to specialise, we promote the modules to agent classes with prompt genomes and Helios-managed promotors. The agent-orchestration framework question (§3.5) belongs in the same conversation.

**Newly filed in v2.** Five additional Phoenix tickets emerge from the v2 review:

- **PHX-0027: Empirical LLM provider re-evaluation** (target Gen 2). Once Athene-style verification exists, measure relation-survival rate per provider on a fixed corpus; revisit the §3.3a default with data.
- **PHX-0028: ExtractionAuditLog rotation and analytics** (target Gen 2). The audit log grows monotonically. Define rotation, archival, and read-side tooling.
- **PHX-0029: Per-sentence resume inside ingest stages** (target Gen 2). Gen 1 resumes at stage boundaries; per-sentence resume eliminates the worst-case ~1.50 EUR redundant LLM cost on crash mid-stage.
- **PHX-0030: Atom-granularity ablation across knowledge forms** (target Gen 2). PID-1 locks sentence-level for narrative; structural and mechanistic knowledge may need different defaults. Empirical study across genres.
- **PHX-0031: Document-level extraction with co-reference resolution** (target Gen 2). PID-2 defaults to sentence-level. Cross-sentence relations are captured imperfectly. A proper discourse-parsing extraction pass is a Gen 2 concern.

**Newly filed in v3.** Three additional Phoenix tickets emerge from the v3 round-2 Wikidata-depth review:

- **PHX-0032: Cross-language entity coreference at scale** (target Gen 2). Gen 1 uses four languages (`en`, `de`, `fr`, `it`) for `wbsearchentities` lookup. Gen 2 ingestion of non-European corpora (Tibetan, Chinese, Arabic, Sanskrit travel literature) needs language-aware tokenisation, transliteration policy, and possibly per-language NER models. Ties to PHX-0008 (Multi-Language Knowledge Bridging) and PHX-0017 (Sensorium).
- **PHX-0033: Pre-curated Wikidata subset for travel literature** (target Gen 2). The §3.4 v3 pipeline depends on a live Wikidata SPARQL endpoint and `wbsearchentities`. A curated, locally-hosted subset (~10 GB, places + persons + organisations + works) would remove the rate-limit ceiling, eliminate cold-network latency, and give us reproducible offline ingest. Ties to PHX-0024 (self-hosted Wikidata mirror) but more focused: the *travel-literature* sub-graph rather than all of Wikidata.
- **PHX-0034: Entity-resolution quality benchmark** (target Gen 2). The five-tier confidence model uses heuristic anchors (0.90 / 0.75 / 0.65 / 0.55 / 0.50). Empirical calibration requires a hand-annotated gold standard from at least three travel books; produces measured precision per tier, possibly revises the anchors. Prerequisite for any future automated promotion-policy refinement.

**Newly filed in v4 (Hesiod review round 2 — Run Reports).** One additional Phoenix ticket. Note on numbering: Hesiod's review round 2 (Run Reports) suggested filing this as PHX-0032, but PHX-0032 was already taken by v3 above. To preserve ID stability, this ticket is filed as PHX-0035; the original Hesiod proposal text is preserved verbatim in the description.

- **PHX-0035: Reviewer agent that consumes RunReports** (target Gen 2). A dedicated agent that periodically reads new `IngestRunReport`, `QueryRunReport`, and `OneirosTickReport` JSON files from `data/run_reports/`, compares verdicts and metrics across runs, identifies recurring patterns (e.g. "tier-1 ratio has been climbing for the last 5 ingests" or "query latency is degrading"), and proposes Phoenix Backlog tickets or prompt-template updates. This is the read-side of the §2.11 Reporting infrastructure. Likely sub-agents: `ReportTrendAnalyzer` (cross-run patterns), `RecommendationConsolidator` (groups free-text recommendations into actionable themes), `BacklogTicketProposer` (drafts PHX YAML for human review). The Reviewer is also the natural owner of the self-verdict thresholds in `Settings.report.thresholds.*` — it should propose threshold updates when measured distributions reveal that the heuristic anchors are mis-calibrated.

**Also explicitly out of Gen 1 scope:**
- **No GUI.** Genesis log §10 is explicit: agent-first, GUI irrelevant.
- **No multi-book.** Only "Seven Years in Tibet" for the demo. Multi-book ingest is mechanically possible but Wikidata rate limits and lack of cross-book deduplication make it premature.
- **No public deployment.** Local laptop demo only.
- **No authentication.** Single trusted operator.
- **No persistence beyond Neo4j.** No object storage for raw sources (the Source Lake idea — PHX-0025).

---

## 8. Preserved-Decisions Audit

Things in the existing codebase or documentation that I examined and chose to keep, with reasons.

- **`KnowledgeStore` Protocol shape** (`src/theogony/core/store.py`). Kept as-is. The interface is well-thought-through, supports both Gen 1 needs and the Phoenix process. Minor addition I propose: add `await store.batch_upsert_nodes(list[KnowledgeNode]) -> list[str]` and `batch_upsert_edges` for ingest performance. Currently ingest would issue thousands of single upserts.
- **`KnowledgeNode.layer` as enum with only `EPHEMERA` and `MNEME`** (no `ONEIROS`). Kept. Oneiros is a process, not a layer; the docs are consistent with this.
- **`vitality` as a weighted sum of four scores.** Kept. The defaults are heuristic and PHX-0009 already records that empirical tuning is needed.
- **Pydantic v2 throughout.** Kept. Already in pyproject.

## 9. Challenged-Decisions Audit

Things in the existing codebase or documentation that I examined and intend to change. Each change is small, justified, and reversible.

### 9.1 `Constellation` should not contain full `KnowledgeNode` objects

**Current.** `Constellation.nodes: list[KnowledgeNode]`. Each `KnowledgeNode` carries its `embedding: list[float]`. With 384-dim embeddings and ~50 nodes per constellation, every API response carries ~75 KB of float32. With 1536-dim (OpenAI) it is 300 KB. This will leak embeddings into the LLM context window if the synthesizer naively serializes the constellation.

**Change.** Introduce `ConstellationNode` and `ConstellationEdge` slim DTOs in `core/model.py`:

```python
class ConstellationNode(BaseModel):
    id: str
    label: str
    node_type: NodeType
    layer: Layer
    confidence: float
    source_ref: SourceRef
    # no embedding, no vitality, no full properties

class ConstellationEdge(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    weight: float
    confidence: float

class Constellation(BaseModel):
    query: str
    nodes: list[ConstellationNode]
    edges: list[ConstellationEdge]
    suggested_sources: list[SourceRef] = ...
    gaps: list[str] = ...
    retrieved_at: datetime = ...
    path: str = "fast"
```

`KnowledgeNode` stays for storage, ingestion, and `/node/{id}` responses where the full record is appropriate. The Hover-Lupe walks `Constellation` → identifies a node id → fetches the full `KnowledgeNode` separately if the user drills in. **This is a small change with large consequences for cost, payload size, and correctness**, and it is much cheaper to make now than later.

### 9.2 ID convention: always `AKA-…`; Wikidata id is in `external_ids`

**Current.** `KnowledgeNode.id` is `AKA-…` *or* `Q-…`.

**Change.** Always `AKA-…`. Wikidata id, when known, lives only in `external_ids["wikidata"]`. Reasons:
- Single source of truth for ID format simplifies indexing, logging, debugging.
- Wikidata sometimes retires Q-ids; rebinding is a problem if our id IS the Q-id.
- Equality and merging logic becomes uniform.

Trade-off: a Wikidata-aligned node looks like `AKA-abc123` not `Q806463` in the URL. Not a real cost. Cited in answers as `AKA-abc123 (Wikidata: Q806463, Uttarkashi)` is more honest anyway.

### 9.3 Add an explicit `embedding_model_id` field to `KnowledgeNode`

**Current.** No first-class field; we would have to put it in `properties`.

**Change.** Add:

```python
class KnowledgeNode(BaseModel):
    ...
    embedding_model_id: str | None = None   # e.g. "BAAI/bge-small-en-v1.5@v1"
    embedding_dim: int | None = None
    ...
```

Required by PHX-0005. Cheaper to do now than to migrate later.

### 9.4 Add an `evidence_span` field to `KnowledgeEdge`

**Current.** `KnowledgeEdge.source_ref` is optional but holds no span.

**Change.** Add an optional `evidence_span: str | None = None` to `KnowledgeEdge`, holding the substring of source text that the LLM cited as justification. Required for the relation-extraction discipline in §3.3.

### 9.5 Deterministic node and edge IDs

**Current.** `KnowledgeNode.id` defaults to `f"AKA-{uuid4().hex[:12]}"`. `KnowledgeEdge.id` defaults to `f"EDGE-{uuid4().hex[:12]}"`. Every ingest of the same source produces a fresh set of IDs.

**Why this fails OQ-7.** Resumable ingest depends on idempotent upserts. If re-running the same sentence after a crash produces a node with a new UUID, `upsert_node` cannot recognise the duplicate and the store accumulates ghosts.

**Change.** Default factories for both IDs become deterministic:

- `KnowledgeNode.id = f"AKA-" + sha256(f"{source_type}:{source_identifier}:{location}:{normalised_label}").hexdigest()[:12]`. The `normalised_label` is the lower-cased, whitespace-collapsed label.
- `KnowledgeEdge.id = f"EDGE-" + sha256(f"{source_id}:{relation_type}:{target_id}:{evidence_span_hash}").hexdigest()[:12]`.

UUID-based IDs remain available via an explicit `KnowledgeNode(id="AKA-...", ...)` constructor argument, so non-extraction code paths (manual nodes, agent-generated nodes) can still mint random IDs when appropriate.

#### 9.5a Edge ID disambiguator: what it includes and what it does not

Hesiod asked specifically: should the edge-ID disambiguator include `llm_model_id` and `prompt_template_id`, so that re-extraction with a different model produces a new edge while re-extraction with the same model is idempotent?

**Decision: no.** The edge-ID disambiguator is `(source_id, relation_type, target_id, evidence_span_hash)` and nothing else. Neither `llm_model_id` nor `prompt_template_id` is part of the hash.

**Reasoning.**

The question forces a clear semantic choice: *what is an edge?* Two answers compete:

- **Edge = a claim about reality.** "Harrer reached Uttarkashi" is one fact. Three different LLMs extracting it from the same sentence produces *one* edge with stronger evidence, not three.
- **Edge = a model output.** Each LLM call that produces an extraction is its own artifact. Three LLMs produce three edges, each owned by its model.

The first answer is consistent with the rest of the architecture. PHILOSOPHY §3 ("Verification Over Authority") explicitly says the chronicle accumulates *degrees of trust* from multiple sources of evidence — that requires the same fact to converge on the same node and edge. ARCHITECTURE.md's `vitality` aggregates `relevance` and `connectivity` per node and edge; counting the same fact three times because three models extracted it would falsify those scores. The Hover-Lupe shows users the chronicle's view of the world, not the chronicle's view of its own extractions.

So the edge identity is the *claim about reality*: source node, relation type, target node, evidence span. If the source sentence is the same and the extracted triple is the same, the edge is the same. The disambiguator includes `evidence_span_hash` because the same `(Harrer, MET, Marchese)` justified by two different sentences is two pieces of evidence (two edges with shared endpoints) — that *is* a meaningful distinction.

**Where model and prompt provenance lives.** Not in the ID, but in the audit log. Specifically:

- `ExtractionAuditLog.resulting_edge_ids` (§2.5) records which audit row produced which edge. To find every model and prompt that ever produced edge `EDGE-abc123`, query: `SELECT llm_provider, llm_model_id, prompt_template_id, created_at FROM extraction_calls WHERE resulting_edge_ids LIKE '%EDGE-abc123%'`.
- The `KnowledgeEdge.properties` dict gets a new optional list field, `extracted_by`, which is populated on first creation and *appended to* (deduplicated) on every subsequent extraction that produces the same edge:

  ```python
  edge.properties["extracted_by"] = [
      {"model_id": "gemini-2.5-flash-lite", "prompt_template_id": "rel_v1", "first_seen": "2026-04-17T10:23:00Z"},
      {"model_id": "gpt-4o-mini",          "prompt_template_id": "rel_v1", "first_seen": "2026-04-19T14:11:00Z"},
  ]
  ```

  This is the "this edge has been independently extracted by N different models with M different prompts" signal. It feeds into `confidence`: an edge produced by three independent models from the same evidence span should be more trusted than one produced by a single model, even before any verification pass. The exact aggregation function is heuristic for Gen 1 (`confidence = max(per_call_confidence) + 0.05 × (n_independent_extractors - 1)`, capped at 0.95) and is explicit in `extraction/scoring.py`.

**What this gives us.**

- *Resume after crash with the same model:* the same evidence span produces the same edge ID; `upsert_edge` is a no-op. Idempotent. ✓
- *Re-extraction with a different model:* same edge ID, but the edge's `properties.extracted_by` gains a new entry, and `confidence` rises. This is the right semantic — a corroborated fact. ✓
- *Different prompt that elicits a different relation type or different evidence span:* different edge ID. Two edges. Correctly distinguished. ✓

**What this does not give us.**

- A way to ask "what would the chronicle look like if we removed everything Gemini Flash Lite produced?" That requires querying the audit log to find affected edges and re-aggregating. Workable. Not a Gen 1 use case.
- Per-extractor versioning of edge weights. The aggregation collapses model-specific signals. Acceptable for Gen 1; PHX-0027 (LLM provider re-evaluation) will need a richer model when measuring relative provider quality.

**Trade-off.** Deterministic IDs are no longer URL-opaque — a sufficiently motivated reader can reverse-engineer "this node came from Gutenberg #944, chapter 3, the label was 'Uttarkashi'". For Gen 1's public-source-only data this is a feature, not a leak. For Lethe Vaults (Gen 2+), deterministic IDs over private content would be a privacy issue and the constructor must mint UUIDs there. Recorded in PHX-0021 (Lethe Vaults & Hades).

**Required by:** OQ-7 (resumable ingest). Cheaper now than after the first ingest run pollutes the store with ghost duplicates.

### 9.6 `KnowledgeNode.manual_resolution_needed` and `resolution_tier`

**Current.** `KnowledgeNode` has no field for "this node failed automatic Wikidata alignment and needs human review" and no field for the resolution path that produced it.

**Why this matters.** The §3.4 v3 honest-failure path needs a way to mark nodes that the pipeline could not confidently resolve, so that `theogony resolve` can find them and a future Hestia or Athene pass can audit them. The five-tier model also wants to record the path explicitly, not just the resulting confidence — two nodes can reach 0.65 confidence by very different routes (tier 2 with bio facts vs. tier 4 with corroborated repetition), and downstream agents may treat them differently.

**Change.** Add two fields to `KnowledgeNode`:

```python
class KnowledgeNode(BaseModel):
    ...
    manual_resolution_needed: bool = False
    resolution_tier: int | None = None    # 0–4 per §3.4 five-tier model;
                                          # None for nodes not produced by entity resolution
                                          # (e.g. claims, events created by relation extraction)
    ...
```

Semantics:

- `manual_resolution_needed=True` ↔ tier 0 (no Wikidata match) ∧ `external_ids == {}`. The two facts are linked but stored separately so that nothing depends on inference: a query "show me unresolved nodes" is one boolean filter, not a join + emptiness check.
- `resolution_tier=4` and `manual_resolution_needed=True` is illegal; the constructor validates this.
- `resolution_tier=None` is the default for nodes not produced by `EntityResolver` (events, claims, agent-created nodes). Down-stream code MUST NOT assume every node has a tier.

**API surface.** `KnowledgeStore` gains one query helper:

```python
async def list_pending_resolution(
    self,
    layer: Layer | None = None,
    limit: int = 100,
) -> list[KnowledgeNode]:
    """Nodes with manual_resolution_needed=True. Used by `theogony resolve`."""
    ...
```

This is the queryable surface for the honest-failure path. `theogony resolve --list` is its CLI presentation.

**Trade-off.** Two more fields on the node. Pydantic validation is one more rule. Some queries get an extra index (Neo4j: `CREATE INDEX node_manual_res FOR (n:KnowledgeNode) ON (n.manual_resolution_needed)`). Cost is ~5 minutes of work; cost of *not* having this and pretending tier 0 nodes are tier 1 is exactly the silent corruption Hesiod called out.

**Required by:** §3.4 (honest failure), `theogony resolve` CLI command. Cheaper now than after we have a chronicle full of mystery nodes.

---

## 10. Constraints Re-checked Against the Proposal

- **Budget ~300 EUR/month.** Gen 1 actual estimated cost: **~3.25 EUR** for default-path development LLM calls with Gemini 2.5 Flash Lite (25 ingest iterations on the demo book, see §3.3a and §4.1 v3 numbers), ~0 EUR for Neo4j (local Docker or Aura Free), ~0 EUR for embeddings (local). With `--detective` enabled on every iteration: ~36 EUR (still inside budget). Switching the default provider to GPT-4o-mini raises the default-path figure to ~5 EUR; switching to Claude Haiku 3.5 raises it to ~25 EUR. All scenarios well within the 300 EUR/month envelope.
- **One full-time contributor.** All four milestones are sized for a single experienced Python developer at full focus. Total optimistic estimate: 18–22 working days. Schedule has 20. The v2 additions (`ExtractionAuditLog`, `IngestRunStore`, `serve` lifecycle, deterministic IDs) added ~1.5 days. The v3 additions (deeper §3.4 `EntityResolver` with multi-language + bio facts + tiers, `BookContextExtractor`, `WikidataDetective`, `theogony resolve` CLI, two new `KnowledgeNode` fields) add another ~2 days. Total v3 work fits inside Week 2's allocated 5 days because `EntityResolver` is now sized L instead of M and the corresponding work in v2 was already budgeted as "M with stretch"; the deeper pipeline absorbs that stretch and a small share of Week 3 slack. The v4 additions (`Reporting` schemas + writer + four `_finalize_report()` hooks + anomaly rules + `theogony reports list/show` CLI) add ~1 day total, distributed as one S item per week (Week 1: schemas + writer; Week 2: ingest finalize + anomaly rules; Week 3: query + oneiros finalize; Week 4: CLI). No item is large enough to displace existing scope; v4 absorbs into the same per-week slack that v3 used.
- **Four weeks to demonstration.** The plan delivers the demonstration moment at end of Week 4 with a few days of slack absorbed into Week 4 polish.
- **Apache 2.0, no proprietary blockers.** Neo4j Community is GPLv3 *server*, accessed over Bolt (Apache 2.0 driver). spaCy, sentence-transformers, FastAPI, Pydantic, Typer, httpx — all permissive. Hosted LLM API usage (Google Gemini / OpenAI / Anthropic — all selectable) is optional and gated by env var; the system runs end-to-end with `StubLLMProvider` for development.
- **Aligned with PHILOSOPHY.md.**
  - Human flourishing principle: respected by *omission* in Gen 1 (no surveillance, no shadow twins, no operative agents) and recorded as Hestia schema for future review.
  - Transparency-by-architecture: every node has `SourceRef`; every relation carries `evidence_span` (§9.4); every LLM call is recorded in `ExtractionAuditLog` (§2.5); every API answer cites node ids; no hidden state.
  - Knowledge belongs to everyone: Apache 2.0; no proprietary services in the critical path; an English-only single-book demo, but reproducible by anyone with a laptop and (optionally) a Google AI Studio free-tier key.

---

## 11. The Single Sentence

If the only thing a contributor reads is one sentence from this document, it should be:

> Generation 1 is whatever lets us ingest one book from Project Gutenberg into a Neo4j-backed Chronik and answer one question about it with cited sources, in under five seconds, on a laptop, and prove that the architecture beneath it can grow into the rest of the vision without being torn up.

Everything else in this document is in service of that sentence.
