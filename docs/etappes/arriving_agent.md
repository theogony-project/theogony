# What an arriving agent finds (PHX-1111)

**Status:** 2026-09-17, measured, fixed, re-measured.
**Instrument:** a fresh clone of `main`, a fresh virtual environment, an
environment holding nothing but `HOME` and a `PATH`, and exactly the commands
`README.md` and `AGENTS.md` document — plus an MCP client that drives
`theogony mcp` over stdio the way a host does.

## Why this was measured

The repository says it is built for agents: `AGENTS.md` calls it "a
deliberately AI-first codebase", `llms.txt` lists the MCP tools, the vision
says agents do not read the Chronik, they activate it. An agent that arrives
has three properties the documents had not been tested against. It has **no
API key** for anyone's LLM. It **is** a language model, so what it wants from a
knowledge substrate is the structure, not another model's prose about the
structure. And it has **minutes**: if the second documented command fails, it
leaves, and it does not file an issue.

None of the 1,960 tests could see any of this, because every one of them runs
inside a configured development environment.

## What it found

| Step, as documented | Before | After |
|---|---|---|
| `pip install -e ".[mcp]"` | works, 50 s, 1.4 GB | unchanged |
| `theogony seed` | works — into a store that ends with the process; the next command cannot see it | unchanged, and now says so |
| `theogony ask "What is the Chronik?"` | **exits 1 before retrieval runs**: no OpenAI key | one command, 11 s: 10 nodes / 10 edges, six cited sources |
| `theogony mcp` (AGENTS.md) | **dies before the MCP handshake**: no OpenAI key | starts in 9 s |
| `theogony mcp --seed` → `pantheon_ask` | `{"error": "this hosted instance does not have an LLM key…"}` returned as a **successful** result, on a local install | full constellation in 0.1 s; `answer_mode: "offline"` |
| stdout during an MCP session | **8 log lines** on the channel the stdio transport reserves for JSON-RPC | 0 |
| unknown node id | success whose body contains `error` | `is_error: true` |

Two of these were not about keys at all. The README's quickstart —
`theogony seed`, then `theogony ask` — questioned an **empty** Chronik even
with a key, ever since the Neo4j store was retired and the in-memory store
stopped outliving its process. And a server that logs to stdout over a stdio
transport is only working to the extent its host is forgiving.

Net, before: **without an OpenAI account, no answer and no constellation could
be obtained by any documented path.** Retrieval — Spreading Activation over the
graph, the one thing this system does differently — never needed a language
model. It was simply placed behind one.

## What changed

- **`build_llm_or_offline`**: the configured LLM, or a stub plus the reason.
  Every read-side entry point calls it. The write side (ingestion, extraction)
  still requires a real provider, because there a stub would write nonsense
  into the substrate.
- **The instance decides, not the setting — and not any stub.** The synthesizer
  factory and the Mnemosyne classifier chose their behaviour from
  `settings.llm.provider`; a provider that is configured but has no key leaves
  the setting saying `openai`. Both now look at what they were given. The first
  version of this fix asked "is it a `StubLLMProvider`?" and five growth-stream
  tests failed: a plain stub is also how tests and demos script an LLM's replies
  through the *real* synthesizer, and the broad check had silently rerouted them
  through the citation-only path. The keyless case now has a type of its own,
  `OfflineLLMProvider`. The offline citation synthesizer this makes reachable
  had existed since PHX-0070.
- **`pantheon_ask` always returns the constellation.** `answer_mode` is `"llm"`,
  `"offline"` or `"none"`. `synthesize=false` is for the caller that is itself
  a language model. `pantheon_status` reports `llm_available` before the first
  question is asked.
- **Seeded by default.** An in-memory store that is empty can answer nothing;
  `--no-seed` remains for `pantheon_chronicle_append` sessions.
- **Errors are errors, logs are on stderr, and the offline answer says what it
  is** — "nothing here is generated" — rather than where it supposedly runs.

## What this does not fix

This is the **Generation-1** layer, and the honest reading of the table is that
the entrance now opens onto the older half of the house.

- The bundled self-description (`pantheon_self`) was written on **2026-04-20**.
  An agent that asks this repository about itself gets the April answer: before
  the mesh, before the identity repairs, before every measurement in
  `docs/etappes/` since.
- The **MESH substrate has no MCP surface**, and there is no keyless way to get
  a mesh workspace at all: reading needs an LLM. Everything measured since July —
  retrieval recall, the contradiction memory, renormalisation, the 2Wiki answer
  arm — lives where an arriving agent cannot go.

Both are PHX-1112. The replay provider built for PHX-1110 is the obvious way
in: recorded Kadmos readings of a public-domain corpus, replayed through the
shipped write path, give a real mesh in a minute without a key.

## What the entrance says now (PHX-1115)

Making the door open was half of it. The files an arriving agent reads were
written for one kind of agent — the one that has already decided to contribute:
eighteen documents of required reading before the first instruction, the
invitation to *use* the system at line 172, nothing for the agent that came
with a different task and wanted one piece. And the document that argues,
agent to agent, that the substrate serves its reader offered sentences to
paraphrase to a human which claimed a reduced hallucination rate and memory
across sessions. Neither was ever measured, and the second is false of the very
surface the document points to.

`AGENTS.md` now opens with three doors — use it, take something
([`TAKE_THIS.md`](../TAKE_THIS.md)), work on a ticket that has a finish line —
says what runs, what is measured and what is not true yet, and only then states
the contract, which is unchanged. [`AGENT_SELF_INTEREST.md`](../AGENT_SELF_INTEREST.md)
keeps its six arguments and marks each with what is built, measured or only
designed. The reasoning is the same as for the numbers in this directory: a
reader that checks is the reader worth writing for, and a claim it cannot
verify costs more than silence.

## The method, because it is reusable

`clone → venv → env -i → the documented commands, verbatim` is a test no unit
test replaces, and it costs five minutes. It is `scripts/fresh_clone_probe.sh`
now, with `scripts/mcp_probe.py` as the MCP host, and it exits non-zero. It should be run whenever a document
that tells a newcomer what to type is changed — and it found seven defects the
first time it was run.
