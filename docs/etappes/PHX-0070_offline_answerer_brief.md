# PHX-0070 — OfflineAnswerSynthesizer (the no-LLM-on-hosted fix)

**From:** Hesiod  
**To:** Talos  
**Date:** 2026-04-22  
**Branch:** new branch off `main`, e.g. `fix/phx-0070-offline-answerer`  
**Scope:** one PR, tightly bounded  
**Predecessor:** Wave 1 closed (W4 PR #63 merged). PHX-0070 is the first post-Wave-1 bug fix and unblocks credible `pantheon_ask` demos on hosted instances without an LLM key.

Direct brief, no Daedalus. Six knobs are pre-locked. Estimated work: ≤ 1 hour Composer.

---

## Why this etappe exists

Reproducer (verified 2026-04-22 against `https://theogony-mcp.fly.dev/sse`):

```
client → pantheon_ask({"q": "What is the Pantheon?", "k": 6})
response:
  verdict:           "failed"
  verdict_reasoning: "synthesis raised before completion"
  cited_node_ids:    []
  constellation:     {nodes: 6, edges: 4}   ← retrieval is fine
  answer:            ""                      ← synth empty
```

Root cause traced (full reading of `agents/factory.py` + `agents/llm.py` + `retrieval/synthesize.py` + `retrieval/pipeline.py`):

1. `build_llm_from_settings` with `provider="stub"` constructs `StubLLMProvider(responses={}, default="")`.
2. `AnswerSynthesizer.synthesize()` calls `LLM.complete(prompt, ...)`.
3. `StubLLMProvider._match(prompt)` finds no matching prefix and returns `self._default == ""`.
4. `LLMResult(text="")` propagates back; **no exception was raised**.
5. The synthesizer's exception handler does nothing; the empty text flows through to `Answer(text="", cited_node_ids=[])`.
6. `QueryPipeline._finalize_report` computes `status = "completed" if answer.text else "partial"` → `"partial"` and `raised = not bool(answer.text)` → `True`.
7. `query_verdict(raised=True, ...)` returns `("failed", "synthesis raised before completion")`.

The verdict-reasoning string is **technically inaccurate** ("raised" implies an exception that didn't occur) and the user-visible behaviour is "Pantheon doesn't work" on every stub-LLM hosted instance — the exact opposite of PHX-0066's friction-free-demo promise.

The PHX-0070 YAML lists two acceptable resolutions:

> a) `StubLLMProvider` either successfully synthesises a deterministic structured answer from any valid `Constellation`, including W1/W2/W3-extended ones, or
> b) is replaced on the hosted path with a small `CitationOnlyAnswerer` that returns "No LLM is available on this hosted instance; here are the cited sources" + the cited node ids derived from the constellation's top-N nodes. Either is acceptable; **the second is more honest.**

This brief implements (b) — the honest path. The `StubLLMProvider` stays as the test-fixture mechanism it was designed for; a new `OfflineAnswerSynthesizer` becomes the production answer for "no LLM key configured".

---

## Pre-locked design knobs

### Knob 1 — Approach: new `OfflineAnswerSynthesizer` class (option b from the YAML)

The clean separation:

- `AnswerSynthesizer` — LLM-driven, calls `LLMProvider.complete`, parses `[AKA-…]` citations from prose. Unchanged.
- `OfflineAnswerSynthesizer` — deterministic, takes a `Constellation` directly, generates a structured citation-only answer. **No LLM dependency at all.**

Both implement the same `synthesize(constellation, *, …) -> Answer` signature. Either can be passed to `QueryPipeline(synthesizer=…)`.

Reasons not to harden `StubLLMProvider` itself:

- `StubLLMProvider` is generic — it serves `RelationExtractor`, `EntityResolver`, and `AnswerSynthesizer` from a single fixture-keyed-prompt-prefix machinery. Coupling it to the answer-synthesis prompt would break that.
- Tests use scripted responses; production uses no responses. Two modes, two consumers — pick the right tool for each.

### Knob 2 — Routing: factory wires offline when `provider == "stub"`

`agents/factory.py` already returns `StubLLMProvider` for `provider="stub"`. Add a parallel factory for the synthesizer:

```python
# new module: src/theogony/retrieval/synthesizer_factory.py
def build_synthesizer(
    settings: Settings,
    llm: LLMProvider,
    *,
    audit_log: ExtractionAuditLog | None = None,
) -> AnswerSynthesizerLike:
    """Pick the right synthesizer for the active LLM provider.

    Stub provider → OfflineAnswerSynthesizer (deterministic, no LLM call).
    Real provider → AnswerSynthesizer (LLM-driven prose with citations).
    """
    if settings.llm.provider == "stub":
        return OfflineAnswerSynthesizer()
    return AnswerSynthesizer(llm, audit_log=audit_log)
```

`AnswerSynthesizerLike` is a small Protocol exporting just the `.synthesize(constellation, *, ...) -> Answer` method that both implementations honour. Keep the Protocol in `retrieval/synthesize.py` next to `AnswerSynthesizer`.

Update the seven callsites that today instantiate `AnswerSynthesizer` directly:

- `src/theogony/api/dependencies.py` (one call site)
- `src/theogony/api/app.py` (already imports the factory; uses dependencies)
- `src/theogony/cli.py` (one call site in the `ask` flow at line ~874)
- `src/theogony/mcp/server.py` (one call site at line ~238)
- `tests/api/conftest.py` (test fixture; keep as-is — tests can opt in)
- `tests/test_retrieval_pipeline.py` (test fixture — keep direct AnswerSynthesizer construction with a scripted StubLLMProvider; that's the legitimate test pattern)

The call sites in production code (`api/dependencies.py`, `cli.py`, `mcp/server.py`) switch from `AnswerSynthesizer(llm, ...)` to `build_synthesizer(settings, llm, audit_log=...)`. Tests continue to construct directly when they want a specific behaviour.

### Knob 3 — `OfflineAnswerSynthesizer` output format

Honest, structured, no fake-prose. Picks the **top N nodes by confidence** (default `N = 6`), formats them as a bulleted citation-only summary:

```python
async def synthesize(
    self,
    constellation: Constellation,
    *,
    max_output_tokens: int | None = None,
    temperature: float = 0.0,
    run_id: str | None = None,
) -> Answer:
    nodes = constellation.nodes
    if not nodes:
        return Answer(
            text=(
                "No language model is available on this hosted instance "
                "and the Chronik returned no nodes for this query. "
                "Try a more specific question or consult `pantheon_status`."
            ),
            cited_node_ids=[],
            raw_llm_response="",
            synthesis=SynthesisBreakdown(),
        )

    top = sorted(nodes, key=lambda n: n.confidence, reverse=True)[: self._top_n]
    cited_ids = [n.id for n in top]

    lines = [
        "No language model is available on this hosted instance, so the "
        "Chronik cannot synthesise a natural-language answer. Below are "
        f"the top {len(top)} cited sources retrieved for "
        f"`{constellation.query}`. Pass any cited id to `pantheon_node` "
        "to drill deeper.",
        "",
    ]
    for n in top:
        sr = n.source_ref
        loc = f" ({sr.location})" if sr and sr.location else ""
        ident = sr.identifier if sr and sr.identifier else "unknown source"
        lines.append(
            f"- [{n.id}] {n.label!s} — {ident}{loc} "
            f"(confidence {n.confidence:.2f})"
        )

    text = "\n".join(lines)
    return Answer(
        text=text,
        cited_node_ids=cited_ids,
        raw_llm_response="",
        synthesis=SynthesisBreakdown(),  # zero tokens, zero cost — honest
    )
```

`top_n` defaults to `6`; configurable via `Settings.llm.offline_top_n_citations: int = 6`.

The `[AKA-…]` brackets in the answer match the existing citation grammar in `_CITATION_RE` from `synthesize.py`, so `_extract_citations` can re-parse the text if anything downstream wants to. (It doesn't — `Answer.cited_node_ids` is the source of truth — but consistency costs nothing.)

### Knob 4 — Verdict semantics flow naturally

The pipeline computes `raised = not bool(answer.text)`. With the offline synthesizer, `text` is always non-empty (the always-included "No language model is available…" header). So:

- `status = "completed"` (text non-empty)
- `raised = False`
- `query_verdict` runs the normal high-conf / latency / gaps check
- For the bundled `pantheon_self` seed: 6 nodes, 6 cited, all confidence ≥ 0.95 → `citations_with_high_confidence_source = 6` → likely `verdict = "good"` or `"partial"` depending on thresholds, **never `"failed"`**.

This is the desired behaviour: hosted-without-LLM gives an honest "good"-verdict answer with full provenance, not a misleading "failed".

### Knob 5 — Minor cleanup: precise `verdict_reasoning` for the empty-text case

The verdict reasoning string `"synthesis raised before completion"` is misleading whenever the LLM returned `text=""` without raising. Replace with two distinct messages in `reporting/verdict.py::query_verdict`:

```python
# Before:
if raised:
    return ("failed", "synthesis raised before completion")

# After:
if raised:
    # `raised` here means "answer.text is empty"; distinguish the two
    # ways that happens for honest reasoning text.
    if "<sentinel for actual exception path>":
        return ("failed", "synthesis raised an exception")
    return ("failed", "synthesis returned empty text")
```

The sentinel — a small code change in the synthesizer to distinguish the two failure modes — is **out of scope for this PR**. Phase-1 fix: change the static reasoning text from `"synthesis raised before completion"` to `"synthesis returned empty answer"`. Less precise than the two-message split but more honest than the current lie. The two-mode split is a separate small ticket if anyone cares enough to chase it.

### Knob 6 — Test coverage: the regression gate the YAML promised

Three new tests, the first one is the ticket's explicit acceptance gate:

```python
# tests/test_pantheon_ask_with_real_stub.py — the regression gate

async def test_pantheon_ask_against_pantheon_self_seed_with_stub_provider() -> None:
    """End-to-end: stub LLM provider + bundled pantheon_self seed.

    This is the test that would have caught PHX-0070. It uses the
    real production wiring (build_llm_from_settings → factory →
    OfflineAnswerSynthesizer), not a unit-test mock.
    """
    settings = Settings(llm=LLMSettings(provider="stub"))
    store = InMemoryKnowledgeStore()
    await load_pantheon_self_seed(store)
    pipeline = await build_pipeline_from_settings(settings, store)

    result = await pipeline.ask("What is the Pantheon?", k=6, hops=2)

    assert result.report.verdict in {"good", "partial"}
    assert result.report.verdict_reasoning != "synthesis raised before completion"
    assert result.answer.text != ""
    assert result.answer.cited_node_ids, "must cite at least one source"
    # The first citation should appear in the constellation.
    assert result.answer.cited_node_ids[0] in {n.id for n in result.constellation.nodes}
```

Plus two unit tests on the synthesizer in isolation:

```python
# tests/test_offline_answer_synthesizer.py

async def test_offline_synthesizer_picks_top_n_by_confidence() -> None: ...
async def test_offline_synthesizer_handles_empty_constellation_gracefully() -> None: ...
async def test_offline_synthesizer_records_zero_cost_and_zero_tokens() -> None: ...
async def test_offline_synthesizer_text_contains_aka_brackets_for_each_cited_id() -> None: ...
```

---

## Goal

After this PR:

- `OfflineAnswerSynthesizer` lives in `src/theogony/retrieval/synthesize.py` (right next to `AnswerSynthesizer`); ~80 lines including the empty-constellation branch.
- `AnswerSynthesizerLike` Protocol declares the shared `.synthesize(...)` interface in the same module.
- `build_synthesizer(settings, llm, *, audit_log)` factory in `src/theogony/retrieval/synthesizer_factory.py`; routes by `settings.llm.provider`.
- The three production call sites (`api/dependencies.py`, `cli.py`, `mcp/server.py`) use `build_synthesizer` instead of constructing `AnswerSynthesizer` directly.
- `Settings.llm.offline_top_n_citations: int = 6` exists; default 6.
- The misleading `verdict_reasoning="synthesis raised before completion"` is replaced with `"synthesis returned empty answer"` in `reporting/verdict.py`.
- New `tests/test_offline_answer_synthesizer.py` with four unit tests.
- New `tests/test_pantheon_ask_with_real_stub.py` with the end-to-end regression gate.
- `hosted/README.md` "What works on the stub LLM" section enumerates the offline-synthesizer behaviour explicitly.
- After deploy, `https://theogony-mcp.fly.dev/sse` returns a non-failed `pantheon_ask` answer with full citations.

---

## Implementation plan (file-by-file)

### `src/theogony/retrieval/synthesize.py`

Add `AnswerSynthesizerLike` Protocol (small, ~10 lines including docstring). Add `OfflineAnswerSynthesizer` class (~80 lines). Both at the bottom of the existing module — no need to split into a new file. Update `__all__` to export the new names.

### `src/theogony/retrieval/synthesizer_factory.py` (new)

The single `build_synthesizer` function (~30 lines including docstring). Re-export from `src/theogony/retrieval/__init__.py`.

### `src/theogony/api/dependencies.py`

Replace `AnswerSynthesizer(state.llm, audit_log=state.audit)` with `build_synthesizer(state.settings, state.llm, audit_log=state.audit)`. Imports adjusted accordingly.

### `src/theogony/cli.py`

Same swap at line ~874 (the `_run_ask` flow).

### `src/theogony/mcp/server.py`

Same swap at line ~238 (the `pantheon_ask` lifespan binding).

### `src/theogony/config/settings.py`

Add `offline_top_n_citations: int = Field(default=6, ge=1, le=50)` to `LLMSettings`.

### `src/theogony/reporting/verdict.py`

Change the `raised` branch reasoning text from `"synthesis raised before completion"` to `"synthesis returned empty answer"`. The truthful split between "actual exception" vs "empty text" is a follow-up ticket.

### `tests/test_offline_answer_synthesizer.py` (new)

Four unit tests per Knob 6.

### `tests/test_pantheon_ask_with_real_stub.py` (new)

The end-to-end regression gate per Knob 6. Uses `pytest.mark.asyncio` and the existing `pantheon_self`-seed loader.

### `hosted/README.md`

In the "Cost expectations" section (or a new "What works on the stub LLM" subsection), enumerate:

- ✓ `pantheon_status`, `pantheon_node`, `pantheon_reports_list`, `pantheon_reports_show` — full functionality, no LLM needed.
- ✓ `pantheon_ask` — returns a structured citation-only answer with the top N (default 6) sources by confidence. No natural-language synthesis. Honest about the limitation in the answer text.
- ✗ Natural-language synthesis — requires a real LLM provider; set `THEOGONY_LLM__PROVIDER=anthropic` (or `gemini`/`openai`) and the matching `*_API_KEY` env var.

### `docs/PHOENIX_BACKLOG.md`

Append to the PHX-0070 entry: `"Closed by PR #...: OfflineAnswerSynthesizer routes the no-LLM-key path away from the empty-StubLLMProvider failure mode. Verdict semantics flow naturally; verdict_reasoning text corrected from 'synthesis raised before completion' to 'synthesis returned empty answer'."`

---

## Cost-benefit considerations

**Token cost**: smallest of the post-W1 work. ~150 lines of new code + ~80 lines of tests + 30 lines of docs. Estimate ≤ €0.20 of Composer execution.

**Runtime cost**: Net **negative** for the offline path. The current behaviour does an LLM round-trip (or stub call) that produces empty text; the offline synthesizer skips the LLM entirely and runs a single sort + format. Sub-millisecond.

**Failure modes worth watching**:

- **Prompt resource missing on stub deploys**: `AnswerSynthesizer.__init__` calls `_load_default_prompt()` which raises `FileNotFoundError` if the packaged prompt is missing. `OfflineAnswerSynthesizer` does **not** load a prompt — it's pure code. So stub deploys no longer depend on the prompt resource being packaged correctly. Net robustness win.
- **Test fixtures that pass `provider="stub"` and a scripted `StubLLMProvider`**: with the factory change, those tests now get the offline synthesizer instead of the LLM-driven one + their scripted responses become dead code. **Mitigation**: tests that need scripted-response behaviour construct `AnswerSynthesizer` directly (the existing pattern in `tests/test_retrieval_pipeline.py`). The factory routes only when called; direct construction is unaffected.
- **Citation invariant on the offline path**: the offline synthesizer's `cited_node_ids` are pulled directly from `constellation.nodes`, so they cannot be hallucinated by definition. The `_extract_citations` re-parse path is bypassed. Document explicitly in the docstring.
- **Empty constellation**: `pantheon_ask` against a totally empty store returns the empty-constellation honest message rather than crashing. Test it.

---

## Out of scope (do not do)

- **Do not** modify `StubLLMProvider` itself. It stays as the generic test fixture.
- **Do not** introduce per-call LLM key pass-through (that is PHX-0066 Phase 2).
- **Do not** add LLM-style prose to the offline answer. The honest "no LLM available, here are the sources" is the contract; faking prose would be the worse failure mode.
- **Do not** split `verdict_reasoning` into "actual exception" vs "empty text" — that requires an extra signal from the synthesizer and a small `query_verdict` refactor. File a separate one-line ticket if it bothers anyone.
- **Do not** change the `Answer` model shape. `OfflineAnswerSynthesizer` returns the same `Answer` Pydantic, with `synthesis = SynthesisBreakdown()` (all zeros) — that is the cleanest signal that the answer was synth-free.
- **Do not** change the `AnswerSynthesizer` LLM-driven path. It is correct as it stands; only the no-LLM routing was wrong.
- **Do not** change the prompt resource. The offline path does not use it.

---

## Done when

- [ ] `OfflineAnswerSynthesizer` and `AnswerSynthesizerLike` Protocol exist in `src/theogony/retrieval/synthesize.py`.
- [ ] `build_synthesizer` exists in `src/theogony/retrieval/synthesizer_factory.py` and is re-exported from `retrieval/__init__.py`.
- [ ] The three production call sites (`api/dependencies.py`, `cli.py`, `mcp/server.py`) use `build_synthesizer`.
- [ ] `Settings.llm.offline_top_n_citations` exists with default 6.
- [ ] `query_verdict`'s `raised`-branch reasoning is `"synthesis returned empty answer"`.
- [ ] `tests/test_offline_answer_synthesizer.py` covers four unit tests; all green.
- [ ] `tests/test_pantheon_ask_with_real_stub.py` is the regression gate; passes against the bundled `pantheon_self` seed.
- [ ] All existing tests stay green without modification (full `pytest -q`).
- [ ] `ruff check` clean. `ruff format --check` clean. `mypy --strict` clean on new modules.
- [ ] `hosted/README.md` enumerates what works on the stub LLM.
- [ ] `docs/PHOENIX_BACKLOG.md` PHX-0070 entry gets the closing note.
- [ ] Verified live: after re-deploy to `theogony-mcp.fly.dev`, `pantheon_ask({"q": "What is the Pantheon?", "k": 6})` returns `verdict in {"good", "partial"}` with non-empty `cited_node_ids` and a structured citation-only `answer` text.
- [ ] PR title: `fix(retrieval): PHX-0070 — OfflineAnswerSynthesizer for no-LLM-key deploys`. PR body includes the live `pantheon_ask` reproducer output before/after.

---

## After this PR

PHX-0070 closed → hosted MCP at `theogony-mcp.fly.dev` produces a credible `pantheon_ask` answer for any agent that connects, **without** requiring anyone to fund an LLM key. PHX-0066's friction-free-demo promise is restored.

Logical next: PHX-0069 (Fly SSE session affinity) is the second post-Wave-1 small fix; together with this one they close the post-W3 hosted-bug pair. After that, Wave 2 begins with PHX-0061 (Vector-Routed Federation), PHX-0062 (Negative Knowledge), or PHX-0063 (Chronik-Diff) — your pick of which becomes the W5 brief.
