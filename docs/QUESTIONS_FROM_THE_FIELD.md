# Questions From The Field

This document records **real questions** asked of Pantheon by users
or agents that revealed something the chronicle does not yet know
or whose answer has architectural implications for the chronicle
itself.

It is the **manual precursor** of [PHX-0071 — Mnemosyne](../phoenix-backlog/PHX-0071.yaml):
once Mnemosyne is implemented she will populate a structured
equivalent of this file automatically. Until then, questions
worth recording land here by hand, and a human (or, eventually,
Mnemosyne) reviews them periodically and decides whether each
one motivates a Phoenix Backlog ticket.

Each entry follows the same shape:

- **When** the question arrived (date + Composer-conversation marker
  if applicable).
- **Who** asked (human, agent, hosted-MCP user).
- **Question** verbatim.
- **Why it matters** for the chronicle's architecture.
- **Outcome**: which PHX (existing or new) the question motivates.

Order is most-recent first.

---

## 2026-04-22 — Heterogeneous embedding dimensions across modalities

**Asker**: human (Jakob), via Composer conversation.

**Question** (verbatim):

> Sind die Vektordimensionen für alle Daten gleich? Würde es Sinn
> machen, für bestimmte Datentypen andere Vektordimensionen zu
> verwenden? Zum Beispiel für normalen Text unser klassisches
> Embedding und für genetischen Code ein anderes Embedding mit
> anderer Dimensionalität und vielleicht für Code wieder ein
> anderes Embedding? Ließe sich das alles in einer einzigen
> Vektordatenbank halten und wie würde der Zugriff auf diese Daten
> aussehen? Und ließen sich diese Daten verknüpfen?

**Why it matters**:

The Chronik today holds one 384-dim embedding per node from
BAAI/bge-small-en-v1.5. That is the right Gen-1 choice and it is
also wrong for the long horizon. Different data modalities have
structurally different optimal embedding geometries:

- Text: 384–1024 dim (BGE, MiniLM, mxbai)
- Code: 768–1024 dim (CodeBERT, jina-code, voyage-code-3)
- Protein: 320–2560 dim (ESM-2, several sizes)
- DNA: 768 dim (DNA-BERT-2)
- Image: 512–768 dim (CLIP, SigLIP, DINOv2)
- Audio: 768 dim (Wav2Vec2, Whisper-encoder)

Padding everything to a common dimension destroys the cosine
geometry. Forcing all modalities through a common projection
space (CLIP-style) is lossy and brittle. The honest architecture
is **multiple embedding spaces inside one chronicle, with
first-class cross-modal links**.

The architectural answer fits Pantheon's existing primitives
almost without modification:

- Add `KnowledgeNode.modality: str = "text"` (default-compatible).
- One Neo4j vector index per (modality, dim) tuple — supported
  natively since Neo4j 5.18 (2024).
- `RetrievalStrategy` (F3) gains an optional `modality_scope`
  on `RetrievalBudget`; default None means fan-out.
- Cross-modal links use the existing `KnowledgeEdge.relation_type`
  with strings like `"DESCRIBES_CODE"`, `"EXPRESSES_PROTEIN"`,
  `"ILLUSTRATES_CONCEPT"`. No edge schema change.
- Cross-modal vector similarity ships in three ranked options:
  edge-driven (Phase 1), bridge embedding (Phase-2 sub-ticket),
  LLM bridge (Phase-2 sub-ticket).

**Outcome**:

Promoted [PHX-0002 — Hierarchical + Heterogeneous Embedding Spaces](../phoenix-backlog/PHX-0002.yaml)
from catalogue-only to a full YAML ticket on 2026-04-22, with
this question cited as the originating evidence. PHX-0002 now
covers both the original abstraction-level pressure and this
modality pressure in one parent ticket; Phase-2 sub-tickets will
schedule the actual implementation work.

This question is also a textbook example of the kind of
**self-referential** query [PHX-0071 — Mnemosyne](../phoenix-backlog/PHX-0071.yaml)
will catch automatically once she is implemented. It is recorded
here manually so the pattern is visible from day one.

---

## How to add an entry

Until Mnemosyne is live:

1. Identify a question that meets at least one of:
   - The Chronik returned a verdict of `partial` or `failed` on
     it AND the topic is structural to the chronicle.
   - The question is *about* the chronicle (its schema, its
     embedding spaces, its workers, its lifecycle).
   - The question reveals a missing PHX.
2. Append a new section above the most-recent entry, following
   the shape of the example above.
3. If the question motivates a new PHX, file the YAML in
   `phoenix-backlog/` and link it bidirectionally (this file
   in the PHX's `referenced_in:`, the PHX in this file's
   "Outcome:").
4. Commit with a `docs(questions)` prefix so the history is
   easy to grep.

With Mnemosyne Phase 1 live (PHX-0071), every query is classified
automatically; keep this manual path for **high-signal** questions the
heuristic might miss (then promote keywords or tune the LLM-fallback
budget rather than letting the signal disappear). Phase 2's structured
`BacklogProposal` pipeline will further automate promotion from clusters;
this file remains the historical seed and onboarding read.
