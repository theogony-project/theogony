"""Local feature extraction for the QA benchmark — embeddings and spaCy entities.

Both benchmark drivers (cheap construction and Kadmos-grade) need the same
passage/question embeddings and the same spaCy NER, so they live here rather than
being copied into each script. Everything runs locally and offline.

Kept apart from :mod:`theogony.mesh.eval.qa_retrieval` (pure scoring compute) and
:mod:`theogony.mesh.eval.qa_datasets` (dataset I/O).
"""

from __future__ import annotations

from typing import Any

import torch

# spaCy entity labels worth keeping as graph nodes. CARDINAL / ORDINAL / PERCENT
# and friends are dropped: they are extremely high-frequency and would become
# exactly the generic degree hubs that swallow activation (PHX-1042).
KEEP_ENTITY_LABELS = frozenset(
    {
        "PERSON",
        "NORP",
        "FAC",
        "ORG",
        "GPE",
        "LOC",
        "PRODUCT",
        "EVENT",
        "WORK_OF_ART",
        "LAW",
        "LANGUAGE",
    }
)

# bge-* models want this instruction on the query side only.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def embed_texts(
    model: Any,
    texts: list[str],
    *,
    batch_size: int = 64,
    instruction: str = "",
    show_progress: bool = True,
) -> torch.Tensor:
    """Encode ``texts`` with a SentenceTransformer, returning an (N, D) float tensor."""
    if not texts:
        return torch.zeros((0, int(model.get_sentence_embedding_dimension())), dtype=torch.float32)
    payload = [instruction + t for t in texts] if instruction else texts
    vecs = model.encode(
        payload,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=show_progress,
    )
    return torch.tensor(vecs, dtype=torch.float32)


def extract_spacy_entities(
    nlp: Any,
    texts: list[str],
    *,
    batch_size: int = 64,
) -> tuple[list[str], list[set[int]]]:
    """Run spaCy NER over ``texts``.

    Returns ``(entity_names, entities_per_text)`` where entity identity is the
    lowercased surface form — the same naive normalisation the Kadmos-grade path
    uses on LLM labels, so the two constructions are compared on equal footing.
    """
    entity_to_idx: dict[str, int] = {}
    per_text: list[set[int]] = []
    for doc in nlp.pipe(texts, batch_size=batch_size):
        ents: set[int] = set()
        for ent in doc.ents:
            if ent.label_ not in KEEP_ENTITY_LABELS:
                continue
            key = ent.text.strip().lower()
            if len(key) < 2:
                continue
            idx = entity_to_idx.get(key)
            if idx is None:
                idx = len(entity_to_idx)
                entity_to_idx[key] = idx
            ents.add(idx)
        per_text.append(ents)
    names = [""] * len(entity_to_idx)
    for name, idx in entity_to_idx.items():
        names[idx] = name
    return names, per_text
