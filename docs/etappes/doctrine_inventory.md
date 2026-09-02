# Was vom lebenden Substrat tatsächlich läuft — eine Inventur

*2026-08-31. Gegen `data/mesh-founding` (5.002 konsolidierte Knoten, 94.490
Kanten, 1.206 Chunks, 14 Ticks) und den Stand von `main` nach PHX-1097.*

## Warum es diese Seite gibt

Fünfmal in den letzten Wochen bin ich beim Arbeiten an etwas anderem über einen
Doktrin-Mechanismus gestolpert, dessen **Eingabe niemand schreibt**: `decay_tier`,
die Aktivierungsschwelle, `frame_consistency`, der Frame-Routing-Aufrufer,
`fired_total`. Jedes Mal war der Fund ein Zufall, und jedes Mal wurde er dort
notiert, wo er auffiel — in einem Docstring, einem Kommentar, einem Ticket.

Die Vermutung war, dass das ein Muster ist und keine fünf Unfälle. Diese Seite
prüft das systematisch: für jeden Mechanismus, den die MESH-Doktrin vorschreibt,
läuft er?

**Was hier „läuft" heißt.** Implementiert *und* von einem echten Pfad aus erreicht
(`retrieve` / `ingest` / `tick` / ein CLI-Kommando) *und* seine Eingaben werden
tatsächlich erzeugt. Drei getrennte Fragen, und jede einzelne kann verneint
werden, während die anderen bejaht sind:

- implementiert, aber kein Aufrufer → **inert**
- aufgerufen, aber die Eingabe ist im ganzen Substrat konstant → **auch inert**,
  denn ein Zweig, der einen konstanten Wert liest, kann nichts unterscheiden
- nicht implementiert, und nicht implementierbar, weil eine Eingabe fehlt →
  **blockiert**

Ein Test, der etwas aufruft, macht es nicht lebendig.

**Methode und ihre Grenzen.** Fünf Leser haben je einen Doktrinbereich
aufgenommen; danach hat für jeden Bereich ein zweiter Durchgang versucht, jedes
„läuft nicht" zu **widerlegen** — Schreiber suchen, Aufrufer suchen, den Pfad
finden, der es doch funktionieren lässt. Ein falsches „das ist inert" ist hier
der teure Fehler: es schickt die nächste Arbeit auf etwas, das schon läuft. Von
110 Widerlegungsversuchen: **105 bestätigt, 4 nach oben korrigiert, 1 nach
unten**. Die vier Korrekturen stehen in der Liste unten drin.

Die Zahl 119 ist eine Zerlegungsentscheidung, keine Naturkonstante — ein
17-Schritte-Tick zählt hier als 17 Zeilen, ein Feld als eine. Das Verhältnis
9/119 ist deshalb weniger aussagekräftig als die Muster darunter. Die *Muster*
habe ich selbst nachgemessen, nicht übernommen.

## Der Bestand

| | MESH_SUBSTRATE | MESH_RETRIEVAL | MESH_IMPLEMENTATION | gesamt |
|---|---|---|---|---|
| **läuft** | 4 | 3 | 2 | **9** |
| teilweise | 6 | 2 | 16 | 24 |
| **inert** | 26 | 4 | 4 | **34** |
| **blockiert** | 8 | 1 | 1 | **10** |
| fehlt | 25 | 2 | 15 | 42 |
| | 69 | 12 | 38 | **119** |

Das Retrieval steht am besten da — es ist auch das einzige, an dem seit Monaten
gearbeitet wird. Die *Dynamik* des Substrats, also das, was es zu einem lebenden
Ding machen soll, steht am schlechtesten.

---

## Fünf Muster

### 1. Das Substrat kann nur vergessen

Das ist der schwerwiegendste Befund, und ich habe ihn selbst nachgemessen.

Der Zerfall läuft: 14 Ticks, λ=0,05, `Δw = -λ·dt·w²`, und die Wirkung ist im
Substrat sichtbar (Gewichte 0,2802–0,9049, der Modus bei 0,3112 reproduziert eine
Vorwärtssimulation über 14 Ticks). Die Hebbsche Verstärkung — das Gegenstück —
ist verdrahtet, durchgehend bis zum Tick, und **hat auf diesem Mesh nie
gefeuert**: alle 14 Tick-Records im Audit-Log tragen `delta_drained: 0`, und die
Sidecar-Datei ist leer. Jedes der 94.490 Gewichte ist reine Ingestion plus
Zerfall.

Das allein wäre nur „niemand hat das Flag gesetzt". Der eigentliche Befund ist
die **Kalibrierung**. Acht echte Abfragen mit `hebbian=True` gegen das lebende
Substrat schrieben 512 Deltas:

    stärkstes Delta einer Abfrage      2,9 · 10⁻⁴
    Median-Delta                       1,9 · 10⁻⁵
    ein Tick Zerfall (Mediangewicht)   4,8 · 10⁻³

**Die stärkste Verstärkung, die eine einzelne Abfrage einer Kante geben kann, ist
17-mal kleiner als ein Tick Vergessen. Im Median 254-mal.** Und der Tick zerfällt
*jede* Kante, während eine Abfrage nur die wenigen berührt, die sie aktiviert.

„Fire together, wire together" steht in der Doktrin als erste der fünf Primitiven.
Sie ist gebaut, sie ist erreichbar, und bei den ausgelieferten Parametern kann sie
gegen den ausgelieferten Zerfall nichts halten. α und λ wurden nie gegeneinander
gemessen.

Dazu kommt: der Zerfall ist **unbedingt**. Die Doktrin sagt „Kanten, die *nicht*
feuern, schwächen sich"; `decay_edges_inplace` zerfällt alle, und der Tick wendet
ihn *nach* dem Merge an — eine gerade verstärkte Kante wird im selben Durchgang
mitzerfallen. Ein Feuersignal, auf das man verzichten könnte, gibt es ohnehin
nicht (siehe Muster 2).

### 2. Siebzehn Felder halten im ganzen Substrat genau einen Wert

Gemessen über alle 5.002 konsolidierten Knoten und alle 94.490 Kanten:

| Feld | Wert überall | wofür die Doktrin es vorsieht |
|---|---|---|
| `fired_total`, `fired_recent` | 0 | Tier-Beförderung, Replay, Zerfall-Gating |
| `positive_feedback_total`, `negative_feedback_total`, `feedback_recent` | 0 | Drei-Faktor-RL |
| `eligibility`, `feedback_modulated_strength` | 0.0 | Eligibility-Traces, modulierte Plastizität |
| `decay_tier` | 0 | gestufter Zerfall |
| `frame_consistency` | 1.0 | Frame-Routing |
| `consolidation_tier` | 1 | Tier-Beförderung, Sättigungsbudgets |
| `consolidation_history` | leer | Alterskorrektur im Atrophie-Band |
| `structural_vector`, `temporal_vector` | None | Sub-Mesh-Matching, zeitliche Nähe |
| `activation_entropy`, `node_potential_cache` | None | Pathologie-Symptome, Pruning |
| `is_anchor` | False | eigene Anker-Klasse (eine `anchor_nodes`-Tabelle existiert nirgends) |
| `qids` | leer | die stärkste Identitätsspur der Doktrin |

Das sind nicht siebzehn Bugs. Das ist **ein** Befund: die Doktrin beschreibt ein
Substrat mit einem Gedächtnis für die eigene Aktivität, und **dieses Gedächtnis
wird nirgends geführt**. Alles, was daraus liest — Tier-Beförderung, Oneiros'
Replay zum Schutz des Seltenen-aber-Wichtigen, Argus' Pathologie-Überwachung, die
Eligibility-Traces des RL — liest eine Geschichte, die niemand aufschreibt.

`qids` steht aus einem anderen Grund in dieser Liste: die 130 einst vorhandenen
Q-IDs wurden entfernt, weil 127 davon konfabuliert waren. Das war richtig. Die
Folge ist, dass das stärkste der drei Identitätssignale der Doktrin auf diesem
Mesh gar nicht existiert — und `_ensure_consolidated_indexes` kann seinen
Vollständigkeits-Check deshalb nie bestehen und scannt bei **jedem** Öffnen des
Workspaces 836 ms lang die Knotentabelle.

### 3. Die Tier-Leiter ist dort, wo das Substrat lebt, verkehrt herum

Die Doktrin sagt: höhere Konsolidierungsstufen tragen **sanftere**
Zerfallsexponenten — Chunks k=2, Entitäten k≈1,5, Hubs k≈1,2 — damit
Arbeitsbegriffe verdampfen und Grundstruktur bleibt.

`decay_tier` ist 0 auf jeder Kante, also läuft immer k=2, und die anderen Zweige
sind unerreichbar. Das war bekannt (PHX-1095). Neu ist, was passiert, wenn man
das Feld ehrlich schreiben würde. Für `0 < w < 1` gilt `w^1,2 > w^2` — ein
*kleinerer* Exponent entfernt *mehr* absolutes Gewicht. Am tatsächlichen
Mediangewicht dieses Substrats (0,3112) und λ=0,05:

    k = 2    (Chunk)      Verlust je Tick  0,00484
    k = 1,5  (Entität)                     0,00863
    k = 1,2  (Hub)                         0,01226   ← 2,5× so viel

Und jedes Gewicht im Mesh liegt unter 1, weil `w_max = 1.0` es dort festhält.
**Die dokumentierte Tier-Modulation würde konsolidierte Struktur schneller
verdampfen lassen als Chunks.** Das Feld zu füllen wäre keine Reparatur; es wäre
die Umkehrung der beabsichtigten Wirkung. Der Mechanismus ist erst dann sinnvoll,
wenn Gewichte über 1 leben dürfen — was die globale Renormalisierung leisten
würde, die es nicht gibt (siehe unten).

### 4. Verdrahtet, aber ohne Unterscheidungskraft

Fünf Mechanismen laufen tatsächlich an und können trotzdem nichts bewirken:

- **Frame-Routing** wird von `retrieve.py:423` aufgerufen — aber nur, wenn ein
  `query_frame` übergeben wird, und **kein Aufrufer in `src/` oder `scripts/` tut
  das**: nicht die CLI, nicht das Cockpit, nicht der Benchmark, nicht das
  Demo-GIF. Es gibt kein Flag dafür. Schlimmer: die Frame-Vektoren des Mesh sind
  eine gesalzene SHA-256-Projektion des Labels (`vectorizer.py:_hash_projection`),
  also 4.977 verschiedene Hashes, keine epistemische Haltung. Routing darauf würde
  Kanten nach einem Hash maskieren.
- **Der Dämpfungsfaktor** (Doktrin: ≈0,5 als Abbruchbedingung) wird nur im
  `raw`- und `degnorm`-Zweig gelesen. Der ausgelieferte Operator ist `ppr`, der
  ihn nie liest — und `mesh ask` hat gar kein `--damping`.
- **Die maximale Hop-Zahl** (Doktrin: 3, nie über 5) gilt ebenso nur für
  `raw`/`degnorm`. `ppr` läuft 12 Iterationen, und `mesh ask --hops` wird in einen
  Zweig durchgereicht, den der Default nie betritt.
- **Die Sättigung** läuft bei jedem Tick und hat noch nie etwas abgeschnitten:
  Kappe 10.000 gegen einen gemessenen maximalen Ausgangsgrad von 1.093. Der
  begleitende `w_max`-Clamp ist gleich wirkungslos (größtes Gewicht 0,9049).
- **Die Aktivierungsschwelle** (Doktrin: ≈0,05 je Knoten) existiert im Code
  überhaupt nicht; die Zugehörigkeit zur Constellation ist `v > 0.0` plus Budget.
  Sie einzubauen wäre auch keine Reparatur — bei PPR erreichen im Median 9 von 50
  Knoten diesen Wert (PHX-1095).

### 5. Zwei Schreiber, kein Schloss, kein Schnappschuss

Die Doktrin verlangt Snapshot-Isolation für Lesevorgänge, gepufferte Schreibvorgänge
und einen **serialisierten** Oneiros mit genau einem Schreiber je Substrat.

Nichts davon hält. `_READ_CONSISTENCY = timedelta(0)` heißt „bei jeder Operation
neu prüfen" — das genaue Gegenteil eines gepinnten Snapshots, und bewusst so
(PHX-1093). `checkout`, `restore` und `as_of` kommen im ganzen Repo nicht vor, ein
Durchgang *könnte* also gar nicht pinnen. Und es gibt keine Sperre: weder
`filelock` noch `flock` noch ein Lockfile irgendwo in `src/`.

Dabei sind es inzwischen **zwei** ungeschützte Lese-Ändere-Schreibe-Zyklen über
das ganze Substrat — `run_minimal_tick` und, seit heute, `run_consolidation`, aus
verschiedenen Prozessen gleichzeitig erreichbar. Die Konsolidierung hat das in
ihrem eigenen Docstring notiert („die Reihenfolge ist der einzige Schutz, den es
gibt"), aber die Doktrin verlangt Serialisierung, und die gibt es nicht.

---

## Ein Nebenbefund, der eigene Aufmerksamkeit verdient

**Der einzige Zeiger des Substrats zurück auf seine Quellen ist tot.** Alle 1.206
Chunk-Knoten tragen ein `raw_text_ref` der Form

    /private/tmp/claude-501/…/scratchpad/fullread/batch_00.txt#p1

— 13 verschiedene Dateien in einem Sitzungs-Scratchpad, von denen **keine einzige
noch existiert**. `SourceProvenance.source_identifier` trägt denselben toten Pfad.

Die Doktrin nennt `raw_text_ref` ausdrücklich als das, woraus das Immunsystem oder
ein Oneiros-Tick einen Chunk abseits des heißen Pfads neu ableiten kann. Auf
diesem Mesh ist das unmöglich.

PHX-1084 hat genau dieses Problem für die **Quellanker** repariert und die
Ingestion nach vorn korrigiert (`source_identifier` ist jetzt
`gutenberg_{book_id}`). Die Chunk-Ebene des bestehenden Mesh wurde nie
nachgezogen. Es ist also kein Code-Fehler mehr, sondern ein unbereinigtes
Datenartefakt — auf dem Mesh, das die Demo zeigt.

---

## Was daraus folgt

Die Doktrin ist nicht falsch. Was fehlt, ist nicht Einsicht, sondern **Sensorik**:
mehrere der beschriebenen Organe sind an Messfühler angeschlossen, die nie
eingebaut wurden. Deshalb ist die Reihenfolge der nächsten Arbeit nicht beliebig.

**Zuerst das Aktivierungsgedächtnis.** `fired_total`, `fired_recent`,
`last_fired_at` auf dem Lesepfad zurückschreiben. Das ist wenig Code und entsperrt
vier Mechanismen auf einmal: Tier-Beförderung, gating-fähigen Zerfall, Oneiros'
Replay und die Eligibility-Traces. Ohne das sind Pathologie-Überwachung und
Therapie Instrumente, die etwas beobachten sollen, das nicht aufgezeichnet wird.

**Dann α gegen λ.** Die Hebbsche Verstärkung 17- bis 254-fach unter dem Zerfall zu
lassen und gleichzeitig „das Substrat lernt aus Benutzung" zu behaupten, ist die
Art Lücke, die dieses Repo sonst sofort aufschreibt. Entweder α anheben, λ senken,
oder den Zerfall auf ungefeuerte Kanten beschränken — aber gemessen, nicht
geraten.

**Und die Renormalisierung vor der Tier-Modulation.** Solange jedes Gewicht unter
1 liegt, dreht die dokumentierte Tier-Leiter ihre eigene Absicht um. Die globale
homöostatische Renormalisierung ist der Mechanismus, der Gewichte in einen Bereich
hebt, in dem die Leiter das Richtige tut — sie kommt also zuerst.

**Nicht als Nächstes:** Splits, Pathologie, Therapie. Alle drei lesen aus der
Aktivierungsgeschichte.

---

## Nachtrag, noch am selben Tag

**PHX-1101 ist gebaut**, und damit ist der erste Eintrag aus Muster 2 abgeräumt:
der Lesepfad zeichnet jetzt auf, welche Knoten ins Arbeitsset gelangt sind, die
Ingestion zeichnet jede Referenz auf einen bereits vorhandenen Knoten auf, und
der Tick faltet beides ein. `fired_total` ging auf einer Kopie des Founding-Mesh
über 47 Abfragen **von einem distinkten Wert auf 32** — Zeus 45, Theogony 43,
der Quellanker 41, Phoebus Apollo 40.

Die Aufnahme oben bleibt stehen, wie sie gemessen wurde. Sie ist der Zustand vom
31. August, und eine Inventur, die sich rückwirkend selbst korrigiert, ist keine.

Was das entsperrt: Tier-Beförderung hat jetzt eine Eingabe, der Zerfall könnte auf
ungefeuerte Kanten beschränkt werden (die doktrintreue Antwort auf PHX-1102),
Oneiros' Replay hat ein Signal, und die Eligibility-Traces haben eine Basis. Keins
davon ist damit gebaut — nur nicht mehr blockiert.

**PHX-1102, am Tag danach:** Muster 1 ist zur Hälfte abgeräumt. Der Zerfall
verschont jetzt, was gefeuert hat — die Regel aus MESH_SUBSTRATE §2, gemessen
als die einzige der drei Stellschrauben, bei der Benutztes hält (0,594 gegen
0,359 unter dem ausgelieferten Zerfall). Das Substrat kann nicht mehr *nur*
vergessen. Ob es *lernt*, sieht das Retrieval auf diesem Mesh nicht — zehn
Runden, kein Gold-Treffer bewegt — und warum, steht in
[`hebbian_calibration.md`](hebbian_calibration.md) und PHX-1104.

Was diese Aufnahme für die Vision bedeutet — welche Verben von *„the mesh is
alive"* heute stimmen, welche Sätze der README nicht mehr, und was Gen 1
ehrlich verspricht — steht in [`what_gen1_promises.md`](what_gen1_promises.md).

## Anhang — die vollständige Aufnahme

Nach Doktrindokument, innerhalb dessen nach Zustand. Jede Zeile trägt die kürzeste
wahre Begründung, meist mit `datei:zeile`. Sie ist auf 230 Zeichen gekürzt — die
Aufnahme sollte lesbar bleiben, und wer eine Zeile bezweifelt, findet den Beleg
schneller im Code als in einem längeren Zitat.

### MESH_SUBSTRATE.md — 69 Mechanismen (4 läuft · 6 teilweise · 26 inert · 8 blockiert · 25 fehlt)


**läuft**

- **description (ConsolidatedNode)** — Written at ingest for every node (kadmos_v2.py:385 via `_entity_description`, source_anchor.py:41-45) and read on real paths: it is the Constellation's display name (retrieval/constellation.py:64-71, 176) and it feeds the `consoli…
- **is_source_anchor (source-anchor entity class)** — Written by ingestion/source_anchor.py:36; live it partitions the mesh 1,219 anchors / 3,783 content nodes. Read on real paths and it changes behaviour: constellation.py:142 splits activated nodes into a separate anchor budget (`_P…
- **relation_descriptor (short relation label)** — Written on every edge; non-null on 94,490/94,490 live edges with 2,680 distinct values. Read on real paths: it is part of the edge identity used for dedup and delta merging (storage/edges.py:237, 490-498, 235-236 — keying by node …
- **tags (discriminating keyword cloud)** — Written at ingest (kadmos_v2.py:386 via `_concept_tags`, :523; source_anchor.py:46) and genuinely differentiating live: 1-7 tags per node, 7 distinct lengths across 5,002 nodes. Read on real paths — the tag-match linking signal (i…

**teilweise**

- **Agent-driven cleanup — Deduplication** — The *application* half exists and has run (consolidation.py:803-969; 48 clusters merged on data/mesh-s5-work, union of edges with weight-summing at :645-649, capped by `enforce_saturation` at :914, absorbed ids recorded at :933-93…
- **Hebbian update (w ← w + α·fire(i)·fire(j))** — Nothing structural — an opt-in flag nobody passes, plus an α/λ calibration that has never been measured against each other.
- **Oneiros operation B — Consolidation, Tier 0 → Tier 1** — Q-ID inheritance is blocked by there being no Q-IDs on the substrate at all.
- **Super-linear decay (dw/dt = -λ·w^k, k=2)** — Live and differentiating in its core: src/theogony/mesh/storage/edges.py:273-299 implements Δw = -λ·dt·w^k, called on every tick at src/theogony/mesh/runtime/oneiros_tick.py:413, driven by the real CLI `theogony mesh tick` (src/th…
- **Tick steps 8/9 — Compute and apply saturation evictions** — Called on every tick: oneiros_tick.py:414 → edges.py:310-334. Three documented parts are missing and the docstring says so (edges.py:315-319): no per-tier cap indexing, no companion weight-sum cap, no admission rule. Step 9's "app…
- **description_vector as a distinct identity-matching surface** — The linking signal itself IS live and load-bearing: src/theogony/mesh/ingestion/linker.py:114-127 scores it and the founding-mesh audit log records 7,281 `mesh_ingest_link_decision` rows with signals description=3,694, tag=633, em…

**inert**

- **ChunkNode.raw_text_ref (off-hot-path pointer for re-derivation)** — Written once, src/theogony/mesh/ingestion/kadmos_v2.py:322. `grep -rn raw_text_ref src/ scripts/ tests/` returns only schemas.py:56 and that line — no reader at all, including inside `run_consolidation`, which regenerates descript…
- **ChunkNode.source (SourceProvenance — immune-system anchor)** — Written at src/theogony/mesh/ingestion/kadmos_v2.py:317-321. No reader anywhere in src/, scripts/ or tests/ — nothing loads a ChunkNode and inspects `.source` (the store's only chunk reader is `get_chunk`, storage/nodes.py:237-242…
- **Edge.creation_context (asserted relation vs observed adjacency)** — Written on every edge at 11 sites in kadmos_v2.py (:335, :348, :427, :444, :480, :506, :546, :558, :578, :630, :658) and by the seed importer; live it is non-null on 94,490/94,490 edges with 8 distinct values (kadmos_paragraph_den…
- **Edge.decay_tier** — Independently confirmed live (already known): 0 on 94,490/94,490 edges, min = max = 0. Adding the upstream cause measured in my area: the derivation the code considers and rejects (storage/edges.py:284-293) is blocked because `Con…
- **Edge.description (free-text relation rationale)** — One writer, src/theogony/mesh/ingestion/kadmos_v2.py:470, which copies `relation.rationale`. That field defaults to "" (ingestion/reading_schemas.py:68) and the reading prompt never asks for it — the relations section of the syste…
- **Edge.eligibility (decaying recent-firing trace, credit assignment)** — The three-factor RL path as a whole — nothing propagates a firing trace or a reward.
- **Edge.feedback_modulated_strength (lifetime feedback audit)** — Same three hits and nothing more: schemas.py:113, storage/edges.py:50 (column), storage/edges.py:579 (serialisation). No writer, no reader, no test. Live: 0.0 on 94,490/94,490 edges.
- **Edge.frame_consistency** — The same missing frame encoder that leaves `frame_vector` a hash and `query_frame` unproduced.
- **Edge.last_fired_at (edge freshness / "edges that are not fired weaken")** — Set at creation and never advanced: `merge_edge_deltas` reinforces an existing edge with `cur.model_copy(update={"weight": nw})` only (storage/edges.py:254-259), leaving last_fired_at untouched, and `decay_edges_inplace` takes a u…
- **Edge.pids (Wikidata property identifiers)** — Genuinely written on two paths — kadmos_v2.py:476-480 at extraction and `_backfill_relation_pids` on every tick (oneiros_tick.py:86-91) — and 1,237 of 94,490 live edges carry one. But nothing reads the stored value. The one consum…
- **Edge.relation_kind (broader relation category)** — Written on every edge (kadmos_v2.py:333, 346, 425, 442, 468, 504, 544, 556, 576, 628, 656) and non-null on 94,490/94,490 live edges with 10 distinct values (co_occurrence 73,455; semantic 8,375; attribution 4,514; hierarchy 4,237;…
- **Hebbian edge creation between co-firing non-neighbours** — The create branch exists at src/theogony/mesh/storage/edges.py:260-269 (the `else` of the key lookup — a brand-new Edge with born_at/last_fired_at = now). It is unreachable from the production write path: the only producer of delt…
- **Node last_fired_at / node firing clock** — Set to creation time at every write site (kadmos_v2:314, linker.py:212, source_anchor.py:34, importer.py:180) and never advanced afterwards — no code path updates a node row on firing. The single non-write reference is `max(n.last…
- **Saturation — count cap per node** — Implemented and called: src/theogony/mesh/storage/edges.py:310-334, invoked every tick at src/theogony/mesh/runtime/oneiros_tick.py:414 with DEFAULT_MAX_OUT_DEGREE = 10,000 (edges.py:307), and again inside consolidation at src/the…
- **Three-factor reward modulation (1 + β · feedback)** — A consumer-supplied feedback value; MESH_RETRIEVAL's rater distinct from the consumer does not exist.
- **Tier-modulated decay (k=2 / 1.5 / 1.2 / 1 by tier)** — A writer for Edge.decay_tier (none in src/); node tiers are constant too (consolidation_tier == 1 on all 5,002 nodes), so a derivation would assign one constant; and correctness additionally requires §6 renormalisation to lift wei…
- **consolidation_history (when each tier promotion happened)** — Declared src/theogony/mesh/schemas.py:71. One writer, src/theogony/mesh/runtime/consolidation.py:591, and its own comment concedes the field's documented meaning is unavailable: "the substrate has no tier promotion to record (noth…
- **consolidation_tier ("1, 2, 3 — earned via Oneiros")** — Written as the literal `1` at all three creation sites (linker.py:213, source_anchor.py:35, seeds/wikidata5m/importer.py:181). Nothing ever increments it — no promotion code exists anywhere in src/. Live: 1 on 5,002/5,002 nodes. R…
- **description_generated_at / description_source_chunks (regeneration audit trail)** — Written at exactly one place, src/theogony/mesh/runtime/consolidation.py:893-899, inside the LLM-describer branch of `run_consolidation`. No reader anywhere in src/, scripts/ or tests/. Live: None and [] on 5,002/5,002 nodes — so …
- **frame_vector (both tiers) — epistemic-frame embedding** — No frame encoder exists. `query_frame` has no producer, and even with one the node side would be hashed label text.
- **is_candidate (entity-candidate flag; flips to False on convergence)** — Written True unconditionally for every node the linker creates (src/theogony/mesh/ingestion/linker.py:214) and left False on source anchors (source_anchor.py has no is_candidate) and on seeded nodes (seeds/wikidata5m/importer.py:1…
- **last_fired_at as an edge firing record** — `last_fired_at` is declared on Edge (src/theogony/mesh/schemas.py:107) and persisted (src/theogony/mesh/storage/edges.py:52, 581), but reinforcement never updates it: merge_edge_deltas strengthens an existing edge with `cur.model_…
- **node_potential_cache** — Declared src/theogony/mesh/schemas.py:92. Only occurrence outside the declaration is src/theogony/mesh/runtime/consolidation.py:593, setting it to `None`. Live: None on 5,002/5,002 nodes. The quantity is real and used, but compute…
- **positive_feedback_total / negative_feedback_total / feedback_recent** — Nothing supplies a feedback signal. `feedback` appears nowhere on the retrieval path; the CLI has no way to return a reward for a Constellation.
- **qids (Q-ID identity anchor, signal 1 of eager linking)** — A trustworthy entity linker. The lookup path (linker.py:311-333) is fully built and would work the moment a seeded or authoritative Q-ID existed; nothing on the reading path produces one.
- **source_url (machine-clean anchor on source-anchor entities)** — Written at src/theogony/mesh/ingestion/source_anchor.py:37. No reader: `grep -rn source_url src/theogony/mesh/` returns only the declaration (schemas.py:75) and that writer; the hits in cockpit/mesh_explorer.py:201 and reporting/m…

**blockiert**

- **Oneiros operation — Tier promotion (Tier 1 → 2 → 3)** — `fired_total`/`fired_recent` have no writer, and Argus's pathology checks are unbuilt — three of the four promotion gates have no input.
- **Saturation — Σ weight cap per node (S, 5·S, 20·S, 100·S)** — S, the substrate-wide weight unit, which doctrine defines via the §6 renormalisation target — and no renormalisation exists to set it.
- **Symptom 2 — Activation hysteresis** — Per-node activation history: `fired_total`/`fired_recent` have no writer, and there is no activation log.
- **Symptom 3 — Context promiscuity** — `activation_entropy` has no producer, and the per-query context diversity it would be computed from is not recorded.
- **Symptom 4 — Refutation absorption** — No refutation/veridicality marker on chunks, and no per-insertion Hebbian record to compare a frame against.
- **Symptom 5 — Saturation lockout for legitimate new input** — There is no admission barrier, so no rejection events exist to sample.
- **structural_vector (ConsolidatedNode)** — Nothing in the repo computes a topology embedding — no Node2Vec/GraphSAGE anywhere in src/. The tick (src/theogony/mesh/runtime/oneiros_tick.py:398-415) has no phase that would produce one.
- **temporal_vector (ConsolidatedNode)** — No temporal-anchor extraction exists on the reading path; nothing produces a date/interval representation for a node.

**fehlt**

- **Agent-driven cleanup — Contradiction resolution** — `grep -rni "contradict" src/theogony/mesh/` returns nothing. No `ContradictionFinding` type, no `CONTRADICTS` edge kind, no writer. Measured on the live mesh: `relation_kind` takes 10 values across 94,490 edges — co_occurrence 73,…
- **Agent-driven cleanup — False-information removal** — No `RemovalProposal` type in src/ (grep). No removal path: MeshNodeStore exposes only `replace_all_consolidated` (nodes.py:336), no per-node removal with an evidence trail. No removal audit action exists — the founding mesh's audi…
- **Agent-driven cleanup — Redundancy compression** — No `RedundancyProposal` type in src/ (grep). The nearest built thing, consolidation.py, is a different operation: it merges Tier-1 entity candidates by shared capitalised name (consolidation.py:298-309), not "many chunks making es…
- **Anchor-node class (pure index nodes)** — `is_anchor` is declared on ConsolidatedNode (schemas.py:73) and is `False` on all 5,002 founding-mesh nodes (measured); `grep -rn "is_anchor" src/` finds only the declaration — no writer. The three per-observation fields doctrine …
- **Atrophied nodes lose firing privileges during Spreading Activation** — No propagation gate on node potential or atrophy exists. src/theogony/mesh/runtime/spreading.py (49 lines, single function `spreading_activation` at line 17) has no threshold or mask. src/theogony/mesh/retrieval/propagation.py has…
- **Atrophy (node marked atrophied, not removed)** — There is no atrophy anywhere in the repository: `grep -rn "atroph" --include="*.py" .` returns **zero matches** across src/, tests/ and scripts/. No `atrophied` field on ConsolidatedNode (src/theogony/mesh/schemas.py:57-95) or on …
- **Global homeostatic renormalisation** — Nothing external — but a correct implementation must be landed together with a rethink of w_max, or the first correction destroys every weight distinction in the substrate.
- **Healthy band [μ − σ, μ + σ] over node potential, with age correction** — A specification that survives a right-skewed potential distribution; plus consolidation cycles for the age correction, which never run.
- **Oneiros operation A — Replay (bridge-biased edge firing)** — No bridge metric exists in src/ — `grep -rni "bridge" src/theogony/mesh/` hits only eval/qa_retrieval.py, which uses "entity-bridge" to mean a co-occurrence edge in a benchmark ablation, not a topological bridge score. The one rep…
- **Pruning under resource pressure (the pruner)** — Two inputs: an operator resource-ceiling signal (nothing produces one), and the set of atrophied nodes the pruner sorts first (atrophy does not exist).
- **Saturation admission rule (new edge must beat the weakest incumbent)** — No rejection path exists. merge_edge_deltas creates or strengthens unconditionally (src/theogony/mesh/storage/edges.py:256-269) with no reference to the target node's incumbent edges, and enforce_saturation runs afterwards (oneiro…
- **Saturation caps indexed by tier** — Node tier promotion (Tier 0→1→2→3), which docs/MESH_MIGRATION_PLAN.md:315 records as not built and blocked on fired_total/fired_recent having no writer.
- **Symptom 1 — Internal/external edge asymmetry** — No implementation and no caller: nothing in src/ computes an intra-region vs. cross-region edge ratio, and there is no region abstraction to compute it over (grep for pathology/region sampling returns only oneiros_tick.py:61-62's …
- **Therapy Stage 1 — Activation temperature** — Spreading Activation is deterministic SpMV with no sampling: src/theogony/mesh/runtime/spreading.py:17-49 (`x ← damping · Aᵀ · x`) and src/theogony/mesh/retrieval/propagation.py:111 `propagate`. `grep -rniE "boltzmann|softmax|temp…
- **Therapy Stage 2 — Dominance penalty** — A region's share of total activation is not tracked; `fired_total`/`fired_recent` have no writer.
- **Therapy Stage 3 — Forced refutation re-injection** — No refutation framing, no signed Hebbian update, and no Argus-to-mesh channel.
- **Therapy Stage 4 — Saturation demolition** — No implementation: nothing in src/ halves or zeroes a region's strongest internal edges. There is also no place to record the audit doctrine makes binding — the audit log's six live actions are ingest and tick only, and there is n…
- **Therapy Stage 5 — Quarantine / split** — No split implementation, no region abstraction, and no cross-tick confirmation state.
- **Tick step 12 — Compute pathology samples** — oneiros_tick.py:61-62 `stub_pathology_phase` raises; no caller. `grep -rni "pathology|mind.lock|hysteresis|promiscuity" src/` returns only that stub and two docstring mentions (oneiros_tick.py:4, consolidation.py:29). No sampler, …
- **Tick step 13 — Apply therapy actions** — oneiros_tick.py:65-66 `stub_therapy_phase` raises; no caller. No escalation state, no stage thresholds, no Mendel-risk logging anywhere in src/.
- **Tick step 4 — Apply renormalisation (conditional on drift threshold)** — `grep -rn "renormal" src/ scripts/ tests/` returns exactly one hit — src/theogony/mesh/runtime/consolidation.py:29, a docstring listing renormalisation among the things S5 has *not* built. There is no implementation, no stub, and …
- **Tick step 5 — Apply pending agent-driven cleanup actions** — Both ends are missing: no agent emits a substrate finding, and no table stores one.
- **Tick steps 10/11 — Compute and apply sub-node splits** — oneiros_tick.py:57-58 `stub_split_phase` raises `NotImplementedError`; grep across the repo finds no caller. There is no split code at all: no cluster detection over a hub's outgoing edges, no `w_HS = Σ w_i`, no `w_i / (1 - p_i)`,…
- **activation_entropy (spiral / context-promiscuity signal)** — Declared src/theogony/mesh/schemas.py:91. The only occurrence outside the declaration in all of src/ and scripts/ is src/theogony/mesh/runtime/consolidation.py:594, which sets it to `None` (a cache invalidation of a value never co…
- **is_anchor (anchor-node class: no Hebbian update, no decay, no split)** — `grep -rnw is_anchor src/ scripts/ tests/` returns exactly one hit in the whole repository: the declaration at src/theogony/mesh/schemas.py:73. (The tests/mesh/test_constellation_anchor_budget.py hits are a local variable of that …

### MESH_RETRIEVAL.md — 12 Mechanismen (3 läuft · 2 teilweise · 4 inert · 1 blockiert · 2 fehlt)


**läuft**

- **Diversified injection A — Maximum Marginal Relevance** — `mmr_order` (src/theogony/mesh/retrieval/diversified.py:49-82) is called by `select_seeds` (diversified.py:132), which is called by `retrieve` (retrieve.py:404-412) on all four real paths above. λ = 0.6 exactly as doctrine specifi…
- **Diversified injection B — weight-class stratification** — `class_seats` and `WeightClasses` (src/theogony/mesh/stratification.py:98-183 and :65-95) are called from diversified.py:143, reached from retrieve.py:404-412, with global class boundaries supplied by `MeshRuntime.weight_classes()…
- **Spreading Activation as the universal retrieval primitive** — `Propagator.propagate` (src/theogony/mesh/retrieval/propagation.py:111-163) is called at src/theogony/mesh/retrieval/retrieve.py:433, and `retrieve()` is reached from four real paths: `theogony mesh ask` (src/theogony/mesh/cli.py:…

**teilweise**

- **"Diversified injection (A + B) is *always* on" / nearest-neighbour seeding forbidden** — MMR and stratification are live (above), but they do not cover the seed set. `_name_anchor_seeds` (retrieve.py:211-293) looks up capitalised spans by label and injects up to 8 nodes at a flat weight of **1.0** (retrieve.py:289); t…
- **The modulated Hebbian rule (three-factor plasticity)** — a feedback signal `f_target` (no channel exists — see "Sources of feedback") and a per-edge propagation trace `s_ij` that `propagate` does not produce.

**inert**

- **Feedback storage — per-edge `feedback_modulated_strength`** — Declared on `Edge` at src/theogony/mesh/schemas.py:113, given an Arrow column at src/theogony/mesh/storage/edges.py:50, and persisted from the model default at edges.py:579. `grep -rn feedback_modulated_strength` over src/ returns…
- **Feedback storage — per-node `positive_feedback_total` / `negative_feedback_total` / `feedback_recent`** — All three are declared on `ConsolidatedNode` (src/theogony/mesh/schemas.py:93-95). There is no writer anywhere in src/. The single reader is the consolidation merge, which sums them into the merged node (src/theogony/mesh/runtime/…
- **Frame routing during Spreading Activation (frame-routed activation / masked SpMV)** — a frame encoder producing epistemic frames rather than a hash projection, plus a `query_frame` on some real caller (there is no flag, API parameter, or config to set one).
- **Relation-conditioned masked hop (`Propagator.relation_masked_hop`)** — a query-relation input on the retrieval API and a relation-restricted adjacency builder — neither exists anywhere in src/.

**blockiert**

- **Eligibility traces (multi-hop credit assignment)** — the per-edge propagation strength `s_ij(t)` — `Propagator.propagate` returns node activations only, so there is nothing to accumulate a trace from.

**fehlt**

- **Diversified injection C — sub-mesh injection (structural matching)** — Nothing exists. `grep -rni 'weisfeiler|wl_hash|submesh|sub_mesh|region_scor'` over src/ and scripts/ returns zero implementation hits — the only match in the repo is a disclaimer at scripts/mesh_relation_retrieval.py:11 ("This is …
- **Sources of feedback (LLM self-rating, downstream task success, explicit user rating, implicit signals)** — None of the four channels exists. **LLM self-rating** (doctrine's default, "every activation"): `grep -rni 'self_rating|self-rating|rater|f_target|reward'` over src/theogony/mesh/ returns one hit — the honesty note at retrieve.py:…

### MESH_IMPLEMENTATION.md — 38 Mechanismen (2 läuft · 16 teilweise · 4 inert · 1 blockiert · 15 fehlt)


**läuft**

- **Diversified seeding — MMR over per-vector ANN results plus weight-class stratification** — select_seeds runs on every retrieval (src/theogony/mesh/retrieval/retrieve.py:404-412), consuming real ANN hits from search_consolidated_by_vector (:361). MMR is genuinely implemented (diversified.py:49-82) and class seats are all…
- **Warm tier — LanceDB tables as source of truth** — MeshNodeStore creates/opens chunk_nodes and consolidated_nodes (src/theogony/mesh/storage/nodes.py:173-200); EdgeStore opens mesh_edges / edge_metadata / edge_dedup_index (src/theogony/mesh/storage/edges.py:466-479). Live on data/…

**teilweise**

- **Audit ledger — a record for every non-trivial Oneiros operation** — The ledger is real, append-only and reached from ingest and tick (src/theogony/mesh/storage/audit.py; oneiros_tick.py:454). But the actions it actually holds on data/mesh-founding are only mesh_ingest_link_decision (7,281), mesh_i…
- **CSR holds (source, target, weight, decay_tier, frame_consistency)** — build_csr_from_columns (src/theogony/mesh/storage/edges.py:337-417) takes weight and frame_consistency and computes weight * frame (:408); decay_tier is not passed at all. Measured across all 94,490 edges of data/mesh-founding: fr…
- **Cold tier — historical Lance versions, queryable on demand** — The audit-trail half is live (mesh_audit, 13,883 rows). The versioned-snapshot half is deliberately destroyed: _DEFAULT_VERSION_RETENTION = timedelta(0) (src/theogony/mesh/storage/nodes.py:95) and every tick calls prune_history on…
- **Damping factor (default ≈ 0.5) as the propagation stop condition** — DEFAULT_DAMPING = 0.5 (src/theogony/mesh/retrieval/defaults.py:66) and it is applied in the raw and degnorm branches (propagation.py:143, :152). But the shipped default operator is ppr (defaults.py:61-62, retrieve.py:305), whose b…
- **Delta buffer: lock-free append, single batched flush, bounded size** — None of the three properties holds. append_hebbian_delta takes a global threading.Lock and opens the sidecar file once per delta inside it (src/theogony/mesh/storage/edges.py:139-145) — 64 opens per query at the default hebbian_ma…
- **Forbidden: reads that mutate the version they read from** — Opening the substrate for reading performs writes and full scans. MeshNodeStore.__init__ calls _ensure_consolidated_indexes() (src/theogony/mesh/storage/nodes.py:216, body :297-320), which adds rows; EdgeStore.__init__ calls _ensu…
- **Lance edge-metadata table kept off the SpMV hot path** — The table exists and is live (94,490 rows). Both of its doctrinal properties fail. (a) 'Edges that are pure Hebbian co-firings with no descriptor are not in this table ... typically 10-30% of edges' — on data/mesh-founding the met…
- **Maximum hop count (default 3, never above 5 for production queries)** — hops=3 is honoured for raw/degnorm (defaults.py:65, propagation.py:139, :148). The shipped default operator is ppr with DEFAULT_PPR_ITERS = 12 (defaults.py:62), executed as 12 propagation iterations (propagation.py:157-162) — abov…
- **Nodes — two Lance tables with per-vector HNSW indices** — Two tables exist and are live. The indices are not HNSW: ensure_indices builds IVF_PQ (src/theogony/mesh/storage/nodes.py:449-456) plus a BTree on id (:436). Coverage is one table only — ensure_indices touches consolidated_nodes a…
- **Tick step 15 — Write the new audit-ledger entries** — One audit row per tick is written and it is real (oneiros_tick.py:454-467; 14 rows in data/mesh-founding). But it is flat: edges_before/after, delta_drained, lambda, dt, max_out_degree, index status, versions_pruned, pids_backfill…
- **Tick step 16 — Build the new stable CSR tensor** — The tick does the opposite: it *invalidates* the CSR cache twice (oneiros_tick.py:431 and :449) and never calls `rebuild_csr`. The CSR is rebuilt lazily by the next reader (oneiros_tick.py:303-318), so the first query after a tick…
- **Tick step 17 — Publish the new Lance version atomically** — `replace_all_edges` (edges.py:754-784) is atomic per table only, and its own docstring says so: "this is atomic *per table*, not across the three. Lance gives no cross-table transaction" (edges.py:769-773). `current_lance_version(…
- **Tick step 3 — Apply decay (super-linear, tier-modulated)** — Called on every tick: oneiros_tick.py:413 → src/theogony/mesh/storage/edges.py:273-298. The super-linear part runs and is the only thing measurably changing edges (audit rows show weight loss across all 14 ticks). The tier-modulat…
- **Tick step 6 — Compute consolidation candidates** — The co-firing history the doctrinal candidate rule keys on: `fired_total`/`fired_recent` have no writer.
- **Tick step 7 — Apply consolidations** — Implemented (consolidation.py:803-969), reached from a real path (scripts/mesh_consolidate.py:83), and it has actually run: data/mesh-s5-work's audit log carries 1 `mesh_oneiros_consolidation` row, and 48 of its 4,934 consolidated…
- **Write the new Lance version atomically; publish the pointer for subsequent readers** — replace_all_edges is atomic per table via mode='overwrite' (src/theogony/mesh/storage/edges.py:782-790), and its own docstring says plainly that it is not atomic across the three: 'a failure between the first and second overwrite …

**inert**

- **Append-only COO delta buffer — the Hebbian write path** — Implemented (src/theogony/mesh/storage/edges.py:88-158) and drained by the tick (oneiros_tick.py:409). Its only producer is append_hebbian_deltas (retrieve.py:98-103), reachable only behind the opt-in --hebbian flag (cli.py:518-52…
- **Frame routing — per-frame mask on the active edges, (A * mask) · X** — build_frame_routed_csr is implemented (src/theogony/mesh/retrieval/frame_routing.py:70-101) and has exactly one caller, retrieve() (retrieve.py:423), gated on a non-zero query_frame (retrieve.py:421). Nothing passes one: `mesh ask…
- **Saturation eviction (Oneiros step 8-9)** — enforce_saturation is called on every tick (src/theogony/mesh/runtime/oneiros_tick.py:414) and is implemented (edges.py:310-334). But DEFAULT_MAX_OUT_DEGREE = 10_000 (edges.py:307) and the largest out-degree on data/mesh-founding …
- **Tick step 2 — Drain the delta buffer** — Implemented and called: oneiros_tick.py:409 `drained = self.edges.delta.drain()`, merged at :412. A producer exists behind an opt-in flag — src/theogony/mesh/cli.py:518-526 `mesh ask --hebbian`, default `False` — reaching src/theo…

**blockiert**

- **Automatic, statistical Hot↔Warm tier movement** — fired_recent / fired_total — declared on both node schemas, never written by any path

**fehlt**

- **Agent-driven cleanup queue drained by the tick (step 5)** — Of the four record types doctrine names, only MergeProposal exists (src/theogony/mesh/runtime/consolidation.py:140); RemovalProposal, ContradictionFinding and RedundancyProposal have zero definitions in src/. MergeProposal is prod…
- **Anchor nodes — separate anchor_nodes Lance table plus inverted anchor index** — Grep over src/, scripts/, tests/ for anchor_nodes and anchor_index returns exactly one hit — the doctrine line itself. No temporal_anchor or geo_anchor field exists anywhere in src/. The live workspace data/mesh-founding/lance con…
- **Global renormalisation (step 4, and the per-tick operations table)** — No implementation anywhere in src/. Grep for renormalis / renormaliz / drift_threshold / global_renorm returns one hit, a docstring in src/theogony/mesh/runtime/consolidation.py:29 listing it among the things not built. run_minima…
- **Hot tier — working-set nodes as dense PyTorch tensors in RAM/VRAM** — No working-set structure exists. The only resident tensor is a whole-graph CSR cache on the runtime (src/theogony/mesh/runtime/oneiros_tick.py:162, built at :303-318 from the full Lance edge table) — not a subset, not per-node, ne…
- **K concurrent Spreading Activation queries fold into one batched SpMM** — Every propagation multiplies a single column. _spmv does x.unsqueeze(1) (src/theogony/mesh/retrieval/propagation.py:41); same shape in runtime/spreading.py:47, eval/link_prediction.py:188, eval/qa_retrieval.py:527. No (N, K) activ…
- **Minimum-activation threshold (default ≈ 0.05) per node** — No threshold exists on any propagation or assembly path. Constellation membership is `v > 0.0` cut by top_k (src/theogony/mesh/retrieval/constellation.py:128-134), and the module states it outright at :116-127, with the measuremen…
- **Oneiros — serialised, single-writer per substrate instance** — No lock, lease or lockfile exists: grep over src/ for filelock, FileLock, flock, lockfile, O_EXCL returns nothing. The only locks in the mesh package are EdgeDeltaBuffer._lock (edges.py:103) and an embedder load lock. run_minimal_…
- **Pruning trigger — RAM / p95-latency / GPU thresholds firing an immediate pruner** — Grep across the repo for prune_ram_threshold, prune_latency_threshold and prune_gpu_threshold returns hits only in the doctrine file. No resource-pressure pruner exists. The similarly-named prune_history (nodes.py:484, edges.py:63…
- **Reads — snapshot isolation, a Lance version pinned per Spreading Activation pass** — _READ_CONSISTENCY = timedelta(0) (src/theogony/mesh/runtime/oneiros_tick.py:127) is passed to both lancedb.connect calls (:149, :192). Zero means 're-check the latest version on every operation' — the opposite of pinning. The comm…
- **Refresh node_potential_cache and activation_entropy for all touched nodes (step 14)** — No writer exists. Measured on data/mesh-founding: node_potential_cache is None on all 5,002 consolidated nodes and activation_entropy is None on all 5,002. run_minimal_tick has no such phase (oneiros_tick.py:398-484). One half has…
- **Stable CSR sparse tensor built by Oneiros at the end of each tick** — run_minimal_tick (src/theogony/mesh/runtime/oneiros_tick.py:398-484) never builds a CSR. It calls invalidate_csr_cache() (:431, :449) and stops. Every reader rebuilds it from the row-per-edge Lance table instead (EdgeStore.csr_fro…
- **Tick frequency — operator-configurable schedule** — There is no scheduler, daemon, interval setting or cron entry anywhere. run_minimal_tick has exactly one non-test caller: the `theogony mesh tick` CLI command (src/theogony/mesh/cli.py:232). Grep for schedule/cron/interval/daemon …
- **Tick step 1 — Pin the input snapshot** — src/theogony/mesh/runtime/oneiros_tick.py:408-414 — the tick reads live tables (`count_rows`, `delta.drain`, `load_all_edges`) with no version pin. src/theogony/mesh/storage/nodes.py:87-88 states outright that "nothing in this cod…
- **Tick step 14 — Refresh node_potential_cache and activation_entropy** — Both fields exist on the schema (src/theogony/mesh/schemas.py:91-92) and are `None` on all 5,002 consolidated nodes in data/mesh-founding (measured). run_minimal_tick has no refresh phase. The only writes in src/ set them to `None…
- **consolidation_tier column partitioning consolidated_nodes; counters/timestamps/qids/description as typed columns** — The Lance schema is id, payload_json, semantic_vector, frame_vector, description_vector (src/theogony/mesh/storage/nodes.py:186-193) — verified against the live table. consolidation_tier, fired_total, born_at, qids, description, i…