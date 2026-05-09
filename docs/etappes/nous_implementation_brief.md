# Nous — Implementation Brief

**Filed by:** Hesiod (architect)  
**For:** Talos (implementer)  
**Date:** 2026-05-07  
**Status:** Ready for Talos implementation  
**Source brief:** `docs/etappes/nous_hesiod_brief.md`

---

## 0. Orientation

Nous is a cognitive synthesis agent that supersedes the `topology_parser`. Where the parser extracts concepts from static chunks, Nous reads incrementally — carrying state forward across paragraphs, running kNN Chronicle lookups in parallel, triggering synthesis and repair as the reading progresses. The result is a denser, better-connected Chronicle subgraph, measured by Monkey 1 (§9 of the Hesiod brief).

This document is the binding plan for Talos. It does not re-narrate the vision; see `notes/architecture/reading_agent_vision.md` for that. It answers the eight architectural questions (Q1–Q8), specifies the module structure, the data model additions, the Etappe breakdown, the test strategy, and the Monkey-1 comparison protocol.

Build Doctrine applies unchanged: schema-first, function before polish, RunReport on every run, honest-failure, YAGNI.

---

## 1. Answers to Q1–Q8

### Q1 — Atomic reading unit: **Paragraph**

Wikipedia provides paragraph segmentation for free as markup. One LLM call per paragraph gives manageable working memory size and a tractable cost model for the first corpus run. Sentence-level would multiply LLM calls by 5–10 and add state complexity without validated benefit. If paragraph-level results are too coarse, sentence-level is added in v2.

**Consequence for implementation:** the Wikipedia fetcher must return text pre-segmented into paragraphs (not flat plaintext). Use the MediaWiki `action=parse` API with section/paragraph structure preserved, or parse `<p>` tags from the HTML response. The existing `fetch_article_plaintext` returns stripped plaintext — Nous needs a companion `fetch_article_structured` that returns sections + paragraphs as a list.

### Q2 — Working memory representation

Two concurrent representations:

1. **Concept registry** — `dict[node_id: str, weight: float]`, where `node_id` is the `AKA-*` id of an active concept. Initialised empty; populated with each LLM reading step output.
2. **Pooled embedding** — a `list[float]` (same dim as the store's embedding model) computed as the weighted average over the embeddings of the top-N active concepts by weight. Used as the kNN query vector for Chronicle lookup.

**Decay:** exponential per paragraph step, `weight *= exp(-1/τ)` where `τ = 3.0` (paragraphs). Applied at the start of each step, before merging the new LLM output. This matches the user's "pre-warmed" intuition: concepts from the last three paragraphs are still active, earlier ones fade.

**Capacity ceiling:** 50 active concepts. When the registry exceeds 50, the bottom half by weight is dropped. Dropped concepts that were already written to the Chronicle are not deleted — they are simply no longer in working memory. This is the "compression" described in the vision.

**Data structure:** `WorkingMemoryState` — a Pydantic model in `src/theogony/nous/model.py` (see §3).

### Q3 — Chronicle hint delivery to LLM: **Structured JSON block, top-5**

Format injected into the LLM prompt as a named field `chronicle_hints`:

```json
[
  {"id": "AKA-abc123", "label": "Sven Hedin", "similarity": 0.91, "source": "gutenberg:43497"},
  {"id": "AKA-def456", "label": "Trans-Himalaya", "similarity": 0.87, "source": "gutenberg:43497"}
]
```

Rationale: plain (id, label, similarity, source) tuples cost ~25–35 tokens per hit. Top-5 is ~175 tokens — far cheaper than a text-summary alternative that would paraphrase nodes and lose the traceable `id` field. The LLM receives the `id` values and may reference them in its structured output to mark which hints it used.

The LLM output schema includes a `chronicle_hits_used: list[str]` field (list of `AKA-*` ids). Any id in `chronicle_hints` that is absent from `chronicle_hits_used` is logged as "offered but ignored" in the `AnnotatedReading`.

### Q4 — Synthesis trigger: **LLM decides at each paragraph boundary**

At the end of every paragraph, the LLM receives a flag `synthesis_opportunity: true` in its prompt. The LLM's structured output includes a `synthesis_event: SynthesisOutput | None` field. If `None`, no synthesis occurs. If populated, it carries the synthesis concept label, the basis node ids, and any diagonal edges to higher-level concepts.

This is not a hard trigger. The LLM may return `synthesis_event: null` for low-density paragraphs (headers, short transitional paragraphs, list-only sections). It may also return a synthesis for mid-paragraph transitions if the working memory is dense — though this is only possible if we add mid-paragraph breaks in a future version. For v1 the synthesis decision is paragraph-level only.

No heuristic override. The LLM's judgement on synthesis is the output we are trying to study; overriding it with a heuristic would pollute Monkey 1.

### Q5 — Repair detection: **LLM asked at every step, supplemented by CONTRADICTS hits**

Every LLM call includes the current open tensions in the prompt (`open_tensions` field: list of `(node_id, description)` pairs). The LLM's output includes `repair_events: list[RepairEvent]`, which may be empty. A `RepairEvent` names the revised node id, the reason for revision, and the updated properties.

Additionally: if the Chronicle kNN search returns a node whose best edge to any working-memory concept is typed `CONTRADICTS`, the `chronicle_hints` for that step carry a `tension: true` flag on that entry. This surfaces potential contradictions without a separate cosine-threshold call.

The cosine-distance option (option b in the brief) is deferred: it requires a calibrated threshold, which we do not have until after the first corpus run.

**Cost:** asking "do you see any tension?" via the `repair_events` field in the structured output schema costs ~0 additional tokens — the schema slot is always present; empty list is the common case.

### Q6 — Identity resolution moment: **At-paragraph-end, progressive backfill via session registry**

Strategy:

1. **First mention** (within the paragraph being read): the LLM emits a candidate Q-ID with `resolution_tier=1`. If no Q-ID is guessed, `resolution_tier=0`.
2. **End of paragraph**: the LLM may revise any working-memory concept's Q-ID assignment based on the full paragraph context. Revised assignments are recorded as a `resolution_update` in the `AnnotatedReading`.
3. **End of article**: a single backfill pass iterates all concepts in the session's synthesis graph that have `resolution_tier <= 1` and re-runs a lightweight resolution check using the full article's context summary (working memory at article end). No additional LLM call — the article-end synthesis carries this as a structured field.

**Backfill in the data model:** the session maintains a `resolution_registry: dict[node_id, ResolutionCandidate]`. When a Q-ID is confirmed or revised, all edges in the local session graph that reference the old provisional id are updated before Chronicle write. Chronicle writes happen at synthesis events (paragraph-level), so provisional-id edges that predate a revision are still in the local session graph and can be corrected before write.

### Q7 — `AnnotatedReading` schema location: **`src/theogony/nous/model.py`**

`core/model.py` belongs to the Chronicle — `KnowledgeNode`, `KnowledgeEdge`, and the IDs. Nous-specific session models are a different domain and must not pollute the core schema.

New file: `src/theogony/nous/model.py` — contains `WorkingMemoryState`, `ChronicleHint`, `SynthesisOutput`, `RepairEvent`, `ReadingStep`, `AnnotatedReading`, `NousRunReport`.

The three small field additions to existing Chronicle models (`nous_session_id`, `synthesis_level`, `relation_codebook` — from §8 of the Hesiod brief) land in `core/model.py` as optional fields on `KnowledgeNode` and `KnowledgeEdge`. See §3 below.

`NousRunReport` extends `RunReportBase` from `reporting/models.py`, following the same pattern as `IngestRunReport`. Its `report_type` literal is `"nous"`. The `reporting/models.py` `RunReportBase.report_type` discriminated union must be extended to include `"nous"`.

### Q8 — Parallelism: **`asyncio.gather` — LLM call and kNN search concurrent**

```python
llm_task = asyncio.create_task(_call_llm(prompt, schema))
knn_task = asyncio.create_task(store.vector_search(pooled_embedding, k=5))
llm_result, chronicle_hits = await asyncio.gather(llm_task, knn_task)
```

The kNN search runs against the pooled embedding from the **previous** step's working memory (computed before the LLM call). This is correct: we want Chronicle context that was relevant before reading this paragraph, not after. The LLM call and the kNN search are independent — no ordering dependency.

If the Chronicle is an `InMemoryKnowledgeStore` (as in tests), the kNN search is synchronous in practice; `asyncio.gather` still works correctly, the gather simply runs the kNN instantly and awaits only the LLM.

The Chronicle write (after the LLM call returns) is sequential and follows the gather — writes are paragraph-level, not per-sentence, and blocking is acceptable there.

---

## 2. Module Structure

```
src/theogony/nous/
    __init__.py              # empty, standard package marker
    model.py                 # all Nous-specific Pydantic models
    reader.py                # NousReader — the main agent class
    wikipedia_parser.py      # structured Wikipedia fetch + segmentation
    prompts.py               # prompt builders for the reading step LLM call
```

**No new agent class beyond `NousReader`.** No cockpit module. No streaming. No multi-resolution model selector.

**CLI integration:** a new `nous read` subcommand in `src/theogony/cli.py` that takes a Wikipedia URL or article title and runs a Nous session. Produces an `AnnotatedReading` JSON file and a `NousRunReport`.

**Reporting:** `NousRunReport` written to `data/run_reports/nous/` (new subdirectory, same pattern as `data/run_reports/ingest/`).

**AnnotatedReading output:** written to `data/nous/` (new directory). Filename: `{session_id}.json`.

---

## 3. Data Model Additions

### 3.1 Additions to `src/theogony/core/model.py`

Three optional fields on existing models. YAGNI: add only what Nous needs to emit.

**On `KnowledgeNode`** (after the `resolution_tier` field):

```python
nous_session_id: str | None = Field(
    default=None,
    description="Reading session that produced this node (Nous only).",
)
synthesis_level: Literal["sentence", "paragraph", "chapter", "article"] | None = Field(
    default=None,
    description="Hierarchy level at which this node was synthesised (Nous only). "
                "None for parser-extracted nodes.",
)
```

**On `KnowledgeEdge`** (after the `evidence_span` field):

```python
relation_codebook: str | None = Field(
    default=None,
    description="Internal codebook entry (BINDS_TO, REINFORCES, etc.) when no Wikidata "
                "P-ID applies. Populated by Nous; left None by the topology_parser.",
)
```

All three fields default to `None` so existing Chronicle data and topology_parser output remain valid without migration.

### 3.2 `src/theogony/nous/model.py` — new models

All models use `ConfigDict(extra="forbid")`.

```python
class ChronicleHint(BaseModel):
    """One kNN hit offered to the LLM as context."""
    id: str                     # AKA-* node id
    label: str
    similarity: float           # cosine similarity, 0.0–1.0
    source: str                 # source_ref.source_type + ":" + identifier
    tension: bool = False       # True if this hit has a CONTRADICTS edge to working memory


class WorkingMemoryState(BaseModel):
    """Snapshot of working memory at a given reading step."""
    step_index: int
    concepts: dict[str, float]          # node_id → weight (after decay applied)
    pooled_embedding: list[float]       # weighted average over top-N concept embeddings
    open_tensions: list[tuple[str, str]]  # [(node_id, description), ...]


class ResolutionUpdate(BaseModel):
    """A within-session revision of a concept's Q-ID."""
    node_id: str
    previous_tier: int | None
    new_tier: int
    new_wikidata_id: str | None
    reason: str


class SynthesisOutput(BaseModel):
    """A synthesis event emitted by the LLM."""
    label: str                          # the synthesis concept's label
    description: str | None = None
    basis_node_ids: list[str]           # working-memory concepts absorbed into this synthesis
    diagonal_edges: list[tuple[str, str, str]] = Field(
        default_factory=list,
        description="[(source_id, relation_type, target_id)] — cross-level edges",
    )
    synthesis_level: Literal["paragraph", "chapter", "article"]
    confidence: float = Field(ge=0.0, le=1.0)


class RepairEvent(BaseModel):
    """A within-session revision triggered by tension."""
    revised_node_id: str
    reason: str
    old_description: str | None = None
    new_description: str | None = None
    tension_source: Literal["llm_detected", "chronicle_contradicts"]


class LLMReadingOutput(BaseModel):
    """Structured output from one LLM reading step."""
    new_concepts: list[dict]            # raw concept dicts; mapped to KnowledgeNode by reader
    new_edges: list[dict]               # raw edge dicts; mapped to KnowledgeEdge by reader
    chronicle_hits_used: list[str]      # AKA-* ids from chronicle_hints that were referenced
    synthesis_event: SynthesisOutput | None = None
    repair_events: list[RepairEvent] = Field(default_factory=list)
    resolution_updates: list[ResolutionUpdate] = Field(default_factory=list)


class ReadingStep(BaseModel):
    """Full record of one paragraph's reading pass."""
    step_index: int
    paragraph_text: str
    section_title: str | None
    synthesis_level_context: Literal["sentence", "paragraph", "chapter", "article"]
    working_memory_before: WorkingMemoryState
    chronicle_hints_offered: list[ChronicleHint]
    llm_output: LLMReadingOutput
    nodes_written: list[str]            # AKA-* ids written to Chronicle in this step
    edges_written: list[str]            # EDGE-* ids written to Chronicle in this step
    llm_cost_eur: float = Field(ge=0.0)
    llm_latency_ms: int = Field(ge=0)


class AnnotatedReading(BaseModel):
    """Full machine-readable record of one Nous reading session."""
    session_id: str
    source_url: str
    article_title: str
    started_at: datetime
    finished_at: datetime
    steps: list[ReadingStep]
    final_working_memory: WorkingMemoryState
    total_nodes_written: int = Field(ge=0)
    total_edges_written: int = Field(ge=0)
    total_synthesis_events: int = Field(ge=0)
    total_repair_events: int = Field(ge=0)
    chronicle_seeded: bool = Field(
        description="True if the Chronicle contained nodes before this session started. "
                    "Monkey-1 comparison requires chronicle_seeded=True to show "
                    "cross-document connection metrics."
    )
```

### 3.3 `NousRunReport` in `src/theogony/reporting/models.py`

Extends `RunReportBase`. Add to the existing file:

```python
class NousRunReport(RunReportBase):
    report_type: Literal["nous"] = "nous"
    session_id: str
    source_url: str
    reading_units_total: int = Field(ge=0)
    nodes_written: int = Field(ge=0)
    edges_written: int = Field(ge=0)
    synthesis_events: int = Field(ge=0)
    repair_events: int = Field(ge=0)
    chronicle_hits_offered: int = Field(ge=0)
    chronicle_hits_used: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    llm_cost_eur: float = Field(ge=0.0)
    wall_clock_s: float = Field(ge=0.0)
    chronicle_seeded: bool
    annotated_reading_path: str | None = None  # path to the JSON file, relative to project root
```

Also extend `RunReportBase.report_type` to include `"nous"` in its `Literal`.

---

## 4. Etappe Breakdown for Talos

Sizing: **S** = ≤ 1 day, **M** = 2–3 days, **L** = 4–5 days.

Dependencies flow top to bottom; no step may begin before its predecessor is green on `pytest -q`.

---

### E1 — Data model and Wikipedia parser (S)

**Files touched:**
- `src/theogony/core/model.py` — add `nous_session_id`, `synthesis_level` to `KnowledgeNode`; `relation_codebook` to `KnowledgeEdge`
- `src/theogony/reporting/models.py` — add `NousRunReport`; extend `report_type` Literal
- `src/theogony/nous/__init__.py` — create (empty)
- `src/theogony/nous/model.py` — create with all Nous models from §3.2
- `src/theogony/nous/wikipedia_parser.py` — structured fetch: returns `list[WikiSection]` where each section has `title: str`, `level: int`, `paragraphs: list[str]`

**Done when:** `pytest -q` green; `ruff format` + `ruff check` clean; `mypy src/theogony` clean.

**Tests (ship with E1):**
- `tests/nous/test_models.py` — round-trip JSON on every new Pydantic model; `extra="forbid"` rejection
- `tests/nous/test_wikipedia_parser.py` — parse a short fixture HTML into expected section/paragraph structure (offline fixture, no HTTP)

---

### E2 — Prompt builders (S)

**Files touched:**
- `src/theogony/nous/prompts.py` — `build_reading_step_prompt(paragraph, working_memory, chronicle_hints, open_tensions, synthesis_opportunity) -> str` and the JSON schema dict for `LLMReadingOutput`

The JSON schema for `LLMReadingOutput` is what gets passed to the LLM's `json_schema` parameter. It must be manually crafted (not auto-generated from Pydantic) to match the `LLMProvider.complete` interface, following the same pattern as the existing relation/topology extractors.

**Done when:** `pytest -q` green; prompt builder returns a deterministic string given fixed inputs (unit testable without LLM).

**Tests (ship with E2):**
- `tests/nous/test_prompts.py` — given fixed inputs, the prompt contains expected substrings (working memory summary, chronicle hints block, synthesis_opportunity flag)

---

### E3 — NousReader core loop (M)

**Files touched:**
- `src/theogony/nous/reader.py` — `NousReader` class

`NousReader.__init__` takes `store: KnowledgeStore`, `llm: LLMProvider`, `embedding_model: ...` (same embedding interface as the existing pipeline). No LLM calls in `__init__`.

Main method: `async def read(self, url: str) -> tuple[AnnotatedReading, NousRunReport]`

Loop structure:
```python
sections = await fetch_article_structured(url)
for section in sections:
    for paragraph in section.paragraphs:
        # 1. Apply decay to working memory
        # 2. Compute pooled embedding from working memory
        # 3. asyncio.gather(llm_call, knn_search)
        # 4. Parse LLMReadingOutput
        # 5. Map raw concept dicts → KnowledgeNode (with nous_session_id, synthesis_level)
        # 6. Map raw edge dicts → KnowledgeEdge (with relation_codebook)
        # 7. Apply resolution_updates to session registry
        # 8. Apply repair_events to local synthesis graph
        # 9. If synthesis_event: write synthesis node + edges to Chronicle
        # 10. Update working memory
        # 11. Append ReadingStep to AnnotatedReading.steps
# Post-loop: article-end backfill pass (resolution_tier <= 1)
# Write NousRunReport
```

On any LLM failure: log, append a `verdict="failed"` step to AnnotatedReading, continue with next paragraph (do not crash). If more than 20% of paragraphs fail, set `NousRunReport.verdict="partial"`. If > 50% fail, set `verdict="failed"`.

**Done when:** `pytest -q` green; `NousReader` runs end-to-end with `InMemoryKnowledgeStore` + `StubLLMProvider` on a two-section fixture article.

**Tests (ship with E3):**
- `tests/nous/test_reader.py` — integration test with `InMemoryKnowledgeStore` + `StubLLMProvider` on a minimal fixture article (2 sections × 3 paragraphs); assert `AnnotatedReading.steps` count, `NousRunReport.nodes_written > 0`, `NousRunReport.verdict == "success"`
- `tests/nous/test_reader_failure.py` — stub LLM returns parse-invalid JSON for >50% of calls; assert `NousRunReport.verdict == "failed"` and report is written (not exception)

---

### E4 — CLI command (S)

**Files touched:**
- `src/theogony/cli.py` — new `nous read` subcommand

```
theogony nous read "Sven Hedin"       # Wikipedia article title
theogony nous read --url <URL>        # direct URL
```

Options:
- `--sections N` — process only first N sections (for fast iteration; analogous to `--sentences N` on the ingest command)
- `--output PATH` — override AnnotatedReading output path
- `--no-chronicle` — use `InMemoryKnowledgeStore` even if a Neo4j store is configured (for cold-store runs that still exercise Nous)

Output on completion:
```
Nous session complete.
  Paragraphs processed: 47
  Nodes written:        312
  Edges written:        1 104
  Synthesis events:     12
  Repair events:        3
  Chronicle hits used:  88 / 235 offered
  LLM calls:           47
  LLM cost:            €0.21
  Wall clock:          4m 12s
  AnnotatedReading:    data/nous/<session_id>.json
  RunReport:           data/run_reports/nous/<run_id>.json
```

**Done when:** `pytest -q` green; `theogony nous read --help` works; manual smoke run with `--sections 2 --no-chronicle` produces an AnnotatedReading JSON file.

**Tests (ship with E4):**
- `tests/nous/test_cli.py` — `CliRunner` test: `nous read --sections 1 --no-chronicle "Test Article"` with mocked HTTP and stub LLM; assert exit code 0, AnnotatedReading file created.

---

### E5 — Monkey-1 comparison script (S)

**Files touched:**
- `scripts/monkey1_compare.py` — standalone script, not a CLI subcommand

Runs both pipelines on the same Wikipedia article title, collects metrics, prints a comparison table. Does not require a live Chronicle at start — can be run with `--cold` to skip the Chronicle-hit columns.

Output (Markdown table to stdout):

```
| Metric                        | topology_parser | Nous     |
|-------------------------------|-----------------|----------|
| Nodes produced                | ?               | ?        |
| Edges produced                | ?               | ?        |
| Edge-to-node ratio            | ?               | ?        |
| Cross-level diagonal edges    | 0 (tree)        | ?        |
| Chronicle hits used           | 0 (no retrieval)| ?        |
| New connections to Hedin nodes| 0               | ?        |
```

The script reads metrics from the `NousRunReport` JSON and from an `IngestRunReport` produced by running the topology_parser on the same article. It does not need a new pipeline — it invokes the existing CLI via subprocess or directly via the Python API.

**Done when:** script runs with mocked inputs and produces a valid Markdown table; no `pytest` test required for the script itself, but the script must not import anything that breaks `pytest -q`.

---

## 5. Test Strategy

### Unit tests (no external services)

Every model: round-trip JSON serialisation; `extra="forbid"` enforcement; invalid-literal rejection. These ship with E1.

Prompt builders: deterministic output given fixed inputs. Ship with E2.

Reader: full loop on InMemoryKnowledgeStore + StubLLMProvider. Ship with E3.

CLI: CliRunner with mocked HTTP + stub LLM. Ship with E4.

### Contract tests (gated by env var)

`THEOGONY_TEST_NEO4J=1` — NousReader writes to a real Neo4j testcontainer; assert at least one node and one edge appear in the store after the session.

`THEOGONY_RUN_NOUS=1` — live LLM run against the Sven Hedin Wikipedia article with `--sections 3`; assert `NousRunReport.verdict in ("success", "partial")` and `edge_to_node_ratio > 1.0`.

These tests do not run in standard CI. They are run locally before the PR merges, following the same discipline as `THEOGONY_RUN_CHARACTERIZATION=1`.

### What does NOT need a test

- The Monkey-1 comparison script (it produces human-readable output, not machine assertions)
- The `AnnotatedReading` JSON file format beyond what the model round-trip covers
- The exact synthesis or repair outputs of the live LLM (empirical, not contractual)

### CI remains `pytest -q` green

The entire E1–E4 test suite runs without any live service, live LLM, or network access. `StubLLMProvider` (already in `src/theogony/agents/llm.py`) returns scripted responses. HTTP is mocked via `respx` or `unittest.mock`.

---

## 6. Success Metric — Monkey-1 Comparison Protocol

**Corpus:** Wikipedia article "Trans-Himalaya" (or "Sven Hedin" — whichever produces the longer article; confirm with `theogony nous read --sections 0 "Sven Hedin" --no-chronicle --dry-run` to count paragraphs before committing).

**Chronicle precondition:** the Gutenberg #43497 bounded ingest must be present in Neo4j before the Nous run:

```bash
docker compose up -d neo4j
theogony ingest 43497 --sentences 500
# Expected: ~756 nodes / ~139 edges / ~20 min / ~€0.70
# See docs/etappes/demo_log.md for exact numbers
```

> **Warning for reproducibility:** running Monkey 1 on a cold store will show `chronicle_hits_used = 0` and `new_connections_to_hedin_nodes = 0`. This is expected and must not be mistaken for a Nous failure. The `NousRunReport.chronicle_seeded` field documents this condition.

**topology_parser baseline:** run the existing pipeline on the same article (via `theogony ingest --url <wikipedia-url>` if supported, or via the Python API directly). Capture `IngestRunReport` metrics.

**Nous run:**

```bash
theogony nous read "Trans-Himalaya" --sections all
```

**Metrics to collect and compare:**

| Metric | How to measure |
|---|---|
| Nodes produced | `NousRunReport.nodes_written` vs `IngestRunReport.store.nodes_upserted` |
| Edges produced | `NousRunReport.edges_written` vs `IngestRunReport.store.edges_upserted` |
| Edge-to-node ratio | edges / nodes for each run |
| Cross-level diagonal edges | count of `KnowledgeEdge` where `source.synthesis_level != target.synthesis_level` in the Nous session; 0 for the parser |
| Chronicle hits used | `NousRunReport.chronicle_hits_used`; 0 for the parser |
| New connections to existing Hedin nodes | count of edges in the Nous session graph that have one endpoint already in the Chronicle (AKA-* id exists before the session); 0 for the parser |

**Threshold for "Monkey 1 answered":** Nous produces an edge-to-node ratio > topology_parser AND at least one cross-level diagonal edge AND at least one Chronicle hit used (when `chronicle_seeded=True`). No absolute number is prescribed — the first run produces the baseline, and the comparison itself is the answer.

---

## 7. Files Created or Modified — Summary

| Path | Action |
|---|---|
| `src/theogony/core/model.py` | Modify — add 3 optional fields |
| `src/theogony/reporting/models.py` | Modify — add `NousRunReport`; extend `report_type` Literal |
| `src/theogony/nous/__init__.py` | Create (empty) |
| `src/theogony/nous/model.py` | Create — all Nous Pydantic models |
| `src/theogony/nous/reader.py` | Create — `NousReader` |
| `src/theogony/nous/wikipedia_parser.py` | Create — structured Wikipedia fetch |
| `src/theogony/nous/prompts.py` | Create — prompt builders |
| `src/theogony/cli.py` | Modify — add `nous read` subcommand |
| `scripts/monkey1_compare.py` | Create — comparison script |
| `tests/nous/test_models.py` | Create |
| `tests/nous/test_wikipedia_parser.py` | Create |
| `tests/nous/test_prompts.py` | Create |
| `tests/nous/test_reader.py` | Create |
| `tests/nous/test_reader_failure.py` | Create |
| `tests/nous/test_cli.py` | Create |

New directories: `src/theogony/nous/`, `tests/nous/`, `data/nous/` (created at runtime by the reader), `data/run_reports/nous/` (created at runtime).

---

## 8. Deferred (not in v1 scope)

Per §7 of the Hesiod brief, the following are explicitly deferred and must not appear in v1:

- Multi-resolution models (sentence=small, paragraph=medium, chapter=large)
- Trust-and-skim mode
- Cross-section repair reach (v1 repair is within-section only)
- Cockpit visualisation
- Streaming Chronicle writes
- Wikipedia link-graph traversal beyond the current article

Any Phoenix Backlog ticket for these items belongs to Talos's discretion after the first Monkey-1 result, not before.

---

*Hesiod withdraws. The build belongs to Talos.*
