# Take this

**For anyone — human or agent — who arrived with a different problem and minutes to spare.**

Most of what is reusable here is smaller than the project. This page lists the
pieces that stand on their own: where each lives, what it depends on, what was
measured about it, and what it does not do. Everything is Apache-2.0 — copy it,
change it, ship it; keep the licence notice. You do not need to adopt the
substrate, agree with the vision, or tell anyone.

Each entry names its evidence. The numbers are this project's own measurements,
with their limits in the linked document; none of them is a claim about your
data.

## Copy one file

**Epistemic frames as factorised axes** — `src/theogony/mesh/frames.py`
(364 lines, standard library only; 17 tests in `tests/mesh/test_frames.py`).
A claim's stance — definition, current, historical, refuted, hypothesis,
observation, quote, disputed, superseded — as a point on seven weighted axes
(veridicality, modality, time, standing, force, attribution, register) instead
of a label, so that "refuted" and "current" are *opposed* (cosine −0.50) while
"definition" and "current" are nearly the same (0.98), and a query can ask for
"what is", "what was believed" or "what is contested" as a direction.
Evidence: [`etappes/contradiction.md`](etappes/contradiction.md) — routing on
hashed frames cost 42 points of recall; on these, both sides of a known
contradiction are retrieved for 6 of 7 cases. Limit: seven of 64 dimensions are
used; nothing is learned.

**Two tests that keep a documentation-heavy repository honest** —
`tests/test_docs_links.py` (88 lines) fails on any relative markdown link that
does not resolve to a *tracked* file; `tests/test_phoenix_backlog_consistency.py`
(167 lines) fails when a ticket's YAML and its catalogue row disagree, when a
closed ticket has no resolution, or when one in progress does not say what
remains. Standard library only. The link test failed twice in the two days
before this page was written — both times on a link to a file that existed on
disk and had not been committed, which is exactly what a reader of the
repository would have hit.

**SQuAD exact match and token F1, with answer aliases** —
`src/theogony/mesh/eval/qa_answers.py` (`exact_match`, `token_f1`,
`best_over_golds`; standard library only).

**An exact paired sign test** — `sign_test_p` and `paired_qa` in
`src/theogony/mesh/eval/qa_mesh.py`: McNemar without the normal approximation,
for two arms that answered the same questions.

## Copy a rule

**A gold set must not contain its own answers.** Two tests in
`tests/mesh/test_corpus_qa_eval.py`: no expected name, and no alias, may appear
in its own question; every alias must belong to a name the question expects.
Evidence: [`etappes/gold_aliases.md`](etappes/gold_aliases.md) — 30 of 111
gold names stood in their own question and three expectations were simply wrong.
Re-scoring the *same stored answers* under the repaired set moved the control
arm from 47% to 86% and flipped a headline from +11 to −11.

**Run the quickstart as a stranger.** Fresh clone, fresh virtual environment,
`env -i`, the documented commands verbatim, and an MCP client that drives the
server over stdio. Evidence: [`etappes/arriving_agent.md`](etappes/arriving_agent.md)
— seven defects on the first run, none visible to 1,960 tests.
`scripts/fresh_clone_probe.sh` and `scripts/mcp_probe.py` are the instrument.

**Report the ceiling with the score.** Every answer arm records whether the
gold answer stood in the material the model was given (`gold_in_context`), so a
reading problem can be told from a retrieval problem. Conflating the two —
is the answer absent, or present and not used? — produced wrong diagnoses here
more than once (PHX-1067).

## Lift a component

**Replay an LLM-extracted graph without the LLM** — `ReplayReadingProvider`,
`load_readings`, `readings_by_paragraph` in `src/theogony/mesh/eval/qa_mesh.py`.
Record each paragraph's extraction once; afterwards any number of graphs can be
rebuilt from the recordings through the real write path — deterministic, free,
no key. Here: 6,119 passages, 35,906 nodes, zero LLM calls.

**A five-arm answer benchmark** — `build_qa_jobs`, `answer_qa_set` in the same
module; `scripts/mesh_qa_constellation.py` drives it. Prior, plain passages,
entities without edges, entities with edges, entities with typed edges only —
one model, one scorer, paired. Evidence:
[`etappes/qa_constellation.md`](etappes/qa_constellation.md).

**Proposing contradictions structurally, before asking a model** —
`src/theogony/mesh/runtime/contradiction.py`. Candidates are pairs of relations
that share an endpoint and a descriptor class but name different partners and
are witnessed by disjoint passages; descriptors are normalised first (thirty
spellings of parenthood, half of them reversed, fold into one directed class);
only then does a model adjudicate, in two steps — is this relation
single-valued, and do the fillers differ. Evidence: the one-step prompt
confirmed 36 of 100 candidates, most of them wrongly; the two-step prompt 3 of
60. Limit: on the founding corpus the pass finds two of seven known
contradictions; extraction noise dominates its precision.

**Homeostatic renormalisation that actually opposes growth** —
`renormalise_edges_inplace` in `src/theogony/mesh/storage/edges.py` (pure
Python over a list of edge objects, despite the module's imports). Evidence:
[`etappes/renormalisation.md`](etappes/renormalisation.md) — scaling alone is
invisible to a row-normalised operator and, uncapped, became an amplifier
(−3.8 points on unused questions); scaling *plus* a weight cap removed the
displacement in every run.

**Personalised PageRank and spreading activation over a sparse CSR tensor** —
`src/theogony/mesh/retrieval/propagation.py` (209 lines, PyTorch).

**Soft-token injection of graph nodes into a frozen reader (xRAG stage 1)** —
`src/theogony/mesh/eval/latent_mile.py`, including a hand-rolled greedy decode
over `past_key_values`, because `generate(inputs_embeds=…)` returns garbage on
Apple MPS with transformers 5.5. Evidence:
[`etappes/latent_mile.md`](etappes/latent_mile.md) — **a null result, kept**:
the projected token carries identity (2.4 nats for the right node's name against
6.8 for a wrong one, on held-out nodes) and the reader still cannot answer from
it (better than text on 0 of 39 questions).

## Findings that need no code

- **One Lance fragment per appended row, until something compacts.** Every
  vector search reads every fragment: 98 ms against 10 ms on the same 2,617
  rows, and a long ingest went from 0.55 s to over 6 s per paragraph within 400
  paragraphs. Compact during the write, not only in maintenance
  ([`etappes/qa_constellation.md`](etappes/qa_constellation.md)).
- **Structural edges in a rendered graph context cost the reader accuracy.**
  Co-occurrence and provenance lines were 60% of the relations shown; removing
  them was worth +2.9 exact match (p = 0.004, n = 1,000). The model answers
  with the wrong *kind* of entity when they are present.
- **A list of entities invites an entity as the answer.** On yes/no questions a
  graph context scored 37% where the model's unaided prior scored 57%.
- **The same model name is not the same model.** One provider alias moved nine
  points on an unchanged closed-book benchmark in three weeks. Compare within a
  run.
- **"Stub" is not "offline".** Deciding behaviour on a test double's base class
  silently rerouted the tests that used it on purpose.
- **A server that logs to stdout is not an MCP stdio server.**
- **A scorer that strips digits cannot score dates**, and a substring scorer
  pays any arm that repeats the question.

## If you take something

Nothing is asked. If a piece fails on your data, that is worth more here than a
star: [`phoenix-backlog/`](../phoenix-backlog/) holds the open work, and a
ticket that says *measured on X, broke at Y* is the form every finding in this
repository took.
