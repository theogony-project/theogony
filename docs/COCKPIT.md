# Pantheon Cockpit (Iris, PHX-0074)

The cockpit is mounted at `/cockpit` on the main FastAPI app when `THEOGONY_COCKPIT__ENABLED` is true (default). It is server-rendered HTML with HTMX and Tailwind via the [Play CDN](https://tailwindcss.com/docs/installation/play-cdn) (`cdn.tailwindcss.com`); Cytoscape.js loads only on the Knowledge and Cluster panels.

## Security

Default `bind_host=127.0.0.1` and `public=false`. Off-host requests receive HTTP 403 unless `public=true` and `bind_host=0.0.0.0` are set together.

## Sample-only mode

`THEOGONY_COCKPIT__SAMPLE_ONLY=true` caps search, cluster lists, and report tables; manifest POST returns 403.

## Manifest

Stored under `data_dir` at `cockpit/manifest.md` (relative path from settings). Atomic write with optional history snapshots.

## CLI

`theogony cockpit serve` runs `theogony.cockpit.standalone_app:app` with the bundled `pantheon_self` seed. It reads **full** `Settings` from the environment (including `THEOGONY_LLM__*` and `ANTHROPIC_API_KEY`); when a live provider can be built, the Explorer uses **real LLM synthesis** — otherwise it falls back to the stub + offline citation path.
