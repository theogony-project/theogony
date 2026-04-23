# W6 — Iris Cockpit Phase 1 (PHX-0074)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-22  
**Branch:** new branch off `main`, e.g. `feat/w6-iris-cockpit`  
**Scope:** one large PR (five panels in one cohesive surface; splitting them across PRs adds nav-consistency churn).  
**Predecessor:** Wave 1 closed; PHX-0070 fixed; W5 Mnemosyne brief landed (PR #67) and may be in-flight as code when this brief is picked up. W6 is the **first user-facing UI** Pantheon has ever shipped.

Direct brief, no Daedalus. Eight knobs are pre-locked. Sprint estimate: ≤ €2.00 of Composer execution (largest sprint to date, but still bounded).

---

## Why this etappe exists

Pantheon is rich in data and poor in Sicht. The W1 cluster machinery, W2 pheromone trails, W3 stub verdicts, W4 depth bands, the run-report pipeline, the bundled `pantheon_self` seed — all of it lives behind a CLI (`theogony reports list`) and a stack of `data/run_reports/*.json` files. The only humans who can read it today are humans who can grep JSON.

That gap is the first thing every potential adopter notices and the last thing they forgive. The PHX-0066 hosted-MCP path solved discovery for **agents**; this brief solves discovery for **humans**.

W6 ships **Phase 1 of Iris** — five read-mostly panels on a single-page dashboard:

1. **Status** — system overview, counts, layer + depth-band distribution, 24h activity, verdict mix.
2. **Knowledge Browser** — search, full node detail, Hover-Lupe sub-graph rendered with Cytoscape.js.
3. **Cluster Map** — list of clusters from W1, drill-down per cluster, cross-cluster edges highlighted.
4. **Reports** — tabbed table of every report type, click for full JSON.
5. **Manifest Editor** — single Markdown file declaring this instance's primary domain, language scope, exclusions.

Read-only on the chronicle by construction (the Manifest is the only write surface, and it writes a single file in `data/cockpit/`, not the chronicle). Default-bind to `127.0.0.1` so accidental public exposure is impossible. Sample-only mode for the operator who wants to demo the cockpit on a public deployment.

The panels share one Jinja2 layout, one Tailwind stylesheet, one HTMX integration, one optional Cytoscape.js dependency loaded only on the panels that need it. **No build pipeline, no React, no second repo.** Tech-stack choice is locked in Knob 1 below; the implementation reads as boring server-rendered HTML with HTMX swap-ins.

---

## Pre-locked design knobs (locked 2026-04-22)

### Knob 1 — Tech stack: HTMX + Tailwind (CDN) + Jinja2 + Cytoscape.js

The five components:

- **Jinja2** (already a transitive FastAPI dep) — server-rendered HTML templates.
- **Tailwind CSS via CDN** with subresource-integrity hash — `https://cdn.jsdelivr.net/npm/[email protected]/dist/tailwind.min.css` pinned. No build step.
- **HTMX** loaded as a single `<script>` tag (~14 KB) — `https://unpkg.com/[email protected]` pinned with SRI. Drives partial-page swaps for table updates, search results, drill-downs.
- **Cytoscape.js** loaded **only** on the Cluster Map and Knowledge Browser (Hover-Lupe) panels — `https://unpkg.com/[email protected]/dist/cytoscape.min.js` pinned. ~700 KB; lazy-loaded so the Status panel stays fast.
- **A small custom CSS file** (`static/css/cockpit.css`, ~150 lines) for the few patterns Tailwind doesn't cover cleanly.

**Rejected alternatives** (so this is not re-debated mid-sprint):

- ❌ **React / Next.js / Vue** — adds a build pipeline, second repo, second deploy artefact. Over-engineered for the scope.
- ❌ **Streamlit / Gradio** — fast to prototype, hard to make "hübsch", hard to integrate with the existing FastAPI auth seam.
- ❌ **Dash / Bokeh** — Python-native dashboards but visually dated; bad fit for the "this should look modern" requirement.
- ❌ **Tailwind via Tailwind-CLI build step** — more performant in production but adds the build pipeline we are explicitly avoiding. Phase-3 sub-ticket if CDN load times become a problem.
- ❌ **Inline Tailwind in `<style>` tags** — defeats Tailwind's purgeable-CSS model and leads to massive HTML payload growth.

### Knob 2 — Routing: `/cockpit` on the existing FastAPI app

The cockpit mounts as a sub-router on the existing FastAPI instance (`src/theogony/api/app.py`). Four routing concerns:

```
GET  /cockpit/                  → status panel (landing)
GET  /cockpit/browser           → knowledge browser
GET  /cockpit/browser/search    → HTMX-fragment search results
GET  /cockpit/browser/node/{id} → HTMX-fragment node detail + Hover-Lupe data
GET  /cockpit/clusters          → cluster map
GET  /cockpit/clusters/{id}     → HTMX-fragment cluster detail
GET  /cockpit/reports           → reports panel (default tab: query)
GET  /cockpit/reports/{type}    → HTMX-fragment report-type table
GET  /cockpit/reports/{type}/{run_id} → HTMX-fragment full-JSON view
GET  /cockpit/manifest          → manifest editor
POST /cockpit/manifest          → save manifest (atomic write + optional git commit)
GET  /cockpit/sse/status        → SSE channel for live status counters
GET  /cockpit/static/{path}     → static files (CSS, JS)
```

**No `/cockpit/api/...`** — the cockpit consumes the same Python service objects (KnowledgeStore, RunReportWriter aggregations) that the existing `/api/v1/...` routes use. The HTMX fragments come back as HTML, not JSON. No JSON API surface for the cockpit beyond what `/api/v1/*` already provides.

### Knob 3 — Read-only on the chronicle (one write surface: the manifest)

Allowed writes from any cockpit code path:

- ✅ `data/cockpit/manifest.md` (atomic write via temp+rename per the existing `RunReportWriter` pattern).
- ✅ `data/cockpit/manifest.history/<timestamp>.md` (one snapshot per save for trivial roll-back).

Forbidden writes (an enforcement test asserts):

- ❌ Any `KnowledgeNode` / `KnowledgeEdge` mutation (no upsert, no batch_update_scores, no delete).
- ❌ Any settings file mutation.
- ❌ Any `phoenix-backlog/` mutation.
- ❌ Any `prompts/` mutation.
- ❌ Any `data/run_reports/` mutation.

The router gets read-only KnowledgeStore + RunReportWriter dependencies via FastAPI's `Depends`. There is no shared write API path. The Manifest endpoint uses a dedicated `ManifestRepository` (Scope decision 5) that knows only how to write to `data/cockpit/`.

### Knob 4 — Default network binding: `127.0.0.1` + opt-in public + sample-only mode

Three defensive layers:

```python
class CockpitSettings(BaseModel):
    """Iris cockpit (PHX-0074 Phase 1)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True)
    bind_host: str = Field(default="127.0.0.1")
    bind_port: int | None = Field(default=None)  # None → mounted on the API port
    public: bool = Field(default=False)  # explicit opt-in for public exposure
    sample_only: bool = Field(default=False)
    sample_top_n_nodes: int = Field(default=20, ge=1, le=200)
    sample_recent_n_reports: int = Field(default=50, ge=1, le=500)
    manifest_path: Path = Field(default=Path("data/cockpit/manifest.md"))
    manifest_git_commit: bool = Field(default=False)
```

- **`enabled=True` + `bind_host="127.0.0.1"` + `public=False`** is the default → the cockpit is reachable only from the host the API runs on.
- **Mounting on the API port** (`bind_port=None`) is the default for hosted-MCP-style deployments.
- **A separate `bind_port`** lets operators run the cockpit on `:8081` while the public API stays on `:8080` (recommended for hosted-public deployments — see hosted/README.md update).
- **`public=True` AND `bind_host="0.0.0.0"`** is required for any public exposure. Setting only one without the other is a config error and raises at startup with a clear message.
- **`sample_only=True`** — every aggregation is capped to a fixed-size sample. Designed for the operator who wants `https://theogony-mcp.fly.dev/cockpit` to serve a public demo without exposing the full chronicle.

When the cockpit is reached via the public-bound API port AND `public=False`, every cockpit route returns `403 Forbidden` with a one-line explanation. The lifespan event-handler logs a startup banner that says **"Cockpit available at http://127.0.0.1:8080/cockpit"** so operators know the URL without reading docs.

### Knob 5 — Manifest contract: single Markdown file, atomic write, optional git commit, history snapshots

`data/cockpit/manifest.md` is **one Markdown file**. The cockpit reads it, the cockpit writes it, no other code in the project reads or writes it during Phase 1.

Default content (auto-created on first save if missing):

```markdown
# Manifest of <hostname>

## Primäre Wissensdomäne

(declare what knowledge this Pantheon instance is for)

## Sprachen

- Primär: <language>

## Ausschlüsse

(declare what this instance does NOT cover)

## Aktualisierungs-Verhalten

(declare how new knowledge is acquired)
```

The save endpoint:

1. Validates the body is valid UTF-8 + ≤ 64 KB.
2. Writes to `data/cockpit/manifest.md.tmp`, fsyncs, atomically renames to `manifest.md`.
3. Snapshots the previous content (if any) to `data/cockpit/manifest.history/<ISO-timestamp>.md`.
4. If `Settings.cockpit.manifest_git_commit = True`: runs `git add data/cockpit/manifest.md` + `git commit -m "manifest: <hostname> @ <timestamp>"` in the project repo. Optional and **default-off** because hosted deployments may not have git available.

The Phase-1 contract is "the Manifest is human-readable text the operator owns". Phase 2 ships **manifest-aware agents** (Mnemosyne and Curiosity Loop read it as additional context) — that is a separate sub-ticket on PHX-0074. Phase 1 just stores.

### Knob 6 — Auth: structural seam now, real auth in Phase 2

Every cockpit route declares an optional `authenticated_user` dependency:

```python
def get_authenticated_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> User | None:
    """Phase 1: always returns None. Phase 2 plugs in real auth here."""
    if settings.cockpit.auth_provider == "none":
        return None
    # Phase 2: dispatch to OIDC / GitHub-OAuth / basic-auth / password-file.
    raise NotImplementedError("Phase-2 auth")
```

`User` is a small Pydantic with `id`, `display_name`, `roles: list[str]`. In Phase 1 every route receives `user=None` and renders for an anonymous viewer. The seam exists so Phase 2 lands as a pure addition — every existing route already accepts the dependency.

`Settings.cockpit.auth_provider: Literal["none", "oidc", "github", "basic", "password_file"] = "none"` exists in Phase 1; only `"none"` is implemented; setting any other value raises `NotImplementedError` at startup with a clear "Phase 2 ships X — see PHX-0074" message.

### Knob 7 — Live update via SSE: only on Status, only four counters, 5s minimum

The Status panel subscribes to `/cockpit/sse/status` for live updates:

```
event: status_tick
data: {"node_count": 278, "edge_count": 1168, "queries_24h": 42, "verdict_mix": {"good": 30, "partial": 10, "poor": 2, "failed": 0}}
```

The server pushes one event every `Settings.cockpit.status_sse_interval_s` seconds (default 5, minimum 5, maximum 300). Counters are computed by aggregating from the existing `RunReportWriter` directories + the in-memory store stats; sub-100ms per tick on the bundled seed.

No SSE on other panels in Phase 1. Browser/Cluster/Reports/Manifest pages are page-load + HTMX-fragment-on-demand. Live updates on those panels are a Phase-2 sub-ticket.

### Knob 8 — Sample-only mode: bounded everything

When `Settings.cockpit.sample_only = True`:

- **Status panel**: counts are honest (the operator wants to show the real size), but per-cluster + per-source breakdowns are capped at top-`sample_top_n_nodes`.
- **Knowledge Browser**: search results capped at `sample_top_n_nodes`. Direct AKA-id lookups still resolve (otherwise the demo can't drill anywhere).
- **Cluster Map**: shows only the `sample_top_n_nodes` largest clusters; drill-down shows up to 20 members per cluster.
- **Reports panel**: shows only the latest `sample_recent_n_reports` per type.
- **Manifest Editor**: displayed but **read-only** in sample mode (POST returns `403 Forbidden`).

The mode is binary and applies globally — no per-panel override. Sample mode is the answer for "I want a public demo at `cockpit.theogony.example.com` without exposing the whole graph".

---

## Goal

After this PR:

- `src/theogony/cockpit/` exists as a new subpackage with the FastAPI router, Jinja2 templates, static assets, aggregations, and the Manifest repository.
- The existing FastAPI app mounts `/cockpit` when `Settings.cockpit.enabled` is `True` (default).
- All five panels render correctly against the bundled `pantheon_self` seed (the integration test + a screenshot smoke).
- `Settings.cockpit` group exists per Knob 4.
- `theogony cockpit serve [--host HOST] [--port PORT] [--sample-only]` CLI command exists for running the cockpit standalone (separate process from the API/MCP).
- `pyproject.toml` declares no new required dependencies (Jinja2 is already transitive); a small optional extra `pip install theogony[cockpit]` brings in `markdown-it-py` for the manifest editor's preview rendering (already installed via the docs-ingest path; declared explicitly here for documentation).
- New test directory `tests/cockpit/` with at least the routing-smoke + read-only-invariance + sample-mode tests.
- New `docs/COCKPIT.md` documents the architecture, panels, security model, sample mode, manifest contract.
- `docs/ARCHITECTURE.md` Memory section + `docs/HIVE.md` agent table + `docs/GLOSSARY.md` updated.
- `hosted/README.md` updated with a "Cockpit on hosted" section explaining how to expose it (or not).
- After deploy, `https://theogony-mcp.fly.dev/cockpit` is reachable when the operator opts in (or stays 403 if they don't).

---

## Scope decisions (read first)

### 1. Subpackage layout

```
src/theogony/cockpit/
├── __init__.py
├── router.py              # FastAPI router, all routes
├── aggregations.py        # read-side aggregation logic (status counters, depth-band distribution, etc.)
├── manifest.py            # ManifestRepository + atomic-write + history snapshots
├── sample_mode.py         # sample-only filter helpers
├── sse.py                 # /cockpit/sse/status handler
├── dependencies.py        # FastAPI dependencies (User auth seam, sample-mode wrapper)
├── templates/
│   ├── base.html          # layout (nav bar, footer)
│   ├── status.html        # Panel 1
│   ├── browser.html       # Panel 2 (page shell)
│   ├── clusters.html      # Panel 3 (page shell)
│   ├── reports.html       # Panel 4 (page shell)
│   ├── manifest.html      # Panel 5
│   └── partials/
│       ├── _node_card.html
│       ├── _hover_lupe.html        # Cytoscape mount point + JSON data
│       ├── _cluster_card.html
│       ├── _cluster_detail.html
│       ├── _report_row.html
│       ├── _report_full.html       # full-JSON view in side panel
│       ├── _status_metrics.html    # counters block (HTMX-swappable)
│       └── _search_results.html    # browser search results
└── static/
    ├── css/
    │   └── cockpit.css            # ~150 LoC custom CSS
    └── js/
        ├── cockpit.js             # HTMX helpers, theme toggle, etc. (~80 LoC)
        ├── cluster_graph.js       # Cytoscape integration (~120 LoC)
        ├── hover_lupe.js          # Hover-Lupe Cytoscape (~80 LoC)
        └── sse_status.js          # Status SSE consumer (~40 LoC)
```

### 2. Aggregation primitives — `aggregations.py`

Pure functions that read from the store + report writer + return small dataclasses. Cacheable later if needed; Phase 1 recomputes on each request (sub-100ms on the seed).

```python
@dataclass(frozen=True)
class StatusSnapshot:
    node_count: int
    edge_count: int
    store_backend: str
    embedding_model: str
    embedding_dim: int
    uptime_s: int
    layer_distribution: dict[str, int]      # "ephemera": 200, "mneme": 78
    depth_band_distribution: dict[int, int] # 0: 50, 1: 80, ..., 5: 20
    edge_type_distribution: dict[str, int]
    activity_24h: dict[str, int]            # "queries": 42, "ingests": 3, ...
    verdict_mix_24h: dict[str, int]         # "good": 30, "partial": 10, ...
    cost_summary_eur: dict[str, float]      # "today": 0.42, "week": 3.17, "month": 12.04


async def compute_status_snapshot(
    store: KnowledgeStore,
    writer: RunReportWriter,
    *,
    sample_mode: bool = False,
) -> StatusSnapshot:
    ...
```

Three sister aggregators ship in the same module:

```python
async def list_clusters_summary(
    store: KnowledgeStore,
    *,
    limit: int | None = None,
) -> list[ClusterSummaryView]: ...

async def list_recent_reports(
    writer: RunReportWriter,
    report_type: str,
    *,
    limit: int = 50,
    verdict_filter: str | None = None,
    since: datetime | None = None,
) -> list[ReportRowView]: ...

async def search_nodes(
    store: KnowledgeStore,
    *,
    query: str,
    limit: int = 20,
    node_type: NodeType | None = None,
    layer: Layer | None = None,
    cluster_id: str | None = None,
) -> list[NodeRowView]: ...
```

`ClusterSummaryView`, `ReportRowView`, `NodeRowView` are tiny Pydantic DTOs designed for template rendering (no embedding fields, no full sources, just enough to render a row).

### 3. Templates — Jinja2 with HTMX swap-targets

`base.html` is the shell:

```html
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Pantheon Cockpit{% endblock %}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/[email protected]/dist/tailwind.min.css"
        integrity="sha384-..." crossorigin="anonymous">
  <link rel="stylesheet" href="{{ url_for('cockpit_static', path='css/cockpit.css') }}">
  <script src="https://unpkg.com/[email protected]" integrity="sha384-..." crossorigin="anonymous"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen">
  {% include "partials/_navbar.html" %}
  <main class="max-w-7xl mx-auto px-4 py-6">
    {% block content %}{% endblock %}
  </main>
  <script src="{{ url_for('cockpit_static', path='js/cockpit.js') }}"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

Each panel template extends `base.html` and overrides `content` + optionally `scripts` (e.g. Cluster Map adds the Cytoscape script tag).

HTMX fragments are returned as plain HTML by routes returning `HTMLResponse`. Example:

```python
@router.get("/browser/search", response_class=HTMLResponse)
async def search_fragment(
    q: str = "",
    node_type: str | None = None,
    layer: str | None = None,
    store: KnowledgeStore = Depends(get_store),
) -> HTMLResponse:
    results = await search_nodes(store, query=q, node_type=node_type, layer=layer)
    return templates.TemplateResponse(
        "partials/_search_results.html",
        {"request": ..., "results": results},
    )
```

The browser panel's HTML form has `hx-get="/cockpit/browser/search" hx-target="#search-results" hx-trigger="input changed delay:300ms"` — no JS needed.

### 4. The Hover-Lupe — Cytoscape.js mount + JSON data inline

The Knowledge Browser's node-detail view embeds the depth-1 neighborhood as Cytoscape data:

```html
<div id="hover-lupe"
     data-graph='{{ hover_lupe_data | tojson | safe }}'
     class="w-full h-96 border border-slate-700 rounded">
</div>
<script src="https://unpkg.com/[email protected]/dist/cytoscape.min.js"
        integrity="sha384-..." crossorigin="anonymous"></script>
<script src="{{ url_for('cockpit_static', path='js/hover_lupe.js') }}"></script>
```

`hover_lupe.js` reads the inline JSON, instantiates Cytoscape with a force-directed layout, and renders nodes color-coded by `node_type`, edges weighted by `weight + pheromone_delta` (W2 effective weight). Click-on-node issues an HTMX request to the same endpoint with the new center → the page partial-refreshes.

`hover_lupe_data` is a dict with `nodes: list[{id, label, node_type, confidence}]` + `edges: list[{source, target, weight, relation_type}]`. Built server-side in the route from `KnowledgeStore.get_neighborhood`.

### 5. The Cluster Map — same pattern, different layout

The Cluster Map panel lists every `ClusterSummary` in a Tailwind grid. Each card shows: cluster_label (or short cluster_id), member_count, dominant_node_type, dominant_source_type. Click → drill-down loads `/cockpit/clusters/{id}` as an HTMX swap that:

1. Lists the top-20 members of the cluster.
2. Fetches the cluster's edges via `store.get_edges_among(member_ids)`.
3. Renders a Cytoscape graph with members as nodes, intra-cluster edges as black, cross-cluster edges (where target is outside the cluster) as red.

Phase 1 does **NOT** ship a 2D-projected centroid map — that needs UMAP and is the Phase-2 sub-ticket. Phase 1 is list + drill-down.

### 6. The Reports panel — tabbed table + side-panel JSON

```html
<div hx-get="/cockpit/reports/query" hx-trigger="load" hx-target="#report-table">
  <nav class="flex gap-2 border-b border-slate-700">
    <a hx-get="/cockpit/reports/query"      hx-target="#report-table" class="...">Queries</a>
    <a hx-get="/cockpit/reports/ingest"     hx-target="#report-table" class="...">Ingests</a>
    <a hx-get="/cockpit/reports/oneiros"    hx-target="#report-table" class="...">Oneiros</a>
    <a hx-get="/cockpit/reports/clustering" hx-target="#report-table" class="...">Clustering</a>
    <a hx-get="/cockpit/reports/blindspot"  hx-target="#report-table" class="...">Blindspots</a>
    <a hx-get="/cockpit/reports/mnemosyne"  hx-target="#report-table" class="...">Mnemosyne</a>
  </nav>
  <div id="report-table" class="mt-4"></div>
  <aside id="report-detail" class="..."></aside>
</div>
```

Each row has `hx-get="/cockpit/reports/{type}/{run_id}" hx-target="#report-detail"`. The detail fragment renders the full JSON in a `<pre>` block with syntax highlighting via a small Tailwind-compatible CSS class set (no library). Filter inputs (`verdict`, `since`) re-fire the table fragment.

### 7. The Manifest Editor — textarea + save button + history list

```html
<form hx-post="/cockpit/manifest"
      hx-target="#save-feedback"
      hx-swap="innerHTML"
      class="space-y-4">
  <textarea name="content" class="w-full h-96 font-mono bg-slate-800 ..." 
            maxlength="65536">{{ current_content }}</textarea>
  <div class="flex items-center justify-between">
    <span id="save-feedback"></span>
    <button type="submit" class="px-4 py-2 rounded bg-amber-600 hover:bg-amber-500">
      Save manifest
    </button>
  </div>
</form>

<aside class="mt-8">
  <h3>History</h3>
  <ul>
    {% for snapshot in history %}
      <li><a hx-get="/cockpit/manifest/history/{{ snapshot.timestamp }}" 
             hx-target="#manifest-textarea">{{ snapshot.timestamp }}</a></li>
    {% endfor %}
  </ul>
</aside>
```

A simple Markdown-preview toggle uses `markdown-it-py` server-side: client clicks "Preview" → HTMX request to `/cockpit/manifest/preview` with the current textarea content → returns rendered HTML in a side panel. No client-side Markdown library; keeps the JS surface tiny.

### 8. SSE for Status panel

```javascript
// static/js/sse_status.js
const sse = new EventSource("/cockpit/sse/status");
sse.addEventListener("status_tick", (event) => {
  const data = JSON.parse(event.data);
  // update each counter via .textContent on data-status-* elements
  document.querySelectorAll("[data-status-key]").forEach((el) => {
    const key = el.dataset.statusKey;
    if (key in data) el.textContent = data[key];
  });
});
```

Server-side handler:

```python
@router.get("/sse/status")
async def sse_status(
    store: KnowledgeStore = Depends(get_store_readonly),
    writer: RunReportWriter = Depends(get_writer),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    interval = max(5, settings.cockpit.status_sse_interval_s)

    async def event_generator():
        while True:
            snapshot = await compute_status_snapshot(store, writer)
            payload = {
                "node_count": snapshot.node_count,
                "edge_count": snapshot.edge_count,
                "queries_24h": snapshot.activity_24h.get("query", 0),
                "verdict_mix": snapshot.verdict_mix_24h,
            }
            yield {"event": "status_tick", "data": json.dumps(payload)}
            await asyncio.sleep(interval)

    return EventSourceResponse(event_generator())
```

`sse_starlette.EventSourceResponse` is already a transitive dep via the MCP server — no new dependency.

---

## Implementation plan (file-by-file)

### `src/theogony/cockpit/__init__.py` (new)

Re-exports `cockpit_router` and `mount_cockpit(app)`. ~30 lines.

### `src/theogony/cockpit/router.py` (new)

The FastAPI router with all routes from Knob 2 + Scope decisions 3-7. ~400 lines.

### `src/theogony/cockpit/aggregations.py` (new)

`StatusSnapshot`, `ClusterSummaryView`, `ReportRowView`, `NodeRowView` Pydantic DTOs + the four async aggregator functions per Scope decision 2. ~250 lines.

### `src/theogony/cockpit/manifest.py` (new)

`ManifestRepository` with `read()`, `save(content)`, `list_history()`, `read_snapshot(timestamp)`. Atomic write per Knob 5. ~120 lines.

### `src/theogony/cockpit/sample_mode.py` (new)

`SampleModeFilter` wraps the aggregators when `sample_only=True`. Pure decorator-style logic. ~60 lines.

### `src/theogony/cockpit/sse.py` (new)

The SSE status handler per Knob 7. ~40 lines.

### `src/theogony/cockpit/dependencies.py` (new)

FastAPI dependencies: `get_store_readonly` (returns the same KnowledgeStore but the route can audit it doesn't write), `get_writer`, `get_settings`, `get_authenticated_user` (returns None in Phase 1 per Knob 6), `get_sample_mode_filter`. ~80 lines.

### `src/theogony/cockpit/templates/` — 13 files

`base.html`, 5 panel templates, 7 partials. Total ~600 lines of HTML.

### `src/theogony/cockpit/static/css/cockpit.css` (new)

Custom CSS for what Tailwind doesn't cover cleanly — primarily syntax-highlighted `<pre>` blocks for the JSON view. ~150 lines.

### `src/theogony/cockpit/static/js/` — 4 files

`cockpit.js` (~80 LoC), `cluster_graph.js` (~120 LoC), `hover_lupe.js` (~80 LoC), `sse_status.js` (~40 LoC). Total ~320 lines of vanilla JS.

### `src/theogony/api/app.py`

In the lifespan or router-mounting section, add:

```python
from theogony.cockpit import mount_cockpit

if settings.cockpit.enabled:
    mount_cockpit(app, settings)
    log.info("cockpit available at http://%s:%d/cockpit",
             settings.cockpit.bind_host or "127.0.0.1",
             settings.cockpit.bind_port or settings.api.port)
```

If `cockpit.bind_port` is set AND differs from the API port, `mount_cockpit` spins up a second uvicorn instance on that port (mirrors the W6 brief's split-port pattern). Phase 1 honest scope: same-port mounting is the default and the recommended path; split-port works but is not load-tested.

### `src/theogony/config/settings.py`

Add `CockpitSettings` per Knob 4. Wire `cockpit: CockpitSettings = Field(default_factory=CockpitSettings)`.

### `src/theogony/cli.py`

Add `theogony cockpit serve [--host HOST] [--port PORT] [--sample-only]` subcommand. ~50 lines. Useful for running the cockpit standalone without spinning up the full API.

### `pyproject.toml`

Add an optional extra:

```toml
[project.optional-dependencies]
cockpit = [
  "markdown-it-py>=3.0.0",   # for manifest preview
]
```

(Most of what we need is already pulled in — Jinja2 via FastAPI, sse_starlette via MCP, pydantic everywhere. The cockpit extra is mainly documentation that Markdown rendering is the manifest editor's only optional dependency.)

### `tests/cockpit/__init__.py` (new)

Empty.

### `tests/cockpit/test_router.py` (new)

- `test_status_panel_renders_against_pantheon_self_seed` — boot test client, GET `/cockpit/`, assert HTML contains node count + edge count.
- `test_browser_search_returns_html_fragment_for_pantheon_query` — POST to `/cockpit/browser/search?q=Pantheon`, assert ≥ 1 `<a>` for cited node.
- `test_browser_node_detail_renders_hover_lupe_data` — GET `/cockpit/browser/node/AKA-b435daf2df24`, assert `data-graph` attribute is present and contains valid JSON.
- `test_clusters_panel_lists_clusters_after_recluster` — load seed, run one ReclusterPhase, GET `/cockpit/clusters`, assert ≥ 1 cluster card.
- `test_reports_panel_default_tab_is_query` — GET `/cockpit/reports`, assert HTMX preload of `/cockpit/reports/query`.
- `test_reports_show_returns_full_json_for_known_run_id` — write a synthetic QueryRunReport, GET `/cockpit/reports/query/<id>`, assert JSON in response.

### `tests/cockpit/test_manifest.py` (new)

- `test_manifest_first_save_creates_default_template` — POST to `/cockpit/manifest` with empty body, assert default template is written.
- `test_manifest_save_writes_atomically_and_snapshots_history` — save A, save B, assert manifest.md = B and history contains A.
- `test_manifest_save_rejects_oversize_body` — POST a 70 KB body, assert 413 Payload Too Large.
- `test_manifest_save_rejects_invalid_utf8` — POST raw bytes that are not valid UTF-8, assert 400.

### `tests/cockpit/test_sample_mode.py` (new)

- `test_sample_mode_caps_search_results_to_top_n`.
- `test_sample_mode_caps_recent_reports_to_n`.
- `test_sample_mode_blocks_manifest_save_with_403`.
- `test_sample_mode_status_panel_still_shows_real_counts` — counts stay honest, breakdowns get capped.

### `tests/cockpit/test_invisibility.py` (new — the read-only contract test)

The Knob-3 enforcement test. Mirrors `test_mnemosyne_invisibility.py` from W5:

1. Boot test client.
2. Snapshot store state (node count, edge count, all node labels, all confidences, all edge weights, all `properties` dicts).
3. GET every cockpit panel's main route + 5 representative HTMX fragments.
4. Snapshot store state again.
5. Assert: byte-for-byte identical. Cockpit must not have mutated any chronicle data.
6. Snapshot the `phoenix-backlog/`, `prompts/`, `data/run_reports/` directories.
7. Same assertion: byte-identical after the cockpit traffic.

### `tests/cockpit/test_security.py` (new)

- `test_public_false_blocks_external_origin` — fake-set host to "external.example.com", assert 403.
- `test_public_true_allows_external_origin`.
- `test_only_setting_public_without_bind_host_raises_at_startup` — config-validation test.
- `test_sample_only_mode_warning_in_status_panel` — when `sample_only=True`, the status panel renders a small banner saying "Sample-only mode active; data is filtered."

### `tests/cockpit/test_sse.py` (new)

- `test_sse_status_emits_event_within_interval` — connect, wait for one event, assert payload shape.
- `test_sse_status_respects_minimum_interval` — set interval to 1s, assert it gets clamped to 5s.

### Documentation touches

1. `docs/COCKPIT.md` (new, ~250 lines): architecture, panel-by-panel walkthrough with screenshots (text-described for Phase 1 — operators capture real ones after deploy), security model, sample-only mode, manifest contract, the Phase-2 / Phase-3 roadmap from PHX-0074. Includes a "Run it locally" quickstart + a "Run it on hosted" snippet.

2. `docs/ARCHITECTURE.md`: short paragraph in a new "Mortal-Facing Surfaces" section: Cockpit (Iris, PHX-0074) is the human-facing dashboard; CLI (`theogony …`) is the operator surface; MCP is the agent surface. Cross-reference docs/COCKPIT.md.

3. `docs/HIVE.md` agent table: add Iris row in the **Presentation** category (sister to Eris/Nemesis/Asklepios/Mnemosyne in the Auditor category but distinct — Iris doesn't audit, she renders).

4. `docs/GLOSSARY.md`: Cockpit entry, Manifest entry, Sample-Only-Mode entry.

5. `docs/PHOENIX_BACKLOG.md`: PHX-0074 catalogue entry gets the "Phase 1 closed by W6 (PR #...)" closing note.

6. `hosted/README.md`: new "Cockpit on hosted" section with three example deployments — operator-only (default), public-with-sample-only, full-public-with-future-auth (warning that auth is Phase 2).

7. `docs/QUESTIONS_FROM_THE_FIELD.md`: log the Cockpit conversation as the third entry, citing PHX-0074 as the outcome.

---

## Cost-benefit considerations

**Token cost**: largest sprint to date but bounded. Estimate breakdown:

- Backend code: ~600 LoC (router, aggregations, manifest, sse, sample_mode, dependencies, settings, CLI).
- Frontend code: ~600 LoC HTML templates + ~320 LoC JS + ~150 LoC CSS = ~1070 LoC of UI.
- Tests: ~400 LoC across 6 new test files.
- Docs: ~400 LoC.

Total: ~2500 LoC. Estimate ≤ €2.00 of Composer execution. Larger than W4 (the previous biggest), justified by being a whole new surface category.

**Runtime cost**:

- Cockpit routes are **on-demand**: zero overhead when nobody is browsing.
- SSE status channel: one push every 5+ seconds when at least one client is connected. Aggregation cost ≤ 100 ms on the bundled seed.
- Cytoscape.js loads only on Cluster Map + Hover-Lupe (~700 KB lazy). Tailwind via CDN (~100 KB cached after first load).
- Memory: negligible (Jinja2 templates compiled once at import time).
- Disk: manifest history snapshots accumulate at one per save. Phase-1 honest scope: no automatic prune; document a small `theogony cockpit prune-history --keep 50` for operators.

**Failure modes worth watching**:

- **CDN dependency on first page load**: if `cdn.jsdelivr.net` or `unpkg.com` is unreachable, the cockpit renders unstyled HTML. SRI hashes prevent silent corruption but not unavailability. Operator who needs offline must build a `static/css/tailwind-pinned.css` + `static/js/htmx-pinned.js` and patch the templates — document the procedure.
- **Tailwind via CDN ships ~3 MB of CSS** (the full Tailwind, before purging). Acceptable for Phase 1 demo; a Phase-2 sub-ticket builds a purged minimal CSS.
- **Cytoscape rendering on huge clusters**: drill-down on a cluster with 500 members would saturate Cytoscape. Phase 1 caps drill-down at top-N members per cluster (`Settings.cockpit.cluster_drill_max_members`, default 50). Document the cap; Phase 2 may add pagination.
- **Manifest race condition on concurrent saves**: the atomic-rename pattern is single-writer-safe. Two operators saving simultaneously: last-writer-wins; the loser sees their save succeeded but the on-disk content is the other's. History snapshots make rollback trivial. Phase-1 honest scope; Phase 2 may add an ETag.
- **SSE connection leak**: client disconnects without closing the EventSource. The server's `EventSourceResponse` handles teardown via cancellation propagation, but a misbehaving proxy can hold idle connections open. Cap at `Settings.cockpit.sse_max_concurrent_clients` (default 50).
- **Read-only contract violation**: the test `tests/cockpit/test_invisibility.py` is the regression gate. Any change to a route that accidentally introduces a write path will fail it.
- **Sample-mode bypass via direct AKA-id lookup**: by design, direct lookups still resolve in sample mode. Document that sample mode hides aggregation surfaces but does not hide individual nodes by id — that is the right trade-off for "demo without exposing aggregate stats" but not for "hide specific nodes from the public" (which needs Phase-2 auth).

---

## Out of scope (do not do)

- **Do not** add authentication. Phase 1 is operator-only via 127.0.0.1 binding + sample-only opt-in. Phase 2 ships real auth via the structural seam from Knob 6.
- **Do not** add settings editing. Phase 1 displays settings read-only; Phase 2 ships propose-and-review.
- **Do not** add resource controls (LLM budget caps, throttling sliders). Phase 3 territory.
- **Do not** add UMAP / t-SNE 2D cluster centroid projection. Phase 2 sub-ticket.
- **Do not** add live updates to Browser/Cluster/Reports/Manifest panels. Phase 2 sub-ticket. Phase 1 SSE is Status-only.
- **Do not** add a mobile-first responsive design. Tailwind handles basic responsiveness for free; Phase 2 may polish.
- **Do not** add a multi-tenant federated view. PHX-0061 dependency; Phase 3.
- **Do not** add internationalisation. Phase 1 ships in English (with a German manifest example noted). i18n is a Phase-3 sub-ticket.
- **Do not** add user-customisable dashboards / saved views / pinned queries. Phase 2 sub-ticket once usage patterns emerge.
- **Do not** add a build pipeline (npm, Webpack, Vite). The whole tech-stack choice in Knob 1 is to avoid this.
- **Do not** introduce new backend dependencies beyond `markdown-it-py` (already a transitive dep; declared explicitly for clarity).
- **Do not** add MCP tools that drive the cockpit (e.g., `pantheon_cockpit_open`). The cockpit is human-facing; agents go through MCP. Cross-surface tools mix concerns.
- **Do not** rebuild the existing CLI surface as a cockpit panel. The CLI stays the operator interface; the cockpit is the human-curiosity interface. Some commands (`recluster`, `oneiros tick`) intentionally have no UI — they are scriptable and that is correct.

---

## Done when

- [ ] `src/theogony/cockpit/` exists with the layout from Scope decision 1.
- [ ] All five panels render correctly against the bundled `pantheon_self` seed.
- [ ] `Settings.cockpit` group exists per Knob 4.
- [ ] Default binding is `127.0.0.1` and `public=False`; setting only one of the two raises at startup.
- [ ] `theogony cockpit serve [--host HOST] [--port PORT] [--sample-only]` works.
- [ ] All existing tests stay green without modification (full `pytest -q`).
- [ ] All new tests pass: `tests/cockpit/test_router.py`, `tests/cockpit/test_manifest.py`, `tests/cockpit/test_sample_mode.py`, `tests/cockpit/test_invisibility.py`, `tests/cockpit/test_security.py`, `tests/cockpit/test_sse.py`.
- [ ] `tests/cockpit/test_invisibility.py` is the read-only contract gate; **must pass byte-identical**.
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy --strict` clean on `src/theogony/cockpit/`.
- [ ] `docs/COCKPIT.md` exists; `docs/ARCHITECTURE.md`, `docs/HIVE.md`, `docs/GLOSSARY.md`, `docs/PHOENIX_BACKLOG.md`, `hosted/README.md`, `docs/QUESTIONS_FROM_THE_FIELD.md` updated.
- [ ] PR title: `feat(cockpit): W6 — Iris Phase 1 (PHX-0074)`. PR body includes the eight resolved knobs, the read-only contract test result, and a description of the visual delta (which panels are visible at `http://127.0.0.1:8080/cockpit` after the change).

---

## After this PR

W6 closes Iris Phase 1. Pantheon now has a **mortal-facing surface**. The operator can finally *see* the chronicle without grepping JSON. Every future architectural decision becomes easier to communicate because there is a screenshot to point at.

Phase 2 sub-tickets (file separately when this lands):

- **Auth + RBAC** — replaces the `User=None` seam from Knob 6 with real authentication.
- **Settings editor** — propose-and-review workflow mirroring Proteus pattern.
- **Manifest-aware Mnemosyne / Curiosity Loop** — the manifest becomes additional context for those agents.
- **2D cluster centroid map** — UMAP-projected SVG on top of the Cluster Map panel.
- **Live Browser/Cluster/Reports/Manifest updates** — extend SSE beyond the Status panel.

Phase 3 sub-tickets:

- Resource management UI (budget caps, throttle sliders).
- Multi-tenant federated cockpit (PHX-0061 dependency).
- Mobile-first responsive design.

W7 candidates after Iris ships (operator picks):

- **PHX-0072 Proteus Phase 1** — twin-agent A/B testing for prompt evolution.
- **PHX-0073 Asklepios Phase 1** — auditor-finding triage to fix tickets.
- **PHX-0002 Phase 1** — heterogeneous embedding spaces (additive schema + per-modality vector_search filter).
- **PHX-0061 Vector-Routed Federation** — the strategic Wave-2 sprint that turns Pantheon from one chronicle into the protocol for many.
- **PHX-0069 Fly SSE session affinity** — operational; needed before any horizontal-scale hosted demo.
