"""Seeds drawn from all four weight classes.

`MESH_MIGRATION_PLAN.md` §"Step S3" names this test and the module it exercises
as deliverables. Neither existed. What shipped was a hub cap inside
`select_seeds`, and it differed from the doctrine in two ways that measurement
makes concrete (PHX-1091):

  - classes were quantiles over whichever ≤64 candidates the ANN returned, so a
    node's class depended on who else was retrieved. On the founding mesh the
    pool's median p25 is 3.71 against a global 1.16, and its p95 is 47.14 against
    17.13 — the "hub" being capped was a different set on every query.
  - only the hub class had a bound. The other three took whatever the MMR order
    gave them, which is not stratification.

Measured after: micro 1.66 seats per question with 1 question of 47 lacking one,
medium and large in every question, hub 2.09 with no floor. Recall 77% -> 80%,
questions answered in full 36 -> 38.
"""

from __future__ import annotations

from theogony.mesh.stratification import (
    CLASS_NAMES,
    class_seats,
    global_weight_classes,
)


def test_boundaries_are_the_doctrines_percentiles() -> None:
    """p25 / p75 / p95 — MESH_RETRIEVAL §"Weight-class stratification"."""
    classes = global_weight_classes([float(i) for i in range(101)])
    assert classes.population == 101
    assert classes.of(0.0) == 0, "micro"
    assert classes.of(50.0) == 1, "medium"
    assert classes.of(90.0) == 2, "large"
    assert classes.of(100.0) == 3, "hub"
    assert len(CLASS_NAMES) == 4


def test_every_present_class_gets_a_seat() -> None:
    """The guarantee the doctrine asks for: a route exists by construction.

    The MMR order here is adversarial — it front-loads one class entirely, which
    is what a query landing in a dense region does.
    """
    classes = [1, 1, 1, 1, 1, 1, 0, 2, 3]
    order = list(range(9))
    chosen = class_seats(classes, order, k=4)
    assert {classes[p] for p in chosen} >= {0, 1, 2}, (
        "micro, medium and large must each be seated; without the guarantee the "
        "first four of the MMR order are all medium"
    )


def test_relevance_takes_the_first_seat() -> None:
    """A guarantee that displaces the answer is not a guarantee worth having.

    Seating the lowest class first meant that at k=1 the most query-relevant
    candidate could be shut out entirely — caught by PHX-1042's
    `test_hub_mask_never_masks_a_seed`, where a query issued with a hub's own
    vector stopped seeding on that hub.
    """
    classes = [3, 0, 1, 2]
    chosen = class_seats(classes, order=[0, 1, 2, 3], k=1)
    assert chosen == [0], "the top of the MMR order is seated before any class guarantee"


def test_the_hub_class_gets_a_cap_and_no_floor() -> None:
    """Giving the class the doctrine caps a floor as well is incoherent.

    It is also observable: guaranteeing the hub a seat made `hub_mask_top_n`
    inert, because the mask never masks a seed — so the lever that exists to
    demote a degree-attracted hub could no longer reach the hub stratification
    had just seeded.
    """
    classes = [1, 3, 3, 3, 0]
    chosen = class_seats(classes, order=[0, 1, 2, 3, 4], k=4, max_hub_fraction=0.5)
    assert sum(1 for p in chosen if classes[p] == 3) <= 2, "capped at half of k"
    # and a hub still gets in on relevance alone
    chosen = class_seats([3, 3, 1], order=[0, 1, 2], k=2)
    assert 0 in chosen


def test_an_absent_class_is_left_empty_rather_than_borrowed() -> None:
    """A seat cannot be filled from an empty class, and pretending is worse."""
    classes = [1, 1, 1]
    chosen = class_seats(classes, order=[0, 1, 2], k=3)
    assert sorted(chosen) == [0, 1, 2]
    assert {classes[p] for p in chosen} == {1}


def test_the_full_budget_is_used_even_when_the_cap_bites() -> None:
    classes = [3, 3, 3, 3, 3, 3]
    chosen = class_seats(classes, order=list(range(6)), k=4, max_hub_fraction=0.25)
    assert len(chosen) == 4, "the cap must not return fewer seeds than asked for"


def test_no_candidates_no_seats() -> None:
    assert class_seats([], [], k=4) == []
    assert class_seats([0, 1], [0, 1], k=0) == []
