# Living Demo — hosted Fly.io smoke (after local recording)

Documentation only — **Talos does not deploy**. You run Fly with your own credentials after the local recording in [`demo/living_growth.md`](living_growth.md) is accepted.

## Deploy

From the repository root:

```bash
fly deploy --config hosted/fly.toml
```

Use the same commit you verified locally (typically `main` after the W9 merge).

## Remote MCP smoke (reference pattern)

The contract-level MCP module tests live under [`tests/test_mcp_server.py`](../tests/test_mcp_server.py). For a hosted smoke walk, point your MCP client at the deployed HTTP/SSE endpoint (see [`hosted/README.md`](../hosted/README.md)) and run a **`pantheon_ask`** sequence against a **thin region** — the same conceptual question family as the local script (Tibet / Hedin / expedition).

## Expected

You should see the **same phase ordering** as locally: cited answer on first hop, stub or thin coverage where expected, then (when growth is enabled on that deployment) Argus phases through fetch and completion. If the hosted stack does not have GrowthBridge/Argus enabled, compare only the stable read path and file a follow-up; do not fake parity in the recording.

## Note

This file intentionally does not pin secrets, regions, or org slugs — those belong in your Fly dashboard and local env, not in git.
