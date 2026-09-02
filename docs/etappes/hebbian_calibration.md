# Der erste Herzschlag — α gegen λ, und was das Retrieval davon sieht

*2026-09-01. `data/mesh-founding` (94.490 Kanten, 6.208 Knoten), die 47
Gold-Fragen, `k_seeds=1`. Simulation und Live-Läufe auf Kopien; kein LLM, kein
Geld. PHX-1102.*

## Ausgangslage

Die Inventur (PHX-1100) fand, dass das Substrat nur vergessen kann: 14 Ticks
Zerfall, null gefeuerte Verstärkung, und die stärkste Hebbsche Rückschreibung
einer Abfrage 17-mal kleiner als ein Tick Zerfall auf dem Mediangewicht. Drei
Stellschrauben standen im Ticket — α anheben, λ senken, oder den Zerfall auf
**ungefeuerte** Kanten beschränken, was MESH_SUBSTRATE §2 wörtlich sagt („edges
that are *not* fired weaken") und was erst seit PHX-1101 möglich ist, weil es
vorher kein Feuersignal gab.

Das Ticket verlangte, die Wahl zu **messen** statt zu argumentieren. Hier ist die
Messung, in zwei Stufen: eine Simulation über die echten Gewichte, dann der
Live-Beweis auf dem Substrat.

## Stufe 1 — Simulation über die echte Gewichtsverteilung

`scripts/mesh_hebbian_calibration.py`. Für 24 der 47 Gold-Fragen (jede zweite)
wird einmal gegen das unveränderte Mesh abgefragt und festgehalten: welche Kanten
gefeuert haben (beide Endpunkte im Arbeitsset) und welche Paare der Hebbsche Pfad
mit welchem Produkt gutschreiben würde — roh und mit auf den Spitzenwert
normalisierter Aktivierung. Dann 20 Ticks, je eine Runde aller 24 Fragen, unter
fünf Politiken. Die Constellations sind eingefroren; das ist eine Näherung
erster Ordnung, und Stufe 2 prüft sie live.

Vorab, was die Größenordnungen sind:

    Kanten, die mindestens eine Frage feuert     16.077 von 94.490 (17 %)
    Kanten, die alle 24 Fragen feuern            0
    ein Tick Zerfall am Mediangewicht 0,3112     4,84e-3
    Hebb-Gutschrift je Kante, roh                max 5,26e-4   Median 1,82e-5
    Hebb-Gutschrift je Kante, normalisiert       max 9,38e-3   Median 6,33e-4

Selbst *normalisiert* liegt die Median-Gutschrift achtfach unter einem Tick
Zerfall. Die Größe der Gutschrift ist nicht das, was eine benutzte Kante hält.

| Politik | 10 meistgefeuerte | nie gefeuert | Median |
|---|---|---|---|
| Start | 0,594 | 0,387 | 0,311 |
| **A** ausgeliefert — roh, alles zerfällt, λ=0,05 | 0,359 | 0,270 | 0,237 |
| **B** α auf Doktrin-Skala — normalisiert, alles zerfällt | 0,363 | 0,270 | 0,237 |
| **C** Gate — roh, nur Ungefeuertes zerfällt | **0,594** | 0,270 | 0,242 |
| **D** B + C | 0,601 | 0,270 | 0,242 |
| **E** λ/10 — roh, alles zerfällt, λ=0,005 | 0,558 | **0,370** | 0,302 |

Nichts erreicht die Kappe, nichts fällt unter 0,05 — in diesem Regime keine
Pathologie.

**Das Gate ist die Schraube.** Es ist die einzige Politik, bei der die benutzten
Kanten halten, und es lässt die unbenutzten exakt so verblassen wie bisher.
α-Skalierung allein ist +0,004 wert (B gegen A), obendrauf +0,007 (D gegen C).
λ/10 verlangsamt alles und trennt nichts: die nie gefeuerten Kanten verlieren
kaum noch, und die benutzten fallen trotzdem.

Das ist auch die *doktrintreue* Antwort. Die anderen beiden tauschen eine Zahl
gegen eine andere; das Gate setzt die Regel um, die das Dokument seit dem ersten
Tag enthält und die nur deshalb nie galt, weil niemand aufschrieb, was gefeuert
hat.

## Was ausgeliefert ist

- **`decay_edges_inplace(…, fired=…)`** überspringt Kanten, die diesen Tick
  gefeuert haben. `fired_pairs()` leitet sie aus den Knoten-Firings ab (beide
  Endpunkte im selben Durchgang, beide Richtungen, weil Kanten gerichtet
  gespeichert sind) und nimmt die Hebb-Deltas dazu. Der Tick zieht jetzt **beide**
  Sidecars vor dem Zerfall ein und stellt beide wieder her, wenn der Schreibvorgang
  scheitert. `decay_gate=True` ist Default; ohne Feuer-Record verschont es nichts,
  und der Tick verhält sich exakt wie vorher — das ist getestet.
- **`append_hebbian_deltas(…, normalize=)`** und `retrieve(hebbian_normalize=)`:
  Aktivierungen vor dem Produkt auf den Spitzenwert normalisieren, also auf die
  [0,1]-Skala, für die α≈1e-2 in der Doktrin geschrieben wurde. PPR ist
  massenerhaltend über den ganzen Graphen, seine rohen Aktivierungen sind ~100×
  kleiner — dieselbe Skalen-Verwechslung, die PHX-1095 für die Schwelle 0,05
  fand. **Default aus**, gemessen marginal; Hebel mit Zahl, kein Default.
- λ bleibt 0,05.

## Stufe 2 — der Herzschlag, live

`scripts/mesh_heartbeat.py`. Die erste falsifizierbare Behauptung von *„the mesh
is alive"* als Protokoll: 24 benutzte Fragen, 23 zurückgehaltene. Recall auf
beiden messen; zehn Runden lang alle benutzten Fragen stellen (Firing wird
aufgezeichnet) und ticken; beide wieder messen. Steigt das eine, ohne dass das
andere fällt, schlägt das Herz.

**Es schlägt nicht.**

| | benutzt | voll | zurückgeh. | voll | w Median | w max | verschont |
|---|---|---|---|---|---|---|---|
| Runde 0 | 84,8 % | 18 | 82,2 % | 18 | 0,311 | 0,905 | — |
| ausgeliefert, Runde 10 | 84,8 % | 18 | 82,2 % | 18 | 0,269 | 0,616 | 0 |
| Gate, Runde 10 | 84,8 % | 18 | 82,2 % | 18 | 0,276 | **0,905** | 15.732 |

Kein einziger Gold-Treffer hat sich in zehn Ticks bewegt, in keiner Variante —
weder unter dem ausgelieferten Zerfall, der das stärkste Gewicht von 0,905 auf
0,616 drückt, noch unter dem Gate, das es exakt hält. Das Gate tut auf dem
Substrat genau, was die Simulation sagt: ~15.700 Kanten je Tick verschont, die
Spitze unverändert, der Median höher als ohne. Und das Retrieval ist dafür blind.

Dann die Wachstums-Variante — Gate *plus* Hebb auf Doktrin-Skala mit bewusst
großem α=0,1, dazu ein rangsensitives Maß (mittlerer Rang der Gold-Entitäten in
einem 200er-Arbeitsset, weil Recall@50 sich erst bewegt, wenn eine Entität die
Budgetgrenze kreuzt):

| Runde | benutzt | Rang | zurückgeh. | Rang | w Median | w max |
|---|---|---|---|---|---|---|
| 0 | 84,8 % | 27,4 | 82,2 % | 30,3 | 0,311 | 0,905 |
| 2 | 84,8 % | 27,5 | 82,2 % | 30,5 | 0,302 | **1,000** |
| 5 | 84,8 % | 26,8 | 82,2 % | 30,9 | 0,288 | 1,000 |
| 10 | 84,8 % | 27,5 | **80,0 %** | 31,0 | 0,276 | 1,000 |

Die benutzten Fragen werden nicht besser (Rang 27,4 → 27,5). Die zurückgehaltenen
werden **schlechter** — eine Frage weniger vollständig, Rang 30,3 → 31,0 — und
das stärkste Gewicht sitzt ab Runde 2 an der Kappe. Das ist keine Verbesserung
mit Nebenwirkung; das ist die Nebenwirkung ohne Verbesserung. Wachstum ohne die
Gewichtssummen-Kappe und ohne Renormalisierung — beides nicht gebaut — ist die
Hub-Pathologie, vor der die Doktrin in §3 und §6 warnt, nicht der Herzschlag.

## Warum das Retrieval blind ist

Der ausgelieferte Operator ist PPR über die **zeilennormalisierte** Adjazenz
(`propagation.py`, `build_row_normalized_adjacency`, im `ppr`-Zweig verwendet).
Er liest nicht, wie stark eine Kante ist, sondern welchen **Anteil** sie an den
Ausgangskanten ihres Knotens hat. Zerfall `w → w·(1 − λw)` ist über die Kanten
eines Knotens fast gleichförmig — bei λw zwischen 0,015 und 0,045 — und deshalb
für PPR nahezu unsichtbar. Zehn Ticks ausgelieferter Zerfall ändern die
Mitgliedschaft der Arbeitssets im Median um 4 % (Jaccard 0,963), die Reihenfolge
in 24 von 24, und die Gold-Treffer gar nicht.

Das Gate erzeugt einen *Unterschied* innerhalb eines Knotens — verschonte gegen
zerfallende Ausgangskanten — von etwa 15 % relativ nach zehn Ticks. Das
verschiebt Ränge (24/24 Reihenfolgen verändert, Jaccard-Median 1,000) und keinen
einzigen Gold-Treffer über die Budgetgrenze.

Das ist nicht das Scheitern des Gates. Es ist der Nachweis, dass die Frage
„lernt das Substrat aus Benutzung" auf diesem Instrument, bei diesem Horizont,
mit diesem Operator nicht beantwortbar ist — und dass die drei Bedingungen
benennbar sind.

## Was der Review vor dem Ausliefern fand

Zwei unabhängige Leser über den Diff, adversarial. Ein Bug, zwei Risiken, vier
Doku-Fehler — alle vor dem Merge behoben:

- **Doppeltes Verschonen nach fehlgeschlagener Knoten-Faltung.** Der Tick zieht
  die Firings jetzt *vor* dem Kanten-Schreiben ein. Scheitert danach die
  Knoten-Faltung, gingen die Durchgänge unmarkiert zurück in den Puffer — und
  verschonten beim nächsten Tick dieselben Kanten ein zweites Mal für eine
  Benutzung. Ein Puffer speiste zwei Commits ohne Vermerk, welcher ihn verbraucht
  hatte. Reproduziert, behoben (`edges_applied`-Marke, die `fired_pairs`
  überspringt), mit Test.
- **O(k²) im Feuer-Index.** Die Menge aller geordneten Paare je Durchgang kostet
  2,45 Mio. Tupel und 204 MB für 1.000 Durchgänge à 50 Knoten, 5,5 GB für 5.000 à
  100 — unabhängig von der Mesh-Größe. Jetzt ein Index Knoten → Durchgänge mit
  Schnittmengen-Test, linear in der Durchgangsgröße.
- **Wiederhergestellte Durchgänge verloren ihren Zeitstempel** und bekamen die
  Wiederherstellungszeit — `last_fired_at` wäre nach jedem fehlgeschlagenen Tick
  falsch nach vorn gewandert. Behoben, mit Test.
- Kleineres: die Wiederherstellung schreibt die Firings *vor* den Deltas zurück
  (ein Anhang statt einer Schleife, die bei voller Platte mittendrin sterben
  kann); ein Delta mit Gewicht ≤ 0 zählt nicht mehr als Feuer; `mesh tick` hat
  `--no-decay-gate` und sagt in `--decay-lambda` nicht mehr „every edge";
  der Modul-Docstring von `retrieve` behauptet nicht mehr „read-only by default";
  „~100× kleiner" war die Rang-50-Spitze, nicht der Peak (~0,2).

Und eines, das nichts mit dem Gate zu tun hatte und trotzdem den PR aufhielt:
der erste CI-Lauf fiel mit 40 Tests durch, weil CI lancedb 0.38 auflöst, dessen
SQL-Dialekt `id = "…"` als Bezeichner liest. Zehn Filter im Store waren so
gebaut. Lokal reproduziert, mit einem dialekt-festen Helfer behoben, festgenagelt
(PHX-1105).

Bestätigt: ohne Feuer-Record ist das Gate byte-genau der alte Tick; beide
Orientierungen und alle parallelen typisierten Relationen eines Paars werden
zusammen verschont; die Simulation spiegelt die Tick-Arithmetik; jede Flagge der
beiden Skripte wird gelesen.

## Was jetzt stimmt, und was nicht

**Vorher** konnte das Substrat nur vergessen. **Jetzt hält es, was es benutzt** —
gemessen, doktrintreu, ohne Nebenwirkung auf das Ungenutzte. Das ist eine echte
Änderung des Substrats, und sie ist ausgeliefert.

**Was weiter nicht stimmt:** *„answers better on what it was used for."* Recall
ist über zehn Ticks jeder Politik invariant. Das Verb *lernt* aus dem Satz
„the mesh is alive" ist damit von *nein* zu *hält* gewandert, nicht zu *ja*.

Was den Herzschlag sichtbar machen würde, jeweils mit Grund:

1. **Ein längerer Horizont.** 15 % relativer Unterschied nach 10 Ticks werden
   etwa 60 % nach 50. Die Simulation kostet Sekunden; der Live-Lauf eine Minute
   je Tick.
2. **Die Gewichtssummen-Kappe und die Renormalisierung**, damit Wachstum nicht an
   `w_max` sättigt, sondern die *Verteilung* verschiebt. Solange beides fehlt,
   ist jedes α > 0 auf Doktrin-Skala ein Pathologie-Erzeuger (oben gemessen).
3. **Ein Instrument, das Ränge misst** — steht jetzt im Heartbeat-Skript — und
   ein Korpus, auf dem `k_seeds=1` mit Namensankern die Gold-Mitgliedschaft
   nicht ohnehin schon festnagelt.

Der dritte Punkt ist unbequem: auf dem Founding-Mesh ist das Retrieval bei
`k_seeds=1` so gut, dass es die Dynamik nicht braucht. Der Herzschlag muss dort
gemessen werden, wo das Retrieval Spielraum hat.

Abgelegt als PHX-1104 — und dort auf 2Wiki gemessen: [`heartbeat_2wiki.md`](heartbeat_2wiki.md).
