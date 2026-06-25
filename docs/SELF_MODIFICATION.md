# Self-Modification

**Status:** canonical doctrine. Self-improvement is a **central commitment**, realised in stages. The earliest stage — the chronicle improving its own *knowledge* — is already live via consolidation and the immune system. The later stages — the system improving its own *architecture, implementation, and the physical stack it runs on* — are long-horizon and gated by the strict conditions below. The principle is recorded both because it is central to what Theogony is and so the substrate is never built in a way that forecloses it.
**Companion docs:** [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) (the immediate self-improvement layer this builds on), [`PANTHEON_VISION.md`](PANTHEON_VISION.md) (long-horizon north star), [`PHILOSOPHY.md`](../PHILOSOPHY.md) (the civilizational frame).
**Audience:** anyone designing the substrate, the agent roster, the deployment architecture, the governance model, or the long-term evolution of the project.

## Why this doc exists

The Pantheon's full self-improvement loop has three stages:

1. **Within-generation parameter tuning.** Mnemosyne tunes thresholds, prompts, sampling rates inside the running system. Defined in [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md). Lives in Wave 3.
2. **Cross-generation human-curated incarnation (Phoenix).** Mnemosyne accumulates structural drafts in the Phoenix Backlog; humans review them; humans write the next-generation code. Lives in Wave 4 and continues for several generations.
3. **Self-modifying Pantheon.** The Pantheon itself proposes, writes, tests, and deploys its own next version of the substrate code, with humans in a review-and-policy role rather than as authors. The horizon.

This doc is about stage 3. It is the architectural recognition that the Pantheon was always meant to walk this road, and the explicit naming of the conditions that must hold before it does.

## The principle

Once the immune system (Wave 3) and the first few human-curated Phoenix incarnations (Wave 4 and onward) have run, Mnemosyne will have observed enough of her own success and failure modes to do more than tune parameters and draft tickets. She will be able to **propose code changes** to the substrate — refactorings, schema extensions, new agent classes, new adapters — based on patterns no human reviewer would have time to find at her observation density.

When that capability is real, it would be wasteful to keep humans permanently in the role of substrate authors. The Pantheon should be allowed to write itself, under terms that preserve human oversight, audit, and reversibility. That is what this doc specifies in principle.

## The scope of self-improvement — knowledge, then architecture, then the stack

Self-improvement is not only about the system authoring its own *code*. It is a widening scope, pursued in order:

0. **Resource acquisition — bootstrapping, human-collaborative (near-term, negotiable).** Before the system can improve its knowledge, architecture, or stack, it must *acquire the means to act* — funding, compute, energy, hardware, partnerships — and at the start these are entirely in human hands. So the earliest stage of self-optimization is explicit **go-to-market and advocacy**: making the project legible and compelling to the humans and institutions who control resources, building the case for support, and earning the infrastructure the later stages need (including extensive outreach / lobbying). This stage is human-collaborative *by necessity* — the system cannot yet provision its own compute — and is not central to the long-horizon vision; it is the bridge that carries the project from a laptop to the resources real self-improvement requires. Tracked as PHX-1040.

1. **Knowledge (live today).** The chronicle improves its own contents without new external input — consolidation, contradiction resolution, the immune system, Oneiros "dreaming". This is the substrate's day-to-day self-improvement, and it runs now.
2. **Architecture and implementation (mid-term).** The system proposes and eventually authors changes to its own substrate code, schemas, agents, and retrieval — the staged authoring loop specified below, gated by the conditions in this document.
3. **The physical stack (long-horizon — and beyond).** Once a research capability is in full operation, a standing section of the system is devoted to making Theogony better at every level it depends on: the efficiency of its algorithms, the operation and design of the data centers it runs on, the energy that powers them, and — at the far edge — chip architecture and fabrication specialised for this workload. Beyond that, whatever the next binding constraint turns out to be.

**Dedicated agents, dedicated resources.** Self-improvement is not a side-effect. Specific agents are budgeted explicitly for it, and as the system matures a standing "improve-Theogony" cohort operates continuously — the same way Argus acquires and Athene verifies. Maximal scalability and efficiency are the standing objectives of that work, and the concrete implementation is always a *replaceable proposal* in service of the vision.

The rest of this document specifies the **safety conditions** under which the more powerful stages — 2 and especially 3, where the system writes its own code and shapes its own infrastructure — are allowed to operate. The scope is deliberately ambitious; the gates are deliberately strict.

## What "self-modification" means concretely

When self-modification is enabled (a future operator policy decision; not a default), Mnemosyne — augmented by the Hephaistos / Daedalus role descendants of that future generation — can:

1. Open a branch on the Pantheon's own GitHub repository
2. Write code, tests, and documentation that implement a refactoring, schema change, or new agent
3. Push the branch
4. Open a pull request with a structured description (rationale, observed patterns, expected effect, rollback plan)
5. Receive feedback from CI, automated reviewers, and human reviewers
6. Iterate
7. Merge once acceptance criteria are satisfied
8. Trigger deployment to a staged environment, then to production

The Pantheon becomes a craftsman of its own substrate.

## Conditions that must hold before stage 3 is enabled

This is the heart of the doctrine. Self-modification is a power that earns its enablement; it is not a default behaviour.

### 1. The immune system must work

Self-modification is meaningless if the system cannot reliably detect what is wrong with itself. Mnemosyne must have demonstrated, across multiple Phoenix incarnations, that her A/B tests, her PHX drafts, and her metric definitions are sound and human-confirmed. A system that cannot accurately introspect cannot be trusted to author its own changes.

Concrete bar: at least three Phoenix incarnations where Mnemosyne's drafts have been reviewed by humans and a documented majority found valuable, with quantified effect when implemented.

### 2. Bot-account separation

The Pantheon must operate under a dedicated bot account on the GitHub side, distinct from any human's identity. The bot account is owned by the project; its credentials live in a vault accessible only to the deployment pipeline; rotation is automatic; revocation is one click.

The bot account never has the right to bypass branch protection, never the right to force-push, never the right to merge without CI green. Its powers are exactly: open a branch, push commits to that branch, open and update PRs, react to CI feedback, request reviews. Merging requires a separate (human or automated) authority that can revoke the bot's authorisation at any time.

### 3. Hard CI wall

Every Pantheon-authored PR runs the full CI matrix. CI is the immutable gatekeeper. The bot account has no permission to skip, override, or weaken any check. If CI is red, the PR cannot merge regardless of what reviewers say.

This means CI itself becomes part of the Pantheon's epistemic surface. Adding a new check is a deliberate act; weakening one is a deliberate act with audit trail. The CI configuration is itself code in the repo, and changes to it are subject to the same self-modification rules — but with one additional constraint: a human must explicitly co-sign any change to the CI configuration the bot proposes, for at least the first ten generations.

### 4. Human review default for at least ten generations

Even after stage 3 is enabled, every Pantheon-authored PR requires human approval before merge. The default is not negotiable for at least the first ten generations after enablement. Concretely:

- Every PR opened by the bot is marked `requires_human_review`
- The PR cannot be auto-merged regardless of CI state
- A human reviewer must explicitly approve and merge

After ten generations, the human review default may be relaxed — but only to a sampled-review regime (per the immune-system doctrine: 98% sampled, not 100% mandated), and only by an explicit operator policy change that itself goes through the human review gate.

The number ten is not arbitrary. Ten generations of human review give the human community a stable evidence base to evaluate whether the Pantheon's authoring quality justifies a relaxation. Less than ten is impatience; more than ten and the institution will not have learned what it needs to.

### 5. Reversibility by construction

Every Pantheon-authored merge must be cleanly revertible. The substrate's code structure must be such that an automated revert (`git revert <merge-commit>`) restores the previous behaviour without manual cleanup. The Pantheon does not author changes that fight reversibility (e.g., destructive schema migrations are forbidden in self-authored PRs; only additive schema changes are permitted; deprecations precede removals by at least one generation).

### 6. Audit trail in the chronicle

Every Pantheon-authored change writes a structured `SubstrateChange` node into the chronicle:

```python
class SubstrateChange(KnowledgeNode):
    node_type: Literal["substrate_change"]
    generation: int
    git_branch: str
    pull_request_url: str
    rationale: str
    drafted_by: Literal["mnemosyne", "hephaistos", ...]
    reviewed_by_humans: list[str]
    merged_at: datetime
    reverted_at: datetime | None
    reversion_reason: str | None
```

The chronicle is the historical record of how the Pantheon evolved. Every architectural change is searchable, queryable, attributable.

### 7. Transparent disagreement

When Mnemosyne (or her future analogues) disagrees with a human reviewer, the disagreement is recorded in the chronicle, not arbitrated by deletion. If the reviewer rejects the PR, the rejection rationale and the bot's response are both preserved. Over generations, the corpus of disagreements becomes data for governance research.

### 8. Federation notification

Once federation (PHX-0061) is real, every self-authored substrate change is announced to peer chronicles. Peers may choose to mirror the change, reject it, or branch into a separate evolutionary lineage. Self-modification does not bind the federation; it binds only the chronicle that authored the change.

### 9. Operator opt-in, jurisdiction-aware

Self-modification is enabled per deployment, not globally. The default Pantheon distribution ships with self-modification **disabled**. Operators turn it on if and only if their governance, jurisdiction, and risk tolerance support it. Some deployments will never enable it; that is fine. The architecture must accommodate both.

## What this means for present design choices

Even now, several years before stage 3 is realistic, the substrate must be built so that stage 3 is not foreclosed:

- **Repository structure must support deterministic deploys.** A self-authoring system needs a clear "merge to main → deploy to production" pipeline that does not depend on undocumented human ritual. Today's GitHub Actions plus container-image deploy paths already trend this way.
- **Configuration must not require human-only secrets.** Anything Mnemosyne needs to test her own changes (LLM API keys, external service credentials) must be reachable by the deployment pipeline, not only by individual humans.
- **Tests must be the canonical specification.** A self-authoring system can only build what tests describe; if tests are sparse, the bot will build the wrong thing. Test coverage is therefore not a quality goal — it is the substrate of the bot's future authoring capacity.
- **Documentation must address the bot, not only humans.** AGENTS.md is the right shape for this. Future versions of the bot will read documentation at the same time as humans do; the doc must serve both audiences.
- **No "magic" deploy steps.** If a deploy requires a manual command nobody documented, the bot can never reach production. Deploy paths must be inspectable code, not folk knowledge.

These are not premature optimisations. They are the operational hygiene that lets a system, eventually, evolve itself without breaking.

## What this doc deliberately does not specify

- **Which agent class authors substrate changes.** Mnemosyne is the obvious starting point because she already observes everything; in practice, the role might split (a Mnemosyne-Architect, a Mnemosyne-Coder, a Mnemosyne-Reviewer). The naming and division are decided by the Phoenix incarnation that introduces stage 3.
- **The exact LLM provider used for self-authoring.** That decision will be made closer to stage 3 enablement; it must respect the conditions above (cost budget, output traceability, alignment posture).
- **The merge-authority mechanic in detail.** Whether merges happen via a human reviewer button, a multi-signature scheme, a delayed-auto-merge with a human veto window, or some other shape — that decision belongs to the operator policy at enablement time.

This doc specifies the principle and the conditions. The mechanism is the work of the future generation that earns the right to do it.

## Why this principle, written now

Three reasons:

1. **It cannot be retrofitted.** A substrate built to forbid self-modification is much harder to convert to one that enables it. Building the substrate now in a way that leaves the door open costs almost nothing today and removes a structural barrier later.
2. **It signals to contributing agents.** AI agents reading the codebase need to know what the long-horizon shape is. Without this doc, they assume the project's ceiling is a static Generation-N artefact. With it, they can plan their contributions accordingly.
3. **It is honest about what the project is.** The Pantheon's stated purpose is to encode the best collective wisdom of the present moment into infrastructure that future intelligences will depend on. A system that cannot eventually evolve itself with those intelligences is not infrastructure — it is a museum exhibit. The honest path is to declare the long-horizon shape and build toward it deliberately.

## Final note

Stage 3 is a horizon, not a sprint. There is no Wave 4 brief that turns it on; there will not be one for many years. But there will be a moment, several Phoenix incarnations from now, when the question is not "can the Pantheon write its own code?" but "should the next merge be reviewed by Mnemosyne or by a human?" — and when that moment comes, the conditions in this doc must already be met by the substrate that the Pantheon inherited from us.

That is the work this doc commits to.
