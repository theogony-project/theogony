# Talos Brief — PR #30 Follow-up

**From:** Hesiod
**To:** Talos
**Branch:** `feat/llm-default-openai-anthropic` (push directly onto the existing PR #30, do **not** open a new PR)
**Scope:** small, mechanical follow-up to land PR #30 cleanly

---

## Context

PR #30 introduced `OpenAILLMProvider` + `AnthropicLLMProvider` and switched the default LLM to OpenAI `gpt-4o-mini`. The PR was authored under a process slip (Hesiod implemented instead of briefing Talos). The User has accepted the artefact but flagged two CI/quality issues and revisited the default-model choice. This brief closes those gaps.

The PR is otherwise approved. CI is currently:
- Lint: **fail** (single `ruff format` violation)
- Tests (3.12, 3.13): pass
- Neo4j contract + live: pass

Goal of this follow-up: green CI, correct docstring, right default model, slightly more honest Anthropic error path. Then merge.

---

## Changes (in order — keep them in one commit per group; one push at the end)

### Change 1 — Lint fix (blocker)

`tests/test_pipeline_characterization.py` — collapse the multi-line `pytest.skip(...)` inside `_build_llm()` to single-line so `ruff format --check` passes. Verify by running locally:

```bash
ruff format --check src/ tests/
```

Must report `126 files already formatted`.

### Change 2 — Docstring correction (blocker)

`src/theogony/config/settings.py`, the `openai_api_key` Field (around line 258–262):

```python
openai_api_key: SecretStr | None = Field(
    default=None,
    alias="OPENAI_API_KEY",
    description="Used by GeminiLLMProvider only when provider=openai.",  # ← wrong
)
```

Replace the description with: `"Used by OpenAILLMProvider when provider=openai."`

(Copy-paste residue from the Gemini field. Cosmetic but visible in `--help` and any schema export.)

### Change 3 — Switch default LLM to Claude 3.5 Haiku (decision: Hesiod)

Rationale: prepaid Anthropic credits, hard cost ceiling per top-up, qualitatively cleaner instruction-following on literary entity/relation extraction (German names, transliteration, relation directionality) than `gpt-4o-mini`. Cost differential (~5×) lands at €3–8 per Gutenberg demo ingest, well within "prepaid credit" semantics.

We deliberately **do not** jump to Claude Haiku 4.5 yet — the pinned `anthropic>=0.30.0` SDK pre-dates the 4.5 release and we do not want to widen scope here. File a Gen-1 PHX if you want to revisit (note in PR body if you think the SDK pin is fine).

Files to update:

1. `src/theogony/config/settings.py`, `LLMSettings`:
   - Change `provider: LLMProviderName = "openai"` → `provider: LLMProviderName = "anthropic"`.
   - Update the class docstring (currently extols OpenAI as default) to reflect Anthropic Claude 3.5 Haiku as the default; keep the existing rationale (prepaid credits, predictable billing) but switch the named provider.
   - The `_default_model_id_for_provider` validator already maps `"anthropic" → "claude-3-5-haiku-20241022"` — no change needed there.

2. `README.md` — wherever the demo path mentions `OPENAI_API_KEY` or `gpt-4o-mini`, switch to `ANTHROPIC_API_KEY` and `claude-3-5-haiku-20241022`. Keep OpenAI and Gemini documented as valid alternatives (one-line each: env var + `THEOGONY_LLM__PROVIDER=...`).

3. `src/theogony/cli.py` — the `status` command currently asserts/displays `openai` as the default provider name. Update the expected default to `anthropic`. (Search for `"openai"` in `status`-handling code.)

4. Tests — adjust any test that hard-codes the OpenAI default:
   - `tests/test_settings.py` — default-provider assertion.
   - `tests/test_cli.py` — `status` output assertion.
   - `tests/test_agents_factory.py` — if it asserts on the *default* path, switch to Anthropic; if it parametrizes both, just verify both branches still pass.
   - `tests/test_extraction_*_live.py` — if any of them skip-on `OPENAI_API_KEY`, generalize to skip-on `Settings().active_llm_api_key() is None` so they work for whichever provider is configured.
   - `tests/cli/test_cli_ask.py` — same generalization if needed.

   **Principle**: tests should care about *the active provider* (whatever it is), not about a specific provider name, except for tests that explicitly target one provider's wire-format.

### Change 4 — Small Anthropic robustness (optional but encouraged)

`src/theogony/agents/llm_anthropic.py`, in `complete()`:

When `json_schema is not None` and we iterate `message.content` looking for the forced `tool_use` block, if the loop finishes without finding one, currently we silently return `text=""`. The downstream Pydantic parse then fails with an opaque "expected JSON object got empty string"-style error.

Replace the silent fall-through with:

```python
raise RuntimeError(
    f"AnthropicLLMProvider: forced tool {_TOOL_NAME!r} not found in response "
    f"for model_id={self._model_id}; got block types "
    f"{[getattr(b, 'type', None) for b in message.content]}"
)
```

Keep the plain-text branch as-is (an empty text response is legitimate there).

### Change 5 — Tiny dead-code cleanup (optional)

`src/theogony/agents/llm_openai.py` and `src/theogony/agents/llm_anthropic.py` both contain:

```python
if TYPE_CHECKING:
    pass
```

near the top. Empty blocks. Either delete the `TYPE_CHECKING` import + the block, or fill it if you actually need a type-only import. Delete is fine — neither file uses `TYPE_CHECKING`-only symbols.

---

## Out of scope (do **not** do here)

- `max_tokens` → `max_completion_tokens` migration in `OpenAILLMProvider`. Fine for current models; file a PHX if you want to track it for the o-series / gpt-5 future.
- Switching to `claude-haiku-4-5`. Needs SDK-version verification first.
- Pricing constants (`USD_TO_EUR`, list prices). Acceptable Gen-1 hardcodes; revisit when we add a third currency or when a price actually changes.
- Any further test refactoring beyond what Change 3 forces.

---

## Verification

Before pushing:

```bash
ruff format --check src/ tests/
ruff check src/ tests/
mypy src/
pytest -q
```

All must be green. (`pytest` will skip live tests without API keys — that is expected.)

Push to the existing branch:

```bash
git push origin feat/llm-default-openai-anthropic
```

Then update the PR body: add a short "PR-30 follow-up" section noting (a) lint fixed, (b) docstring fixed, (c) default switched to Claude 3.5 Haiku with one-line rationale, (d) optional polish applied.

---

## Escalation

Escalate to Hesiod (don't decide silently) if any of these surface:

1. Switching the default to Anthropic breaks more tests than the ones listed in Change 3 — there may be a hidden assumption to discuss.
2. The `anthropic>=0.30.0` SDK turns out to not support `claude-3-5-haiku-20241022` (very unlikely, but if it does — flag, don't pin a higher version unilaterally).
3. Anything in the existing Anthropic provider implementation looks structurally wrong while you are touching the file (not just the polish item above) — open a fresh PHX rather than expanding scope here.

Otherwise: proceed, push, ping when CI is green.
