# F1 — Vitality Math Consolidation

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-21  
**Branch:** new branch off `main`, e.g. `chore/f1-vitality-consolidation`  
**Scope:** one PR, tightly scoped  
**Predecessor:** PHX-0009 has been catalogue-only since Gen 1; this etappe is its first real cleanup. No structural change in behaviour — just a single-source-of-truth refactoring that unblocks PHX-0057, PHX-0058, PHX-0059, PHX-0060.

This is the **first sprint of the architecture-audit Phase 0**. F2 (TickPhase pipeline) and F3 (RetrievalStrategy protocol) follow as separate briefs. Land F1 first; F1's pattern sets the discipline F2/F3 will follow.

Direct brief, no Daedalus. This is a refactoring etappe, not an architectural decision round.

---

## Why this etappe exists

The vitality math currently lives in two homes:

1. **`src/theogony/core/vitality.py`** — the original Gen-1 helpers (`compute_freshness`, `dynamic_vitality_threshold`, `promotion_ready`, `connectivity_score`). These use **logarithmic / exponential** formulas. They are well-tested in `tests/test_vitality.py` and consumed by `KnowledgeNode.can_be_promoted` and a few other places.

2. **`src/theogony/memory/oneiros.py:_tick`** — the OneirosWorker computes its own freshness and connectivity inline, using **linear formulas** (linear-cap-at-N for connectivity, linear-decay-over-N-days for freshness). The plan §5 E8.5 brief deliberately picked these shapes for the worker because they are clearer for lifecycle math; the existing helpers stay test-locked at their log/exp shape.

The two homes are not in conflict semantically — they are intentionally different formulas serving different purposes. But they are physically scattered, so:

- New tickets that want to consult or modify vitality math (PHX-0057, PHX-0058, PHX-0059, PHX-0060) cannot find a single canonical home.
- A future tuning round (PHX-0009 itself) would have to touch two files in lockstep without missing one.
- The "vitality" concept is conceptually one thing in the doctrine; having it scattered violates the architecture-clarity goal.

**This PR puts both homes under one roof: `src/theogony/core/vitality.py`.** It does not change behaviour. It is a refactoring of code location, not formula.

---

## Goal

After this PR:

- `src/theogony/core/vitality.py` is the single canonical home for all vitality-related math (both log/exp and linear formulas).
- The OneirosWorker imports its formulas from `core/vitality.py` instead of computing them inline.
- The existing test suite stays green byte-for-byte (no behaviour change).
- New tests in `tests/test_vitality.py` cover the moved linear formulas with the same assertion shape as the existing log/exp formulas.
- A new short docstring at the top of `core/vitality.py` explains the two formula families and which is used where.

---

## Scope decisions (read first)

### 1. Move the OneirosWorker's inline math into `core/vitality.py` as new functions

Two new pure functions in `core/vitality.py`:

- `compute_freshness_linear(last_accessed: datetime | None, horizon_days: float, *, now: datetime | None = None) -> float`  
  Linear decay over `horizon_days`. Returns `1.0` at zero idle, `0.0` at >= `horizon_days` idle. Replaces the inline `idle_days = ...; new_fresh = max(0.0, 1.0 - idle_days / cfg.freshness_horizon_days)` in OneirosWorker.

- `compute_connectivity_linear(degree: int, full_credit_edges: int) -> float`  
  Linear cap. Returns `min(1.0, degree / full_credit_edges)`. Replaces the inline `new_conn = min(1.0, degree / cfg.connectivity_full_credit_edges)` in OneirosWorker.

Both are **side-effect-free, pure functions of their inputs**. They take their parameters explicitly (no Settings dependency) so they can be tested in isolation and reused from anywhere.

### 2. Keep the existing log/exp helpers intact

`compute_freshness` (the log/exp version with `half_life_days`), `dynamic_vitality_threshold`, `promotion_ready`, and `connectivity_score` (the log version) **stay exactly as they are**. Their tests stay locked. Their callers (`KnowledgeNode.can_be_promoted`) stay unchanged.

The two formula families coexist deliberately:
- **Log/exp** for situations where the natural scale is multiplicative (freshness as exponential decay matches information-theoretic intuition; connectivity as `log1p` rewards the early edges most).
- **Linear** for the OneirosWorker's per-tick lifecycle math, where the operator wants predictable, easy-to-tune behaviour and the formula must be auditable in seconds.

### 3. Add a module docstring at the top of `core/vitality.py`

The new docstring must explain:

- The two formula families.
- Which is used where (log/exp for `KnowledgeNode.can_be_promoted` and the dynamic threshold; linear for `OneirosWorker._tick`).
- That PHX-0009 may eventually unify or further tune these — and that the unification, when it happens, lands here.

### 4. Update the OneirosWorker import + replace the two inline computations

In `src/theogony/memory/oneiros.py:_tick`:

Before:
```python
idle_days = (started - _aware(node.last_accessed)).total_seconds() / 86400.0
new_fresh = max(0.0, 1.0 - idle_days / cfg.freshness_horizon_days)
# ...
new_conn = min(1.0, degree / cfg.connectivity_full_credit_edges)
```

After:
```python
new_fresh = compute_freshness_linear(
    node.last_accessed,
    horizon_days=cfg.freshness_horizon_days,
    now=started,
)
new_conn = compute_connectivity_linear(
    degree=degree,
    full_credit_edges=cfg.connectivity_full_credit_edges,
)
```

The `_aware` helper in `oneiros.py` stays (it normalises naive datetimes); `compute_freshness_linear` should take its `now` parameter as **already aware UTC** and not call `_aware` itself (caller's responsibility — keeps the function signature pure).

### 5. New tests in `tests/test_vitality.py`

Add at minimum:

- `test_compute_freshness_linear_at_zero_idle_returns_one`
- `test_compute_freshness_linear_at_horizon_returns_zero`
- `test_compute_freshness_linear_above_horizon_clamps_to_zero`
- `test_compute_freshness_linear_handles_naive_datetime_when_now_provided`
- `test_compute_freshness_linear_handles_none_last_accessed_returns_one`  
  (Edge case: a node that has never been accessed should be treated as fresh-on-arrival.)
- `test_compute_connectivity_linear_at_zero_degree_returns_zero`
- `test_compute_connectivity_linear_at_full_credit_returns_one`
- `test_compute_connectivity_linear_above_full_credit_clamps_to_one`
- `test_compute_connectivity_linear_zero_full_credit_handled_gracefully`  
  (Edge case: avoid division-by-zero. Decision: when `full_credit_edges == 0`, return `1.0` if `degree > 0`, else `0.0`.)

The OneirosWorker tests in `tests/test_oneiros.py` should stay green without changes — that is the regression contract.

### 6. No behaviour change

The OneirosWorker's `_tick` must produce **byte-identical scores** before and after this PR for any given input. The contract is: `new_fresh` and `new_conn` are computed with the same arithmetic, just from a different physical location. Run the existing `tests/test_oneiros.py` suite as your regression gate.

---

## Implementation plan (file-by-file)

### `src/theogony/core/vitality.py`

1. Add module docstring explaining the two formula families.
2. Add `compute_freshness_linear` and `compute_connectivity_linear` as new public functions.
3. Existing `compute_freshness`, `dynamic_vitality_threshold`, `promotion_ready`, `connectivity_score` stay unchanged.

### `src/theogony/memory/oneiros.py`

1. Add imports: `from theogony.core.vitality import compute_freshness_linear, compute_connectivity_linear`.
2. In `_tick`, replace the two inline computations with calls to the new helpers (see "Scope decision 4" for the exact diff shape).
3. The `_aware` helper stays. Pass `now=_aware(started)` (or just `started` if it is already aware) to `compute_freshness_linear`.
4. **Do not** remove the inline-math comment block (Plan §5 E8.5 references it as the formula spec) — replace it with a one-line comment pointing at the two functions in `core/vitality.py`.

### `tests/test_vitality.py`

1. Add the new tests listed in "Scope decision 5".
2. Existing tests untouched.

### `tests/test_oneiros.py`

1. Should stay green without modification. If any test fails, it indicates an arithmetic drift — investigate before claiming the regression contract holds.

### Documentation touches

1. PHX-0009 catalogue entry in `docs/PHOENIX_BACKLOG.md` gets a one-line update at the end: `"Phase 1 of PHX-0009 closed by F1 (this PR): math consolidated under core/vitality.py. Future tuning rounds touch one file."`
2. No other docs need updating; the architecture is unchanged.

---

## Cost-benefit considerations

This PR has very low cost surface and clear benefit. Specifically:

- **Token cost**: small. Composer should consume well under €0.20 of tokens to execute. The brief is tight; the changes are mechanical.
- **Runtime cost**: zero. Same arithmetic, same number of operations, same memory profile.
- **Test cost**: marginal. ~10 new tiny tests; total wall-clock added to the suite is < 0.1 s.
- **Review cost**: low. The diff is small (estimate < 100 lines) and 70% of it is the new tests.

The only failure mode worth watching: **arithmetic drift**. If the new helpers compute a slightly different number than the inline code (e.g. floating-point ordering in the division), `test_oneiros.py` will fail. Trust those tests as the contract.

---

## Out of scope (do not do)

- **Do not** unify the log/exp and linear formulas. PHX-0009 (Vitality Function Tuning) may eventually justify that, with empirical data; this PR does not.
- **Do not** change Settings names. `freshness_horizon_days`, `connectivity_full_credit_edges` stay as they are.
- **Do not** add new lifecycle behaviour. No new promote/degrade paths, no new score components, nothing the OneirosWorker is not already doing today.
- **Do not** add backward-compatibility shims. The inline computations are gone in one move; there is no graceful degradation needed because the formulas are equivalent.
- **Do not** touch `KnowledgeNode.can_be_promoted` or `NodeScores.vitality`. Those are higher-level aggregations, not per-component math, and they live in `core/model.py` for good reason.
- **Do not** add a typer command, an API endpoint, a CLI flag, an MCP tool, or any other new surface. This is purely an internal refactoring.

---

## Done when

- [ ] `compute_freshness_linear` and `compute_connectivity_linear` exist in `core/vitality.py` with full type annotations and docstrings.
- [ ] `OneirosWorker._tick` no longer contains inline freshness or connectivity math; both come from `core/vitality.py` imports.
- [ ] `tests/test_vitality.py` covers all nine new tests listed in "Scope decision 5"; all green.
- [ ] `tests/test_oneiros.py` stays green without modification.
- [ ] Full test suite (`pytest -q`) is green.
- [ ] `ruff check` clean. `ruff format --check` clean.
- [ ] `mypy src/theogony/core/vitality.py src/theogony/memory/oneiros.py` clean (strict).
- [ ] PHX-0009 catalogue entry updated with the closing line.
- [ ] PR body lists which Plan section / PHX ticket the work covers (PHX-0009 Phase 1) and which architecture-audit phase (Phase 0 sprint F1). PR title: `chore(vitality): F1 — consolidate vitality math under core/vitality.py`.

---

## After this PR

F1 is the smallest piece of the Phase 0 foundation. When merged, the next briefs:

- **F2**: TickPhase pipeline refactoring in OneirosWorker (separate brief, separate PR).
- **F3**: RetrievalStrategy Protocol skeleton (separate brief, separate PR — this is PHX-0056 Phase 1).

Together F1 + F2 + F3 form the architecture foundation that PHX-0057 / 0058 / 0059 / 0060 build on top of. Land them in order.
