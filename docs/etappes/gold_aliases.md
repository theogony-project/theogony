# Das Gold-Set repariert: Aliase, und nichts mehr, was die Frage verrät (PHX-1098)

**Stand:** 2026-09-16, gemessen. Spur C des Plans, erstes Stück.
**Werkzeug:** `eval/gold/founding_corpus.json` (`aliases` je Frage), `corpus_answers._score(…, aliases)`, `corpus_qa.GoldQuestion.names_for`, zwei neue Hygiene-Tests.

## Zwei Fehler in einer Datei

**Keine Aliase.** Der Bewerter verglich den Gold-String wörtlich. Das Gold sagte
`Helius`, die Übersetzung und die Modelle sagen auch `Helios`, und so bekam
„Eos, Selene, Helios, Helius" 3 von 3 dafür, einen Gott zweimal zu nennen,
während das richtige „Helios, Eos, Selene" 2 von 3 bekam. Ein Gold-Set, das
durch eine Verdopplung zu erfüllen war, die das Substrat entfernen soll
(gefunden in PHX-1097, bewusst nicht dort behoben, weil eine
Instrumentkorrektur, die mit dem Ergebnis landet, das sie schmeichelt, nichts
wert ist).

**Die Frage verriet die Antwort.** 30 der 111 Gold-Namen standen in ihrer
eigenen Frage — „What measures the depth of Tartarus?" erwartete `Tartarus`,
„How were Chrysaor and Pegasus born?" erwartete Chrysaor und Pegasus. Ein
Substring-Bewerter bezahlt das, sobald eine Antwort die Frage nachspricht, und
bezahlt einen Arm, der in Sätzen antwortet, am meisten: der weiche Arm der
latenten Meile (PHX-1109) kam so auf 28 %, wo eine strenge Zählung 11 % gab.

Beim Aufräumen stellten sich **drei Erwartungen als schlicht falsch** heraus,
jede gegen den Korpus geprüft:

| Frage | stand im Gold | steht im Text |
|---|---|---|
| Whom did Hermaon beget with Thronia? | Thronia, Belus | **Arabus** — Belus ist Thronias Vater (Fr. 15) |
| What offspring did Echidna bear to Orthus? | Echidna, Orthus | **Sphinx** und **Nemean lion** (Theog. 326) |
| Who are the sons of Iapetus? | Menoetius, Prometheus, Epimetheus | dazu **Atlas** (Theog. 509) |

Und mehrere Fragen, deren „Antwort" nur ihr eigenes Subjekt war, erwarten
jetzt, was sie fragen: `fifty` für die Töchter des Nereus, `foam` für
Aphrodite, `anvil` für die Tiefe des Tartaros, `fire` für die Chimaira,
`flesh`/`bones` für die Portionen des Prometheus, `Earth`/`Heaven` für den
Grund, aus dem Kronos seine Kinder verschlang.

## Was sich geändert hat

- **92 Gold-Namen statt 111, mit 130 Aliasen.** Jeder Name trägt die
  Schreibungen, die diese Übersetzung und die Modelle benutzen (Helius/Helios,
  Heaven/Uranus, Sea/Pontus, Eunomia/Order). Der Bewerter akzeptiert jede und
  zählt den kanonischen Namen einmal.
- **Der Retrieval-Abgleich** liest die Aliase ebenfalls: ein Knoten, den das
  Substrat `Helios` nennt, beantwortet einen Gold-Eintrag `Helius`.
- **Zwei Tests halten das fest:** kein erwarteter Name und kein Alias steht in
  seiner eigenen Frage; jeder Alias gehört zu einem erwarteten Namen. Die
  Zählungen sind exakt gepinnt (92, 65 genealogisch), weil eine Untergrenze
  nicht bemerkt, wenn eine veröffentlichte Zahl aufhört, zur Datei zu passen.

## Die Neubewertung — die Wirkung des Instruments, getrennt vom Modell

Die Tickets PHX-1087, 1096 und 1097 wurden auf dem alten Bewerter gemessen.
Ihre Zahlen werden hier nicht stillschweigend ersetzt, sondern die Änderung
wird selbst gemessen: **dieselben gespeicherten Antworten, drei Bewertungen.**

### Die latente Meile (PHX-1109), gespeicherte Antworten des 3B-Lesers

| Arm | altes Gold, 111 Namen | altes Gold ohne die nachgesprochenen | neues Gold, 92 Namen mit Aliasen |
|---|---|---|---|
| `closed_book` | 16 % (4/47) | 14 % (3/39) | 15 % (6/47) |
| `constellation` (Text) | 38 % (8/47) | 49 % (13/39) | **47 % (16/47)** |
| `soft`, 20 Epochen | 28 % (11/47) | 11 % (4/39) | **14 % (6/47)** |
| `soft`, 5 Epochen | 19 % (6/47) | 9 % (2/39) | 10 % (3/47) |
| `soft_untrained` | 11 % (2/47) | 0 % (0/39) | 0 % (0/47) |

Das neue Gold reproduziert die strenge Zählung aus PHX-1109 fast auf den Punkt
— und tut es über alle 47 Fragen statt über die 39, die die strenge Zählung
übrig ließ. Der Text-Arm steigt (die Aliase zahlen sich aus, und die Fragen
verlangen jetzt Antworten, die er gibt), der weiche Arm fällt auf das, was er
wirklich trägt. Die beiden Korrekturen — im Harness und in der Datei — sagen
dasselbe, unabhängig voneinander.

### Retrieval auf dem Founding-Mesh (`k_seeds=1`, `top_k=50`, 14 Ticks)

| | altes Gold | neues Gold |
|---|---|---|
| Recall | 87 % | **80 %** (72 von 90 vorhandenen) |
| vollständig | 39/47 | 34/47 |
| genealogisch / erzählend | — | 86 % / 65 % |

Der Rückgang ist die Korrektur selbst: die nachgesprochenen Namen waren gratis
abrufbar, weil die Frage sie nennt und die Namensanker sie seeden. Was jetzt
fehlt, sind echte Antworten, und zwei davon sind keine Entitäten (`fifty`,
`anvil` — Abdeckung 98 %) und einige weitere sind Gemeinnamen, die das
Substrat hält, aber nicht aktiviert (`foam`, `fire`, `stone`, `Sea`, `Hecate`,
die drei Schildfiguren, `flesh`/`bones`). Das ist eine ehrlichere Zahl für den
erzählenden Teil: 65 % statt der 86 %, die PHX-1080 für ihn berichtete.

### Der Antwort-Arm (deepseek-chat, drei Wiederholungen, `data/mesh-founding`)

*(folgt, sobald der Lauf durch ist)*
