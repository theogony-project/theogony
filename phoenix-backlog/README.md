# Phoenix Backlog — Active Tickets

> **State as of 2026-05-13 — post-migration.** The MESH migration pivot has landed (see [`docs/MESH_MIGRATION_PLAN.md`](../docs/MESH_MIGRATION_PLAN.md)) and the 51 legacy PHX YAMLs have been labelled via [`archive/MIGRATION_AUDIT.csv`](archive/MIGRATION_AUDIT.csv). The post-migration backlog is open at PHX-1000+; the meta-ticket [`PHX-1001.yaml`](PHX-1001.yaml) tracks the migration lifecycle. The new catalogue is at [`docs/PHOENIX_BACKLOG.md`](../docs/PHOENIX_BACKLOG.md).
>
> The legacy catalogue at [`docs/PHOENIX_BACKLOG.md`](../docs/PHOENIX_BACKLOG.md) reflects the pre-MESH state. Any ticket cited from a pre-MESH document refers to that legacy catalogue; the new catalogue will be written when the labelling pass completes.

This directory holds the **active** Phoenix tickets as structured YAML files. The legacy catalogue of every Gen-1 ticket — including those without a YAML here — lives in [`docs/PHOENIX_BACKLOG.md`](../docs/PHOENIX_BACKLOG.md) and in the legacy implementation plan ([`docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md`](../docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md) §7). Both are historical context, not operative; the operative plan is [`docs/MESH_MIGRATION_PLAN.md`](../docs/MESH_MIGRATION_PLAN.md).

## When to create a YAML

Create a `PHX-####.yaml` here when one of the following becomes true for a ticket already named in the catalogue:

- An agent or human is **actively working** on it.
- A pull request **references** it (e.g. "blocked by PHX-0017", "partially addresses PHX-0021").
- A RunReport or anomaly rule **emits** it as a finding.
- The ticket needs a **structured workspace** — fields, status transitions, linked PRs, evidence — beyond what prose in the catalogue can carry.

If none of these are true, leave the ticket as a catalogue entry only. An empty stub YAML is worse than no YAML — it pretends to be tracked when it is not.

## When to file a brand-new ticket

If the ticket is genuinely new (post-MESH-pivot):

1. **Pick a number in the post-migration space (PHX-1000+).** The gap between PHX-0074 (last legacy ticket) and PHX-1000 is deliberate — it marks the doctrine boundary. Numbers are never reused.
2. Add a short entry to the post-migration catalogue (to be created; until then, link the ticket from [`docs/MESH_MIGRATION_PLAN.md`](../docs/MESH_MIGRATION_PLAN.md) or the relevant doctrine doc).
3. Create the YAML here if the ticket is active per the criteria above; otherwise a catalogue entry alone is sufficient.

If the ticket appears to duplicate a concern from the archived legacy backlog ([`archive/`](archive/)), reference the legacy ticket via a `migrated_from:` field in the new YAML, so the lineage is preserved without re-using the old number.

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

The catalogue allocates the numbered space, not this directory. If you see `PHX-0021` referenced in a pre-MESH document but no `PHX-0021.yaml` here, that is **not** a gap — it has been moved to [`archive/`](archive/) along with the rest of the legacy backlog (and is, for that specific number, a legacy catalogue-only ticket that was never activated as a YAML). Run `git grep "PHX-0021"` to find every place the ticket is mentioned across the repository.

For post-MESH tickets (PHX-1000+), the same rule applies: a catalogue entry without a YAML here means the ticket is named but not yet active.
