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

*(Ergebnisse folgen.)*
