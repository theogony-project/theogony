"""PHX-1052 — the passage's protagonist must become an entity, not just a theme.

Measured live on both Haiku 4.5 and Sonnet 4.6: the central figure of a passage
landed only as `paragraph_concept` and never as a concept, so the foam-birth
passage produced Cronos, Gaia, Cyprus and Eros — but no Aphrodite. The entity the
text is *about* was the one entity missing.

The fix was prompt-text only, which left it unguarded: nothing failed if the
requirement was edited out, and nothing noticed if a model stopped honouring it.
Three layers close that, each catching a different kind of drift:

1. **Prompt contract** — the instruction is still in the prompt. Catches an editor
   dropping it; cannot see model behaviour at all.
2. **Pipeline behaviour** — a protagonist-bearing reading materialises the
   protagonist as its own consolidated node, distinct from the paragraph concept.
   Catches the ingestion path regressing to folding protagonists into the theme.
3. **Live characterization** (opt-in) — the actual model, on the actual passage
   that failed. The only layer that can catch model drift, and therefore the only
   one that tests what PHX-1052 was really about.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import SYSTEM_PROMPT, MeshParagraphReader
from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

# The foam-birth passage from Hesiod's Theogony — the one that produced the
# original failure. Kept verbatim so the live layer probes the measured case.
FOAM_BIRTH = (
    "And so soon as he had cut off the members with flint and cast them from the "
    "land into the surging sea, white foam spread around them from the immortal "
    "flesh, and in it there grew a maiden. First she drew near holy Cythera, and "
    "from there, afterwards, she came to sea-girt Cyprus, and came forth an awful "
    "and lovely goddess, and grass grew up about her beneath her shapely feet. Her "
    "gods and men call Aphrodite."
)


# ---------------------------------------------------------------------------
# 1. Prompt contract
# ---------------------------------------------------------------------------


def test_prompt_still_requires_the_protagonist_as_a_named_concept() -> None:
    """The instruction must survive prompt edits — it is the whole fix."""
    prompt = SYSTEM_PROMPT.lower()
    assert "central figure" in prompt
    assert "concepts" in prompt
    # The prompt must forbid the exact failure mode, not merely mention protagonists.
    assert "paragraph_concept alone" in prompt or "never leave the protagonist" in prompt


def test_prompt_still_requires_variant_names_to_keep_the_texts_label() -> None:
    """Venus/Jove must stay the text's label with the canonical name as a tag.

    Same commit, same failure family: without it a variant name either vanishes or
    silently overwrites the canonical entity's label.
    """
    prompt = SYSTEM_PROMPT.lower()
    assert "variant" in prompt
    assert "tags" in prompt


# ---------------------------------------------------------------------------
# 2. Pipeline behaviour
# ---------------------------------------------------------------------------


_READING_WITH_PROTAGONIST = json.dumps(
    {
        "concepts": [
            {
                "label": "Aphrodite",
                "entity_type": "person",
                "tags": ["goddess", "olympian"],
                "description": "Greek goddess of love, born from the sea foam.",
                "qids": [{"qid": "Q35500", "confidence": 0.95}],
            },
            {
                "label": "Cyprus",
                "entity_type": "place",
                "tags": ["island"],
                "description": "Island the goddess came to after her birth.",
                "qids": [],
            },
        ],
        "relations": [
            {
                "source": "Aphrodite",
                "target": "Cyprus",
                "relation_descriptor": "came_to",
                "relation_kind": "semantic",
                "rationale": "The passage says she came to sea-girt Cyprus.",
            }
        ],
        "paragraph_concept": {
            "label": "The birth of Aphrodite from sea foam",
            "description": "The passage narrates the goddess's birth from the foam.",
            "tags": ["myth", "paragraph_concept"],
            "basis_concepts": ["Aphrodite", "Cyprus"],
        },
    }
)


def test_protagonist_becomes_its_own_node_not_only_the_paragraph_concept(
    mesh_runtime: MeshRuntime,
) -> None:
    """The protagonist and the theme must be *different* nodes.

    The original bug was the protagonist being representable only through the
    paragraph concept. Asserting both exist separately pins the distinction.
    """
    llm = StubLLMProvider(responses={f"PARAGRAPH:\n{FOAM_BIRTH}": _READING_WITH_PROTAGONIST})
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=5)

    asyncio.run(
        reader.read_text(
            text=FOAM_BIRTH,
            source_type="test",
            source_identifier="phx-1052",
            title="Foam birth",
            anchor="fixture://phx-1052",
        )
    )

    descriptions = [(node.description or "") for node in mesh_runtime.nodes.iter_consolidated()]
    protagonist = [d for d in descriptions if "goddess of love" in d]
    paragraph_concept = [d for d in descriptions if "narrates the goddess" in d]

    assert protagonist, "the protagonist was not materialised as its own node"
    assert paragraph_concept, "the paragraph concept was not materialised"
    # Distinct nodes — the theme must not stand in for the entity.
    assert protagonist != paragraph_concept


def test_identity_evidence_persists_when_the_caller_vouches_for_it(
    mesh_runtime: MeshRuntime,
) -> None:
    """PHX-1053's guarantee, kept where it is real.

    A Q-ID handed over by a caller that vouches for it — the wikidata5m seed
    import — must survive the merge and stay Q-ID-addressable. That was the
    PHX-1053 failure: Aphrodite's Q35500 merged into a hymn concept and
    evaporated with the process.
    """
    from datetime import UTC, datetime

    from theogony.mesh.schemas import QIDTag

    linker = EagerLinker(
        mesh_runtime.nodes,
        mesh_runtime.edges,
        semantic_dim=mesh_runtime.semantic_dim,
        frame_dim=mesh_runtime.frame_dim,
    )
    linker.link_reference(
        label="Aphrodite",
        description="Greek goddess of love born from sea foam",
        tags=["goddess"],
        qids=[QIDTag(qid="Q35500", confidence=0.99, attached_at=datetime.now(UTC))],
        semantic_vector=[0.1] * mesh_runtime.semantic_dim,
        frame_vector=[0.0] * mesh_runtime.frame_dim,
        description_vector=[0.1] * mesh_runtime.semantic_dim,
        qids_are_authoritative=True,
    )

    assert mesh_runtime.nodes.get_consolidated_by_qid("Q35500") is not None


def test_the_reader_does_not_vouch_for_the_model(mesh_runtime: MeshRuntime) -> None:
    """The other side of that boundary, and the reason it exists.

    Of 130 Q-IDs the reading model wrote into the founding mesh, 3 were
    plausible, 122 named an unrelated entity and 5 did not exist: Gaia carried
    the identifier of analytical chemistry, Cronus that of Anubis, Hera that of
    Willy Brandt. Stored, those are durable and Q-ID-addressable — a later
    reference carrying the same identifier merges straight into the wrong node.

    The protagonist itself must still be materialised; that is PHX-1052 and it
    is asserted above. What must not happen is the guess being written down
    (PHX-1063).
    """
    llm = StubLLMProvider(responses={f"PARAGRAPH:\n{FOAM_BIRTH}": _READING_WITH_PROTAGONIST})
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=5)
    asyncio.run(
        reader.read_text(
            text=FOAM_BIRTH,
            source_type="test",
            source_identifier="phx-1052-qid",
            title="Foam birth",
            anchor="fixture://phx-1052-qid",
        )
    )

    assert mesh_runtime.nodes.get_consolidated_by_qid("Q35500") is None
    descriptions = [(n.description or "") for n in mesh_runtime.nodes.iter_consolidated()]
    assert [d for d in descriptions if "goddess of love" in d], "protagonist still required"


# ---------------------------------------------------------------------------
# 3. Live characterization — the only layer that sees model drift
# ---------------------------------------------------------------------------


@pytest.mark.characterization
@pytest.mark.skipif(
    os.environ.get("THEOGONY_RUN_CHARACTERIZATION") != "1",
    reason="opt-in: costs a real LLM call (THEOGONY_RUN_CHARACTERIZATION=1)",
)
def test_live_model_extracts_the_protagonist(mesh_runtime: MeshRuntime) -> None:
    """The measured failure case, against the configured model.

    PHX-1052 was a *model behaviour* bug: no stub can catch it coming back. This
    runs the real reader over the passage that failed and asserts the goddess is
    among the extracted entities. One paragraph, one call — cents, not euros.
    """
    from theogony.agents.factory import build_llm_from_settings
    from theogony.config.settings import Settings

    settings = Settings()
    reader = MeshParagraphReader(
        mesh_runtime, llm=build_llm_from_settings(settings), max_paragraphs=1, settings=settings
    )
    result = asyncio.run(
        reader.read_text(
            text=FOAM_BIRTH,
            source_type="characterization",
            source_identifier="phx-1052-live",
            title="Foam birth",
            anchor="fixture://phx-1052-live",
        )
    )
    assert result is not None

    blob = " ".join(
        f"{node.description or ''} {' '.join(node.tags)}"
        for node in mesh_runtime.nodes.iter_consolidated()
    ).lower()
    assert "aphrodite" in blob or "venus" in blob, (
        "the passage's protagonist was not extracted — PHX-1052 has regressed"
    )
