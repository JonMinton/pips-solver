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
        (ConstraintKind.NONE, None, 3): 1,
        (ConstraintKind.ALL_DIFFERENT, None, 3): 1,
        (ConstraintKind.ALL_EQUAL, None, 2): 1,
        (ConstraintKind.SUM_EQ, 8, 2): 1,
        (ConstraintKind.SUM_LT, 5, 1): 1,
    }),
)


@pytest.mark.parametrize("case", [EASY, MEDIUM], ids=["easy", "medium"])
def test_parse(case):
    p = parse_screenshot(_shot(case["path"]))
    assert len(p.cells) == case["n_cells"]
    assert len(p.cells) == 2 * len(p.dominoes)
    assert Counter(tuple(sorted(d)) for d in p.dominoes) == Counter(
        tuple(sorted(d)) for d in case["dominoes"]
    )
    assert _constraint_multiset(p) == case["constraints"]


@pytest.mark.parametrize("case", [EASY, MEDIUM], ids=["easy", "medium"])
def test_solve(case):
    p = parse_screenshot(_shot(case["path"]))
    sol = solve(p)
    assert sol is not None
    assert sol.energy == 0
    verify_solution(p, sol)
