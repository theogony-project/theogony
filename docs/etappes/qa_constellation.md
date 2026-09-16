# Der Antwort-Arm auf einem Korpus, den das Modell nicht kennt (PHX-1110)

**Stand:** 2026-09-16, gemessen. Spur C des Plans, zweites und letztes Stück.
**Werkzeug:** `eval/qa_mesh.py` (Replay-Ingestion, fünf Arme, gepaarter
Vorzeichentest), `scripts/mesh_qa_mesh_ingest.py`, `scripts/mesh_qa_constellation.py`.

## Warum dieses Stück jetzt das einzige ist

PHX-1098 hat den Founding-Korpus als Kontrollgruppe geschlossen: unter dem
korrigierten Gold beantwortet deepseek-chat Hesiod zu **86 %** ohne jedes
Material, und die Constellation liegt mit 75 % darunter. Auf einem Korpus,
den das Modell auswendig kann, misst der Antwort-Arm den Preis der Bindung
an das Material, nicht den Mehrwert des Graphen. Die Frage „hilft der Graph
beim Antworten" lässt sich nur stellen, wo das Vorwissen niedrig ist.

2WikiMultihopQA ist so ein Korpus. PHX-1089 hat dort das Vorwissen bei
**24,8 % EM** gemessen und das Retrieval bei +11 bis +23 Punkten darüber.
Was PHX-1089 dem Modell reichte, waren aber **Passagen**: ganze Absätze,
von kNN oder von Spreading Activation über einen billigen spaCy-Graphen
ausgewählt. Das Konsumformat des Substrats selbst — die Constellation aus
Entitäten und typisierten Relationen, die `mesh ask` rendert — ist auf
einem unbekannten Korpus nie gemessen worden.

## Der Aufbau

**Ein Mesh aus 2Wiki, ohne einen LLM-Aufruf.** `scripts/mesh_qa_kadmos.py`
hatte für PHX-1089 jede der 6.119 Passagen einmal von Kadmos lesen lassen
und die Lesung gecacht (Schlüssel: blake2b-128 des Passagentexts). Ein
Replay-Provider beantwortet den Absatz-Prompt des Lesers aus diesem Cache,
und der ausgelieferte Schreibpfad (`MeshParagraphReader`) baut daraus ein
Mesh — derselbe Linker, dieselbe Identitätsauflösung, dieselben Kanten, die
ein Nutzerkorpus bekäme. Ein Absatz, den der Cache nicht hält, wird als
Lesefehler gezählt, nicht erfunden (auf 2Wiki: 6.119 von 6.119 gefunden).
Das Ergebnis, `data/mesh-2wiki`: 6.119 Chunks, **35.906 konsolidierte
Knoten, 38.746 gelesene Relationen**, 3.322 Absatzkonzepte, 616 MB nach der
Kompaktierung; 81 Minuten bei 0,80 s je Absatz, 0 Ticks.

**Fünf Arme, ein Modell, ein Bewerter.** deepseek-chat, Temperatur 0, die
Prompts von PHX-1089 (nur „passages" wird zu „material", weil zwei Arme
Entitäten reichen statt Absätze). Bewertet mit SQuAD EM/F1 gegen den
Antwortschlüssel samt Aliasen — nicht mit dem Founding-Bewerter, der Ziffern
streicht (der Korpus trägt Fußnotenzahlen), denn die Hälfte der
2Wiki-Antworten sind Daten.

| Arm | Material | Frage, die er beantwortet |
|---|---|---|
| `closed_book` | keines | das Vorwissen |
| `passages` | Top-5 Passagen nach Kosinus | schlichtes RAG; die Brücke zu PHX-1089 (`knn`) |
| `vector_only` | Top-50 Mesh-Entitäten nach Kosinus, als Beschreibungen | was der Knotenspeicher allein trägt |
| `constellation` | dieselbe Art Entitäten plus die Relationen zwischen ihnen | das ausgelieferte Rendering (`mesh ask`) |
| `constellation_typed` | dasselbe ohne die Strukturkanten | ob die Strukturkanten den Leser etwas kosten |

Die Aussage, die zählt, ist `constellation` gegen `vector_only`: derselbe
Knotenspeicher, dieselbe Einbettung, der einzige Unterschied ist, ob die
Kanten gezeigt werden. Gegen `passages` ist die härtere Frage, ob die
Rendering-Form des Substrats mit schlichtem RAG überhaupt mithält. Jeder
Arm trägt seine Decke mit (`gold in ctx`: stand die Antwort im Material?),
damit ein Leseproblem von einem Retrieval-Problem zu unterscheiden bleibt.
Gepaart, Frage für Frage, mit exaktem Vorzeichentest auf den diskordanten
Paaren, `k_seeds = 1`, `record_firing=False`, 0 Ticks.

Was die Arme dem Modell reichen (auf 20 Fragen gemessen, vor dem Lauf):

| Arm | Zeichen je Prompt | Zeilen | Antwort steht im Material |
|---|---|---|---|
| `passages` | 3.216 | 5 Passagen | 50 % |
| `vector_only` | 4.261 | 50 Entitäten | 40 % |
| `constellation` | 7.567 | 50 Entitäten + ~50 Relationen | 45 % |
| `constellation_typed` | 5.109 | 50 Entitäten + ~15 Relationen | 45 % |

Die Mesh-Arme reichen mehr Zeichen und treffen die Antwort seltener: eine
Entitätsbeschreibung trägt, was Kadmos über die Entität geschrieben hat,
nicht jedes Datum des Absatzes. Das ist keine Eigenschaft des Harness,
sondern des Substrats — es hält, was es gelesen hat.

## Zwei Befunde vor der ersten Antwort

**Ein Lesen wurde quadratisch.** Die Ingestion begann bei 0,55 s je
Absatz und stand nach 400 Absätzen bei über 6 s. Ursache: jeder Knoten ist
ein eigenes Lance-Fragment, bis etwas kompaktiert, und jede Vektorsuche —
zwei je Konzept, für die Identität — liest alle Fragmente. Gemessen: 2.617
Knoten in 2.617 Fragmenten, **98 ms je Suche gegen 10 ms** auf denselben
Zeilen kompaktiert. Der Tick kompaktiert (`prune_history`, PHX-1060), aber
ein Lesen tickt nicht. `MeshRuntime.compact()` macht die Wartung außerhalb
des Ticks aufrufbar, und der Leser ruft sie jetzt alle 200 Absätze
(`compact_every`). Der Founding-Korpus mit 1.206 Absätzen hatte das nie
sichtbar gemacht; ein Korpus in Buchlänge hätte es.

**60 % der gerenderten Relationen sind Strukturkanten.** Auf den 47
Founding-Fragen bekommt eine Constellation im Mittel 65 Relationszeilen,
davon 60 % `co_mentions_in_paragraph`, `appears_in_source` und Verwandte;
auf 2Wiki 61 %. Das ist der ausgelieferte Pfad, und jede Founding-Messung
(PHX-1087/1096/1097/1098) hat ihn so gemessen. `render_constellation`
kennt jetzt `typed_only`, und der fünfte Arm misst, was die Zeilen kosten,
bevor der Standard geändert wird.

## Ergebnis

1.000 Fragen, fünf Arme, deepseek-chat, 24,7 Minuten
(`data/run_reports/qa_constellation/2wiki_1000.json`):

| Arm | EM | F1 | Antwort stand im Material |
|---|---|---|---|
| `closed_book` (Vorwissen) | 33,8 % | 37,9 % | — |
| `passages` (Top-5, schlichtes RAG) | 42,7 % | 48,3 % | 55,4 % |
| `vector_only` (50 Entitäten) | 40,5 % | 45,5 % | 54,6 % |
| `constellation` (mit Strukturkanten) | 41,2 % | 47,0 % | 61,0 % |
| `constellation_typed` (ohne) | **44,1 %** | **49,8 %** | 61,0 % |

Gepaart, Frage für Frage (EM besser / schlechter, Vorzeichentest):

| Vergleich | ΔEM | ΔF1 | besser / schlechter | p (EM) |
|---|---|---|---|---|
| `constellation` gegen `vector_only` | +0,7 | +1,5 | 138 / 131 | 0,72 |
| `constellation_typed` gegen `vector_only` | **+3,6** | **+4,3** | 147 / 111 | **0,03** |
| `constellation_typed` gegen `constellation` | +2,9 | +2,8 | 63 / 34 | 0,004 |
| `constellation_typed` gegen `passages` | +1,4 | +1,6 | 173 / 159 | 0,48 |
| jeder Material-Arm gegen `closed_book` | +6,7 bis +8,9 | +7,6 bis +10,4 | | < 0,001 |

### Was das heißt

**Der Graph hilft beim Antworten — um etwa vier Punkte, und nur ohne die
Strukturkanten.** Dieselben fünfzig Entitäten, dieselbe Einbettung, der
einzige Unterschied sind die Relationszeilen: mit den gelesenen Relationen
allein 44,1 % gegen 40,5 %, signifikant, 147 Fragen besser und 111
schlechter. Das ist die erste Messung dieser Aussage auf einem Korpus, den
das Modell nicht kennt. Die +11 des Founding-Korpus (PHX-1097/1098) waren
auf einem Korpus mit 86 % Vorwissen gemessen; hier, bei 34 %, bleiben +3,6.

**Die ausgelieferte Rendering-Form verschenkte den Gewinn.** Mit den
Strukturkanten drin (`co_mentions_in_paragraph`, `appears_in_source`, 60 %
der Zeilen) bleibt von den vier Punkten weniger als einer (+0,7, p = 0,72);
die Strukturzeilen kosten 2,9 Punkte, 63 Fragen besser ohne sie, 34
schlechter. Wo sie kosten, antwortet das Modell mit der falschen Art
Entität: nach dem Film gefragt, nennt es den Regisseur; nach dem Sterbeort,
eine andere Stadt aus der Liste. `render_constellation` lässt die
Strukturkanten seit dieser Messung standardmäßig weg (`typed_only=True`);
jede Founding-Zahl vor PHX-1110 wurde mit ihnen gemessen und bleibt so
stehen. `mesh ask` zeigt sie dem Menschen weiterhin.

**Gegen schlichtes RAG: Gleichstand, aus zwei gegenläufigen Stücken.** Die
typisierte Constellation liegt 1,4 Punkte über fünf Passagen, nicht
signifikant. Dahinter stecken zwei Effekte, die sich aufheben:

| Teilmenge | n | `closed_book` | `passages` | `vector_only` | `constellation` | `constellation_typed` |
|---|---|---|---|---|---|---|
| Ja/Nein-Fragen | 110 | **57,3 %** | 55,5 % | 50,0 % | 28,2 % | 37,3 % |
| Antwort ist ein Datum | 54 | 7,4 % | **33,3 %** | 3,7 % | 11,1 % | 9,3 % |
| alle übrigen | 836 | 32,4 % | 41,6 % | 41,6 % | 44,9 % | **47,2 %** |

Auf den 836 Fragen mit einer Entität als Antwort schlägt die typisierte
Constellation die Passagen um 5,6 Punkte — das sind die
Vergleichsfragen („which film came out first", „whose director is
younger"), bei denen die Relationen die Kette sichtbar machen, die die
Antwort braucht. Auf Ja/Nein-Fragen bricht sie ein: eine Liste von
Entitäten verleitet das Modell, mit einer Entität zu antworten („Iran"
statt „yes"), und die Constellation mit Strukturkanten fällt auf 28 %,
unter das Vorwissen. Auf Datumsfragen trägt das Mesh die Antwort meist
nicht: eine Entitätsbeschreibung hält, was Kadmos über die Entität
schrieb, nicht jedes Datum des Absatzes — 33 % für die Passagen gegen
unter 12 % für jeden Mesh-Arm.

**Die Decke ist höher, die Ausbeute niedriger.** Das Mesh hält die Antwort
bei 61 % der Fragen im Material, die Passagen bei 55 %: das Retrieval
über den Graphen findet mehr. Steht die Antwort da, macht das Modell aus
den Passagen zu 62 % eine richtige Antwort, aus der typisierten
Constellation zu 64 %, aus der mit Strukturkanten zu 60 %. Steht sie
nicht da, hilft das Vorwissen bei den Passagen noch zu 19 %, bei der
Constellation nur zu 12 %: das größere Material bindet das Modell stärker
an sich.

**Vorbehalt zur Kontrollgruppe.** PHX-1089 hatte das Vorwissen am
26. August bei 24,8 % EM gemessen, derselbe Modellname, dieselben Prompts,
dieselben 1.000 Fragen; heute stehen 33,8 %. Was hinter `deepseek-chat`
antwortet, ist nicht dasselbe Modell wie damals. Der Passagen-Arm liegt
mit 42,7 % dagegen fast auf dem `knn`-Arm von damals (43,4 %). Alle
Vergleiche hier sind innerhalb eines Laufs, eines Tages, eines Modells.

## Was offen bleibt

- **Ja/Nein-Fragen.** Eine Liste von Entitäten verleitet das Modell zur
  Entitätsantwort; die Passagen tun das nicht. Das ist eine Eigenschaft der
  Rendering-Form, nicht des Retrievals, und ein Prompt, der die Frageart
  erkennt, oder ein Rendering, das Vergleiche als Vergleiche zeigt, ist die
  naheliegende Probe.
- **Daten.** Das Mesh hält keinen Absatztext, nur `raw_text_ref`, und die
  Beschreibung einer Entität trägt, was Kadmos über sie schrieb. Ein Arm, der
  zu den Entitäten der Constellation die Absätze legt, aus denen sie stammen,
  würde die Decke der Passagen (Daten) mit der Decke des Graphen (Ketten)
  verbinden; er ist nicht gemessen.
- **`mesh ask`** rendert die Strukturkanten weiterhin für den Menschen. Ob
  sie dort etwas kosten, ist nicht gemessen; dass sie einem Modell 2,9 Punkte
  kosten, ist es.
- **Die Kontrollgruppe ist beweglich.** Zwischen dem 26. August und heute hat
  sich das Vorwissen desselben Modellnamens um neun Punkte bewegt. Jede
  Aussage dieses Instruments gilt innerhalb eines Laufs.
