# Die latente letzte Meile — die Constellation als Vektoren statt als Text (PHX-1109)

**Stand:** 2026-09-11, Messung läuft. Branch `feat/phx-1109-latent-mile`.
**Anlass:** [`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md) §Nachtrag 2026-09-11 — die Berichte über latentes Reasoning, und die Feststellung, dass bei uns alles durch Text läuft.
**Werkzeug:** `scripts/mesh_latent_mile.py`, `src/theogony/mesh/eval/latent_mile.py`.

## Die Behauptung, die hier geprüft wird

VISION.md, Zeile 44: *„The Constellation is returned to the agent in vector form,
directly injectable into its latent space — no text translation required. The
agent does not read context. It receives structure."* Die Vision-Ledger führt
den Satz als *nicht prüfbar*. Er ist es, seit ein offener Kleinleser auf dem
Laptop läuft und einen Einbettungs-Eingang hat.

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
nutzen kann, kann die weiche nicht widerlegen.

**Projektor.** Zwei Schichten (Eingang → 2048 → 2048, GELU), ein Knotenvektor
→ ein weiches Token. Vor dem Training auf die mittlere Norm eines echten
Token-Embeddings kalibriert, damit die Kontrolle „untrainiert" die Abwesenheit
des Trainings misst und nicht eine Skala, die eine Größenordnung daneben liegt.

**Eingang.** `--vectors both`: der `semantic_vector` (384-d, bge-small-en, der
Vektor, über den Spreading Activation läuft) ⊕ der `description_vector`
(384-d, die Einbettung der regenerierten Beschreibung). Der zweite ist das
Analogon zu xRAGs Dokument-Embedding, weil das Paraphrase-Ziel *die
Beschreibung ist*. `semantic` allein ist die doktrintreue, härtere Variante und
steht als Flag bereit.

**Training.** Paraphrase, wie xRAG Stufe 1: aus dem weichen Token soll der
Leser den Eintrag erzeugen, den der Text-Arm zeigt (`Label — Beschreibung`).
Trainingsdaten sind die 3.715 Entitätsknoten des konsolidierten Founding-Mesh
(Median 13 Wörter Beschreibung; die 1.219 Quellanker ausgeschlossen, ihre
Beschreibungen sind Dateinamen und der Text-Arm zeigt sie auch nicht). In
Gruppen von 1–4 Knoten je Beispiel, weil der Antwort-Prompt fünfzig weiche
Tokens in einer Liste zeigt und ein Projektor, der nur einzelne Tokens gesehen
hat, nie ein Token *nach* einem anderen erlebt hat. 5 % der Knoten
zurückgehalten. Das Gold-Set berührt das Training nicht.

**Vier Arme, derselbe Leser, dieselbe Constellation je Frage** (`k_seeds=1`,
`top_k=50`, `record_firing=False`), dieselbe Bewertung wie das
Antwort-Instrument (PHX-1087, Substring-Treffer auf den Gold-Namen):

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

## Ergebnisse

### Das Training

Qwen2.5-3B, `both`, Seed 0, 3.529 Knoten im Training, 186 zurückgehalten,
Batch 8, AdamW 1e-3, fünf Epochen zu je etwa 14 Minuten auf einem M4 Pro:

| Epoche | Verlust Training | Verlust zurückgehalten | Label wiedererkannt (30 Training / 30 zurückgehalten) |
|---|---|---|---|
| 1 | 3,03 | 2,46 | 0 % / 0 % |
| 2 | 2,51 | 2,21 | 0 % / 0 % |
| 3 | 2,39 | 2,16 | 0 % / 3 % |
| 4 | 2,30 | 2,07 | 0 % / 3 % |
| 5 | 2,23 | 2,01 | 0 % / 7 % |

Die Kurve fällt nach fünf Epochen noch. Ein einzelnes weiches Token bringt den
Leser fast nie dazu, den Namen des Knotens zurückzugeben: nach Epoche 2
antwortet er auf *Tyndareus* mit „Aesop — The Greek fabulist", auf *Briareos*
mit „Theodamas — A Spartan general". Das Register stimmt, die Identität nicht.

**Was der Vektor trägt, gemessen** (`diagnose`, je 60 Knoten, Verlust je Token
in nats, nach Epoche 5):

| Knoten | Vektor | Name-Tokens | Beschreibungs-Tokens |
|---|---|---|---|
| Training | der richtige | 2,60 | 1,77 |
| Training | der eines anderen Knotens | 4,86 | 2,47 |
| Training | untrainierter Projektor | 13,81 | 4,52 |
| zurückgehalten | der richtige | 2,91 | 1,84 |
| zurückgehalten | der eines anderen Knotens | 4,88 | 2,44 |
| zurückgehalten | untrainierter Projektor | 14,51 | 4,86 |

Die Zeile, auf die es ankommt, ist *richtig gegen fremd*: 2,3 nats je
Namens-Token trägt der Vektor an Identität, und zwischen Training und
zurückgehalten liegt fast nichts — der Projektor lernt eine Abbildung, kein
Verzeichnis. Nach Epoche 2 waren es 0,9 nats. Aber 2,6 bis 2,9 nats je Token
heißt: der Name ist mit ein paar Prozent je Token wahrscheinlich, nicht
sicher. Genau das sieht man dann in den Antworten.

### Die vier Arme

47 Gold-Fragen, `k_seeds=1`, `top_k=50`, derselbe Leser, dieselbe
Constellation je Frage, Greedy:

| Arm | Antwort-Recall | vollständig |
|---|---|---|
| `closed_book` | 16 % | 4/47 |
| `constellation` (Text) | **38 %** | 8/47 |
| `soft` (Vektoren) | 19 % | 6/47 |
| `soft_untrained` | 11 % | 2/47 |

Frage für Frage:

| Vergleich | Δ Recall (gepaart) | besser / schlechter / gleich |
|---|---|---|
| Vektoren gegen Text, dieselbe Constellation | −15 | 7 / 22 / 18 |
| trainiert gegen untrainiert | +10 | 12 / 5 / 30 |
| Vektoren gegen Vorwissen | +9 | 10 / 4 / 33 |
| Text gegen Vorwissen | +24 | 23 / 4 / 20 |

Nach Fragenart: genealogisch (n = 26) Text 38 %, Vektoren 19 %, Vorwissen 13 %;
erzählend (n = 21) Text 37 %, Vektoren **27 %**, Vorwissen 15 %.

### Lesung

**Die Vektoren tragen etwas, und es ist nicht die Aufmachung.** Trainiert
gegen untrainiert: +10 Punkte, 12 Fragen besser gegen 5. Der untrainierte
Projektor bringt den Leser zum Stottern (`ă, ă, ă, …`) oder zu `None`; der
trainierte antwortet mit Namen aus dem richtigen Universum.

**Sie tragen Identität, und man sieht es dort, wo der Text sie verliert.**
Die sieben Fragen, auf denen die Vektoren gewinnen, sind keine Zufälle:
*Echidna, Orthus* (der Text sagt „Cerberus"), *Chrysaor, Pegasus* (der Text
sagt „Medusa"), *Hermaon, Thronia*, *Zeus* für den melischen Feuerbringer,
*Tartarus*. Das sind spezifische, teils entlegene Namen, die der Leser aus dem
Vektor zurückgewinnt, während er sie im Textblock von fünfzig Einträgen
übersieht.

**Aber sie tragen sie nicht sicher genug, um Listen zu bilden.** Wo der Text
gewinnt, sind es Aufzählungsfragen: die Kinder des Cronos, die Titanen, die
Flüsse der Tethys. Aus fünfzig weichen Tokens bildet der Leser keine Liste; er
nennt einen Namen („Titans", „Hera", „Pallas") oder einen Satz („Night bore
Day"). Bei erzählenden Fragen mit einer Antwort liegen die Vektoren 10 Punkte
hinter dem Text, bei genealogischen 20.

**Das Ergebnis, in einem Satz:** auf dieser Skala — ein 3B-Leser, 3.529
Trainingsvektoren, fünf Epochen auf einem Laptop — ist die latente letzte Meile
ein Kanal, der die Hälfte dessen trägt, was der Text trägt, und dabei etwas
anderes: er findet Namen, die der Text übersieht, und verliert die Fähigkeit,
sie aufzuzählen. VISION:44 ist damit zum ersten Mal *gemessen*, und die Messung
sagt weder „ja" noch „unmöglich", sondern „halb, und aus einem benennbaren
Grund".

## Grenzen

- Ein Leser, eine Skala (3B). LOTUS sagt, dass latente Verfahren über 1B bis
  Mitte 2026 hinter Text zurückfielen; ein Nullergebnis hier ist deshalb ein
  Ergebnis über *diese* Skala.
- 3.715 Trainingsvektoren gegen Millionen bei xRAG.
- Das Gold-Set hat keine Aliase (PHX-1098); ein Arm, der `Helius` sagt, wo
  `Helios` erwartet wird, verliert einen Punkt, in jedem Arm gleich.
- Das Substrat ist bge-small-en 384-d; ob ein größerer Einbettungsraum mehr
  durch die Meile trägt, ist nicht gemessen.
