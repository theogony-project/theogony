# S2.5 — Wikidata5m Bulk Seed Implementation Brief

**From:** Chaos
**To:** Talos (default). Daedalus only if architecture-level clarification is needed (it shouldn't be — S2.5 is fully specified in [`docs/MESH_MIGRATION_PLAN.md`](../MESH_MIGRATION_PLAN.md) §"Step S2.5").
**Date:** 2026-05-15
**Branch:** new branch off `main`, e.g. `feat/mesh-s25-wikidata5m-bulk-seed`
**Scope:** one PR for the smoke-test loop; further PRs (per smoke-test iteration / per scaled run) follow.
**Predecessor PRs (already merged on `main`):**

- #149 — S1 substrate skeleton
- #151 — S2 initial Kadmos v2 ingestion
- #154 — S2 dense paragraph topology + IngestRunReport
- #156 — doctrine clarification ("no raw text in substrate", description size bound)
- #157 — added S2.5 step to migration plan
- #158 — filed PHX-1030
- #159 — refreshed PHX-1001 status

**Lifecycle ticket:** [`PHX-1030`](../../phoenix-backlog/PHX-1030.yaml).

This brief is a hand-off, not a re-derivation. The architecture is decided in [`MESH_MIGRATION_PLAN.md`](../MESH_MIGRATION_PLAN.md) §"Step S2.5". Read that section first; this brief sequences the work and locks the smoke-test-first strategy the operator chose.

---

## Required reading (in order, before touching code)

1. [`AGENTS.md`](../../AGENTS.md) — the binding contract.
2. [`MESH_SUBSTRATE.md`](../MESH_SUBSTRATE.md) — substrate doctrine.
3. [`MESH_IMPLEMENTATION.md`](../MESH_IMPLEMENTATION.md) — runtime spec.
4. [`MESH_MIGRATION_PLAN.md`](../MESH_MIGRATION_PLAN.md) — **especially §"Step S2.5"** (your spec) and §"Forbidden patterns during the migration" point 3.
5. [`BUILD_DOCTRINE.md`](../BUILD_DOCTRINE.md) — function-first phase rules.
6. [`PHX-1030`](../../phoenix-backlog/PHX-1030.yaml) — your lifecycle ticket.
7. The two predecessor S2 PRs on `main` so you understand the existing `Kadmos v2` ingestion shape you are integrating beside (not into):
   - `src/theogony/mesh/ingestion/kadmos_v2.py`
   - `src/theogony/mesh/ingestion/linker.py`
   - `src/theogony/mesh/ingestion/vectorizer.py`
   - `src/theogony/mesh/storage/{nodes,edges,audit}.py`
   - `src/theogony/mesh/runtime/oneiros_tick.py`

---

## What this etappe is, in one sentence

Bulk-seed the substrate with **~4.81M Q-ID-anchored Tier-1 nodes + ~21.35M relational edges** from the Wikidata5m KEPLER dataset, embedding Wikipedia first-paragraphs **off-substrate** so the source body never enters the mesh — and do it through a **smoke-test-first** iterative loop, not a single big-bang run.

---

## Operator-locked decisions (read first)

These four are not yours to relitigate. They are operator decisions; flag and escalate to Chaos only if they prove physically impossible.

### 1. Smoke-test first, scale later

Do **not** try a 4.81M-entity run on the first PR. The plan is:

1. **Smoke-1** — `--max-entities 1000 --max-triplets 5000`. Verify the pipeline end-to-end: streaming, embedding, idempotency, audit, no raw text in DB, eager-linking handoff to S2 Kadmos v2.
2. **Smoke-2** — `--max-entities 10000 --max-triplets 50000`. Verify scaling holds (memory, throughput, no surprises).
3. **Smoke-3..N** — operator-driven. May expand to 100k / 500k / full corpus depending on what Smoke-1/2 reveal.

Each smoke run is its own commit / PR-review cycle. The first PR delivers the loader + importer + Smoke-1 results.

### 2. Embedding model is not yet locked

The doctrine default per [`MESH_SUBSTRATE.md`](../MESH_SUBSTRATE.md) §"Node anatomy" is BGE-M3 class (1024-d). For S2.5 the operator wants to **evaluate which model is best fit during the smoke loop**. Make the embedder pluggable: a thin protocol `MeshEmbedder` with a `BGEM3Embedder` and a `BGESmallEnEmbedder` implementation (the latter already shipped via `LocalSentenceTransformerEmbedder`-style code in the codebase). Add a `--embedder` CLI flag (`bge-m3` | `bge-small-en` | extensible). Default for Smoke-1: `bge-m3` if it loads cleanly on the operator's M4-Pro within 2 GB VRAM/RAM; fall back to `bge-small-en` otherwise.

Do **not** hard-wire OpenAI / Anthropic embedding APIs into the seed path — wikidata5m is local data, the import pass should be local-compute-only by default.

### 3. (a) — Keep the `wikidata5m_text.txt` paragraphs on disk, do not delete

After embedding, the four `data/raw/wikidata5m/*.txt` files **stay on disk** in their gitignored location. They are off-substrate inputs for later refresh runs. Do not delete them, do not move them, do not parse-cache-and-delete. They are the operator's property; the seed importer is a *consumer* of those files, not a *manager* of them.

### 4. PHX-1001 update is already done; no further meta-ticket touching

#159 refreshed PHX-1001 to reflect S2 merged + S2.5 in flight. Do not touch PHX-1001 in your S2.5 implementation PR. If the lifecycle changes during your work (e.g. Smoke-1 reveals a blocker), you update **PHX-1030**, not PHX-1001.

---

## Goal

Implement the deliverables in [`MESH_MIGRATION_PLAN.md`](../MESH_MIGRATION_PLAN.md) §"Step S2.5" so that, on a freshly initialised mesh:

```bash
theogony mesh seed wikidata5m --max-entities 1000 --max-triplets 5000
theogony mesh status
theogony mesh ingest --text-file <fixture-with-seeded-qid> --title "smoke handoff"
```

Produces:

1. A substrate with ~1000 Q-ID-anchored Tier-1 nodes (one per seeded entity) and up to 5000 typed `Edge`s between them.
2. A clean audit ledger: one entry per node insertion, one per edge insertion, one for the run-level summary.
3. A `MeshSeedRunReport` written to disk under the existing `run_reports/` directory shape.
4. **Zero paragraph bodies in the `description` column** — verified by a dedicated invariant test, not just spot-check.
5. Q-ID uniqueness invariant holds (no two Tier-1 nodes share a Q-ID).
6. The subsequent Kadmos v2 ingest of a paragraph that mentions a seeded Q-ID produces an `IngestRunReport.resolution.tier_counts` showing a **signal-1 (Q-ID match)** link to the existing seeded node — no candidate created.

Definition of Done is the spec in `MESH_MIGRATION_PLAN.md` §"Step S2.5" — read it verbatim, do not paraphrase.

---

## Scope cap (binding)

The scope cap from `MESH_MIGRATION_PLAN.md` §"Step S2.5" applies. Repeated here for emphasis:

- **No retrieval** beyond `theogony mesh status`. (S3.)
- **No description regeneration / re-embedding.** A future PHX ticket handles refresh; not yours.
- **No coupling to Kadmos v2 internals** beyond using the same `MeshTextVectorizer` (or a leaner local equivalent) for embedding consistency.
- **No Cockpit / MCP integration.** (S4.)
- **No consolidation, splits, pathology, therapy.** (S5.)
- **No deletion of the legacy path.** (S6.)
- **No raw text storage anywhere in the mesh.** Wikipedia first-paragraphs are read off-substrate, embedded, **discarded from the import path**. `description` on each seeded `ConsolidatedNode` is `None` or the entity name only (≤ 100 chars). Asserted by `tests/mesh/seeds/test_wikidata5m_no_raw_text.py`.

If you feel pulled toward any of those, **stop and escalate** — do not silently expand scope (Forbidden Pattern 5 of the migration plan).

---

## File layout (suggested; you may refine)

```
src/theogony/mesh/seeds/
    __init__.py
    wikidata5m/
        __init__.py
        loader.py        # streaming readers for the 4 .txt files
        relations.py     # P-ID → (relation_kind, relation_descriptor) registry
        embedder.py      # MeshEmbedder protocol + 2 implementations + factory
        importer.py      # orchestrator: stream → embed → upsert → audit → report

src/theogony/reporting/
    models.py            # extend with MeshSeedRunReport (Pydantic v2, extra="forbid")

src/theogony/mesh/cli.py # extend with `mesh seed wikidata5m` subcommand

tests/mesh/seeds/
    __init__.py
    test_wikidata5m_loader.py
    test_wikidata5m_relations.py
    test_wikidata5m_importer.py
    test_wikidata5m_no_raw_text.py     # the invariant
    test_wikidata5m_idempotent.py
    test_wikidata5m_eager_linking_handoff.py
    fixtures/
        entities_50.txt
        text_50.txt
        relations_5.txt
        triplets_10.txt
```

The fixtures should be hand-curated subsets of the real files (sample real Q-IDs and P-IDs, do not synthesise fake ones — the eager-linking handoff test needs realistic identifiers).

---

## Implementation guidance (concrete, but not a code dictation)

### Loader

Stream the four files line by line. **Do not** load the full 21M-triplet file into memory; iterate. Yield typed records:

```python
@dataclass(frozen=True)
class EntityRecord:
    qid: str            # "Q336997"
    aliases: list[str]  # rest of tab-separated row

@dataclass(frozen=True)
class TextRecord:
    qid: str
    description_text: str  # the Wikipedia first-paragraph, used as embedding INPUT only

@dataclass(frozen=True)
class RelationRecord:
    pid: str            # "P39"
    aliases: list[str]

@dataclass(frozen=True)
class TripletRecord:
    subject_qid: str
    predicate_pid: str
    object_qid: str
```

Malformed lines are logged with line number + reason; they do **not** raise. They increment a `loader_malformed_lines` counter in the run report.

### Relations registry

The 825 P-IDs deserve a small hand-curated mapping for the most common ones (`P31` instance-of, `P279` subclass-of, `P106` occupation, `P17` country, `P19` place-of-birth, `P39` position-held, `P54` member-of-sports-team, `P161` cast-member, etc.). Map each to:

- `relation_kind` (one of the existing kinds used by Kadmos v2: `semantic`, `hierarchy`, `causal`, `temporal`, `attribute`, `co_occurrence`, `attribution`, `extraction` — extend if necessary, but only with operator escalation)
- `relation_descriptor` (one short string, the canonical descriptor)

For the long tail of unmapped P-IDs, fall through with `relation_kind = "semantic"`, `relation_descriptor = first_alias_normalised` (lower-cased, underscores), and append the P-ID itself to the edge's `pids` list. Track unmapped P-ID counts in the seed report so the registry can be expanded later.

The hand-curated mapping is a Python dict in `relations.py`; aim for ~30–50 most-common P-IDs. Do not try to map all 825 in this PR.

### Embedder

Define a thin protocol:

```python
class MeshEmbedder(Protocol):
    model_id: str
    dim: int
    async def embed_many(self, texts: list[str], *, batch_size: int = 64) -> list[list[float]]: ...
```

Provide two implementations:

- `BGEM3Embedder` — wraps `BAAI/bge-m3` via `sentence_transformers` with MPS / CPU device autodetect.
- `BGESmallEnEmbedder` — wraps `BAAI/bge-small-en-v1.5`, same shape.

A `build_embedder(name: str) -> MeshEmbedder` factory keyed by the `--embedder` CLI flag.

The embedder is called twice per entity: once to produce `semantic_vector` (input: Wikipedia first-paragraph), once to produce `description_vector` (also input: Wikipedia first-paragraph — same input is fine for now; if you find a meaningful reason to use different inputs, escalate). Both vectors land on the `ConsolidatedNode`. The first-paragraph **string** is then dropped on the floor — no field on the node carries it.

### Importer

Orchestrate three passes:

1. **Pass 1 — entity upsert.** Stream entities + their texts (joined by Q-ID). For each entity: check if a Tier-1 node with that Q-ID already exists (via the existing `EagerLinker` or a direct `MeshNodeStore` lookup). If yes, increment `entities_skipped_duplicate_qid` and continue (idempotent). If no, embed, build `ConsolidatedNode` with `qids=[QIDTag(qid, confidence=1.0, attached_at=now)]`, `tags=aliases[:50]` (cap to keep tags manageable), `description=None` (or `entity_name` if you can extract one cheaply from the first alias — but ≤ 100 chars), `is_candidate=False`, `consolidation_tier=1`. Append to store, write audit entry, increment `entities_upserted`.
2. **Pass 2 — edge upsert.** Stream triplets. For each triplet: look up source and target Tier-1 nodes by Q-ID; if either is missing (because it was outside the `--max-entities` slice), increment `edges_skipped_missing_endpoint` and continue. Otherwise build the edge using the relations registry, append, audit, increment `edges_upserted`.
3. **Pass 3 — finalise.** Write the `MeshSeedRunReport` to the run-reports directory; emit a final audit entry with the run summary.

Memory discipline: do **not** materialise the 21M-triplet stream as a list. Iterate. The CSR rebuild from delta-buffer happens on the next Oneiros tick, naturally — your importer pushes edges into the delta-buffer via `EdgeStore.append_edge` (the existing path). If buffer-flush thresholds need tuning for the bulk path, escalate; otherwise trust the existing Oneiros tick.

### `MeshSeedRunReport`

Pydantic v2 (`extra="forbid"`). Fields per the YAML spec in PHX-1030. Use existing `RunReportWriter` (the same one Kadmos v2 uses) — do not invent a new writer. The report is emitted under the existing `run_reports/` shape; consumers (Argus, the operator, future Mnemosyne) read it as just another structured run report.

### CLI

Add `theogony mesh seed wikidata5m` under the existing `mesh` Typer app. Flags per the migration plan §S2.5 deliverables. The command is async at the top (`asyncio.run(...)`) like `mesh ingest` already is.

---

## Tests (the six the migration plan calls out — non-negotiable)

The six tests are listed in `MESH_MIGRATION_PLAN.md` §"Step S2.5" deliverables. Three of them are critical:

1. **`test_wikidata5m_no_raw_text.py`** — the invariant. After Smoke-1, walk every `ConsolidatedNode` produced by the seed run via `MeshNodeStore.load_all_consolidated()` and assert `node.description is None or len(node.description) <= 100`. This is the hard contract.

2. **`test_wikidata5m_idempotent.py`** — second run on the same fixture is a no-op. `entities_upserted == 0` on the second run, `entities_skipped_duplicate_qid == fixture_size`. Edge idempotency: the importer either deduplicates by `(source_id, target_id, relation_descriptor)` or relies on the substrate's existing edge-saturation discipline — your call, but document it.

3. **`test_wikidata5m_eager_linking_handoff.py`** — the integration check. After Smoke-1, run `theogony mesh ingest --text-file fixture_paragraph_mentioning_Q336997.txt`. Assert that the resulting `IngestRunReport.resolution.tier_counts` includes a count for tier 4 (Q-ID match per the `_SIGNAL_TO_TIER` mapping in `kadmos_v2.py`). If the count is 0, the handoff is broken — that's the whole point of S2.5 and the invariant must hold.

The other three (`loader`, `relations`, `importer`) follow normal pytest discipline.

---

## Verification before each PR push

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy src/theogony/mesh
mypy src/theogony/reporting          # MeshSeedRunReport must type-check
pytest -q tests/mesh                 # both S2 and S2.5 tests
pytest -q                            # full suite — no regression
```

The format-check is the one that bit Chaos last time (#155); run both `ruff format` (rewrite) and `ruff format --check` (verify) before pushing.

After Smoke-1 passes locally, manually verify the handoff:

```bash
theogony mesh seed wikidata5m --max-entities 1000 --max-triplets 5000
theogony mesh status                 # check counts
theogony mesh ingest --text-file <fixture> --title "handoff smoke"
# inspect the IngestRunReport: resolution.tier_counts must show signal 4 hits
```

Document the actual numbers in the PR body (entity count, edge count, embedding duration, signal-4 hits in the handoff).

---

## Out of scope for this brief (but on the radar)

- **Wikidata freshening pass.** Re-pull current Wikipedia first-paragraphs via Q-ID after S2.5 lands. Future PHX ticket; not yours.
- **Refresh of P-ID registry coverage** beyond ~30–50 hand-mapped most-common predicates. Future PHX ticket; not yours.
- **Embedding-model evaluation report.** After Smoke-1/2/3 the operator and Chaos will write up which embedder gave best identity-matching quality at what cost. Not part of the implementation PRs themselves; that is the post-implementation evaluation step.
- **Dataset freshness upgrade** from wikidata5m (2019/2020) to a fresh Wikidata Truthy Dump-derived equivalent. Future PHX ticket; not yours.

If you discover any of these are actually blockers (rather than later improvements), **escalate to Chaos** — do not improvise around them.

---

## Escalation

Escalate to Chaos (and let Chaos decide whether Daedalus needs to be looped in) if any of these happen:

1. The architecture in `MESH_MIGRATION_PLAN.md` §S2.5 turns out underdetermined for a real implementation choice (e.g. how to deduplicate edges at insertion time vs. relying on saturation; how the seed importer should interact with the Oneiros tick during a multi-million-edge bulk insert).
2. `BAAI/bge-m3` will not fit / will not run on the operator's hardware and `bge-small-en` is not a sufficient fallback.
3. The wikidata5m file format in `data/raw/wikidata5m/` deviates from what the brief describes (e.g. encoding quirks, malformed-row rate above 1%).
4. The eager-linking handoff test fails — i.e. Kadmos v2 does not pick up the seeded Q-IDs as signal-1 matches. That would mean either S2's `EagerLinker` has a bug or the seed importer is writing Q-IDs in the wrong shape. Either is a hard escalation.
5. The Smoke-1 `MeshSeedRunReport` shows >5% unmapped P-IDs in the seed (suggesting the hand-mapped registry is too narrow) **and** that meaningfully changes downstream eager linking. Otherwise just expand the registry in a small follow-up.
6. Any pull toward storing raw text — even "just the first sentence". The invariant is hard.

Otherwise: proceed, push, open one PR per smoke iteration, and tag Chaos when CI is green.

---

## One-line summary

> **Stream wikidata5m → embed off-substrate → upsert ~1000 Q-ID-anchored Tier-1 nodes + edges → verify the handoff to S2's eager linker → escalate the smoke results before scaling.**
