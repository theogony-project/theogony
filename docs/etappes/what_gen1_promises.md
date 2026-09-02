# Was Gen 1 verspricht — die Vision gegen die Inventur gehalten

*2026-08-31, nach PHX-1097 (Konsolidierung), PHX-1100 (Inventur) und PHX-1101
(Aktivierungsgedächtnis). Gegen `README.md`, `docs/VISION.md`, das MESH-Triplett
und `ROADMAP.md`, mit den Messungen dieser Sitzung.*

## Warum diese Seite

Die Inventur ([`doctrine_inventory.md`](doctrine_inventory.md)) sagt, welche
Mechanismen laufen. Sie sagt nicht, was das für die Vision bedeutet — und die
Vision ist der Grund, aus dem alles andere gebaut wird. Diese Seite hält die
beiden gegeneinander und formuliert am Ende neu, was das Substrat in Gen 1
ehrlich verspricht.

Die Doktrin verlangt das ausdrücklich. `MESH_SUBSTRATE.md` §„Why the substrate's
mechanism is a system": *„Implementations should be honest about which subset
they realise and which failure modes are open as a result."* Das hier ist diese
Ehrlichkeit, auf einer Seite.

## Die Vision hat drei Schichten, und die Inventur trifft nur eine

**Die zivilisatorische Schicht** — Schienen statt Fahrzeuge, ein Commons, das
niemandem gehört, Provenienz und Widerspruch als erste Klasse, eine Stiftung
statt eines Exits. Nichts in der Inventur berührt sie. Sie ist eine Wette auf
Governance, keine auf Code, und sie wird nicht dadurch falsch, dass ein Zähler
auf Null steht. Diese Seite lässt sie in Ruhe.

**Die empirische Schicht** — die drei Fragen, an denen die README das Projekt
misst. Eine davon ist beantwortet, zwei sind offen. Dazu unten.

**Die architektonische Schicht** — das MESH-Triplett, der Satz *„The mesh is
alive"*, die fünf lebensähnlichen Dynamiken, der permanente Traum. Hier hat die
Inventur ihre Wirkung, und hier ist der Abstand zwischen dem, was die Dokumente
sagen, und dem, was läuft, am größten. Der Rest dieser Seite handelt davon.

---

## „The mesh is alive" — Wort für Wort

Der Satz, auf den sich MESH_SUBSTRATE verdichtet: *„The mesh is alive: it grows,
it links, it forgets, it consolidates, and it heals."* Nach der Inventur, mit dem
Beleg je Verb:

| es… | Stand | Beleg |
|---|---|---|
| **wächst** | ja | 1.210 Absätze gelesen, 5.002 Knoten, 94.490 Kanten; Ingestion läuft und ist auditiert (13.883 Audit-Zeilen) |
| **verknüpft** | ja, mit einer Einschränkung | der Eager-Linker läuft; aber 93 % der Kanten sind Nähe, nicht Urteil (PHX-1066), und das stärkste Identitätssignal — Q-IDs — existiert auf dem Mesh nicht mehr (127 von 130 waren konfabuliert, PHX-1063) |
| **vergisst** | **ja — und nur das** | 14 Ticks superlinearer Zerfall, im Gewichtsspektrum sichtbar; unbedingt, weil kein Feuersignal existierte |
| **konsolidiert** | seit heute, von Hand | PHX-1097: 48 Cluster, 68 Knoten; als Skript, nicht im Tick, weil es ein Sprachmodell braucht |
| **heilt** | nein | Pathologie-Überwachung, Therapie, Widerspruchsauflösung, Falschinformations-Entfernung: nichts davon existiert |
| *lernt aus Benutzung* | **nein** | Hebbsche Verstärkung verdrahtet, in 14 Ticks nie gefeuert, und 17–254× zu schwach gegen den Zerfall (PHX-1102) |

Das letzte Verb steht nicht im Satz. Es steht in der README („The learning loop
closes"), in VISION.md („amplified by Hebbian reactivation along frequently-used
paths") und in der Doktrin als erste der fünf Primitiven. Es ist das Verb, das
ein Substrat von einer Datenbank unterscheidet — und es ist das, das am
weitesten vom Laufen entfernt ist.

Der ehrliche Satz für Gen 1, heute: **Das Mesh wird gelesen, aktiviert, und
vergisst. Es konsolidiert auf Anweisung. Es merkt sich seit heute, was es
benutzt hat. Es lernt nicht, es heilt nicht.**

## Die fünf lebensähnlichen Dynamiken

Die README, Abschnitt 2: *„Lifelike dynamics — Hebbian strengthening,
super-linear decay, bounded saturation, atrophy decoupled from deletion,
homeostatic renormalisation."* Fünf Mechanismen in einem Atemzug.

| | läuft? | was die Messung sagt |
|---|---|---|
| Hebbsche Verstärkung | verdrahtet, nie gefeuert | stärkstes Delta einer Abfrage 2,9e-4 gegen 4,8e-3 Zerfall je Tick; Kanten *erzeugen* kann sie gar nicht — der Zweig ist vom Produktionspfad aus unerreichbar |
| superlinearer Zerfall | **ja** | k=2, λ=0,05, jeder Tick, jede Kante |
| begrenzte Sättigung | inert | Kappe 10.000 gegen maximalen Ausgangsgrad 1.093; hat in 14 Ticks nie etwas abgeschnitten; die Gewichtssumme-Kappe der Doktrin fehlt |
| Atrophie ohne Löschung | fehlt | kein gesundes Band, kein Pruner, kein Ressourcendruck-Auslöser |
| homöostatische Renormalisierung | fehlt | ein einziger Treffer im Repo: der Docstring, der sagt, dass es nicht gebaut ist |

**Einer von fünf.** Und der eine, der läuft, ist der, der wegnimmt.

Das ist kein Vorwurf an die Doktrin. Sie sagt selbst, dass ein Teilsystem *„fails
differently than the full design"*. Superlinearer Zerfall ohne Renormalisierung
und ohne Verstärkung ist genau so ein Teilsystem, und seine Ausfallart ist
benennbar: **ein Substrat, dessen Gewichte monoton gegen Null laufen, gebremst
nur durch die Häufigkeit der Ticks.** Vierzehn Ticks in elf Tagen haben das
Founding-Mesh von einem Gewichtsmodus bei 0,4 auf 0,31 gebracht. Nichts hält
dagegen.

## Der permanente Traum

VISION.md: *„There is no nightly batch job. Instead, a continuous, low-priority
'dreaming' process runs at all times."* README: *„a continuous low-priority
process that runs activation across existing knowledge, treats the resulting
constellations as new observations, and writes back denser connections. The
Chronik grows wiser without reading new text."*

Drei Dinge daran, jedes für sich belegt:

1. **Der Mesh-Tick hat keinen Zeitplan.** `run_minimal_tick` hat genau einen
   Aufrufer außerhalb der Tests: die CLI. Es gibt einen `OneirosWorker` mit
   `tick_interval_s` — er treibt den **Gen-1-Store** und importiert `theogony.mesh`
   nirgends. Der permanente Traum ist der alte Traum, über der alten Datenbank.
2. **„Writes back denser connections"** — die Hebbsche Rückschreibung kann keine
   Kante erzeugen (der Zweig ist unerreichbar), und sie hat auf dem Mesh nie
   gefeuert. Jede der 94.490 Kanten stammt aus der Ingestion.
3. **Das „+34,8 % MRR ohne neuen Text"** der README stammt aus
   `scripts/mesh_oneiros_dream.py`, das laut eigenem Docstring *„never writes to
   the workspace"*. Es ist eine Simulation über eine Kopie im Speicher, mit den
   echten Tick-Funktionen — ein legitimes Experiment, aber kein Prozess, der
   irgendwo läuft, und kein Mesh, das dadurch dichter geworden wäre.

Der Traum ist als Messung real und als Prozess Fiktion. Das ist eine andere
Aussage als die der README.

## Die drei empirischen Fragen

Die README nennt sie *„the line between believing in the substrate and
demonstrating it."*

**1. Liest Kadmos v2 dichter als Chunking?** Unbeantwortet, und die Frage ist
schlechter gestellt als sie aussieht: es gibt **zwei** Kadmos v2
(`kadmos/reader.py`, kognitiv, mit totem Ähnlichkeitskanal; und
`mesh/ingestion/kadmos_v2.py`, produktiv, aber *„paradigmatisch v1: zustandslos
je Absatz"* — Tiefenaudit Juli). Das, was das Founding-Mesh gelesen hat, ist das
zweite. `TARGET_ARCHITECTURE` führt die Frage als *Monkey 1* mit Stand *„Kadmos v1
baseline established (0.49 ratio). True Nous not yet implemented."* Das ist noch
der Stand.

**2. Schlägt Spreading Activation kNN bei hoher Kantendichte?** **Ja, gemessen —
das eine demonstrierte Ergebnis des Projekts.** Auf zurückgehaltenen
HippoRAG-Fragen, Konfiguration ohne Blick auf sie gewählt: **+0,102 Recall@5 auf
2Wiki**, +0,030 HotpotQA, kein Einbruch auf PopQA. Und der Weg dorthin war
lehrreich: die erste Messung fand *exakte Parität*, und die war ein
Seeding-Artefakt (Seed-Retention 1,000, Rettungsrate 0,000). Der Vorteil lebt
bei engem Seeding — was diese Sitzung auf dem Founding-Mesh bestätigt hat
(k_seeds=1: 87 %, k_seeds=5: 78 %, k_seeds=32: 59 %).

Zwei Einschränkungen, die dazugehören. Das Retrieval auf dem Founding-Mesh liegt
bei 87 % Recall — aber der **Antwortschritt** bewegt sich nicht, egal was das
Retrieval liefert, und das Instrument, das das messen soll, hat auf seiner
mesh-unabhängigen Kontrollgruppe **neun Punkte Streuung** (43–52 %) und ein
Gold-Set, das eine Dopplung belohnt, die das Substrat entfernen soll (PHX-1098).
Der Korpus ist Hesiod, und das Modell hat Hesiod gelesen; die Hälfte jedes
Antwort-Ergebnisses ist Vorwissen. **Auf diesem Korpus lässt sich die zweite
Frage für den Antwortschritt nicht mehr entscheiden.** Für das Retrieval ist sie
entschieden.

**3. Erzeugt das MNLM Schlüsse, die in keiner Quelle stehen?** Nicht getestet.
Blockiert auf H100-Rechenzeit (PHX-1035). Und der Falsifikator hat einen
strukturellen Falsch-Positiv-Kanal, den das Tiefenaudit benannt hat: das Modell
schreibt in den Index, den der Grader liest, und Llama kennt Wikipedia. Die
Ablation-Kontrollen (frozen-mesh, parametric-only) stehen inzwischen im Brief
§6.2 — aber die Frage bleibt die einzige der drei, zu der es keine einzige Zahl
gibt.

**Bilanz: eine von drei beantwortet, für das Retrieval.** Das ist mehr, als die
meisten Projekte dieser Größe vorweisen können, und weniger, als die README
suggeriert, wenn sie die drei Fragen als *„next milestones"* nebeneinanderstellt.

## Wo die Doktrin selbst korrigiert werden muss

Die Inventur fand vor allem Implementierungslücken. An vier Stellen fand sie
etwas anderes: Sätze im Triplett, die so nicht stehen bleiben können, weil die
Messung ihnen widerspricht.

1. **Tier-modulierter Zerfall.** MESH_SUBSTRATE §2: höhere Stufen tragen
   *„gentler decay exponents"* (k=2 → 1,5 → 1,2 → 1). Für `0 < w < 1` gilt
   `w^1,2 > w^2`; der kleinere Exponent entfernt *mehr*. Am Mediangewicht 0,3112
   verliert k=1,2 das 2,5-fache von k=2. Alle Gewichte liegen unter 1, weil
   `w_max` sie dort hält. **Die Leiter ist im Gewichtsbereich, den das Substrat
   bewohnt, verkehrt herum.** Entweder Gewichte dürfen über 1 leben
   (Renormalisierung), oder die Modulation muss anders formuliert werden
   (z. B. λ je Tier statt k je Tier).
2. **Die Aktivierungsschwelle.** MESH_IMPLEMENTATION §„Damping and stop
   conditions" und ROADMAP: *„propagation halts at min_activation (~0.05)"*. Die
   Zahl ist für `x_{t+1} = damping · A · x_t + injection` kalibriert. Was läuft,
   ist PPR, massenerhaltend, auf einer anderen Skala: im Median erreichen 9 von
   50 Knoten 0,05. Die Zahl gehört zu einem Operator, der nicht ausgeliefert ist.
3. **„Typically 10–30 % of edges have any descriptor populated."**
   (MESH_IMPLEMENTATION §„Edges"). Gemessen auf jedem Mesh im Repo: **100 %** —
   94.490 von 94.490, 984.070 von 984.070. Der Satz beschreibt eine
   Extraktion, die es nicht gibt; die Folge ist, dass die Metadaten-Tabelle so
   groß ist wie der Kantentensor und ein kalter `mesh ask` 352 ms für ihren
   Aufbau zahlt.
4. **`fired_recent` ist ein „rolling window counter"** ohne Fensterlänge, und
   nichts im Triplett sagt, ob ein Quellanker feuert. PHX-1101 hat beides
   entscheiden müssen (γ=0,9, unbegründet; Anker ja, gemessen) — die Doktrin
   sollte es nachtragen, statt die Antwort in einem Ticket zu lassen.

Dazu, aus dem Tiefenaudit vom Juli und unverändert: die Tier-1-Arithmetik in
`CHRONIK_SCALE` geht nicht auf (CSR 95–250 GB gegen 80 GB GPU), und
MESH_IMPLEMENTATION widerspricht sich bei der Kantenzahl (10⁹ gegen 10¹⁰).

## Was in der README nicht mehr stimmt

Der Abschnitt *„Where we are — honestly"* ist das stärkste Stück der README, und
genau deshalb müssen seine Sätze stimmen. Fünf davon tun das nicht mehr, oder
nicht so, wie sie dastehen. Hier stehen sie mit dem Beleg — **nicht geändert**,
weil die README Jakobs Stimme ist und weil der Umfang dieser Seite ein Dokument
war, nicht zwei.

| README sagt | Stand | Vorschlag |
|---|---|---|
| *„Lifelike dynamics — Hebbian strengthening, super-linear decay, bounded saturation, atrophy decoupled from deletion, homeostatic renormalisation."* | einer von fünf läuft | *„Lifelike dynamics — super-linear decay runs; Hebbian strengthening is wired and at the shipped calibration cannot hold an edge against one tick of decay (PHX-1102); saturation, atrophy and renormalisation are specified and unbuilt (PHX-1100)."* |
| *„A continuous Oneiros process scores and promotes knowledge"* | Gen-1-Worker; der Mesh-Tick ist unscheduled; nichts wurde je befördert (`consolidation_tier` = 1 überall) | *„A continuous Oneiros process runs on the Gen-1 store; the mesh tick is invoked by hand (`mesh tick`), and tier promotion has an input only since PHX-1101."* |
| *„The learning loop closes … Query → reinforcement → tick → denser mesh now runs end to end"* | läuft end-to-end, wurde nie ausgeführt, kann keine Kante erzeugen, und ist 17–254× zu schwach | *„The learning loop is wired end to end and has never run on the founding mesh: all 14 ticks drained zero reinforcement, and at the shipped α/λ a single query's strongest delta is 17× smaller than one tick of decay (PHX-1102). It cannot create edges; the create branch is unreachable from the query path."* |
| *„one continuous Oneiros 'dream' pass improved held-out link-prediction MRR by +34.8 %"* | in-memory-Simulation, schreibt nie zurück | *„an in-memory simulation of the dream pass, using the substrate's real tick functions on a copy, improved held-out MRR by +34.8 % — no mesh was changed by it."* |
| *„recall over them runs 74 % at the default 50-node constellation"* | 80 % am Default, 87 % bei k_seeds=1 (konsolidiert) | Zahl aktualisieren und den Seed-Befund nennen (PHX-1099). |

Und ein Satz, der fehlt: **dass die Konsolidierung existiert** (PHX-1097) und
dass die Inventur öffentlich ist. Das eine ist das Substrat, das zum ersten Mal
seine eigene Identität geklärt hat; das andere ist die ehrlichste Statuszeile,
die dieses Projekt je hatte.

`llms.txt` trägt dieselben Sätze in kürzerer Form und dieselben Fehler.

---

## Was Gen 1 ehrlich verspricht

Die Vision ist nicht falsch geworden. Was die Inventur gezeigt hat, ist der
Abstand zwischen dem Satz *„the mesh is alive"* und dem Stand — und dass dieser
Abstand aus **Sensorik** besteht, nicht aus Einsicht. Mehrere Organe sind gebaut
und an Messfühler angeschlossen, die nie eingebaut wurden. Seit heute ist der
erste eingebaut.

Also, neu formuliert, was das Substrat in Gen 1 verspricht — jeder Satz belegt:

> **Gen 1 ist ein Substrat, in das gelesen und aus dem aktiviert wird.**
> Es hält Wissen als Vektoren und gewichtete Kanten, ohne Rohtext als Nutzlast,
> und die Aktivierung darüber schlägt Nearest-Neighbour auf Mehrsprung-Fragen —
> gemessen auf zurückgehaltenen Fragen, mit einer Konfiguration, die ohne Blick
> auf sie gewählt wurde.
>
> **Es vergisst.** Superlinear, jeden Tick, jede Kante.
>
> **Es konsolidiert auf Anweisung.** Ein Pass, der Entitätskandidaten mit einem
> Sprachmodell zusammenführt, die Beschreibung neu erzeugt und jede Absorption
> im Audit hinterlässt.
>
> **Es merkt sich, was es benutzt hat.** Seit heute — und noch liest nichts
> daraus.
>
> **Es lernt nicht aus Benutzung, es heilt nicht, es befördert nicht.** Die
> Organe dafür sind zum Teil gebaut, ihre Kalibrierung ist es nicht, und die
> Doktrin, nach der sie gebaut wurden, braucht an vier Stellen eine Korrektur.
>
> **Und es sagt das alles selbst.** Jede Behauptung über dieses Substrat ist
> gegen eine Kontrolle gemessen, jeder Fehlschlag ist als Ticket abgelegt, und
> die Inventur dessen, was läuft, ist öffentlich. Das ist das eine Versprechen,
> das Gen 1 heute vollständig hält.

Das ist weniger als *„a language model turned inside out"* und mehr als *„a very
good RAG"*. Es ist ein Lese-Substrat mit dem Skelett eines lebenden, dessen
Herzschlag noch nicht gemessen wurde — und dessen erster Herzschlag die nächste
Arbeit ist ([`PHX-1102`](../../phoenix-backlog/PHX-1102.yaml)).

## Was das für die Reihenfolge heißt

Nichts Neues gegenüber der Inventur, nur bestätigt aus der Vision heraus: Das
Verb, das der Vision am meisten fehlt, ist *lernt*. Der Weg dorthin ist
Aktivierungsgedächtnis (gebaut) → Zerfall nur auf Ungefeuertes und α gegen λ
(PHX-1102) → Renormalisierung, damit die Tier-Leiter das Richtige tut. Splits,
Pathologie und Therapie danach — sie lesen aus einer Geschichte, die seit heute
erst geschrieben wird.
