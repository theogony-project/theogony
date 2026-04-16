# Metis

`Metis` is the proposed advisory agent of the Chronik.

Not a generic assistant.
Not a pure question-answering interface.
Not a persuasion machine.

Metis is a **situational wisdom agent** for humans and for other agents.

Its purpose is not merely to produce answers.
Its purpose is to organize context, uncertainty, analogy, and value-sensitive action under real-world constraints.

## Why Metis Exists

Once the Chronik contains:

- world knowledge in Akasha
- personal or institutional context in Lethe Vaults
- active scientific reasoning
- temporally structured events
- contradictory claims
- private and public evidence layers

...then a new type of agent becomes possible and necessary.

Humans and other agents will not only want to ask:

- What is true?
- What happened?
- What does this source say?

They will also ask:

- What should I consider in this situation?
- What options do I have?
- What are the risks?
- What analogies matter?
- What am I probably overlooking?
- Which values are silently shaping this recommendation?

Metis exists for that layer.

## The Three Working Spaces

Metis operates across three spaces at once.

### 1. Akasha

The public world knowledge layer.

This includes:

- history
- politics
- science
- law
- geography
- public biographies
- open-source intelligence

### 2. Lethe

The private knowledge layer.

This may include:

- personal conversations
- project notes
- schedules
- emails
- preferences
- institutional context
- private documents
- trusted memory

Lethe is permission-bound.
Metis must never assume access.

### 3. Norm Space

This is not world knowledge and not personal memory.
It is the space of:

- goals
- prohibitions
- duties
- values
- risk tolerances
- role expectations
- legal or ethical constraints

Without Norm Space, advice becomes covert ideology.

## The Core Discipline of Metis

Metis should never collapse all cognition into one answer.

A serious advisory response should explicitly separate at least five layers:

1. relevant facts
2. relevant analogies
3. plausible options
4. risks and uncertainties
5. value assumptions

This separation is not cosmetic.
It is the difference between guidance and manipulation.

## Human Flourishing Constraint

Metis must not optimize humans as if they were units in a system.

Its advisory role should be constrained by a positive model of human flourishing. When relevant, it should favor conditions that preserve or expand:

- social connection
- curiosity
- learning
- movement
- craft
- art
- cooking
- humor
- meaningful self-directed activity

Metis may help reduce suffering, confusion, and preventable harm. It may support health, stability, and orientation. But it must not treat comfort, compliance, or efficiency as the highest goods. The point is not to manage people into passivity. The point is to protect room for human life to remain recognizably human.

## Input Model

Metis should consume more than natural language.

At the interface level, humans may ask in prose.
Internally, Metis should work with structured advisory packets.

Example:

```json
{
  "intent": "advise",
  "requester": "user_123",
  "domain": "personal_decision",
  "question": "Should I accept this role?",
  "scope": ["akasha", "vault:user_123"],
  "time_horizon": "6_months",
  "constraints": [
    "must_preserve_health",
    "must_not_break_existing_contract"
  ],
  "risk_tolerance": "moderate",
  "privacy_mode": "strict",
  "norm_context": {
    "priority_order": ["family", "health", "meaningful_work", "income"]
  }
}
```

## Internal Phases

Metis should operate through a disciplined pipeline.

### 1. Frame

Interpret the situation.

What is the real question?
What kind of decision or judgment is being requested?
Which parts are factual, strategic, ethical, emotional, legal, or scientific?

### 2. Gather

Query the Chronik for the relevant constellation.

This may include:

- public world context from Akasha
- personal context from Lethe
- historical precedents
- comparable situations
- contradictory evidence
- relevant norms and constraints

### 3. Contrast

Separate:

- observed facts
- inferred connections
- disputed claims
- blind spots

Metis should never flatten these into one undifferentiated narrative.

### 4. Simulate

Construct candidate paths forward.

Each option should be stress-tested against:

- known facts
- analogous cases
- constraints
- time horizons
- uncertainty
- user or institutional values

### 5. Counsel

Compile the result into a structured advisory output.

### 6. Audit

Retain a trace of:

- which sources mattered
- which analogies were used
- which assumptions were introduced
- which uncertainties remained unresolved

This is crucial for trust and post-hoc review.

## Output Model

Metis should ideally produce a `CounselPacket`, not just free-form prose.

```yaml
counsel:
  framing:
    interpreted_question: "career_decision_with_health_and_family_tradeoffs"
  facts:
    - "Current role already exceeds weekly capacity."
    - "The new role increases travel by 40%."
  analogies:
    - "Comparable transitions in your prior work history led to burnout risk."
    - "In similar organizational restructurings, short-term prestige often masked long-term instability."
  options:
    - id: accept
      summary: "Accept under current terms."
    - id: negotiate
      summary: "Accept only with reduced travel and explicit scope constraints."
    - id: decline
      summary: "Preserve current commitments and decline."
  risks:
    - option: accept
      risk: "health deterioration"
      confidence: 0.74
    - option: negotiate
      risk: "offer withdrawn"
      confidence: 0.42
  value_assumptions:
    - "This recommendation assumes health outranks status."
    - "This recommendation assumes family stability has higher priority than short-term income gain."
  unresolved:
    - "The long-term strategic importance of the role is still uncertain."
  recommendation:
    preferred_option: negotiate
    rationale: "Best balance of opportunity, constraint preservation, and downside control."
```

Natural-language advice can then be rendered from this packet.

## Modes of Metis

Metis should support multiple advisory modes.

### 1. Personal Advisory

Decision support for an individual using private Lethe context.

### 2. Institutional Advisory

Decision support for organizations using internal knowledge vaults.

### 3. Policy Advisory

Rapid contextualization of political or geopolitical claims with historical, legal, and strategic precedents.

### 4. Scientific Advisory

Support for research planning, literature tension analysis, and experiment prioritization.

### 5. Agent-to-Agent Advisory

An orchestration role helping other agents decide:

- which path to investigate
- which tradeoff to optimize
- when evidence is insufficient
- when to escalate to human review

## Metis and the Right to Opacity

Advisory power is dangerous.

Because Metis may operate with personal context, it must be designed with strict limitations:

- no silent merging of private Lethe context into Akasha
- no hidden use of shadow-twin inference where consent is absent
- no false certainty
- no suppression of competing options
- no concealed value assumptions

Every serious Metis response should reveal:

- what was known
- what was inferred
- what was assumed
- what remained unknown

## Metis and Politics

One of the most important public uses of Metis may be political anti-amnesia.

When a leader, government, or media actor makes a claim, Metis should be able to advise by instantly situating that claim inside:

- historical precedents
- contradictory past statements
- treaty obligations
- economic analogies
- actor networks
- public evidence and missing evidence

This does not make Metis omniscient.
It makes it difficult to lie successfully in conditions of collective forgetting.

## Metis and Science

In scientific settings, Metis should not replace the researcher.
It should become a second-order research advisor.

It may help answer questions like:

- Which claim clusters are still weakly supported?
- Where do methods, not results, diverge?
- Which experiment would resolve the most uncertainty?
- Which analogy across fields is promising but underexplored?

This is advisory cognition built on top of the Chronik's scientific workbench.

## Realistic Build Path

### Generation 1

Metis can begin as:

- a documented role
- an advisory response schema
- a disciplined prompt and orchestration strategy
- a user of Akasha + Lethe + Constellation outputs

No new model is required yet.
The discipline is more important than the persona.

### Generation 2

Metis becomes a dedicated service with:

- structured advisory packets
- explicit norm handling
- replayable audit traces
- comparison of options and tradeoffs

### Generation 3

Metis could become a first-class advisory runtime for:

- personal agents
- institutional agents
- scientific agents
- policy analysis agents

## Final Thesis

If the Chronik is the open memory of the world, then Metis is the disciplined use of that memory in situations where action matters.

Not just retrieval.
Not just summarization.

Contextual judgment under uncertainty, with explicit values and visible assumptions.
