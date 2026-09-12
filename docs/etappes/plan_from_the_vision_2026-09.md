# Der Plan aus der Vision — September 2026

*2026-09-03. Grundlage: die ursprüngliche, umfassende Vision — `PHILOSOPHY.md`,
`docs/VISION.md`, `PANTHEON_VISION.md`, `DEEP_TECH_VISION.md`,
`TARGET_ARCHITECTURE.md`, `CHRONICLE_PRINCIPLES.md`, `CURIOSITY.md`, `HIVE.md`,
`ROADMAP.md`, `BUILD_DOCTRINE.md`, die Migrationspläne — Satz für Satz gegen das
gehalten, was dieses Repository seit August gemessen hat. Die Ledger mit allen
620 Aussagen, je mit Quelle, Beleg und Status, liegt daneben:
[`vision_claims_ledger.json`](vision_claims_ledger.json). 258 davon sind
tragend; 61 sind widerlegt, 170 teilweise bestätigt, 171 bestätigt, der Rest
offen, unprüfbar oder Wert.*

## Wie dieser Plan zustande kam

Die Doktrin-Inventur (PHX-1100) hat gemessen, welche *Mechanismen* laufen. Sie
sagt nichts darüber, welche *Versprechen* die Vision damit hält oder bricht —
und die Vision ist der Grund, aus dem alles gebaut wird. Diese Seite geht den
umgekehrten Weg: von der Vision zur Messung, und daraus zur Reihenfolge.

Vier Entscheidungen, die offen standen, sind unterwegs getroffen und umgesetzt
worden, jede mit ihrer Zahl:

- **Die Konsolidierung ist auf `data/mesh-founding` angewandt.** Retrieval
  84 → 87 %, 36 → 39 volle Fragen; die Identität von 68 Kandidaten ist geklärt;
  von den zwei Antwort-Verlusten waren zwei Scorer-Artefakte. Das alte Mesh
  liegt unter `data/mesh-founding.pre-consolidation-2026-09-02`.
- **`DEFAULT_K_SEEDS` ist 1** — aber nur, weil das Mesh ein anderes ist. Mit
  PHX-1091s eigenem Tune/Test-Protokoll (drei Mischungen, beide Richtungen):
  auf dem *alten* Mesh verliert `k=1` zurückgehalten in 3 von 6 Splits, auf dem
  *konsolidierten* wird es in 6 von 6 gewählt und gewinnt in 5 von 6
  (+0,092 · +0,087 · +0,071 · +0,109 · 0,000 · +0,159). Die Entscheidungen
  hängen zusammen; allein wäre die zweite falsch gewesen.
- **Alle 1.206 `raw_text_ref` zeigen wieder auf eine Quelle** —
  `gutenberg_348#p1..1210` statt eines gelöschten Sitzungsverzeichnisses
  (PHX-1103). Das Substrat kann zum ersten Mal seit dem Volllauf einen Chunk
  wieder herleiten.
- **`constraints.txt` pinnt die Pakete, an denen das Repo viermal gebrochen
  ist**, und wird in CI und Install-Zeile mit `-c` installiert (PHX-1076).
  pyproject bleibt lose.

Dazu sind die fünf falschen Sätze der README-Statussektion korrigiert, und
`llms.txt` mit ihnen.

## Die Vision in sieben Verben

Was die Vision dem Substrat zuspricht, lässt sich auf sieben Verben bringen.
Jedes gegen die Ledger:

| Verb | Vision | Stand | Beleg |
|---|---|---|---|
| **liest** | Nous liest wie ein Mensch — Satz für Satz, mit Arbeitsgedächtnis, revidierend | Kadmos v2 liest zustandslos je Absatz; es gibt zwei Kadmos v2; Monkey 1 nie gelaufen | TARGET_ARCHITECTURE:158, ROADMAP:32 |
| **aktiviert** | kein Nachschlagen, Aktivierung; Konstellation statt Dokument | **bestätigt** — die Primitive auf jedem echten Pfad; +0,102 Recall@5 gegen kNN auf zurückgehaltenem 2Wiki | TARGET:102, qa_benchmark |
| **erinnert sich / lernt aus Benutzung** | jede Interaktion stärkt oder schwächt; das System wird durch Gebrauch besser | seit PHX-1101/1102: hält, was es benutzt; auf 2Wiki +1,3 auf Benutztem, **−1,5 auf Zurückgehaltenem** | PHILOSOPHY:108, heartbeat_2wiki |
| **träumt** | Oneiros läuft ununterbrochen, schreibt dichtere Verbindungen zurück | **widerlegt als Prozess**: kein Scheduler, der Erzeugungs-Zweig unerreichbar; die +34,8 % sind eine Simulation im Speicher | PHILOSOPHY:100-102, VISION:84 |
| **heilt** | Immunsystem, Widerspruchsauflösung, Beförderung nach Mneme | **nein** — kein Symptom, keine Therapie, keine Beförderung, und *kein Widerspruch darstellbar* | VISION:34, PANTHEON:244 |
| **wächst, wo hingeschaut wird** | die Neugier-Schleife: Aufmerksamkeit wird Akquise | Gen-1-Skelett; auf dem Mesh nichts | CURIOSITY:5-17 |
| **denkt innen** | das MNLM denkt *im* Mesh, Vektoren rein, Vektoren raus | blockiert auf GPU; kein einziger Messwert | ROADMAP:212, PHX-1035 |

Zwei Verben tragen, drei sind gerade erst angeschlossen, zwei existieren nur
als Dokument. Das ist ehrlicher als *„the mesh is alive"* — und es ist mehr, als
vor vier Wochen wahr war.

## Der eine Befund, der die Reihenfolge festlegt

Die Ledger enthält 61 widerlegte Aussagen. Die meisten sind Mechanismen, die
nicht gebaut sind — das wusste die Inventur. Fünf davon sind etwas anderes: sie
sind **Nicht-Verhandelbares** aus `PANTHEON_VISION` §„Non-Negotiable
Principles", und sie scheitern nicht an fehlendem Code, sondern am
**Datenmodell**:

| Nicht-verhandelbar | Stand im Mesh |
|---|---|
| 2 — Widerspruch, Unsicherheit, konkurrierende Deutungen bleiben erhalten | keine Darstellung eines Widerspruchs, nirgends; `relation_kind` hat 10 Werte, keiner ist *contradicts* |
| 3 — Zeit ist intrinsisch: Wandel, Ablösung, Erwartung, Zerfall | nur Zerfall; `temporal_vector` ist auf jedem Knoten `None`; keine Gültigkeit, keine Ablösung |
| 1 — jede Aussage trägt Ursprung, Basis, Revisionspfad | Provenienz ja (seit heute wieder lebendig), Revision nein: Kanten haben weder Vertrauen noch Autor noch Geschichte |
| 5 — Autorität, Zugriff, Verantwortung maschinenlesbar | kein Feld dafür, in keinem Schema |
| „Chronik statt Enzyklopädie" — das Neue, Umstrittene, Abgelöste darstellbar | Gen 1 hatte `DISPUTED` als Status; das Mesh hat es nicht mehr |

Die MESH-Doktrin hat das alles in ein Feld verlegt: `frame_vector`, die
epistemische Haltung eines Knotens — Behauptung, Verneinung, Hypothese,
Widerspruch. Und `frame_vector` ist heute eine gesalzene SHA-256-Projektion des
Labels (PHX-1095). Der Frame trägt einen Hash, keine Haltung.

**Das ist derselbe Befund wie PHX-1101, eine Ebene höher.** Dort führte das
Substrat kein Gedächtnis seiner eigenen *Aktivität*, und alles, was daraus las
— Beförderung, Replay, Zerfall-Gating, RL — konnte nicht laufen. Hier führt es
kein Gedächtnis des *Widerspruchs*, und alles, was daraus lesen müsste —
Athene, Chronos, das Immunsystem, die Chronik, Metis' Voraussetzungen, die
zweite Säule „Wissenschaftlicher Arbeitstisch" — kann nicht laufen. Das Verb
*heilt* ist nicht ungebaut. Es ist unbaubar, bis das Substrat weiß, was ein
Widerspruch ist.

## Der Plan — vier Spuren, in dieser Reihenfolge

### A. Sicher lernen — die Renormalisierung (PHX-1106)

Das Verb *lernt* ist angeschlossen und verdrängt. MESH_SUBSTRATE §6 sieht die
Gegenkraft vor; die Ledger sagt, sie ist nicht gebaut; der 2Wiki-Herzschlag
sagt, sie wird gebraucht (−1,5 auf Zurückgehaltenem über 50 Runden). Ein
Tick-Schritt nach dem Zerfall, der das Gewicht je Knoten auf eine Zielsumme
hält. Repariert nebenbei die verkehrte Tier-Leiter.

*Fertig, wenn:* auf 2Wiki über 50 Runden benutzt ≥ +1 und zurückgehalten ≥ 0 —
und dasselbe auf HotpotQA und mit einem zweiten Seed, damit zwei Fragen Effekt
nicht die ganze Last tragen. Eine bis zwei Sitzungen.

**Ergebnis (2026-09-12, [`renormalisation.md`](renormalisation.md)):** gebaut
und gemessen, die Bedingung so nicht erfüllt — und zwar von der Baseline
nicht: der Gewinn +1,3 aus PHX-1104 war ein Seed (+0,3 auf HotpotQA, −0,7 mit
Seed 1). Was über beide Datensätze und beide Seeds hält, ist die Verdrängung
(−1,5 / −2,3 / −2,3), und die globale Renormalisierung *mit Kappe* hebt sie
jedes Mal auf (+1,5 / −0,7 / +0,7) für einen halben Punkt auf dem Benutzten.
Ohne Kappe ist §6 unsichtbar und dann ein Verstärker (−3,8). `mesh tick` läuft
jetzt standardmäßig damit, Sollwert 0,9 der Eintrittsmasse. Das Verb *lernt*
bleibt bei *hält, ohne zu verdrängen*; ob es je *gewinnt*, entscheidet nicht
die Dynamik, sondern der Erzeugungszweig (PHX-1100), der unerreichbar ist.

### B. Das Gedächtnis des Widerspruchs (PHX-1107)

Der Befund oben, als Bauplan. Nicht das ganze Immunsystem — die Voraussetzung
dafür, die alle heilenden Verben teilen:

1. **Echte Frames.** Kadmos gibt je Chunk und je Relation eine epistemische
   Haltung aus — behauptet, verneint, hypothetisch, bestritten, abgelöst —
   und der Vectorizer projiziert sie in den 64-d Frame-Raum über eine feste
   Basis statt über einen Hash. Damit wird Frame-Routing von inert zu
   wirksam, ohne eine Zeile im Retrieval zu ändern: der Mechanismus wartet seit
   S3 auf sein Signal.
2. **`contradicts` und `supersedes` als `relation_kind`**, mit `valid_from` /
   `valid_to` auf der Kante — die kleinste Darstellung von Zeit, die
   Nicht-Verhandelbares 3 erfüllt. Kein neues Schema; die Felder sind frei.
3. **Ein Widerspruchs-Gold-Set** auf dem Founding-Korpus. Hesiod widerspricht
   sich selbst (die Geburt der Aphrodite, die Eltern der Musen); der Demo-Beat 2
   hing seit PHX-1045 an genau so einer Frage.
4. **Den Founding-Korpus neu lesen**, mit Frames. 1 h 41 min, € 0,26 — der
   billigste Weg, ein Substrat zu bekommen, das weiß, was es bezweifelt.

*Fertig, wenn:* eine Widerspruchsfrage aus dem Gold-Set beide Seiten in der
Constellation zurückgibt, Frame-Routing auf dem neu gelesenen Mesh eine
messbare Wirkung hat (Recall auf dem Widerspruchs-Set mit gegen ohne), und das
Verb *heilt* zum ersten Mal einen Eingang hat, auf dem Athene etwas finden
könnte. Drei bis fünf Sitzungen.

### C. Das Instrument — fortlaufend, klein

Alles oben wird nur sichtbar, wenn das Instrument es sehen kann. Drei Dinge,
jedes eine halbe Sitzung: die Gold-Aliase (PHX-1098, damit „Helios" nicht
„Helius" verfehlt); der Antwort-Arm auf einem Korpus, den das Modell nicht
auswendig kann (HippoRAG, wo die Kontrollgruppe nicht bei 50 % steht); und das
Widerspruchs-Gold-Set aus B als drittes Instrument neben Retrieval und Antwort.

### D. Nous — das Lesen mit Arbeitsgedächtnis (Monkey 1)

Das erste Verb der Vision und ihre Phase 1. Es steht hier hinten, nicht weil es
weniger wichtig wäre, sondern weil die Messung sagt, wo es zahlt: bei
Passagen-Seeding ist die Konstruktion fast unsichtbar (±0,01), bei
Entitäts-Seeding entscheidet sie (+0,18). Der bessere Leser lohnt sich dort, wo
die Antwort eine Entität oder ein Pfad ist — und das Instrument dafür entsteht
in B und C. Nous vorher zu bauen hieße, es nicht messen zu können.

## Was bewusst nicht als Nächstes kommt

- **Das MNLM** (Phase 4, Monkey 3): auf H100-Rechenzeit blockiert. Der
  Falsifikator hat inzwischen die Ablation-Kontrollen, die das Tiefenaudit
  verlangte. Sobald Rechenzeit da ist, ist der Brief bereit; bis dahin ist jeder
  Satz darüber ein Versprechen.
- **Die Neugier-Schleife auf dem Mesh**: braucht Stub-Erkennung, Auslöser,
  Dispatcher — und vor allem etwas, das die Akquise wieder ins Substrat schreibt.
  Nach B, weil neues Wissen zuerst als *bestritten* ankommen können muss.
- **Föderation, Sichtbarkeit, Tiers**: Nicht-Verhandelbares 5. Die Vision selbst
  sagt, nicht in Gen 1.
- **Der Agenten-Roster auf dem Mesh** (Argus, Athene, Chronos, Nemesis, Eris,
  Mnemosyne): der Gen-1-Code läuft auf dem Store, der abgelöst wird. Auf das
  Mesh portieren heißt, ihnen etwas zum Finden zu geben — B.
- **S4 und S6** (Backend-Abstraktion, Entfernung des Legacy-Pfads): 105 Dateien
  referenzieren das alte Schema. Reine Ingenieursarbeit, ohne die kein Vorhaben
  der Vision scheitert. Nach A und B, wenn das Mesh auf jeder Oberfläche das
  bessere Substrat ist.
- **Skalierung auf 4,81 M** (S2.5): der RAM-Fehler im Resolver ist echt und
  klein; er ist nicht das, was die Vision heute blockiert.
- **Chronese**: von `TARGET_ARCHITECTURE` selbst widerlegt — Vektoren sind das
  Medium, nicht eine kanonische Sprache. Bleibt Dokument.

## Korrekturen an Doktrin und Vision (PHX-1108)

Die Ledger nennt Sätze, die als Status formuliert sind und nicht mehr stimmen,
oder Annahmen, die als Tatsachen dastehen und gemessen widerlegt sind. Drei sind
heute korrigiert, weil sie reine Statuszeilen sind; der Rest steht im Ticket,
damit die Dokumente ihre Stimme behalten und trotzdem nicht lügen:

- `TARGET_ARCHITECTURE` §Monkey 2 — *„Not yet run"* → gemessen, +0,102.
- `TARGET_ARCHITECTURE` §Dichte — *„Minimum viable density 20:1"* → widerlegt
  in beide Richtungen: der Vorteil zeigt sich bei 7:1, und dichtere Brücken
  bewegen nichts.
- `CHRONICLE_PRINCIPLES` 12 — *„consolidation + immune system — live today"* →
  Konsolidierung seit 2026-08-31 als Pass, Immunsystem nein.
- Im Ticket: die Tier-Leiter (§2), die Schwelle 0,05, „10–30 % der Kanten mit
  Deskriptor", HNSW (es ist IVF-PQ), „append-only ledger" gegen
  Overwrite-und-Prune je Tick, „Oneiros läuft ununterbrochen" (VISION,
  PHILOSOPHY, CHRONIK_SCALE), das Fenster von `fired_recent`.

## Anhang — die tragenden Aussagen, die nicht mehr so stehen können

Aus den 258 tragenden Aussagen der Ledger die widerlegten, mit Quelle und dem
Beleg in einem Satz. Der Volltext steht in
[`vision_claims_ledger.json`](vision_claims_ledger.json).

| Aussage | Quelle | Beleg |
|---|---|---|
| Es gibt keinen nächtlichen Batch; Oneiros läuft ununterbrochen | PHILOSOPHY:100, VISION:84 | `run_minimal_tick` hat einen Aufrufer außerhalb der Tests, die CLI; der Worker mit Intervall treibt den Gen-1-Store |
| Oneiros schreibt dichtere Verbindungen zurück | PHILOSOPHY:102 | der Erzeugungs-Zweig ist vom Abfragepfad unerreichbar; jede der 94.490 Kanten stammt aus der Ingestion |
| Gutes Wissen wird nach Mneme befördert | VISION:34 | `consolidation_tier` = 1 auf jedem Knoten; keine Beförderung im Code |
| Q-IDs sind das stärkste Identitätssignal | CHRONICLE_PRINCIPLES:36, ROADMAP:67 | 127 von 130 waren konfabuliert; das Mesh hat keine mehr; der stärkste Korruptionsvektor, nicht das stärkste Signal |
| Widerspruch und Unsicherheit bleiben erhalten | PANTHEON:244 | keine Darstellung eines Widerspruchs im Mesh |
| Zeit ist intrinsisch | PANTHEON:248 | nur Zerfall; `temporal_vector` überall `None` |
| Autorität, Zugriff, Verantwortung maschinenlesbar | PANTHEON:256 | kein Feld, in keinem Schema |
| Redundanz-Kollaps: ein zweites Lesen fügt Kanten hinzu, keinen Knoten | PANTHEON:194 | sechs Zeus-Knoten, bis PHX-1097; `MergeNodes` ist ein MNLM-DTO, keine Substrat-Primitive |
| Ein Chronik wird nicht schwerer zu betreiben, je weiser sie wird | PANTHEON:228 | Konsolidierung ein Handlauf; MNLM blockiert; kein Arbeitsset, die ganze CSR im Speicher |
| Kadmos v2 liest mit Arbeitsgedächtnis und revidiert | TARGET:158 | der produktive Leser hat keinen Zustand über Absätze hinweg |
| Nous verdichtet über einen GNN-Encoder, Text nie als Zwischenmedium | TARGET:39 | kein GNN im Repo; Nous-Brief „ready for implementation" seit Mai |
| Mindestdichte 20:1, darunter schlägt SA kNN nicht | TARGET:113 | +0,102 zurückgehalten bei ≈ 7:1; Dichte-Sweeps flach |
| Ein Verbatim-Layer bewahrt Quelltext für Forensik und Zitat | DEEP_TECH:45 | von TARGET verboten; nur ein Zeiger, der bis heute tot war |
| Chronese ist die native Sprache; Graph, Vektor, Text sind Projektionen | CHRONESE:3 | TARGET sagt das Gegenteil, und TARGET ist bindend |
| Selbstverbesserung Stufe 1 (Konsolidierung + Immunsystem) ist heute live | CHRONICLE_PRINCIPLES:54, ROADMAP:274 | Konsolidierung seit 2026-08-31 als Pass; Immunsystem nein; heute korrigiert |
| Das Ledger ist append-only; Fehler werden abgelöst, nicht überschrieben | BUILD_DOCTRINE:65 | Knoten- und Kantentabellen werden je Tick mit `overwrite` geschrieben und auf Retention 0 geprunt |
| Diese Struktureigenschaften kosten nichts und machen Wachstum-mit-Fehlern reparierbar | BUILD_DOCTRINE:67 | ein Volllauf musste wiederholt werden, weil der Name beim Schreiben verworfen wurde; Chunks waren bis heute nicht herleitbar |
| Gen 1 setzt die Neugier-Schleife nicht um, aber so, dass sie ohne Neugründung nachrüstbar ist | CURIOSITY:11 | die Neugründung fand statt: der MESH-Pivot vom 2026-05-13 |
| Hestia hat ein stehendes Abonnement auf jeden Neugier-Auslöser | CURIOSITY:143 | HestiaLite wurde in W13 gelöscht; `hestia.py` ist ein Schema ohne Laufzeit |
| Der Oneiros-Tick läuft alle paar Minuten, mit Renormalisierung und gestuftem Zerfall | CHRONIK_SCALE:146 | kein Scheduler; nur k=2; keine Renormalisierung |
| Neo4j ist hinter dem Store-Protokoll vollständig reversibel | GEN1_LEGACY:588 | der Migrationsplan nannte die Diskrepanz strukturell und schrieb sechs Schritte |

---

## Nachtrag 2026-09-11 — Spur E: die latente letzte Meile (PHX-1109)

Anlass war Jakobs Frage nach den Berichten, dass Sprachmodelle ihr Denken
zunehmend in internen Schichten erledigen und keine lesbaren Zwischenschritte
mehr brauchen. Die Recherche ergab zwei Befunde, die man auseinanderhalten
muss:

- **Heutige Frontier-Modelle rechnen schon jetzt Wesentliches ohne Spur im
  Text.** Baherwani, Goldstein und Panda (Juli 2026) heben mit inhaltsleeren
  Fülltokens die Genauigkeit von 13 Frontier-Modellen um bis zu 13 Punkte;
  Wang (April 2026) nennt die latente Trajektorie die Arbeitshypothese des
  Feldes und den Text ihre Projektion; Anthropic übersetzt seit Mai
  Aktivierungen per Autoencoder in Sprache und findet dort, was die Kette
  verschweigt.
- **Architekturen ohne Text-Zwischenschritte funktionieren, aber klein.**
  Coconut (Meta) füttert den verborgenen Zustand zurück, ein kontinuierlicher
  Gedanke kodiert mehrere nächste Schritte zugleich. Rekurrente Tiefe (Huginn,
  3,5B) erreicht die Reasoning-Leistung deutlich größerer Modelle. LOTUS (Juni
  2026) schließt bei 3B zum expliziten Chain-of-Thought auf, bei 2,5- bis
  6,9-fach geringerer Latenz — und sagt zugleich, dass frühere latente
  Methoden über 1B zurückfielen. Kohli et al. (COLM 2026): rekurrente
  Transformer kombinieren in einem Vorwärtsdurchlauf Fakten, die im Training
  nie zusammen vorkamen. Kein Frontier-Lab hat einen latenten Reasoner
  ausgeliefert (Turing Post, Juli 2026).

**Was das für Theogony heißt, in vier Sätzen.** Die Richtung der Kernthese
wird respektabel, für eine andere Behauptung als unsere: Text ist auch *im*
Modell nicht das Medium. Bei uns läuft trotzdem alles durch Text, deshalb ist
VISION:44 („der Agent liest keinen Kontext, er empfängt Struktur") bei uns
ungemessen. Was latentes Denken wegnimmt, die lesbare Spur, ist genau das, was
ein Substrat mit Ursprung, Revisionspfad und lesbarem Widerspruch anbietet —
**das Substrat ist die Prüfspur, die latente Modelle nicht mehr erzeugen**, und
das gilt nur, wenn PHX-1107 existiert. Und die Konkurrenz wird schärfer: wenn
Modelle Fakten in den Gewichten komponieren, muss das Mesh zeigen, dass es
komponiert, was *gestern* gelesen wurde, mit Provenienz (Monkey 3).

**Spur E, nach B eingeordnet, heute begonnen, weil sie das Instrument nutzt,
das da ist.** xRAG (2024) zeigt: eingefrorener Retriever, eingefrorenes
Modell, kleiner trainierter Projektor, ein Dokument als ein Token. Auf uns
übertragen: Knotenvektoren aus bge-small-en, ein Projektor, der
Einbettungsraum eines offenen Kleinlesers; die Constellation wird zu weichen
Tokens plus Kantenstruktur statt zu einem Textblock. Drei Arme mit demselben
lokalen Leser, dieselbe Bewertung wie das Antwort-Instrument, untrainierter
Projektor als Kontrolle. Das MNLM-Brief hat diesen Weg als verwässert
abgelehnt; das Brief hat beim Horizont recht und bei der Reihenfolge nicht.

*Fertig, wenn:* die weiche Constellation gegen die Text-Constellation auf dem
Gold-Set gemessen ist, mit Streuung. Ein Nullergebnis ist ein Ergebnis. An der
Reihenfolge A → B ändert sich nichts: beide sind Voraussetzungen für jeden
Leser, ob Text oder latent.

**Ergebnis (2026-09-12, [`latent_mile.md`](latent_mile.md)):** der Vektor
kommt an, die Antwort nicht. Ein eingefrorener 3B-Leser liest aus dem
projizierten Knotenvektor die Identität des Knotens (2,4 gegen 6,8 nats je
Namens-Token mit dem richtigen gegen einen fremden Vektor, auf ungesehenen
Knoten), bildet aber aus fünfzig solchen Tokens keine Antwort: streng bewertet
Text 49 %, Vorwissen 14 %, Vektoren 9–11 %, gegen den Text auf keiner Frage
besser. Gebaut ist xRAG Stufe 1; der Hebel ist Stufe 2, Instruktionstuning
mit Selbst-Destillation, und die braucht Frage-Antwort-Daten jenseits des
Gold-Sets. VISION:44 zerfällt in „receives structure" (ja) und „no text
translation required" (auf dieser Skala nein). Spur E bleibt nach B; die
Reihenfolge ändert sich nicht. Nebenbefund fürs Instrument: 30 der 111
Gold-Namen stehen in der eigenen Frage (PHX-1098).
