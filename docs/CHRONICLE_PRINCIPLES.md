# Chronicle Principles

**Purpose:** Non-negotiables distilled from the Pantheon north star. Use this when another doc needs doctrine without repeating the full manifesto — see [`PANTHEON_VISION.md`](PANTHEON_VISION.md).

**Terminology:** *Pantheon* here means the **planetary chronicle / knowledge substrate** (long horizon), not the mythological agent roles (Argus, Athene, …). See [`GLOSSARY.md`](GLOSSARY.md).

---

## The Founding Principle — Language is the Edge, Not the Substrate

**Sprache ist der Rand, nicht das Substrat.**

Bedeutung existiert vor Sprache. Ein Mensch versteht die Stimmung im Raum, bevor er Worte dafür hat. Ein Mathematiker sieht eine Struktur, bevor er sie benennen kann. Ein Musiker hört eine Harmonie, die er nicht vollständig übersetzen kann. Bedeutung ist keine Funktion von Sprache — Sprache ist eine mögliche Ausgabe von Bedeutung.

Wittgensteins Satz — "Die Grenzen meiner Sprache sind die Grenzen meiner Welt" — beschreibt eine Beobachtung, keine Wahrheit. Er hat das Ausgabemedium für das Denkmedium gehalten.

Die Chronik ist kein Textarchiv mit Vektoren als Index. Die Chronik ist ein **semantischer Raum**, in dem Bedeutung ohne Sprache existiert, sich bewegt, verdichtet und verändert. Sprache betritt diesen Raum nur an zwei Punkten:

- **Am Eingang:** Argus bringt Text. Kadmos übersetzt ihn in Vektoren und Kanten. Danach existiert kein Text mehr im System.
- **Am Ausgang:** Iris aktiviert einen Subgraphen und formuliert daraus Sprache für einen Menschen. Das ist Ausgabe, kein Abruf. Iris liest keinen gespeicherten Text — sie erzeugt Sprache aus Bedeutung.

Alles zwischen Kadmos und Iris — Nous, Chronik, Oneiros, Kalypso — operiert ohne Sprache. Das ist keine Einschränkung. Das ist der Kern.

**Das Gegenmodell ist RAG.** RAG speichert Textstellen und gibt sie zurück. Die Chronik speichert Bedeutung und erzeugt Sprache. Wenn Text als Payload gespeichert oder zwischen Agenten übertragen wird, ist es RAG. Wenn nur Vektoren und Kanten fließen, ist es Chronik. Jeder Agent, der Text als internes Kommunikationsmedium verwendet, verstößt gegen dieses Prinzip.

---

## The Ten Non-Negotiables

1. **Chronicle over encyclopedia** — Preserve reality in motion: disputes, weak evidence, supersession, and strategic relevance; do not flatten to a single settled summary.

2. **Provenance-first** — Every meaningful claim must carry origin, basis, and revision path; opaque insertion is unacceptable.

3. **Native identity over time** — Pantheon-native identity is primary; Wikidata Q-IDs and other external ids are bootstrap links and compatibility anchors, not the eternal center of gravity.

4. **Contradiction is first-class** — Conflict, uncertainty, and competing interpretations stay legible; premature collapse is a failure mode.

5. **Governance in the data model** — Access, authority, trust, review, and responsibility are machine-legible, not only informal policy.

6. **Privacy as operational necessity** — Governed visibility and data sovereignty are required for adoption and law *now*, even if long-term realism about superhuman capability stays skeptical of policy-only guarantees.

7. **Rebuildability over mystique** — The chronicle must be inspectable, portable, and partially reconstructible; if it cannot be rebuilt, it cannot be trusted.

8. **Trails strengthen the graph; Slow-Path may walk against them** — Attention leaves durable edge-level signals (`pheromone_delta`); deliberate Slow-Path retrieval may use `invert` to read without reinforcing those trails (see [`PHEROMONE.md`](PHEROMONE.md)).

9. **The chronicle is allowed to dream; the dream is allowed to be wrong; the dream is never elevated without verification.** — Morpheus may propose low-confidence `INFERENCE` edges; promotion to trusted knowledge still flows through evidence and (eventually) Athene-style review. **This applies to ingestion too, not only to inference:** raw extraction may produce imperfect, contradictory, or low-confidence assertions; that is the design, not a defect. Pre-validation gates are forbidden. Truth emerges post-hoc through mass, consolidation, and the immune system — see [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md) for the binding statement of the current Function-First Phase.

10. **AI-Native Communication (Vector-Vector-Mesh)** — The substrate is built by AI agents, for AI agents. It abandons human-readable text as the primary retrieval interface in favor of Latent Space Communication. Agents inject vectors, and the mesh responds via Spreading Activation over a hyper-dense Tensor-Manifold. Text generation is a final-mile translation for humans, not the core operating language of the system. Labels and text attributes on nodes are debugging infrastructure for humans and the immune system — not knowledge, not retrieval primitives, not inter-agent communication.
