# Iris Explorer — chat + animated d3 view of one query

> Phase 1 of "make the Chronik feel alive". A live, citation-anchored
> retrieval surface inside the cockpit at **`/cockpit/explorer`**.

## What it is

A second cockpit panel beside the existing Status / Knowledge / Clusters /
Reports / Manifest tabs. The user types a question; the Explorer UI POSTs to
**`/cockpit/api/ask-stream`** (SSE: phase events, then one ``complete`` event
with the full payload). **`/cockpit/api/ask`** is the same pipeline as a
single JSON response (tests, curl, agents). Both run the standard
:class:`~theogony.retrieval.pipeline.QueryPipeline` against whichever store
the cockpit is bound to (the same in-memory `pantheon_self` seed in the
demo, or a Neo4j-backed Chronik in a persistent deployment).

The response payload is shaped for direct visualisation:

| Field | Purpose |
|---|---|
| `answer.text` | Rendered prose (or empty string when running on the offline synthesizer) |
| `answer.cited_node_ids` | Highlighted in gold in the graph |
| `constellation.nodes` | Node id, label, type, layer, confidence, cluster |
| `constellation.edges` | Source/target/weight/relation + pheromone delta |
| `constellation.gaps` | Knowledge gaps the pipeline flagged |
| `query_embedding_preview` | First 32 components of the embedded query (for a sparkline) |
| `timing_ms` | `embed_ms` / `multi_hop_ms` / `synthesis_ms` / `total_ms` |
| `retrieval` | `seed_count`, `final_node_count`, `k`, `hops`, `strategy` |
| `entry_plan` | When LLM entry planning is on: `sub_queries`, `rationale`, `used_llm_planner`, `planner_duration_ms` |
| `verdict` | `QueryRunReport.verdict` |

## LLM Chronicle entry planner (optional)

When a **non-stub** LLM is configured and you set:

```bash
export THEOGONY_RETRIEVAL__CHRONICLE_ENTRY_PLANNER__ENABLED=true
```

the pipeline asks the model for several **short search strings** before
retrieval. Each string is embedded and run through multi-hop retrieval; hits
are **merged by best cosine score per node** so the Chronik is not anchored
only on the raw user question. The Explorer shows the chosen strings under
**Chronik-Einstieg**. Tunables: `THEOGONY_RETRIEVAL__CHRONICLE_ENTRY_PLANNER__MAX_SUB_QUERIES`
(1–8), `__MAX_CHARS_PER_SUB_QUERY`, `__MAX_PLANNER_TOKENS`.

## What you see

The right pane runs a **d3-force** simulation. Layers:

- **Pulse rings** radiate from the centre when a query starts (visual cue
  that the Chronik received the question).
- **Query node** (golden, fixed at the centre) connects via dashed
  amber edges to the **top seed** nodes (vector hits).
- **Constellation edges** are drawn as solid grey lines; edges connecting
  two **cited** nodes turn emerald.
- **Cited nodes** get an emerald body and a yellow ring; their labels
  are visible. Clicking any non-query node opens the Knowledge browser
  for that node id in a new tab.
- A small **vector signature** sparkline shows the first 32 components
  of the query embedding as a positive/negative bar chart.
- A **timing bar** breaks total latency into embed / retrieve / synth.

## Caps (ask / ask-stream)

The Explorer query endpoints clamp:

- `query` length ≤ 1 000 chars
- `k` ∈ [1, 25] (default 10)
- `hops` ∈ [0, 3] (default 2)

## Chronicle write-back (`POST /cockpit/api/chronicle-append`)

The **Save as hypothesis in Chronik** control calls this route with
`fragments: [{title, body}, …]` and optional `context_note`. It delegates to
the same :func:`theogony.chronicle.append_fragments.append_text_fragments` as
``pantheon_chronicle_append``, with ``origin="cockpit_explorer"`` (nodes get
``source_type=cockpit_curator`` and ``properties["origin"]`` set accordingly).

- **`McpAppendSettings`** caps and ``enabled`` apply (disable with
  ``THEOGONY_MCP_APPEND__ENABLED=false`` — the API returns HTTP 200 with an
  ``error`` string in JSON, same as the MCP tool).
- **`cockpit.sample_only`** returns **403** — no writes in sample-only demo
  mode.

## SSE shape (`/cockpit/api/ask-stream`)

Each event is one line ``data: <json>`` followed by a blank line:

| `type` | Fields |
|--------|--------|
| `phase` | `phase`: `embed` \| `retrieve` \| `synthesize`, `ms` |
| `complete` | `payload`: same object as `/cockpit/api/ask` |
| `error` | `message` |

## Why a separate JSON endpoint and not the existing `pantheon_ask` MCP tool?

`pantheon_ask` returns the same content over MCP for AI agents. The cockpit
endpoint adds the **visualisation-only** fields (`query_embedding_preview`,
denormalised `is_cited` flags, full `timing_ms` block) that an LLM client
does not need but a browser frontend does. Keeping the MCP tool slim
preserves the agent contract; keeping the JSON endpoint decoupled lets
the Explorer evolve without renegotiating MCP descriptors.

## Local persistence — one-line setup

The Explorer works against any `KnowledgeStore` mounted on the cockpit.
For a persistent local Chronik that grows across restarts:

```bash
docker compose up -d neo4j           # ships in docker-compose.yml
theogony seed                        # imports bundled pantheon_self into Neo4j
theogony serve                       # FastAPI app + cockpit at /cockpit/explorer
```

Hosted Fly currently runs the in-memory seed by default; flip to Neo4j
by setting `THEOGONY_MCP_SEED=0` and pointing `THEOGONY_NEO4J__*` at a
managed Neo4j (see `hosted/README.md`).

## Tests

`tests/cockpit/test_explorer.py` covers:

- HTML page renders with chat input, phase HUD, save control, and d3 mount point
- `POST /cockpit/api/ask` returns the rich JSON shape
- `POST /cockpit/api/ask-stream` returns SSE ending in `complete`
- `POST /cockpit/api/chronicle-append` upserts when append is enabled
- append is **403** when `cockpit.sample_only` is true
- empty query is rejected
- `k` / `hops` are clamped to safe bounds
