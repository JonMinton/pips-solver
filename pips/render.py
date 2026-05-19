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


def solution_layout(puzzle: Puzzle, sol: Optional[Solution]) -> dict:
    """Structured geometry for a graphical (SVG) render.

    Cells carry their (cluster-local) grid position, region, colour and
    solved value; every domino placement is tagged ``"H"`` (horizontal)
    or ``"V"`` (vertical).
    """
    clusters: Dict[int, dict] = {}
    for (r, c) in puzzle.cells:
        k = r // GAP
        cl = clusters.setdefault(k, {"cells": []})
        rid = puzzle.region_of[(r, c)]
        cl["cells"].append({
            "r": r % GAP, "c": c, "region": rid,
            "color": list(puzzle.regions[rid].color),
            "val": (sol.value[(r, c)] if sol else None),
        })

    placements = []
    n_h = n_v = 0
    if sol:
        for (a, b, (va, vb)) in sol.placements:
            horiz = a[0] == b[0]
            n_h += horiz
            n_v += not horiz
            placements.append({
                "cluster": a[0] // GAP,
                "a": [a[0] % GAP, a[1]], "b": [b[0] % GAP, b[1]],
                "va": va, "vb": vb,
                "orient": "H" if horiz else "V",
            })

    out = []
    for k in sorted(clusters):
        cells = clusters[k]["cells"]
        out.append({
            "minr": min(x["r"] for x in cells),
            "maxr": max(x["r"] for x in cells),
            "minc": min(x["c"] for x in cells),
            "maxc": max(x["c"] for x in cells),
            "cells": cells,
            "placements": [p for p in placements if p["cluster"] == k],
        })
    return {"clusters": out, "n_h": n_h, "n_v": n_v}


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
