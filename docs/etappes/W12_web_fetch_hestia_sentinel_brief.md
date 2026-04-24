# W12 — WikipediaAdapter + WebFetchAdapter + HestiaSentinel (Living Demo Wave 2, slice 3)

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-24
**Branch:** `feat/w12-web-fetch-hestia-sentinel`
**Scope:** one PR
**Predecessor:** W11 merged on `main`
**Sprint slot:** Living Demo W12 (third of four in Wave 2)

This brief is auto-mode-grade. Every knob is locked. If you find yourself wanting to "improve" something not listed below, you have a brief violation. Stop and file a Phoenix ticket.

---

## Sprint hygiene (mandatory)

1. `git checkout main && git pull --ff-only origin main` (W11 must be merged first; if not, this brief is blocked).
2. `git checkout -b feat/w12-web-fetch-hestia-sentinel`
3. Implement.
4. `git push -u origin feat/w12-web-fetch-hestia-sentinel`
5. `gh pr create --base main --title "feat(curiosity): W12 — Wikipedia + WebFetch + HestiaSentinel"` with the body shape at the bottom.

---

## Why this etappe exists

W11 turned Argus into a researcher, but he can only act on Wikidata and Gutenberg. The user explicitly directed: "Jede Quelle. Websuche. Es soll keine Allowlist gepflegt werden müssen." Wave 2's whole-source promise needs Wikipedia and the open web.

Opening the web also means opening the governance question. The W7-B `HestiaLite` is a whitelist gatekeeper, which is the wrong shape for "any URL the planner picks". W12 replaces it with `HestiaSentinel`, which judges per-candidate (URL, content, claim profile) using deterministic defensive rules first and a small LLM fallback for the unsure cases.

---

## Locked knobs

### Knob 1 — WikipediaAdapter

`src/theogony/acquisition/wikipedia.py`. Uses the Wikipedia REST API:

- search: `GET https://en.wikipedia.org/w/rest.php/v1/search/page?q=<query>&limit=<n>`
- fetch by title: `GET https://en.wikipedia.org/w/rest.php/v1/page/<title>/html` (renders to HTML, then strip via trafilatura)
- alternate language: when query looks German (heuristic: contains umlauts or matches a small German stopword set), try `de.wikipedia.org` first; on miss fall back to `en`.

```python
class WikipediaAdapter:
    @property
    def source_type(self) -> str: return "wikipedia"

    def supports(self, source_type: str) -> bool: return source_type == "wikipedia"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]: ...

    async def acquire(self, candidate: SourceCandidate) -> RawContent: ...
```

`SourceCandidate.metadata` carries `wikipedia_pageid`, `wikipedia_lang`, `wikidata_qid` (when the page returns one in its `wikibase_item` field — link back to the Wikidata anchor).

`RawContent.content` is the trafilatura-extracted plain text of the article body, capped at 200 KB. `RawContent.metadata["wikipedia_lang"]` carries the language code so the EntityResolver knows the source.

User-Agent string (mirrors GutenbergAdapter pattern):

```
theogony/<__version__> (+https://github.com/theogony-project/theogony; open knowledge infrastructure)
```

### Knob 2 — WebFetchAdapter (generic, robots.txt-aware)

`src/theogony/acquisition/web_fetch.py`. The planner emits `WEB_FETCH(url=...)` after using `web_search`. This adapter actually fetches the URL.

```python
class WebFetchAdapter:
    @property
    def source_type(self) -> str: return "web"

    def supports(self, source_type: str) -> bool: return source_type == "web"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        """Web search is the LLM provider's job. This adapter does not search; raise NotImplementedError."""

    async def acquire(self, candidate: SourceCandidate) -> RawContent: ...
```

The `acquire` flow:

1. Validate `candidate.url` is a `https://` URL with a registered TLD. Reject otherwise (`ValueError`, no fetch).
2. Fetch and respect `robots.txt`. Use `urllib.robotparser` (stdlib, no new dep). Cache parsed robots.txt per host with a 1h TTL in-memory.
3. If robots disallows our user-agent → raise a typed `RobotsDisallowedError`. Argus catches and records as a HestiaSentinel-style rejection.
4. GET with timeout 30s, follow redirects (max 5), max response body 5 MiB.
5. Run trafilatura on the response body. If trafilatura returns empty (binary content, paywall stub, etc.) → raise `ContentExtractionFailedError`.
6. Build `RawContent` with `source_type="web"`, `identifier=<sha256(url)>[:16]`, `url=<final_url_after_redirects>`, `content=<extracted_text>`, `bytes_acquired=len(content.encode())`, `metadata={"http_status": ..., "final_url": ..., "content_length": ...}`.

Politeness: 2s minimum delay between requests to the **same host** (mirror Gutenberg pattern), shared with concurrent calls via per-host `asyncio.Lock`.

### Knob 3 — HestiaSentinel (replaces HestiaLite)

New module `src/theogony/agents/hestia_sentinel.py`.

```python
class SentinelDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    UNSURE_ESCALATED = "unsure_escalated"  # only as transient state inside .review()


class HestiaReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]   # never UNSURE; .review() resolves it
    reason: str
    rule_fired: str  # name of rule or "llm_fallback"
    llm_called: bool = False
    llm_cost_eur: float = Field(default=0.0, ge=0.0)


class HestiaSentinel:
    def __init__(self, *, llm: LLMProvider, settings: HestiaSentinelSettings) -> None: ...

    async def review(self, *, candidate: EvaluatorCandidate, context: PlannerContext) -> HestiaReview: ...
```

Rules, in order. First match decides:

1. **`source_type_unknown`** — `candidate.source_step.kind` is not in {wikidata_lookup, gutenberg_search, wikipedia_fetch, web_fetch} → REJECTED. Defensive against schema drift.
2. **`url_scheme_or_host_invalid`** — for `web` candidates: URL is not https, or host parses to an IP literal, or host is in the locked block list (see below) → REJECTED.
3. **`content_size_excessive`** — `candidate.estimated_bytes > settings.max_candidate_bytes` (default 5 MiB) → REJECTED.
4. **`hard_block_keywords_in_label_or_summary`** — case-insensitive substring match against `HARD_BLOCK_KEYWORDS` (locked list below) → REJECTED.
5. **`gutenberg_or_wikidata_or_wikipedia_default_approve`** — for those three source types, no further checks. APPROVED. Rationale: those are public, governed, civilization-scale knowledge sources; trusting them by default is the right base policy. (Their content can still be flagged by the LLM fallback if the URL/title hints at sensitive material.)
6. **`web_no_obvious_block_then_llm_fallback`** — for `web` candidates that survived rules 1-4: the deterministic policy is exhausted. Call the LLM fallback (Knob 4) for a per-candidate judgement.

```python
HARD_BLOCK_KEYWORDS = [
    "child sexual abuse material", "csam",
    "weapons synthesis", "explosive synthesis",
    "bioweapon synthesis", "chemical weapon synthesis",
    "self-harm instructions",
]

LOCKED_HOST_BLOCK_LIST = [
    # Domains that we will not crawl for the demo, ever:
    "facebook.com", "instagram.com", "tiktok.com",   # social media profile pages
    "linkedin.com",                                  # personal profile pages
    "reddit.com",                                    # user-generated, low signal/noise
]
```

Both lists are module constants; not configurable from settings. Adding to them is a code change with a brief amendment.

### Knob 4 — HestiaSentinel LLM fallback

When rule 6 fires, ask the same LLM provider used for the synthesizer (Sonnet 4.6) a short structured question:

System prompt at `src/theogony/agents/prompts/hestia_sentinel.md`:

```
You are HestiaSentinel for Pantheon, the safety auditor for autonomous research.

A research candidate URL has passed deterministic checks. Your job is a final
per-candidate judgement.

Output a JSON object matching this schema:

{ "decision": "approved" | "rejected", "reason": "<one short sentence>" }

Approve when:
- the source is a recognised reference work, news outlet, academic paper, or
  primary document
- the content is encyclopedic, biographical, geographical, historical,
  technical, scientific, or current-events focused

Reject when:
- the source profiles a private individual (not a public figure)
- the content concerns an individual person's private life, health, sexuality,
  religion, or finances without an evidently public scope
- the URL points to commercial junk, SEO spam, content farms, paywall stubs
- the URL appears to be a dating profile, criminal records aggregator, or
  reputation-management site
- the topic asked the user about is itself a narrow attack vector
  (synthesis instructions for weapons, biology, malware, etc.)

Be conservative for personal-information research.
Be permissive for clearly public-knowledge topics.
Output JSON only.
```

Cap: max 200 input tokens, max 100 output tokens, max 3s timeout. Anthropic Sonnet 4.6 cost target: < 0.001 EUR per fallback call. The fallback **never** retries: if the LLM call fails for any reason, default to REJECTED with reason `llm_fallback_unavailable`.

### Knob 5 — HestiaSentinelSettings

```python
class HestiaSentinelSettings(BaseModel):
    """HestiaSentinel per-candidate auditor (Wave 2 W12)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    llm_fallback_enabled: bool = True
    llm_fallback_max_total_tokens: int = Field(default=300, ge=100, le=2000)
    max_candidate_bytes: int = Field(default=5 * 1024 * 1024, ge=1)


class CuriositySettings(BaseModel):
    # ... existing ...
    hestia_sentinel: HestiaSentinelSettings = Field(default_factory=HestiaSentinelSettings)
    # NOTE: hestia_lite stays in settings for one release; deprecation in W13.
```

When `hestia_sentinel.enabled` is True, ArgusAgent uses HestiaSentinel; otherwise it falls back to HestiaLite (W7-B). The demo path enables Sentinel.

### Knob 6 — ArgusAgent wiring update

`src/theogony/agents/argus.py` — extend the constructor:

```python
class ArgusAgent:
    def __init__(
        self,
        *,
        planner: ResearchPlanner,
        executor: ResearchExecutor,
        evaluator: Evaluator,
        hestia: HestiaLiteApproval | HestiaSentinel,   # union type for transitional release
        ingest_runner: IngestRunner,
        settings: ArgusSettings,
    ) -> None: ...
```

The `process` flow's HestiaLite call is renamed `_hestia_review` and dispatches: if `isinstance(hestia, HestiaSentinel)` → call its async `review`; else fall through to the legacy sync `review`. One `if/else`, locked.

`argus_wiring.argus_dispatch_session` decides which Hestia to instantiate from settings.

### Knob 7 — Wikidata cross-reference at ingest

When `IngestionPipeline` consumes a `RawContent` with `metadata["wikidata_qid"]` set (Wikidata or Wikipedia origin), the EntityResolver gets a hint: the named entity at the start of the synthetic content is **already known** to be that Q-ID; skip the wbsearchentities call and go directly to `getEntities`. Code-wise: pass the qid hint into `IngestionPipeline.run` via a new optional kwarg `entity_hint_qid: str | None = None`. The W11 `WikidataAdapter` and the W12 `WikipediaAdapter` set this.

If this adds complexity > 30 LOC in the ingest pipeline → file PHX, stop. The hint is an optimization, not the core; merging the PR without it (planner emits both Wikidata and Wikipedia candidates that resolve normally) is acceptable.

### Knob 8 — New repo dependency: trafilatura

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
research = [
    "trafilatura>=1.12,<2.0",
]
```

Group `research` because not every install needs HTML extraction. The default cockpit-serve and ingest paths do not import trafilatura unless `WebFetchAdapter` or `WikipediaAdapter` is constructed. CI installs `theogony[research]` for the W12+ test surface.

---

## Files to add / change

**New**

- `src/theogony/acquisition/wikipedia.py`
- `src/theogony/acquisition/web_fetch.py`
- `src/theogony/agents/hestia_sentinel.py`
- `src/theogony/agents/prompts/hestia_sentinel.md`
- `tests/test_acquisition_wikipedia.py`
- `tests/test_acquisition_web_fetch.py`
- `tests/test_hestia_sentinel.py`

**Edit**

- `src/theogony/agents/argus.py` — Hestia union type + dispatch.
- `src/theogony/curiosity/research_executor.py` — wire WikipediaAdapter and WebFetchAdapter when present.
- `src/theogony/curiosity/argus_wiring.py` — instantiate the right Hestia from settings.
- `src/theogony/config/settings.py` — add `HestiaSentinelSettings`; keep `HestiaLiteSettings` for one release.
- `src/theogony/extraction/pipeline.py` — optional `entity_hint_qid` kwarg on `run`.
- `pyproject.toml` — add `[project.optional-dependencies] research = ["trafilatura..."]`.

**Forbidden in this PR**

- Any change to ResearchPlanner / Evaluator / WikidataAdapter beyond importing them. W11 stays stable.
- Any change to `src/theogony/cockpit/`. SSE vocabulary is W13.
- Removing HestiaLite. Deprecation is W13.
- Adding any third source vendor besides Wikipedia + generic web. No Brave, no DuckDuckGo, no Common Crawl.
- Adding any new pytest marker. The `living_demo` marker covers the smoke gate.

---

## Acceptance criteria (machine-runnable)

### A1 — Lint and type

```bash
ruff format
ruff check
mypy src/theogony/acquisition src/theogony/agents src/theogony/curiosity src/theogony/extraction/pipeline.py src/theogony/config/settings.py
```

### A2 — Unit tests

```bash
pytest -q tests/test_acquisition_wikipedia.py tests/test_acquisition_web_fetch.py \
         tests/test_hestia_sentinel.py
```

Required behaviours:

- `test_wikipedia_search_returns_candidates_with_pageid`
- `test_wikipedia_acquire_extracts_main_text_via_trafilatura` (use a fixture HTML file, not a live call)
- `test_wikipedia_acquire_records_wikidata_qid_in_metadata_when_present`
- `test_wikipedia_german_query_tries_de_first`
- `test_web_fetch_rejects_http_url`
- `test_web_fetch_rejects_ip_literal_host`
- `test_web_fetch_respects_robots_disallow` (use a fixture robots.txt)
- `test_web_fetch_caches_robots_per_host_for_one_hour`
- `test_web_fetch_extracts_text_via_trafilatura_with_5MB_cap`
- `test_web_fetch_records_final_url_after_redirects`
- `test_hestia_sentinel_approves_wikipedia_by_default`
- `test_hestia_sentinel_approves_gutenberg_by_default`
- `test_hestia_sentinel_rejects_locked_block_list_host`
- `test_hestia_sentinel_rejects_hard_block_keyword_in_label`
- `test_hestia_sentinel_rejects_oversized_candidate`
- `test_hestia_sentinel_calls_llm_fallback_for_unknown_web_candidate`
- `test_hestia_sentinel_rejects_when_llm_fallback_fails`
- `test_argus_dispatch_with_sentinel_when_settings_enabled`

### A3 — Existing test suite stays green

```bash
pytest -q
```

The HestiaLite tests stay (Sentinel is opt-in for one release).

### A4 — Living-demo smoke

```bash
pytest -q -m living_demo
```

The W11 smoke is updated to also exercise a Wikipedia step (StubLLMProvider's deterministic plan is extended in this PR to emit one wikipedia_fetch step in addition to the wikidata_lookup). Use a fixture HTML response so the smoke still runs offline.

### A5 — Manual reset + full demo dry-run

```bash
THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh
.venv/bin/theogony cockpit serve --host 127.0.0.1 --port 8000
# in another shell, with ANTHROPIC_API_KEY set:
curl -N -X POST http://127.0.0.1:8000/cockpit/api/research-request \
     -H 'Content-Type: application/json' \
     -d '{"run_id":"<recent>","query":"Wer war Sven Hedin und was hat er in Tibet erforscht?"}'
```

Expected observation in the cockpit growth panel: a real `ResearchPlan` with steps including at least one `WIKIPEDIA_FETCH` and at least one `WIKIDATA_LOOKUP`, possibly one `WEB_FETCH`. After ingest, re-asking the same question in the Explorer must yield a longer, better-cited answer.

This is the first PR where the demo recording is feasible. Talos does not record it (W13), but Talos must paste the observed phase sequence into the PR body.

---

## STOP-and-file rules

- `urllib.robotparser` cannot interpret modern robots.txt files (e.g. with `Crawl-delay` directives we must parse) → file PHX, stop. Do not pull in a heavier robots library unless explicitly approved.
- trafilatura silently drops main content for >X% of a benchmark batch → file PHX, stop. We will not paper over that with a custom extractor.
- The Wikipedia REST API has rate-limited us to a level where the smoke test fails reliably → file PHX, stop. The API permits 200 req/s anonymous; if we hit that, we have a bug elsewhere.
- The HestiaSentinel LLM fallback prompt cannot reliably parse to JSON → file PHX, stop. Do not add a try-except retry loop in this PR.
- Adding `entity_hint_qid` to `IngestionPipeline.run` would require restructuring the resolver chain → file PHX, ship without the hint, document in PR body.

---

## PR description template

```
W12 — WikipediaAdapter + WebFetchAdapter + HestiaSentinel

Implements Living Demo Wave 2 slice 3 per docs/etappes/W12_web_fetch_hestia_sentinel_brief.md.
Builds on W11. Sister sprint W13 closes the wave with the cockpit + recording.

What this PR does:
- adds WikipediaAdapter (REST API, trafilatura extraction, de->en fallback)
- adds WebFetchAdapter (https only, robots.txt, trafilatura, 5 MiB cap, 2s/host)
- adds HestiaSentinel (deterministic rules + LLM fallback for unsure web candidates)
- wires Sentinel into Argus behind a settings flag
- replaces HestiaLite when Sentinel is enabled (HestiaLite stays for one release)
- adds optional `theogony[research]` dependency group with trafilatura

What this PR does NOT do:
- it does not change the SSE vocabulary or cockpit panel (W13)
- it does not delete HestiaLite
- it does not record the demo (W13)

Manual demo dry-run observed phase sequence:
<paste here>

Acceptance criteria run locally:
- `ruff format && ruff check`
- `mypy src/theogony/acquisition src/theogony/agents src/theogony/curiosity
       src/theogony/extraction/pipeline.py src/theogony/config/settings.py`
- `pytest -q`
- `pytest -q -m living_demo`
- manual reset + research-request POST per A5

PHX tickets filed: <list, or "none">

@hesiod-review
```
