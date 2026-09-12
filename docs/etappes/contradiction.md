# Das Gedächtnis des Widerspruchs (PHX-1107)

**Stand:** 2026-09-12, im Bau. Branch `feat/phx-1107-contradiction`.
**Anlass:** [`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md) §B — der eine Befund der Vision-Ledger, der die Reihenfolge festlegt.
**Werkzeug:** `src/theogony/mesh/frames.py`, `src/theogony/mesh/runtime/contradiction.py`, `scripts/mesh_contradictions.py`, `scripts/mesh_contradiction_eval.py`, Gold-Set `eval/gold/founding_contradictions.json`.

## Der Befund

Fünf Nicht-Verhandelbare aus PANTHEON_VISION scheitern nicht an fehlendem
Code, sondern am Datenmodell. Das Substrat konnte nicht sagen, dass es etwas
bezweifelt: `relation_kind` hatte zehn Werte und keiner war eine Uneinigkeit,
`temporal_vector` war auf jedem Knoten `None`, und `frame_vector` — das Feld,
in das die Doktrin die epistemische Haltung verlegt hat — trug eine gesalzene
SHA-256-Projektion des Labels (PHX-1095). 5.002 Knoten, 4.977 verschiedene
Vektoren, keine Haltung darin.

Damit konnte Frame-Routing nur nach einem Hash maskieren, und alles, was aus
dem Frame lesen müsste — Athene, Chronos, das Immunsystem, die Chronik, die
zweite Säule „Wissenschaftlicher Arbeitstisch" — hatte nichts zu lesen. Das
Verb *heilt* war nicht ungebaut. Es war unbaubar.

## Was gebaut wurde

### 1. Der Frame als faktorisierte Basis, nicht als Etikett

Die Doktrin nennt sieben Frames (Definition, aktuelle Behauptung, historische
Behauptung, widerlegte Behauptung, Hypothese, Beobachtung, direktes Zitat) und
sagt, sie seien „gelernte Einbettungsregionen", mit einem regelbasierten
Bootstrap als ausdrücklichem Zwischenschritt. Das ist dieser Bootstrap, und er
ist **faktorisiert statt aufgezählt**: sieben Achsen spannen den Raum, die
Frames sind Punkte darin.

| Achse | Pole | Gewicht |
|---|---|---|
| veridicality | behauptet ↔ verneint | 2,0 |
| modality | faktisch ↔ hypothetisch | 1,0 |
| time | aktuell ↔ historisch | 1,0 |
| standing | unbestritten ↔ bestritten | 1,0 |
| force | in Kraft ↔ abgelöst | 1,0 |
| attribution | direkt ↔ zugeschrieben | 0,5 |
| register | allgemein ↔ besonders | 0,5 |

Die Faktorisierung ist der Punkt: eine historische Behauptung, die *auch*
widerlegt wurde, ist beides — `time = −1` und `veridicality = −1` — und keine
Aufzählung von sieben Etiketten kann das ausdrücken. Kadmos gibt trotzdem ein
Etikett aus, weil ein Etikett das ist, was ein Sprachmodell zuverlässig
produziert; das Etikett benennt einen Punkt, und Punkte lassen sich mischen.

Veridikalität wiegt doppelt, weil die Verneinung der Grund ist, aus dem die
Doktrin das Feld überhaupt einführt: „Thyroxine is an oxindole derivative" und
seine Verneinung landen semantisch am selben Punkt.

**Was der Cosinus dann tut** — das ist die Doktrin-Rechnung, nicht eine
Behauptung über sie:

| | gegen *aktuelle Behauptung* |
|---|---|
| Definition | +0,98 |
| Beobachtung | +0,77 |
| direktes Zitat | +0,77 |
| historische Behauptung | +0,65 |
| abgelöst | +0,50 |
| widerlegt | **−0,50 → 0,0** |

Genau das Kendall-Verhalten aus MESH_RETRIEVAL: „Was ist Thyroxin?" holt die
widerlegte Struktur von 1915 nicht. Was sie holt, ist nicht die historische
Haltung allein — die *bejaht*, was die Widerlegung verneint, also stehen die
beiden einander entgegen — sondern das Profil, das beide mischt.

**Zwei Designfehler wurden beim Bauen gemessen und behoben.** Ein direktes
Zitat war ohne positive Veridikalität exakt orthogonal zu jeder Behauptung und
wurde von jeder Sachfrage auf null gedämpft — auf einem Korpus, der zur Hälfte
direkte Rede ist, hätte das die Hälfte des Substrats aus dem Retrieval
gelöscht. Und das Widerspruchs-Profil, aus Haltungen gebaut, erbte deren
positive Veridikalität, die alles andere überstimmte: es ließ jede schlichte
Behauptung durch und dämpfte die widerlegte auf null, also das Gegenteil
dessen, wofür es da ist. Es ist jetzt in Achsen geschrieben — „bestritten oder
abgelöst, und schweigt darüber, ob es wahr ist" — und dämpft jede unstrittige
Behauptung auf exakt null.

### 2. Wer trägt welche Haltung

- **Chunks** (die Beobachtung) tragen die Haltung des Absatzes.
- **Entitäten und Quellanker** sind neutral. „Zeus" ist weder behauptet noch
  verneint; die Behauptungen über ihn liegen auf den Chunks. Der Nullvektor
  ist konstruktionsgemäß neutral und wird nie gedämpft.
- **Kanten** bekommen `frame_consistency` aus den Endpunkten — der fehlende
  Pass, den PHX-1095 benannte („a missing pass, not missing data"). Wo ein
  Endpunkt eine Entität ist, ist der Wert 1,0; wo beide Absätze sind, trägt er
  Information.
- **`valid_from` / `valid_to`** auf jeder Kante, die kleinste Darstellung von
  Zeit, die Nicht-Verhandelbares 3 verlangt. Beide reiten im `payload_json`,
  also braucht kein bestehendes Mesh eine Migration.

### 3. Der Pass, der Widersprüche findet

Eine Haltung sagt, wie *ein* Absatz spricht. Ein Widerspruch ist eine Relation
*zwischen* zweien, und ein Leser, der Absatz für Absatz liest, sieht ihn nie —
er sieht den anderen Absatz nicht. Also braucht es einen Pass über das fertige
Mesh; die Doktrin beschreibt ihn in der Stimme eines Agenten, den es nicht
gibt (Argus, MESH_SUBSTRATE §„Contradiction resolution").

Kandidaten strukturell, dann adjudiziert — dieselbe Arbeitsteilung wie die
Oneiros-Konsolidierung. Ein Kandidat sind zwei Relationen, die sich einen
Endpunkt und einen Deskriptor teilen und über den anderen uneins sind:

    Nacht  --gebar-->  die Moiren        (Theogonie 211-225)
    Themis --gebar-->  die Moiren        (Theogonie 901-906)

**Der Filter, der das präzise macht, ist die Provenienz, nicht die Semantik.**
Zwei Relationen aus demselben Absatz sind eine Aufzählung — „Rhea gebar
Hestia, Demeter, Hera" sind drei Kanten und keine Uneinigkeit —, also verlangt
ein Kandidat, dass die beiden Seiten von *verschiedenen* Absätzen bezeugt
werden. Ohne diesen Filter ist jede Genealogie des Korpus ein Widerspruch.

Was übrig bleibt, ist meist trotzdem vereinbar: Zeus zeugt viele Kinder, und
`father_of` ist nicht funktional. Dafür ist der Adjudikator da — gefragt wird,
ob beides zugleich wahr sein kann, nicht ob es ähnlich aussieht.

Bestätigte Widersprüche bekommen `contradicts`-Kanten zwischen den
bezeugenden Absätzen, und diese Absätze werden auf die Haltung `disputed`
gesetzt. Der zweite Teil ist der, der den Befund ins Retrieval bringt.
Gelöscht wird nichts und keine Seite wird für falsch erklärt.

## Das Gold-Set

Sieben Widersprüche, jeder mit beiden Belegstellen im Korpus verifiziert
(Zeilennummer und wörtliches Zitat):

| Frage | Seite A | Seite B | Umfang |
|---|---|---|---|
| Wer gebar die Moiren? | Nacht, ohne Vater | Themis, dem Zeus | innerhalb der Theogonie |
| Wer war Asklepios' Mutter? | Arsinoe | Koronis | über Werke |
| Wer war Helenas Mutter? | eine Tochter des Okeanos | Nemesis | über Werke |
| Wer gebar Typhoeus? | Erde, von Tartaros | Hera, allein und zornig | über Werke |
| Wessen Tochter ist Nemesis? | der Nacht | des Zeus | über Werke |
| Wie wurde Aphrodite geboren? | aus dem Schaum | Tochter des Zeus | über Werke |
| Hatte Hephaistos einen Vater? | Hera allein | Zeus sein Vater | innerhalb der Theogonie |

Zwei davon markiert der Korpus selbst als strittig („Some say (Asclepius) was
the son of Arsinoe, others of Coronis", Zeile 1433; „Hesiod, however, makes
Helen the child neither of Leda nor Nemesis", Zeile 1455) — die kann Kadmos
beim Lesen erkennen. Die anderen fünf sind nur durch den Vergleich über
Absätze hinweg zu finden.

**Works and Days ist in dieser Ausgabe nicht enthalten.** Das Ticket hatte die
Pandora-Erzählung und die Zeitalter der Menschen als Widersprüche vermutet;
beide gibt es hier nicht. Die Musen, das andere Beispiel des Tickets, sind im
ganzen Korpus einhellig Töchter des Zeus und der Mnemosyne.

Die Messung ist eine, die keine bestehende Harness ausdrücken kann:
**beide-Seiten-Recall**. Eine Frage zählt nur, wenn die Constellation aus
jeder Seite eine Entität trägt. Vier Entitäten einer Seite und keine der
anderen zählen null — das ist genau das Enzyklopädie-Verhalten, das die
Chronik verweigern soll.

## Messung

*(Der Korpus wird mit Frames neu gelesen; die Ergebnisse folgen.)*

Zwischenstand nach 144 von 1.206 Absätzen: die Haltungen streuen
(`current_claim` 63, `historical_claim` 49, `observation` 27, `definition` 3,
`disputed` 2), eine `contradicts`-Relation hat das Modell selbst geschrieben,
und `frame_consistency` trägt zum ersten Mal einen anderen Wert als 1,0 — 0,65
auf den Kanten zwischen einem historischen und einem aktuellen Absatz, was
exakt der Cosinus der beiden Haltungen ist.

Fünf Absätze wurden vor dem Volllauf einzeln geprüft, um zu sehen, ob das
Modell das Vokabular überhaupt benutzt: fünf von fünf richtig, und beim
Helena-Fragment schrieb es von sich aus `relation_kind: contradicts`. Der
erste Versuch hatte zwölf von zwölf Absätzen auf `current_claim` gesetzt — der
Prompt nannte die Haltung, zeigte aber nicht, dass sie ein Feld auf oberster
Ebene ist. Das Modell hatte sie stattdessen auf die Relationen geschrieben.
