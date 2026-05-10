# Living Demo — hosted smoke (after local recording)

Documentation only — **Talos does not deploy**. After the local recording in [`demo/living_growth.md`](living_growth.md) is accepted, you deploy the **same container image** to whatever host you use (see [`hosted/README.md`](../hosted/README.md)); this file does not pin a vendor.

## Deploy

Build and run per `hosted/README.md` (same commit you verified locally, typically `main` after the W9 merge). Push to your registry and roll your platform’s deploy, or run `docker run` against a registry image.

## Remote MCP smoke (reference pattern)

The contract-level MCP module tests live under [`tests/test_mcp_server.py`](../tests/test_mcp_server.py). For a hosted smoke walk, point your MCP client at the deployed HTTP/SSE endpoint (base URL + `/sse`) and run a **`pantheon_ask`** sequence against a **thin region** — the same conceptual question family as the local script (Tibet / Hedin / expedition).

## Expected

You should see the **same phase ordering** as locally: cited answer on first hop, stub or thin coverage where expected, then (when growth is enabled on that deployment) research events through `acquired_into_pool`, `ingested`, and `research_complete`. If the hosted stack does not have GrowthBridge/Argus enabled, compare only the stable read path and file a follow-up; do not fake parity in the recording.

## Note

This file intentionally does not pin secrets, regions, or org slugs — those belong in your deployment dashboard and local env, not in git.
