# Week 4 — Demonstration capture + final polish

Brief from Hesiod to Talos, 2026-04-19. Direct brief, no Daedalus design round (per the new workflow: Daedalus is invoked only when there are genuine architectural trade-offs; Week 4 is execution + capture, no open questions).

Follows merged Etappe E8.5 (PR #27) — the Memory layer breathes, the Plan §1 demo critical path is now structurally complete (E7 store + E8 retrieval + E8.5 lifecycle + E9 API/CLI all in main).

## What this etappe does

Closes Plan §5 Week 4 — the **Demonstration** milestone. After this PR lands, a critical observer can clone the repo, follow the README, and reproduce the Plan §1 demo end-to-end. The Chronik proves itself: ingests Heinrich Harrer's *Seven Years in Tibet* (Gutenberg #944), answers questions about it with cited passages, and shows its own self-assessment via run reports.

Bundled scope (one PR, sibling pattern to PR #24 / PR #27):

1. **Full Hedin or Harrer ingest** — actually run `theogony ingest 944` against a real Neo4j, capture the `IngestRunReport`, document the timing + cost + node/edge counts in a new `docs/etappes/demo_log.md`.
2. **Ten demo queries** — run them via `theogony ask`, capture the answers + cited node ids + verdicts, write into the same `demo_log.md`. This is the agent-readable retrospective layer demonstrating itself; future Reviewer agent (PHX-0035) gets its first real corpus from this.
3. **OneirosWorker observed live** — let the worker run during + after ingest; capture at least one `OneirosTickReport` showing real promotion/degradation activity. Document in `demo_log.md`.
4. **README quickstart finalised** — the current README's "Local development" section is good but lists nine sequential steps without narrative. Restructure it as: (a) one-paragraph "what you get", (b) prerequisites, (c) **the demo sequence** (the Plan §1 moment as a copy-paste recipe), (d) "going further" (status, reports, resolve, serve). The Plan §1 demo is the *headline*, not buried at step 6.
5. **Hestia schema + prompts (S)** — Plan §5 Week 4 deliverable: `src/theogony/agents/hestia.py` with `HestiaReview` Pydantic schema (no runtime; schema-only per Plan §1 "Hestia as Schema and prompt templates only"). `prompts/hestia_sentinel.md` and `prompts/hestia_auditor.md` written from `docs/HESTIA.md`. No CLI command; no integration into the runtime; the schema exists so a future Hestia agent has the shape it must produce.
6. **Plan §5 Week 4 marked DONE** in the implementation plan with the actual numbers.

Out of bundle (User-action follow-ups, post-merge):

- **5-min screen recording.** Hesiod cannot capture this; user records terminal session of the demo sequence after this PR lands. Brief notes the README will reference it as `docs/demo_recording.mp4` (or external link); the path is reserved.
- **Phoenix backlog filing for Gen-2 Hestia runtime.** Already covered by existing PHX entries (PHX-0036 around hand-annotation; the Hestia runtime itself is implicit Gen-2 infra; no new ticket needed unless the schema work surfaces something concrete).

## Scope decisions (read first)

### This is the LAST Gen-1 PR before the demo recording

After this PR merges, Gen 1's structural surface is done. The README points to the demo, the demo runs, the schemas exist, the agent retrospective layer has real data. From here, Hesiod's next briefs are either: (a) the opportunistic PHX cluster (PHX-0053 traverse strip-embedding + a few siblings), or (b) Detective Mode if PHX-0041's re-measurement justifies it. Both are *post-Gen-1-demo* work. Keep this PR focused on closing Week 4 cleanly.

### Real ingest, real Neo4j — not stubs

The whole point of Week 4 is honesty: stub-mode demos prove nothing. Run against a real `docker compose up neo4j` against the real Heinrich Harrer book (Gutenberg #944), with a real Gemini API key, with real wall-clock measurements. If the ingest costs 0.18 EUR — write 0.18 EUR. If it surfaces 47 manual-resolution candidates — write 47. If a query returns a "partial" verdict because the constellation only carried two cited nodes — write that, *don't re-run until it's "good"*. The honesty is the deliverable. The Plan §3.3a v5 free-tier-promise correction is the precedent: we ship the truth, including unflattering numbers, because the future depends on us setting the honesty bar.

If something blocks the real ingest (e.g. Wikidata rate limit during peak hours, Gemini quota exceeded mid-run), document the block + the workaround in `demo_log.md`; do **not** silently work around it with stubs.

### Hestia schema is intentionally minimal

`HestiaReview` is one Pydantic model with the fields the future Hestia runtime will produce: `subject_path` (what was reviewed), `concerns` (list of `{category, severity, reasoning, evidence_locator}`), `recommendations` (list of `{action, urgency, rationale}`), `verdict ∈ {"clean", "watch", "concern", "drift"}`, `verdict_reasoning`, `reviewed_at`, `reviewed_by` (the model id). No code that *uses* the schema; no orchestration; no integration with `RunReportWriter` (separate Gen-2 concern). The schema's only job in Gen 1 is to make the next person's PR small: when someone files PHX for "stand up Hestia auditor agent", the schema is the constraint they target.

The two prompts (`prompts/hestia_sentinel.md` and `prompts/hestia_auditor.md`) are the operational shape. *Sentinel*: monitors a single PR / commit / config change for drift signals; produces one `HestiaReview` per artefact. *Auditor*: scheduled (e.g. weekly) sweep over the `data/run_reports/` directory + recent commits + recent prompt changes; produces one `HestiaReview` per sweep. Both prompt files lift their structure from `docs/HESTIA.md`'s own categories ("efficiency-uber-alles drift", "surveillance creep", etc.) and reference `HestiaReview` as the required output schema. No `[]` placeholders; written as actual production-ready prompts a future Talos can wire to a `HestiaSentinel` / `HestiaAuditor` class without further design.

### `demo_log.md` is a permanent artefact, not a transcript dump

Keep it tight: one section per question, the question + the system's answer + the cited node ids + the run_id (so any reader can `theogony reports show <run_id>` to inspect details). Two sections at the top: *Setup* (one paragraph: hardware, Neo4j version, Gemini model, embedding model) + *Ingest* (numbers from the IngestRunReport: nodes minted, edges minted, tier distribution, manual_resolution_needed count, total cost EUR, wall-clock). One section at the bottom: *Oneiros activity* (one tick's report copy-pasted, with a one-sentence interpretation). Keep prose to the minimum needed to make it readable a year from now.

### README quickstart restructure — the demo is the headline

Current README "Local development" section reads like a developer onboarding checklist. Restructure as:

```
## Local development

### What you get

One paragraph: A working Theogony installation that ingests Project
Gutenberg books, answers questions about them with cited passages, and
self-reports its own run quality. Demo runs end-to-end on a developer
laptop in ~10 minutes.

### Prerequisites

- Python 3.12+
- Docker (for Neo4j 5.18-community)
- A Gemini API key (free tier works for the demo)

### The demo

(Six commands: clone → install → docker → ingest 944 → ask → reports
show. Numbered, copy-pasteable, with the wall-clock budget alongside
each step. Mirror the Plan §1 demonstration moment exactly.)

### Going further

- `theogony status` — check config + report counts
- `theogony reports list / show` — inspect any run's self-assessment
- `theogony resolve --list / <id>` — manual Wikidata resolution
- `theogony serve` — FastAPI surface (see API reference below)
- `pytest` — run the test suite
- `docker compose up neo4j` — Neo4j-store-required tests

### API reference

(Compact: list the four endpoints from E9 with one-line examples.)
```

The current README's `Stop everything: docker compose down. Wipe Neo4j data: docker compose down -v.` line stays as the closing operational note.

### No code changes outside the additions above

`OneirosWorker`, `KnowledgeStore`, `MultiHopRetriever`, `ConstellationAssembler`, `AnswerSynthesizer`, `QueryPipeline`, FastAPI routes, Typer CLI commands — **none** edited. This is a documentation-and-execution PR. The only `src/` addition is `src/theogony/agents/hestia.py` (one Pydantic model, ~50 lines).

If during the demo run Talos hits a real bug (something crashes, something returns nonsense), file a PHX ticket and document in `demo_log.md` as a known issue. Do **not** silently fix it in this PR — that is scope creep and would muddy the "Week 4 closes Gen 1" signal. If it is a *blocker* for the demo (the demo cannot run at all), escalate to Hesiod via PR comment + a separate fix PR before this one.

## Files

```
docs/etappes/demo_log.md                       NEW   the Heinrich Harrer demo run captured: setup + ingest + 10 queries + Oneiros tick
docs/etappes/W4_brief.md                       NEW   this brief (file the markdown for traceability after Talos starts)
docs/IMPLEMENTATION_PLAN_GEN1.md               EDIT  §5 Week 4 — mark deliverables as DONE with actual numbers; one-line top-of-doc reconciliation block
README.md                                      EDIT  full restructure of "Local development" per the spec above
src/theogony/agents/hestia.py                  NEW   HestiaReview Pydantic model
prompts/hestia_sentinel.md                     NEW   per-artefact drift-monitoring prompt
prompts/hestia_auditor.md                      NEW   scheduled-sweep audit prompt
tests/test_agents_hestia.py                    NEW   schema round-trip + prompt-file existence tests (3-5 tests)
```

No PHX ticket edits in this PR (none open need touching for Week 4).

## Classes & APIs

### `HestiaReview` — `src/theogony/agents/hestia.py`

```python
"""
HestiaReview — Pydantic schema for the Hestia agent's drift-monitoring output.

Hestia is the Pantheon's Human Flourishing Guardian (docs/HESTIA.md). In Gen 1
this is a SCHEMA-ONLY deliverable per Plan §1 ("Hestia as Schema and prompt
templates only"). No runtime; no orchestration; no integration with
RunReportWriter. The schema exists so the future Hestia runtime (Sentinel +
Auditor agent classes, Gen 2 territory) targets a stable, reviewed shape from
day one.

Two production prompts at prompts/hestia_sentinel.md and
prompts/hestia_auditor.md drive the agent classes when they exist; both
require their LLM call to produce one HestiaReview per artefact / sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HestiaCategory = Literal[
    "efficiency_uber_alles",
    "surveillance_creep",
    "managed_contentment",
    "diversity_collapse",
    "control_for_care",
    "expropriation_of_meaning",
    "other",
]
HestiaSeverity = Literal["info", "watch", "concern", "drift"]
HestiaUrgency = Literal["next_review", "next_sprint", "immediate"]
HestiaVerdict = Literal["clean", "watch", "concern", "drift"]


class HestiaConcern(BaseModel):
    """One specific drift signal Hestia identified in the reviewed artefact."""

    model_config = ConfigDict(extra="forbid")

    category: HestiaCategory
    severity: HestiaSeverity
    reasoning: str = Field(min_length=1)
    evidence_locator: str = Field(min_length=1, description="file:line, run_id, prompt name, etc.")


class HestiaRecommendation(BaseModel):
    """One concrete action Hestia recommends in response to the concerns."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    urgency: HestiaUrgency
    rationale: str = Field(min_length=1)


class HestiaReview(BaseModel):
    """One Hestia review of a single artefact (sentinel) or sweep (auditor).

    The schema is intentionally narrow: Hestia is a *counter-weight*, not a
    veto. Concerns + recommendations + a verdict; no enforcement, no patches.
    The verdict is the executive summary the project lead reads first.
    """

    model_config = ConfigDict(extra="forbid")

    subject_path: str = Field(min_length=1, description="file path, run_id, or 'sweep:<date>'")
    reviewed_by: str = Field(min_length=1, description="LLM model id (e.g. 'gemini-2.5-flash-lite')")
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    concerns: list[HestiaConcern] = Field(default_factory=list)
    recommendations: list[HestiaRecommendation] = Field(default_factory=list)
    verdict: HestiaVerdict
    verdict_reasoning: str = Field(min_length=1)


__all__ = [
    "HestiaCategory",
    "HestiaSeverity",
    "HestiaUrgency",
    "HestiaVerdict",
    "HestiaConcern",
    "HestiaRecommendation",
    "HestiaReview",
]
```

The `HestiaCategory` literal mirrors the drift modes named in `docs/HESTIA.md` ("efficiency becomes the only metric", "surveillance becomes normalized", etc.). The `HestiaVerdict` literal mirrors `OneirosTickReport.verdict` and `IngestRunReport.verdict` (consistent vocabulary across all agent self-reports). `extra="forbid"` is the project's standing convention for Pydantic models.

### Prompts — operational shape

`prompts/hestia_sentinel.md` is the single-artefact prompt: input is one PR / commit / config change / prompt diff; output is one `HestiaReview`. It instructs the LLM to walk the artefact through the seven `HestiaCategory` lenses, produce zero-or-more `HestiaConcern` rows, propose zero-or-more `HestiaRecommendation` rows, and arrive at one `verdict`. Reference `docs/HESTIA.md` for the categories' definitions; quote the `HestiaReview` JSON schema verbatim in the "Required output format" section.

`prompts/hestia_auditor.md` is the sweep prompt: input is a window of recent run reports + recent commits + recent prompt changes; output is one `HestiaReview` per sweep. Same seven-category walk, but at the system-trajectory level rather than per-artefact. Reference `docs/HESTIA.md` for "What Hestia Watches" specifically.

Both prompts close with: "Produce ONE HestiaReview as a JSON object matching the schema below. Do not produce prose outside the JSON object."

Pattern lifted from the existing `prompts/daedalus.md` and `prompts/talos.md` files (read those first; mirror the section structure for consistency).

### `IMPLEMENTATION_PLAN_GEN1.md` — Week 4 reconciliation

Add a one-paragraph reconciliation block at the top of the doc (sibling to the post-E8.5-merge block already there). Edit `§5 Week 4 — Demonstration` to mark deliverables with actual numbers from `demo_log.md`:

```diff
 ### Week 4 — Demonstration

 **Goal:** ingest "Seven Years in Tibet" in full, run the demonstration moment from §1 reliably, ship documentation.

 **Deliverables.**
-- Full ingest of Gutenberg #944.
+- ✅ Full ingest of Gutenberg #944. Captured in [`demo_log.md`](etappes/demo_log.md) — N nodes, M edges, K manual_resolution_needed, X.XX EUR, Y.Y min wall-clock.
-- `memory/oneiros.py` and `memory/relevance.py` — minimal worker active in `theogony serve`.
+- ✅ `memory/oneiros.py` (E8.5, PR #27) + `memory/relevance.py` (E8, PR #20) — worker active in `theogony serve`. One sample tick captured in `demo_log.md`.
-- `agents/hestia.py` — `HestiaReview` Pydantic schema.
+- ✅ `agents/hestia.py` — `HestiaReview` Pydantic schema (W4 PR).
-- `prompts/hestia_sentinel.md`, `prompts/hestia_auditor.md`.
+- ✅ `prompts/hestia_sentinel.md`, `prompts/hestia_auditor.md` (W4 PR).
 - `prompts/daedalus.md` already exists; we leave it.
-- `theogony reports list` and `theogony reports show <run_id>` working end-to-end against the report directories. (S, §2.11)
+- ✅ `theogony reports list` and `theogony reports show <run_id>` working end-to-end (E9, PR #23). Demonstrated in `demo_log.md`.
-- README quickstart updated to reflect the demo sequence.
+- ✅ README quickstart restructured around the demo sequence (W4 PR).
-- `docs/IMPLEMENTATION_PLAN_GEN1.md` (this document) updated with what actually shipped.
+- ✅ This block updated; reconciliation history at top of doc.
-- Phoenix Backlog tickets filed for every deferral (see §7).
+- ✅ 29 PHX tickets in `phoenix-backlog/` covering all deferrals.
-- A 5-minute screen recording of the demo, archived.
+- 🟡 5-minute screen recording: user-action follow-up post-merge (Hesiod cannot capture).
```

Walk the **Success criteria** list similarly; mark with ✅ / 🟡 / ❌ + actual numbers.

If a success criterion fails, mark it ❌ + the failure mode. *Do not falsify*. A ❌ on a success criterion is itself useful information (it tells the next iteration where Gen 1 fell short of its own bar) and triggers a PHX ticket for that specific gap.

## Tests

| File | Layer (§3.8) | What it asserts |
|---|---|---|
| `test_agents_hestia.py` | 4 unit | `HestiaReview` round-trips through JSON; `extra="forbid"` rejects unknown fields; `verdict` is one of the four literals; `prompts/hestia_sentinel.md` and `prompts/hestia_auditor.md` exist and are non-empty (one test that reads each file). 3–5 tests total. |

No new tests for `demo_log.md` (it's a captured artefact, not code). No new tests for the README (it's prose). No new tests for the plan reconciliation (it's documentation).

## How to run the demo (the bulk of this PR's work)

The actual `theogony ingest 944` + ten `theogony ask` + Oneiros observation is the bulk of this PR — Talos's wall-clock time goes mostly here, not in code. Sequence:

1. `docker compose up -d neo4j` — fresh database (or `docker compose down -v && docker compose up -d neo4j` if there is leftover data from prior tests; the demo wants a clean slate).
2. `THEOGONY_LLM__PROVIDER=gemini GEMINI_API_KEY=… theogony ingest 944` — run the full ingest. Expected: ~7000 sentences, ~5–10 min wall-clock, ~0.10–0.20 EUR. Capture the `IngestRunReport` run_id + the wall-clock + the cost via `theogony reports show <run_id>`. Record the printed Rich panel verbatim in `demo_log.md`.
3. `THEOGONY_ONEIROS__TICK_INTERVAL_S=30 theogony serve &` — start the API. The shorter tick interval (30 s vs production default 60 s) means at least one full tick fires during the query session.
4. Run **ten queries** through the CLI. Suggested mix (Talos picks the actual ten — the goal is breadth, not these exact strings):
   - 4 fact-recall queries: "Welche Ethnien beschreibt Heinrich Harrer in seinen Erlebnissen, und auf welchen Wegen begegnet er ihnen?", "Wer ist Peter Aufschnaiter?", "Wann erreichte Harrer Lhasa?", "Welche Beziehung hat Harrer zum Dalai Lama?".
   - 3 multi-hop queries: "Welche Personen aus Harrers Umfeld stehen in Beziehung zum tibetischen Hof?", "Wie hängt Harrers Flucht mit dem zweiten Weltkrieg zusammen?", "Welche Orte besucht Harrer auf seiner Reise von Indien nach Lhasa?".
   - 2 honest-failure queries: questions the book does *not* answer, e.g. "Was wurde aus Harrer nach 1959?" (book ends earlier), "Welche musikalischen Vorlieben hatte Aufschnaiter?". The verdict should land on `partial` or `inconclusive` with truthful reasoning — *that* is the win, not a hallucinated answer.
   - 1 Hover-Lupe walk: pick a cited node id from one of the answers and run `theogony node <id>`; capture the depth-1 neighbourhood; pick one neighbouring id and `theogony node <neighbour-id>`; capture again. This proves the Hover-Lupe story.
5. After the queries: `theogony reports list -t oneiros -n 5` — verify at least one tick fired during the session. `theogony reports show <oneiros-run-id>` for one of them. Capture in `demo_log.md`.
6. `kill %1` (or whatever brings down `theogony serve`); confirm the lifespan logs the 5-s graceful shutdown cleanly.
7. `theogony reports list -n 30` — final summary of what the run produced. Capture as the closing artefact in `demo_log.md`.

The Plan §5 Week 4 success criteria are checked against the captured numbers. If criterion #4 (5-s p95 query latency) fails on Mac, document + flag — bare-metal Linux is the production target, same hardware-band reasoning as PHX-0046 / PHX-0048.

## Plan deviations to escalate (not anticipated, but if encountered)

- **Gemini quota exhausts mid-ingest.** Document in `demo_log.md` (this is real-world data — happens to operators too). Resume options: (a) wait + retry (Gemini free tier resets daily), (b) switch to OpenAI / Anthropic via `THEOGONY_LLM__PROVIDER` if Talos has an API key, (c) document partial run with the actual numbers it reached. Escalate to Hesiod via PR comment if the resume is non-obvious.
- **Wikidata 429 storm.** PHX-0039 / PHX-0040 / PHX-0041 territory — already filed. Document in `demo_log.md` as a known issue; do not silently work around. The demo proceeds with reduced tier-1 / tier-2 resolution counts.
- **A query returns plausibly wrong information** (e.g. the LLM cites real nodes but synthesises a wrong claim from them). This is the OQ-6 / Athene Gen-2 territory — *expected* in Gen 1 within bounds. Document in `demo_log.md` as an honest finding; do not retry until the answer is "right". One or two such cases in ten queries is exactly the kind of empirical evidence that motivates Gen 2's Athene work.
- **`theogony serve` lifespan fails to cancel within 5 s** during demo shutdown. Escalate immediately — this is an E9 / E8.5 regression. File PHX, do not paper over.
- **Hestia prompt drafting takes > 1 hour.** Lift heavily from `docs/HESTIA.md` (it carries the categories, the watch-points, the "Why Hestia exists" framing). The prompts are short (~30–60 lines each); if drafting feels like creative writing, you are over-engineering — Gen 2 will refine the prompts based on actual sentinel/auditor output.

## Done when

- `docs/etappes/demo_log.md` written with: setup paragraph, ingest summary (real numbers), 10 query sections (question + answer + cited node ids + run_id), one Oneiros tick capture, closing summary.
- `docs/etappes/W4_brief.md` exists (this file, committed for traceability).
- `README.md` restructured per the spec above; copy-paste-runnable demo sequence at the top of "Local development".
- `src/theogony/agents/hestia.py` exists with `HestiaReview` + sub-models; `mypy --strict` clean.
- `prompts/hestia_sentinel.md` + `prompts/hestia_auditor.md` exist; both reference `HestiaReview` schema and `docs/HESTIA.md`; both close with the "Produce ONE HestiaReview as JSON" instruction.
- `tests/test_agents_hestia.py` passes; 3–5 tests covering schema round-trip + `extra="forbid"` + verdict literal + prompt-file existence.
- `docs/IMPLEMENTATION_PLAN_GEN1.md` §5 Week 4 marked DONE with actual numbers from `demo_log.md`; top-of-doc reconciliation paragraph added.
- `pytest tests/ -q` green; `ruff check src/ tests/`, `ruff format --check src/ tests/`, `mypy --strict src/theogony` all green.
- PR body includes: a copy of `demo_log.md`'s top-of-document summary section (one paragraph, the headline numbers); the verdict distribution across the ten queries (e.g. "7 good / 2 partial / 1 inconclusive"); a confirmation that the README's demo sequence was executed end-to-end before opening this PR.

## Scope boundaries (do not touch)

- **`OneirosWorker`, `KnowledgeStore`, retrieval pipeline, FastAPI routes, CLI commands** — production E7/E8/E8.5/E9 code. Untouched.
- **`docs/HESTIA.md`, `docs/VISION.md`, `docs/ARCHITECTURE.md`, `docs/PHILOSOPHY.md`** — the upstream vision docs. The Hestia prompts *reference* them; they are not edited.
- **`prompts/daedalus.md`, `prompts/talos.md`** — existing prompts. Read for structural reference; do not edit.
- **PHX backlog tickets** — none need touching for Week 4. Do not file new ones unless the demo surfaces something concrete (a real bug, a real measured gap).
- **`pyproject.toml`** — no new dependencies. The Hestia work is pure-Pydantic.
- **CI / `.github/workflows/`** — no changes. The new test file inherits the existing `pytest` job.

## Next after Week 4

This PR closes Gen 1's structural surface. After merge:

1. **User records the screen recording** — terminal-session capture of the README's demo sequence, ~5 min, archived as `docs/demo_recording.mp4` or external link. Hesiod cannot do this; it is a deliberate user-action follow-up.
2. **Opportunistic PHX cluster** — Hesiod brief-bundles PHX-0053 (traverse strip-embedding) + 1-2 other low-priority opportunistic tickets in one cleanup PR. Talos's choice of timing.
3. **Detective Mode** (conditional on PHX-0041 re-measurement of Wikidata SPARQL throttling) — if the measurement justifies it, Hesiod briefs the etappe.
4. **PHX-0035 Reviewer agent** — once `demo_log.md` plus 5-10 more weeks of run reports exist on disk, the Reviewer agent has enough corpus to be useful. Probable next-major-etappe after Detective Mode.

The Daedalus design rounds will be invoked as the architecture warrants — not by default. PR #27's pattern (one big, focused PR per etappe) is now the norm.

---

End of brief. Run the demo. Capture the truth. Ship the README + Hestia schemas + the plan-Week-4-marked-DONE in one PR.
