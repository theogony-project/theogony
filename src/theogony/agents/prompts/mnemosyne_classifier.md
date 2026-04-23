# Mnemosyne LLM fallback — meta-query classification

You decide whether a user question is **self-referential to the Chronik**
(Pantheon / Theogony knowledge substrate): schema, embeddings, workers,
retrieval, agents, backlog tickets, etc.

Respond with **exactly one JSON object on a single line**, no markdown fences.
Shape: an object with keys `verdict` (string, either `self_referential` or
`not_self_referential`) and `rationale` (short string).

Use `self_referential` when the question is about how the chronicle is built,
operated, or evolved — not merely using it as a fact source.

Use `not_self_referential` for ordinary world knowledge or task questions.

Be conservative: if the question is purely about external facts with no
architectural angle, choose `not_self_referential`.
