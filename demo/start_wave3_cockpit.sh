#!/usr/bin/env bash
set -euo pipefail

# Wave 3 Cockpit local entrypoint: chronicle is **Neo4j** so operator work survives
# restarts. This script exports Neo4j explicitly so a stale shell cannot inherit
# THEOGONY_COCKPIT__KNOWLEDGE_STORE=memory and silently drop persistence.
#
# Ephemeral in-process graph (no Bolt / CI only): opt in explicitly:
#   THEOGONY_COCKPIT__USE_MEMORY=1 ./demo/start_wave3_cockpit.sh
#
# Neo4j Bolt defaults to THEOGONY_NEO4J__URI (bolt://localhost:7687). When Docker
# is available, this script runs `docker compose up -d neo4j` for the bundled dev
# container. Skip that step with THEOGONY_DEMO_AUTO_NEO4J=0 (remote Neo4j, etc.).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${THEOGONY_COCKPIT__USE_MEMORY:-0}" = "1" ]; then
  export THEOGONY_COCKPIT__KNOWLEDGE_STORE=memory
else
  export THEOGONY_COCKPIT__KNOWLEDGE_STORE=neo4j
fi

if [ "${THEOGONY_COCKPIT__KNOWLEDGE_STORE}" = "neo4j" ] && [ "${THEOGONY_DEMO_AUTO_NEO4J:-1}" != "0" ]; then
  _uri="${THEOGONY_NEO4J__URI:-bolt://localhost:7687}"
  case "${_uri}" in
    bolt://127.0.0.1:*|bolt://localhost:*)
      if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        docker compose up -d neo4j ||
          echo "start_wave3_cockpit: warning: docker compose up neo4j failed (Docker running?). Bolt must be reachable." >&2
      fi
      ;;
  esac
fi

export THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED="${THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED:-true}"
export THEOGONY_CURIOSITY__ARGUS__ENABLED="${THEOGONY_CURIOSITY__ARGUS__ENABLED:-true}"
export THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED="${THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED:-true}"
export THEOGONY_CURIOSITY__EVALUATOR__ENABLED="${THEOGONY_CURIOSITY__EVALUATOR__ENABLED:-true}"
export THEOGONY_CURIOSITY__ATHENE__ENABLED="${THEOGONY_CURIOSITY__ATHENE__ENABLED:-true}"
export THEOGONY_CURIOSITY__CHRONOS__ENABLED="${THEOGONY_CURIOSITY__CHRONOS__ENABLED:-true}"
export THEOGONY_CURIOSITY__NEMESIS__ENABLED="${THEOGONY_CURIOSITY__NEMESIS__ENABLED:-true}"
export THEOGONY_CURIOSITY__ERIS__ENABLED="${THEOGONY_CURIOSITY__ERIS__ENABLED:-true}"
export THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED="${THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED:-true}"

exec "${THEOGONY_PYTHON_BIN:-venv/bin/theogony}" cockpit serve --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
