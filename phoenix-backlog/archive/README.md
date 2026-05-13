# Phoenix Backlog Archive — Pre-MESH-Migration

This directory holds the **51 active PHX YAMLs** as they existed at the moment of the MESH-migration pivot (2026-05-13).

They were moved here (via `git mv`, so history is preserved) when the binding doctrine of the substrate shifted from the catalogued Generation-1 plan to the MESH triplet ([`MESH_SUBSTRATE.md`](../../docs/MESH_SUBSTRATE.md) + [`MESH_IMPLEMENTATION.md`](../../docs/MESH_IMPLEMENTATION.md) + [`MESH_RETRIEVAL.md`](../../docs/MESH_RETRIEVAL.md)), and the binding implementation plan became [`MESH_MIGRATION_PLAN.md`](../../docs/MESH_MIGRATION_PLAN.md).

## Status of these tickets

Each ticket has been labelled via the migration audit at [`MIGRATION_AUDIT.csv`](MIGRATION_AUDIT.csv). The three outcomes are:

- **carry-forward** — a new PHX-1000+ ticket has been filed; see the post-migration catalogue at [`docs/PHOENIX_BACKLOG.md`](../../docs/PHOENIX_BACKLOG.md).
- **obsolete** — the concern no longer applies (Neo4j-specific, or superseded by the MESH doctrine). The YAML stays here unchanged.
- **absorbed into MESH doctrine** — the concern is now part of the MESH triplet itself. The YAML stays here unchanged.

**The pass is complete as of 2026-05-13.** 28 tickets were carried forward, 13 were absorbed, and 10 were declared obsolete.

## Why preserve them at all

The `phoenix-backlog/README.md` rule is: tickets are never silently deleted. These YAMLs are the record of the Generation-1 design discourse — what was tried, what was deferred, what was filed in response to which run report. They are useful to:

- the next agent doing the labelling pass (they need the original wording to decide carry-forward / obsolete / absorbed);
- any future audit of how the project's design evolved;
- the immune system's long-horizon self-observation (per [`IMMUNE_SYSTEM.md`](../../docs/IMMUNE_SYSTEM.md) and [`SELF_MODIFICATION.md`](../../docs/SELF_MODIFICATION.md)).

## Don't edit these in place

The archive is read-only. If a ticket here turns out to still describe a live concern post-MESH-pivot, file a **new** ticket in the post-migration backlog (numbered PHX-1000+) and reference this YAML via `migrated_from`. Do not retroactively rewrite the archived YAML.
