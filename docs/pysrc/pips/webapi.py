"""Browser entry point (called from JavaScript via Pyodide).

The web app writes the input image to ``/tmp/in.png`` in the Pyodide
virtual filesystem, then calls :func:`run`.  Everything else is the
exact same parser and solver used by the CLI, so results are identical.
"""
from __future__ import annotations

import time

from .parser import parse
from .render import render_puzzle, render_solution
from .solver import solve, verify_solution

INPUT_PATH = "/tmp/in.png"


def run(path: str = INPUT_PATH) -> dict:
    t0 = time.perf_counter()
    res = parse(path)
    t1 = time.perf_counter()
    sol = solve(res.puzzle)
    t2 = time.perf_counter()

    verified = False
    if sol is not None:
        try:
            verify_solution(res.puzzle, sol)
            verified = sol.energy == 0
        except AssertionError:
            verified = False

    p = res.puzzle
    return {
        "parsed": render_puzzle(p),
        "solution": render_solution(p, sol),
        "parse_ms": round((t1 - t0) * 1000, 1),
        "solve_ms": round((t2 - t1) * 1000, 1),
        "solved": sol is not None and sol.energy == 0,
        "verified": verified,
        "n_cells": len(p.cells),
        "n_dominoes": len(p.dominoes),
        "n_regions": len(p.regions),
        "n_clusters": res.debug.get("n_clusters", 1),
    }
