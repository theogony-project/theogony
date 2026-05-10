#!/usr/bin/env bash
# Living Demo W9 — one-shot reset (see docs/etappes/W9_demo_lock_brief.md).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${THEOGONY_ALLOW_DEMO_RESET:-}" != "1" ]]; then
  echo "set THEOGONY_ALLOW_DEMO_RESET=1 to confirm wipe"
  exit 2
fi

mkdir -p "${REPO_ROOT}/data/run_reports"
rm -f "${REPO_ROOT}/data/audit.sqlite"
rm -rf "${REPO_ROOT}/data/run_reports"/*

theogony seed --store memory

cat > "${REPO_ROOT}/.demo.env" <<'EOF'
# Content flows into the chronicle without a pre-gate content judge.
# The immune system (Athene / Chronos / ...) observes and acts asynchronously.
# See docs/IMMUNE_SYSTEM.md for doctrine.
THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true
THEOGONY_CURIOSITY__ARGUS__ENABLED=true
THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED=true
THEOGONY_CURIOSITY__EVALUATOR__ENABLED=true
THEOGONY_CURIOSITY__ATHENE__ENABLED=true
THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE=1.0
# Demo mode samples every pool entry so the immune-system panel visibly changes.
# Production default remains 0.02.
THEOGONY_CURIOSITY__CHRONOS__ENABLED=true
# Nemesis is read-only and safe for demo mode. Eris remains opt-in because red-team
# campaigns are intentionally adversarial; W16 supports fixture runs only.
THEOGONY_CURIOSITY__NEMESIS__ENABLED=true
EOF

cat <<'EOF'
Living Demo reset complete.
Source the env: source .demo.env
Start the cockpit: theogony cockpit serve --host 127.0.0.1 --port 8000
Open: http://127.0.0.1:8000/cockpit/explorer
EOF
