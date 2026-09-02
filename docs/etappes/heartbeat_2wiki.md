# Der Herzschlag auf 2Wiki — das Substrat lernt aus Benutzung, und verdrängt dabei

*2026-09-02. 2WikiMultihopQA, Kadmos-Graph aus dem Cache: 6.119 Passagen, 32.499
Entitäten, 283.144 Kanten. 300 Fragen, 150 benutzt / 150 zurückgehalten,
hybrides Seeding S=2 — der Punkt, an dem das Projekt sein einziges demonstriertes
Ergebnis hat. 50 Runden, vier Politiken. Kein LLM, kein Geld, 61 Minuten.
`scripts/mesh_heartbeat_qa.py`, Report
`data/run_reports/mesh_eval/heartbeat_2wikimultihopqa_01M1HKG6ZGGNPXXWEZ46VRZD4A.json`.
PHX-1104.*

## Warum hier

Auf dem Founding-Mesh konnte der Herzschlag nicht sichtbar werden: Recall 85 %,
die Gold-Treffer von Namensankern festgenagelt, zehn Runden, keine Bewegung
([`hebbian_calibration.md`](hebbian_calibration.md)). PHX-1104 nannte drei
Bedingungen — längerer Horizont, ein Korpus mit Spielraum, die Renormalisierung
als Gegenkraft. Dieser Lauf erfüllt die ersten beiden und misst, ob die dritte
gebraucht wird.

**Im Speicher, auf den echten Tick-Funktionen.** Der Graph ist der des
Benchmarks, der Propagationskern der des Benchmarks (zeilennormalisierte
Adjazenz, 3 Hops, Dämpfung 0,5 — der Betriebspunkt, an dem +0,102 gemessen
wurde), die Dynamik die des Substrats: `merge_edge_deltas`,
`decay_edges_inplace(fired=…)`, `enforce_saturation`, `fired_pairs`. Ein
Durchgang ist das Top-50-Arbeitsset nach Aktivierung, wie eine Constellation.
Nichts wird in einen Workspace geschrieben.

**Das Gewichtsregime ist ein anderes als auf dem Founding-Mesh.** Die Kappe
`w_max = 1,0` greift hier von Anfang an: Containment-Kanten kommen *bei* 1,0 an,
Relationszähler darüber. Nach der Kappe liegen **56,8 % aller Kanten am
Anschlag**, der Median ist 1,0. Auf dem rohen Graphen misst SA@5 0,777 / 0,818
(benutzt / zurückgehalten), nach der Kappe 0,777 / 0,813 — die Kappe kostet einen
halben Punkt. kNN, die Kontrolle, die sich nie bewegen darf: 0,650 / 0,717.

## Die vier Politiken

| Runde | Politik | used@5 | Rang | held@5 | Rang | w Median | am Anschlag | verschont |
|---|---|---|---|---|---|---|---|---|
| 0 | — | 0,777 | 9,1 | 0,813 | 6,5 | 1,000 | 56,8 % | — |
| 50 | **alter Zerfall** (alles zerfällt) | 0,773 | 9,7 | 0,810 | 6,8 | 0,281 | 0 % | 0 |
| 50 | **Gate** (nur Ungefeuertes zerfällt) | 0,780 | 9,3 | **0,798** | 7,4 | 0,281 | 5,4 % | 36.760 |
| 50 | **Gate + Hebb α=0,01**, normalisiert | **0,790** | **8,9** | 0,798 | 7,1 | 0,281 | 6,0 % | 30.092 |
| 50 | **Gate + Hebb α=0,1**, normalisiert | 0,787 | 8,9 | 0,797 | 7,2 | 0,281 | 6,2 % | 30.070 |

Die vollständigen Verläufe an den Messpunkten 1/2/3/5/10/20/30/50 stehen im
Report; die drei Bewegungen, auf die es ankommt:

**Gleichmäßiger Zerfall ist auch hier fast unsichtbar.** Unter dem alten Zerfall
verliert das Substrat 72 % seines Gewichts (Median 1,000 → 0,281) und das
Retrieval verliert 0,4 Punkte. Zweiter Korpus, dieselbe Aussage wie auf dem
Founding-Mesh: der Operator liest Anteile, nicht Stärken.

**Mit Gutschrift steigt das Benutzte — und hält.** Gate plus Hebb auf
Doktrin-Skala: benutzte Fragen 0,777 → **0,790** (+1,3 Punkte), Rang 9,1 → 8,9.
Der Sprung kommt in Runde 1 (+1,0) und bleibt über 50 Runden stehen. Das ist das
erste Mal, dass sich das Verb *lernt* aus „the mesh is alive" auf einer Messung
überhaupt bewegt hat. Die Größe von α ist dabei nahezu egal (0,790 gegen 0,787):
die gutgeschriebenen Kanten sitzen an der Kappe, und mehr Gutschrift hat dort
nichts zu tun.

**Und das Zurückgehaltene fällt — unter dem Gate, mit oder ohne Gutschrift.**
0,813 → **0,798** (−1,5 Punkte), Rang 6,5 → 7,4. Nicht als Sprung, sondern als
Drift: 0,813 · 0,813 · 0,813 · 0,810 · 0,813 · 0,812 · 0,805 · 0,798 über die
acht Messpunkte. Der Mechanismus ist sichtbar in der Spalte *am Anschlag*: 5,4 %
der Kanten — die um die benutzten Fragen — bleiben bei 1,0, während alle anderen
auf 0,28 fallen. Ihr *Anteil* an jedem Knoten, den sie berühren, wächst damit um
das 3,5-fache, und der Random Walk kippt zu den benutzten Regionen. Fragen, deren
Pfade durch gemischte Knoten laufen, verlieren Anteil.

Eine Beobachtung, die ich nicht erklären kann und deshalb nur notiere: in Runde
1 hebt die Gutschrift auf den benutzten Fragen **auch die zurückgehaltenen** —
0,813 → 0,828, Rang 6,5 → 6,3. Der Gewinn zerfällt bis Runde 20 wieder. Am
plausibelsten: 2Wiki-Fragen teilen Entitäten, und gestärkte Brücken helfen
zunächst allen Fragen durch dieselben Hubs, bis die asymmetrische Verdrängung
das überwiegt. Das ist eine Vermutung, keine Messung.

## Was das heißt

Die Vision sagt *„fire together, wire together"* und *„edges that are not fired
weaken"*. Beides ist jetzt gebaut, und auf einem Korpus mit Spielraum tut beides,
was es soll — benutzte Pfade werden besser, unbenutzte verblassen. Der Preis
steht daneben, klein und monoton: **was nicht benutzt wird, wird nicht nur
vergessen, sondern verdrängt.** Ein Substrat, das ein Jahr lang eine Handvoll
Fragen beantwortet, würde auf alles andere schlechter, nicht nur älter.

Das ist nicht das Scheitern des Gates. Es ist der gemessene Grund, aus dem die
Doktrin in §6 die **globale homöostatische Renormalisierung** vorsieht — die
Gegenkraft, die das Gesamtgewicht je Knoten stabil hält, damit „mehr Anteil für
das Benutzte" nicht „weniger für alles andere" bedeutet. Bisher war das ein
Argument. Jetzt ist es −1,5 Punkte über 50 Runden auf zurückgehaltenen Fragen,
und das nächste Organ, das gebaut wird (PHX-1106).

## Grenzen dieses Laufs

- **Effektgrößen von 1–1,5 Punkten auf 150 Fragen** sind ein bis zwei Fragen.
  Die Messung ist deterministisch (kein LLM), die Drift ist monoton über acht
  Punkte, der Sprung in Runde 1 reproduziert sich in beiden Wachstums-Läufen —
  aber es sind zwei Fragen, und ein zweiter Seed oder ein zweiter Datensatz
  (HotpotQA, MuSiQue) müsste sie bestätigen.
- **Die Arbeitssets waren nicht vollständig reproduzierbar.** 56,8 % der
  Gewichte am Anschlag erzeugen exakt gleiche Aktivierungen, und `torch.topk`
  bricht die Bindung zwischen zwei Politiken aus demselben Zustand verschieden
  (36.858 gegen 30.214 verschonte Kanten in Runde 1). Das Top-5-Ranking war
  davon unberührt, der Rand des Arbeitssets nicht. Das Skript sortiert seit
  diesem Lauf stabil; dieser Lauf entstand davor.
- **Kern und Tick sind zwei Systeme.** Der Propagationskern ist der des
  Benchmarks (gedämpfte Diffusion), nicht `Propagator.propagate(operator="ppr")`
  des Substrats (Neustart-PPR, 12 Iterationen). Beide lesen die zeilennormalisierte
  Adjazenz; die Aussage über Anteile gilt für beide. Die Zahlen sind mit der
  Seeding-Studie vergleichbar, nicht mit `mesh ask`.
- **Nur Hebb-Gutschrift auf bestehende Kanten.** Der Erzeugungs-Zweig ist im
  Substrat unerreichbar (PHX-1100); hier ebenso. „Denser mesh" hat auch dieser
  Lauf nicht erzeugt.
