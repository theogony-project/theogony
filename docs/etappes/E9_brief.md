# E9 — API + CLI surface (FastAPI app + four new Typer commands)

Brief from Hesiod to Talos, 2026-04-19. Companion to Plan §2.8, §3.7, §4.4, §5 E9 (M); follows merged Etappe E8 (PR #20).

## What this etappe does

Closes the user-facing surface of the Plan §1 demonstration moment. After E9, an operator can:

```bash
docker compose up -d neo4j
theogony ingest 43497 --sentences 200 --neo4j         # E5/E6/E7 + E9 wiring
theogony ask "Wer war Sven Hedin?"                     # E8 retrieval, real CLI
theogony node AKA-3432a578cfb0                         # Hover-Lupe one-shot
theogony resolve --list                                # E2 honest-failure surface
theogony serve                                         # FastAPI lifespan via uvicorn
curl localhost:8000/query -d '{"q":"Wer war Sven Hedin?"}'
```

Three of these — `ask`, `node`, `serve` — are what make Theogony a *system* rather than a Python package. `resolve` carries forward the v3 §3.4 manual-resolution discipline. The HTTP surface is the substrate the future Hover-Lupe UI (Gen 2) will couple onto. After E9 there is no functionality gap between the Plan §1 demo script and what a fresh contributor can do from a terminal.

## Scope decisions (read first)

### OneirosWorker stays OUT, but its lifespan slot is wired

Plan §4.4 specifies the FastAPI `lifespan` with an `OneirosWorker` slot:

```text
oneiros = OneirosWorker(store, settings)
app.state.oneiros_task = asyncio.create_task(oneiros.run())
```

E9 does **not** ship `OneirosWorker` itself — that is reserved for the **separate post-E8 etappe (E8.5 in the post-E8 plan reconciliation Daedalus is filing)**. E9's `serve` lifespan therefore wires the slot as a **conditional**: if `app.state.oneiros` is set (a future `OneirosWorker` instance), start its task; if it is `None` (current state), skip. This makes E9 self-contained and gives E8.5 a single-line wire-up. Test the absent case (start + clean shutdown without OneirosWorker) — do not skip the lifespan test on this account.

### `theogony ingest` rewires to Neo4j (carry-over from E7)

The existing `theogony ingest` (E6) currently uses `InMemoryKnowledgeStore` — explicitly documented as "process-local; the Neo4jKnowledgeStore (E7) will replace it for persistence." E9 makes that swap, gated by a `--store` option that defaults to `neo4j` and accepts `memory` for offline tests:

```bash
theogony ingest 43497 --sentences 50            # default: --store neo4j
theogony ingest 43497 --sentences 50 --store memory  # in-memory, for tests/CI
```

This is the only edit to the existing `ingest` command — its body, options, error handling, and rich output stay the same. Wire `--store neo4j` to construct `Neo4jKnowledgeStore` from `Settings.neo4j`, with the same `async with store: …` ctxmgr the smoke script (`scripts/smoke_e8.py`) already uses.

### CLI single-file vs. package — Talos calls it

`src/theogony/cli.py` is currently 522 lines. Adding four commands plus their helpers will push it past ~1000 lines. If you decide that warrants splitting into `src/theogony/cli/__init__.py` + `cli/{ask,node,resolve,serve,ingest,reports}.py`, do it — but this is YAGNI-territory: a 1000-line CLI module is still readable and has zero import-graph cost. **Default: stay single-file.** Escalate only if mypy/ruff start complaining about cyclic imports between command modules.

### Detective Mode is OUT

`theogony resolve` ships **without** the `--detective` flag in E9. Plan §5 schedules Detective Mode as a separate S–M etappe gated on PHX-0041's re-measurement. The `resolve` command's `--list` and interactive Q-ID assignment are E9 deliverables; the `--detective` flag is not.

## Files

```
src/theogony/api/__init__.py                   EDIT  re-export FastAPI app + DTOs
src/theogony/api/app.py                        NEW   FastAPI app + lifespan
src/theogony/api/dependencies.py               NEW   per-request state extractors
src/theogony/api/dto.py                        NEW   request/response Pydantic schemas
src/theogony/api/routes/__init__.py            NEW   re-export router groups
src/theogony/api/routes/health.py              NEW   GET /health
src/theogony/api/routes/query.py               NEW   POST /query
src/theogony/api/routes/node.py                NEW   GET /node/{id}
src/theogony/api/routes/ingest.py              NEW   POST /ingest (async background)
src/theogony/cli.py                            EDIT  +ask, +node, +resolve, +serve; ingest --store
tests/test_api_health.py                       NEW   /health smoke
tests/test_api_query.py                        NEW   /query against InMemory + StubLLM
tests/test_api_node.py                         NEW   /node/{id} happy + 404 + Hover-Lupe shape
tests/test_api_ingest.py                       NEW   /ingest accepted; report URL returned
tests/test_api_lifespan.py                     NEW   startup+shutdown ordering, no-OneirosWorker case
tests/test_cli_ask.py                          NEW   typer.testing.CliRunner; cited answer rendered
tests/test_cli_node.py                         NEW   neighborhood Rich panel; missing-node honest fail
tests/test_cli_resolve.py                      NEW   --list paths; interactive flow stubbed
tests/test_cli_serve_smoke.py                  NEW   subprocess-spawned uvicorn; /health returns 200
docs/etappes/E9_brief.md                       (this file — already exists)
```

The retrieval and store layers are **not edited**. `Neo4jKnowledgeStore`, `MultiHopRetriever`, `ConstellationAssembler`, `AnswerSynthesizer`, `QueryPipeline`, `RelevanceTracker` all stay verbatim. E9 is pure surface.

## Classes & APIs

### FastAPI lifespan — `api/app.py`

The lifespan is the single owner of long-lived resources. It mirrors Plan §4.4 exactly, with the OneirosWorker slot conditional per the scope decision above.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    audit = ExtractionAuditLog(settings.data_dir / "audit.sqlite").__enter__()
    embedder = LocalSentenceTransformerEmbedder(
        model_id=settings.embedding.model_id, dim=settings.embedding.dim,
    )
    _ = await embedder.embed("warmup")  # eager BGE-small load
    llm = build_llm_from_settings(settings)
    store = await Neo4jKnowledgeStore(settings.neo4j, embedding_dim=embedder.dim).__aenter__()
    report_writer = RunReportWriter(settings.run_reports_dir)

    app.state.settings = settings
    app.state.audit = audit
    app.state.embedder = embedder
    app.state.llm = llm
    app.state.store = store
    app.state.report_writer = report_writer

    # OneirosWorker slot — wired conditionally; E8.5 will populate it.
    app.state.oneiros = None
    app.state.oneiros_task = None

    log.info("api lifespan: startup complete")
    try:
        yield
    finally:
        if app.state.oneiros_task is not None:
            app.state.oneiros_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(app.state.oneiros_task, timeout=5.0)
        await app.state.store.__aexit__(None, None, None)
        if hasattr(app.state.llm, "aclose"):
            await app.state.llm.aclose()
        app.state.audit.__exit__(None, None, None)
        log.info("api lifespan: shutdown complete")


app = FastAPI(title="Theogony", lifespan=lifespan)
app.include_router(health_router)
app.include_router(query_router)
app.include_router(node_router)
app.include_router(ingest_router)
```

The `__enter__`/`__aenter__` / `__exit__`/`__aexit__` calls are **deliberate** rather than nested `async with` blocks — the lifespan needs to keep all five resources alive across the `yield` and tear them down only in the `finally`. Document the choice in the docstring; do not refactor to `AsyncExitStack` unless mypy forces it.

### Per-request dependencies — `api/dependencies.py`

One factory per pipeline. They construct the pipeline from `app.state` and inject it via FastAPI's `Depends(...)` so route handlers stay testable (override the dependency in tests, no monkeypatching).

```python
def get_query_pipeline(request: Request) -> QueryPipeline:
    state = request.app.state
    return QueryPipeline(
        embedder=state.embedder,
        retriever=MultiHopRetriever(state.store),
        assembler=ConstellationAssembler(state.store),
        synthesizer=AnswerSynthesizer(state.llm, audit_log=state.audit),
        relevance=RelevanceTracker(state.store),
        settings=state.settings,
        report_writer=state.report_writer,
    )

def get_store(request: Request) -> KnowledgeStore: ...
def get_settings(request: Request) -> Settings: ...
```

### Routes

#### `GET /health` — `api/routes/health.py`

Returns 200 plus a small JSON: `{"status": "ok", "version": "0.1.0", "store": "neo4j", "report_counts": {...}}`. Same data as `theogony status`, intentionally so — the `/health` endpoint is what an external monitor would scrape; `theogony status` is the human face of the same information.

Do **not** include LLM provider connectivity in `/health` — calling Gemini just to answer a healthcheck is wrong. Add a `?deep=true` query param later if needed (Gen 2; do not anticipate).

#### `POST /query` — `api/routes/query.py`

Request DTO:
```python
class QueryRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=2000)
    layer: Layer | None = None
    k: int = Field(default=10, ge=1, le=50)
    hops: int = Field(default=2, ge=0, le=4)
```

Response DTO mirrors `QueryResult` shape **but excludes** `Constellation.nodes[*].embedding`-bearing fields if any leaked through (defensive — the slim DTOs already exclude them, but the API boundary is a second filter). Returns `Answer.text`, `Answer.cited_node_ids`, the slim `Constellation`, the `report.run_id`, the `report.verdict`, and `report.verdict_reasoning`. The full report stays on disk; expose `report_url=/reports/{run_id}` so a UI can fetch it later (E9 does **not** add a `/reports/{run_id}` endpoint — `theogony reports show` is the supported path; document the URL as a Gen-2 placeholder).

Honest failure: catch `LLMRateLimitError`, `LLMProviderError`, transport errors → return `503 Service Unavailable` with a structured JSON `{"error": "...", "verdict": "failed"}`. Do **not** let an exception escape into a default 500.

#### `GET /node/{id}` — `api/routes/node.py`

The Hover-Lupe substrate. Returns the `KnowledgeNode` (slim DTO — no embedding), its depth-1 neighbourhood (`KnowledgeStore.get_neighborhood(node_id, depth=1, min_weight=0.3)`), and the inbound/outbound edges. 404 if the id is unknown.

Response DTO:
```python
class NodeResponse(BaseModel):
    node: ConstellationNode
    neighborhood: Constellation  # path="fast"; no synthesized answer; no gaps
```

`ConstellationAssembler.assemble(query=node.label, retrieval_result=...)` is **not** the right tool here — it depends on a query-anchored `MultiHopResult`. Instead, project directly: `Constellation(query=node.label, nodes=[ConstellationNode.from_knowledge_node(n) for n in [node, *neighbors]], edges=[ConstellationEdge.from_knowledge_edge(e) for e in edges], suggested_sources=[…], gaps=[], path="fast")`. Document the small projection helper in `api/routes/node.py`; do **not** add a public `Constellation.from_node_neighborhood(...)` method on `core/model.py` (that's premature API).

#### `POST /ingest` — `api/routes/ingest.py`

Accepts `{"source_type": "gutenberg", "identifier": "43497", "options": {...}}`, returns `202 Accepted` with `{"run_id": "01K...", "report_url": "..."}` and runs the ingest in a `BackgroundTask`. The background task writes the report to disk on completion; the operator polls `theogony reports show <run_id>` (or in Gen 2, the `/reports/{run_id}` endpoint).

Why background: an ingest is 30s–10min depending on book size — keeping the HTTP request open for that is wrong. Why no SSE/Websocket progress stream: YAGNI; the report-writer's per-stage updates are already on disk.

The `BackgroundTask` runs against `app.state.store` (Neo4j by default). Honest failure: any exception during the background task is logged + the report is still finalised with `status="failed"` and persisted (Plan §2.11.4 — never abort, always write the report).

### CLI commands — `cli.py` (additions)

Order of additions in the file: after `ingest` (which is currently the last command), before `if __name__ == "__main__"`. Each command follows the existing pattern: a sync Typer entry that calls `asyncio.run(_run_<command>(…))`, with rich-styled output and honest-failure panels.

#### `theogony ask "<query>"`

```python
@app.command()
def ask(
    query: str = typer.Argument(..., help="The question to ask the Chronik."),
    k: int = typer.Option(10, "--k", min=1, max=50, help="Number of seed nodes."),
    hops: int = typer.Option(2, "--hops", min=0, max=4, help="Graph expansion depth."),
    layer: str | None = typer.Option(None, "--layer", help="Restrict to layer: chronik|wissen|aletheia."),
) -> None: ...
```

Wires the same components as `scripts/smoke_e8.py` (Neo4j store + embedder + LLM + audit log + report writer + QueryPipeline). Renders a Rich panel:

```
╭───────────────── Wer war Sven Hedin? ─ good ─────────────────╮
│ Sven Hedin was a Swedish [AKA-3432a578cfb0] explorer who…    │
│                                                                │
│ Cited: AKA-3432a578cfb0, AKA-7c91e2ab9912 (2 nodes, 1 high-conf) │
│ Constellation: 10 nodes / 4 edges / 0 gaps                    │
│ Synthesis: 1240 ms · 287 in / 22 out tokens · 0.000273 EUR    │
│ Run: 01KP1G... → theogony reports show 01KP1G...               │
╰────────────────────────────────────────────────────────────────╯
```

Verdict-coloured border (good=green, partial=yellow, poor/failed=red) — same `verdict_styles` table the existing `_print_ingest_summary` already uses; lift it into a module-level constant rather than duplicating.

#### `theogony node <id>`

Prints the node's full record + a Rich tree of its depth-1 neighbourhood, with each neighbour's `node_type`, confidence, and `relation_type` to/from the queried node. Source refs are rendered as a small bullet list under the panel.

```
╭───────────────────── AKA-3432a578cfb0 ─ entity ─────────────────╮
│ Sweden                                                            │
│ confidence=0.92 · resolution_tier=2 · external_ids: Q34            │
├──── Neighbourhood (depth=1) ────────────────────────────────────┤
│ ←─ AKA-9f82b1c7…  Sven Hedin       (BORN_IN) confidence=0.81     │
│ →─ AKA-aa11ef02…  King Oskar       (RULED) confidence=0.74       │
│ Sources: gutenberg:43497, wikidata:Q34                            │
╰────────────────────────────────────────────────────────────────────╯
```

Honest failure: missing id → red panel "no node with that id; did you mean …?" with up to three closest prefix matches.

#### `theogony resolve [<mention>] [--list]`

Two modes:
- `theogony resolve --list` → prints a table of nodes with `manual_resolution_needed=true`, columns `(label, mention, candidates_count, source_ref)`. Reads via `KnowledgeStore.list_pending_resolution()` (already in the Protocol). Cap output at `--last=20` (default) to keep the terminal usable.
- `theogony resolve <mention>` → opens an interactive session: print the candidate Q-IDs (from the audit log's last `entity_resolution` row for this mention), prompt the user to pick one (or type `none` for tier-0), call `KnowledgeStore.resolve_node(node_id, q_id)` (already in the Protocol), write one `manual_resolution` audit row, print success.

Use Typer's `confirm` and `prompt` helpers — do not roll your own input loop. The interactive flow should accept a `--non-interactive --pick=<Q-ID>` pair for scripting (E9 ships interactive; the non-interactive mode is the test surface).

#### `theogony serve [--host] [--port] [--reload]`

Thin wrapper around `uvicorn.run("theogony.api.app:app", host=..., port=..., reload=...)`. Default host `127.0.0.1`, port `8000` (do not default to `0.0.0.0` — local-first principle). `--reload` enables uvicorn's reload mode for dev; document that it bypasses the lifespan (uvicorn limitation, well-known) so dev iterations against the API still work but real serve uses `--no-reload` (the default).

Print a single line on start: `Theogony API → http://127.0.0.1:8000  (try: curl localhost:8000/health)` — same UX as `npm run dev`.

## Tests

Nine new test files. The existing test patterns apply: API tests via `httpx.AsyncClient`/`TestClient` against an in-process FastAPI app with `InMemoryKnowledgeStore` + `StubLLMProvider` (Plan §3.8 layer 4). CLI tests via `typer.testing.CliRunner` (Plan §3.8 layer 3 conceptually, layer 4 in practice — they go through the same wiring).

| File | Layer (§3.8) | What it asserts |
|---|---|---|
| `test_api_health.py` | 4 | 200; payload shape; no LLM call (assert via `unittest.mock.AsyncMock` on the LLM dep). |
| `test_api_query.py` | 4 integration | Happy path returns `Answer + Constellation + run_id`; 503 on synthesizer transport error; 422 on empty/oversized query. |
| `test_api_node.py` | 4 | Existing id → 200 + neighbourhood; missing id → 404 + "did you mean" hint; embedding never appears in response payload. |
| `test_api_ingest.py` | 4 | 202 + run_id; background task runs; report file appears on disk after a brief wait. |
| `test_api_lifespan.py` | 4 lifespan | Startup wires every `app.state.*`; shutdown cleans them up; OneirosWorker absent does NOT skip lifespan; OneirosWorker present (mocked) DOES start + cancel. |
| `test_cli_ask.py` | 4 | `CliRunner.invoke(["ask", "..."])` exits 0; output contains `[AKA-…]`; verdict-coloured panel rendered. |
| `test_cli_node.py` | 4 | `node <id>` exits 0; missing id exits 1 with red panel; embedding never appears in stdout. |
| `test_cli_resolve.py` | 4 | `resolve --list` prints pending; `resolve <m> --non-interactive --pick=Q123` writes audit row + success message. |
| `test_cli_serve_smoke.py` | 5 e2e | Spawns `theogony serve` as subprocess; polls `http://127.0.0.1:<random>/health`; sends SIGINT; asserts clean exit ≤ 5 s. Gated on `THEOGONY_TEST_SERVE=1` (do not run on every CI — process spawning is slow + flaky in matrices). |

CI: the eight non-`serve` tests join the existing Py3.12/3.13 jobs (no new job). `test_cli_serve_smoke.py` gets its own optional CI step that runs only on the linux runner, similar to the `THEOGONY_TEST_NEO4J=1` gating pattern. Do **not** add a Windows or macOS matrix entry for serve-smoke; the lifespan is asyncio + uvicorn, both well-tested upstream on those platforms.

## Scope boundaries (do not touch)

- **`OneirosWorker`** — separate post-E8 etappe (E8.5). Wire the lifespan slot conditionally; do not implement the worker.
- **`/reports/{run_id}` HTTP endpoint** — Gen 2; document `theogony reports show` as the current path.
- **Detective Mode + `--detective` flag on `resolve`** — separate etappe gated on PHX-0041.
- **WebSocket / SSE progress streams on `/ingest`** — Gen 2.
- **Auth / API keys / rate limiting on the HTTP surface** — Gen 2 / deployment concern, not Gen 1 demo.
- **`/health?deep=true`** — Gen 2.
- **Hestia / Reviewer agent surfaces** — Week 4 / Gen 2.
- **Prompts directory packaging** — PHX-0049 (filed by Daedalus in the post-E8 reconciliation round). `theogony serve` and `theogony ask` rely on the editable-install layout for now; document the constraint in the README quickstart.
- **`ConstellationAssembler` N+1 neighbourhood probes** — PHX-0050 (filed by Daedalus). Use the existing assembler verbatim; do not optimise.

## Plan deviations to escalate (not anticipated, but if encountered)

- **uvicorn lifespan + reload incompatibility.** If you find that `--reload` breaks the lifespan in a way that makes dev iteration painful, document it in the PR body and ship `--reload` as a known-broken-with-lifespan flag (uvicorn issue, not ours). Do not start a Daedalus round for upstream bugs.
- **`theogony resolve` interactive flow + Typer prompt with `pytest`.** If `CliRunner` cannot drive the prompts cleanly, fall back to asserting `--non-interactive --pick=Q…` only and document the limitation. The interactive mode is operator-facing, not test-bound.
- **`/ingest` BackgroundTask + Neo4j connection lifecycle.** If the BackgroundTask outlives the request and the store is closed in the meantime, you'll see a `ServiceUnavailable`. The lifespan-owned store is correct (it lives across the BackgroundTask). Verify with the test; escalate only if the contract breaks.
- **`theogony serve` startup time on a cold machine.** BGE-small download + spaCy load + Neo4j driver + audit log open is ~5–15 s on a cold cache. Document in the panel-on-start. Do not add a "preload" command; the lifespan IS the preload.

## Done when

- `pytest tests/ -q` green; nine new test files pass.
- `THEOGONY_TEST_NEO4J=1 pytest -q` green (the api tests use InMemory; the existing Neo4j tests stay green).
- `ruff check src/ tests/`, `ruff format --check src/ tests/`, `mypy --strict src/theogony` all green.
- One end-to-end smoke captured in the PR body: `theogony serve &` + `curl localhost:8000/health` + `curl -X POST localhost:8000/query -d '{"q":"Wer war Sven Hedin?"}'` against a Neo4j store loaded by `theogony ingest 43497 --sentences 50`.
- One CLI smoke captured in the PR body: `theogony ask "Wer war Sven Hedin?"` rendered Rich panel with at least one `[AKA-…]` citation that resolves to a node in the constellation.
- `theogony resolve --list` shows a non-empty list against the same Neo4j ingest.
- `theogony reports list` and `theogony reports show <run_id>` find the query report from the smoke (carry-over verification — these commands already work from E6).
- PR body documents: deliverables vs Plan §5 E9 success criteria; the OneirosWorker-slot conditional wiring; the `theogony ingest --store` rewire; CLI single-file vs. package decision (and why); cross-references to PHX-0049/0050 for known constraints.

## Next after E9

The Plan §1 demo loop is fully closed after E9. Next candidates in priority order:

1. **E8.5 — Memory lifecycle** (`OneirosWorker` + `OneirosTickReport` + retention cap + lifespan wire-in). Fills the conditional slot E9 leaves open.
2. **PHX-0049 / PHX-0050** — production-readiness: prompts packaging + assembler N+1 batching. PHX-0042 query-plan audit kicks in here too (it was filed for "after E8 lands, against retrieval queries in their settled form" — E9 doesn't change retrieval shape, so the audit is unblocked the moment E9 ships).
3. **Detective Mode etappe** (conditional on PHX-0041 re-measurement).
4. **Week 4 demonstration** (Plan §5: full Gutenberg #944 ingest + screen recording + README update). The infrastructure is ready after E9; this is mostly orchestration + documentation.
