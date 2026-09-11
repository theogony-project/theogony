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

*(wird nach dem Lauf eingetragen)*

### Das Training

### Die vier Arme

### Lesung

## Grenzen

- Ein Leser, eine Skala (3B). LOTUS sagt, dass latente Verfahren über 1B bis
  Mitte 2026 hinter Text zurückfielen; ein Nullergebnis hier ist deshalb ein
  Ergebnis über *diese* Skala.
- 3.715 Trainingsvektoren gegen Millionen bei xRAG.
- Das Gold-Set hat keine Aliase (PHX-1098); ein Arm, der `Helius` sagt, wo
  `Helios` erwartet wird, verliert einen Punkt, in jedem Arm gleich.
- Das Substrat ist bge-small-en 384-d; ob ein größerer Einbettungsraum mehr
  durch die Meile trägt, ist nicht gemessen.
