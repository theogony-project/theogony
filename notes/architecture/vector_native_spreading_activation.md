# Konzept: Vector-Native Spreading Activation im Theogony Mesh

> **Status: historischer Kontext (überholt).** Dieser frühe MVP-Entwurf hat den Geist der Substrate-Architektur richtig erfasst (LanceDB + PyTorch CSR, Spreading Activation als SpMV, Latent Space Injection statt Text-RAG), ist aber durch die MESH-Triplet — [`docs/MESH_SUBSTRATE.md`](../../docs/MESH_SUBSTRATE.md), [`docs/MESH_IMPLEMENTATION.md`](../../docs/MESH_IMPLEMENTATION.md), [`docs/MESH_RETRIEVAL.md`](../../docs/MESH_RETRIEVAL.md) — in jeder Hinsicht ersetzt. Die Triplet spezifiziert Knoten-Anatomie (zwei Tiers, mehrere Vektoren pro Knoten, eager identity), Kanten-Anatomie (quantitativer Kern + optionale semantische Deskriptoren), die vollständige Dynamik (super-linearer Decay, Sättigung, Atrophie, Renormalisierung, Splits), Pathologie und Therapie, und die Retrieval-Disziplin (Diversified Injection, Frame Routing, Three-Factor RL) — alles, was in dieser Notiz nur skizzenhaft angedeutet wird. Wo dieses Dokument und die MESH-Triplet differieren, ist die MESH-Triplet operativ. Diese Notiz bleibt erhalten als historischer Beleg für den frühen Entwurf, nicht als Implementierungs-Vorlage.

**Dokument-Status:** MVP-Entwurf (Function-First Phase) — überholt durch die MESH-Triplet
**Kontext:** Implementierung einer reinen Vektorsprache und kognitiven "Spreading Activation" für das Theogony-Wissenssubstrat. Gemäß `BUILD_DOCTRINE.md` liegt der Fokus auf Geschwindigkeit, Machbarkeit und autonomem Wachstum ohne menschliche Prä-Validierung.

Das Theogony-Mesh verabschiedet sich von Text als primärem Kommunikationsmedium zwischen KI-Agenten. Stattdessen operiert das Substrat als **Tensor-Manifold**, in dem sowohl Knoten (Nodes) als auch Kanten (Synapsen) als hochdimensionale Vektoren existieren. Die Informationsabfrage erfolgt nicht über strukturierte Query-Sprachen (wie Cypher oder SQL), sondern über kognitive Aktivierungsausbreitung (Spreading Activation).

---

## 1. Vektor-Injektion: Der Kommunikations-Einstieg

Wie "injiziert" ein LLM einen Gedanken in das Mesh, ohne den Umweg über natürliche Sprache zu gehen?

*   **Der Stimulus (Injection Vector):** Anstatt einen Text-Prompt (`"Wer war Einstein?"`) an eine Retrieval-Pipeline zu senden, übermittelt der Agenten-Prozess direkt seinen internen Zustand. Dies ist idealerweise die **temporär ausgerichtete Sequenz der Hidden States der letzten Schichten (Last-Layer Hidden States)** der Transformer-Architektur.
*   **Fallback für das MVP:** Da kommerzielle APIs (wie OpenAI) den direkten Zugriff auf Hidden States oft blockieren, nutzt das MVP einen dedizierten, lokal laufenden Embedding-Proxy (z.B. ein schnelles `all-MiniLM-L6-v2` oder Nomic-Embed-Text Modell). Der Agent schickt seinen rohen "Gedanken-Kontext", welcher unmittelbar in einen dichten Vektor (den Stimulus-Vektor $S_0$) umgewandelt und in das Mesh injiziert wird. Langfristig (mit offenen Modellen wie Llama 3) wird der Token-Schritt komplett übersprungen ("Latent-Space Communication").
*   **Format:** Ein hochdimensionaler Float32- oder Bfloat16-Tensor, der die aktuelle intentionale Ausrichtung des Agenten repräsentiert.

---

## 2. Der Spreading Activation Algorithmus

Sobald der Stimulus-Vektor $S_0$ im System ankommt, beginnt die Energie-Ausbreitung (Spreading Activation) durch das Vektor-Geflecht, inspiriert von der ACT-R Kognitionsarchitektur.

### Der Ablauf (Schritt-für-Schritt):
1.  **Initiale Zündung:** Der Stimulus-Vektor $S_0$ wird mit initialer Energie $E_{start}$ (z.B. $E=1.0$) versehen. Das System führt eine schnelle Approximate Nearest Neighbor (ANN) Suche im Vektorraum aus, um die $k$ semantisch ähnlichsten Einstiegsknoten zu finden. Diese Knoten erhalten die Startenergie.
2.  **Kanten-Evaluierung (Tensor-Matrix-Multiplikation):** Von den aktivierten Knoten aus breitet sich die Energie über die Kanten (die selbst Vektoren sind!) aus. Das System berechnet das Kanten-Gewicht dynamisch. Das Gewicht $W$ einer Kante zu einem Nachbarknoten wird bestimmt durch:
    *   **Semantische Relevanz:** Cosine Similarity zwischen dem Stimulus $S_0$ und dem Kanten-Vektor sowie dem Zielknoten-Vektor.
    *   **Hebbiansches Lernen (Reactivation Frequency):** Häufig genutzte Kanten haben einen "gestärkten" Multiplikator.
3.  **Energie-Weitergabe:** Die Energie des Zielknotens $E_{ziel}$ berechnet sich als:
    $E_{ziel} = (E_{quelle} \times W) - D$
    (Wobei $D$ ein konstanter Dämpfungsfaktor (Decay) pro Hop ist).
4.  **Abbruchkriterium (Stop Condition):** Die Ausbreitung stoppt auf einem Pfad, wenn die Energie $E$ eines Knotens unter einen systemweiten Schwellenwert (Threshold $T_{min}$) fällt oder eine maximale Hop-Distanz (z.B. 3 Hops) erreicht ist, um Endlosschleifen (Context Exhaustion) zu verhindern.

Durch die "Lateral Inhibition" (seitliche Hemmung) werden hochrelevante Pfade gestärkt, während irrelevante, rauschende Pfade durch den Decay $D$ schnell absterben.

---

## 3. Die "Constellation" (Das Ergebnis für das LLM)

Anstatt dem LLM eine flache Liste von Text-Chunks zurückzugeben, liefert das Mesh eine **"Constellation"**.

*   **Das Format:** Eine Constellation ist ein stark verbundener, lokalisierter Subgraph von Vektoren (Knoten und Kanten), deren Aktivierungsenergie den Schwellenwert überschritten hat. Rein technisch ist dies eine aggregierte Tensor-Matrix.
*   **Verarbeitung durch das LLM:** Die Constellation wird dem empfangenden LLM direkt in den Latent Space "injiziert" (Latent Space Injection). Bei quelloffenen Modellen wird diese Vektor-Matrix als **Soft Prompts** oder direkt in den KV-Cache (Key-Value Cache) geladen. Das LLM "weiß" dadurch plötzlich den Kontext, ohne ihn als Text lesen zu müssen.
*   **Vorteil:** Das Problem der "Context Isolation" herkömmlicher RAG-Systeme wird gelöst. Das LLM erhält nicht nur isolierte Fakten, sondern die exakten mathematischen Beziehungsvektoren (Kausalität, Widersprüche) direkt in sein neuronales Netzwerk eingespeist.

---

## 4. Speichertechnologie für das MVP

Herkömmliche Graphdatenbanken (GDBs) mit Pointer-Chasing brechen unter der Last von Millionen Vektor-Kanten zusammen. Das Mesh benötigt eine Technologie, die Graphen als **kontinuierliche Tensor-Arrays** behandelt.

**Der MVP-Tech-Stack:**
1.  **LanceDB (Columnar Vector Store):** Dient als persistente, Append-Only Speicherschicht. Es speichert Knoten und Kanten (Synapsen) als First-Class Citizens im Vektorraum. Es unterstützt von Haus aus Versionierung (Time Travel), was dem Theogony-Prinzip der immutablen Provenienz entspricht.
2.  **PyTorch Tensor Computation Runtime (TCR):** Für die eigentliche Spreading Activation zur Laufzeit wird der Graph in den GPU-Speicher (VRAM) als **Compressed Unique Source (CUS)** oder **Compressed Sparse Row (CSR)** Tensor geladen.
3.  **Ablauf:** Die Ausbreitung der Energie ist keine iterative "for-Schleife" über Knoten, sondern eine massiv parallelisierte Matrix-Multiplikation in PyTorch. Eine Energie-Ausbreitung über 100.000 Kanten geschieht so durch eine einzige GPU-Instruktion in Millisekunden.
4.  **Keine ACID-Transaktionen:** Um die Ingest-Geschwindigkeit für Agenten zu maximieren, gibt es keine klassischen Updates oder Locks. Wird ein Fakt korrigiert, schreibt das System einen neuen Vektor und eine "Supersedes"-Kante (Append-Only Ledger).

---

## Fazit für die Implementierung

Dieses Design trennt Text endgültig von der Maschinen-Kommunikation. Text existiert nur am Rand (beim initialen Ingest von Wikipedia oder bei der Ausgabe für einen menschlichen Operator). Im Zentrum kommunizieren Agenten durch Vektor-Matrizen und Spreading Activation über LanceDB/PyTorch – ein Design, das extreme Dichte (1000x Kanten vs. Knoten) und Millisekunden-Retrieval nativ vereint.