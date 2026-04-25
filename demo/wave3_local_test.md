# Wave 3 local test (operator runbook)

Repeatable steps to exercise the immune loop and Mnemosyne conductor after Living Demo Wave 3 work (W13–W17). Run on a clean checkout when you want an honest end-to-end sanity check.

## 1. Prereqs

- Local repo on `main` (or your sprint branch rebased on current `main`).
- Python virtualenv at `.venv` with the project installed (`pip install -e ".[dev]"` or your usual set).
- Local Neo4j running for the default graph-backed path (`STORE` defaults to `neo4j`; the Cockpit standalone chronicle defaults to Neo4j as well — see `THEOGONY_COCKPIT__KNOWLEDGE_STORE`).
- `ANTHROPIC_API_KEY` (or your configured provider key) is required only for the research planner and live LLM paths. The Mnemosyne conductor can run with `--metric-mode fixture` without calling a hosted model.

## 2. Reset

```bash
THEOGONY_ALLOW_DEMO_RESET=1 bash demo/reset_living_growth.sh
```

## 3. Run cockpit

```bash
bash demo/start_wave3_cockpit.sh
```

Without these flags, `Research this further` may legitimately emit no trigger (`trigger_id=null`).

If you prefer explicit flags instead of the helper script:

```bash
THEOGONY_CURIOSITY__GROWTH_BRIDGE__ENABLED=true \
THEOGONY_CURIOSITY__ARGUS__ENABLED=true \
THEOGONY_CURIOSITY__RESEARCH_PLANNER__ENABLED=true \
THEOGONY_CURIOSITY__EVALUATOR__ENABLED=true \
THEOGONY_CURIOSITY__ATHENE__ENABLED=true \
THEOGONY_CURIOSITY__CHRONOS__ENABLED=true \
THEOGONY_CURIOSITY__NEMESIS__ENABLED=true \
THEOGONY_CURIOSITY__ERIS__ENABLED=true \
THEOGONY_MNEMOSYNE__CONDUCTOR_ENABLED=true \
venv/bin/theogony cockpit serve --host 127.0.0.1 --port 8000
```

## 4. Ask and research

1. Open: `http://127.0.0.1:8000/cockpit/explorer?growth=on`
2. Ask: `Wer war Sven Hedin und was hat er in Tibet erforscht?`
3. In the research panel you should see phases such as `planning_started`, `executing_step`, `acquired_into_pool`, `ingested`, and `research_complete` (exact ordering may vary with timing).

## 5. Run immune workers

After research has produced pool entries and ingested material:

```bash
bash demo/run_wave3_workers.sh
```

The script defaults to `STORE=neo4j` (persisted chronicle). Use `STORE=memory` for a quick offline run without Bolt.

In the Explorer (operator drawer), **Run immune + Mnemosyne tick** calls `POST /cockpit/operator/worker-tick` on the same store as the running Cockpit process (disable with `THEOGONY_COCKPIT__OPERATOR_WORKER_FROM_UI=false`).

## 6. Inspect reports

```bash
.venv/bin/theogony reports list --type chronos
.venv/bin/theogony reports list --type nemesis
.venv/bin/theogony reports list --type eris
.venv/bin/theogony reports list --type mnemosyne_conductor
```

## 7. Success criteria

- The verification pool shows at least one entry after a successful research run.
- Athene writes at least one Finding when eligible pool rows exist.
- Chronos clears at least one sampled pool entry **or** its report states why nothing was cleared.
- Nemesis writes a run report (findings count may be zero).
- Eris in fixture mode writes a campaign report.
- Mnemosyne conductor writes a `mnemosyne_conductor` report and, in fixture mode, includes at least one metric definition.
- Under `data/run_reports/` (or your configured `run_reports_dir`), the `backlog_proposals/` directory exists; it may be empty if no backlog draft rules fired.

## 8. What this does not prove

- Factual truth of answers or ingested claims.
- Live adversarial robustness beyond the Eris fixture harness.
- Self-modifying code, automated settings apply, or production scheduling.
- That every environment will have the same LLM cost or latency.
