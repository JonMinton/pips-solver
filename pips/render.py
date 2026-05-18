"""Text rendering of a parsed puzzle and its solution."""
from __future__ import annotations

from typing import Optional

from .model import Puzzle, Solution


def _bbox(puzzle: Puzzle):
    rs = [r for r, _ in puzzle.cells]
    cs = [c for _, c in puzzle.cells]
    return min(rs), max(rs), min(cs), max(cs)


def render_puzzle(puzzle: Puzzle) -> str:
    r0, r1, c0, c1 = _bbox(puzzle)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lines = []
    for r in range(r0, r1 + 1):
        row = []
        for c in range(c0, c1 + 1):
            if (r, c) in puzzle.region_of:
                row.append(letters[puzzle.region_of[(r, c)] % 26])
            else:
                row.append(".")
        lines.append(" ".join(row))
    out = ["Board (each letter = a region):", *lines, "", "Regions:"]
    for rid in sorted(puzzle.regions):
        reg = puzzle.regions[rid]
        out.append(
            f"  {letters[rid % 26]}: {reg.constraint.describe():<18} "
            f"{len(reg.cells)} cell(s)"
        )
    doms = " ".join(f"[{a}|{b}]" for a, b in puzzle.dominoes)
    out += ["", f"Dominoes ({len(puzzle.dominoes)}): {doms}"]
    return "\n".join(out)


def render_solution(puzzle: Puzzle, sol: Optional[Solution]) -> str:
    if sol is None:
        return "No solution found (puzzle infeasible as parsed)."
    r0, r1, c0, c1 = _bbox(puzzle)
    lines = []
    for r in range(r0, r1 + 1):
        row = []
        for c in range(c0, c1 + 1):
            row.append(str(sol.value[(r, c)]) if (r, c) in sol.value else ".")
        lines.append(" ".join(row))
    out = [f"Solution (energy = {sol.energy}):", *lines, "", "Checks:"]
    for rid in sorted(puzzle.regions):
        reg = puzzle.regions[rid]
        vals = [sol.value[c] for c in reg.cells]
        viol = reg.constraint.violation(vals)
        mark = "ok " if viol == 0 else "BAD"
        out.append(
            f"  [{mark}] region {rid} {reg.constraint.describe():<18} "
            f"values={vals}"
        )
    return "\n".join(out)
