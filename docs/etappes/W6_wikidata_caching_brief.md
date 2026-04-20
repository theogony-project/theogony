# W6 — Persistent Wikidata caching (and nothing else)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-20  
**Branch:** new branch off `main`, e.g. `feat/wikidata-caching`  
**Scope:** one PR, tightly scoped  
**Predecessor:** PR #32 merged — W5 established two truths:

1. Anthropic Haiku 4.5 is live and usable.
2. The public Wikidata path is now the dominant bottleneck for repeat ingest work.

Direct brief, no Daedalus. This is an execution / infra-hardening etappe, not an architecture round.

---

## Why this etappe exists

W5 proved that the LLM layer is no longer the critical blocker. The slow path is now Wikidata:

- `query.wikidata.org` throttles aggressively on Hedin-scale workloads.
- `WikidataClient` explicitly says it **does not cache between calls**.
- `IngestionPipeline._resolution_summary_from()` still hard-codes:

```python
wikidata_api_requests=0
cache_hits=0
failures_after_retry=0
```

That means:

1. We pay the same network latency every rerun.
2. We cannot measure whether caching helped, because the report counters are fake zeros.
3. The next contributor has no honest before/after instrumentation.

**This PR fixes exactly that.**

Not mirrors.  
Not a Wikidata subset.  
Not SPARQL batching redesign.  
Just caching.

---

## Goal

Add a **persistent, local, read-through cache** for Wikidata responses so that:

- repeated ingests of the same corpus stop paying the full Wikidata round-trip cost,
- overlapping corpora reuse prior Wikidata work,
- `IngestRunReport.resolution` shows real `wikidata_api_requests`, `cache_hits`, and `failures_after_retry`,
- the system gains a first small step toward self-owned knowledge infrastructure without widening scope into mirrors or dumps.

---

## Scope decisions (read first)

### 1. Persistent cache, not just in-memory memoization

This etappe is about **surviving process restarts and helping reruns**.  
An in-memory dict inside one `WikidataClient` instance is not enough.

Use a persistent local store on disk, under `data/`, e.g.:

```text
data/wikidata_cache.sqlite
```

SQLite is the right tool here:

- already a project pattern (`ExtractionAuditLog`),
- no extra service,
- atomic enough,
- inspectable by humans with `sqlite3`.

### 2. Cache the four Wikidata read operations we actually use

The cache must cover the current `WikidataClient` surface:

1. `search(mention, language, limit)`
2. `fetch_labels_aliases(qids, languages)`
3. `fetch_types(qids)`
4. `fetch_bio_facts(qids, language="en")`

No speculative future methods.

### 3. Do not cache transient failures

Do **not** write 429 / 502 / transport errors / timeouts into the cache.

Cache:

- successful payloads,
- and explicit empty-success results where the upstream answered cleanly with “nothing found”.

Do not cache:

- retryable HTTP failures,
- malformed payloads,
- parse failures,
- local exceptions.

### 4. Honest expectation: caching helps reruns first, not the very first dense book

Do not oversell this PR.

Caching will materially help:

- repeated runs of the same book,
- similar travel-literature corpora with overlapping people / places / works,
- repeated disambiguation of the same Q-IDs across books.

Caching will **not** make the *first ever* full-unbounded Hedin ingest magically cheap, because much of the pain there is first-touch Wikidata work.

The PR body and any docs you touch must say this plainly.

### 5. No scope creep into PHX-0033

This PR is **not**:

- a local Wikidata subset,
- a Toolforge path,
- a self-hosted mirror,
- request collapsing beyond what falls out naturally from the cache,
- a new resolver algorithm,
- a new queue / worker topology.

If you feel tempted toward any of those, stop and escalate.

---

## Concrete implementation

### A. Add a small cache module

Create a focused module, e.g.:

```text
src/theogony/extraction/wikidata_cache.py
```

with a tiny API, something in the spirit of:

- `get_search(...)`
- `put_search(...)`
- `get_labels_aliases(...)`
- `put_labels_aliases(...)`
- `get_types(...)`
- `put_types(...)`
- `get_bio_facts(...)`
- `put_bio_facts(...)`

Implementation freedom is yours, but the design constraints are:

- SQLite-backed
- explicit schema
- JSON payload storage is fine
- deterministic key normalisation
- no hidden magic

If you prefer a generic `(namespace, key_json) -> payload_json` table instead of four bespoke tables, that is acceptable **if** the key normalisation remains readable and testable.

### B. Keying rules

#### `search()`

Key on:

- fully normalised mention string,
- language,
- limit.

Store the full list of `WikidataCandidate` DTO payloads.

It is acceptable to cache empty successful search results.

#### `fetch_labels_aliases()`

Do **not** key on the whole batch as one blob.

Cache per:

- `qid`
- ordered / canonicalised language set

Reason: partial batch hits matter. If 49 Q-IDs are cached and 1 is not, the client should fetch only the miss.

#### `fetch_types()`

Cache per `qid`.

#### `fetch_bio_facts()`

Cache per:

- `qid`
- `language`

### C. `WikidataClient` becomes cache-aware

Extend `WikidataClient.__init__()` with an optional cache dependency, e.g.:

```python
cache: WikidataCache | None = None
```

The client should:

- check cache first,
- fetch only misses,
- write successful misses back to cache,
- merge cached and live-fetched fragments into one return value.

This is especially important for:

- `fetch_labels_aliases()`
- `fetch_types()`
- `fetch_bio_facts()`

because those are naturally partial-hit methods.

### D. Add real counters to `WikidataClient`

Expose honest counters for one client lifetime:

- `api_requests`
- `cache_hits`
- `failures_after_retry`

Definition:

- `api_requests`: actual upstream HTTP calls made after cache misses.
- `cache_hits`: number of logical items served from cache (not just number of SQL lookups).
- `failures_after_retry`: number of upstream requests that still failed after retry logic exhausted.

Keep this simple and documented. The point is trend visibility, not theoretical purity.

### E. Wire counters into the ingest report

Replace the current fake zeros in `src/theogony/extraction/pipeline.py` with real values from the `WikidataClient` used by the resolver.

After this PR, `ResolutionSummary` in the report must finally tell the truth.

### F. Use existing `data_dir`

Do not invent a sprawling new config surface unless you genuinely need it.

The default cache location should derive from existing settings, e.g.:

```python
settings.data_dir / "wikidata_cache.sqlite"
```

If you need exactly one toggle like “disable cache for a test”, keep it minimal.

Bias toward:

- one default path,
- maybe one boolean enable/disable switch,
- no TTL tuning matrix,
- no premature cache-admin CLI.

### G. Minimal staleness policy

Prefer the simplest policy that is honest and shippable.

Recommended default:

- **no active expiry** in Gen 1 / early Gen 2,
- cache is manually deletable by removing `data/wikidata_cache.sqlite`.

Reason:

- labels, aliases, `P31`, and Stage-4 bio facts are stable enough for our current workflow,
- TTL adds policy complexity with little practical gain right now,
- PHX-0033 will eventually supersede this for serious offline operation.

If you strongly prefer a TTL, keep it single-value and conservative. But “no expiry yet” is fully acceptable here.

---

## Files likely in scope

Expected touch set (adjust if needed, but keep it tight):

- `src/theogony/extraction/wikidata_cache.py` — new
- `src/theogony/extraction/wikidata_client.py`
- `src/theogony/extraction/pipeline.py`
- maybe `src/theogony/config/settings.py` (only if a tiny cache toggle/path is truly needed)
- `tests/test_extraction_wikidata_client.py`
- `tests/test_extraction_pipeline.py`
- maybe `tests/test_extraction_resolve.py`
- maybe README one-liner in “Going further” or ops note if you think cache-file visibility helps contributors

Not more unless necessary.

---

## Tests and verification

### Required tests

Add / update focused tests for:

1. **Search cache hit skips HTTP**
   - first call hits mocked HTTP,
   - second identical call is cache-served.

2. **Partial batch hit for `fetch_labels_aliases()`**
   - some Q-IDs already cached,
   - only misses trigger upstream call,
   - merged output is complete and deterministic.

3. **Partial batch hit for `fetch_types()`**
   - same pattern as above.

4. **Persistent cache survives client recreation**
   - create cache on disk,
   - construct a new `WikidataClient`,
   - confirm hits come from persisted cache rather than new mocked HTTP calls.

5. **Report counters are real**
   - pipeline / resolver test that asserts `wikidata_api_requests` and `cache_hits` are no longer hard-coded zeros.

### Verification run

Run one cheap empirical check, not a full expensive validation round:

```bash
theogony ingest 43497 --sentences 50
theogony ingest 43497 --sentences 50
```

same `data/` directory, same machine, same provider.

Document in the PR body:

- first run `wikidata_api_requests`
- second run `wikidata_api_requests`
- second run `cache_hits`
- before/after wall-clock delta

No need to edit `demo_log.md` for this. PR body is enough.

If `--sentences 50` turns out too noisy, use a smaller controlled fixture or a resolver-only benchmark — but keep the verification cheap.

### Standard suite

Before pushing:

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy src/
pytest -q
```

If you add a live or semi-live benchmark command, keep it out of `pytest` by default.

---

## Success criteria

This etappe is successful if all of the following are true:

1. Re-running the same small ingest against the same `data/` directory makes **substantially fewer** upstream Wikidata requests than the first run.
2. `IngestRunReport.resolution.wikidata_api_requests` is non-zero and believable on first run.
3. `IngestRunReport.resolution.cache_hits` is non-zero and believable on rerun.
4. No behavior change in resolver semantics: same node selection, same tiering, same failure modes — just fewer network round-trips.
5. The PR body states the honest limit: this is a **rerun / overlap accelerator**, not a substitute for PHX-0033.

---

## Out of scope

Explicitly do **not** do these here:

- self-hosted Wikidata mirror
- travel-literature subset / PHX-0033 implementation
- Toolforge path
- batch-size retuning of the public SPARQL strategy
- resolver heuristic changes
- multi-process shared locking sophistication
- cache invalidation UI / CLI
- cache warming jobs
- documentation rewrite of the whole demo flow

If you discover a small README note is warranted, keep it to one paragraph max.

---

## Escalation

Escalate to Hesiod instead of deciding silently if any of these happen:

1. The cleanest implementation clearly requires a new settings group and not just a default path under `data_dir`.
2. Cache key design becomes ambiguous enough that two sensible implementations would produce materially different hit rates.
3. Wiring the real counters into `IngestRunReport` forces broader changes to reporting schemas than expected.
4. You discover existing hidden caching that contradicts this brief.
5. The cheap verification run shows almost no benefit — that would mean our mental model is wrong and we should reassess before adding complexity.

Otherwise: proceed, push, open one PR, and ping when CI is green.
