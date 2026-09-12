# Die latente letzte Meile — die Constellation als Vektoren statt als Text (PHX-1109)

**Stand:** 2026-09-12, gemessen. Branch `feat/phx-1109-latent-mile`.
**Anlass:** [`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md) §Nachtrag 2026-09-11 — die Berichte über latentes Reasoning, und die Feststellung, dass bei uns alles durch Text läuft.
**Werkzeug:** `scripts/mesh_latent_mile.py train | answer | diagnose`, `src/theogony/mesh/eval/latent_mile.py`. Kurven und Zusammenfassungen aller Läufe: [`latent_mile_runs.json`](latent_mile_runs.json).

**Das Ergebnis in einem Satz: der Vektor kommt an, die Antwort nicht.** Ein
eingefrorener 3B-Leser liest aus einem projizierten Knotenvektor die Identität
des Knotens heraus — messbar, wachsend mit dem Training, auch für Knoten, die
der Projektor nie gesehen hat. Aber aus fünfzig solchen Tokens und den
Relationen dazwischen bildet er keine Antwort: streng bewertet schlägt die
weiche Constellation die Text-Constellation auf keiner einzigen von 39 Fragen,
in keinem von vier Läufen, und liegt auf dem Niveau seines Vorwissens. Was sie
sicher schlägt, ist die Kontrolle: derselbe Prompt mit untrainiertem Projektor
scort null. Und die Messung hat nebenbei den Bewerter erwischt: unter dem
ausgelieferten Substring-Scorer sah der 20-Epochen-Lauf nach Gleichstand aus
(−2 gegen Text, 11 vollständige Antworten gegen 8), weil der weiche Arm in
Sätzen antwortet, die die Frage nachsprechen, und 30 der 111 Gold-Namen in
ihrer eigenen Frage stehen.

## Die Behauptung, die hier geprüft wird

VISION.md, Zeile 44: *„The Constellation is returned to the agent in vector
form, directly injectable into its latent space — no text translation
required. The agent does not read context. It receives structure."* Die
Vision-Ledger führt den Satz als *nicht prüfbar*. Er ist es, seit ein offener
Kleinleser auf dem Laptop läuft und einen Einbettungs-Eingang hat.

Die Prüfung ist bewusst die kleinste, die die Behauptung trifft — xRAG (Cheng
et al. 2024), Stufe 1: Retriever eingefroren, Sprachmodell eingefroren, ein
kleiner trainierter Projektor dazwischen, ein Dokument als ein Token. Hier ist
der Retriever das Substrat selbst, und das Dokument ist ein Knoten.

## Aufbau

**Leser.** Qwen2.5-3B-Instruct, eingefroren, fp16 auf MPS (fp32 antwortet
identisch, gemessen auf 8 Fragen). Der 1,5B, den das MNLM-Brief als PoC-Ziel
nennt, wurde zuerst probiert und verworfen: er liest das Text-Material kaum —
auf den ersten 8 Gold-Fragen 24 % gegen 33 % ohne Material —, während der 3B
es gut liest (55 % gegen 27 %). Ein Leser, der die Text-Constellation nicht
nutzen kann, kann die weiche nicht widerlegen. (Der 1,5B-Projektorlauf, nach
drei Epochen abgebrochen: Verlust 3,06 → 2,57, zurückgehalten 2,52 → 2,29,
Wiedererkennung 0 %.)

**Projektor.** Zwei Schichten (Eingang → 2048 → 2048, GELU), ein Knotenvektor
→ ein weiches Token, an der Stelle eines Platzhalter-Tokens in den
Chat-Prompt gespleißt. Vor dem Training auf die mittlere Norm eines echten
Token-Embeddings kalibriert, damit die Kontrolle „untrainiert" die Abwesenheit
des Trainings misst und nicht eine Skala, die eine Größenordnung daneben liegt.

**Eingang.** `both`: der `semantic_vector` (384-d, bge-small-en, der Vektor,
über den Spreading Activation läuft) ⊕ der `description_vector` (384-d, die
Einbettung der regenerierten Beschreibung). Der zweite ist das Analogon zu
xRAGs Dokument-Embedding, weil das Paraphrase-Ziel *die Beschreibung ist*.
`semantic` allein ist die doktrintreue, härtere Variante und wurde ebenfalls
gemessen.

**Training.** Paraphrase, wie xRAG Stufe 1: aus dem weichen Token soll der
Leser den Eintrag erzeugen, den der Text-Arm zeigt (`Label — Beschreibung`).
Trainingsdaten sind die 3.715 Entitätsknoten des konsolidierten Founding-Mesh
(Median 13 Wörter Beschreibung; die 1.219 Quellanker ausgeschlossen, ihre
Beschreibungen sind Dateinamen und der Text-Arm zeigt sie auch nicht). In
Gruppen von 1–4 Knoten je Beispiel, weil der Antwort-Prompt fünfzig weiche
Tokens in einer Liste zeigt und ein Projektor, der nur einzelne Tokens gesehen
hat, nie ein Token *nach* einem anderen erlebt hat. 5 % der Knoten (186)
zurückgehalten. Das Gold-Set berührt das Training nicht. Batch 8, AdamW 1e-3,
Gradient-Checkpointing durch den eingefrorenen Leser (ohne das lag der Laptop
23 GB im Swap), etwa 14 Minuten je Epoche auf einem M4 Pro.

**Vier Arme, derselbe Leser, dieselbe Constellation je Frage** (`k_seeds=1`,
`top_k=50`, `record_firing=False`), dieselbe Bewertung wie das
Antwort-Instrument (PHX-1087, Substring-Treffer auf den Gold-Namen), dazu die
strenge Bewertung (unten):

| Arm | Material |
|---|---|
| `closed_book` | keines |
| `constellation` | das ausgelieferte Textrendering: `Label — Beschreibung` je Knoten, Relationen als Tripel über den Labels, nur Kanten an einem Seed |
| `soft` | dieselben Knoten als weiche Tokens, dieselben Tripel mit weichen Tokens statt Labels |
| `soft_untrained` | derselbe Prompt, der Projektor vor dem Training (fester Seed) |

Ein Test beweist, dass der weiche Prompt das Textrendering mit ausgeschnittenen
Namen ist: setzt man die Namen wieder ein, entsteht der Text-Arm wörtlich.
Greedy-Decoding ist deterministisch; eine Wiederholung misst nichts. Die
Streuung, die es gibt, ist die über Trainings-Seeds.

**Was nicht geht, und warum es von Hand gebaut ist.** `generate()` mit
`inputs_embeds` liefert auf MPS unter transformers 5.5.4 Unsinn (`'OSTROPHE'`
auf „Who is the father of Zeus?"), mit und ohne Cache, in fp16, bf16 und fp32,
während der Vorwärtsdurchlauf mit denselben Embeddings bis auf 0,0 exakt ist
und die CPU korrekt antwortet. Der Decoder ist deshalb ein Greedy-Loop über
`past_key_values`, 30 Zeilen.

## Das Training: was der Vektor trägt

Verlust in nats je Token des Paraphrase-Ziels, `both`, Seed 0, fortgesetzt
von 5 auf 20 Epochen; die 30er-Stichproben der Wiedererkennung sind grob:

| Epoche | Training | zurückgehalten | Label wiedererkannt (Training / zurückgehalten) |
|---|---|---|---|
| 1 | 3,03 | 2,46 | 0 % / 0 % |
| 2 | 2,51 | 2,21 | 0 % / 0 % |
| 5 | 2,23 | 2,01 | 0 % / 7 % |
| 10 | 1,90 | 1,84 | 7 % / 10 % |
| 15 | 1,67 | **1,72** | 10 % / 10 % |
| 20 | 1,46 | 1,79 | 13 % / 13 % |

Ab Epoche 15 trennen sich die Kurven: der Projektor beginnt, das Verzeichnis
zu lernen statt die Abbildung. Seed 1 nach 5 Epochen: 2,19 / 2,10;
`semantic` nach 5 Epochen: 2,13 / 1,98 — der doktrintreue Vektor lernt die
Paraphrase nicht schlechter.

Ein einzelnes weiches Token bringt den Leser selten dazu, den Namen des Knotens
zurückzugeben: nach Epoche 2 antwortet er auf *Tyndareus* mit „Aesop — The
Greek fabulist", auf *Briareos* mit „Theodamas — A Spartan general". Das
Register stimmt, die Identität nicht. **Gemessen, was das Token trägt**
(`diagnose`, je 60 Knoten, Verlust je Token; *fremd* = derselbe Projektor mit
dem Vektor eines anderen Knotens):

| Projektor | Knoten | Name-Tokens richtig / fremd / Kontrolle | Beschreibungs-Tokens richtig / fremd / Kontrolle |
|---|---|---|---|
| `both`, 5 Ep. | Training | 2,60 / 4,86 / 13,81 | 1,77 / 2,47 / 4,52 |
| `both`, 5 Ep. | zurückgehalten | 2,91 / 4,88 / 14,51 | 1,84 / 2,44 / 4,86 |
| `semantic`, 5 Ep. | Training | 2,48 / 4,82 / 12,69 | 1,74 / 2,48 / 4,83 |
| `semantic`, 5 Ep. | zurückgehalten | 2,85 / 4,80 / 13,03 | 1,83 / 2,44 / 5,22 |
| `both`, 20 Ep. | Training | **1,17** / 6,74 / 13,81 | 1,11 / 3,59 / 4,52 |
| `both`, 20 Ep. | zurückgehalten | **2,42** / 6,80 / 14,51 | 1,78 / 3,71 / 4,86 |

Die Spalte, auf die es ankommt, ist *richtig gegen fremd* auf zurückgehaltenen
Knoten: 2,0 nats je Namens-Token trägt der Vektor nach fünf Epochen an
Identität, 4,4 nats nach zwanzig — und der semantische Vektor allein trägt
genauso viel wie beide zusammen. **Der Vektor kommt an.** Zwischen Training
und zurückgehalten liegt nach fünf Epochen fast nichts (der Projektor lernt
eine Abbildung), nach zwanzig ein Faktor zwei (er beginnt, sie auswendig zu
lernen).

## Die vier Arme

47 Gold-Fragen, derselbe Leser, dieselbe Constellation je Frage, Greedy.
Zwei Bewertungen: **ausgeliefert** = Substring-Treffer auf allen Gold-Namen,
wie PHX-1087; **streng** = ohne die Gold-Namen, die in der Frage selbst stehen
(30 von 111; 8 Fragen fallen weg, 39 bleiben).

| Lauf | Arm | ausgeliefert | vollständig | streng | vollständig | Wörter je Antwort |
|---|---|---|---|---|---|---|
| alle | `closed_book` | 16 % | 4/47 | 14 % | 3/39 | 2 |
| alle | `constellation` (Text) | **38 %** | 8/47 | **49 %** | 13/39 | 2 |
| alle | `soft_untrained` | 9–11 % | 1–2/47 | **0 %** | 0/39 | 2 |
| `both`, Seed 0, 5 Ep. | `soft` | 19 % | 6/47 | 9 % | 2/39 | 3 |
| `both`, Seed 1, 5 Ep. | `soft` | 17 % | 2/47 | 11 % | 2/39 | 2 |
| `semantic`, Seed 0, 5 Ep. | `soft` | 8 % | 4/47 | 1 % | 1/39 | 19 |
| `both`, Seed 0, 20 Ep. | `soft` | **28 %** | **11/47** | 11 % | 4/39 | 6 |

Frage für Frage, gepaart (besser / schlechter / gleich):

| Lauf | Vektoren gegen Text | Vektoren gegen untrainiert | Vektoren gegen Vorwissen |
|---|---|---|---|
| `both` 0, 5 Ep., ausgeliefert | −15 (7 / 22 / 18) | +10 (12 / 5 / 30) | +9 (10 / 4 / 33) |
| `both` 0, 5 Ep., **streng** | −43 (**0** / 24 / 15) | +8 (5 / 0 / 34) | −2 (3 / 3 / 33) |
| `both` 1, 5 Ep., ausgeliefert | −22 (4 / 20 / 23) | +4 (11 / 5 / 31) | +2 (10 / 5 / 32) |
| `both` 1, 5 Ep., **streng** | −42 (**0** / 22 / 17) | +9 (7 / 0 / 32) | 0 (5 / 3 / 31) |
| `semantic` 0, 5 Ep., ausgeliefert | −24 (6 / 25 / 16) | +3 (6 / 6 / 35) | 0 (9 / 9 / 29) |
| `semantic` 0, 5 Ep., **streng** | −48 (**0** / 25 / 14) | +3 (1 / 0 / 38) | −7 (1 / 5 / 33) |
| `both` 0, 20 Ep., ausgeliefert | **−2 (13 / 17 / 17)** | +23 (16 / 2 / 29) | +21 (18 / 5 / 24) |
| `both` 0, 20 Ep., **streng** | −38 (**0** / 20 / 19) | +12 (7 / 0 / 32) | +3 (6 / 4 / 29) |

Text gegen Vorwissen, streng, in jedem Lauf: +41 (23 / 1 / 15). Nach
Fragenart, streng, 20 Epochen: genealogisch (n = 24) Text 47 %, Vektoren 6 %,
Vorwissen 7 %; erzählend (n = 15) Text 57 %, Vektoren 23 %, Vorwissen 13 %.

## Lesung

**Die Vektoren tragen etwas, und es ist nicht die Aufmachung.** Gegen den
untrainierten Projektor gewinnt der trainierte streng in jedem Lauf und
verliert nie (5 / 0, 7 / 0, 1 / 0, 7 / 0). Der untrainierte Projektor bringt
den Leser zum Stottern (`ă, ă, ă, …`) oder zu `None`; der trainierte antwortet
mit Namen aus dem richtigen Universum.

**Aber der Leser kann aus ihnen keine Antwort bilden.** Streng bewertet
schlägt die weiche Constellation die Text-Constellation auf *keiner* Frage, in
keinem Lauf, und liegt auf dem Niveau des Vorwissens (−2, 0, −7, +3). Wo der
Text gewinnt, sind es alle Fragen: die Kinder des Cronos („Titans, Cyclopes,
and Hecatoncheires"), die Kinder der Nacht („Night bore Time"), die Kinder des
Streits („Strife bore 10 children."). Der Leser weiß, *wovon* die Rede ist —
das zeigt die Diagnose —, aber nicht, *was* die fünfzig Tokens über die Frage
sagen.

**Der ausgelieferte Bewerter hätte etwas anderes erzählt.** Unter ihm sah der
20-Epochen-Lauf nach Gleichstand aus: −2 gegen den Text, 13 Fragen besser
gegen 17, elf vollständige Antworten gegen acht, und bei erzählenden Fragen
50 % gegen 37 %. Alle dreizehn „Gewinne" sind Fragen, deren Gold-Namen in der
Frage stehen — *How were Chrysaor and Pegasus born?* erwartet Chrysaor und
Pegasus, *What measures the depth of Tartarus?* erwartet Tartarus —, und der
weiche Arm, per Paraphrase darauf trainiert, Einträge *auszuschreiben*,
antwortet in Sätzen, die die Frage nachsprechen („Chrysaor and Pegasus were
born from the severed head of Medusa"), während der Text-Arm der Anweisung
„nur Namen" folgt („Medusa"). Sechs Wörter je Antwort gegen zwei. Der
Substring-Scorer bezahlt das. **30 der 111 Gold-Namen stehen in ihrer
eigenen Frage;** das ist ein Fehler des Gold-Sets, der jeden Arm gleich
aufbläht, außer er antwortet in Sätzen — dann ungleich. Der Nachtrag steht in
PHX-1098, die strenge Bewertung steht jetzt im Harness.

**Warum es hier scheitert, wo es bei xRAG geht.** xRAG hat zwei Stufen:
Paraphrase (das Token *dekodieren*) und danach Instruktionstuning mit
Selbst-Destillation vom Text-RAG-Lehrer (das Token *unter einer Anweisung
benutzen*). Gebaut wurde Stufe 1. Sie liefert, was sie verspricht — die
Identität kommt an —, und sie kann nicht liefern, was Stufe 2 verspricht.
Mehr Epochen sind nicht der Hebel: ab Epoche 15 lernt der Projektor das
Verzeichnis auswendig, und streng ändert sich nichts (9 → 11 %). Der Hebel ist
Stufe 2, und die braucht Frage-Antwort-Daten, die nicht das Gold-Set sind —
synthetische Fragen aus dem Mesh, oder HippoRAG.

**Was das für VISION:44 heißt.** Der Satz ist zum ersten Mal gemessen, und die
Messung trennt ihn in zwei Hälften. *„The agent receives structure"* — ja, auf
dieser Skala nachweisbar: ein eingefrorenes Modell liest aus dem Substratvektor
die Identität des Knotens, wachsend, verallgemeinernd. *„No text translation
required"* — nein, nicht mit diesem Rezept: die Übersetzung in Text bleibt die
Meile, auf der die Antwort entsteht, und der Abstand ist ein Trainingsrezept
(Stufe 2), nicht ein Beweis, dass das Medium es nicht trägt. Und das
Instrument hat wieder mehr gezeigt als der Gegenstand: ohne die strenge
Bewertung stünde hier ein falsches „Gleichstand nach zwanzig Epochen".

## Grenzen

- Ein Leser, eine Skala (3B). LOTUS sagt, dass latente Verfahren über 1B bis
  Mitte 2026 hinter Text zurückfielen; ein Nullergebnis hier ist ein Ergebnis
  über *diese* Skala und *dieses* Rezept.
- 3.715 Trainingsvektoren gegen Millionen bei xRAG; ein Seed für `semantic`
  und für die 20 Epochen.
- Das Gold-Set hat keine Aliase (PHX-1098) und 30 Namen in der eigenen Frage;
  die strenge Bewertung streicht die zweiten, nicht die ersten.
- Das Substrat ist bge-small-en 384-d; ob ein größerer Einbettungsraum mehr
  durch die Meile trägt, ist nicht gemessen.
- Die Relationsbezeichner (`co_mentions_in_paragraph` in vielen Tripeln) sind
  in beiden Armen gleich; im weichen Arm werden sie dem Leser sichtbar zum
  Muster („co_mentions_in_paragraph — Co-mentions: …"). Ob ein Prompt ohne
  strukturelle Kanten den weichen Arm hebt, ist nicht gemessen.
