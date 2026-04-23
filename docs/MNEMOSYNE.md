# Mnemosyne (PHX-0071)

Mnemosyne is the **meta-cognitive** layer: she classifies whether a user
question is *about the Chronik itself* (schema, retrieval, workers,
embeddings, backlog) versus ordinary world knowledge.

## Phase 1 (W5) scope

1. **Per-query classification** — after each `pantheon_ask`, a
   `MetaClassification` is attached to the `QueryRunReport`.
2. **Persisted audit signal** — when the verdict is `self_referential`,
   cited nodes receive `properties["self_referential_in_runs"] += [run_id]`
   (append-only, idempotent per run).
3. **Aggregation** — optional Oneiros tick phase `mnemosyne_aggregation`
   (default **off**) clusters recent self-referential observations via
   HDBSCAN on `region_descriptor.query_embedding` and writes
   `MnemosyneObservationCluster` reports under `run_reports/mnemosyne/`.

Phase 2 (out of scope for W5) will add a BacklogProposal drafter and
Hestia review hook.

## Heuristic classifier

Deterministic keyword scoring on lowercased text. Single-word keywords
match as **whole tokens** (alphanumeric tokens from the query) to avoid
mid-word false positives (e.g. `graph` inside `paragraph`). Multi-word
markers and prefixes ending with `-` (e.g. `phx-`) use substring match.

Verdict ladder:

- `self_referential` — any high-keyword hit in query or cited node label,
  **or** ≥ 2 mid-keyword hits across query + answer.
- `uncertain` — exactly one mid-keyword hit and query length ≥ 50 chars.
- `not_self_referential` — otherwise.

When `Settings.mnemosyne.classifier_mode == "heuristic_with_llm_fallback"`
and an LLM is configured, `uncertain` escalates to a small JSON-line LLM
call (see `agents/prompts/mnemosyne_classifier.md`). Rate limits:
`max_llm_classifications_per_hour` and `llm_classification_max_cost_eur`.
When budget is exhausted, uncertain resolves to `not_self_referential`
with `llm_fallback_skipped=True`.

## Operator surfaces

- `theogony mnemosyne classify "<question>"` — heuristic-only diagnostic
  (no constellation / answer).
- `theogony reports list --type mnemosyne` / `reports show <id>`.
- MCP `pantheon_reports_list` / `pantheon_reports_show` accept
  `report_type=mnemosyne`.

## Read-only contract

Mnemosyne may only append `self_referential_in_runs` and write run
reports. No other node mutation, no edge mutation, no writes under
`phoenix-backlog/` or `prompts/`.
