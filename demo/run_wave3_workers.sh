#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="${THEOGONY_PYTHON_BIN:-venv/bin/theogony}"
STORE="${STORE:-memory}"

THEOGONY_CURIOSITY__ATHENE__ENABLED=true "$BIN" curiosity athene-run --once --store "$STORE"
THEOGONY_CURIOSITY__CHRONOS__ENABLED=true "$BIN" curiosity chronos-run --once --store "$STORE"
THEOGONY_CURIOSITY__NEMESIS__ENABLED=true "$BIN" curiosity nemesis-run --once --store "$STORE"
THEOGONY_CURIOSITY__ERIS__ENABLED=true "$BIN" curiosity eris-run --once --store memory --fixture
THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED=true "$BIN" mnemosyne conduct --once --store "$STORE" --metric-mode fixture

"$BIN" reports list --type chronos
"$BIN" reports list --type nemesis
"$BIN" reports list --type eris
"$BIN" reports list --type mnemosyne_conductor
