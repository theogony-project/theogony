"""PHX-1122: under the names guard an eager link stands only when the label names the node.

The PHX-1120 audit judged a random sample of the 2Wiki mesh's mentions under
the PHX-1051 v2 guard. A re-mention placed on a node of another name was wrong
45 times in 54 decided cases; one placed on a node bearing its name was right
71 times in 77 (the 261 mentions that minted their own node set apart). Every
one of the 45 passed v2 on a shared tag that token-overlaps the label, in three
shapes:

1. the shared tag is the label itself (21): a related entity's name (an
   author's name on his book), a category the label names, or a namesake
   carrying the label as a tag;
2. the tag is a category noun inside the label (22: "film festival" on every
   festival);
3. the tag names a sibling told apart only by a numeral (2: "John I" onto
   "John II").

The names guard reads the candidate's name, its first tag, which no later link
changes, and admits a mention whose label is that name (`name_key`) or that the
reader tied to the node from both sides (``mutual``). It also closes a fourth
door of v2 that no wrong link in the sample needed: a label remembered from an
earlier link admitting the next mention by itself. A paragraph-concept node
bears no name (the reader creates it without its label among its tags), so no
mention links onto one, and a paragraph concept is named like any mention. A
missed merge leaves two nodes for consolidation; a wrong merge corrupts one
silently (MESH_SUBSTRATE.md, identity). Default stays v2.
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import pytest
from ulid import ULID

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.concept_resolver import name_key, naming_rule
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.ingestion.linker import EagerLinker, LinkDecision, NamingGuard
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode

# --------------------------------------------------------------------------
# The rule, pure
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "name"),
    [
        ("Zeus", "zeus"),
        ("U.S.", "US"),
        ("K.J. Apa", "KJ Apa"),
        ("Washington, D.C.", "Washington DC"),
        ("Mud-man", "Mud man"),
        ("O'Brien", "OBrien"),
        ("Kauai", "Kauaʻi"),
        ("México", "Mexico"),
        ("İstanbul", "Istanbul"),
        ("sea", "sea"),
        ("Ζεύς", "ζευς"),
        ("सीता", "सीता"),
    ],
)
def test_the_same_name_written_two_ways_is_exact(label: str, name: str) -> None:
    assert naming_rule(label, name) == "exact"


@pytest.mark.parametrize(
    ("label", "name"),
    [
        # shape 1: the candidate is a related entity
        ("Jens Bjørneboe", "Drømmen og hjulet"),
        ("New York City", "Queens"),
        ("Hesiod", "Theogony"),
        # shape 2: a category noun inside the label
        ("Seattle International Film Festival", "Newport International Film Festival"),
        # shape 3: siblings told apart by a numeral
        ("John I, Lord of Polanen", "John II, Lord of Polanen"),
        ("The Bat (1926 film)", "The Bat (1920 play)"),
        ("Gothelo", "Gothelo I"),
        # variants are left to consolidation: each kind, admitted, also joined
        # different entities in the 2Wiki and HotpotQA readings
        ("Academy Award", "Academy Awards"),
        ("The Rolling Stones", "Rolling Stone"),
        ("Back in Black", "Back to Black"),
        ("Louis XV of France", "Louis XV"),
        ("King James I of Scotland", "King James I"),
        ("Henry II of France", "Henry II"),
        ("MGM", "Metro-Goldwyn-Mayer"),
        ("NY", "Neil Young"),
        # what the fold keeps: the words and the spaces between them, a leading
        # article, symbols, a possessive's s, other scripts' marks
        ("Golmaal", "Gol Maal"),
        ("Mud-man", "Mudman"),
        ("The Predator", "Predator"),
        ("The Iron Man", "Iron Man"),
        ("the Police", "police"),
        ("the blessed gods", "blessed gods"),
        ("C++", "C#"),
        ("St. Peter's", "St. Peter"),
        ("सीता", "सती"),
        ("パリ", "バリ"),
        # one letter apart is another entity as often as another spelling
        ("Proto", "Ploto"),
        ("Peleus", "Peneus"),
        ("Athene", "Athena"),
        # an epithet, a qualifier on a lone name, a plural common noun
        ("Zeus the Thunderer", "Zeus"),
        ("Aphrodite of Cyprus", "Aphrodite"),
        ("goddess", "goddesses"),
        ("Ocean", "boundless sea"),
    ],
)
def test_anything_else_does_not_name_the_node(label: str, name: str) -> None:
    assert naming_rule(label, name) is None


@pytest.mark.parametrize(
    ("label", "name"),
    [
        # Kingdom of León and the viscounty of Léon in Brittany: the vector score
        # (0.775 in the PHX-1122 review's offline estimate) let it through
        ("León", "Léon"),
        # case is set aside
        ("WHO", "who"),
    ],
)
def test_known_costs_of_the_fold(label: str, name: str) -> None:
    """Names the fold equates though they can name different entities. Accents
    and case are set aside all the same: on the judged sample of PHX-1120,
    which holds only links v2 made, that keeps 7 right links (México, İstanbul,
    Thüringia), and a cost of this kind, a link v2 refused, cannot appear in
    that sample at all — the replay's audit is where it shows."""
    assert naming_rule(label, name) == "exact"


def test_an_empty_name_names_nothing() -> None:
    assert name_key(" The  Hague ") == "the hague"
    assert naming_rule("", "Zeus") is None
    assert naming_rule("...", "Zeus") is None


def test_mutual_tags_name_an_exonym_and_one_side_alone_does_not() -> None:
    assert (
        naming_rule(
            "Siam",
            "Thailand",
            mention_tags=["Siam", "Thailand", "place"],
            node_tags=["Thailand", "Siam", "place"],
        )
        == "mutual"
    )
    # the node names the mention, the mention does not name the node: a related
    # entity as often as an alias (the founding mesh merged Hesiod into his poem
    # 164 times through this door)
    assert (
        naming_rule(
            "Hesiod",
            "Theogony",
            mention_tags=["Hesiod", "poet", "concept"],
            node_tags=["Theogony", "Hesiod", "poem"],
        )
        is None
    )
    # a numeral tells two that tag each other apart: a father and a son do
    assert (
        naming_rule(
            "Edward III",
            "Edward II",
            mention_tags=["Edward III", "Edward II", "person"],
            node_tags=["Edward II", "Edward III", "person"],
        )
        is None
    )
    # an apostrophe's letter is no numeral: a translated title is one work
    assert (
        naming_rule(
            "Tolgo il disturbo",
            "I'll Be Going Now",
            mention_tags=["Tolgo il disturbo", "I'll Be Going Now", "film"],
            node_tags=["I'll Be Going Now", "Tolgo il disturbo", "film"],
        )
        == "mutual"
    )


# --------------------------------------------------------------------------
# Through the linker
# --------------------------------------------------------------------------


def _unit(*values: float) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values] + [0.0] * (8 - len(values))


def _node(name: str, *tags: str, vec: list[float]) -> ConsolidatedNode:
    return _node_tagged([name, *tags], f"{name} — an entity", vec=vec)


def _node_tagged(tags: list[str], description: str, *, vec: list[float]) -> ConsolidatedNode:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description=description,
        description_vector=vec,
        tags=tags,
    )


def _linker(
    tmp_path: Path, *nodes: ConsolidatedNode, naming_guard: NamingGuard = "names"
) -> EagerLinker:
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    for node in nodes:
        runtime.nodes.append_consolidated(node)
    return EagerLinker(
        runtime.nodes, runtime.edges, semantic_dim=8, frame_dim=4, naming_guard=naming_guard
    )


def _link(linker: EagerLinker, label: str, tags: list[str], vec: list[float]) -> LinkDecision:
    # tags as kadmos_v2._concept_tags builds them: the label first, the type last
    return linker.link_reference(
        label=label,
        description=f"{label} — as the paragraph describes it",
        tags=[label, *tags],
        qids=[],
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description_vector=vec,
    )


def _link_paragraph_concept(
    linker: EagerLinker, label: str, tags: list[str], vec: list[float]
) -> LinkDecision:
    # as kadmos_v2 links a paragraph concept: its model tags and the marker,
    # without the label
    return linker.link_reference(
        label=label,
        description=label,
        tags=[*tags, "paragraph_concept"],
        qids=[],
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description_vector=vec,
    )


def test_a_tag_naming_a_related_entity_does_not_name_the_node(tmp_path: Path) -> None:
    """Shape 1. The book carries its author's name as a tag; v2 merged the author
    into the book on that tag at a score of 0.95 (cosine 0.88)."""
    book = _node("Drømmen og hjulet", "Jens Bjørneboe", "novel", vec=_unit(1.0, 0.1))
    decision = _link(
        _linker(tmp_path, book), "Jens Bjørneboe", ["author", "person"], _unit(1.0, 0.12)
    )
    assert decision.is_new and decision.signal == "emergent"
    v2 = _linker(tmp_path / "v2", book, naming_guard="v2")
    assert _link(v2, "Jens Bjørneboe", ["author", "person"], _unit(1.0, 0.12)).node.id == book.id


def test_the_mention_lands_on_the_node_that_bears_its_name(tmp_path: Path) -> None:
    """With the author's own node in the mesh, the book is not where the mention
    goes; the named node is, though it scores lower."""
    book = _node("Drømmen og hjulet", "Jens Bjørneboe", "novel", vec=_unit(1.0, 0.1))
    author = _node("Jens Bjørneboe", "author", "person", vec=_unit(1.0, 0.5))
    linker = _linker(tmp_path, book, author)
    decision = _link(linker, "Jens Bjørneboe", ["author", "person"], _unit(1.0, 0.12))
    assert decision.node.id == author.id and not decision.is_new


def test_siblings_told_apart_by_a_numeral_stay_apart(tmp_path: Path) -> None:
    """Shape 3. The shared tag 'Lord of Polanen' token-overlaps the label, so v2
    merged John I into John II."""
    john_ii = _node("John II, Lord of Polanen", "Lord of Polanen", "person", vec=_unit(1.0, 0.1))
    decision = _link(
        _linker(tmp_path, john_ii),
        "John I, Lord of Polanen",
        ["Lord of Polanen", "person"],
        _unit(1.0, 0.11),
    )
    assert decision.is_new


def test_reciprocal_tags_merge_a_name_the_node_does_not_bear(tmp_path: Path) -> None:
    """The variant a name rule cannot see: the reader tagged each with the other."""
    thailand = _node("Thailand", "Siam", "place", vec=_unit(1.0, 0.1))
    decision = _link(_linker(tmp_path, thailand), "Siam", ["Thailand", "place"], _unit(1.0, 0.12))
    assert decision.node.id == thailand.id and decision.signal == "description"


def test_no_mention_lands_on_a_paragraph_concept(tmp_path: Path) -> None:
    """A paragraph-concept node is created without its label among its tags, so
    its first tag is a topic and it bears no name. Under v2 an entity mention
    landed on one by that topic ('actress' on a claim about one silent-film
    actress), and so did another paragraph's concept ("Disambiguation" pages of
    unrelated titles on one node)."""
    claim = _node_tagged(
        ["actress", "film producer", "paragraph_concept"],
        "American actress and film producer of the early silent film era.",
        vec=_unit(1.0, 0.1),
    )
    page = _node_tagged(
        ["disambiguation", "paragraph_concept"], "Disambiguation", vec=_unit(0.1, 1.0)
    )
    names = _linker(tmp_path, claim, page)
    assert _link(names, "actress", ["profession"], _unit(1.0, 0.11)).is_new
    assert _link_paragraph_concept(
        names, "Disambiguation", ["disambiguation"], _unit(0.1, 1.0)
    ).is_new
    v2 = _linker(tmp_path / "v2", claim, page, naming_guard="v2")
    assert _link(v2, "actress", ["profession"], _unit(1.0, 0.11)).node.id == claim.id
    assert (
        _link_paragraph_concept(v2, "Disambiguation", ["disambiguation"], _unit(0.1, 1.0)).node.id
        == page.id
    )


def test_a_paragraph_concept_is_named_like_any_mention(tmp_path: Path) -> None:
    """Under v2 a paragraph's summary joined the entity it is about, and another
    person's career joined the first career, each on a shared tag. Neither label
    names the node it joined."""
    goss = _node("Luke Goss", "singer", "person", vec=_unit(1.0, 0.1))
    career = _node_tagged(
        ["career", "filmography", "paragraph_concept"], "Luke Goss's career", vec=_unit(0.1, 1.0)
    )
    names = _linker(tmp_path, goss, career)
    summary = _link_paragraph_concept(
        names, "Luke Goss's career", ["Luke Goss", "career"], _unit(1.0, 0.11)
    )
    other = _link_paragraph_concept(
        names, "Dan Milne's career", ["career", "filmography"], _unit(0.1, 1.0)
    )
    assert summary.is_new and other.is_new
    v2 = _linker(tmp_path / "v2", goss, career, naming_guard="v2")
    assert (
        _link_paragraph_concept(
            v2, "Luke Goss's career", ["Luke Goss", "career"], _unit(1.0, 0.11)
        ).node.id
        == goss.id
    )
    assert (
        _link_paragraph_concept(
            v2, "Dan Milne's career", ["career", "filmography"], _unit(0.1, 1.0)
        ).node.id
        == career.id
    )


def test_names_entities_names_an_entity_mention_and_leaves_paragraph_concepts_to_v2(
    tmp_path: Path,
) -> None:
    """The arm that tells the two layers apart: an entity mention is guarded by
    name, and no entity mention lands on a paragraph concept, while a paragraph
    concept joins what v2 lets it join."""
    book = _node("Drømmen og hjulet", "Jens Bjørneboe", "novel", vec=_unit(1.0, 0.1))
    career = _node_tagged(
        ["career", "filmography", "paragraph_concept"], "Luke Goss's career", vec=_unit(0.1, 1.0)
    )
    linker = _linker(tmp_path, book, career, naming_guard="names_entities")
    assert _link(linker, "Jens Bjørneboe", ["author", "person"], _unit(1.0, 0.12)).is_new
    assert _link(linker, "career", ["profession"], _unit(0.1, 1.0)).is_new
    other = _link_paragraph_concept(
        linker, "Dan Milne's career", ["career", "filmography"], _unit(0.1, 1.0)
    )
    assert other.node.id == career.id and not other.is_new


# --------------------------------------------------------------------------
# Through a read, with the tags the reader builds
# --------------------------------------------------------------------------

_P1 = "The Newport International Film Festival screened the film."
_P2 = "The Seattle International Film Festival screened it a year later."


def _reading(label: str) -> str:
    concept = {
        "label": label,
        "entity_type": "event",
        "tags": ["film festival"],
        "description": "A film festival",
        "qids": [],
    }
    return json.dumps({"concepts": [concept], "relations": [], "paragraph_concept": None})


def test_a_category_noun_inside_the_label_keeps_its_own_node(
    mesh_runtime: MeshRuntime, tmp_path: Path
) -> None:
    """Shape 2, end to end. The festivals share the tag 'film festival', which
    token-overlaps the label: v2 took Seattle's festival into Newport's on the
    tag tier (this is how Newport's grew to 123 mentions, the largest hub of the
    2Wiki mesh). Under names Seattle's festival is a node of its own, and the
    run's audit row says which guard built the workspace."""
    responses = {
        f"PARAGRAPH:\n{_P1}": _reading("Newport International Film Festival"),
        f"PARAGRAPH:\n{_P2}": _reading("Seattle International Film Festival"),
    }
    reader = MeshParagraphReader(
        mesh_runtime,
        llm=StubLLMProvider(responses=responses),
        max_paragraphs=10,
        naming_guard="names",
    )
    asyncio.run(
        reader.read_text(
            text=f"{_P1}\n\n{_P2}",
            source_type="test",
            source_identifier="festivals",
            title="Festivals",
            anchor=str(tmp_path / "festivals.txt"),
        )
    )
    names = {n.tags[0] for n in mesh_runtime.nodes.load_all_consolidated() if n.tags}
    assert {"Newport International Film Festival", "Seattle International Film Festival"} <= names
    rows = [
        json.loads(r["payload_json"])
        for r in mesh_runtime.audit.list_recent(limit=1000)
        if r["action"] in ("mesh_ingest_link_decision", "mesh_ingest_run")
    ]
    seattle = next(r for r in rows if r.get("label") == "Seattle International Film Festival")
    assert seattle["signal"] == "emergent"
    [run] = [r for r in rows if "naming_guard" in r]
    assert run["naming_guard"] == "names"


# --------------------------------------------------------------------------
# What the names guard costs on an epithet corpus, and the unchanged default
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("node_name", "label"),
    [
        # a qualifier on a lone name: Hesiod's "of Cyprus" is the same goddess,
        # 2Wiki's "Augustus, Duke of Saxe-Weissenfels" is not the same Augustus
        ("Aphrodite", "Aphrodite of Cyprus"),
        ("Dione", "Dione of Olympus"),
        # an epithet is not a name
        ("Zeus", "Zeus the Thunderer"),
    ],
)
def test_under_names_an_epithet_or_a_qualified_lone_name_stays_emergent(
    tmp_path: Path, node_name: str, label: str
) -> None:
    """A cost the measurement has to weigh: the v2 guard merged these on the
    shared tag (tests/mesh/test_ingestion_linker_identity_attractor.py and
    test_substrate_invariants.py pin it), the names guard leaves them to
    consolidation."""
    node = _node(node_name, node_name.casefold(), vec=_unit(1.0, 0.1))
    decision = _link(_linker(tmp_path, node), label, [node_name.casefold()], _unit(1.0, 0.12))
    assert decision.is_new


def test_under_names_a_remembered_alias_alone_no_longer_merges(tmp_path: Path) -> None:
    """Another cost: under v2 a label any earlier link attached admitted the next
    mention by itself, a right alias here (Jove is Zeus). The names guard
    consults no remembered label, because one wrong link would otherwise recruit
    the next with its label; no wrong link in the PHX-1120 sample came through
    that door, so closing it is a precaution."""
    zeus = _node("Zeus", "god", vec=_unit(0.0, 1.0))
    linker = _linker(tmp_path, zeus)
    linker._registry.remember(zeus, aliases=["Jove"], qids=[])
    assert _link(linker, "Jove", ["god"], _unit(0.05, 0.99)).is_new
    v2 = _linker(tmp_path / "v2", zeus, naming_guard="v2")
    v2._registry.remember(zeus, aliases=["Jove"], qids=[])
    assert not _link(v2, "Jove", ["god"], _unit(0.05, 0.99)).is_new


def test_the_default_guard_is_still_v2(tmp_path: Path) -> None:
    """The author lands on his book under the default, as before PHX-1122."""
    book = _node("Drømmen og hjulet", "Jens Bjørneboe", "novel", vec=_unit(1.0, 0.1))
    runtime = MeshRuntime(tmp_path / "default", semantic_dim=8, frame_dim=4)
    runtime.nodes.append_consolidated(book)
    linker = EagerLinker(runtime.nodes, runtime.edges, semantic_dim=8, frame_dim=4)
    assert linker.naming_guard == "v2"
    decision = _link(linker, "Jens Bjørneboe", ["author", "person"], _unit(1.0, 0.12))
    assert decision.node.id == book.id and not decision.is_new


def test_an_unknown_guard_is_refused(tmp_path: Path) -> None:
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    with pytest.raises(ValueError, match="naming_guard"):
        EagerLinker(
            runtime.nodes,
            runtime.edges,
            semantic_dim=8,
            frame_dim=4,
            naming_guard="v3",  # type: ignore[arg-type]
        )
