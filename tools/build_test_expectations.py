"""Generate the golden expected-output files used by the unit tests.

For every example screenshot this records what the *parser* and the
*solver* modules currently produce, into ``tests/expected/<name>.json``.
Run this only when a change to parser/solver behaviour is intentional;
the committed JSON files are the contract the unit tests enforce.

    python tools/build_test_expectations.py
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pips.parser import parse_screenshot
from pips.solver import solve, verify_solution

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "example-screenshots")
EXPECTED = os.path.join(ROOT, "tests", "expected")

# every example image -> a short test id
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

# images where the parser is known to mis-read exactly one tag at very
# small render scale (surfaced live by the app's Help-Me review mode).
# The golden files capture the *actual* deterministic output so the
# suite is a true regression gate; this dict documents the deviation.
KNOWN_MISREADS = {
    "mobile-easy": "one '=' tag is read as 'sum = 1'",
    "mobile-hard": "one 'sum = 1' tag is read as '!='",
}


def expectation(image_path: str) -> dict:
    puzzle = parse_screenshot(image_path)
    parser_out = {
        "n_cells": len(puzzle.cells),
        "n_dominoes": len(puzzle.dominoes),
        "dominoes": sorted(sorted(d) for d in puzzle.dominoes),
        "constraints": sorted(
            [r.constraint.kind.name, r.constraint.target, len(r.cells)]
            for r in puzzle.regions.values()
        ),
    }
    sol = solve(puzzle)
    if sol is None:
        solver_out = {"solved": False}
    else:
        verify_solution(puzzle, sol)        # must hold for a golden
        solver_out = {
            "solved": True,
            "energy": sol.energy,
            "values": sorted([list(cell), v]
                             for cell, v in sol.value.items()),
        }
    return {"parser": parser_out, "solver": solver_out}


def main() -> None:
    os.makedirs(EXPECTED, exist_ok=True)
    for test_id, fname in IMAGES.items():
        exp = expectation(os.path.join(SHOTS, fname))
        exp["_image"] = fname
        if test_id in KNOWN_MISREADS:
            exp["_known_misread"] = KNOWN_MISREADS[test_id]
        out = os.path.join(EXPECTED, f"{test_id}.json")
        with open(out, "w") as fh:
            json.dump(exp, fh, indent=2)
        print(f"  {test_id:14s} cells={exp['parser']['n_cells']:3d} "
              f"dominoes={exp['parser']['n_dominoes']:3d} "
              f"solved={exp['solver'].get('solved')}")
    print(f"wrote {len(IMAGES)} expectation files to {EXPECTED}")


if __name__ == "__main__":
    main()
