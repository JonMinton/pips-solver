#!/usr/bin/env python3
"""CLI: parse a NYT Pips screenshot and solve it.

    python solve.py example-screenshots/easy-example.png [--debug]
"""
import argparse
import sys
import time

from pips.parser import parse
from pips.render import render_puzzle, render_solution
from pips.solver import solve


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Solve a NYT Pips screenshot.")
    ap.add_argument("screenshot")
    ap.add_argument("--debug", action="store_true",
                    help="print parser diagnostics")
    args = ap.parse_args(argv)

    res = parse(args.screenshot, debug=args.debug)
    if args.debug:
        d = res.debug
        print(f"[debug] separator row={d['separator']} pitch={d['pitch']} "
              f"clusters={d['n_clusters']} regions={d['n_regions']} "
              f"free-regions={d['n_free']}")
        for bbox, desc, rid in d["tags"]:
            print(f"[debug] tag {bbox} -> {desc!r} -> region {rid}")
        print()

    print(render_puzzle(res.puzzle))
    print()
    t = time.perf_counter()
    sol = solve(res.puzzle)
    dt = (time.perf_counter() - t) * 1000
    print(render_solution(res.puzzle, sol))
    print(f"\nSolved in {dt:.1f} ms")
    return 0 if sol is not None and sol.energy == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
