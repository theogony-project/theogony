# Das Gedächtnis des Widerspruchs (PHX-1107)

> **English abstract.** *Finding.* The mesh could not represent a contradiction:
> ten relation kinds, none of them a disagreement, and frame vectors that were a
> salted hash of the label. Everything that heals would have to read from that.
> *Built.* Epistemic frames as seven weighted axes instead of seven labels (nine
> stances as points: refuted against current cosine −0.50, definition against
> current +0.98); `contradicts` and `supersedes` as relation kinds with
> `valid_from` / `valid_to` on the edge; the founding corpus read again with
> stances (eight stance values in use, 39 paragraphs `disputed`, 30
> `contradicts` relations written by the reader itself); and a contradiction
> pass — 690 structural candidates, 74 confirmed (11%), 334 edges, 141
> paragraphs marked disputed, eleven minutes. Two things made the pass find
> anything: descriptor normalisation (parenthood arrives under more than thirty
> spellings, half of them reversed: 0 → 202 candidates) and a two-step
> adjudicator that first asks whether the relation is single-valued (36 of 100
> confirmed → 3 of 60). *Measured* on seven verified contradictions of the
> corpus: both sides in the Constellation for 6 of 7 on the re-read mesh, 5 of 7
> on the old one. The strongest finding is the control: frame routing on the old
> hashed frames costs 42 points (5/7 → 2/7); on real frames it costs nothing.
> Routing did nothing at all until entities inherited the centroid of their
> paragraphs' frames — 82% of them held no stance — and after that it trades one
> question for another rather than gaining. *Limits.* 86% against 71% confounds
> re-reading with framing; extraction noise sits among the confirmed
> contradictions; frame promotion is not part of the tick.

**Stand:** 2026-09-12, gemessen. Branch `feat/phx-1107-contradiction`.
**Anlass:** [`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md) §B — der eine Befund der Vision-Ledger, der die Reihenfolge festlegt.
**Werkzeug:** `src/theogony/mesh/frames.py`, `src/theogony/mesh/runtime/contradiction.py`, `scripts/mesh_contradictions.py`, `scripts/mesh_contradiction_eval.py`, Gold-Set `eval/gold/founding_contradictions.json`.

## Der Befund

Fünf Nicht-Verhandelbare aus PANTHEON_VISION scheitern nicht an fehlendem
Code, sondern am Datenmodell. Das Substrat konnte nicht sagen, dass es etwas
bezweifelt: `relation_kind` hatte zehn Werte und keiner war eine Uneinigkeit,
`temporal_vector` war auf jedem Knoten `None`, und `frame_vector` — das Feld,
in das die Doktrin die epistemische Haltung verlegt hat — trug eine gesalzene
SHA-256-Projektion des Labels (PHX-1095). 5.002 Knoten, 4.977 verschiedene
Vektoren, keine Haltung darin.

Damit konnte Frame-Routing nur nach einem Hash maskieren, und alles, was aus
dem Frame lesen müsste — Athene, Chronos, das Immunsystem, die Chronik, die
zweite Säule „Wissenschaftlicher Arbeitstisch" — hatte nichts zu lesen. Das
Verb *heilt* war nicht ungebaut. Es war unbaubar.

## Was gebaut wurde

### 1. Der Frame als faktorisierte Basis, nicht als Etikett

Die Doktrin nennt sieben Frames (Definition, aktuelle Behauptung, historische
Behauptung, widerlegte Behauptung, Hypothese, Beobachtung, direktes Zitat) und
sagt, sie seien „gelernte Einbettungsregionen", mit einem regelbasierten
Bootstrap als ausdrücklichem Zwischenschritt. Das ist dieser Bootstrap, und er
ist **faktorisiert statt aufgezählt**: sieben Achsen spannen den Raum, die
Frames sind Punkte darin.

| Achse | Pole | Gewicht |
|---|---|---|
| veridicality | behauptet ↔ verneint | 2,0 |
| modality | faktisch ↔ hypothetisch | 1,0 |
| time | aktuell ↔ historisch | 1,0 |
| standing | unbestritten ↔ bestritten | 1,0 |
| force | in Kraft ↔ abgelöst | 1,0 |
| attribution | direkt ↔ zugeschrieben | 0,5 |
| register | allgemein ↔ besonders | 0,5 |

Die Faktorisierung ist der Punkt: eine historische Behauptung, die *auch*
widerlegt wurde, ist beides — `time = −1` und `veridicality = −1` — und keine
Aufzählung von sieben Etiketten kann das ausdrücken. Kadmos gibt trotzdem ein
Etikett aus, weil ein Etikett das ist, was ein Sprachmodell zuverlässig
produziert; das Etikett benennt einen Punkt, und Punkte lassen sich mischen.

Veridikalität wiegt doppelt, weil die Verneinung der Grund ist, aus dem die
Doktrin das Feld überhaupt einführt: „Thyroxine is an oxindole derivative" und
seine Verneinung landen semantisch am selben Punkt.

**Was der Cosinus dann tut** — das ist die Doktrin-Rechnung, nicht eine
Behauptung über sie:

| | gegen *aktuelle Behauptung* |
|---|---|
| Definition | +0,98 |
| Beobachtung | +0,77 |
| direktes Zitat | +0,77 |
| historische Behauptung | +0,65 |
| abgelöst | +0,50 |
| widerlegt | **−0,50 → 0,0** |

Genau das Kendall-Verhalten aus MESH_RETRIEVAL: „Was ist Thyroxin?" holt die
widerlegte Struktur von 1915 nicht. Was sie holt, ist nicht die historische
Haltung allein — die *bejaht*, was die Widerlegung verneint, also stehen die
beiden einander entgegen — sondern das Profil, das beide mischt.

**Zwei Designfehler wurden beim Bauen gemessen und behoben.** Ein direktes
Zitat war ohne positive Veridikalität exakt orthogonal zu jeder Behauptung und
wurde von jeder Sachfrage auf null gedämpft — auf einem Korpus, der zur Hälfte
direkte Rede ist, hätte das die Hälfte des Substrats aus dem Retrieval
gelöscht. Und das Widerspruchs-Profil, aus Haltungen gebaut, erbte deren
positive Veridikalität, die alles andere überstimmte: es ließ jede schlichte
Behauptung durch und dämpfte die widerlegte auf null, also das Gegenteil
dessen, wofür es da ist. Es ist jetzt in Achsen geschrieben — „bestritten oder
abgelöst, und schweigt darüber, ob es wahr ist" — und dämpft jede unstrittige
Behauptung auf exakt null.

### 2. Wer trägt welche Haltung

- **Chunks** (die Beobachtung) tragen die Haltung des Absatzes.
- **Entitäten und Quellanker** sind neutral. „Zeus" ist weder behauptet noch
  verneint; die Behauptungen über ihn liegen auf den Chunks. Der Nullvektor
  ist konstruktionsgemäß neutral und wird nie gedämpft.
- **Kanten** bekommen `frame_consistency` aus den Endpunkten — der fehlende
  Pass, den PHX-1095 benannte („a missing pass, not missing data"). Wo ein
  Endpunkt eine Entität ist, ist der Wert 1,0; wo beide Absätze sind, trägt er
  Information.
- **`valid_from` / `valid_to`** auf jeder Kante, die kleinste Darstellung von
  Zeit, die Nicht-Verhandelbares 3 verlangt. Beide reiten im `payload_json`,
  also braucht kein bestehendes Mesh eine Migration.

### 3. Der Pass, der Widersprüche findet

Eine Haltung sagt, wie *ein* Absatz spricht. Ein Widerspruch ist eine Relation
*zwischen* zweien, und ein Leser, der Absatz für Absatz liest, sieht ihn nie —
er sieht den anderen Absatz nicht. Also braucht es einen Pass über das fertige
Mesh; die Doktrin beschreibt ihn in der Stimme eines Agenten, den es nicht
gibt (Argus, MESH_SUBSTRATE §„Contradiction resolution").

Kandidaten strukturell, dann adjudiziert — dieselbe Arbeitsteilung wie die
Oneiros-Konsolidierung. Ein Kandidat sind zwei Relationen, die sich einen
Endpunkt und einen Deskriptor teilen und über den anderen uneins sind:

    Nacht  --gebar-->  die Moiren        (Theogonie 211-225)
    Themis --gebar-->  die Moiren        (Theogonie 901-906)

**Der Filter, der das präzise macht, ist die Provenienz, nicht die Semantik.**
Zwei Relationen aus demselben Absatz sind eine Aufzählung — „Rhea gebar
Hestia, Demeter, Hera" sind drei Kanten und keine Uneinigkeit —, also verlangt
ein Kandidat, dass die beiden Seiten von *verschiedenen* Absätzen bezeugt
werden. Ohne diesen Filter ist jede Genealogie des Korpus ein Widerspruch.

Was übrig bleibt, ist meist trotzdem vereinbar: Zeus zeugt viele Kinder, und
`father_of` ist nicht funktional. Dafür ist der Adjudikator da — gefragt wird,
ob beides zugleich wahr sein kann, nicht ob es ähnlich aussieht.

Bestätigte Widersprüche bekommen `contradicts`-Kanten zwischen den
bezeugenden Absätzen, und diese Absätze werden auf die Haltung `disputed`
gesetzt. Der zweite Teil ist der, der den Befund ins Retrieval bringt.
Gelöscht wird nichts und keine Seite wird für falsch erklärt.

## Das Gold-Set

Sieben Widersprüche, jeder mit beiden Belegstellen im Korpus verifiziert
(Zeilennummer und wörtliches Zitat):

| Frage | Seite A | Seite B | Umfang |
|---|---|---|---|
| Wer gebar die Moiren? | Nacht, ohne Vater | Themis, dem Zeus | innerhalb der Theogonie |
| Wer war Asklepios' Mutter? | Arsinoe | Koronis | über Werke |
| Wer war Helenas Mutter? | eine Tochter des Okeanos | Nemesis | über Werke |
| Wer gebar Typhoeus? | Erde, von Tartaros | Hera, allein und zornig | über Werke |
| Wessen Tochter ist Nemesis? | der Nacht | des Zeus | über Werke |
| Wie wurde Aphrodite geboren? | aus dem Schaum | Tochter des Zeus | über Werke |
| Hatte Hephaistos einen Vater? | Hera allein | Zeus sein Vater | innerhalb der Theogonie |

Zwei davon markiert der Korpus selbst als strittig („Some say (Asclepius) was
the son of Arsinoe, others of Coronis", Zeile 1433; „Hesiod, however, makes
Helen the child neither of Leda nor Nemesis", Zeile 1455) — die kann Kadmos
beim Lesen erkennen. Die anderen fünf sind nur durch den Vergleich über
Absätze hinweg zu finden.

**Works and Days ist in dieser Ausgabe nicht enthalten.** Das Ticket hatte die
Pandora-Erzählung und die Zeitalter der Menschen als Widersprüche vermutet;
beide gibt es hier nicht. Die Musen, das andere Beispiel des Tickets, sind im
ganzen Korpus einhellig Töchter des Zeus und der Mnemosyne.

Die Messung ist eine, die keine bestehende Harness ausdrücken kann:
**beide-Seiten-Recall**. Eine Frage zählt nur, wenn die Constellation aus
jeder Seite eine Entität trägt. Vier Entitäten einer Seite und keine der
anderen zählen null — das ist genau das Enzyklopädie-Verhalten, das die
Chronik verweigern soll.

## Der neu gelesene Korpus

1.206 Absätze, 2 h 27 min, € 0,39 (`deepseek-chat`). Das Substrat trägt zum
ersten Mal epistemische Haltungen:

| Haltung | Absätze |
|---|---|
| `current_claim` | 380 |
| `direct_quote` | 298 |
| `historical_claim` | 290 |
| `observation` | 111 |
| `definition` | 66 |
| `disputed` | **39** |
| `hypothesis` | 20 |
| `refuted_claim` | 2 |

Dazu **30 `contradicts`-Relationen, die das Modell beim Lesen selbst schrieb** —
Stellen, an denen der Text den Streit benennt. Und `frame_consistency` trägt
zum ersten Mal etwas: von 127.402 Kanten liegen 5.590 unter 1,0, davon **185
bei exakt 0** — Kanten zwischen Absätzen in gegensätzlichen Haltungen. PHX-1095
hatte das Feld auf allen 94.490 Kanten des alten Mesh bei exakt 1,0 gemessen.

Vor dem Volllauf wurden fünf Absätze einzeln geprüft, um zu sehen, ob das
Modell das Vokabular überhaupt benutzt: fünf von fünf richtig, und beim
Helena-Fragment schrieb es von sich aus `relation_kind: contradicts`. Der
*erste* Versuch hatte zwölf von zwölf Absätzen auf `current_claim` gesetzt —
der Prompt nannte die Haltung, zeigte aber nicht, dass sie ein Feld auf
oberster Ebene ist, und das Modell schrieb sie stattdessen auf die Relationen.

## Der Widerspruchs-Pass

690 Kandidaten, 74 bestätigt (11 %), 334 `contradicts`-Kanten, 141 Absätze auf
`disputed` gesetzt. 11 Minuten, Bruchteile eines Cent.

Darunter echte mythologische Widersprüche: Laomedon gegen Tros als Vater des
Ganymedes, Theia gegen Euryphaessa als Mutter von Eos und Selene, Klymene gegen
Alkmene als Mutter des Iphiklos, Tyro gegen Althaia als Mutter des Pheres. Und
Rauschen aus der Extraktion: Fragmentnummern, die an zwei Orten „liegen", und
ein Paar „February part_of 1321 / 1325".

**Zwei Dinge waren nötig, damit der Pass überhaupt etwas findet.**

*Deskriptor-Normalisierung.* Der strukturelle Filter vergleicht (Endpunkt,
Deskriptor), sieht eine Uneinigkeit also nur, wenn beide Seiten die Relation
gleich buchstabieren. Kadmos tut das nicht: Elternschaft kommt unter mehr als
dreißig Schreibungen an — `bore` 145, `son_of` 120, `fathered` 80,
`daughter_of` 79, `father_of` 45, `mother_of` 45, `parent_of` 43, `child_of`
26 — und die Hälfte zeigt in die andere Richtung. Mit einer kuratierten Klasse
für Verwandtschaft und kanonischer Richtung: **202 Elternschafts-Kandidaten
statt null.** Die Richtung ist dabei nicht Kosmetik, sondern macht die
Gruppierung funktional: ein Kind hat einen Vater und eine Mutter, eine Mutter
hat viele Kinder, also ist die Frage, die sich lohnt, immer „wie viele Eltern
hat dieses Kind".

*Ein zweistufiger Adjudikator.* Der erste Prompt bestätigte 36 von 100
Kandidaten — „Apollo ging nach A / ging nach B" als Widerspruch. Der zweite
fragt zuerst, ob die Relation überhaupt nur einen Wert zulässt, und erst dann,
ob die Werte verschieden sind: 3 von 60. Er erkennt auch Aliase („Earth
parent_of Cyclopes / Gaia bore Cyclopes" → vereinbar).

## Die Messung: gibt eine strittige Frage beide Seiten zurück?

Sieben Fragen, `k_seeds=1`, `top_k=50`. Eine Frage zählt nur, wenn die
Constellation aus *jeder* Seite eine Entität trägt.

| Mesh | Profil | beide Seiten | Seiten Ø |
|---|---|---|---|
| alt (Hash-Frames, konsolidiert) | `any` | 71 % (5/7) | 1,71 |
| alt (Hash-Frames) | `contradiction` | **29 % (2/7)** | 1,00 |
| neu, geframt | `any` | **86 % (6/7)** | 1,86 |
| neu, geframt | `contradiction` | 86 % (6/7) | 1,86 |

**Der stärkste Befund steht in der zweiten Zeile.** Auf dem alten Mesh kostet
dasselbe Frame-Routing 42 Punkte — es maskiert nach einem gesalzenen Hash und
zerstört die Constellation. Auf dem neuen kostet es nichts. PHX-1095 hatte
vermutet, dass „routing on them today would mask edges by a hash"; das ist die
Zahl dazu.

Der Vergleich 86 % gegen 71 % vermischt zwei Änderungen — das neue Mesh wurde
auch neu gelesen und ist unkonsolidiert (5.688 Knoten gegen 4.934) — und trägt
deshalb weniger weit als die Zeile darüber.

### Das Routing wirkt erst, wenn Entitäten eine Haltung tragen

Die erste Messung nach dem Neulesen gab für `any`, `contradiction` und
`what_is` **identische** Zahlen, Frage für Frage. Der Grund: eine Constellation
besteht aus Entitäten, und 82 % der Entitäten hielten keine Haltung — die
Haltung lag auf den Chunks. `frame_consistency` ist für einen neutralen Knoten
konstruktionsgemäß 1,0, also skalierte jedes Profil jede Kante mit 1,0. Dieselbe
Gestalt wie PHX-1104: das Substrat hielt etwas, das der Operator nicht lesen
konnte.

MESH_RETRIEVAL nennt den fehlenden Schritt in einem Nebensatz — der Frame sei
„mutable by Oneiros during consolidation (when many chunks with consistent
frames consolidate, the consolidated node inherits the dominant frame)". Gebaut
als `run_frame_promotion`: jeder Knoten nimmt den Schwerpunkt der Frames der
Absätze, die ihn erwähnen. Schwerpunkt statt Modus, weil die Mischung das
Signal ist — eine Figur, die in vierzig ruhigen und zwei strittigen Absätzen
vorkommt, soll überwiegend ruhig und ein wenig strittig lesen. 3.590 von 5.688
Knoten geerbt, 1.207 Quellanker blieben neutral.

Danach, Frage für Frage:

| Frage | `any` vorher | `contradiction` vorher | `any` nachher | `contradiction` nachher |
|---|---|---|---|---|
| fates-parentage | beide | beide | beide | **eine** |
| helen-parentage | eine | eine | eine | **beide** |
| die übrigen fünf | beide | beide | beide | beide |

**Das Routing tut jetzt etwas, und zwar das Erwartbare.** Es holt die
Helena-Frage, die kein anderes Profil holt — die eine, bei der der Korpus den
Streit selbst benennt („Hesiod, however, makes Helen the child neither of Leda
nor Nemesis"), deren Absätze also als `disputed` gelesen wurden. Und es
verliert die Moiren, zwei schlichte Genealogie-Absätze ohne Streitmarkierung,
die nur strukturell uneins sind.

Im Gesamtwert ist das ein Tausch, kein Gewinn. Als Mechanismus ist es der
Unterschied zwischen beweisbar wirkungslos und nachweisbar wirksam.
