"""Per-image unit tests for the parser and the solver modules.

For every example screenshot there is one parser test and one solver
test.  Each asserts the module's output against an explicit golden file
in ``tests/expected/`` (regenerate with
``python tools/build_test_expectations.py`` when a behaviour change is
intentional).

This suite is the pre-deploy gate: ``tools/run_pre_deploy_tests.py``
runs it, and the ``.githooks/pre-push`` hook runs that before any push.
"""
import json
import os

import pytest

from pips.parser import parse_screenshot
from pips.solver import solve, verify_solution

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_DIR = os.path.join(ROOT, "tests", "expected")

# every example image -> short test id (must match build_test_expectations)
IMAGES = {
    "easy": "easy-example.png",
    "medium": "medium-example.png",
    "hard": "hard-example.png",
    "hard2": "hard-example-2.png",
    "hard3": "hard-example-3.png",
    "mobile-easy": "mobile-easy.png",
    "mobile-medium": "mobile-medium.png",
    "mobile-hard": "mobile-hard.png",
}
IDS = sorted(IMAGES)


def _expected(test_id: str) -> dict:
    with open(os.path.join(EXPECTED_DIR, f"{test_id}.json")) as fh:
        return json.load(fh)


def _shot(name: str) -> str:
    return os.path.join(ROOT, "example-screenshots", name)


@pytest.mark.parametrize("test_id", IDS)
def test_parser(test_id):
    """The parser turns each screenshot into the exact expected board."""
    exp = _expected(test_id)["parser"]
    puzzle = parse_screenshot(_shot(IMAGES[test_id]))

    assert len(puzzle.cells) == exp["n_cells"], "cell count"
    assert len(puzzle.dominoes) == exp["n_dominoes"], "domino count"
    assert len(puzzle.cells) == 2 * len(puzzle.dominoes), \
        "cells must be exactly twice the dominoes"

    got_dominoes = sorted(sorted(d) for d in puzzle.dominoes)
    assert got_dominoes == [sorted(d) for d in exp["dominoes"]], "dominoes"

    got_constraints = sorted(
        [r.constraint.kind.name, r.constraint.target, len(r.cells)]
        for r in puzzle.regions.values()
    )
    assert got_constraints == [list(c) for c in exp["constraints"]], \
        "region constraints"


@pytest.mark.parametrize("test_id", IDS)
def test_solver(test_id):
    """The solver returns the exact expected, independently-verified
    energy-0 solution for each parsed board."""
    exp = _expected(test_id)["solver"]
    puzzle = parse_screenshot(_shot(IMAGES[test_id]))
    sol = solve(puzzle)

    assert (sol is not None) == exp["solved"], "solvability"
    if not exp["solved"]:
        return

    assert sol.energy == 0, "solution energy must be 0"
    verify_solution(puzzle, sol)        # independent re-check of the tiling

    got_values = sorted([list(cell), v] for cell, v in sol.value.items())
    assert got_values == [list(x) for x in exp["values"]], \
        "solved cell values"
