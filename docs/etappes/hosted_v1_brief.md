# Hosted v1 — `hosted/` subdirectory + Dockerfile + SSE transport + Smithery manifest

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-21  
**Branch:** new branch off `main`, e.g. `feat/hosted-mcp-v1`  
**Scope:** one PR, tightly scoped  
**Predecessor:** PR #37 (MCP server), PR #40 (`pantheon_self` seed). PHX-0066 is the parent vision ticket; this etappe is its **Phase 1** — the minimum viable hosted setup the operator can deploy themselves to Fly.io and list on Smithery.

Direct brief, no Daedalus. This is a deployment / packaging etappe, not an architectural decision round.

---

## Why this etappe exists

PHX-0037 (MCP server) and PHX-0040 (Pantheon-of-Pantheon seed) shipped the substrate. Today an operator can run `theogony mcp` over stdio against a freshly-seeded chronicle. But:

1. **stdio transport only** — works for desktop hosts (Claude Desktop, Cursor) but not for an HTTP-reachable hosted service. To put Pantheon on a public URL that AI agents can hit, we need an **SSE transport** (Server-Sent Events) on the MCP server.
2. **No deploy artefacts** — there is no Dockerfile, no container image, no Smithery manifest, no deploy guide. Every prospective operator would have to reinvent the wheel.
3. **No seed-on-startup helper** — `theogony mcp` today expects a pre-seeded store. A hosted single-instance service that boots fresh needs to seed itself before serving its first request.

This PR fixes those three gaps. It does **not** ship the public deployment itself — that is the operator's manual `flyctl deploy` step, with their own credentials. It ships the artefacts that make that deploy a single-command operation.

---

## Goal

After this PR:

- `theogony mcp --transport sse --host 0.0.0.0 --port 8080` runs the MCP server over HTTP/SSE.
- `theogony mcp --seed-from <path>` (or `--seed`, defaulting to the bundled `pantheon_self` dump) loads the seed into the in-memory store before opening the MCP transport.
- `hosted/Dockerfile` produces a container image (target ≤ 500 MB) that the operator deploys to Fly.io / HuggingFace Spaces / Modal in one command.
- `hosted/smithery.yaml` lists the service for the Smithery MCP registry.
- `hosted/README.md` walks the operator through the Fly.io deploy in under 10 minutes, with HuggingFace Spaces and Modal as alternatives.
- A smoke test verifies the SSE transport actually serves an MCP `tools/list` request end-to-end inside an integration test.

---

## Scope decisions (read first)

### 1. SSE transport via the official `mcp` SDK

The `mcp` extra (already in `pyproject.toml`) ships `mcp.server.sse.SseServerTransport`. Use it. Do not invent a custom HTTP wrapper.

The canonical pattern (verified against the MCP Python SDK docs):

```python
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route
import uvicorn

async def run_sse(server, host: str, port: int) -> None:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_inst = uvicorn.Server(config)
    await server_inst.serve()
```

**Note on `request._send`**: Starlette deprecated this access path in 0.40+. Use the public `request.receive_send_pair()` if available, otherwise fall back to `request._send` with a noqa comment referencing the upstream issue (the MCP SDK's own examples currently use `_send` until they migrate; track upstream).

`starlette` and `uvicorn` are **already** in the dependency tree (`uvicorn[standard]` is a core dep; `starlette` comes via `fastapi`). No new top-level dependency is needed.

### 2. New CLI flags on `theogony mcp`

Extend `src/theogony/cli.py:mcp` to accept:

```python
--transport [stdio|sse]  # default stdio (preserves current behaviour)
--host TEXT              # SSE only; default 127.0.0.1
--port INTEGER           # SSE only; default 8080
--seed / --no-seed       # default --no-seed (preserves current behaviour)
--seed-from PATH         # default = bundled pantheon_self dump
```

When `--transport stdio` (the default), `--host` and `--port` are ignored with a single info-log line ("stdio transport: --host/--port ignored").

When `--transport sse`, the host binds. Default `127.0.0.1` (local-first principle); the hosted Dockerfile overrides to `0.0.0.0`.

When `--seed`, the server loads the bundled `pantheon_self` seed into the in-memory store before opening the transport. Implementation: reuse the existing seed-load path from `theogony seed`'s implementation. Wire it into the MCP server's `open_resources` lifespan **before** the `yield`, so the first MCP `tools/call` already has the chronicle populated.

### 3. New `hosted/` subdirectory at repo root

```
hosted/
├── Dockerfile
├── README.md
├── smithery.yaml
├── fly.toml         # Fly.io app config; not committed with credentials
└── .dockerignore
```

The contents are spec'd in detail below ("Implementation plan").

### 4. Read-only single-instance hosted service

The hosted service exposes the read-side MCP tools only: `pantheon_ask`, `pantheon_node`, `pantheon_status`, `pantheon_reports_list`, `pantheon_reports_show`. **Ingest is not enabled** in Phase 1 — the bundled seed is the entire corpus. This matches PHX-0066's "no ingest surface, no privacy attack surface" guardrail.

The operator does not need to disable any tools at runtime; the MCP server already does not expose ingest tools (PR #37 deliberately deferred them).

### 5. Pass-through LLM keys (no operator billing)

The hosted service does not bundle an LLM API key. Each `pantheon_ask` invocation reads its API key from the request context (the MCP host passes it through) or from the calling agent's environment. The operator's machine never sees the key, never bills the LLM cost.

In Phase 1 this is achieved by simply **not setting** any `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` env var in the container. The `build_llm_from_settings` factory will then raise a clean error if a tool tries to call the LLM without a key — the calling MCP host is expected to pass the key in via its own MCP-protocol tool-call envelope.

If the MCP protocol does not yet support per-call API key pass-through cleanly (which is the current 2026-04 reality), the Phase 1 hosted service degrades to: only `pantheon_node`, `pantheon_status`, `pantheon_reports_list`, `pantheon_reports_show` work without an LLM (they don't need one). `pantheon_ask` returns a clear error message: "this hosted instance does not have an LLM key configured; you can run a local install with your own key, or wait for PHX-0066 Phase 2 which will support per-call key pass-through". Document this honestly in `hosted/README.md`.

### 6. Rate-limiting middleware

Add a simple per-IP rate limiter to the SSE-transport entrypoint:

- `Settings.hosted.rate_limit_per_hour` (default 60)
- `Settings.hosted.rate_limit_per_day` (default 1000)
- `Settings.hosted.rate_limit_bypass_token` (optional; operator-issued)

Implementation: Starlette middleware using an in-memory dict of `{ip: (request_count, window_start)}`. No external dependency. Returns HTTP 429 when exceeded, with a JSON body explaining the limit and when it resets.

Operator can disable rate limiting entirely with `Settings.hosted.rate_limit_per_hour=0`.

### 7. `/health` endpoint

The SSE transport's Starlette app exposes a `/health` route returning JSON:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "store": "memory",
  "embedding_model": "BAAI/bge-small-en-v1.5@v1",
  "embedding_dim": 384,
  "node_count": 278,
  "edge_count": 1168,
  "uptime_seconds": 12345.6,
  "last_query_at": "2026-04-21T15:00:00Z"
}
```

Used by Fly.io's health-check loop and by operators monitoring the service.

### 8. Don't pre-decide the hosting target

The Dockerfile + the documented deploy steps must work on **at least Fly.io** as the primary target, with **HuggingFace Spaces (Docker SDK)** and **Modal** as documented alternatives. No code may assume Fly.io specifically. Configuration that differs per platform (e.g., port, host binding) is operator-provided via env vars (`PORT`, `HOST`).

### 9. No automatic webhook-on-push integration

A GitHub-webhook-triggered redeploy on every `main` push is a great Phase 2 feature but **out of scope** for this etappe. Document the manual `flyctl deploy` step in the README. The operator can layer a webhook on top later if they want it.

---

## Implementation plan (file-by-file)

### `src/theogony/cli.py`

Extend the `mcp` typer command to accept the new flags listed in Scope decision 2. The body branches on `--transport`:

```python
if transport == "stdio":
    if host != "127.0.0.1" or port != 8080:
        log.info("stdio transport: --host/--port ignored")
    asyncio.run(serve_stdio(seed_path=seed_from if seed else None))
elif transport == "sse":
    asyncio.run(serve_sse(host=host, port=port, seed_path=seed_from if seed else None))
else:
    _console.print(f"[red]Unknown --transport: {transport!r}[/red]")
    raise typer.Exit(code=2)
```

Use the same module-level Typer `_OPT` constants pattern that `seed` already uses (avoids the B008 lint we hit before).

### `src/theogony/mcp/server.py`

Two changes:

1. Refactor `open_resources` to optionally accept a `seed_path: Path | None`. When provided, load the seed into the in-memory store before yielding.
2. Add a new top-level `serve_sse(host: str, port: int, seed_path: Path | None) -> None` async function. Lazily import `mcp.server.sse.SseServerTransport`, `starlette`, `uvicorn`. Build a Starlette app with `/sse`, `/messages/`, and `/health` routes. Apply the rate-limit middleware. Run via uvicorn.

The existing `serve_stdio` keeps its current shape; add an optional `seed_path` parameter to it too for symmetry.

The `build_server` function stays unchanged — both transports use the same `Server` instance.

### `src/theogony/config/settings.py`

Add a new `HostedSettings` Pydantic model:

```python
class HostedSettings(BaseModel):
    rate_limit_per_hour: int = 60
    rate_limit_per_day: int = 1000
    rate_limit_bypass_token: SecretStr | None = None
```

Wire it into the top-level `Settings` class as `hosted: HostedSettings = Field(default_factory=HostedSettings)`.

### `hosted/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build deps then theogony[mcp]. Install from the local checkout
# so we do not depend on PyPI (PHX-0066 ships before publication).
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"

# Pre-warm spaCy is NOT needed for hosted v1 — the bundled seed is
# already extracted; the server only needs the embedder + the MCP
# tools. Document this in the README so future operators do not add
# the spacy download step "to be safe".

# Runtime configuration via env vars.
ENV HOST=0.0.0.0 \
    PORT=8080 \
    THEOGONY_LLM__PROVIDER=stub

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; \
        urllib.request.urlopen(f'http://localhost:{__import__(\"os\").environ.get(\"PORT\",\"8080\")}/health', timeout=3); \
        sys.exit(0)" || exit 1

ENTRYPOINT ["theogony", "mcp", "--transport", "sse", "--seed"]
CMD ["--host", "0.0.0.0", "--port", "8080"]
```

Image size target: ≤ 500 MB. If `sentence-transformers` + Python 3.12-slim base pushes us over, document the size in `hosted/README.md` and accept it; do not switch to Alpine (compilation pain not worth it).

### `hosted/.dockerignore`

```
**/__pycache__
**/*.pyc
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
.git
.github
docs/etappes
docs/run_reports
phoenix-backlog
tests
venv
.venv
data
neo4j_data
dist
build
*.egg-info
hosted/fly.toml
.env
.env.*
```

### `hosted/smithery.yaml`

```yaml
# Smithery.ai MCP server registry manifest.
# https://smithery.ai/docs/manifest

name: theogony
displayName: "Theogony — Pantheon-of-Pantheon Chronicle"
description: |
  An open, model-neutral, provenance-bearing knowledge substrate.
  This hosted instance ships pre-seeded with the project's own
  vision, doctrine, and architecture (the Pantheon-of-Pantheon
  chronicle). Ask any question about Theogony, the Chronik,
  the Pantheon vision, or the agent ecosystem and get a cited
  answer drawn from the project's own self-description.

homepage: https://github.com/theogony-project/theogony
repository: https://github.com/theogony-project/theogony
license: Apache-2.0
keywords:
  - knowledge-graph
  - rag
  - memory
  - provenance
  - pantheon
  - chronicle
  - vector-database
  - agents

transport:
  type: sse
  url: "${HOSTED_URL}/sse"

tools:
  - name: pantheon_ask
    description: Ask the Chronik a cited, verdict-anchored question.
  - name: pantheon_node
    description: "Hover-Lupe: fetch a node and its depth-1 neighborhood."
  - name: pantheon_status
    description: Current configuration and report counts.
  - name: pantheon_reports_list
    description: List recent run reports (ingest, query, oneiros).
  - name: pantheon_reports_show
    description: Return one report's full JSON.
```

(The `${HOSTED_URL}` placeholder is filled in after deploy; the operator updates the listing on Smithery's web UI.)

### `hosted/README.md`

Document, in this order:

1. **What this hosts** (one paragraph — the bundled `pantheon_self` chronicle as a public read-only MCP service).
2. **Cost expectations** (operator side ≤ €5/month on free tiers; LLM cost is pass-through to the calling agent).
3. **Fly.io deploy** (step-by-step, with `flyctl launch` walkthrough).
4. **HuggingFace Spaces deploy** (Docker SDK; Spaces config snippet).
5. **Modal deploy** (one short Modal stub; less detailed because Modal is the alternative path).
6. **Smithery listing** (after deploy, register the URL on Smithery).
7. **Operator monitoring** (the `/health` endpoint).
8. **Rate limits** (the defaults; how to bypass via token).
9. **Phase 2 roadmap** (webhook-on-push redeploy, federation enable, Hestia integration).

Keep it under 250 lines. Operator should be able to deploy in under 10 minutes following only this README.

### `tests/test_mcp_sse.py` (new)

One integration test that:

1. Starts the SSE server on a random local port via `serve_sse` in a background asyncio task.
2. Connects to `/sse`, sends an `initialize` request, then `tools/list`.
3. Asserts that the `tools/list` response contains all five expected tool names.
4. Tears down the server cleanly.

Use `httpx` (already a core dep) for the HTTP client. Use `pytest-asyncio` (already in dev). Mark with the existing characterization-style env-gate if startup is too slow for the default suite (`@pytest.mark.skipif(...)` on a `THEOGONY_TEST_SSE` env var).

### Documentation touches

1. **`README.md`** main file: add a one-line note in the MCP section pointing at `hosted/README.md` for the deploy path.
2. **`docs/INDEX.md`**: list `hosted/README.md` under "Operations" (create the section if it does not exist; alongside `RELEASING.md`).
3. **PHX-0066** catalogue entry in `docs/PHOENIX_BACKLOG.md`: append `"Phase 1 closed by hosted v1 PR (this PR): SSE transport, Dockerfile, Smithery manifest, deploy guide. Phase 2 (per-call LLM key pass-through, webhook redeploy, federation enable) tracked separately."`

---

## Cost-benefit considerations

**Token cost for Composer**: medium. SSE transport addition is real code (estimate 80–150 lines including the Starlette wiring), the new tests are small, the documentation is short but careful. Total estimate ≤ €0.50.

**Runtime cost for the operator**: ≤ €5/month on Fly.io free tier (3 × 256 MB shared CPU machines is more than enough for a single-instance read-only service). The bundled seed loads in ~5 s at startup; subsequent tool calls are ms.

**Image size cost**: target ≤ 500 MB. The `sentence-transformers` install brings PyTorch CPU which is the largest single footprint. Acceptable for now; image-size optimisation is Phase 2.

**Failure modes worth watching**:

- **MCP SDK API drift**: the `SseServerTransport` API has been changing through 2025–2026. If the documented pattern in Scope decision 1 fails against the installed SDK version, fall back to the lower-level `Server.run` pattern with manual stream wiring. Document the SDK version pinned (`mcp>=1.0.0` already in `pyproject.toml`).
- **Starlette `_send` deprecation**: noted in Scope decision 1. Use the public API where the SDK supports it.
- **Embedder cold-start**: the BGE-small load is a few hundred ms but the seed-load adds ~5 s. The Dockerfile's `--start-period=20s` healthcheck buffer accommodates this.

---

## Out of scope (do not do)

- **Do not** ship a hosted instance under any account. The operator does that with their own credentials.
- **Do not** add a webhook-on-push redeploy. That is Phase 2.
- **Do not** add federation routing (PHX-0061). That is Phase 3.
- **Do not** add Hestia auditing on hosted queries. That is PHX-0039.
- **Do not** add per-call LLM key pass-through if the MCP protocol does not yet support it cleanly. Document the Phase-2 path; do not invent a custom protocol extension.
- **Do not** publish the package to PyPI as part of this PR. The Dockerfile installs from the local checkout; PyPI publication is the separate PHX-0066 Phase 2.
- **Do not** add monitoring beyond `/health`. Prometheus scraping, Grafana dashboards, log aggregation — all later.
- **Do not** add authentication beyond the rate-limit-bypass token. OAuth, JWT, OIDC — all later.

---

## Done when

- [ ] `theogony mcp --transport sse --host 0.0.0.0 --port 8080 --seed` runs locally and serves an SSE endpoint that an MCP client (Claude Desktop SSE config, or `mcp-cli`) can connect to.
- [ ] `tests/test_mcp_sse.py` passes locally with the env gate enabled. Existing `tests/test_mcp_server.py` (stdio smoke) stays green without modification.
- [ ] `hosted/Dockerfile` builds successfully (`docker build hosted/`); image size ≤ 500 MB.
- [ ] `hosted/README.md` walks an operator through Fly.io deploy in under 10 minutes; HuggingFace Spaces and Modal alternative paths are documented.
- [ ] `hosted/smithery.yaml` is valid YAML; Smithery's manifest validator passes (operator-tested manually after deploy).
- [ ] PHX-0066 catalogue entry updated.
- [ ] `pytest -q` green. `ruff check` clean. `ruff format --check` clean. `mypy` clean on the touched modules.
- [ ] PR title: `feat(hosted): hosted v1 — SSE transport + Dockerfile + Smithery manifest`. PR body lists which Plan / PHX ticket the work covers (PHX-0066 Phase 1) and the operator-side deploy steps.

---

## After this PR

The operator can deploy to Fly.io in one command and list on Smithery. Two follow-on tracks open up:

1. **Phase 2 of PHX-0066**: webhook-on-push redeploy, per-call LLM key pass-through (when MCP protocol supports it), federation enable.
2. **The "agents-can-find-and-use-Pantheon" verification loop**: with the hosted instance live, the user can register the SSE endpoint in Cursor / Claude Desktop and run the verification protocol from the architecture-audit conversation (cited node IDs from the bundled seed prove the agent really queried the chronicle).

The next Phase-0 brief in line is **F2 — TickPhase pipeline refactoring in OneirosWorker**. F1 ships first; F2 follows; F3 (RetrievalStrategy Protocol) closes Phase 0.
