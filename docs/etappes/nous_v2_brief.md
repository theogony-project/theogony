# Nous — Architekturbeschreibung: Kognitives Lesen

**Filed by:** Hesiod (architect)  
**Date:** 2026-05-08  
**Status:** Architekturbeschluss — bereit für Implementierungsplanung  
**Supersedes:** `docs/etappes/nous_hesiod_brief.md` (was als "Nous v1" bezeichnet wurde, ist jetzt **Kadmos** — die Translationsschicht)  
**Nomenklatur-Entscheidung:** Das frühere "Nous v1" wird umbenannt in **Kadmos**
(Text-Translationsschicht). **Nous** bezeichnet ab jetzt ausschließlich die kognitive
Syntheseschicht — den Webmeister, der aus Kadmos-Output durch Verstehen und
Revision ein gefaltetes Wissensnetz erzeugt.

**Verdict über Kadmos v1 als Nous:** Kadmos hat seinen Job gemacht — er hat
bewiesen, dass JSON-Extraktion die 1000:1-Edge-Ratio nicht erreicht und den
Leseprozess nicht modelliert. Kadmos *als Translationsschicht* bleibt nützlich.
Nous *als kognitiver Syntheselayer* wird hiermit neu definiert.

---

## 0. Das Leitbild

Wenn ein Mensch einen Text liest, passiert kein Batch-Processing. Es passiert
etwas Kontinuierliches: Konzepte entstehen, aktivieren Vorwissen, kondensieren
zu Synthesen, werden revidiert, wenn späterer Text den Kontext verändert.
Das Ergebnis ist kein Extrakt — es ist ein **Verständnis**, das sich während
des Lesens aufbaut und umbaut.

Nous v2 modelliert genau das. Das LLM ist nicht Extraktor, sondern **Interpret
mit Arbeitsgedächtnis**. Das Netz, das entsteht, ist kein Nebenprodukt —
es ist das Lesen selbst, materialisiert.

---

## 1. Was Kadmos v1 als Nous falsch gemacht hat

Drei strukturelle Fehler, die erklären warum die frühere Implementierung
als *kognitiver Syntheselayer* gescheitert ist — und warum Kadmos als
*Translationsschicht* dennoch seinen Platz hat:

**Fehler 1 — LLM als Extraktor.** v1 hat das LLM gefragt: "Extrahiere mir
Entities und Relations aus diesem Paragraph." Das ist NLP-Pipeline-Denken.
Das LLM versteht keinen Text, wenn es ihn als Datenquelle behandelt — es
versteht ihn, wenn es ihn *liest*, im Kontext dessen was davor kam.

**Fehler 2 — Kein aktives Arbeitsgedächtnis.** v1 hat den LLM-Calls das
bisherige Verständnis nicht als Kontext gegeben. Jeder Paragraph wurde
isoliert verarbeitet. Das ist das Äquivalent von jedem Satz einzeln zu lesen
und danach das Buch zuzuklappen.

**Fehler 3 — Falsches Substrat.** Neo4j ist eine Pointer-Chasing-Datenbank.
Sie kann keine Tensor-Operationen ausführen, keine Spreading Activation,
keine massenhafte implizite Vernetzung. Die Zielarchitektur ist
LanceDB + PyTorch.

---

## 2. Das kognitive Modell (Grundlage)

Quelle: `notes/architecture/reading_agent_vision.md` — direkt vom Nutzer
beschrieben.

**Satzebene:** Ein Satz bringt 5–10 neue Konzepte. Gleichzeitig aktiviert
er massiv parallel ~50 Vorwissens-Konzepte im Langzeitgedächtnis —
nicht sequentiell, sondern wie ein Gewitter mit Potentialgefälle. Aus
diesem Aktivierungssturm **kondensiert eine Synthese**. Diese Synthese
ist das, was primär in den nächsten Satz mitgenommen wird.

**Absatzebene:** Satzsynthesen kondensieren zu Absatzsynthesen. Die
Absatzsynthese ist nicht die Summe der Sätze — sie ist das Destillat,
das entsteht, wenn der Leser das Gelesene zu einem kohärenten
Zwischenverständnis verdichtet.

**Kapitel- und Artikelebene:** Absatzsynthesen kondensieren weiter. Die
Hierarchie ist **emergent, nicht vorgegeben**: sie entsteht aus dem Lesen
selbst, nicht aus einer strukturellen Vorgabe.

**Revision:** Wenn ein späterer Abschnitt etwas erscheinen lässt, das
ein früheres Konzept in ein neues Licht rückt, geht der Leser zurück —
nicht im Text, sondern im Verständnis. Er revidiert die Synthese, die
das frühere Konzept enthält. Das ist kein Fehler, das ist Normalzustand.

**Parallelsuche:** Während der Leser liest, laufen im Hintergrund zwei
Suchprozesse parallel und billig:
- Ähnlichkeitssuche: welche Konzepte im Langzeitgedächtnis liegen nah
  an dem, was gerade gelesen wird?
- Kantentraversal: von aktiven Konzepten aus vertikal hochgehen zu
  Synthesen, dann diagonal oder horizontal in andere Äste —
  was liegt da?

Diese Suchprozesse liefern **Kandidaten**. Das LLM urteilt, ob eine
vermutete Nähe tatsächlich eine Verbindung ist.

---

## 3. Die drei Komponenten von Nous v2

### 3.1 Das Arbeitsgedächtnis (ReadingState)

Das Arbeitsgedächtnis ist der Kern. Es ist kein Protokoll und kein
Datenbankschema — es ist der lebendige Zustand des Lesers während der Lektüre.

Es enthält:

**Aktive Konzepte** — eine Menge von Konzepten, die gerade "warm" sind.
Jedes Konzept hat:
- Ein **Label** (menschenlesbar, LLM-vergeben)
- Ein **Embedding** (384-dim, lokal berechnet)
- Ein **Aktivierungsgewicht** (float 0–1, zerfällt über Zeit/Schritte)
- Eine **Revisions-Geschichte** (Liste von Änderungen mit Schritt-Referenz)
- Eine **Quellanker-Referenz** (welcher Abschnitt hat dieses Konzept
  erstmals eingeführt)

**Aktive Verbindungen** — Kanten zwischen aktiven Konzepten. Jede
Verbindung hat:
- Quell- und Ziel-Konzept-ID
- Einen **Verbindungstyp** (LLM-vergeben, frei formulierbar —
  nicht aus einem Codebook)
- Ein **Verständnis-Gewicht** (wie stark sieht das LLM diese Verbindung?)
- Eine **Begründung** (ein Satz des LLM, warum diese Verbindung besteht)
- Eine Revisions-Geschichte

**Synthesen** — kondensierte Verständnis-Knoten auf einer höheren
Abstraktionsebene. Eine Synthese fasst mehrere Konzepte zusammen.
Sie hat ein Embedding, das der LLM durch seinen Output implizit
definiert (indem er sie beschreibt), und das dann lokal berechnet wird.

**Offene Fragen / Spannungen** — Konzepte oder Verbindungen, bei denen
das LLM Unsicherheit signalisiert hat. Diese werden dem nächsten
Schritt explizit mitgegeben.

Das Arbeitsgedächtnis hat eine **Kapazitätsgrenze** (ca. 30–50 aktive
Konzepte). Wenn es voll ist, werden die am schwächsten aktivierten
Konzepte **komprimiert** — sie werden zu einer Synthese zusammengefasst
und aus dem aktiven Satz entfernt. Das entspricht dem menschlichen
"Vergessen" von Details bei gleichzeitigem Behalten des Verstehens.

### 3.2 Der Leseakt (ReadingStep)

Bei jedem Schritt — einem Satz, einem Absatz, einem Kapitelende;
die Granularität entscheidet das System dynamisch — passiert folgendes:

**Schritt A: Hypothesen-Generierung (parallel, billig, kein LLM)**

Zwei Prozesse laufen gleichzeitig:

1. **Ähnlichkeitssuche** über das bestehende lokale Netz (und später
   über die Chronik): die Embeddings der aktuell aktiven Konzepte werden
   als Query-Vektoren verwendet, kNN-Suche liefert Kandidaten-Konzepte,
   die semantisch nah liegen. Diese werden dem LLM als "vermutete Nähe"
   präsentiert.

2. **Kantentraversal** im lokalen Netz: von aktiven Konzepten aus wird
   das Netz traversiert — vertikal zu höheren Synthesen, dann diagonal
   oder horizontal in andere Äste. Da die Hierarchie fuzzy ist, gibt es
   keine scharfen Level: ein Konzept kann direkt mit einer Artikel-Synthese
   verbunden sein, ohne den Weg über Absatz- und Kapitel-Synthesen zu gehen.
   Die Traversal-Ergebnisse werden ebenfalls dem LLM als Kandidaten gegeben.

Beide Prozesse liefern **keine Fakten**, sondern **Hypothesen**:
"Vielleicht hängt das zusammen." Das LLM urteilt.

**Schritt B: LLM-Leseakt (der eigentliche Leseschritt)**

Der LLM bekommt:

```
SYSTEM: Du bist ein Leser mit Arbeitsgedächtnis. Du liest einen Text
Abschnitt für Abschnitt. Bei jedem Schritt sagst du, was sich in
deinem Verständnis ändert.

USER: {
  "current_reading": "<Abschnitt-Text>",
  "current_understanding": {
    "active_concepts": [...],   // kompakte Darstellung der warmen Konzepte
    "active_connections": [...], // wichtigste aktive Verbindungen
    "open_tensions": [...],      // was noch unklar ist
    "recent_syntheses": [...]    // letzte Verdichtungen
  },
  "hypotheses": {
    "similarity_candidates": [...], // aus Schritt A
    "traversal_candidates": [...]   // aus Schritt A
  }
}
```

Der LLM antwortet nicht mit "extrahierten Entities". Er antwortet mit
einem **Verständnis-Update**:

```json
{
  "new_concepts": [...],           // was neu dazukommt
  "new_connections": [...],        // neue Verbindungen, die er sieht
  "confirmed_hypotheses": [...],   // welche Kandidaten aus Schritt A er bestätigt
  "rejected_hypotheses": [...],    // welche er verwirft, und warum
  "revisions": [...],              // was sich an bisherigem Verständnis ändert
  "synthesis": null | {...},       // wenn das LLM jetzt bereit ist zu verdichten
  "open_tensions": [...]           // was bleibt ungeklärt
}
```

**Der Schlüssel:** `revisions`. Wenn das LLM in diesem Schritt erkennt,
dass ein früheres Konzept oder eine frühere Verbindung jetzt anders zu
verstehen ist, schreibt es eine Revision. Die Revision hat eine
Begründung und eine Referenz auf den Schritt, in dem das revidierte
Konzept entstanden ist. Das Konzept im Arbeitsgedächtnis wird
entsprechend aktualisiert — mit Revisions-Provenienz.

**Schritt C: Arbeitsgedächtnis aktualisieren**

Die Antwort des LLM wird in den ReadingState geschrieben:
- Neue Konzepte werden hinzugefügt
- Neue Verbindungen werden hinzugefügt
- Revisionen werden angewendet (mit Provenienz)
- Aktivierungsgewichte werden aktualisiert (neue Konzepte auf 1.0,
  bestehende leicht erhöht wenn referenziert, alle anderen leicht
  zerfallen)
- Wenn Kapazitätsgrenze überschritten: Komprimierung

**Schritt D: Lokales Netz schreiben**

Die Konzepte und Verbindungen aus dem ReadingState werden in das
lokale Lese-Session-Netz (LanceDB) geschrieben. Noch nicht in die
globale Chronik — das ist ein separater Schritt nach dem Lesen.

### 3.3 Die Granularitäts-Entscheidung

v1 hat pro Paragraph einen LLM-Call gemacht. Das ist eine starre
Vorgabe. In v2 entscheidet das System dynamisch:

**Satz-Granularität:** Wenn ein Abschnitt viele neue Konzepte einführt
oder eine Revision auslöst, wird auf Satzebene gelesen. Mehr Calls,
aber präziseres Verständnis.

**Absatz-Granularität:** Der Normalfall für informationsdichte Absätze.

**Kapitel-Granularität (Skim):** Wenn die aktiven Konzepte des
Arbeitsgedächtnisses den Kapiteltitel bereits gut abdecken — wenn
das LLM im vorigen Schritt signalisiert hat, dass dieses Kapitel
vertrautes Terrain ist — dann kann ein Kapitel mit einem einzigen
"Skim"-Call gelesen werden. Das entspricht dem menschlichen
"Trust-and-skim".

Die Granularitätsentscheidung ist Teil des LLM-Outputs: eine Option
`"next_granularity": "sentence" | "paragraph" | "section" | "skim"`.

---

## 4. Das lokale Lese-Netz

Während des Lesens entsteht ein **lokales Netz** — nicht die globale
Chronik, sondern ein Session-spezifisches Netz, das das Verständnis
des aktuellen Artikels materialisiert.

Dieses Netz lebt in LanceDB (in-process, nicht persistent zwischen
Sessions). Es enthält:

- **Konzept-Knoten**: ein Embedding-Vektor + Label + Aktivierungsgewicht
  + Revisions-Geschichte
- **Verständnis-Kanten**: kein Codebook, kein festes Schema. Der LLM
  beschreibt die Verbindung in einem Satz. Das Embedding dieser Beschreibung
  *ist* das Kanten-Embedding.
- **Synthese-Knoten**: Abstraktionen über mehreren Konzept-Knoten.
  Ihre Position im Vektorraum ist berechnet (gewichteter Durchschnitt der
  Basis-Knoten plus dem Embedding des LLM-generierten Synthese-Labels).

Die Kanten entstehen durch **Verstehen** (LLM-Urteil), nicht durch
Ähnlichkeit. Aber die Ähnlichkeit der Kanten-Embeddings untereinander
ist das, was später Spreading Activation durch das Netz ermöglicht.

Das lokale Netz nach dem vollständigen Lesen eines Artikels ist das
**Verständnis des Artikels** — nicht ein Extrakt, sondern eine
Wissensstruktur, die zeigt wie die Konzepte zusammenhängen, auf welchen
Ebenen, mit welcher Stärke, mit welcher Revisions-Geschichte.

### 4.1 Die Dichte des Netzes

Wo kommt die 1000:1-Ratio her?

Primär durch **implizite Kanten**: nach dem Lesen, wenn alle
Konzept-Embeddings im lokalen Netz liegen, läuft ein Post-Pass:
jeder Knoten bekommt kNN-Edges zu seinen nächsten Nachbarn im
Embedding-Raum. Diese Edges tragen kein LLM-Label — sie sind reine
Vektornähe, gewichtet mit cosine similarity. Sie sind die
Materialisierung der assoziativen Verbindungen, die ein Leser hat,
ohne sie explizit formulieren zu können.

Explizite Kanten (LLM-vergeben): ~800 Knoten × ~10 Verbindungen = ~8000
Implizite Kanten (Vektornähe, k=200): ~800 Knoten × ~200 = ~160.000

Verhältnis: ~200:1. Mit Chronik-Einbettung (wo bestehende Knoten
weitere Edges einbringen): deutlich höher.

Der Unterschied zu v1: die impliziten Kanten kommen **nach** dem
LLM-gesteuerten Verständnis — sie sind Verdichtung, nicht Ersatz.

---

## 5. Revision — das Herzstück

Revision ist das, was Nous v2 von v1 grundlegend unterscheidet.

### 5.1 Wie Revision ausgelöst wird

In jedem LLM-Call prüft der LLM sein aktuelles Verständnis gegen den
neuen Abschnitt. Er kann eine Revision auslösen wenn:

- Ein früheres Konzept durch neuen Kontext falsch oder unvollständig ist
- Eine frühere Verbindung sich als irrtümlich oder umgekehrt herausstellt
- Eine frühere Synthese zu grob war und aufgebrochen werden muss

Der LLM signalisiert dies durch das `revisions`-Feld in seiner Antwort.

### 5.2 Was eine Revision enthält

```json
{
  "target_concept_id": "...",         // was wird revidiert
  "revision_type": "update" | "split" | "merge" | "invalidate",
  "reason": "...",                    // ein Satz: warum
  "triggering_passage": "...",        // der Textteil, der die Revision ausgelöst hat
  "old_understanding": "...",         // was vorher galt
  "new_understanding": "..."          // was jetzt gilt
}
```

`split`: ein Konzept wird zu zwei. `merge`: zwei werden zu einem.
`invalidate`: ein Konzept war falsch — es wird nicht gelöscht (Provenienz
bleibt erhalten), aber als invalidiert markiert.

### 5.3 Wie weit Revisionen zurückreichen

In v1: nur innerhalb des aktuellen Abschnitts. In v2: über die gesamte
Lese-Session. Das Arbeitsgedächtnis hält alle Konzepte mit ihren
Entstehungs-Schritt-Referenzen. Eine Revision kann auf Schritt 3 verweisen,
auch wenn wir gerade in Schritt 47 sind.

Die Einschränkung: das LLM sieht nur die **kompakte Darstellung** des
Arbeitsgedächtnisses, nicht den Rohtext aller bisherigen Schritte.
Es kann also nur revidieren, was im aktuellen Arbeitsgedächtnis sichtbar
ist. Was bereits komprimiert wurde (zu einer Synthese verdichtet), ist
als Synthese noch adressierbar — die Revision würde dann die Synthese
selbst betreffen, nicht ihre Basis-Konzepte einzeln.

---

## 6. Technisches Substrat

### 6.1 LanceDB als Primärspeicher

Das lokale Lese-Netz lebt in einer In-Process-LanceDB-Instanz.
Append-only, kein Locking, keine Transaktionen. Fehler-Korrekturen
werden als neue Rows mit `supersedes`-Referenz geschrieben, nie als
Update.

Nach dem Lesen: die lokale LanceDB kann in die globale Chronik
exportiert werden (separater Schritt, nicht Teil des Lesens selbst).

### 6.2 Embeddings

Jedes Konzept bekommt sofort ein Embedding — local, ohne LLM, mit
dem konfigurierten Embedding-Modell (BAAI/bge-small-en-v1.5 oder besser).
Das Embedding des Konzept-Labels ist der primäre Vektor.

Kanten-Embeddings werden aus dem Embedding der Verbindungs-Beschreibung
berechnet (der Satz, den das LLM als Begründung geliefert hat).

### 6.3 PyTorch für Spreading Activation (Post-Read)

Nach dem Lesen, wenn das lokale Netz vollständig ist, kann ein
Spreading-Activation-Pass über den Graphen laufen — als CSR-Tensor
in PyTorch, nicht als Graphdatenbank-Traversal. Das ist der Schritt,
der die impliziten kNN-Kanten materializes und das Netz auf die
gewünschte Dichte bringt.

### 6.4 KnowledgeStore-Protokoll

Nous v2 schreibt **nicht** durch das bestehende `KnowledgeStore`-Protokoll,
das auf Neo4j ausgelegt ist. Es schreibt direkt in LanceDB.

Die globale Chronik (Neo4j oder ein zukünftiger LanceDB-basierter Store)
wird nach dem Lesen als separater Export befüllt. Das entkoppelt den
Leseprozess von der Persistenz-Infrastruktur.

---

## 7. Was v2 nicht baut (Scope-Grenzen)

- **Keine globale Chronik-Integration während des Lesens.** Die
  Ähnlichkeitssuche in Schritt A läuft zunächst nur über das lokale
  Lese-Session-Netz. Chronik-Suche kommt in v3.
- **Keine Multi-Artikel-Sessions.** v2 liest einen Artikel pro Session.
- **Kein Cockpit.** Output ist JSON + AnnotatedReading + RunReport.
- **Kein Streaming.** Der Leseprozess ist synchron, ein Schritt nach
  dem anderen.
- **Kein Multi-Resolution-Modell.** Ein LLM für alle Granularitäten.

---

## 8. Was Monkey 1 in v2 bedeutet

Die Vergleichsmetrik aus dem v1-Brief bleibt gültig, aber mit anderen
Erwartungen:

| Metrik | v1 Ergebnis | v2 Ziel |
|---|---|---|
| Edge/Node-Ratio (explizit) | 1.10 | 5–15 (LLM-Verbindungen + Synthesen) |
| Edge/Node-Ratio (gesamt mit kNN) | 1.10 | 100–500 |
| Revision events | 0 | messbar > 0 |
| Synthesis-Hierarchie-Levels | 1 (alle paragraph) | 3–4 (paragraph, section, article) |
| Cross-source connections (bei Chronik-Export) | 636 | höher, durch Verstehen |

Die 1000:1-Ratio ist das Fernziel für den Chronik-Export mit kNN-Pass.
Innerhalb einer Lese-Session (explizite + implizite Kanten): 100–500:1
ist das realistische v2-Ziel.

---

## 9. Die offenen Entscheidungen für den Implementierungsplan

Diese Fragen beantwortet Hesiod im Implementierungsbrief, der auf
diesem Architekturbeschluss aufbaut:

**Q1 — Granularitäts-Initialisierung.** Mit welcher Granularität
beginnt der erste Schritt? Satz, Absatz, oder dynamisch je nach
Artikel-Länge?

**Q2 — Arbeitsgedächtnis-Komprimierung.** Wann genau wird komprimiert?
Beim Überschreiten der Kapazitätsgrenze, oder vorausschauend an
Sektionsgrenzen?

**Q3 — Hypothesen-Budget.** Wie viele Kandidaten aus Ähnlichkeitssuche
und Traversal werden dem LLM pro Schritt präsentiert? Mehr Kandidaten =
bessere Urteile, aber mehr Token-Kosten.

**Q4 — Revisions-Reichweite.** Wie weit zurück kann der LLM
revidieren? Nur aktive Konzepte, oder auch komprimierte Synthesen?

**Q5 — LanceDB-Schema.** Wie werden Konzepte, Kanten und Revisionen
in LanceDB modelliert? Separate Tabellen oder eine einheitliche
Assertions-Tabelle?

**Q6 — AnnotatedReading-Format.** Was genau enthält das
Ausgabe-JSON? Soll es den vollständigen Revisions-Graph enthalten,
oder nur die finale Lesezustand?

**Q7 — Kanten-Embedding.** Embedding des Verbindungs-Beschreibungs-Satzes
(teurer, semantisch reicher) oder Mittelwert der Quell- und Ziel-Embeddings
(billig, aber verliert den Verbindungstyp)?

---

## 10. Warum das schwer ist — und warum es richtig ist

Das Schwierige an v2: das LLM muss sich an frühere Schritte "erinnern",
ohne den Rohtext aller früheren Schritte zu bekommen (zu lang, zu teuer).
Die Lösung — eine kompakte Darstellung des Arbeitsgedächtnisses — ist
selbst ein Design-Problem. Zu kompakt: das LLM verliert Kontext und
kann nicht gut revidieren. Zu ausführlich: die Prompts werden teuer und
langsam.

Das ist das Kernproblem, das Nous v2 lösen muss. Es gibt keine fertige
Antwort darauf. Es ist empirisch: man baut, man misst, man kalibriert.
Das ist der Wert des ersten Corpus-Laufs.

Das Richtige daran: es ist das Problem, das man lösen *muss*, wenn man
ein System bauen will, das wirklich liest statt nur extrahiert. v1 hat
dieses Problem umgangen, indem es jeden Paragraph isoliert behandelt hat.
v2 stellt sich ihm.

---

*Hesiod withdraws. The architecture belongs to the implementer.*
