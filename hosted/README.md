# Hosted Theogony MCP (read-first + bounded growth)

This directory packages a **single-instance** MCP server over **HTTP/SSE**. The default image pre-seeds the bundled `pantheon_self` chronicle (the project’s own vision, doctrine, architecture, glossary, and prompts) into **memory** for a frictionless demo.

**Bounded writes:** the MCP tool `pantheon_chronicle_append` lets agents add short text fragments as new `KnowledgeNode` rows (embedded, `mcp_agent` provenance, `hypothesized` status) under strict size caps. There is still **no full Gutenberg ingest** over MCP (that remains the long-running API/CLI path).

**Persistence:** in the default container, appended nodes live in RAM with the seed and are lost on restart. For a Chronik that **keeps growing across deploys**, point the server at **Neo4j** and set `THEOGONY_MCP_SEED=0` (see *Persistent Neo4j on Fly* below).

## Cost expectations

- **Operator**: typically **under €5/month** on free tiers (one small VM; Fly.io shared CPU is enough for read-only traffic).
- **LLM**: the container image defaults to `THEOGONY_LLM__PROVIDER=stub`. There is **no** hosted LLM key in Phase 1; natural-language synthesis still requires a **local** install with a real provider + API keys, or PHX-0066 Phase 2 (per-call key pass-through when MCP supports it).

### What works on the stub LLM (`THEOGONY_LLM__PROVIDER=stub`)

- **`pantheon_status`**, **`pantheon_node`**, **`pantheon_reports_list`**, **`pantheon_reports_show`** — full read-side behaviour; no LLM calls.
- **`pantheon_ask`** — returns a **structured, citation-only** answer: honest header text plus the top **N** retrieved nodes by confidence (default **N = 6**, configurable via `THEOGONY_LLM__OFFLINE_TOP_N_CITATIONS`). No natural-language prose from a model; citations are grounded in the constellation.
- **Natural-language synthesis** — **not** available on stub. Set `THEOGONY_LLM__PROVIDER=anthropic` (or `gemini` / `openai`) and the matching `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, or `OPENAI_API_KEY` env var.

## Cockpit on hosted

The same container runs **FastAPI + MCP-SSE + Iris** when the build includes the cockpit package. After deploy, `https://<your-app>.fly.dev/cockpit` exists as a route; whether humans can use it depends entirely on env (see [`docs/COCKPIT.md`](../docs/COCKPIT.md)).

1. **Operator-only (default intent)** — leave `THEOGONY_COCKPIT__ENABLED=true` (default) with **`THEOGONY_COCKPIT__PUBLIC=false`** (default). The process still listens on `0.0.0.0:8080` for MCP, but cockpit routes return **403** when the request is not from loopback. Operators reach the UI via **SSH tunnel**, **Fly `proxy`**, or a **sidecar admin port** (e.g. bind cockpit settings to `127.0.0.1` on `8081` while MCP stays on `8080` — see cockpit settings in `COCKPIT.md`).
2. **Public URL with capped content** — set **`THEOGONY_COCKPIT__SAMPLE_ONLY=true`** so search, clusters, and report tables are capped to a fixed sample. You may still need **`THEOGONY_COCKPIT__PUBLIC=true`** plus an explicit **`THEOGONY_COCKPIT__BIND_HOST`** that matches how traffic arrives if you truly want the dashboard on the public listener; treat this as a **demo** posture, not a private chronicle browser.
3. **Full graph on a public listener (not recommended in Phase 1)** — would require **`THEOGONY_COCKPIT__PUBLIC=true`** without sample-only, exposing the same aggregations the operator sees. **No authentication ships in Phase 1** ([PHX-0074](../phoenix-backlog/PHX-0074.yaml)); prefer tunnel or split-port until Phase 2 auth lands.

## Build the image

From the **repository root** (so `pyproject.toml` and `src/` are in the build context):

```bash
docker build -f hosted/Dockerfile -t theogony-mcp:local .
```

The repository root `.dockerignore` matches `hosted/.dockerignore` (same ignore rules; plain `docker build` has no `--ignorefile` flag on older Docker engines). The root **`Dockerfile` is a symlink to `hosted/Dockerfile`** so tools that insist on `./Dockerfile` (including some Fly Depot builds) still run the correct recipe.

The image installs Theogony from the checkout (no PyPI publish required). Target size is **≤ ~500 MB** on lean CPU wheels; some platforms resolve a **large CUDA-enabled PyTorch** build (image can exceed 500 MB). Phase 2 may add a slimmer variant; for now prefer documenting the measured `docker images` size for your registry.

## Fly.io (primary path)

The reference deployment lives at **https://theogony-mcp.fly.dev/** (single-instance, read-only, `pantheon_self` seed). To run your own:

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) (`curl -L https://fly.io/install.sh | sh`) and log in (`fly auth signup` / `fly auth login`).
2. Pick a globally-unique app name and reserve it: `fly apps create <your-name>`. Then set `app = "<your-name>"` in `hosted/fly.toml` (the file is pre-pinned to `theogony-mcp`).
3. From the **repository root**, deploy via Fly's remote builder (no local Docker needed). Use either the root `fly.toml` (pins `hosted/Dockerfile` so `src/` is in the build context for hatchling) or the explicit flags:
   ```bash
   fly deploy --remote-only
   ```
   ```bash
   fly deploy -c hosted/fly.toml --dockerfile hosted/Dockerfile --remote-only
   ```
   If the image build fails with `file does not exist: src/theogony/__init__.py`, Fly is using a Dockerfile that only copied `pyproject.toml` — fix the app's `[build]` dockerfile path or deploy from an up-to-date checkout with the root `fly.toml` present.
   **`fly launch plan generate` (experimental)** can fail with: *launch manifest was created for a FastAPI app, but this is a Dockerfile app*. The hosted MCP image is **Dockerfile-first**; `fastapi` is only a library dependency. Regenerate the plan from the **repo root** so Fly reads your pinned build: `fly launch plan propose -c fly.toml -r <region> [--name <unique>]` and pass **only the JSON object** from that command’s stdout (strip any leading log lines) as the manifest to `generate`. Safer for this repo: skip `launch plan` and use **`fly deploy`** (or `fly deploy --build-only --push`) with the same `fly.toml`. Note: `generate` may rewrite `fly.toml` — review diffs or work on a branch.
   First build is **slow** (~30–40 min wall-clock end-to-end): pip install of CUDA-bundled PyTorch wheels takes ~8 min × 2 (multi-arch), layer export ~8 min × 2, push to `registry.fly.io` ~4 min, machine rollout ~30 s. Image lands at ~2.7 GB. Subsequent deploys with cached layers are much faster.
4. Health: `https://<your-app>.fly.dev/health` returns JSON (`status`, `embedding_model`, `node_count`, `edge_count`, `uptime_seconds`, `last_query_at`). For the `pantheon_self` seed expect `node_count=278`, `edge_count=1168`.
5. MCP SSE URL for clients: `https://<your-app>.fly.dev/sse` (POST JSON-RPC to the `endpoint` URL the SSE stream advertises under `/messages/`).

### Persistent Neo4j (Chronik keeps growing across deploys)

1. Provision **Neo4j Aura** (or any Bolt 5.x reachable from Fly) and note `URI`, user, password, database name.
2. **Fly secrets** (example names — match `Neo4jSettings` / `THEOGONY_NEO4J__*` in `src/theogony/config/settings.py`):
   - `THEOGONY_NEO4J__URI` — e.g. `neo4j+s://xxxx.databases.neo4j.io`
   - `THEOGONY_NEO4J__USER`, `THEOGONY_NEO4J__PASSWORD`, `THEOGONY_NEO4J__DATABASE` (often `neo4j`)
3. **Turn off the in-memory seed** so the process opens the real store:
   - `fly secrets set THEOGONY_MCP_SEED=0`
4. **Bootstrap once** (from any machine with the same Neo4j env): `theogony seed` imports the bundled `pantheon_self` dump into Neo4j, or skip and start from an empty graph.
5. **Redeploy** the app. Agents can then call MCP tool **`pantheon_chronicle_append`** to add vetted text fragments; they land as normal nodes and survive restarts.
6. Optional: `fly secrets set THEOGONY_MCP_APPEND__ENABLED=false` to disable appends on a fully public demo without touching rate limits.

The container reads **`HOST`** and **`PORT`**; defaults are `0.0.0.0` and `8080`. RAM: see the `[[vm]]` block in `hosted/fly.toml` (the sentence-transformer needs headroom on first `/sse` connect).

**No webhook auto-redeploy** in Phase 1 — run `fly deploy` manually when you cut a new image.

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
