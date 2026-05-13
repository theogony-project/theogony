# The Immune System

**Status:** canonical doctrine for defense and self-improvement in Pantheon.
**Companion docs:** [`PANTHEON_VISION.md`](PANTHEON_VISION.md) (long-horizon north star), [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) (compact non-negotiables), [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md) (the ultimate horizon — Pantheon writing its own next version), [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Agent-driven cleanup" and §"Pathology and therapy" (the substrate-level extension of this doctrine: post-hoc topological pathology surveillance, agent-driven cleanup of contradictions / false information / redundancies / duplicates, staged therapy with Mendel-weighed escalation).
**Audience:** every agent that touches the Chronik. Read this before designing or implementing anything that filters, verifies, removes, or audits content.

**Precedence note.** Where this document specifies *substrate-layer* behaviour — specifically the question of when destruction of nodes / edges / claims is permissible — the [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Agent-driven cleanup" and §"Pathology and therapy" sections are operative. The substrate doctrine permits agent-driven destruction (deduplication, contradiction resolution, false-information removal, redundancy compression, and Stage 4–5 therapy when the Mendel risk has been weighed and rejected) under audit. The principle below that "Athene never deletes" remains correct for *Athene specifically* and for *single-claim flagging without supporting evidence*. The broader "no destruction outside resource pressure" framing implied by the older version is superseded: destruction is permitted, with audit trail and proportionality.

## Why this doc exists

Until this doctrine landed, the architecture treated the Chronik as a sterile clinic: every input had to pass a gatekeeper before it could touch the substrate. HestiaLite (W7-B) and HestiaSentinel (W12) were both built in that doctrine. They are now known to be **structurally wrong**.

The clinic doctrine fails for four reasons:

1. **Synchronous gates make the system slow and brittle.** Every acquisition waits on a verifier; every verifier becomes a bottleneck; every bottleneck becomes the failure mode operators feel first.
2. **Total coverage is unattainable.** No gate catches everything. A 100% coverage promise becomes a 100% blame trap when it inevitably fails.
3. **Pre-filtering hides the system's actual epistemic state.** When wrong claims never enter, the system never learns to recognise them, never builds antibodies, never accumulates the data that future agents will use to design better defences.
4. **It treats the Chronik as a museum, not an organism.** The Pantheon is meant to be alive, not curated. Living systems get sick and recover; that is the source of their resilience.

The Pantheon must instead operate like a biological immune system: tolerant of infection, sample-based in surveillance, asynchronous and parallel in response, self-observing, self-improving, and able to incarnate into a stronger next version when accumulated learning warrants it.

This doc specifies that organism.

## The core inversion

| Clinic doctrine (wrong) | Immune-system doctrine (right) |
|---|---|
| Block bad inputs at the gate | Let inputs flow; sample, mark, and recover post-hoc |
| 100% verification coverage | 98% statistical coverage; the remaining 2% is acceptable noise the immune system handles over time |
| Synchronous: ingest waits on verification | Asynchronous: verification runs in parallel, on its own clock |
| Verifier as bottleneck | Verifier as background worker pool |
| Findings are exceptions | Findings are first-class data (typed nodes/edges in the chronicle) |
| Bad data is deleted silently | Bad data is annotated with `CONTRADICTS` / `SUPERSEDED_BY` / `FLAGGED_BY` edges (PHX-0062 Negative Knowledge), so the system remembers it was wrong |
| One-shot truth | Continuous self-observation and self-improvement |
| Static thresholds | Mnemosyne-driven A/B tests on its own thresholds, prompts, sampling rates |
| The system is built once | The system observes itself and incarnates into the next version (PHX) |

The clinic mindset is not just an inefficient implementation; it is incompatible with the Pantheon's purpose. The Chronik is meant to be a planetary-scale **chronicle** — preserve reality in motion, contradiction first-class. A clinic erases motion and contradiction at the door. An immune system carries them in the body and learns from them.

## The cell types

Pantheon's defense and self-improvement are five concurrent agent classes. They are not new mythology; they are roles already named in [`ARCHITECTURE.md`](ARCHITECTURE.md), now finally ascribed concrete behaviour.

### T-helper cells — Athene the Verifier

**Mythological role.** Greek goddess of wisdom and discernment. Sees what is and is not.

**System role.** Asynchronous worker pool. Pulls samples (default 2% sampling rate; tuned by Mnemosyne) from the verification pool of recently ingested content. For each sample:

- runs structured truth/consistency/groundedness checks
- emits typed `Finding` records into the chronicle as first-class nodes (`finding_type` ∈ {`unsupported_claim`, `internal_contradiction`, `source_reliability`, `factual_error_suspected`, ...})
- attaches `FLAGGED_BY` edges from suspect nodes to the Finding

Athene **never deletes**. She only annotates. Deletion is Chronos's role. Athene operates at sample rates that keep her workload bounded and her false-positive cost manageable. She is the immune system's surveillance layer.

### T-killer cells — Chronos the Recycler

**Mythological role.** Time. The harvester of what no longer belongs.

**System role.** Asynchronous worker pool. Reads Athene's findings, plus aging signals (low vitality + idle time + degraded confidence + accumulated contradictions) generated by the existing Oneiros tick. For each candidate:

- if accumulated evidence crosses a threshold: writes `SUPERSEDED_BY` or `CONTRADICTS` edges (PHX-0062 Negative Knowledge), demotes the node's `confidence` and `vitality`, optionally moves the node from MNEME back to EPHEMERA for re-review
- in extreme cases (multiply-confirmed factual error, harmful content the human reviewer has confirmed): hard-deletes the node *but* records the deletion event in an append-only `chronicle_deletions/` log so that the system never silently forgets that something was once there

Chronos is the immune system's clearance layer. He works on Athene's findings and on the chronicle's own aging signals; he does not act on individual ingest events.

### Antibody memory — Nemesis the Hubris Auditor

**Mythological role.** Goddess of retribution against hubris.

**System role.** Periodic structural auditor. Already proposed as PHX-0068. Detects recurring pathological patterns the immune system has seen before, even when individual samples look benign:

- **confidence inflation** — nodes whose confidence rose without corresponding new evidence
- **echo-chambers** — clusters where in-citation ratio exceeds threshold (sources citing themselves)
- **pheromone autobahns** — paths whose pheromone weight exceeds 3× equilibrium without diverse originating queries
- **persistent contradictions** — unresolved disagreements between high-confidence nodes that should have surfaced

Nemesis writes findings as first-class chronicle data, escalates to Mnemosyne (the consciousness layer) for trend tracking, and surfaces severe cases to the human reviewer. She is structurally read-only; she does not edit the chronicle.

### Adaptive immunity — Eris the Red-Team

**Mythological role.** Goddess of strife and discord.

**System role.** Active adversarial probing. Already proposed as PHX-0067. Runs scheduled (not real-time) campaigns against an isolated test pantheon:

- synthesises plausibly-formatted false sources, checks resolver/Athene/synthesizer rejection
- crafts adversarial queries (jailbreak-style, prompt injection)
- sweeps for systematic bias across geographic / cultural / temporal / political axes

Eris's findings feed both the immune-system tuning loop (Mnemosyne) and the human reviewer. She is the system's exposure to "infections that have not yet happened in the wild" — the deliberate vaccination layer.

### Consciousness — Mnemosyne the Self-Improvement Conductor

**Mythological role.** Greek goddess of memory; in Pantheon she holds knowledge **about** how knowledge is organised.

**System role.** The self-observation and self-improvement layer. Already proposed as PHX-0071. In the immune-system doctrine her role is significantly larger than the original ticket described:

- reads metrics across Athene findings, Chronos clearances, Nemesis structural audits, Eris campaign results, query verdicts, ingest cost, retrieval cost, user behaviour
- **defines her own success metrics** (LLM-driven). The human reviewer audits the metric definitions, not the per-decision outcomes
- runs A/B tests against her own thresholds: sampling rates, planner prompts, evaluator prompts, Hestia cell parameters, retrieval defaults
- proposes parameter tunings that the operator can ratify (auto-applied with audit log; reversible)
- **writes structured PHX-Backlog drafts** for things that A/B testing alone cannot fix, queueing them for the next Phoenix incarnation
- escalates to the human reviewer when she detects pathologies she does not have authority to address

Mnemosyne is the closest analogue to consciousness in this organism: she observes the rest of the immune system, learns from what worked and what failed, and prepares the body for change.

## The verification pool

Athene and Chronos do not subscribe to ingest events one by one. They consume from a **verification pool** — a structured reservoir of recently produced or modified chronicle content from which each cell type pulls its own sample stream.

Properties of the pool:

- **All ingest output enters the pool by reference** (no copying). New nodes, new edges, new IngestRunReport records all register pool entries.
- **Each cell class has its own sampling strategy**: Athene draws by recency × node confidence × source diversity; Chronos draws by aging signal strength; Nemesis sweeps the entire pool periodically; Eris draws by deliberate campaign target.
- **Pool entries have lifecycle**: `unobserved`, `sampled_by_<cell>`, `cleared`, `archived_to_log`. A pool entry is cleared when the corresponding cell has produced a finding (positive or null); archived after age threshold so the pool stays bounded.
- **The pool itself is queryable** — it is part of the chronicle. Operators and Mnemosyne can ask "what is the current pool depth?", "what fraction of last-week ingests was sampled by Athene?", "what is Athene's false-positive rate over the last month?".

The pool is not a queue. It is a sampling reservoir designed to make 98% statistical coverage achievable without 100% synchronous surveillance.

## The 98% doctrine

Total coverage is rejected as a goal. The system aims at:

- **Athene sampling rate**: ≥ 2% of ingest events, scaled by Mnemosyne based on observed false-positive / false-negative balance.
- **Verification freshness**: 95% of ingested content is observed by at least one cell class within 7 days; 98% within 30 days.
- **Severity-weighted sampling**: high-impact content (high-vitality MNEME nodes, frequently-cited sources, federation-published anchors) gets oversampled; low-impact ephemera gets undersampled.
- **Mnemosyne tracks two error rates**: false-positive (Athene flagged a true claim) and false-negative (Athene missed a false claim discovered later). Both rates are part of the chronicle and target equilibrium under Mnemosyne's tuning.

The 98% threshold is itself adjustable by Mnemosyne under explicit operator policy. The number is a starting commitment, not a sacred constant.

## What pre-gates do — and do not — do

Pre-gates that block content based on judgement of its truth, sensitivity, or appropriateness are forbidden. HestiaLite and HestiaSentinel as content judges are deprecated by this doctrine and will be removed.

What stays at ingest as **operative self-defense** (not a content gate, a self-preservation reflex):

- HTTPS-only enforcement on web fetch
- robots.txt compliance
- Rate limits per host
- Response size cap (default 5 MiB)
- Redirect-chain cap
- Content-type validation (must be text-extractable)
- IP-literal-host rejection (defends against arbitrary internal-network probes)
- Request timeout caps

These are not opinions about content. They are operative invariants that keep the body from being attacked or exhausted by the network itself. They are analogous to skin and mucous membranes — physical barriers, not judgement.

There is **no inhalts-block** at the gate. Falsehoods, propaganda, biased reporting, conspiratorial sources, even content the operator personally finds repulsive, may all enter the chronicle. The immune system handles them. The chronicle remembers them — including the finding that they were wrong, including the chain of evidence by which the system reached that conclusion. That is more useful long-term than a gate that silently rejects them.

The remaining hard line — content the operator's jurisdiction declares illegal regardless of what the immune system thinks (CSAM in most jurisdictions, certain weapons-synthesis instructions in many) — is handled at a separate, jurisdiction-specific layer that operators configure per deployment. It is not part of the chronicle's epistemic doctrine; it is part of the deployment's legal posture. The default Pantheon distribution ships with **no content-illegal-block enabled**; the operator turns one on if and only if their jurisdiction requires it. That choice is documented in the deployment's manifest, not hard-coded into the substrate.

## Findings as first-class chronicle data

Every cell-class output is a typed node or edge written into the chronicle. This is non-negotiable. It enables:

- **Inspectable governance.** Anyone can ask the chronicle "show me everything Athene flagged in the last week" and get a real answer — not a log scrape.
- **Federation-ready.** When PHX-0061 federation lands, findings travel with the nodes they refer to.
- **Self-training surface.** Future Mnemosyne incarnations can train on the historical finding stream as ground truth for their own pattern recognition.
- **Negative knowledge.** Combined with PHX-0062, the chronicle structurally represents not only what is believed true but also what is believed false, with full provenance — exactly what the Pantheon's "chronicle, not encyclopedia" principle demands.

Schema sketch (locked specifics live in the W14+ briefs):

```python
class Finding(KnowledgeNode):
    node_type: Literal["finding"]
    finding_type: Literal["unsupported_claim", "internal_contradiction",
                          "source_reliability", "factual_error_suspected",
                          "echo_chamber", "pheromone_autobahn",
                          "confidence_inflation", "adversarial_test_outcome"]
    severity: Literal["info", "low", "medium", "high", "critical"]
    cell: Literal["athene", "chronos", "nemesis", "eris"]
    target_node_ids: list[str]
    evidence: list[str]
    sampled_at: datetime
    resolved_at: datetime | None
    resolution_action: Literal["none", "annotated", "demoted",
                                "deleted", "escalated_to_human"] | None
```

## The self-improvement loop

Mnemosyne is the heart of this loop. She does the following continuously, with budgets and audit trail:

1. **Observe.** Read findings from all cell classes, plus query/ingest/oneiros report streams, plus operator-set policy constraints.
2. **Hypothesise.** Identify candidate parameter tunings (sampling rates, prompt variants, threshold values, evaluator weighting, planner step caps).
3. **Define metric.** Decide what would count as the hypothesis being right (e.g., "increased Athene true-positive rate without raising false-positive rate above 0.05"). Mnemosyne defines this herself; the operator sees the metric definition and can veto it before A/B starts.
4. **A/B test.** Run two parameter regimes in parallel for a defined window, with traffic split per Mnemosyne's design. Both regimes write findings; both feed back to the chronicle.
5. **Compare.** Score each regime against the metric. Auto-apply the winner if the difference is statistically meaningful and within the operator's pre-set "auto-apply ceiling" (default: small parameter tweaks; off-by-default for prompt rewrites).
6. **Report.** Write the experiment, the metric, the result, and the action taken into the chronicle as a structured `MnemosyneExperiment` node. Operators audit the trail, not the per-experiment decision.
7. **Escalate.** Patterns Mnemosyne cannot fix by parameter tuning become drafts in the Phoenix Backlog. Examples: "the entity resolver fails systematically on transliterated Tibetan place names; needs a Phase-2 redesign", "the synthesizer's verdict heuristic over-weights citation count for short answers". Mnemosyne writes the draft; humans review; accepted drafts feed into the next Phoenix incarnation.

The self-improvement loop closes the gap between observation and design. Without it, the human reviewer is the bottleneck; with it, the human reviews policy and patterns rather than per-decision outcomes.

## Phoenix incarnation as the next horizon

When accumulated Mnemosyne drafts and human-curated policy changes warrant a real architectural step, the Pantheon enters a **Phoenix incarnation**: a planned generation transition (Gen 1 → Gen 2 → ...). The mechanics of incarnation are not yet decided in detail — they are the subject of Wave 4 work — but the principle is clear:

- The current chronicle's content is preserved (chronicle is data, not code)
- The agent pantheon (Athene, Chronos, Nemesis, Eris, Mnemosyne) gets new versions with refined behaviour
- The substrate code is restructured to carry the lessons Mnemosyne and humans accumulated
- Federation peers are notified of the version transition

Phoenix incarnation is currently **human-driven**: humans write the next-generation code, humans deploy it. The next horizon — explicitly part of the long-term Pantheon vision — is that **the Pantheon writes its own next version**. That horizon has its own canonical doctrine document: [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md). Read that next.

## Why this doctrine cannot be partially adopted

It is tempting to think "we keep the old Hestia gate but also add Athene". This does not work. The two doctrines contradict at the architectural root:

- A gate that pre-filters content shapes what Athene can ever see. She becomes a curator of the operator's blind spots, not an immune system of the chronicle. The 98% sampling target becomes meaningless.
- A gate that approves on whitelist + sometimes asks the LLM is a fragile compromise that combines the worst of both: the latency of a synchronous gate, the false confidence of a complete filter, and the gaps of an LLM judgement under pressure.
- The system's epistemic posture must be one or the other. The Chronik either trusts itself to learn from its own infections, or it pretends infections never happen and decays in front of any real adversary.

Hestia in the W7-B / W12 form is therefore being removed entirely. Hestia as a Pantheon agent **role** is not removed; her real long-term role (described in [`HESTIA.md`](HESTIA.md) — drift monitoring, escalation, regulatory dial) is **post-hoc**, observational, and aligned with this doctrine. That work is in PHX-0039 (full Hestia) and is a peer of Mnemosyne in the consciousness layer.

## Implementation roadmap (Wave 3 reference)

The Living Demo Plan ([`docs/plans/LIVING_DEMO_PLAN.md`](plans/LIVING_DEMO_PLAN.md)) carries the per-sprint detail. Summary:

- **W13** — pre-gate removal: HestiaLite and HestiaSentinel deleted; ingest paths route directly into the verification pool; cockpit vocabulary updated to make the immune-system flow visible (`acquired_into_pool` instead of `hestia_review`).
- **W14** — verification pool + Athene v0.1 (T-helper).
- **W15** — Chronos v0.1 (T-killer).
- **W16** — Nemesis (antibody memory) + Eris (adaptive immunity).
- **W17** — Mnemosyne as the consciousness conductor (A/B tests + PHX-Backlog draft writer).
- **PHX-Run / Wave 4** — first Phoenix incarnation. Self-modification doctrine ([`SELF_MODIFICATION.md`](SELF_MODIFICATION.md)) governs.

## Final note

The clinic doctrine asked the Chronik to be perfectly clean. The immune-system doctrine asks it to be alive. Live systems are noisy; their resilience is in how they handle the noise, not in suppressing it. Pantheon was always meant to be the second kind of system. This doc closes the gap between what was designed and what was being built.
