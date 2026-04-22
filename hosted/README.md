# Hosted Theogony MCP (read-only)

This directory packages a **single-instance, read-only** MCP server over **HTTP/SSE**, pre-seeded with the bundled `pantheon_self` chronicle (the project’s own vision, doctrine, architecture, glossary, and prompts). There is **no ingest surface** in Phase 1 — the corpus is the seed only.

## Cost expectations

- **Operator**: typically **under €5/month** on free tiers (one small VM; Fly.io shared CPU is enough for read-only traffic).
- **LLM**: the container image defaults to `THEOGONY_LLM__PROVIDER=stub`. For real answers via `pantheon_ask`, callers must use a **local** install with API keys, or wait for PHX-0066 Phase 2 (per-call key pass-through when MCP supports it). Until then, `pantheon_node`, `pantheon_status`, and the report tools work without a live LLM.

## Build the image

From the **repository root** (so `pyproject.toml` and `src/` are in the build context):

```bash
docker build -f hosted/Dockerfile -t theogony-mcp:local .
```

The repository root `.dockerignore` matches `hosted/.dockerignore` (same ignore rules; plain `docker build` has no `--ignorefile` flag on older Docker engines).

The image installs Theogony from the checkout (no PyPI publish required). Target size is **≤ ~500 MB** on lean CPU wheels; some platforms resolve a **large CUDA-enabled PyTorch** build (image can exceed 500 MB). Phase 2 may add a slimmer variant; for now prefer documenting the measured `docker images` size for your registry.

## Fly.io (primary path)

The reference deployment lives at **https://theogony-mcp.fly.dev/** (single-instance, read-only, `pantheon_self` seed). To run your own:

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) (`curl -L https://fly.io/install.sh | sh`) and log in (`fly auth signup` / `fly auth login`).
2. Pick a globally-unique app name and reserve it: `fly apps create <your-name>`. Then set `app = "<your-name>"` in `hosted/fly.toml` (the file is pre-pinned to `theogony-mcp`).
3. From the **repository root**, deploy via Fly's remote builder (no local Docker needed):
   ```bash
   fly deploy -c hosted/fly.toml --dockerfile hosted/Dockerfile --remote-only
   ```
   First build is **slow** (~30–40 min wall-clock end-to-end): pip install of CUDA-bundled PyTorch wheels takes ~8 min × 2 (multi-arch), layer export ~8 min × 2, push to `registry.fly.io` ~4 min, machine rollout ~30 s. Image lands at ~2.7 GB. Subsequent deploys with cached layers are much faster.
4. Health: `https://<your-app>.fly.dev/health` returns JSON (`status`, `embedding_model`, `node_count`, `edge_count`, `uptime_seconds`, `last_query_at`). For the `pantheon_self` seed expect `node_count=278`, `edge_count=1168`.
5. MCP SSE URL for clients: `https://<your-app>.fly.dev/sse` (POST JSON-RPC to the `endpoint` URL the SSE stream advertises under `/messages/`).

The container reads **`HOST`** and **`PORT`**; defaults are `0.0.0.0` and `8080`. The pinned `[[vm]]` block in `hosted/fly.toml` requests **1 GB RAM** — the sentence-transformer loads ~400 MB on first `/sse` connect, so the default 256 MB OOMs on cold start.

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
