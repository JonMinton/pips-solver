#!/usr/bin/env python3
"""Daily macro: fetch today's NYT Pips puzzles, screenshot, parse and solve.

Workflow:

1. Launch Chromium with a *persistent* user-data dir, so the one-time
   NYT login (if your account needs it) survives across runs.
2. Navigate to https://www.nytimes.com/games/pips.
3. For each difficulty (easy / medium / hard), click the matching
   button, wait for the puzzle to render, full-page screenshot to
   ``example-screenshots/daily/YYYY-MM-DD-<diff>.png``.
4. Run the existing parser + solver on each capture.
5. Write a per-day report to ``test-results/daily/YYYY-MM-DD.json``
   and print a console summary.

First-time setup (once):

    pip install playwright
    python -m playwright install chromium
    # then run interactively so you can log in if NYT prompts:
    python tools/daily_capture_and_solve.py            # headed
    # subsequent runs (or from launchd / cron) can be headless:
    python tools/daily_capture_and_solve.py --headless

If NYT redesigns the page and the difficulty selectors break,
override them on the command line:

    python tools/daily_capture_and_solve.py \\
        --easy "text=Easy" --medium "text=Medium" --hard "text=Hard"

Note: automated scraping of any site is your responsibility; capturing
your own daily puzzle for personal solving practice is fine in spirit,
but check the site's terms of service.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "example-screenshots" / "daily"
REPORTS = ROOT / "test-results" / "daily"
PROFILE = ROOT / ".browser-profile"
URL = "https://www.nytimes.com/games/pips"

# Default selectors.  Override with --easy / --medium / --hard if NYT
# changes the markup.  Each is tried as a Playwright locator; the first
# match wins.  Playwright supports CSS, text=, role=, aria=, etc.
DEFAULT_SELECTORS = {
    "easy":   "button:has-text(/easy/i)",
    "medium": "button:has-text(/medium/i)",
    "hard":   "button:has-text(/hard/i)",
}


def _ensure_dirs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROFILE.mkdir(exist_ok=True)


def navigate_and_capture(
        selectors: Dict[str, str], headless: bool,
        viewport_w: int, viewport_h: int) -> Dict[str, str]:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        sys.exit(
            "[daily] playwright is not installed. Install it once:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium\n")

    today = _dt.date.today().isoformat()
    captures: Dict[str, str] = {}

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=headless,
            viewport={"width": viewport_w, "height": viewport_h},
            device_scale_factor=2,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print(f"[daily] navigating to {URL} …")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)            # let the SPA settle

        for diff, sel in selectors.items():
            target = OUT / f"{today}-{diff}.png"
            print(f"[daily] {diff}: clicking selector {sel!r} …")
            try:
                page.locator(sel).first.click(timeout=4000)
                page.wait_for_timeout(1200)
            except PWTimeout:
                print(f"[daily]   (no '{diff}' button found — capturing "
                      "whatever is visible)")
            except Exception as e:                # noqa: BLE001
                print(f"[daily]   (click failed: {e})")
            page.screenshot(path=str(target), full_page=True)
            captures[diff] = str(target)
            print(f"[daily]   → {target}")
            page.wait_for_timeout(400)
        ctx.close()
    return captures


def solve_each(captures: Dict[str, str]) -> Dict[str, dict]:
    sys.path.insert(0, str(ROOT))
    from pips.parser import parse_screenshot
    from pips.solver import solve, verify_solution

    out: Dict[str, dict] = {}
    for diff, path in captures.items():
        if not os.path.exists(path):
            out[diff] = {"status": "missing"}; continue
        try:
            puzzle = parse_screenshot(path)
            sol = solve(puzzle)
            verified = False
            err: Optional[str] = None
            if sol is not None:
                try:
                    verify_solution(puzzle, sol); verified = sol.energy == 0
                except AssertionError as e:
                    err = str(e)
            out[diff] = {
                "status": "solved" if (sol and verified) else
                          ("unverified" if sol else "no_solution"),
                "n_cells": len(puzzle.cells),
                "n_dominoes": len(puzzle.dominoes),
                "n_regions": len(puzzle.regions),
                "energy": (sol.energy if sol else None),
                "verified": verified,
                "error": err,
            }
        except Exception as e:                    # noqa: BLE001
            out[diff] = {"status": "exception", "error": repr(e)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--headless", action="store_true",
                    help="Run Chromium without a visible window (use after "
                         "first-time interactive login).")
    ap.add_argument("--easy",   default=DEFAULT_SELECTORS["easy"])
    ap.add_argument("--medium", default=DEFAULT_SELECTORS["medium"])
    ap.add_argument("--hard",   default=DEFAULT_SELECTORS["hard"])
    ap.add_argument("--viewport-w", type=int, default=1280)
    ap.add_argument("--viewport-h", type=int, default=900)
    args = ap.parse_args()

    _ensure_dirs()
    selectors = {
        "easy": args.easy, "medium": args.medium, "hard": args.hard,
    }

    captures = navigate_and_capture(
        selectors, headless=args.headless,
        viewport_w=args.viewport_w, viewport_h=args.viewport_h)

    print("[daily] running parser + solver on captures …")
    results = solve_each(captures)

    today = _dt.date.today().isoformat()
    summary = {"date": today, "captures": captures, "results": results}
    report = REPORTS / f"{today}.json"
    with open(report, "w") as fh:
        json.dump(summary, fh, indent=2)

    print(f"\n=== {today} ===")
    any_failed = False
    for diff, r in results.items():
        st = r.get("status")
        if st == "solved":
            print(f"  {diff:7s} solved — {r['n_cells']} cells, "
                  f"{r['n_dominoes']} dominoes, energy {r['energy']}, ✓")
        else:
            any_failed = True
            extra = r.get("error") or ""
            print(f"  {diff:7s} {st}  {extra[:100]}")
    print(f"\n  report: {report}")
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
