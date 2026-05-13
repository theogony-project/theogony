# Phoenix Backlog Archive — Pre-MESH-Migration

This directory holds the **51 active PHX YAMLs** as they existed at the moment of the MESH-migration pivot (2026-05-13).

They were moved here (via `git mv`, so history is preserved) when the binding doctrine of the substrate shifted from the catalogued Generation-1 plan to the MESH triplet ([`MESH_SUBSTRATE.md`](../../docs/MESH_SUBSTRATE.md) + [`MESH_IMPLEMENTATION.md`](../../docs/MESH_IMPLEMENTATION.md) + [`MESH_RETRIEVAL.md`](../../docs/MESH_RETRIEVAL.md)), and the binding implementation plan became [`MESH_MIGRATION_PLAN.md`](../../docs/MESH_MIGRATION_PLAN.md).

## Status of these tickets

Each ticket here is one of three things; **the labelling pass that decides which** has not yet been done. The migration plan ([`MESH_MIGRATION_PLAN.md`](../../docs/MESH_MIGRATION_PLAN.md) §"Parallel etappe — PHX backlog migration") specifies the labelling pass as its own piece of work:

- **carry-forward** — the ticket addresses a real concern that survives the migration. When labelled as such, a new ticket gets filed in the post-migration backlog (numbered PHX-1000+), with `migrated_from: PHX-XXXX` linking back to the archived YAML.
- **obsolete** — the ticket addresses a concern that no longer applies (e.g., tickets about Neo4j, about codebook edge compression the MESH doctrine does not use, about retrieval strategies that diversified injection absorbs). When labelled as such, the YAML stays here unchanged.
- **absorbed into MESH doctrine** — the ticket's concern is now part of the MESH triplet itself (e.g., "Activation Engine v1" → `MESH_RETRIEVAL.md` §"Diversified injection" and §"Spreading Activation as the universal retrieval primitive"). When labelled as such, the YAML stays here unchanged.

The audit trail of the labelling pass will live in `MIGRATION_AUDIT.csv` next to this README (one row per archived ticket: `id, title, decision, new_ticket_id_or_null, reason`). That file does not yet exist; it is produced when the labelling pass runs.

## Why preserve them at all

The `phoenix-backlog/README.md` rule is: tickets are never silently deleted. These YAMLs are the record of the Generation-1 design discourse — what was tried, what was deferred, what was filed in response to which run report. They are useful to:

- the next agent doing the labelling pass (they need the original wording to decide carry-forward / obsolete / absorbed);
- any future audit of how the project's design evolved;
- the immune system's long-horizon self-observation (per [`IMMUNE_SYSTEM.md`](../../docs/IMMUNE_SYSTEM.md) and [`SELF_MODIFICATION.md`](../../docs/SELF_MODIFICATION.md)).

## Don't edit these in place

The archive is read-only. If a ticket here turns out to still describe a live concern post-MESH-pivot, file a **new** ticket in the post-migration backlog (numbered PHX-1000+) and reference this YAML via `migrated_from`. Do not retroactively rewrite the archived YAML.
