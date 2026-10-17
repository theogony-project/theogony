#!/bin/sh
# Run the documented quickstart as a stranger would (PHX-1111).
#
#     scripts/fresh_clone_probe.sh [workdir]
#
# A local clone of the *committed* state, a fresh virtual environment, and an
# environment that inherits nothing but HOME and a PATH — no API keys, no .env.
# Then the commands README.md and AGENTS.md tell a newcomer to type, verbatim,
# and an MCP client that drives the server over stdio as a host does.
#
# No unit test replaces this: every test runs inside a configured development
# environment, which is exactly what an arriving agent does not have. The first
# run found seven defects (docs/etappes/arriving_agent.md). Run it whenever a
# document that tells a newcomer what to type is changed. Needs network access
# for pip, and for the embedding model on a machine that has never cached it.
#
# Since PHX-1112 the run also builds the demo mesh (`theogony mesh demo`, the
# bundled Kadmos readings of Hesiod's Theogony replayed through the shipped
# reader) and asks it, on the command line and over MCP. Acceptance: a
# Constellation out of a mesh, from a fresh clone, in under three minutes,
# without any key.
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=${1:-$(mktemp -d)}
PYTHON=${PYTHON:-python3}

echo "== clone (committed state only) -> $WORK/theogony"
rm -rf "$WORK/theogony"
git clone -q "$REPO" "$WORK/theogony"
cd "$WORK/theogony"
git log --oneline -1

echo "== install, as AGENTS.md documents it"
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -q -e ".[mcp]"

clean() {
    env -i HOME="$HOME" PATH="$WORK/theogony/.venv/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
        TERM=dumb NO_COLOR=1 COLUMNS=140 "$@"
}

echo "== theogony ask (README quickstart, no key)"
clean theogony ask "What is the Chronik?" 2>/dev/null | grep -E "AKA-|Constellation:|No language model" | head -12

# A pipeline's status is its last command's, so the demo and the question are
# captured to a file and their exit status checked; piped into grep, a failing
# `mesh demo` would have printed nothing and the probe would have gone on.
echo "== theogony mesh demo (a real mesh from the bundled readings, no key; PHX-1112)"
DEMO_START=$(date +%s)
DEMO_OUT="$WORK/mesh_demo.out"
if ! clean theogony mesh demo >"$DEMO_OUT" 2>&1; then
    tail -20 "$DEMO_OUT"
    echo "FAIL  theogony mesh demo exited non-zero"
    exit 1
fi
grep -E "paragraphs replayed|Workspace|had no recorded" "$DEMO_OUT" | head -4
echo "   mesh demo took $(( $(date +%s) - DEMO_START )) s"

echo "== theogony mesh ask (README, no key)"
ASK_OUT="$WORK/mesh_ask.out"
if ! clean theogony mesh ask "Who are the children of Cronos?" >"$ASK_OUT" 2>&1; then
    tail -20 "$ASK_OUT"
    echo "FAIL  theogony mesh ask exited non-zero"
    exit 1
fi
grep -E '"nodes"|"edges"|"seeds"' "$ASK_OUT" | head -3
if grep -qE '"nodes": 0,' "$ASK_OUT"; then
    echo "FAIL  theogony mesh ask returned no nodes"
    exit 1
fi

echo "== theogony mcp (AGENTS.md, no key; pantheon_* and, over the demo mesh, mesh_*)"
clean python scripts/mcp_probe.py theogony "$WORK/theogony" --expect-mesh 2>/dev/null
