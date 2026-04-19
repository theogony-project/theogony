# Characterization run reports

Persisted `IngestRunReport` JSON files from
`tests/test_pipeline_characterization.py` (Plan §3.8 layer 6).

These are **documentation of the project state**, not runtime data
(production reports live under `{settings.data_dir}/run_reports/`,
which is gitignored). The test writes one file per run; consecutive
runs accumulate here and serve as a longitudinal record of pipeline
behaviour against the same Hedin Trans-Himalaya Vol. I narrative
slice (sentences 260..560).

## Reading a report

Each report is the standard `IngestRunReport` schema (see
`src/theogony/reporting/models.py`) with one extra top-level key
`characterization_meta` that records the slice indices, wall-clock,
LLM call count, total cost, and the calibration values the test
ran against.

```bash
jq '.characterization_meta' <ulid>.json
jq '.resolution.tier_counts, .relations.parsed_ok' <ulid>.json
```

## When to add bands / tighten

When the pipeline composition changes meaningfully (new stage,
default-model swap), do an explorative run, inspect the new metrics
in this directory, update `CAL_*` constants in the test, and
document the change in the PR body. Bands are ±20% around the
calibration per Daedalus's E7 spec.

## What this is NOT

Not the PHX-0034 entity-resolution quality benchmark. That is
Gen-2 work (gold-standard precision/recall, cross-provider,
multi-slice). This layer measures **drift**, not **correctness**.
