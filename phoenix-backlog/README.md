# Phoenix Backlog — Active Tickets

This directory holds the **active** Phoenix tickets as structured YAML files. The full catalogue of every conceived ticket — including those without a YAML here — lives in [`docs/PHOENIX_BACKLOG.md`](../docs/PHOENIX_BACKLOG.md) and in the implementation plan ([`docs/IMPLEMENTATION_PLAN_GEN1.md`](../docs/IMPLEMENTATION_PLAN_GEN1.md) §7).

## When to create a YAML

Create a `PHX-####.yaml` here when one of the following becomes true for a ticket already named in the catalogue:

- An agent or human is **actively working** on it.
- A pull request **references** it (e.g. "blocked by PHX-0017", "partially addresses PHX-0021").
- A RunReport or anomaly rule **emits** it as a finding.
- The ticket needs a **structured workspace** — fields, status transitions, linked PRs, evidence — beyond what prose in the catalogue can carry.

If none of these are true, leave the ticket as a catalogue entry only. An empty stub YAML is worse than no YAML — it pretends to be tracked when it is not.

## When to file a brand-new ticket

If the ticket is genuinely new (not yet in the catalogue):

1. Pick the next free PHX-#### number, ascending and contiguous from the highest already used in the catalogue (`docs/PHOENIX_BACKLOG.md`) and the implementation plan (`docs/IMPLEMENTATION_PLAN_GEN1.md` §7). Numbers are never reused.
2. Add a short entry to `docs/PHOENIX_BACKLOG.md` (or the relevant plan section) so the catalogue stays the source of truth for the numbered space.
3. Create the YAML here if the ticket is active per the criteria above; otherwise the catalogue entry alone is sufficient.

## YAML schema

See [`docs/PHOENIX_BACKLOG.md`](../docs/PHOENIX_BACKLOG.md#ticket-format) for the canonical schema. In short:

- `id`, `category`, `priority`, `status`, `generation_target`, `title`, `filed_by`, `created_at`, `description`, `resolution`.
- Add `linked_prs:` and `linked_runreports:` lists once such links exist.

## Lifecycle

- A YAML is **created** when a ticket becomes active.
- It is **updated** as work progresses (`status`, `linked_prs`, evidence in `description`).
- It is **resolved** by setting `status: resolved` and filling `resolution`. Resolved tickets remain as YAML for historical traceability of how a question was settled — they are not deleted.
- A YAML may be **archived back to catalogue-only** form (i.e. the YAML deleted, the catalogue entry retained) only if the ticket was opened in error or has clearly become obsolete; this is rare and should be noted in the commit message.

## Numbering hygiene

The catalogue allocates the numbered space, not this directory. If you see `PHX-0021` referenced in the plan but no `PHX-0021.yaml` here, that is **not** a gap — it is a catalogue-only ticket awaiting activation. Run `git grep "PHX-0021"` to find every place the ticket is mentioned across the repository.
