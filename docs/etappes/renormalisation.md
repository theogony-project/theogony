# Renormalisierung — die Gegenkraft, die das Gate braucht (PHX-1106)

**Stand:** 2026-09-12, Messung läuft. Branch `feat/phx-1106-renormalisation`.
**Anlass:** [`heartbeat_2wiki.md`](heartbeat_2wiki.md) — unter dem Gate lernt das Substrat aus Benutzung (+1,3 auf benutzten Fragen) und verdrängt dabei (−1,5 auf zurückgehaltenen, monoton über 50 Runden). MESH_SUBSTRATE §6 sieht die globale homöostatische Renormalisierung als Gegenkraft vor; die Inventur fand sie nicht gebaut.
**Werkzeug:** `renormalise_edges_inplace` in `storage/edges.py`, der Tick-Schritt in `run_minimal_tick(renormalise=…)`, `mesh tick --renormalise`, die Politiken `renorm_*` in `scripts/mesh_heartbeat_qa.py`.

## Was §6 sagt, und was ein Operator davon sieht

Die Doktrin: einmal je Tick wird jede Kante mit demselben Faktor skaliert, bis
das Gesamtgewicht je Knoten wieder bei `R_ideal` liegt. „The correction is
multiplicative across all edges — uniform across tiers, weights, ages — so
relative ordering is preserved."

Erhalten bleibt mehr als die Ordnung: **jeder Anteil.** Der Operator, der die
Constellation baut, liest die zeilennormalisierte Adjazenz — PPR im Substrat,
gedämpfte Diffusion im Benchmark-Kern —, und die ist gegen jede globale
Skalierung invariant. Was den Herzschlag bewegt hat, war nie die absolute
Stärke einer Kante, sondern ihr Anteil am Knoten: 5,4 % der Kanten bleiben
unter dem Gate am Anschlag, alle anderen fallen auf 0,28, und der Anteil der
verschonten Kanten an jedem Knoten wächst um das 3,5-fache. Eine Skalierung,
die jede Kante gleich behandelt, ändert an diesem Verhältnis nichts. §6 ist,
wie geschrieben, für den Operator unsichtbar.

Sichtbar wird sie erst durch das, was im Tick nach ihr kommt: die Kappe.
Gefeuerte Kanten sitzen bei `w_max = 1,0`; hebt die Renormalisierung alle
Kanten an, werden sie abgeschnitten, während die ungefeuerten unter ihnen
zurückgehoben werden. Der Anteil, den das Gate den benutzten Kanten gab, wird
ihnen von der Kappe wieder genommen. Das ist die Gegenkraft — nicht die
Skalierung, sondern Skalierung *und* Kappe. Und es ist auch die Warnung der
Inventur: „a correct implementation must be landed together with a rethink of
w_max, or the first correction destroys every weight distinction in the
substrate" — eine Kante bei 0,7 wird jeden Tick um den globalen Faktor
gehoben und verliert nur ihren eigenen Zerfall; sie kriecht zur Kappe.

## Drei Lesarten, gebaut

| Modus | Regel | Was der Operator sieht |
|---|---|---|
| `global` | ein Faktor über alle Kanten, Sollwert = Gesamtgewicht je Knoten beim ersten Einschalten (`homeostatic_ratio` in `mesh_state.json`) | nur die Kappe: gefeuerte Kanten werden abgeschnitten, ungefeuerte gehoben |
| `out` | je Quellknoten: die Summe der Ausgangsgewichte zurück auf den Wert vor dem Tick | je Zeile dasselbe wie `global`, aber vollständig statt im Mittel |
| `in` | je Zielknoten: die Summe der Eingangsgewichte zurück auf den Wert vor dem Tick | synaptische Skalierung im Wortsinn (Turrigiano & Nelson, die Quelle, die §6 zitiert): ein Ziel, das nur gefeuerte Kanten empfängt, wird herunterskaliert und verliert Anteil in jeder Zeile, die auf es zeigt |
| `free` | `global`, aber nach der Kappe: Gewichte dürfen über 1 leben | nichts — die Kontrolle, die sagt, ob die anderen mehr tun als die Kappe |

Alle drei sitzen an der Stelle, die MESH_IMPLEMENTATION §„Oneiros — implementation
order" nennt: Schritt 3 Zerfall, Schritt 4 Renormalisierung, Schritte 8–9
Sättigung. Die per-Knoten-Modi halten den Wert *vor dem Einmischen der
Gutschrift*, damit Gutschrift die Verteilung innerhalb des Knotens verschiebt
und der Zerfall ihn nicht leert — das ist der Satz aus dem Ticket, wörtlich
genommen. Die tier-bewusste Milderung aus §6 ist als Option gebaut und hier
aus, weil `decay_tier` auf jeder Kante 0 ist (PHX-1095).

**Die Hypothese des Tickets:** benutzt +1,3 bleibt, zurückgehalten fällt nicht
mehr. Und die Alternativen, die es selbst nennt: fallen beide, ist der Sollwert
falsch; fällt benutzt, frisst die Renormalisierung die Gutschrift.

## Messung

Derselbe Herzschlag wie PHX-1104: 2WikiMultihopQA, 300 Fragen, 150 benutzt /
150 zurückgehalten, hybrides Seeding S=2, 3 Hops, Dämpfung 0,5, `w_max` 1,0,
λ 0,05, 50 Runden, Gutschrift α = 0,01 normalisiert. Fünf Politiken aus
demselben Zustand: `grow01` (Gate + Gutschrift, die Baseline aus PHX-1104) und
die vier Lesarten darauf. Dann dasselbe auf HotpotQA, dann 2Wiki mit einem
zweiten Seed — die Bedingung aus dem Plan, bevor ein bis zwei Fragen Effekt
als Effekt gelten.

### 2Wiki, Seed 0

Report `data/run_reports/mesh_eval/heartbeat_2wikimultihopqa_01M2A4JCFDXAR60DFJ97E7Q5Q8.json`,
62 Minuten. kNN-Kontrolle 0,650 / 0,717, roher Graph 0,777 / 0,818, nach der
Kappe 0,777 / 0,813 — die Baseline `grow01` reproduziert PHX-1104 auf die
dritte Stelle. Recall@5 an den Messpunkten 0 / 1 / 2 / 3 / 5 / 10 / 20 / 30 / 50:

| Politik | benutzt | zurückgehalten | Δ50 benutzt | Δ50 zurückgehalten | w Mittel / Median, Runde 50 | am Anschlag |
|---|---|---|---|---|---|---|
| `grow01` (Baseline) | ,777 ,787 ,787 ,787 ,787 ,787 ,787 ,790 ,790 | ,813 ,828 ,828 ,828 ,827 ,827 ,807 ,805 ,798 | **+1,3** | **−1,5** | 0,336 / 0,281 | 6,0 % |
| `renorm_global` | ,777 ,787 ,790 ,787 ,787 ,788 ,788 ,788 ,788 | ,813 ,833 ,833 ,833 ,828 ,823 ,825 ,827 ,828 | **+1,2** | **+1,5** | 0,950 / 0,950 | 12,1 % |
| `renorm_out` | ,777 ,790 ,790 ,790 ,790 ,790 ,790 ,790 ,783 | ,813 ,828 ,828 ,828 ,827 ,823 ,818 ,813 ,813 | +0,7 | ±0,0 | 0,868 / 0,995 | 49,7 % |
| `renorm_in` | ,777 ,783 ,783 ,783 ,783 ,783 ,788 ,788 ,788 | ,813 ,828 ,828 ,828 ,827 ,825 ,823 ,815 ,802 | +1,2 | −1,2 | 0,867 / 0,995 | 49,7 % |
| `renorm_free` | ,777 ,787 ,787 ,790 ,787 ,788 ,788 ,788 ,788 | ,813 ,828 ,828 ,830 ,827 ,828 ,825 ,823 ,825 | +1,2 | +1,2 | 0,956 / 0,955 | 12,1 % |

**Die Hypothese des Tickets hält, mit der globalen Lesart.** Unter
`renorm_global` bleibt der Gewinn auf den benutzten Fragen (+1,2 gegen +1,3),
und die zurückgehaltenen fallen nicht mehr — sie liegen nach 50 Runden 1,5
Punkte *über* Runde 0. Der Rang der zurückgehaltenen Gold-Passagen geht von
6,5 auf 6,7 statt auf 7,1.

**Was dabei sichtbar wird, ist der Mechanismus der Verdrängung, rückwärts.**
Die Gutschrift hebt in Runde 1 beide Hälften — benutzt +1,0, zurückgehalten
+1,5, in allen fünf Politiken gleich, weil 2Wiki-Fragen Entitäten teilen und
gestärkte Brücken zunächst allen helfen (die Beobachtung aus PHX-1104, die
dort unerklärt blieb). In der Baseline frisst die Drift des Gates diesen
Gewinn ab Runde 20 wieder auf: die ungefeuerten Kanten fallen auf 0,28, die
verschonten bleiben bei 1,0, und die zurückgehaltenen Fragen verlieren drei
Punkte gegenüber Runde 1. Unter der globalen Renormalisierung werden die
ungefeuerten Kanten jeden Tick zurückgehoben und die gefeuerten an der Kappe
abgeschnitten: das Mittel bleibt bei 0,95 statt auf 0,34 zu fallen, die Drift
findet nicht statt, und der Gewinn aus Runde 1 bleibt stehen.

**Die drei anderen Lesarten, in einem Satz je:** `out` hält jede Zeile so
streng, dass auch der Gewinn halbiert wird (+0,7 / ±0) — die Gutschrift wird
innerhalb der Zeile sofort wieder herausskaliert. `in` (synaptische
Skalierung) hält den Gewinn und bremst die Drift nur (−1,2 statt −1,5; der
Einbruch beginnt bei Runde 30 statt 20). `free` ist keine saubere Kontrolle:
die Kappe greift am Anfang der nächsten Runde wieder, und die Zahlen sind die
der globalen Lesart — die echte Kontrolle, ganz ohne Kappe, steht unten.

**Der Preis, benannt:** unter `global` sitzen nach 50 Runden alle Gewichte
bei 0,95 ± wenig (Median 0,950, Mittel 0,950). Die Warnung der Inventur trifft
zu — die Gewichtsunterschiede des eingelesenen Graphen sind nach 50 Ticks
weitgehend eingeebnet. Dass das Retrieval darunter nicht leidet, sondern über
Runde 0 liegt, sagt etwas über diesen Graphen: seine Anteile tragen mehr als
seine Stärken. Ob das auf dem Founding-Mesh so ist, wo die Gewichte breiter
streuen (Median 0,31), ist nicht gemessen.
