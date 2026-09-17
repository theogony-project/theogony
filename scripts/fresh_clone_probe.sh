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

echo "== theogony mcp (AGENTS.md, no key)"
clean python scripts/mcp_probe.py theogony "$WORK/theogony" 2>/dev/null
