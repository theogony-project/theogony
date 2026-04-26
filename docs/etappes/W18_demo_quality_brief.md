# W18 - Demo Quality: Faster Ingest, Relation Edges, and Honest Knowledge Quality

**From:** Hesiod-2
**To:** Talos (auto-mode)
**Date:** 2026-04-26
**Branch:** `feat/w18-demo-quality`
**Scope:** one PR (quality of the living demo's knowledge production path)
**Predecessor:** W17.5 is on `main` (PR #109 / #110 / #111). Strategy-game analogy is on `main` (PR #112).
**Sprint slot:** Living Demo W18

This is **not** a new architecture sprint and **not** another Cockpit UI-polish pass (W17.5-B already targeted legibility). It fixes why the live demo still **fails knowledge-quality expectations** after W17.5: the growth loop can run, but ingests are often **slow**, **`verdict=poor`**, **relation-poor** (e.g. relation extraction **not wired** / skipped in the Cockpit growth path), and **insufficiently explainable** to the operator. **W18** makes growth output **relation-rich, bounded, and explainable** within immune-system doctrine.

---

## Local observation that triggered this brief

The 2026-04-26 local Cockpit run showed:

- Browser console had no meaningful JS crash.
- `/health` works.
- `Research this further` produced real acquired pool entries.
- Verification pool had `total=3`, all `unobserved`.
- New ingest reports existed for `Sven_Hedin` and `Transhimalaya`.
- All new ingest reports had `verdict=poor`.
- Report reasons were mainly:
  - `low_tier_ratio=0.80/0.84 (>0.60 poor-threshold)`
- The expensive stage was:
  - `mentions_resolved`: 70-166 seconds for single Wikipedia pages.
- The relation stage was skipped:
  - `relations_extracted`: `No relation_extractor configured`

So the system is no longer completely stalled. But it is not yet convincing: it fetches material, spends too long resolving mentions, writes many low-tier nodes, and stores few/no relation edges. The Cockpit also does not make this quality problem legible enough.

---

## Sprint goal

After W18, a local Sven Hedin-style research run should:

1. finish ingest in a demo-acceptable time budget,
2. extract at least some relation edges in the Cockpit growth path,
3. reduce noisy low-tier node production by bounding and prioritizing mention resolution,
4. show ingest quality and bottlenecks plainly in the Cockpit,
5. still preserve the immune-system doctrine: post-hoc verification, no pre-gate truth filter.

---

## Doctrine constraints

- Do not add a content-judgement pre-gate.
- Do not synchronously run Athene/Chronos/Nemesis/Eris/Mnemosyne inside ingest.
- Do not hide `poor` reports or fake a better verdict.
- Do not lower quality thresholds just to make reports green.
- Do not remove low-tier nodes globally; reduce noisy demo ingestion by better bounded selection.
- Do not introduce a new LLM provider.
- Do not redesign the research planner/evaluator.

---

## Knob 1 - Add a bounded demo-ingest profile

The Cockpit growth path needs bounded defaults that are good enough for live demos.

Add settings under `CockpitSettings`:

```python
demo_ingest_ner_sentence_limit: int = Field(default=60, ge=1, le=500)
demo_ingest_max_resolve_mentions: int = Field(default=120, ge=1, le=1000)
demo_ingest_max_relation_sentences: int = Field(default=24, ge=0, le=200)
demo_ingest_relations_enabled: bool = True
```

Rules:

- These settings affect Cockpit/growth demo ingestion only.
- CLI/API ingest behavior remains controlled by its existing flags.
- The demo profile must be visible in logs or ingest report stage notes.

Update Cockpit wiring:

- `src/theogony/cockpit/growth_stream.py`
  - pass `ner_sentence_limit=settings.cockpit.demo_ingest_ner_sentence_limit`
  - pass `max_resolve_mentions=settings.cockpit.demo_ingest_max_resolve_mentions`
  - pass `max_relation_sentences=settings.cockpit.demo_ingest_max_relation_sentences`
  - create `RelationExtractor(llm=llm, audit_log=audit)` when `demo_ingest_relations_enabled` is true
- `src/theogony/curiosity/argus_wiring.py`
  - keep CLI/dispatcher behavior unchanged unless this wiring is explicitly used by Cockpit.

Acceptance:

- Unit test proves Cockpit pipeline receives the Cockpit demo limits.
- Unit test proves CLI ingest still controls limits through existing CLI options.

---

## Knob 2 - Add `max_resolve_mentions` to `IngestionPipeline`

`ner_sentence_limit` bounds sentences, but a Wikipedia page can still produce too many mentions. Add a second bound after NER and before entity resolution.

Extend `IngestionPipeline.__init__`:

```python
max_resolve_mentions: int | None = None
```

Behavior:

1. Build `all_mentions` from NER as today.
2. If `max_resolve_mentions is None`, keep current behavior.
3. If set, select a bounded subset before `_stage_resolve`.
4. The report still records the original NER summary honestly.
5. Add stage note on `mentions_resolved`, e.g.:
   - `resolved 120/765 mentions after demo cap`

Selection policy:

- Preserve original sentence order.
- Deduplicate exact normalized mention text after keeping first occurrence.
- Prefer entity labels with types:
  - `PERSON`, `ORG`, `GPE`, `LOC`, `FAC`, `WORK_OF_ART`, `EVENT`, `PRODUCT`
- Deprioritize:
  - `CARDINAL`, `QUANTITY`, `DATE`, `TIME`, `PERCENT`, `MONEY`, `ORDINAL`
- Always keep at least one mention per sentence until the cap is reached when possible.

This is not a truth filter. It is an operational cost/quality bound for demo ingestion.

Acceptance tests:

- `max_resolve_mentions=None` preserves current mention count.
- cap selects no more than N mentions.
- high-signal entity types are preferred over numeric/date mentions.
- report/stage note exposes the cap.

---

## Knob 3 - Enable relation extraction in Cockpit growth path

The local run showed `relations_extracted` skipped. That makes the Chronik feel like a bag of nodes, not a living graph.

In Cockpit growth ingestion:

- Instantiate `RelationExtractor(llm=llm, audit_log=audit)` when `settings.cockpit.demo_ingest_relations_enabled` is true.
- Pass `max_relation_sentences=settings.cockpit.demo_ingest_max_relation_sentences`.
- Keep relation extraction bounded.

Acceptance:

- Cockpit growth ingest report no longer says `No relation_extractor configured` when enabled.
- Test with a stub relation extractor yields `relations.attempted > 0` and `store.edges_upserted > 0`.
- If relation extraction raises for one sentence, pipeline continues, as current relation stage intends.

---

## Knob 4 - Add relation/quality summary to the growth panel

The Cockpit must tell the operator what quality was produced.

Update:

- `src/theogony/cockpit/growth_stream.py`
- `src/theogony/cockpit/static/js/explorer_growth.js`
- tests for growth event rendering

On `ingested` and/or `research_complete`, include from `IngestRunReport`:

- `ingest_verdict`
- `ingest_reasoning`
- `word_count`
- `sentence_count`
- `nodes_upserted`
- `edges_upserted`
- `low_tier_ratio`
- `resolution_tier_counts` if already available in report model
- `relations_attempted`
- `relations_parsed_ok`
- `relations_dropped_total`
- slowest stage name/duration

Render under Outcome:

```text
Ingest quality: poor - low_tier_ratio=0.80 (>0.60 poor-threshold)
Stored: 123 nodes, 12 edges
Relations: attempted=24 parsed=12 dropped=3
Slowest stage: mentions_resolved 42.1s
```

Rules:

- Do not hide `poor`.
- Do not show raw JSON.
- If multiple candidates ingested, show one compact line per candidate, max 5.

Acceptance:

- Fixture poor ingest report -> UI renders quality reason.
- Fixture report with relation edges -> UI renders relation counts.
- Fixture slow `mentions_resolved` -> UI renders slowest stage.

---

## Knob 5 - Add a demo-quality smoke test

Add a focused test that proves the Sven-Hedin-like path can produce graph structure without live network or live LLM.

Create:

- `tests/cockpit/test_demo_quality_growth.py` or equivalent.

Test shape:

1. Use stub acquisition content with a short Sven Hedin paragraph containing people/places and 2-3 relation-rich sentences.
2. Use stub/fake resolver or fake Wikidata client where needed.
3. Use stub relation extractor returning at least two relations.
4. Run the same Cockpit ingest wiring function or a narrow helper extracted from it.
5. Assert:
   - report verdict is not failed,
   - `relations_extracted` not skipped,
   - edges are upserted,
   - report exposes bounded mention cap note,
   - growth event payload includes ingest quality fields.

Do not require Anthropic, Wikidata, Wikipedia, Neo4j, or external network for this test.

---

## Knob 6 - Add a live characterization command, gated by env

Add a documented, optional characterization target for the actual live demo path.

Could be a pytest marker or demo script:

```bash
THEOGONY_RUN_LIVE_DEMO_QUALITY=1 pytest -q tests/characterization/test_live_demo_quality.py
```

It should:

- skip unless env var is set,
- use configured live LLM and live web/Wikipedia path,
- run one bounded Sven Hedin-style research/ingest,
- assert:
  - pool total increases,
  - at least one ingest report is written,
  - relation stage is not skipped if relations enabled,
  - total wall-clock stays under a generous ceiling, e.g. 180s for one candidate,
  - failure output prints report path and verdict reasoning.

If this is too much for W18, add the skipped test scaffold and file a PHX note. But prefer implementing it; this is the live edge that keeps biting us.

---

## Knob 7 - Do not call this "fixed" unless the demo loop improves

Update `demo/wave3_local_test.md` with a W18 quality section:

- expected pool entries after research,
- expected ingest quality line in Cockpit,
- expected relation count line,
- expected slowest-stage line,
- how to run the optional live characterization test.

Update `docs/LIVING_DEMO.md` with one paragraph:

- W18 makes the demo judge knowledge production, not just worker existence.

---

## Acceptance criteria

Run:

```bash
ruff format
ruff check
pytest -q tests/cockpit
pytest -q tests/extraction
pytest -q tests/agents/test_argus.py
pytest -q
```

Optional live characterization:

```bash
THEOGONY_RUN_LIVE_DEMO_QUALITY=1 pytest -q tests/characterization/test_live_demo_quality.py
```

Manual smoke:

1. Start Cockpit with the current demo script.
2. Ask: `Wer war Sven Hedin und was hat er in Tibet erforscht?`
3. Click `Research this further`.
4. Expected:
   - pool total increases,
   - ingest quality line appears,
   - slowest stage is visible,
   - relation stage is not skipped,
   - at least one relation/edge count is non-zero when the relation extractor returns usable output,
   - the run is bounded enough to watch live.

---

## STOP-and-file rules

- If enabling relation extraction would push the live run beyond acceptable latency even with `max_relation_sentences=24`, reduce the default to 12 and file PHX for relation-extraction throughput.
- If `max_resolve_mentions` requires a large resolver rewrite, implement the selection just before `_stage_resolve` in `IngestionPipeline` and file PHX for deeper resolver batching.
- If low-tier ratio remains high after bounded selection, do not lower thresholds. Show it honestly and file PHX for resolver quality.
- If this PR grows beyond about 600 LOC excluding tests/docs, split: W18-A for bounded ingest + relation enabling, W18-B for Cockpit quality display.

---

## PR description template

```markdown
W18 - Demo quality: bounded ingest + relation edges

What this PR does:
- adds Cockpit demo-ingest limits for NER, mention resolution, and relation extraction
- enables bounded relation extraction in the Cockpit growth path
- adds `max_resolve_mentions` to the ingestion pipeline
- surfaces ingest quality, relation counts, and slowest stage in the growth panel
- adds focused tests for demo-quality knowledge production
- documents the W18 local/live characterization path

What this PR does NOT do:
- no content pre-gate
- no synchronous immune worker invocation
- no new LLM provider
- no threshold lowering to make reports look green
- no research planner redesign

Acceptance criteria run locally:
- `ruff format && ruff check`
- targeted tests from the brief
- `pytest -q`
- optional live characterization if env is available

Notes / deviations:
<list or "none">

PHX tickets filed:
<list or "none">
```
