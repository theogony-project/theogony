# W11 — ResearchPlanner + Evaluator + WikidataAdapter (Living Demo Wave 2, slice 2)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w11-research-planner`
**Scope:** one PR
**Predecessor:** W10 merged on `main`
**Sprint slot:** Living Demo W11 (second of four in Wave 2)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (W10 must be merged first; if not, this brief is blocked).
2. `git checkout -b feat/w11-research-planner`
3. Implement.
4. `git push -u origin feat/w11-research-planner`
5. `gh pr create --base main --title "feat(curiosity): W11 — LLM ResearchPlanner + Evaluator + WikidataAdapter"` with the body shape at the bottom.

---

## Why this etappe exists

W10 corrected when triggers fire. W11 corrects what happens after. Today Argus does `gutendex.search(origin_query)`, which is single-source keyword lookup. The vision (and the user's explicit direction) demands a research process: decompose the question, decide what kind of evidence would help, search across multiple sources including the open web, evaluate the findings, and select what to ingest.

W11 builds that. It uses the LLM provider's native `web_search` tool so we do not maintain a search vendor relationship. The planner LLM is allowed to invoke the tool internally during planning; what we receive is a structured `ResearchPlan` that already references concrete URLs, Wikidata Q-IDs, or Gutenberg book numbers.

W11 ships **planner + evaluator + Wikidata adapter only**. Web/Wikipedia adapters and Hestia rework are W12.

---

## Locked knobs

### Knob 1 — ResearchPlanner contract

```python
class PlannerContext(BaseModel):
    """Everything the planner needs to decide a plan."""

    model_config = ConfigDict(extra="forbid")

    origin_query: str
    answer_text_or_none: str | None
    answer_verdict: Literal["good", "partial", "poor", "failed"]
    cited_node_count: int
    gap_class: GapClass
    region_descriptor: RegionDescriptor


class ResearchPlanner:
    def __init__(self, *, llm: LLMProvider, settings: ResearchPlannerSettings) -> None: ...

    async def plan(self, context: PlannerContext) -> ResearchPlan: ...
```

The planner is **always** allowed to return an empty `ResearchPlan(steps=[])`, which the executor treats as "no useful research direction found; emit done immediately". This is honest behaviour, not failure. Do not coerce empty plans into "at least try Gutenberg".

### Knob 2 — Anthropic provider with `web_search` tool

The planner uses the existing `AnthropicLLMProvider` (`src/theogony/agents/llm_anthropic.py`). The Anthropic Messages API supports a server-side `web_search` tool of type `web_search_20250305` (see [Anthropic docs](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/web-search-tool)). The planner call passes the tool in the `tools` array; the model can issue `web_search` calls during its turn and we receive the final structured output once the model is done searching.

Add a new provider method to `LLMProvider` Protocol:

```python
async def complete_with_web_search_for_research_plan(
    self,
    *,
    system_prompt: str,
    user_prompt: str,
    output_schema: type[BaseModel],
    max_search_calls: int = 3,
    max_total_tokens: int = 4000,
) -> tuple[ResearchPlan, ResearchPlannerCost]:
    ...
```

Where `ResearchPlannerCost` is a tiny Pydantic model with `usd_cost: float`, `eur_cost: float`, `search_call_count: int`, `model_id: str`. This goes on `ResearchPlan.planner_cost_eur` (single field) plus the audit log entry (full breakdown).

Implementation lives in `AnthropicLLMProvider`. Other providers (`OpenAILLMProvider`, `GeminiLLMProvider`, `StubLLMProvider`) implement the method as raising `NotImplementedError("web_search planning requires Anthropic")`. **Do not silently degrade.** When the provider does not support the tool, we want a loud failure that the cockpit surfaces; W11's whole point is the planner.

The `StubLLMProvider` is the exception: it returns a deterministic `ResearchPlan` with one `WIKIDATA_LOOKUP` step targeting the first noun-phrase in the query. This keeps the `living_demo` smoke gate runnable without an Anthropic key.

### Knob 3 — Planner system prompt (locked text in the brief)

Lives in `src/theogony/agents/prompts/research_planner.md`. The text is:

```
You are the Research Planner for Pantheon, a knowledge chronicle.

A user asked a question. The system answered, but the answer was weak — either
no citations, low-confidence sources, or off-topic. Your job is to plan a small,
focused research effort to fill the gap.

Output a JSON object matching this schema:

{
  "steps": [
    { "kind": "wikidata_lookup" | "gutenberg_search" | "wikipedia_fetch" | "web_fetch",
      "target": "<provider-native target, see below>",
      "rationale": "<one sentence why this step helps>",
      "expected_evidence_kind": "entity" | "biographical" | "geographic" | "primary_text"
                                | "encyclopedic" | "current_events" }
  ]
}

Rules:
- Emit AT MOST 3 steps. Fewer is better when fewer is enough.
- An empty plan ([]) is allowed when no productive research direction exists.
- "wikidata_lookup": target = a name or Q-id, e.g. "Sven Hedin" or "Q154759".
- "gutenberg_search": target = a focused search query for Project Gutenberg's
  catalogue, NOT the user's natural-language question. Good: "Hedin Tibet
  expedition". Bad: "Was weißt du über Tibet/Hedin".
- "wikipedia_fetch": target = a Wikipedia article title (en preferred, de OK),
  e.g. "Sven Hedin" or "Trans-Himalaya (book series)".
- "web_fetch": target = a single concrete URL. Use the web_search tool first
  to find a strong primary source, then emit web_fetch with the chosen URL.

You have a web_search tool available. Use it sparingly (max 3 calls). Use it
when you need to find URLs for web_fetch steps, or when you need to verify that
a Wikipedia article actually exists, or when the user's question concerns
current events that no static source covers.

Do not invent URLs. Do not invent Wikidata Q-IDs. Do not invent Wikipedia
article titles. If you cannot find a real target, do not emit the step.
```

This prompt is the entire planner brain. Do not add chain-of-thought instructions, JSON examples, or temperature parameters beyond what `AnthropicLLMProvider` already does for its other structured-output calls.

### Knob 4 — Evaluator contract

After the executor (Knob 5) collects candidates from each step, the Evaluator picks 0-N candidates to ingest:

```python
class EvaluatorCandidate(BaseModel):
    """One candidate returned from a research step."""

    model_config = ConfigDict(extra="forbid")

    source_step: ResearchStep
    candidate_label: str           # "Sven Hedin (Q154759)" / "#43497 Trans-Himalaya Vol.1"
    summary: str = ""              # 1-3 sentences, set by the adapter
    estimated_bytes: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluatorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: list[EvaluatorCandidate] = Field(default_factory=list, max_length=3)
    rejected: list[tuple[EvaluatorCandidate, str]] = Field(default_factory=list)
    rationale: str = ""
    evaluator_cost_eur: float = Field(default=0.0, ge=0.0)


class Evaluator:
    def __init__(self, *, llm: LLMProvider) -> None: ...

    async def evaluate(
        self,
        *,
        context: PlannerContext,
        candidates: list[EvaluatorCandidate],
    ) -> EvaluatorDecision: ...
```

The evaluator system prompt lives at `src/theogony/agents/prompts/research_evaluator.md`. The text:

```
You are the Research Evaluator for Pantheon. The Planner produced a plan; the
Executor ran each step and collected candidate sources. Your job is to pick
which candidates should be ingested into the chronicle.

You receive:
- the original question and current weak answer
- the gap_class and a brief region description
- the candidates: each with a label, summary, and estimated size

Output a JSON object matching this schema:

{
  "selected": [<index into candidates list>, ...],
  "rejected": [{ "index": <int>, "reason": "<short reason>" }, ...],
  "rationale": "<one paragraph on the selection logic>"
}

Rules:
- Pick AT MOST 3 candidates. Pick 0 if none clearly help.
- Prefer Wikipedia / Wikidata for encyclopedic gaps; prefer Gutenberg for
  primary-text gaps; prefer specific web sources for current-events gaps.
- Reject duplicates that overlap heavily with already-cited sources.
- Reject candidates whose summary suggests off-topic or low-quality content.
- Total estimated_bytes across selected SHOULD stay under 2 MiB.
```

### Knob 5 — ResearchExecutor

```python
class ResearchExecutor:
    def __init__(
        self,
        *,
        wikidata: WikidataAdapter,
        gutenberg: GutenbergAdapter,
        # wikipedia and web_fetch are W12 — the executor calls them only when present
        wikipedia: WikipediaAdapter | None = None,
        web_fetch: WebFetchAdapter | None = None,
    ) -> None: ...

    async def execute_step(self, step: ResearchStep) -> list[EvaluatorCandidate]:
        ...
```

`execute_step` dispatches by `step.kind`. For W11, only `WIKIDATA_LOOKUP` and `GUTENBERG_SEARCH` produce candidates; the other two return `[]` with a logged warning "adapter not yet wired (W12)". The executor is wired into `argus_wiring.argus_dispatch_session` so adapters share resource lifetimes correctly.

### Knob 6 — WikidataAdapter

A thin wrapper on the existing `extraction.wikidata_client.WikidataClient`. Lives at `src/theogony/acquisition/wikidata.py`. Exposes the AcquisitionAdapter shape (so the executor can treat it uniformly), but its `acquire` step builds a `RawContent` from the Wikidata entity description plus alias list — this gives the ingest pipeline something textual to digest, while the entity's Q-ID is preserved in `RawContent.metadata["wikidata_qid"]` so the EntityResolver immediately re-anchors it to the same node.

```python
class WikidataAdapter:
    @property
    def source_type(self) -> str: return "wikidata"

    def supports(self, source_type: str) -> bool: return source_type == "wikidata"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        """Looks up by name AND by Q-id (depending on whether `query` matches `^Q\\d+$`)."""

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        """Builds a synthetic 'wikidata article' text from labels, aliases, descriptions."""
```

The synthetic content is small (typically 1-5 KB). It is content the EntityResolver in the ingest pipeline already understands — Q-IDs land back on the right node automatically.

### Knob 7 — Argus refactor

`src/theogony/agents/argus.py` is rewritten:

```python
class ArgusAgent:
    def __init__(
        self,
        *,
        planner: ResearchPlanner,
        executor: ResearchExecutor,
        evaluator: Evaluator,
        hestia: HestiaLiteApproval,   # W12 will swap to HestiaSentinel
        ingest_runner: IngestRunner,
        settings: ArgusSettings,
    ) -> None: ...

    async def process(self, trigger: CuriosityTrigger) -> ArgusResult: ...
```

The new `process` flow:

1. Build `PlannerContext` from the trigger + a fresh QueryRunReport lookup of the answer.
2. `plan = await planner.plan(context)` → write `plan` back into `trigger.research_plan` and update the on-disk `CuriosityRunReport` immediately (so the cockpit can render the plan even before steps execute; W13 will subscribe).
3. Empty plan? outcome `NO_PLANNED_STEPS`, no LLM evaluator call, return.
4. For each `step in plan.steps`: collect `EvaluatorCandidate`s from `executor.execute_step(step)`.
5. `decision = await evaluator.evaluate(context, candidates)` → write `decision` into the report.
6. For each `selected_candidate in decision.selected`: HestiaLite review (still in this PR; replaced in W12). On reject, record outcome and continue. On approve: acquire → ingest, record `ingest_run_id`.
7. Outcomes: `APPROVED_AND_INGESTED` (≥1 ingested), `NO_PLANNED_STEPS`, `NO_CANDIDATE_SELECTED`, `ALL_REJECTED_BY_HESTIA`, `INGEST_FAILED`.

The W7-B `ArgusOutcome` enum is **extended** (do not break existing readers; add new values, do not remove old):

```python
class ArgusOutcome(StrEnum):
    APPROVED_AND_INGESTED = "approved_and_ingested"
    APPROVED_INGEST_FAILED = "approved_ingest_failed"
    REJECTED_BY_HESTIA = "rejected_by_hestia"           # legacy single-source case
    NO_CANDIDATES = "no_candidates"                     # legacy single-source case
    NO_CANDIDATE_ABOVE_THRESHOLD = "no_candidate_above_threshold"  # legacy
    UNSUPPORTED_SOURCE_TYPE = "unsupported_source_type"  # legacy
    BUDGET_EXCEEDED = "budget_exceeded"
    NO_PLANNED_STEPS = "no_planned_steps"               # NEW
    NO_CANDIDATE_SELECTED = "no_candidate_selected"     # NEW
    ALL_REJECTED_BY_HESTIA = "all_rejected_by_hestia"   # NEW (multi-candidate)
    INGEST_FAILED = "ingest_failed"                     # NEW (any step failed)
```

The legacy single-source path is no longer reachable via the bridge after W11 (the planner always runs first), but the enum values stay for the historical reports on disk.

### Knob 8 — Settings

```python
class ResearchPlannerSettings(BaseModel):
    """LLM-driven research planner (Wave 2 W11)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False                 # default off; demo enables explicitly
    max_search_calls: int = Field(default=3, ge=0, le=10)
    max_total_tokens: int = Field(default=4000, ge=500, le=20000)
    max_steps_per_plan: int = Field(default=3, ge=0, le=5)


class EvaluatorSettings(BaseModel):
    """LLM-driven evaluator (Wave 2 W11)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False                 # default off; demo enables explicitly
    max_total_tokens: int = Field(default=2000, ge=200, le=10000)


class CuriositySettings(BaseModel):
    # ... existing fields ...
    research_planner: ResearchPlannerSettings = Field(default_factory=ResearchPlannerSettings)
    evaluator: EvaluatorSettings = Field(default_factory=EvaluatorSettings)
```

Default-off everywhere. The demo path enables both. Without them enabled, Argus falls back to the W7-B-style direct Gutenberg lookup so the system never silently breaks for users who do not opt in.

---

## Files to add / change

**New**

- `src/theogony/agents/research_planner.py`
- `src/theogony/agents/research_evaluator.py`
- `src/theogony/agents/prompts/research_planner.md`
- `src/theogony/agents/prompts/research_evaluator.md`
- `src/theogony/curiosity/research_executor.py`
- `src/theogony/acquisition/wikidata.py`
- `tests/test_research_planner.py`
- `tests/test_research_evaluator.py`
- `tests/test_research_executor.py`
- `tests/test_acquisition_wikidata.py`
- `tests/test_argus_with_planner.py`

**Edit**

- `src/theogony/agents/argus.py` — rewire per Knob 7. Keep legacy outcome values.
- `src/theogony/agents/llm.py` — add `complete_with_web_search_for_research_plan` to the Protocol; add `ResearchPlannerCost` dataclass.
- `src/theogony/agents/llm_anthropic.py` — implement the new method against `web_search_20250305`.
- `src/theogony/agents/llm_openai.py`, `llm_gemini.py` — raise `NotImplementedError`.
- `src/theogony/agents/llm.py` `StubLLMProvider` — return the deterministic single-step plan.
- `src/theogony/curiosity/argus_wiring.py` — instantiate planner / evaluator / executor; pass into `ArgusAgent`.
- `src/theogony/config/settings.py` — add `ResearchPlannerSettings`, `EvaluatorSettings`.
- `tests/test_argus.py` — keep legacy tests for the no-planner fallback.

**Forbidden in this PR**

- Any change under `src/theogony/cockpit/` beyond what is strictly required by the Argus signature change. The SSE vocabulary stays as W8 left it; W13 redoes it.
- Any new acquisition adapter besides `WikidataAdapter`. Wikipedia and WebFetch are W12.
- Any change to `HestiaLiteApproval`. W12 replaces it.
- Any new dependency. `httpx`, `pydantic`, `anthropic` are already in the repo.
- Any backlog clean-up.

---

## Acceptance criteria (machine-runnable)

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/agents src/theogony/curiosity src/theogony/acquisition src/theogony/config/settings.py
```

### A2 — Unit tests

```bash
pytest -q tests/test_research_planner.py tests/test_research_evaluator.py \
         tests/test_research_executor.py tests/test_acquisition_wikidata.py \
         tests/test_argus_with_planner.py
```

Required behaviours:

- `test_planner_returns_empty_plan_when_llm_returns_empty_steps`
- `test_planner_rejects_more_than_max_steps_via_schema`
- `test_planner_records_cost_on_returned_plan`
- `test_anthropic_provider_invokes_web_search_tool_for_planner` (use `respx` or the existing `httpx.MockTransport` pattern; assert the tools array contains `web_search_20250305`)
- `test_stub_provider_returns_deterministic_one_step_plan`
- `test_other_providers_raise_not_implemented_for_planner`
- `test_evaluator_returns_empty_selection_when_candidates_empty`
- `test_evaluator_caps_selection_at_three`
- `test_executor_dispatches_wikidata_step_to_wikidata_adapter`
- `test_executor_returns_empty_for_unwired_kinds_with_warning`
- `test_wikidata_adapter_search_by_name_returns_candidates`
- `test_wikidata_adapter_search_by_qid_returns_one_candidate`
- `test_wikidata_adapter_acquire_builds_raw_content_with_qid_metadata`
- `test_argus_with_planner_happy_path_writes_plan_then_decision_to_curiosity_report`
- `test_argus_outcome_no_planned_steps_when_planner_returns_empty`
- `test_argus_outcome_no_candidate_selected_when_evaluator_picks_none`
- `test_argus_legacy_path_still_works_when_planner_disabled`

### A3 — Existing test suite stays green

```bash
pytest -q
```

### A4 — Living-demo smoke

```bash
pytest -q -m living_demo
```

The W7-B smoke is updated to the planner-enabled path. The deterministic `StubLLMProvider` plan from Knob 2 makes this runnable without an Anthropic key.

### A5 — Optional live planner test (gated)

Add `tests/test_research_planner_live.py` with `@pytest.mark.live_anthropic`. Marker is opt-in only:

```bash
ANTHROPIC_API_KEY=sk-... THEOGONY_RUN_LIVE_ANTHROPIC=1 \
  pytest -q -m live_anthropic
```

Tests one end-to-end planner call with the real Anthropic provider against the test query "Wer war Sven Hedin und was hat er in Tibet erforscht?". Assert: at least one step in the returned plan, total cost < 0.05 EUR, runtime < 30s. Document the marker in `pyproject.toml`.

This test is the only authority for "the web_search tool actually works". CI does not run it; the user runs it during PR review or before recording.

---

## STOP-and-file rules

- The `web_search_20250305` tool ID has changed in the Anthropic SDK between versions and the current pin no longer accepts it → file PHX, stop, do not paper over with try/except.
- The `WikidataClient` shape does not allow building a `RawContent` from an entity payload without going through the EntityResolver pipeline → file PHX, stop. Adapter must be a thin wrapper, not a re-implementation of resolution.
- `ArgusAgent.process` cannot be rewritten without breaking the W7-B legacy fallback path → file PHX, stop. Both paths must coexist for one release cycle.

---

## PR description template

```
W11 — LLM ResearchPlanner + Evaluator + WikidataAdapter

Implements Living Demo Wave 2 slice 2 per docs/etappes/W11_research_planner_brief.md.
Builds on W10. Sister sprints W12, W13 follow.

What this PR does:
- adds ResearchPlanner using Anthropic Sonnet 4.6 with native web_search tool
- adds Evaluator that picks 0-3 candidates per research run
- adds ResearchExecutor and WikidataAdapter
- rewires ArgusAgent to plan -> execute -> evaluate -> hestia -> ingest
- keeps the legacy single-source path as a default-off fallback

What this PR does NOT do:
- it does not add Wikipedia or generic web fetch (W12)
- it does not replace HestiaLite (W12)
- it does not change the SSE vocabulary (W13)
- it does not add a new LLM provider; only Anthropic supports the planner

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/agents src/theogony/curiosity src/theogony/acquisition src/theogony/config/settings.py`
- `pytest -q`
- `pytest -q -m living_demo`
- (optional) `THEOGONY_RUN_LIVE_ANTHROPIC=1 pytest -q -m live_anthropic`

PHX tickets filed: <list, or "none">

@hesiod-review
```
