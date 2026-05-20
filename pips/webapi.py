"""Browser entry point (called from JavaScript via Pyodide).

The web app writes the input image to ``/tmp/in.png`` in the Pyodide
virtual filesystem, then calls :func:`run`.  Everything else is the
exact same parser and solver used by the CLI, so results are identical.

``run`` returns the parsed puzzle as an editable *structure* together
with per-item confidence flags, so the front-end can show a review
panel for low-confidence items.  When the user edits and confirms,
:func:`solve_structured` rebuilds the puzzle from the (possibly edited)
structure and re-runs the solver — bypassing the parser entirely so
corrections always stick.
"""
from __future__ import annotations

import time
from typing import Optional

from .model import Constraint, ConstraintKind, Puzzle, Region
from .parser import parse
from .render import render_puzzle, render_solution, solution_layout
from .solver import solve, verify_solution

INPUT_PATH = "/tmp/in.png"

# Confidence thresholds for "low" flagging (tuned on the sample puzzles
# so that observed mis-reads stand out but correct ones never do).
GLYPH_SCORE_FLAG = 0.85
GLYPH_MARGIN_FLAG = 0.06
TAG_COST_FLAG = 32.0
CELL_COV_FLAG = 0.70
BORDERLINE_PIP_FLAG = 1


def _structure_from_puzzle(p: Puzzle, debug: dict) -> dict:
    rconf = debug.get("region_conf", {})
    dconf = debug.get("domino_conf", [])
    cconf = debug.get("cell_conf", {})

    cells = []
    for (r, c) in sorted(p.cells):
        cells.append({
            "id": f"{r}_{c}",
            "r": r, "c": c,
            "rid": p.region_of[(r, c)],
            "cov": round(cconf.get((r, c), 1.0), 3),
        })

    regions = []
    for rid in sorted(p.regions):
        reg = p.regions[rid]
        info = rconf.get(rid, {})
        regions.append({
            "id": rid,
            "kind": reg.constraint.kind.name,
            "target": reg.constraint.target,
            "color": list(reg.color),
            "n_cells": len(reg.cells),
            "labels": list(info.get("labels", [])),
            "score": round(info.get("glyph_score", 1.0), 3),
            "margin": round(info.get("glyph_margin", 1.0), 3),
            "cost": round(info.get("match_cost", 0.0), 2),
        })

    dominoes = []
    for i, (a, b) in enumerate(p.dominoes):
        info = dconf[i] if i < len(dconf) else {}
        dominoes.append({
            "id": i, "a": int(a), "b": int(b),
            "borderline_a": int(info.get("borderline_a", 0)),
            "borderline_b": int(info.get("borderline_b", 0)),
        })

    return {"cells": cells, "regions": regions, "dominoes": dominoes}


def _flags_for(structure: dict) -> list:
    flags = []
    for r in structure["regions"]:
        reasons = []
        if r["kind"] != "NONE":
            if r["score"] < GLYPH_SCORE_FLAG:
                reasons.append(f"glyph match score {r['score']} is low")
            if r["margin"] < GLYPH_MARGIN_FLAG:
                reasons.append(f"runner-up template is close ({r['margin']})")
            if r["cost"] > TAG_COST_FLAG:
                reasons.append(f"tag→region assignment cost {r['cost']} is high")
        if reasons:
            flags.append({"kind": "region", "id": r["id"],
                          "reasons": reasons})
    for d in structure["dominoes"]:
        if (d["borderline_a"] >= BORDERLINE_PIP_FLAG or
                d["borderline_b"] >= BORDERLINE_PIP_FLAG):
            flags.append({"kind": "domino", "id": d["id"],
                          "reasons": ["borderline pip-blob size"]})
    for c in structure["cells"]:
        if c["cov"] < CELL_COV_FLAG:
            flags.append({"kind": "cell", "id": c["id"],
                          "reasons": [f"slot coverage {c['cov']} is low"]})
    return flags


def _puzzle_from_structure(structure: dict, color_fallback) -> Puzzle:
    region_of = {}
    for c in structure["cells"]:
        region_of[(int(c["r"]), int(c["c"]))] = int(c["rid"])
    cells = sorted(region_of)

    regions = {}
    for r in structure["regions"]:
        rid = int(r["id"])
        kind = ConstraintKind[r["kind"]]
        target = r.get("target")
        target = int(target) if target is not None else None
        cons = Constraint(kind, target) if kind is not ConstraintKind.NONE \
            else Constraint(ConstraintKind.NONE)
        member = [c for c in cells if region_of[c] == rid]
        color = tuple(int(v) for v in r.get(
            "color", color_fallback.get(rid, (200, 200, 200))))
        regions[rid] = Region(rid=rid, constraint=cons,
                              cells=member, color=color)

    # drop empty regions (the user may have moved all cells out)
    regions = {rid: reg for rid, reg in regions.items() if reg.cells}

    dominoes = [(int(d["a"]), int(d["b"])) for d in structure["dominoes"]]
    return Puzzle(cells=cells, region_of=region_of,
                  regions=regions, dominoes=dominoes)


def _solve_and_report(p: Puzzle) -> dict:
    t = time.perf_counter()
    try:
        p.validate()
        valid = True
        err = None
    except ValueError as e:
        valid = False
        err = str(e)
    sol = solve(p) if valid else None
    solve_ms = round((time.perf_counter() - t) * 1000, 1)

    verified = False
    if sol is not None:
        try:
            verify_solution(p, sol)
            verified = sol.energy == 0
        except AssertionError:
            verified = False
    return {
        "solution_text": render_solution(p, sol),
        "layout": solution_layout(p, sol),
        "solve_ms": solve_ms,
        "solved": sol is not None and sol.energy == 0,
        "verified": verified,
        "n_cells": len(p.cells),
        "n_dominoes": len(p.dominoes),
        "n_regions": len(p.regions),
        "valid": valid,
        "error": err,
    }


def run(path: str = INPUT_PATH) -> dict:
    t0 = time.perf_counter()
    res = parse(path)
    parse_ms = round((time.perf_counter() - t0) * 1000, 1)
    p = res.puzzle
    structure = _structure_from_puzzle(p, res.debug)
    flags = _flags_for(structure)
    out = {
        "parse_ms": parse_ms,
        "parsed_text": render_puzzle(p),
        "structure": structure,
        "flags": flags,
        "needs_review": bool(flags),
        "n_clusters": res.debug.get("n_clusters", 1),
    }
    if not flags:
        out.update(_solve_and_report(p))
        out["parsed"] = out.pop("solution_text", "")
        out["parsed"] = render_puzzle(p)
        out["solution"] = render_solution(p, solve(p))
    return out


def solve_structured(structure: dict) -> dict:
    color_fallback = {int(r["id"]): tuple(r.get("color", (200, 200, 200)))
                      for r in structure["regions"]}
    p = _puzzle_from_structure(structure, color_fallback)
    rep = _solve_and_report(p)
    rep["parsed"] = render_puzzle(p)
    rep["solution"] = rep.pop("solution_text")
    rep["structure"] = _structure_from_puzzle(p, debug={
        "region_conf": {}, "domino_conf": [], "cell_conf": {},
    })
    return rep
