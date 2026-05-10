# Hosted Theogony MCP (read-first + bounded growth)

This directory packages a **single-instance** MCP server over **HTTP/SSE**. The default image pre-seeds the bundled `pantheon_self` chronicle (the project’s own vision, doctrine, architecture, glossary, and prompts) into **memory** for a frictionless demo.

**Bounded writes:** the MCP tool `pantheon_chronicle_append` lets agents add short text fragments as new `KnowledgeNode` rows (embedded, `mcp_agent` provenance, `hypothesized` status) under strict size caps. There is still **no full Gutenberg ingest** over MCP (that remains the long-running API/CLI path).

**Persistence:** in the default container, appended nodes live in RAM with the seed and are lost on restart. For a Chronik that **keeps growing across deploys**, point the server at **Neo4j** and set `THEOGONY_MCP_SEED=0` (see *Persistent Neo4j* below).

## Cost expectations

- **Operator**: typically **under €5/month** on free tiers (one small shared-CPU VM is enough for read-only traffic).
- **LLM**: the container image defaults to `THEOGONY_LLM__PROVIDER=stub`. There is **no** hosted LLM key in Phase 1; natural-language synthesis still requires a **local** install with a real provider + API keys, or PHX-0066 Phase 2 (per-call key pass-through when MCP supports it).

### What works on the stub LLM (`THEOGONY_LLM__PROVIDER=stub`)

- **`pantheon_status`**, **`pantheon_node`**, **`pantheon_reports_list`**, **`pantheon_reports_show`** — full read-side behaviour; no LLM calls.
- **`pantheon_ask`** — returns a **structured, citation-only** answer: honest header text plus the top **N** retrieved nodes by confidence (default **N = 6**, configurable via `THEOGONY_LLM__OFFLINE_TOP_N_CITATIONS`). No natural-language prose from a model; citations are grounded in the constellation.
- **Natural-language synthesis** — **not** available on stub. Set `THEOGONY_LLM__PROVIDER=anthropic` (or `gemini` / `openai`) and the matching `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, or `OPENAI_API_KEY` env var.

## Cockpit on hosted

The same container runs **FastAPI + MCP-SSE + Iris** when the build includes the cockpit package. After deploy, `https://<your-public-base-url>/cockpit` exists as a route when you expose the service; whether humans can use it depends entirely on env (see [`docs/COCKPIT.md`](../docs/COCKPIT.md)).

1. **Operator-only (default intent)** — leave `THEOGONY_COCKPIT__ENABLED=true` (default) with **`THEOGONY_COCKPIT__PUBLIC=false`** (default). The process still listens on `0.0.0.0:8080` for MCP, but cockpit routes return **403** when the request is not from loopback. Operators reach the UI via **SSH tunnel**, **your platform’s private networking / port-forward**, or a **sidecar admin port** (e.g. bind cockpit settings to `127.0.0.1` on `8081` while MCP stays on `8080` — see cockpit settings in `COCKPIT.md`).
2. **Public URL with capped content** — set **`THEOGONY_COCKPIT__SAMPLE_ONLY=true`** so search, clusters, and report tables are capped to a fixed sample. You may still need **`THEOGONY_COCKPIT__PUBLIC=true`** plus an explicit **`THEOGONY_COCKPIT__BIND_HOST`** that matches how traffic arrives if you truly want the dashboard on the public listener; treat this as a **demo** posture, not a private chronicle browser.
3. **Full graph on a public listener (not recommended in Phase 1)** — would require **`THEOGONY_COCKPIT__PUBLIC=true`** without sample-only, exposing the same aggregations the operator sees. **No authentication ships in Phase 1** ([PHX-0074](../phoenix-backlog/PHX-0074.yaml)); prefer tunnel or split-port until Phase 2 auth lands.

## Build the image

From the **repository root** (so `pyproject.toml` and `src/` are in the build context):

```bash
docker build -f hosted/Dockerfile -t theogony-mcp:local .
```

The repository root `.dockerignore` matches `hosted/.dockerignore` (same ignore rules; plain `docker build` has no `--ignorefile` flag on older Docker engines). The root **`Dockerfile` is a symlink to `hosted/Dockerfile`** so tools that insist on `./Dockerfile` (including some remote builders) still run the correct recipe.

The image installs Theogony from the checkout (no PyPI publish required). Target size is **≤ ~500 MB** on lean CPU wheels; some platforms resolve a **large CUDA-enabled PyTorch** build (image can exceed 500 MB). Phase 2 may add a slimmer variant; for now prefer documenting the measured `docker images` size for your registry.

## Run the image (any container host)

The default path is: **build** (above), **push** to your registry (if needed), then **run** on Kubernetes, a VPS, or another container host you operate. There is **no** organisation-operated public demo URL you should rely on; run your own image or use Fly (below) with **your** app name. Historical Phoenix tickets may still mention an old `*.fly.dev` hostname for context.

Example local smoke:

```bash
docker run --rm -p 8080:8080 theogony-mcp:local
```

Then `GET http://localhost:8080/health` and point an MCP client at `http://localhost:8080/sse` (POST JSON-RPC to the `endpoint` URL the SSE stream advertises under `/messages/`).

First cold build can be **slow** on some hosts (large PyTorch wheels, multi-arch). Prefer documenting the measured `docker images` size for your registry.

### Persistent Neo4j (Chronik keeps growing across deploys)

1. Provision **Neo4j Aura** (or any Bolt 5.x reachable from the container) and note `URI`, user, password, database name.
2. Inject secrets the way your platform expects (Kubernetes `Secret`, PaaS env UI, …). Names must match `Neo4jSettings` / `THEOGONY_NEO4J__*` in `src/theogony/config/settings.py`, for example:
   - `THEOGONY_NEO4J__URI` — e.g. `neo4j+s://xxxx.databases.neo4j.io`
   - `THEOGONY_NEO4J__USER`, `THEOGONY_NEO4J__PASSWORD`, `THEOGONY_NEO4J__DATABASE` (often `neo4j`)
3. Set **`THEOGONY_MCP_SEED=0`** so the process opens the real store instead of re-seeding memory.
4. **Bootstrap once** (from any machine with the same Neo4j env): `theogony seed` imports the bundled `pantheon_self` dump into Neo4j, or skip and start from an empty graph.
5. **Restart / redeploy** the container. Agents can then call MCP tool **`pantheon_chronicle_append`** to add vetted text fragments; they land as normal nodes and survive restarts.
6. Optional: set `THEOGONY_MCP_APPEND__ENABLED=false` to disable appends on a fully public demo without touching rate limits.

The container reads **`HOST`** and **`PORT`**; defaults are `0.0.0.0` and `8080`. **Memory:** the sentence-transformer loads on first `/sse` connect; allow **about 1 GB RAM** or more in production-like deployments.

**No webhook auto-redeploy** in Phase 1 — redeploy manually when you cut a new image.

## Fly.io (optional)

The repo ships **`fly.toml`** (root) and **`hosted/fly.toml`** for operators who deploy on [Fly.io](https://fly.io/). This is **not** required for local Docker or other hosts.

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) and log in.
2. Reserve an app name (`fly apps create <name>`) and set `app = "<name>"` in `hosted/fly.toml` if it still shows a placeholder.
3. From the **repository root**:
   ```bash
   fly deploy --remote-only
   ```
   or explicitly:
   ```bash
   fly deploy -c hosted/fly.toml --dockerfile hosted/Dockerfile --remote-only
   ```
   Root `fly.toml` pins `hosted/Dockerfile` so hatchling sees `src/` during the image build. First full build can be **slow** (large wheels / multi-arch); see Fly build logs for timing.
4. Health and MCP: `https://<your-app>.fly.dev/health` and `https://<your-app>.fly.dev/sse` (same JSON-RPC + `/messages/` pattern as in the generic path above).

For **Neo4j** on Fly, use `fly secrets set` with the same `THEOGONY_NEO4J__*` / `THEOGONY_MCP_SEED` variable names as in *Persistent Neo4j* above. RAM hints live in the `[[vm]]` block in `hosted/fly.toml`.

## Hugging Face Spaces (Docker)

1. Create a **Docker** Space and push this repo (or a fork).
2. Set the Space **Dockerfile path** to `hosted/Dockerfile` and build context to the **repository root**.
3. Expose port **8080** (or set `PORT` to the Space’s required port and align the Space UI setting).
4. Point your MCP client at `https://<user>-<space>.hf.space/sse` (or the Space URL your UI shows).

## Modal (sketch)

Wrap the same container command in a Modal `@web_server` that exposes port 8080, or run `theogony mcp --transport sse --seed --host 0.0.0.0 --port $MODAL_PORT` inside a Modal image built from `hosted/Dockerfile`. Modal’s port wiring differs by template — set `PORT`/`HOST` to match Modal’s proxy.

## Smithery

1. After deploy, fill `HOSTED_URL` in `hosted/smithery.yaml` (or paste the public base URL in Smithery’s UI).
2. Register the server on [Smithery](https://smithery.ai/) and validate the manifest (YAML + tool list).

## Monitoring

- **`GET /health`**: JSON snapshot (`version`, `store`, embedding model id + `@v1`, counts, `uptime_seconds`, `last_query_at` after the first successful MCP POST under `/messages/`).

## Rate limits

Defaults: **60/hour** and **1000/day** per client IP (rolling windows). Tune with:

- `THEOGONY_HOSTED__RATE_LIMIT_PER_HOUR`
- `THEOGONY_HOSTED__RATE_LIMIT_PER_DAY`
- `THEOGONY_HOSTED__RATE_LIMIT_BYPASS_TOKEN` (optional secret; send header `X-Theogony-RateLimit-Bypass` with the same value to skip limits for trusted callers).

Set `THEOGONY_HOSTED__RATE_LIMIT_PER_HOUR=0` to **disable** rate limiting entirely.

## Phase 2 (not this PR)

- GitHub webhook → automatic redeploy  
- Per-call LLM API key pass-through (when MCP standardises it)  
- Federation / Hestia-hosted auditing per separate Phoenix tickets  

## spaCy

The hosted image **does not** run `python -m spacy download …`. The bundled seed is already extracted; only the sentence-transformer embedder loads at startup.
