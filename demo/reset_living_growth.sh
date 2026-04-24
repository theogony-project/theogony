#!/usr/bin/env bash
# Living Demo W9 — one-shot reset (see docs/etappes/W9_demo_lock_brief.md).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${THEOGONY_ALLOW_DEMO_RESET:-}" != "1" ]]; then
  echo "set THEOGONY_ALLOW_DEMO_RESET=1 to confirm wipe"
  exit 2
fi

if [[ -n "${THEOGONY_NEO4J__URI:-}" ]]; then
  NEO4J_URI="${THEOGONY_NEO4J__URI}"
  NEO4J_USER="${THEOGONY_NEO4J__USER:-neo4j}"
  NEO4J_PASSWORD="${THEOGONY_NEO4J__PASSWORD:-}"
  NEO4J_DATABASE="${THEOGONY_NEO4J__DATABASE:-neo4j}"

  if command -v cypher-shell >/dev/null 2>&1; then
    CYPHER="MATCH (n) DETACH DELETE n"
    # cypher-shell accepts password via env NEO4J_PASSWORD when -p is omitted in some versions;
    # pass explicitly for compatibility.
    NEO4J_PASSWORD="${NEO4J_PASSWORD}" cypher-shell -a "${NEO4J_URI}" -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" -d "${NEO4J_DATABASE}" "${CYPHER}"
  else
    python -c "
import asyncio
import os

from neo4j import AsyncGraphDatabase

async def _wipe() -> None:
    uri = os.environ['THEOGONY_NEO4J__URI']
    user = os.environ.get('THEOGONY_NEO4J__USER', 'neo4j')
    password = os.environ.get('THEOGONY_NEO4J__PASSWORD', '') or ''
    database = os.environ.get('THEOGONY_NEO4J__DATABASE', 'neo4j')
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session(database=database) as session:
        await session.run('MATCH (n) DETACH DELETE n')
    await driver.close()

asyncio.run(_wipe())
"
  fi
else
  mkdir -p "${REPO_ROOT}/data/run_reports"
  rm -f "${REPO_ROOT}/data/audit.sqlite"
  rm -rf "${REPO_ROOT}/data/run_reports"/*
fi

# When Neo4j is not targeted by URI, re-seed into memory so CI-like hosts
# without Bolt still pass W9 acceptance (see W9 brief A1).
if [[ -n "${THEOGONY_NEO4J__URI:-}" ]]; then
  theogony seed
else
  theogony seed --store memory
fi

cat > "${REPO_ROOT}/.demo.env" <<'EOF'
THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true
THEOGONY_CURIOSITY__ARGUS__ENABLED=true
EOF

cat <<'EOF'
Living Demo reset complete.
Source the env: source .demo.env
Start the cockpit: theogony cockpit serve --host 127.0.0.1 --port 8000
Open: http://127.0.0.1:8000/cockpit/explorer?growth=on
Recording script: demo/living_growth.md
EOF
