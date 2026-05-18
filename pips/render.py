"""Text rendering of a parsed puzzle and its solution.

Boards may be several disconnected clusters; each cluster lives in its
own coordinate band (``row // 1000``) and is drawn as a separate block.
"""
from __future__ import annotations

from typing import Dict, Optional

from .model import Puzzle, Solution

GAP = 1000
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _blocks(cells):
    clusters: Dict[int, list] = {}
    for (r, c) in cells:
        clusters.setdefault(r // GAP, []).append((r, c))
    return [clusters[k] for k in sorted(clusters)]


def _grid(block, glyph):
    rs = [r for r, _ in block]
    cs = [c for _, c in block]
    out = []
    for r in range(min(rs), max(rs) + 1):
        out.append(" ".join(
            glyph(r, c) if (r, c) in set(block) else "."
            for c in range(min(cs), max(cs) + 1)
        ))
    return out


def render_puzzle(puzzle: Puzzle) -> str:
    out = ["Board (each letter = a region):"]
    for bi, block in enumerate(_blocks(puzzle.cells)):
        if bi:
            out.append("")
        out += _grid(block,
                     lambda r, c: LETTERS[puzzle.region_of[(r, c)] % 52])
    out += ["", "Regions:"]
    for rid in sorted(puzzle.regions):
        reg = puzzle.regions[rid]
        out.append(
            f"  {LETTERS[rid % 52]}: {reg.constraint.describe():<18} "
            f"{len(reg.cells)} cell(s)"
        )
    doms = " ".join(f"[{a}|{b}]" for a, b in puzzle.dominoes)
    out += ["", f"Dominoes ({len(puzzle.dominoes)}): {doms}"]
    return "\n".join(out)


def render_solution(puzzle: Puzzle, sol: Optional[Solution]) -> str:
    if sol is None:
        return "No solution found (puzzle infeasible as parsed)."
    out = [f"Solution (energy = {sol.energy}):"]
    for bi, block in enumerate(_blocks(puzzle.cells)):
        if bi:
            out.append("")
        out += _grid(block, lambda r, c: str(sol.value[(r, c)]))
    out += ["", "Checks:"]
    for rid in sorted(puzzle.regions):
        reg = puzzle.regions[rid]
        vals = [sol.value[c] for c in reg.cells]
        viol = reg.constraint.violation(vals)
        out.append(
            f"  [{'ok ' if viol == 0 else 'BAD'}] region {rid} "
            f"{reg.constraint.describe():<18} values={vals}"
        )
    return "\n".join(out)
