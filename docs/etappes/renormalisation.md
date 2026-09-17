# Renormalisierung — die Gegenkraft, die das Gate braucht (PHX-1106)

> **English abstract.** *Question.* Use makes the substrate displace what it
> does not use (PHX-1104). Does the doctrine's global homeostatic
> renormalisation (MESH_SUBSTRATE §6) stop that? *Method.* The heartbeat
> protocol in memory on the substrate's real tick functions: Kadmos graphs of
> 2WikiMultihopQA and HotpotQA, 300 questions split 150 used / 150 held out, 50
> rounds, recall@5, two datasets and two seeds, no LLM. *Result.* The decay gate
> displaces in every run (held-out −1.5 / −2.3 / −2.3). Global renormalisation
> *with the weight cap* removes it every time (+1.5 / −0.7 / +0.7; mean +0.5
> against −2.0) for about half a point on the used questions. What does not hold
> is the gain: the +1.3 of PHX-1104 was one seed (+0.3 on HotpotQA, −0.7 on seed
> 1), so the plan's condition is met by no policy, the baseline included. *§6 as
> written, without a cap,* is invisible for ten rounds — a row-normalised
> operator is scale-invariant, measured to the third decimal — and then an
> amplifier: credited edges grow without bound (strongest weight 41.9), scaling
> shrinks everything else, held-out falls −3.8 against −2.0. The counterforce is
> scaling *and* cap, not scaling. *Decision.* `mesh tick` renormalises globally
> by default at a set point of 0.9 of entry mass. The verb "learns" stays at
> "holds without displacing"; whether it ever gains depends on the edge-creating
> branch, which is unreachable (PHX-1100).

**Stand:** 2026-09-12, gemessen. Branch `feat/phx-1106-renormalisation`.
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

### HotpotQA, Seed 0

Report `heartbeat_hotpotqa_01M2A84TFEQHWBGQ5ED3M7Q8DK.json`, 9.811 Passagen,
61.540 Entitäten, 525.576 Kanten, 125 Minuten. Ein Korpus mit weniger
Spielraum: kNN 0,837 / 0,827, Spreading Activation 0,850 / 0,840 — der
Vorsprung des Graphen ist hier ein Punkt, nicht zehn.

| Politik | benutzt | zurückgehalten | Δ50 benutzt | Δ50 zurückgehalten | w Mittel, Runde 50 |
|---|---|---|---|---|---|
| `grow01` (Baseline) | ,850 ,853 ,857 ,857 ,857 ,857 ,857 ,857 ,853 | ,840 ,830 ,827 ,830 ,830 ,837 ,830 ,823 ,817 | +0,3 | **−2,3** | 0,319 |
| `renorm_global` | ,850 ,850 ,847 ,843 ,847 ,843 ,843 ,843 ,843 | ,840 ,827 ,830 ,830 ,830 ,830 ,830 ,830 ,833 | −0,7 | −0,7 | 0,970 |
| `renorm_out` | ,850 ,843 ,843 ,843 ,843 ,843 ,847 ,847 ,847 | ,840 ,833 ,833 ,833 ,833 ,837 ,827 ,823 ,823 | −0,3 | −1,7 | 0,896 |
| `renorm_in` | ,850 ,847 ,850 ,850 ,847 ,843 ,843 ,843 ,843 | ,840 ,823 ,823 ,823 ,823 ,823 ,823 ,820 ,813 | −0,7 | −2,7 | 0,896 |
| `renorm_free` | ,850 ,853 ,850 ,847 ,843 ,847 ,847 ,843 ,843 | ,840 ,830 ,827 ,827 ,827 ,833 ,830 ,830 ,833 | −0,7 | −0,7 | 0,975 |

**Hier ist nichts zu bewahren, und die Renormalisierung bewahrt es
trotzdem.** Die Gutschrift in Runde 1 hilft dem Benutzten kaum (+0,3, später
+0,7) und kostet das Zurückgehaltene sofort (−1,0) — auf HotpotQA teilen die
Fragen ihre Brücken nicht so, wie 2Wiki-Fragen es tun. Danach frisst die
Drift des Gates weiter: −2,3 nach 50 Runden, stärker als auf 2Wiki. Unter
`global` steht das Zurückgehaltene ab Runde 2 still (0,830 → 0,833), die
Drift ist weg; der Preis ist das Benutzte, das von +0,7 auf −0,7 fällt, weil
die Einebnung der Gewichte auf diesem Graphen etwas kostet, das die Anteile
nicht ersetzen. Die Bedingung des Plans — benutzt ≥ +1 *und* zurückgehalten ≥
0 — ist auf HotpotQA von keiner Politik zu erfüllen, weil schon die Baseline
kein +1 hat: dieser Herzschlag hat hier keinen Raum, wie auf dem
Founding-Mesh. Was sich messen lässt, ist die Verdrängung, und die nimmt
`global` von −2,3 auf −0,7.

### 2Wiki, Seed 1

Report `heartbeat_2wikimultihopqa_01M2AF9A6G64V5XFBE90FPDTSZ.json`, 69 Minuten.
Derselbe Graph, andere Hälften: kNN 0,708 / 0,715, Spreading Activation
0,808 / 0,800.

| Politik | benutzt | zurückgehalten | Δ50 benutzt | Δ50 zurückgehalten |
|---|---|---|---|---|
| `grow01` (Baseline) | ,808 ,807 ,805 ,803 ,803 ,803 ,805 ,805 ,802 | ,798 ,805 ,808 ,807 ,805 ,797 ,787 ,782 ,775 | −0,7 | **−2,3** |
| `renorm_global` | ,808 ,807 ,803 ,803 ,797 ,793 ,793 ,793 ,793 | ,798 ,803 ,800 ,802 ,807 ,803 ,807 ,807 ,805 | −1,5 | **+0,7** |
| `renorm_out` | ,808 ,807 ,803 ,803 ,803 ,803 ,797 ,797 ,797 | ,798 ,800 ,805 ,805 ,803 ,793 ,788 ,780 ,777 | −1,2 | −2,2 |
| `renorm_in` | ,808 ,802 ,802 ,802 ,802 ,795 ,793 ,793 ,793 | ,798 ,803 ,803 ,807 ,817 ,807 ,813 ,808 ,803 | −1,5 | +0,5 |
| `renorm_free` | ,808 ,807 ,807 ,803 ,800 ,793 ,793 ,793 ,793 | ,798 ,805 ,807 ,807 ,808 ,795 ,808 ,815 ,805 | −1,5 | +0,7 |

**Der Gewinn aus Seed 0 wiederholt sich nicht, die Verdrängung schon.** Mit
diesen Hälften bringt die Gutschrift dem Benutzten nichts (−0,7 nach 50
Runden), und das Zurückgehaltene fällt −2,3, wie auf HotpotQA. Die +1,3 aus
PHX-1104 waren, was der Bericht dort selbst als Möglichkeit nannte: ein bis
zwei Fragen eines Seeds. Unter `global` fällt das Zurückgehaltene wieder nicht
(+0,7), und das Benutzte zahlt −1,5.

### Alle drei Läufe nebeneinander

Δ50 in Punkten Recall@5, benutzt / zurückgehalten:

| Politik | 2Wiki Seed 0 | HotpotQA Seed 0 | 2Wiki Seed 1 | Mittel benutzt | Mittel zurückgehalten |
|---|---|---|---|---|---|
| `grow01` (Baseline) | +1,3 / −1,5 | +0,3 / −2,3 | −0,7 / −2,3 | +0,3 | **−2,0** |
| `renorm_global` | +1,2 / +1,5 | −0,7 / −0,7 | −1,5 / +0,7 | −0,3 | **+0,5** |
| `renorm_out` | +0,7 / ±0 | −0,3 / −1,7 | −1,2 / −2,2 | −0,3 | −1,3 |
| `renorm_in` | +1,2 / −1,2 | −0,7 / −2,7 | −1,5 / +0,5 | −0,3 | −1,1 |
| `renorm_free` | +1,2 / +1,2 | −0,7 / −0,7 | −1,5 / +0,7 | −0,3 | +0,4 |

Was über Datensätze und Seeds hält: **das Gate verdrängt** (−1,5, −2,3, −2,3),
und **die globale Renormalisierung nimmt die Verdrängung jedes Mal weg**
(+1,5, −0,7, +0,7 — im Mittel 2,5 Punkte besser als die Baseline auf dem
Zurückgehaltenen). Was nicht hält: dass das Substrat aus Benutzung robust
*gewinnt* — die Baseline liegt auf dem Benutzten bei +1,3, +0,3, −0,7 —, und
die Renormalisierung kostet dort im Mittel 0,6 Punkte gegen die Baseline, in
zwei von drei Läufen etwa einen. Die Bedingung des Plans (benutzt ≥ +1 und
zurückgehalten ≥ 0, auf beiden Datensätzen und beiden Seeds) erfüllt keine
Politik, weil ihre erste Hälfte schon von der Baseline nur in einem Lauf
erfüllt wird. Die Frage, die bleibt, ist der Preis auf dem Benutzten, und ob
er an der Einebnung hängt — dafür der Sollwert-Sweep unten.

### Die Kontrolle ohne Kappe: §6, wie geschrieben

Report `heartbeat_2wikimultihopqa_01M2AK99P0RBXSZ5H1MCZQ676V.json`, 2Wiki Seed
0, 29 Minuten. Keine Kappe beim Eintritt, beim Einmischen der Gutschrift, bei
der Sättigung: der rohe Graph (Gewichte bis 9,0), Gewichte dürfen wachsen,
und die globale Skalierung ist die einzige Homöostase — das Regime, das §6
beschreibt.

| Politik | benutzt | zurückgehalten | Δ50 benutzt | Δ50 zurückgehalten | w Mittel / Median / max, Runde 50 |
|---|---|---|---|---|---|
| `grow01_uncapped` | ,777 ,793 ,793 ,793 ,793 ,793 ,793 ,793 ,790 | ,818 ,835 ,832 ,832 ,828 ,827 ,807 ,805 ,798 | +1,3 | −2,0 | 0,340 / 0,281 / 9,0 |
| `renorm_uncapped` | ,777 ,793 ,793 ,793 ,793 ,793 ,793 ,793 ,792 | ,818 ,835 ,832 ,830 ,827 ,827 ,802 ,798 ,780 | +1,5 | **−3,8** | 0,968 / 0,568 / 41,9 |

Bis Runde 10 sind die beiden bis auf die dritte Stelle gleich — die
Skaleninvarianz des Operators, gemessen. Danach trennen sie sich, und zwar in
die falsche Richtung: **§6, wie geschrieben, verstärkt die Verdrängung.** Die
gefeuerten Kanten wachsen mit der Gutschrift ohne Grenze (das stärkste
Gewicht nach 50 Runden: 41,9), die globale Skalierung schrumpft alles andere,
damit die Masse hält, und der Anteil des Unbenutzten fällt schneller als
unter dem Zerfall allein: −3,8 gegen −2,0. Das ist genau, was die Doktrin
verspricht — „an edge that fires more often than average grows; one that
fires less shrinks" — und genau das Gegenteil dessen, was das Ticket von ihr
erhoffte. Die kleine Abweichung vor Runde 10 kommt vom quadratischen Zerfall,
der nicht skaleninvariant ist: gehobene Gewichte verlieren absolut mehr.

Die Gegenkraft, die in den Läufen oben wirkt, ist also nicht §6. Es ist §6
*mit der Kappe*: die Skalierung hebt das Unbenutzte zurück, die Kappe hindert
das Benutzte am Davonlaufen. Ohne die Kappe wäre die Renormalisierung ein
Verstärker.

**Der Preis, benannt:** unter `global` mit Sollwert 1,0 sitzen nach 50
Runden alle Gewichte bei 0,95 ± wenig (Median 0,950, Mittel 0,950). Die
Warnung der Inventur trifft zu — die Gewichtsunterschiede des eingelesenen
Graphen sind nach 50 Ticks weitgehend eingeebnet. Dass das Retrieval auf 2Wiki
darunter nicht leidet, sagt etwas über diesen Graphen: seine Anteile tragen
mehr als seine Stärken. Auf HotpotQA kostet es 0,7 auf dem Benutzten.

### Der Sollwert: `R_ideal` ist ein Stellparameter

§6 nennt `R_ideal` einen Stellparameter. Der Tick verankert ihn beim ersten
Einschalten an der Masse, die das Mesh dann trägt; die Frage ist, ob er
*darunter* liegen sollte, damit die gehobenen Kanten nicht an der Kappe
landen. Reports `heartbeat_2wikimultihopqa_01M2AN1Q0G15B0VFEZHNKRTDCP.json`
und `heartbeat_hotpotqa_01M2AQXJMQNEHDSFDC1TJSKGK4.json`, Seed 0, Sollwert als
Anteil der Eintrittsmasse:

| Sollwert | 2Wiki Δ50 benutzt / zurückgehalten | 2Wiki w Median, Runde 50 | HotpotQA Δ50 benutzt / zurückgehalten | HotpotQA w Median |
|---|---|---|---|---|
| 1,0 | +1,2 / +1,5 | 0,950 | −0,7 / −0,7 | 0,972 |
| **0,9** | **+1,2 / +1,2** | **0,851** | **−0,3 / −0,7** | **0,873** |
| 0,8 | +1,2 / +1,2 | 0,745 | −0,3 / −1,0 | 0,769 |
| 0,7 | +1,5 / −0,2 | 0,640 | −0,3 / −1,0 | 0,665 |

Bei 0,9 tut die Gegenkraft dasselbe wie bei 1,0, der Median bleibt bei 0,85
statt 0,95, und auf HotpotQA halbiert sich der Preis auf dem Benutzten. Bei
0,7 ist der Gewinn auf dem Zurückgehaltenen weg: die gehobenen Kanten bleiben
so weit unter der Kappe, dass die gefeuerten ihnen wieder davonlaufen.
**0,9 ist der Betriebspunkt**, und `DEFAULT_RENORM_SCALE` trägt ihn.

## Was ausgeliefert wird, und warum

`mesh tick` läuft ab jetzt mit `--renormalise global --renorm-scale 0.9`; der
Sollwert wird beim ersten Tick in `mesh_state.json` verankert
(`homeostatic_ratio`) und danach gehalten, `--renormalise off` schaltet ab.
`run_minimal_tick` selbst bleibt bei `renormalise=None`: die Funktion ist die
Primitive, aus der Harnesse und Tests ihre Kompositionen bauen; der Befehl
ist die gemessene Komposition.

Die Begründung in drei Zahlen: über zwei Datensätze und zwei Seeds verdrängt
das Gate das Unbenutzte um −1,5, −2,3, −2,3; die globale Renormalisierung mit
Kappe hebt das auf (+1,5, −0,7, +0,7) und kostet dafür im Mittel einen halben
Punkt auf dem Benutzten, dessen Gewinn ohnehin nur in einem der drei Läufe da
war. Ein Substrat, das ein Jahr lang eine Handvoll Fragen beantwortet, wird
damit auf alles andere nicht mehr schlechter. Das war der Satz, mit dem
PHX-1104 endete, und er ist jetzt eine Einstellung.

Was die Doktrin davon lernen muss, steht in PHX-1108: §6, wie geschrieben —
uniform, ohne Kappe, „relative ordering is preserved" —, ist für einen
Operator, der Anteile liest, unsichtbar und mit wachsenden Gewichten ein
Verstärker der Verdrängung (−3,8). Die Gegenkraft ist die Kappe, die die
Doktrin an anderer Stelle (§3, als Sättigung je Knoten) vorsieht und die hier
als `w_max` je Kante gebaut ist. Die Tier-Leiter (PHX-1100, Muster 3) bleibt
unangetastet: die Gewichte leben weiter unter 1, und `decay_tier` ist auf
jeder Kante 0.

## Grenzen

- Effektgrößen von einem bis zwei Punkten auf 150 Fragen; deterministisch,
  aber ein bis drei Fragen. Drei Läufe, zwei Datensätze, zwei Seeds — der
  Vorzeichenwechsel auf dem Zurückgehaltenen hält in allen drei, die
  Größe schwankt.
- Der Herzschlag-Kern ist die gedämpfte Diffusion des Benchmarks, nicht der
  PPR des Substrats; beide lesen Anteile, die Aussage gilt für beide, die
  Zahlen sind nicht mit `mesh ask` vergleichbar.
- Nur Gutschrift auf bestehende Kanten; der Erzeugungszweig bleibt
  unerreichbar (PHX-1100).
- Das Founding-Mesh (Median 0,31, breite Streuung, Retrieval an Namensankern
  festgenagelt) ist ein anderes Gewichtsregime als die Benchmark-Graphen mit
  57 % der Kanten am Anschlag; die Messung dort steht unten.

## Auf dem Founding-Mesh, mit dem echten Tick

`scripts/mesh_heartbeat.py --policies grow,renorm --rounds 10` auf Kopien von
`data/mesh-founding`, 24 benutzte / 23 zurückgehaltene Gold-Fragen,
`k_seeds = 1`, Gutschrift α = 0,1 normalisiert, der Tick des Substrats
(`run_minimal_tick`, Sollwert 0,9 beim ersten Tick verankert):

| Runde | Baseline benutzt / zurückgehalten | w Median | Renorm benutzt / zurückgehalten | w Median | w max |
|---|---|---|---|---|---|
| 0 | 87,9 % / 86,7 % | 0,311 | 87,9 % / 86,7 % | 0,311 | 1,000 |
| 1 | 86,4 % / 84,4 % | 0,306 | 86,4 % / 84,4 % | 0,281 | 0,917 |
| 5 | 87,9 % / 84,4 % | 0,293 | 87,9 % / 84,4 % | 0,286 | 1,000 |
| 10 | 87,9 % / 84,4 % | 0,276 | 87,9 % / 84,4 % | 0,293 | 1,000 |

An jedem Messpunkt dieselben Zahlen: auf einem Mesh, dessen Gewichte unter
der Kappe leben, ist die Renormalisierung für das Retrieval das, was die
Theorie sagt — unsichtbar. Was sie tut, ist die Masse halten: der Median
fällt unter der Baseline in zehn Ticks von 0,311 auf 0,276 (das „Substrat,
das nur vergessen kann" aus PHX-1100) und steht unter der Renormalisierung
bei 0,293. Der Preis auf dem Benutzten, den die Benchmark-Graphen zeigen,
tritt hier nicht auf, weil die Kappe nichts abschneidet; der Gewinn auf dem
Zurückgehaltenen auch nicht, aus demselben Grund. Als Standard für `mesh
tick` ist sie auf dem Mesh, das die Demo zeigt, damit gemessen harmlos, und
auf einem Mesh, das an der Kappe lebt, gemessen nötig.
