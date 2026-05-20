"""End-to-end acceptance tests against the two example screenshots.

These assert the *full* pipeline: the parser reads the exact board,
constraints and dominoes, and the energy solver returns an independently
verified energy-0 solution.
"""
import os
from collections import Counter

import pytest

from pips.model import ConstraintKind
from pips.parser import parse_screenshot
from pips.solver import solve, verify_solution

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _shot(name):
    return os.path.join(ROOT, "example-screenshots", name)


def _constraint_multiset(puzzle):
    return Counter(
        (r.constraint.kind, r.constraint.target, len(r.cells))
        for r in puzzle.regions.values()
    )


EASY = dict(
    path="easy-example.png",
    n_cells=8,
    dominoes=Counter([(2, 2), (5, 5), (2, 4), (1, 2)]),
    constraints=Counter({
        (ConstraintKind.SUM_EQ, 6, 3): 1,
        (ConstraintKind.SUM_LT, 5, 1): 1,
        (ConstraintKind.SUM_EQ, 9, 2): 1,
        (ConstraintKind.NONE, None, 2): 1,
    }),
)

MEDIUM = dict(
    path="medium-example.png",
    n_cells=14,
    dominoes=Counter([(4, 3), (5, 5), (3, 2), (5, 3), (4, 0), (6, 6), (0, 3)]),
    constraints=Counter({
        (ConstraintKind.ALL_EQUAL, None, 3): 1,
        (ConstraintKind.NONE, None, 2): 1,    # r2c0 + r3c0 (adjacent)
        (ConstraintKind.NONE, None, 1): 1,    # r0c5 (separate)
        (ConstraintKind.ALL_DIFFERENT, None, 3): 1,
        (ConstraintKind.ALL_EQUAL, None, 2): 1,
        (ConstraintKind.SUM_EQ, 8, 2): 1,
        (ConstraintKind.SUM_LT, 5, 1): 1,
    }),
)


HARD = dict(
    path="hard-example.png",
    n_cells=28,
    dominoes=Counter([(5, 3), (5, 2), (4, 4), (0, 0), (6, 3), (1, 0),
                      (4, 0), (6, 2), (5, 5), (4, 6), (2, 1), (3, 3),
                      (0, 6), (2, 3)]),
    constraints=Counter({
        (ConstraintKind.ALL_EQUAL, None, 3): 1,
        (ConstraintKind.NONE, None, 1): 4,
        (ConstraintKind.SUM_EQ, 3, 1): 3,
        (ConstraintKind.SUM_EQ, 7, 2): 1,
        (ConstraintKind.SUM_EQ, 7, 3): 1,
        (ConstraintKind.SUM_EQ, 11, 2): 1,
        (ConstraintKind.SUM_EQ, 14, 3): 1,
        (ConstraintKind.SUM_GT, 1, 1): 1,
        (ConstraintKind.SUM_GT, 2, 1): 2,
        (ConstraintKind.SUM_GT, 4, 1): 1,
        (ConstraintKind.SUM_GT, 11, 2): 1,
        (ConstraintKind.SUM_LT, 2, 1): 2,
    }),
)

HARD2 = dict(
    path="hard-example-2.png",
    n_cells=26,
    dominoes=Counter([(0, 1), (1, 1), (1, 2), (1, 3), (1, 5), (2, 2),
                      (3, 3), (3, 5), (4, 4), (4, 5), (4, 6), (5, 6),
                      (6, 6)]),
    constraints=Counter({
        (ConstraintKind.ALL_EQUAL, None, 4): 2,
        (ConstraintKind.NONE, None, 1): 1,
        (ConstraintKind.SUM_EQ, 2, 2): 1,
        (ConstraintKind.SUM_EQ, 8, 2): 2,
        (ConstraintKind.SUM_EQ, 9, 2): 2,
        (ConstraintKind.SUM_EQ, 9, 3): 2,
        (ConstraintKind.SUM_GT, 0, 1): 1,
    }),
)

HARD3 = dict(
    path="hard-example-3.png",
    n_cells=30,
    dominoes=Counter([(0, 1), (0, 2), (0, 3), (0, 4), (1, 4), (1, 5),
                      (1, 6), (2, 2), (2, 3), (2, 6), (3, 4), (4, 5),
                      (4, 6), (5, 5), (6, 6)]),
    constraints=Counter({
        (ConstraintKind.ALL_DIFFERENT, None, 6): 1,
        (ConstraintKind.ALL_EQUAL, None, 3): 2,
        (ConstraintKind.ALL_EQUAL, None, 4): 1,
        (ConstraintKind.SUM_EQ, 0, 1): 1,
        (ConstraintKind.SUM_EQ, 0, 3): 1,
        (ConstraintKind.SUM_EQ, 1, 1): 1,
        (ConstraintKind.SUM_EQ, 2, 2): 1,
        (ConstraintKind.SUM_EQ, 7, 2): 1,
        (ConstraintKind.SUM_EQ, 12, 2): 2,
        (ConstraintKind.SUM_GT, 2, 1): 1,
    }),
)

ALL = [EASY, MEDIUM, HARD, HARD2, HARD3]
IDS = ["easy", "medium", "hard", "hard2", "hard3"]


@pytest.mark.parametrize("case", ALL, ids=IDS)
def test_parse(case):
    p = parse_screenshot(_shot(case["path"]))
    assert len(p.cells) == case["n_cells"]
    assert len(p.cells) == 2 * len(p.dominoes)
    assert Counter(tuple(sorted(d)) for d in p.dominoes) == Counter(
        tuple(sorted(d)) for d in case["dominoes"]
    )
    assert _constraint_multiset(p) == case["constraints"]


@pytest.mark.parametrize("case", ALL, ids=IDS)
def test_solve(case):
    p = parse_screenshot(_shot(case["path"]))
    sol = solve(p)
    assert sol is not None
    assert sol.energy == 0
    verify_solution(p, sol)


@pytest.mark.parametrize("case", ALL, ids=IDS)
def test_layout(case):
    from pips.render import solution_layout
    p = parse_screenshot(_shot(case["path"]))
    sol = solve(p)
    lay = solution_layout(p, sol)
    assert lay["n_h"] + lay["n_v"] == len(p.dominoes)
    seen = 0
    for cl in lay["clusters"]:
        for pl in cl["placements"]:
            assert pl["orient"] in ("H", "V")
        for cell in cl["cells"]:
            assert cell["val"] is not None  # solved board has every value
            seen += 1
    assert seen == len(p.cells)
